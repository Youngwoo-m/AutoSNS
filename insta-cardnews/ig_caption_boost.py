"""이미 올린 인스타 게시물 캡션 끝에 활성화 문구(저장·팔로우 유도)를 덧붙인다.

새 게시물은 post_instagram 이 발행 시점에 넣지만, 그전 게시물에는 없어서 도달·전환에
기여하지 못한다.

편집 방식(시행착오 끝에 확정한 경로):
  - 원문은 '편집 화면의 캡션칸(box.text)'에서 읽는다. og:description 은 긴 캡션이
    잘려서 원문 복원에 쓸 수 없다.
  - 캡션칸은 contenteditable 이라 커서 이동(End/Cmd+↓)과 전체선택(Cmd+A)이 먹지 않는다.
    → Selection API 로 내용을 전부 선택하고 BACK_SPACE 키 이벤트로 비운 뒤 새로 넣는다.
    (예전에 커서가 문단 중간에 있어 문구가 본문 사이에 끼어드는 사고가 났다)
  - 본문은 execCommand('insertText'), 줄바꿈은 ENTER 키로 넣는다. insertText 는 '\n' 을
    버려서 캡션이 한 줄로 뭉개지고, 반대로 전부 타이핑하면 '@'·'#' 자동완성이 떠서
    엔터가 엉뚱한 멘션을 고를 수 있다(execCommand 로 넣은 텍스트는 자동완성이 안 뜬다).
  - '완료'는 캡션칸 내용이 의도한 문자열과 정확히 일치할 때만 누른다. 어긋나면 '취소'로
    빠져나오므로 게시물이 망가지지 않는다(실제로 초기 버전의 실패 2건이 여기서 걸렸다).
  - 저장 확인도 편집창을 다시 열어서 한다(og:description 은 잘려서 확인용으로 못 쓴다).

검증 이력: 2026-09-10 기존 게시물 140건 보강 완료(실패 0, 차단 0). 캡션이 없는
게시물 3건은 건너뛰었다.

인스타는 짧은 시간의 대량 편집을 스팸으로 보고 막을 수 있어:
  - 기본 dry_run=True, 1회 한도(기본 12건), 편집 간 랜덤 지연(기본 25~60초)
  - 처리한 코드는 상태파일에 누적, '차단' 문구 감지 시 즉시 중단

사용: python ig_caption_boost.py            # dry-run(대상만 출력)
      python ig_caption_boost.py --go [N]   # 실제 편집(N건까지)
"""
import json
import os
import random
import re
import sys
import time

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from common import load_config, log
from post_instagram import build_driver, shot

STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "caption_boost_state.json")
BLOCK_HINTS = ["작업이 차단", "잠시 후 다시", "제한되었습니다", "스팸"]
BOX_SEL = "div[role='textbox'][contenteditable='true']"


def _state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"done": [], "failed": []}


def _save(s):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def _collect_codes(d, user, scrolls=12):
    """내 프로필 그리드에서 게시물 코드를 최신순으로 모은다."""
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


def _blocked(d):
    try:
        return any(h in d.find_element(By.TAG_NAME, "body").text for h in BLOCK_HINTS)
    except Exception:
        return False


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
                        if e.is_displayed():
                            ActionChains(d).move_to_element(e).pause(0.3).click().perform()
                            return True
                    except Exception:
                        continue
        time.sleep(0.5)
    return False


def _open_editor(d, code):
    """게시물 편집 화면을 열고 캡션칸 요소를 돌려준다(실패 시 None)."""
    d.get(f"https://www.instagram.com/p/{code}/")
    time.sleep(random.uniform(3.5, 5.0))
    if not _click_text(d, ["옵션 더 보기", "옵션", "More options"]):
        return None
    time.sleep(1.5)
    if not _click_text(d, ["수정", "Edit"]):
        return None
    time.sleep(random.uniform(3.5, 5.0))
    boxes = [b for b in d.find_elements(By.CSS_SELECTOR, BOX_SEL) if b.is_displayed()]
    return boxes[0] if boxes else None


