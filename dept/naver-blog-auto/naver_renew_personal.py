"""이미 교차 발행한 개인 네이버 글(safeworking) 본문을 티스토리 원문 붙여넣기 판으로 바꿔 다시 발행한다.

옛 교차 발행(줄 글 입력)은 표가 '|' 줄 글, 인용이 「」 가 되고 구분선·문단 안 링크·둘째 그림·PDF 가 빠졌다.
글 수정 화면을 열어 본문만 모두 지우고 naver_crosspost_personal.py 와 같은 방식(naver_paste.py)으로 다시 채운다.
제목·카테고리·태그·글 주소는 그대로 둔다. 원문과 구성요소 수가 다르면 발행하지 않는다(2026-10-28).

    ./.venv/bin/python naver_renew_personal.py --log-no 224456997528 \
        --tistory-url https://na-geoai.tistory.com/186 --dry|--go

결과 마지막 줄 JSON: {"status": "renewed"|"dry"|"error", "url": …, "message": …}
"""
import argparse
import os
import re
import sys
import time

# 프로필 환경변수·sys.path 는 교차 발행 모듈이 잡는다
from naver_crosspost_personal import HERE, BLOG_ID, build_data, out

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


# 제목 칸을 뺀 본문 구성요소 수와, 자리 안내 글(placeholder)을 뺀 본문 글자
BODY_JS = """
var cs=document.querySelectorAll('.se-content .se-component:not(.se-documentTitle)'), t='';
cs.forEach(function(c){ var w=document.createTreeWalker(c, NodeFilter.SHOW_TEXT), n;
  while((n=w.nextNode())){ if(!n.parentElement.closest('[class*="placeholder"]')) t+=n.textContent; } });
return [cs.length, t.replace(/\\u200b/g,'').trim().length, document.querySelectorAll('.se-content .se-component:not(.se-documentTitle):not(.se-text)').length];"""


def _key(driver, key, code, vk, mods=0, commands=None):
    # macOS 크롬드라이버의 Cmd+A 는 '전체 선택' 편집 명령을 실행하지 않는다 → CDP 로 명령을 함께 보낸다
    down = {"type": "rawKeyDown", "modifiers": mods, "key": key, "code": code, "windowsVirtualKeyCode": vk}
    if commands:
        down["commands"] = commands
    driver.execute_cdp_cmd("Input.dispatchKeyEvent", down)
    driver.execute_cdp_cmd("Input.dispatchKeyEvent",
                           {"type": "keyUp", "modifiers": mods, "key": key, "code": code, "windowsVirtualKeyCode": vk})


def clear_body(driver):
    """본문 구성요소(글·그림·표 등)를 모두 지워 빈 문단 하나만 남긴다. 제목은 그대로."""
    for _ in range(3):
        el = [e for e in driver.find_elements(By.CSS_SELECTOR, ".se-content .se-component.se-text .se-text-paragraph")
              if not driver.execute_script("return !!arguments[0].closest('.se-documentTitle');", e)]
        if not el:
            raise RuntimeError("본문 문단을 찾지 못함")
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el[0])
        ActionChains(driver).move_to_element(el[0]).click().perform()
        time.sleep(0.5)
        # 에디터는 두 번째 전체 선택에서 글 전체(그림·표 포함)를 고른다
        for _ in range(2):
            _key(driver, "a", "KeyA", 65, 4, ["selectAll"])
            time.sleep(0.6)
        _key(driver, "Backspace", "Backspace", 8)
        time.sleep(2)
        n, chars, others = driver.execute_script(BODY_JS)
        if n <= 1 and chars == 0 and others == 0:
            return
    raise RuntimeError(f"본문을 비우지 못함(남은 구성요소 {n}개, 글자 {chars}자)")


