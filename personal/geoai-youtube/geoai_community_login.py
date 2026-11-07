"""최초 1회 실행: 유튜브에 '직접' 로그인해 Chrome 프로필(쿠키)을 저장한다.

게시물(커뮤니티) 작성은 공개 API 가 없어 브라우저로 해야 한다. 그래서 발행 잡이
쓸 로그인 세션을 이 프로필에 담아 둔다(비밀번호는 저장하지 않는다 — 쿠키만).

    ./.venv/bin/python geoai_community_login.py

창이 뜨면 **@geoai-safety 채널 계정**으로 로그인한다(2단계 인증 포함).
로그인 감지되면 알아서 저장하고 닫힌다.
"""
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from common import log
from geoai_community import PROFILE_DIR, chrome_options

TIMEOUT_SEC = 420


def main():
    driver = webdriver.Chrome(options=chrome_options(headless=False))
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"},
    )
    driver.get("https://www.youtube.com/")
    log(f"브라우저에서 유튜브에 직접 로그인하세요(최대 7분 대기). 프로필: {PROFILE_DIR}")
    waited = 0
    while waited < TIMEOUT_SEC:
        names = {c["name"] for c in driver.get_cookies()}
        if "SAPISID" in names or "__Secure-3PAPISID" in names:
            log("로그인 감지 — 프로필 저장 중...")
            time.sleep(3)
            driver.quit()
            log("저장 완료. geoai_community.py 로 게시물을 올릴 수 있습니다.")
            return
        time.sleep(3)
        waited += 3
    driver.quit()
    log("시간 초과: 로그인이 감지되지 않았습니다. 다시 실행해 주세요.")


if __name__ == "__main__":
    main()
