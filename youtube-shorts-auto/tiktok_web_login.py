"""최초 1회: 틱톡 웹에 로그인해 세션을 chrome-profile-tiktok 에 남긴다.

아이디·비밀번호는 저장하지 않는다. Chrome 이 열리면 **사람이 직접** 로그인하고,
로그인이 끝나면 터미널에서 Enter 를 누른다. 쿠키만 프로필 폴더에 남는다.

Chrome 은 chromedriver 가 아니라 평범한 앱으로 띄운다 — 틱톡은 자동화로 실행된
브라우저를 감지하면 접속 즉시 로그인 쿠키를 지운다(2026-09-22 확인).
"""
import time

from tiktok_web import PROFILE_DIR, build_driver, launch_chrome, logged_in, shot, UPLOAD_URL
from common import log

if __name__ == "__main__":
    log(f"프로필 위치: {PROFILE_DIR}")
    launch_chrome("https://www.tiktok.com/login")
    print("\n열린 Chrome 창에서 학과 틱톡 계정으로 직접 로그인하세요.")
    print("(비밀번호는 저장되지 않고, 로그인 세션 쿠키만 프로필에 남습니다.)")
    input("로그인이 끝나면 Enter 를 누르세요... ")
    d = build_driver()
    try:
        d.get(UPLOAD_URL)
        time.sleep(10)
        if logged_in(d):
            log("✅ 로그인 확인 — 이제 tiktok_web.py 로 업로드할 수 있습니다.")
        else:
            shot(d, "login_check")
            log(f"⚠️ 업로드 화면 진입 실패(현재: {d.current_url})")
    finally:
        pass