def renew(log_no, data, go):
    import naver_paste
    from publish_naver import build_driver, click_if_present, log, shot
    driver = build_driver(False)
    try:
        driver.get(f"https://blog.naver.com/PostUpdateForm.naver?blogId={BLOG_ID}&logNo={log_no}")
        time.sleep(4)
        if "nid.naver.com" in driver.current_url:
            raise RuntimeError("로그인 세션이 만료되었습니다(로그인-개인 앱으로 다시 로그인).")
        try:
            WebDriverWait(driver, 10).until(EC.frame_to_be_available_and_switch_to_it((By.ID, "mainFrame")))
        except Exception:
            pass
        WebDriverWait(driver, 30).until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, ".se-section-documentTitle .se-text-paragraph")))
        time.sleep(2)
        # '작성 중인 글이 있습니다' → 취소해 발행된 원래 글을 연다
        click_if_present(driver, By.XPATH, "//*[contains(@class,'se-popup')]//button[contains(.,'취소')]", 2)
        click_if_present(driver, By.CSS_SELECTOR, ".se-help-panel-close-button", 2)
        title = driver.find_element(By.CSS_SELECTOR, ".se-section-documentTitle").text.strip()
        if re.sub(r"\s+", "", title) != re.sub(r"\s+", "", data["title"]):
            raise RuntimeError(f"수정 화면 제목이 원문과 다름: {title[:40]!r}")
        clear_body(driver)
        log(f"{log_no}: 본문 비움")
        naver_paste.fill(driver, data)
        shot(driver, f"renew_{log_no}")
        if not go:
            log("DRY: 발행 누르기 전에 멈춤")
            return
        if not click_if_present(driver, By.XPATH, "//button[contains(@class,'publish') and contains(.,'발행')]", 6):
            click_if_present(driver, By.XPATH, "//*[contains(@class,'publish_btn')]", 6)
        time.sleep(2)
        shot(driver, f"renew_layer_{log_no}")
        if not click_if_present(driver, By.XPATH,
                "//div[contains(@class,'layer') or contains(@class,'option')]"
                "//button[contains(@class,'confirm') and contains(.,'발행')]", 6):
            if not click_if_present(driver, By.XPATH, "//button[contains(@class,'confirm_btn')]", 6):
                raise RuntimeError("발행 확인 버튼을 찾지 못함")
        for _ in range(20):
            time.sleep(1)
            if "PostUpdateForm" not in driver.current_url:
                break
        time.sleep(2)
        shot(driver, f"renew_after_{log_no}")
        if "PostUpdateForm" in driver.current_url:
            raise RuntimeError("발행을 눌렀지만 수정 화면에 머물러 있음")
    finally:
        driver.quit()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--log-no", required=True)
    ap.add_argument("--tistory-url", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry", action="store_true")
    g.add_argument("--go", action="store_true")
    ap.add_argument("--job", default="claude")
    args = ap.parse_args()
    url = f"https://blog.naver.com/{BLOG_ID}/{args.log_no}"
    try:
        workdir = os.path.join(HERE, "logs", f"renew_{args.log_no}_{time.strftime('%Y%m%d_%H%M%S')}")
        data = build_data(args.tistory_url, workdir, "", "")
    except Exception as e:
        return out("error", url, f"{type(e).__name__}: {e}")
    print(f"{args.log_no}: {data['title'][:50]} | 원문 구성 {data['paste']['expect']}", file=sys.stderr)
    from shared.axlock import Timeout, hold, stopped
    if args.go and stopped():
        return out("error", url, "비상 정지 중이라 발행하지 않았습니다")
    try:
        with hold(["profile:safeworking"], job=f"{args.job}:naver_renew", wait=2400):
            os.environ["AX_LOCKED"] = "1"
            renew(args.log_no, data, args.go)
    except Timeout:
        return out("error", url, "40분 기다려도 safeworking 크롬 프로필이 비지 않았습니다")
    except Exception as e:
        return out("error", url, f"{type(e).__name__}: {str(e)[:300]}")
    return out("renewed" if args.go else "dry", url, "" if args.go else "본문을 바꾸고 발행 직전에 멈췄습니다(logs/ 에 스크린샷)")


if __name__ == "__main__":
    sys.exit(main())
