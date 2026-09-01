"""쓰레드(Threads) 텍스트 글쓰기 — 인스타와 같은 로그인 세션(chrome-profile-insta) 재사용.

쓰레드는 인스타(Meta) 계정으로 로그인되며, 최초 1회 사용자가 쓰레드를 활성화해 두면
이 크롬 프로필로 바로 글을 쓸 수 있다. (별도 API/토큰 불필요)

발행 파이프라인에서 뉴스 헤드라인+요약+링크+해시태그를 텍스트 스레드로 크로스포스트한다.

★ 안전장치(다른 프로젝트와 동일): 수동 실행은 항상 dry_run(작성 화면까지만, 게시 안 함).
  실제 게시는 --go 또는 파이프라인에서 dry_run=False 로만.

사용:
  python post_threads.py "본문"        # dry-run(작성창까지, 게시 안 함)
  python post_threads.py --go "본문"    # 실제 게시
"""
import sys
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from common import load_config, log
from post_instagram import build_driver, shot, _set_clip, MOD_KEY

MAX_LEN = 500   # 쓰레드 글자 제한


def _compose(data, cfg=None):
    """뉴스 data → 쓰레드 텍스트(헤드라인 + 한 줄 요약 + 링크 + 해시태그, 500자 이내)."""
    scenes = data.get("scenes") or data.get("cards") or []
    headline = data.get("title") or (
        scenes[0].get("heading") if scenes and isinstance(scenes[0], dict) else "재난안전 소식")
    summary = ""
    if scenes and isinstance(scenes[0], dict):
        summary = (scenes[0].get("narration") or scenes[0].get("heading") or "").strip()
    url = (data.get("_yt", {}) or {}).get("url", "") or data.get("url", "")
    tags = data.get("hashtags") or []
    tags = [t for t in tags if t.lower() != "shorts"][:6]
    tagline = " ".join("#" + t for t in tags)
    parts = [headline]
    if summary and summary[:20] not in headline:
        parts.append(summary)
    if url:
        parts.append("▶ " + url)
    if tagline:
        parts.append(tagline)
    text = "\n\n".join(parts).strip()
    return text[:MAX_LEN]


def _open_composer(driver):
    driver.get("https://www.threads.com/")
    time.sleep(4)
    for xp in ("//*[@aria-label='만들기']", "//*[@aria-label='새 스레드']",
               "//div[@role='button'][contains(.,'새로운 스레드')]",
               "//div[contains(@role,'button')][contains(.,'새로운 소식이 있나요')]"):
        els = driver.find_elements(By.XPATH, xp)
        if els:
            try:
                driver.execute_script("arguments[0].click();", els[0])
                break
            except Exception:
                pass
    time.sleep(2.5)


def _textbox(driver):
    for xp in ("//div[@role='dialog']//div[@contenteditable='true']",
               "//div[@contenteditable='true']",
               "//div[@role='textbox']"):
        els = driver.find_elements(By.XPATH, xp)
        if els:
            return els[-1]
    return None


def _post_button(driver):
    # 작성창의 '게시' 버튼(비활성 아닌 것 우선, 대개 마지막에 렌더된 것).
    els = driver.find_elements(
        By.XPATH, "//div[@role='button'][normalize-space()='게시'] "
        "| //div[@role='button'][normalize-space()='Post']")
    for e in reversed(els):
        if (e.get_attribute("aria-disabled") or "").lower() != "true":
            return e
    return els[-1] if els else None


def post(text=None, data=None, dry_run=None, image=None):
    cfg = load_config()
    tcfg = cfg.get("threads", {})
    if dry_run is None:
        dry_run = tcfg.get("dry_run", True)
    if not dry_run and not tcfg.get("enabled", False):
        log("threads.enabled=false → 실제 게시 중단, dry-run 으로만 진행합니다.")
        dry_run = True
    if text is None:
        text = _compose(data or {}, cfg)
    if not text.strip():
        log("쓰레드 본문이 비어 게시 생략."); return {"status": "empty"}

    driver = build_driver(headless=tcfg.get("headless", False))
    try:
        _open_composer(driver)
        shot(driver, "threads_open")
        box = _textbox(driver)
        if box is None:
            shot(driver, "threads_nobox")
            log("쓰레드 작성창을 못 찾음(활성화/로그인 확인)."); return {"status": "no_box"}
        box.click()
        time.sleep(0.8)
        _set_clip(text)
        ActionChains(driver).key_down(MOD_KEY).send_keys("v").key_up(MOD_KEY).perform()
        time.sleep(1.2)
        shot(driver, "threads_typed")
        if dry_run:
            log(f"[DRY-RUN] 쓰레드 작성 완료(게시 안 함): {text[:40]}...")
            return {"status": "dry_run", "text": text}
        btn = _post_button(driver)
        if btn is None:
            shot(driver, "threads_nopost"); log("게시 버튼 못 찾음."); return {"status": "no_button"}
        driver.execute_script("arguments[0].click();", btn)
        time.sleep(4)
        shot(driver, "threads_done")
        log("쓰레드 게시 완료(추정).")
        return {"status": "published", "text": text}
    finally:
        driver.quit()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--go"]
    go = "--go" in sys.argv
    txt = args[0] if args else "세명대학교 재난안전학과 쓰레드 테스트입니다. 재난안전 소식을 전합니다."
    print(post(text=txt, dry_run=not go))
