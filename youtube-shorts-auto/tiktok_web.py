"""틱톡 웹(TikTok Studio)에 로그인된 크롬 프로필로 세로 mp4 를 올린다.

API(tiktok_upload.py) 는 앱 심사를 통과해야 공개 게시가 되고, 2026-09-22 현재
개발자 포털에 앱 자체가 없어 쓸 수 없다. 그래서 인스타와 같은 방식 —
전용 크롬 프로필에 한 번 로그인해 두고 브라우저로 올리는 길 — 을 함께 둔다.

  tiktok_web_login.py   최초 1회 로그인(사람이 직접 로그인, 세션만 프로필에 남는다)
  tiktok_web.py         업로드. 기본은 dry-run 이라 '게시' 를 누르지 않는다.

안전장치(다른 업로더와 같은 철학):
  - 인자 없이 돌리면 dry-run: 영상·캡션을 올려두고 게시 직전에 멈춘 뒤 스크린샷만 남긴다.
  - 실제 게시는 --post 를 줄 때만 일어난다.
  - 같은 mp4 를 두 번 올리지 않게 tiktok_web_state.json 에 기록한다.
"""
import json
import os
import sys
import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

from common import BASE_DIR, LOGS_DIR, POSTS_DIR, load_config, log

PROFILE_DIR = os.path.join(BASE_DIR, "chrome-profile-tiktok")
STATE_PATH = os.path.join(BASE_DIR, "tiktok_web_state.json")
UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload?from=webapp"

# 한국어/영어 UI 를 모두 받는다(틱톡은 계정 언어에 따라 바뀐다).
POST_LABELS = ["게시", "Post", "업로드", "Upload"]
CAPTION_HINTS = ["설명", "캡션", "Description", "caption"]


def build_driver(headless=False):
    o = Options()
    o.add_argument(f"--user-data-dir={PROFILE_DIR}")
    o.add_argument("--disable-blink-features=AutomationControlled")
    o.add_experimental_option("excludeSwitches", ["enable-automation"])
    o.add_experimental_option("useAutomationExtension", False)
    o.add_argument("--window-size=1400,1000")
    o.add_argument("--lang=ko-KR")
    o.set_capability("unhandledPromptBehavior", "accept")
    if headless:
        o.add_argument("--headless=new")
    d = webdriver.Chrome(options=o)
    d.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"},
    )
    return d


def shot(d, name):
    p = os.path.join(LOGS_DIR, f"{datetime.now():%Y%m%d_%H%M%S}_tiktok_{name}.png")
    try:
        d.save_screenshot(p)
        log(f"스크린샷: {p}")
    except Exception as e:
        log(f"스크린샷 실패: {e}")
    return p


def _state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"posted": []}


def _mark(video):
    s = _state()
    s["posted"].append({"video": os.path.basename(video),
                        "at": datetime.now().isoformat(timespec="seconds")})
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def already_posted(video):
    return any(x["video"] == os.path.basename(video) for x in _state()["posted"])


def logged_in(d):
    """업로드 화면까지 들어가지면 로그인된 것으로 본다."""
    return "login" not in d.current_url and "/upload" in d.current_url


