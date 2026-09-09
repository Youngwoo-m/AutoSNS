"""이미 올린 인스타 게시물 캡션에 활성화 문구(저장·팔로우 유도)를 덧붙인다.

⚠ 미검증 — 실제로 쓰지 말 것(2026-09-09). 첫 시험에서 캡션 입력칸이
   contenteditable 이라 커서가 끝으로 가지 않아 문구가 문단 중간에 끼어들었고
   (게시물 DdDxHXDGjad 캡션 손상), 전체 선택 후 재입력·execCommand 교체 두 방식의
   복구도 실패했다. 편집 저장 경로를 다시 검증하기 전에는 --go 로 돌리지 말 것.
   새 게시물은 post_instagram 이 발행 시점에 문구를 넣으므로 이 도구 없이도 된다.

새 게시물은 post_instagram 이 자동으로 넣지만, 그전 게시물에는 없어서 도달·전환에
기여하지 못한다. 캡션 끝에 저장 유도 + 팔로우 CTA 를 덧붙인다.

인스타는 짧은 시간의 대량 편집을 스팸으로 보고 액션을 막을 수 있으므로:
  - 기본 dry_run=True(무엇을 고칠지만 출력).
  - 1회 실행 한도(기본 15건)와 편집 간 랜덤 지연(기본 20~45초).
  - 이미 문구가 있으면 건너뛴다(멱등). 처리한 코드는 상태파일에 누적.
  - '차단/잠시 후 다시' 문구가 보이면 즉시 중단.

사용: python ig_caption_boost.py            # dry-run
      python ig_caption_boost.py --go [N]   # 실제 편집(N건까지)
"""
import json
import os
import random
import sys
import time

from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from common import load_config, log
from post_instagram import build_driver, shot

STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "caption_boost_state.json")
BLOCK_HINTS = ["작업이 차단", "잠시 후 다시", "제한되었습니다", "스팸"]


def _state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"done": [], "skipped": []}


def _save(s):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def _collect_codes(d, user, scrolls=12):
    """내 프로필 그리드에서 게시물 코드를 최신순으로 모은다."""
    import re
    d.get(f"https://www.instagram.com/{user}/")
    time.sleep(6)
    if "accounts/login" in d.current_url:
        raise RuntimeError("인스타 세션 만료 — ig_manual_login.py 로 로그인 필요")
    codes = []
    for _ in range(scrolls):
        for a in d.find_elements(By.CSS_SELECTOR, "main a[href*='/p/'], main a[href*='/reel/']"):
            m = re.search(r"/(?:p|reel)/([A-Za-z0-9_-]+)/", a.get_attribute("href") or "")
            if m:
                codes.append(m.group(1))
        d.execute_script("window.scrollBy(0,1800)")
        time.sleep(2)
    return list(dict.fromkeys(codes))


def _caption(d):
    """열려 있는 게시물의 캡션(og:description 안의 따옴표 부분)."""
    og = d.execute_script(
        "var m=document.querySelector('meta[property=\"og:description\"]');return m?m.content:''")
    return og.split(': "', 1)[1].rstrip('"') if ': "' in og else ""


def _click_text(d, labels, timeout=8):
    """보이는 텍스트/aria-label 이 labels 중 하나인 요소를 네이티브 클릭.

    React 는 JS element.click() 을 무시하는 경우가 있어 ActionChains 로 누른다."""
    end = time.time() + timeout
    while time.time() < end:
        for lb in labels:
            for xp in (f"//*[@aria-label='{lb}']",
                       f"//*[self::button or self::div or self::span][normalize-space()='{lb}']"):
                for e in d.find_elements(By.XPATH, xp):
                    try:
                        if not e.is_displayed():
                            continue
                        ActionChains(d).move_to_element(e).pause(0.3).click().perform()
                        return True
                    except StaleElementReferenceException:
                        return True
                    except Exception:
                        continue
        time.sleep(0.5)
    return False


def _blocked(d):
    try:
        body = d.find_element(By.TAG_NAME, "body").text
    except Exception:
        return False
    return any(h in body for h in BLOCK_HINTS)