def _set_text(d, box, text):
    """캡션칸을 비우고 text 로 채운다. 성공하면 True."""
    ActionChains(d).move_to_element(box).pause(0.4).click().perform()
    time.sleep(0.6)
    d.execute_script(
        "const el=arguments[0]; el.focus();"
        "const r=document.createRange(); r.selectNodeContents(el);"
        "const s=window.getSelection(); s.removeAllRanges(); s.addRange(r);", box)
    time.sleep(0.4)
    ActionChains(d).send_keys(Keys.BACK_SPACE).perform()   # 전체 선택 상태에서 삭제
    time.sleep(1.0)
    if box.text.strip():
        return False                                        # 비우기 실패 → 손대지 않는다
    # 본문은 execCommand 로 넣고, 줄바꿈만 ENTER 키로 만든다.
    #  - insertText 는 '\n' 을 통째로 버려서 캡션이 한 줄로 뭉개진다.
    #  - 반대로 전부 타이핑하면 '@'·'#' 자동완성이 떠서 ENTER 가 멘션을 고를 수 있다.
    #    (execCommand 로 넣은 텍스트는 자동완성을 띄우지 않는 것을 확인했다)
    for i, para in enumerate(text.split("\n")):
        if i:
            ActionChains(d).send_keys(Keys.ENTER).perform()
            time.sleep(0.25)
        if para:
            d.execute_script(
                "arguments[0].focus(); document.execCommand('insertText', false, arguments[1]);",
                box, para)
            time.sleep(0.35)
    time.sleep(1.0)
    return True


def _norm(s):
    """비교용 정규화 — 편집칸은 줄바꿈/공백을 살짝 다르게 돌려준다."""
    return re.sub(r"\s+", " ", s or "").strip()


def _boost_one(d, code, add_lines):
    """캡션 끝에 add_lines 를 덧붙인다. 반환: added|skip|error|blocked"""
    box = _open_editor(d, code)
    if box is None:
        return "error"
    original = box.text
    if not original.strip():
        _click_text(d, ["취소", "Cancel"])
        return "skip"                                       # 캡션 없는 게시물은 건드리지 않음
    need = [ln for ln in add_lines if _norm(ln) not in _norm(original)]
    if not need:
        _click_text(d, ["취소", "Cancel"])
        return "skip"
    target = original.rstrip() + "\n\n" + "\n\n".join(need)
    if not _set_text(d, box, target):
        _click_text(d, ["취소", "Cancel"])
        return "error"
    # 의도한 내용과 정확히 일치할 때만 저장한다(어긋나면 취소 → 게시물 무손상).
    if _norm(box.text) != _norm(target):
        log(f"  내용 불일치 → 저장하지 않고 취소({code})")
        _click_text(d, ["취소", "Cancel"])
        return "error"
    if not _click_text(d, ["완료", "Done"]):
        _click_text(d, ["취소", "Cancel"])
        return "error"
    time.sleep(random.uniform(4.0, 6.0))
    if _blocked(d):
        return "blocked"
    # 저장 확인: 편집창을 다시 열어 실제 저장된 캡션을 읽는다(og:description 은 잘려서 못 씀).
    box2 = _open_editor(d, code)
    if box2 is None:
        return "error"
    ok = _norm(box2.text).endswith(_norm(need[-1]))
    _click_text(d, ["취소", "Cancel"])
    time.sleep(1.0)
    return "added" if ok else "error"


def run(go=False, limit=None, headless=None):
    cfg = load_config()
    ig = cfg.get("instagram", {})
    add = [x for x in (ig.get("save_cta"), ig.get("follow_cta")) if x]
    limit = int(limit or ig.get("caption_boost_limit", 12))
    lo, hi = ig.get("caption_boost_delay", [25, 60])
    st = _state()
    seen = set(st.get("done", [])) | set(st.get("failed", []))
    d = build_driver(headless=ig.get("headless", False) if headless is None else headless)
    added = errors = 0
    try:
        codes = [c for c in _collect_codes(d, ig["username"]) if c not in seen]
        log(f"미처리 {len(codes)}건 (이번 최대 {limit}건, dry_run={not go})")
        for code in codes[:limit]:
            if not go:
                log(f"  [DRY] {code}")
                continue
            res = _boost_one(d, code, add)
            if res == "blocked":
                shot(d, "caption_blocked")
                log("⚠ 인스타 제한 감지 → 즉시 중단")
                break
            if res == "added":
                added += 1
                st.setdefault("done", []).append(code)
                log(f"  보강 {added}/{limit} → {code}")
            elif res == "skip":
                st.setdefault("done", []).append(code)
                log(f"  건너뜀(문구 있음/캡션 없음) → {code}")
            else:
                errors += 1
                st.setdefault("failed", []).append(code)
                log(f"  실패(저장 안 함) → {code}")
            _save(st)
            time.sleep(random.uniform(lo, hi) if res == "added" else random.uniform(4, 8))
    finally:
        d.quit()
    log(f"종료 — 보강 {added}건, 실패 {errors}건")
    return {"added": added, "errors": errors}


if __name__ == "__main__":
    go = "--go" in sys.argv
    n = None
    if go:
        i = sys.argv.index("--go")
        if len(sys.argv) > i + 1 and sys.argv[i + 1].isdigit():
            n = int(sys.argv[i + 1])
    print(json.dumps(run(go=go, limit=n), ensure_ascii=False))
