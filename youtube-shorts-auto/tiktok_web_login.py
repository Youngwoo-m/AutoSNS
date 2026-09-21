"""최초 1회: 틱톡 웹에 로그인해 세션을 chrome-profile-tiktok 에 남긴다.

아이디·비밀번호는 저장하지 않는다. 브라우저가 열리면 **사람이 직접** 로그인하고,
로그인이 끝나면 터미널에서 Enter 를 누른다. 쿠키만 프로필 폴더에 남는다.
이후 tiktok_web.py 가 이 프로필을 그대로 쓴다.
"""
import time

from tiktok_web import PROFILE_DIR, build_driver, logged_in, shot
from common import log

if __name__ == "__main__":
    log(f"프로필 위치: {PROFILE_DIR}")
    d = build_driver(headless=False)
    try:
        d.get("https://www.tiktok.com/login")
        print("\n브라우저에서 학과 틱톡 계정으로 직접 로그인하세요.")
        print("(비밀번호는 저장되지 않고, 로그인 세션 쿠키만 프로필에 남습니다.)")
        input("로그인이 끝나면 Enter 를 누르세요... ")
        d.get("https://www.tiktok.com/tiktokstudio/upload?from=webapp")
        time.sleep(8)
        if logged_in(d):
            log("✅ 로그인 확인 — 이제 tiktok_web.py 로 업로드할 수 있습니다.")
        else:
            shot(d, "login_check")
            log(f"⚠️ 업로드 화면 진입 실패(현재: {d.current_url}) — 다시 시도해 주세요.")
    finally:
        d.quit()