def _edit_one(d, code, add_lines):
    """게시물 하나의 캡션 끝에 add_lines 를 덧붙인다. 반환: added|skip|error"""
    d.get(f"https://www.instagram.com/p/{code}/")
    time.sleep(random.uniform(3.0, 4.5))
    cap = _caption(d)
    need = [ln for ln in add_lines if ln.split("\n")[0][:12] not in cap]
    if not need:
        return "skip"
    if not _click_text(d, ["옵션 더 보기", "옵션", "더 보기 옵션", "More options"]):
        return "error"                      # '...' 메뉴 못 엶
    time.sleep(1.5)
    if not _click_text(d, ["수정", "Edit"]):
        return "error"
    time.sleep(random.uniform(2.5, 4.0))
    # 캡션 입력칸은 contenteditable div 이고, 같은 화면의 빈 textarea 가 함께 잡힌다.
    # 기존 캡션이 들어 있는(=내용이 가장 긴) 칸을 고른다.
    boxes = [b for b in d.find_elements(By.XPATH, "//textarea | //div[@contenteditable='true']")
             if b.is_displayed()]
    if not boxes:
        return "error"
    def _len(b):
        try:
            return len((b.get_attribute("value") or b.text or "").strip())
        except Exception:
            return 0
    box = max(boxes, key=_len)
    if _len(box) == 0:
        return "error"
    ActionChains(d).move_to_element(box).pause(0.3).click().perform()
    time.sleep(0.5)
    d.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", box)
    # 캡션 맨 끝으로 커서를 옮긴다. contenteditable 은 End/Cmd+↓ 로는 끝까지 가지 않아
    # (문단 중간에 끼어드는 사고가 났다) Selection API 로 확실히 끝에 붙인다.
    if box.tag_name == "textarea":
        d.execute_script("arguments[0].selectionStart = arguments[0].selectionEnd = "
                         "arguments[0].value.length;", box)
    else:
        d.execute_script(
            "const el=arguments[0]; el.focus();"
            "const r=document.createRange(); r.selectNodeContents(el); r.collapse(false);"
            "const s=window.getSelection(); s.removeAllRanges(); s.addRange(r);", box)
    time.sleep(0.3)
    for ln in need:
        box.send_keys("\n\n" + ln)
        time.sleep(0.4)
    time.sleep(1.0)
    if not _click_text(d, ["완료", "Done"]):
        return "error"
    time.sleep(random.uniform(3.0, 5.0))
    if _blocked(d):
        return "blocked"
    # 저장 확인: 게시물을 다시 열어 캡션에 문구가 들어갔는지 본다(편집창 오독 방지).
    d.get(f"https://www.instagram.com/p/{code}/")
    time.sleep(random.uniform(3.0, 4.0))
    cap_now = _caption(d)
    # 끝부분에 정확히 붙었는지 확인(중간 삽입 사고 방지). 마지막 줄 기준으로 본다.
    tail_ok = cap_now.rstrip().rstrip('"').endswith(need[-1].strip())
    return "added" if tail_ok else "error"


def run(go=False, limit=None):
    cfg = load_config()
    ig = cfg.get("instagram", {})
    user = ig["username"]
    add = [x for x in (ig.get("save_cta"), ig.get("follow_cta")) if x]
    limit = int(limit or ig.get("caption_boost_limit", 15))
    lo, hi = ig.get("caption_boost_delay", [20, 45])
    st = _state()
    done = set(st.get("done", []))
    d = build_driver(headless=ig.get("headless", True))
    added = errors = 0
    try:
        codes = [c for c in _collect_codes(d, user) if c not in done]
        log(f"미처리 게시물 {len(codes)}건 (이번 실행 최대 {limit}건, dry_run={not go})")
        for code in codes[:limit]:
            if not go:
                log(f"  [DRY] {code}")
                continue
            res = _edit_one(d, code, add)
            if res == "blocked":
                shot(d, "caption_blocked")
                log("⚠ 인스타 제한 감지 → 즉시 중단")
                break
            if res == "added":
                added += 1
                st.setdefault("done", []).append(code)
                _save(st)
                log(f"  캡션 보강 {added}/{limit} → {code}")
                time.sleep(random.uniform(lo, hi))
            else:
                errors += 1
                log(f"  건너뜀({res}) → {code}")
                if res == "skip":
                    st.setdefault("done", []).append(code)
                    _save(st)
                time.sleep(random.uniform(4, 8))
    finally:
        d.quit()
    log(f"종료 — 보강 {added}건, 건너뜀/실패 {errors}건")
    return {"added": added, "errors": errors}


if __name__ == "__main__":
    go = "--go" in sys.argv
    n = None
    if go:
        i = sys.argv.index("--go")
        if len(sys.argv) > i + 1 and sys.argv[i + 1].isdigit():
            n = int(sys.argv[i + 1])
    print(json.dumps(run(go=go, limit=n), ensure_ascii=False))
