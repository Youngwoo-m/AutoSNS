"""이미 발행한 네이버 블로그 글에 유튜브 영상을 넣는다('자주 묻는 질문' 바로 앞).

진로 시리즈 네이버판 1·2편은 발행 코드가 구조형 글에서 영상을 넣지 못하던 때에
나가서 영상이 없다(2026-09-28 고침, 1885810). 새 글과 같은 자리에 같은 모양으로
'🎬 영상으로 보기' 한 줄과 영상 카드를 넣는다.

지키는 것:
  - 글에 이미 유튜브 영상이 있으면 손대지 않는다.
  - '❓ 자주 묻는 질문' 문단을 못 찾으면 넣지 않는다(엉뚱한 자리에 넣지 않게).
  - 기본은 넣어 본 뒤 발행 전에 멈춘다(스크린샷만). --go 일 때만 수정 발행한다.
  - 발행 뒤 공개 글을 다시 열어 영상이 들어갔는지 확인한다.

사용: python naver_add_video.py <logNo> <유튜브 URL>          # 넣어 보고 멈춤
      python naver_add_video.py <logNo> <유튜브 URL> --go     # 수정 발행
"""
import sys
import time

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from common import load_config, log
from publish_naver import (MOD_KEY, _embed_video, _type_text, build_driver,
                           click_if_present, shot)

# 블로그 주소는 로그인 계정(config.naver_id=smuds)과 다르다. config 의 blog_id 는 블로거용이라 쓰지 않는다.
BLOG_ID = "studs23"
FAQ_HEAD = "❓ 자주 묻는 질문"
VIDEO_SEL = ".se-component.se-oembed, .se-component.se-video, iframe[src*='youtube']"


def _has_video(driver):
    return bool(driver.find_elements(By.CSS_SELECTOR, VIDEO_SEL))


def _faq_paragraph(driver):
    for p in driver.find_elements(By.CSS_SELECTOR, ".se-component.se-text .se-text-paragraph"):
        if (p.text or "").strip().startswith(FAQ_HEAD):
            return p
    return None


def _video_before_faq(driver):
    """영상 카드가 FAQ 문단보다 앞에 있는지(문서 순서) 확인한다."""
    return driver.execute_script("""
      const v = document.querySelector(arguments[0]);
      const ps = [...document.querySelectorAll('.se-component.se-text .se-text-paragraph')];
      const f = ps.find(p => (p.innerText||'').trim().startsWith(arguments[1]));
      if (!v || !f) return false;
      return !!(v.compareDocumentPosition(f) & Node.DOCUMENT_POSITION_FOLLOWING);
    """, VIDEO_SEL, FAQ_HEAD)


def add_video(log_no, video_url, go=False):
    cfg = load_config()
    blog_id = BLOG_ID
    driver = build_driver(cfg.get("publish", {}).get("headless", False))
    try:
        driver.get(f"https://blog.naver.com/PostUpdateForm.naver?blogId={blog_id}&logNo={log_no}")
        time.sleep(5)
        try:
            driver.switch_to.alert.accept()
        except Exception:
            pass
        if "nidlogin" in driver.current_url or "nid.naver.com" in driver.current_url:
            raise RuntimeError("로그인 세션이 만료되었습니다. login_setup.py 를 다시 실행해 주세요.")
        try:
            WebDriverWait(driver, 15).until(
                EC.frame_to_be_available_and_switch_to_it((By.ID, "mainFrame")))
        except Exception:
            pass                                    # 수정 화면이 iframe 없이 뜨는 경우
        time.sleep(3)
        click_if_present(driver, By.CSS_SELECTOR, ".se-popup-button-cancel", timeout=3)
        click_if_present(driver, By.CSS_SELECTOR, ".se-help-panel-close-button", timeout=2)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, ".se-component.se-text .se-text-paragraph")))
        time.sleep(1)

        if _has_video(driver):
            log(f"영상 넣기 {log_no}: 이미 영상이 있어 건드리지 않습니다.")
            return "has_video"
        faq = _faq_paragraph(driver)
        if faq is None:
            shot(driver, f"addvideo_nofaq_{log_no}")
            log(f"영상 넣기 {log_no}: '{FAQ_HEAD}' 문단을 못 찾아 넣지 않습니다.")
            return "no_faq"

        # FAQ 문단 맨 앞에서 ENTER → 위에 빈 문단이 생긴다 → 그 줄로 올라가 채운다.
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", faq)
        ActionChains(driver).move_to_element(faq).click().perform()
        time.sleep(0.4)
        ActionChains(driver).key_down(MOD_KEY).send_keys(Keys.ARROW_LEFT).key_up(MOD_KEY).perform()
        time.sleep(0.3)
        ActionChains(driver).send_keys(Keys.ENTER).perform()
        time.sleep(0.4)
        ActionChains(driver).send_keys(Keys.ARROW_UP).perform()
        time.sleep(0.3)
        _type_text(driver, "🎬 영상으로 보기")
        _embed_video(driver, video_url)
        time.sleep(1)
        shot(driver, f"addvideo_after_{log_no}")

        if not (_has_video(driver) and _video_before_faq(driver)):
            log(f"영상 넣기 {log_no}: 영상 카드가 FAQ 앞에 들어가지 않았습니다 — 발행하지 않습니다.")
            return "not_inserted"
        if not go:
            log(f"영상 넣기 {log_no}: [DRY] 들어간 것 확인, 발행 전에 멈춤(저장하지 않음).")
            return "dry"

        if not click_if_present(driver, By.XPATH,
                "//button[contains(@class,'publish') and contains(.,'발행')]", 6):
            click_if_present(driver, By.XPATH, "//*[contains(@class,'publish_btn')]", 6)
        time.sleep(2)
        shot(driver, f"addvideo_layer_{log_no}")
        if not click_if_present(driver, By.XPATH,
                "//div[contains(@class,'layer') or contains(@class,'option')]"
                "//button[contains(@class,'confirm') and contains(.,'발행')]", 6):
            click_if_present(driver, By.XPATH, "//button[contains(@class,'confirm_btn')]", 6)
        time.sleep(6)

        # 공개 글을 다시 열어 확인한다(모바일 페이지가 가볍고 iframe 없이 본문이 바로 나온다).
        driver.switch_to.default_content()
        driver.get(f"https://m.blog.naver.com/{blog_id}/{log_no}")
        time.sleep(5)
        ok = bool(driver.find_elements(By.CSS_SELECTOR, VIDEO_SEL + ", .se-oembed"))
        shot(driver, f"addvideo_public_{log_no}")
        log(f"영상 넣기 {log_no}: {'완료(공개 글에서 확인)' if ok else '⚠ 공개 글에서 영상을 찾지 못함'}")
        return "added" if ok else "not_confirmed"
    finally:
        driver.quit()


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    print(add_video(a[0], a[1], go="--go" in sys.argv))
