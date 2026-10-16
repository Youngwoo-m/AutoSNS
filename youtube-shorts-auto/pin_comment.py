"""우리가 단 첫 댓글을 영상 상단에 고정한다.

왜 브라우저인가: 댓글 작성은 API(commentThreads.insert)로 되지만 '고정'은 YouTube
Data API 에 아예 없다. 스튜디오·시청 페이지에서만 가능한 동작이라, 로그인된 크롬
프로필(chrome-profile-youtube)로 메뉴를 눌러 처리한다.

고정은 영상 소유 채널로 로그인돼 있어야 메뉴에 나타난다. 메뉴에 '고정'이 없으면
다른 계정으로 보고 있는 것이므로, 엉뚱한 메뉴를 누르지 않고 멈춘다.

프로필은 채널마다 따로 둔다. chrome-profile-youtube 는 개인(GeoAI) 계정으로 로그인돼
있어 학과 영상의 댓글을 고정할 수 없다(메뉴에 '신고'만 나온다 — 2026-10-15 확인).
학과용 프로필은 --login 으로 한 번 만들어 두면 된다. 로그인은 사람이 직접 한다.

사용:
    python pin_comment.py --login                 # 학과 계정 로그인용 창을 띄운다(1회)
    python pin_comment.py --check                 # 어느 계정으로 로그인됐는지 확인
    python pin_comment.py <영상ID>                # 시험 실행(고정 직전까지만)
    python pin_comment.py <영상ID> --go           # 실제 고정
    python pin_comment.py <영상ID> --go --profile chrome-profile-youtube
"""
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from common import log  # noqa: E402
from geoai_community import chrome_options  # noqa: E402

PIN_LABELS = ("고정", "Pin")
MENU_LABELS = ("작업 메뉴", "댓글 작업 메뉴", "More actions", "Action menu")
LOGS_DIR = os.path.join(BASE_DIR, "logs")


def _shot(d, name):
    os.makedirs(LOGS_DIR, exist_ok=True)
    p = os.path.join(LOGS_DIR, f"{time.strftime('%Y%m%d_%H%M%S')}_pin_{name}.png")
    try:
        d.save_screenshot(p)
        log(f"스크린샷: {p}")
    except Exception:
        pass
    return p


def who(d):
    """로그인된 계정 이름. 영상 소유 채널과 다르면 '고정'이 보이지 않는다."""
    d.get("https://www.youtube.com/")
    time.sleep(5)
    for sel in ("button#avatar-btn", "ytd-topbar-menu-button-renderer button"):
        for el in d.find_elements("css selector", sel):
            lab = el.get_attribute("aria-label") or ""
            if lab:
                return lab
    return "(알 수 없음)"


DEPT_PROFILE = os.path.join(BASE_DIR, "chrome-profile-youtube-dept")


def _options(profile_dir, headless=True):
    """geoai_community 의 옵션을 쓰되 프로필 폴더만 바꾼다(채널마다 다른 계정)."""
    o = chrome_options(headless=headless)
    args = [a for a in o.arguments if not a.startswith("--user-data-dir=")]
    o2 = type(o)()
    for a in args:
        o2.add_argument(a)
    o2.add_argument(f"--user-data-dir={profile_dir}")
    return o2