def _file_input(d, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        for e in d.find_elements(By.CSS_SELECTOR, "input[type=file]"):
            return e            # 숨어 있어도 send_keys 는 동작한다
        time.sleep(1)
    return None


def _caption_box(d, timeout=40):
    """캡션 입력칸(contenteditable)을 찾는다. 영상 처리 중에는 늦게 나타난다."""
    end = time.time() + timeout
    while time.time() < end:
        boxes = [e for e in d.find_elements(By.CSS_SELECTOR, "div[contenteditable='true']")
                 if e.is_displayed()]
        if boxes:
            return boxes[0]
        time.sleep(1)
    return None


def _clear_caption(d, box):
    """틱톡 캡션칸은 파일명이 미리 채워져 있다. 전부 지운다.

    contenteditable 에서는 Cmd+A 가 안 먹는 경우가 있어 Selection API 로 고르고
    BACK_SPACE 를 보낸다(인스타에서 확인한 방식).
    """
    box.click()
    time.sleep(0.3)
    d.execute_script("""
      const el = arguments[0];
      el.focus();
      const r = document.createRange(); r.selectNodeContents(el);
      const s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
    """, box)
    time.sleep(0.2)
    ActionChains(d).send_keys(Keys.BACK_SPACE).perform()
    time.sleep(0.5)


def _type_caption(d, box, caption):
    _clear_caption(d, box)
    for i, line in enumerate(caption.split("\n")):
        if i:
            ActionChains(d).key_down(Keys.SHIFT).send_keys(Keys.ENTER)\
                .key_up(Keys.SHIFT).perform()
        ActionChains(d).send_keys(line).perform()
        time.sleep(0.4)     # 해시태그 자동완성 창이 뜨면 가라앉을 시간을 준다
    ActionChains(d).send_keys(Keys.ESCAPE).perform()
    time.sleep(0.5)
    return box.text.strip()


def _click_post(d):
    for lb in POST_LABELS:
        for e in d.find_elements(By.XPATH,
                                 f"//button[normalize-space()='{lb}']"
                                 f"|//div[@role='button'][normalize-space()='{lb}']"):
            if e.is_displayed() and e.is_enabled():
                e.click()
                return lb
    return None


def upload(video, caption, post=False):
    if not os.path.exists(video):
        raise SystemExit(f"mp4 가 없습니다: {video}")
    if post and already_posted(video):
        raise SystemExit(f"이미 올린 영상입니다: {os.path.basename(video)}")

    d = build_driver()
    try:
        d.get(UPLOAD_URL)
        time.sleep(8)
        if not logged_in(d):
            shot(d, "not_logged_in")
            raise SystemExit("로그인이 안 돼 있습니다 — tiktok_web_login.py 를 먼저 실행하세요.")

        inp = _file_input(d)
        if inp is None:
            shot(d, "no_file_input")
            raise SystemExit("파일 입력칸을 못 찾았습니다(화면 구조 변경?)")
        inp.send_keys(os.path.abspath(video))
        log(f"영상 전송: {os.path.basename(video)}")
        time.sleep(10)

        box = _caption_box(d)
        if box is None:
            shot(d, "no_caption_box")
            raise SystemExit("캡션 입력칸을 못 찾았습니다")
        got = _type_caption(d, box, caption)
        log(f"캡션 입력됨({len(got)}자): {got[:60]}…")

        if not post:
            p = shot(d, "dryrun")
            log("DRY-RUN: '게시' 를 누르지 않고 멈춥니다. 화면을 확인하세요.")
            log("실제 게시는 --post 를 붙여 다시 실행하세요.")
            input("확인했으면 Enter 를 눌러 창을 닫습니다... ")
            return {"status": "dry_run", "shot": p}

        lb = _click_post(d)
        if lb is None:
            shot(d, "no_post_button")
            raise SystemExit("'게시' 버튼을 못 찾았습니다")
        log(f"'{lb}' 클릭 — 업로드 마무리를 기다립니다")
        time.sleep(20)
        p = shot(d, "posted")
        _mark(video)
        log("✅ 게시 완료(화면 스크린샷으로 확인하세요)")
        return {"status": "posted", "shot": p}
    finally:
        d.quit()


def _latest():
    """영상이 실제로 렌더링된 것 중 가장 최근 대본 json 을 돌려준다.

    대본만 만들어지고 렌더링 전인 json 이 맨 뒤에 올 수 있으므로(그날 아침 파이프라인
    중간 상태), video 가 비었거나 파일이 없는 건 건너뛴다.

    파일명 정렬은 쓰지 않는다 — 재난안전판(20260921_...)과 GeoAI판(geoai_20260921_...)이
    이름 규칙이 달라 사전순으로는 시간 순서가 뒤집힌다. 수정시각으로 고른다.
    """
    paths = [os.path.join(POSTS_DIR, f) for f in os.listdir(POSTS_DIR) if f.endswith(".json")]
    for path in sorted(paths, key=os.path.getmtime, reverse=True):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        v = data.get("video")
        if v and os.path.exists(v):
            return data
    raise SystemExit("렌더링된 영상이 있는 대본을 찾지 못했습니다.")


def build_caption(data, cfg):
    from tiktok_upload import _build_caption
    return _build_caption(data, cfg.get("youtube", {}))


if __name__ == "__main__":
    cfg = load_config()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    data = _latest()
    video = args[0] if args else data.get("video")
    caption = build_caption(data, cfg)
    print(upload(video, caption, post="--post" in sys.argv))
