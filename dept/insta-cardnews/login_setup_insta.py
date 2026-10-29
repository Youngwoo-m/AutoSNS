"""인스타그램 로그인 1회 셋업. 비번을 코드에 저장하지 않고, Chrome 프로필(쿠키)에
저장해 이후 자동 게시에 재사용한다. (네이버 login_setup 과 같은 방식)

실행하면 인스타 로그인 페이지가 열린다. 직접 로그인(2단계 인증 포함)까지 끝낸 뒤,
피드가 보이면 터미널에서 Enter 를 눌러 종료한다. 그때 프로필에 세션이 저장된다.
세션이 만료되면(자동 게시가 '로그인 없음'으로 실패) 이 스크립트를 다시 실행하면 된다.
"""
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from common import PROFILE_DIR, log


def main():
    opts = Options()
    opts.add_argument(f"--user-data-dir={PROFILE_DIR}")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    # use-mock-keychain 을 빼 로그인 앱(일반 크롬)과 같은 진짜 키체인 키로 쿠키를 읽고 쓴다(2026-10-28)
    opts.add_experimental_option("excludeSwitches", ["enable-automation", "use-mock-keychain"])
    opts.add_argument("--lang=ko-KR")
    opts.add_argument("--window-size=1280,1000")
    # 크롬이 실행마다 앱 전체(~1.4GB)를 임시 폴더에 복제하고 남기는 것을 막는다(2026-10-09)
    opts.add_argument("--disable-features=MacAppCodeSignClone")
    driver = webdriver.Chrome(options=opts)
    try:
        driver.get("https://www.instagram.com/accounts/login/")
        log("인스타그램 로그인 창을 열었습니다. 브라우저에서 직접 로그인하세요.")
        print("\n로그인(2단계 인증 포함)을 마치고 '피드'가 보이면, 여기서 Enter 를 누르세요.")
        try:
            input()
        except EOFError:
            time.sleep(120)  # 입력 불가 환경이면 2분 대기
        log(f"세션 저장 완료(프로필: {PROFILE_DIR}). 이제 자동 게시가 가능합니다.")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