def login(profile_dir=None, timeout_sec=420):
    """사람이 직접 로그인할 창을 띄우고, 로그인 쿠키가 생기면 저장하고 닫는다.

    Enter 를 기다리던 방식은 쿠키가 저장되기 전에 창이 닫히거나 로그인 실패를
    알아채지 못했다(2026-10-17: 프로필은 생겼는데 로그인 안 된 상태로 남았다).
    geoai_community_login.py 와 같이 SAPISID 쿠키가 보일 때까지 기다린다.
    비밀번호는 저장하지 않는다 — 쿠키만 남는다."""
    from selenium import webdriver
    profile_dir = profile_dir or DEPT_PROFILE
    d = webdriver.Chrome(options=_options(profile_dir, headless=False))
    # 구글은 자동화 표시가 있는 창의 로그인을 막는다 — 표시를 지운다.
    d.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument",
                      {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"})
    d.get("https://www.youtube.com/")
    log(f"창에서 학과 계정(@smds2023)으로 로그인하세요. 최대 {timeout_sec // 60}분 기다립니다.")
    log(f"프로필: {profile_dir}")
    waited = 0
    try:
        while waited < timeout_sec:
            names = {c["name"] for c in d.get_cookies()}
            if "SAPISID" in names or "__Secure-3PAPISID" in names:
                time.sleep(3)          # 쿠키가 디스크에 내려갈 틈
                log("로그인 감지 — 프로필 저장 완료")
                return True
            time.sleep(3)
            waited += 3
        log("시간이 지나 중단합니다(로그인 감지 못 함).")
        return False
    finally:
        d.quit()


def pin(video_id, go=False, headless=True, profile_dir=None):
    from selenium import webdriver
    profile_dir = profile_dir or (DEPT_PROFILE if os.path.exists(DEPT_PROFILE)
                                  else os.path.join(BASE_DIR, "chrome-profile-youtube"))
    log(f"프로필: {os.path.basename(profile_dir)}")
    d = webdriver.Chrome(options=_options(profile_dir, headless=headless))
    try:
        log(f"로그인 계정: {who(d)}")
        d.get(f"https://www.youtube.com/watch?v={video_id}")
        time.sleep(7)
        # 댓글 영역은 스크롤해야 불러온다(지연 로딩).
        for _ in range(4):
            d.execute_script("window.scrollBy(0, 900);")
            time.sleep(1.5)
        threads = d.find_elements("css selector", "ytd-comment-thread-renderer")
        log(f"댓글 {len(threads)}개 로드됨")
        if not threads:
            _shot(d, "no_comments")
            return {"status": "no_comments"}

        mine = threads[0]        # 우리가 업로드 직후 단 댓글이 가장 위에 온다
        txt = (mine.text or "").replace("\n", " ")[:60]
        log(f"대상 댓글: {txt}")
        d.execute_script("arguments[0].scrollIntoView({block:'center'});", mine)
        time.sleep(1)

        btn = None
        for el in mine.find_elements("css selector", "button, yt-icon-button"):
            lab = (el.get_attribute("aria-label") or "")
            if any(k in lab for k in MENU_LABELS):
                btn = el
                break
        if btn is None:
            _shot(d, "no_menu_button")
            return {"status": "no_menu"}
        d.execute_script("arguments[0].click();", btn)
        time.sleep(2)

        item = None
        for el in d.find_elements("css selector", "tp-yt-paper-item, ytd-menu-service-item-renderer"):
            t = (el.text or "").strip()
            if t and any(t.startswith(k) for k in PIN_LABELS):
                item = el
                break
        if item is None:
            _shot(d, "no_pin_item")
            log("메뉴에 '고정'이 없습니다 — 이 영상의 소유 채널로 로그인돼 있지 않습니다.")
            return {"status": "not_owner"}

        _shot(d, "menu_open")
        if not go:
            log("시험 실행: 여기서 멈춥니다(실제 고정하지 않음).")
            return {"status": "dry_run"}

        d.execute_script("arguments[0].click();", item)
        time.sleep(2)
        # 확인 대화상자(있을 때만)
        for el in d.find_elements("css selector", "yt-button-renderer, button"):
            t = (el.text or "").strip()
            if t in ("고정", "PIN", "Pin"):
                d.execute_script("arguments[0].click();", el)
                break
        time.sleep(3)
        _shot(d, "after_pin")
        log("댓글 고정 완료")
        return {"status": "pinned"}
    finally:
        d.quit()


def main():
    argv = sys.argv[1:]
    args = [a for a in argv if not a.startswith("--")]
    go = "--go" in argv
    profile = None
    if "--profile" in argv:
        name = argv[argv.index("--profile") + 1]
        profile = name if os.path.isabs(name) else os.path.join(BASE_DIR, name)
    if "--login" in argv:
        login(profile)
        return
    if "--check" in sys.argv:
        from selenium import webdriver
        d = webdriver.Chrome(options=_options(
            profile or os.path.join(BASE_DIR, "chrome-profile-youtube"), headless=True))
        try:
            log(f"로그인 계정: {who(d)}")
        finally:
            d.quit()
        return
    if not args:
        raise SystemExit("영상 ID 를 주세요: python pin_comment.py <영상ID> [--go]")
    print(pin(args[0], go=go, profile_dir=profile))


if __name__ == "__main__":
    main()
