"""인스타그램 '수동' 로그인 런처 (429 레이트리밋 대응).

흐름:
1) IG_LOGIN_DELAY 초(기본 600=10분) 동안 대기해 429 레이트리밋이 풀리길 기다린다.
2) 준비된 크롬 프로필로 인스타 로그인 페이지를 연다. 429 페이지면 가볍게 몇 번만
   재시도(과도한 요청으로 차단 악화 방지).
3) 로그인 폼이 보이면 멈춘다 → 사용자가 브라우저에서 직접 아이디/비번 입력·로그인.
4) 로그인 완료(피드 진입)를 감지하면 스크린샷 후 종료. 쿠키가 프로필에 저장된다.

자격증명을 코드/파일에 저장하지 않는다. 사람이 직접 입력한다.
"""
import os
import time

from selenium.webdriver.common.by import By

from common import log
from post_instagram import build_driver, shot, _click_by_labels

LOGIN_URL = "https://www.instagram.com/accounts/login/"


def _is_rate_limited(driver):
    src = (driver.page_source or "")
    return ("429" in src and "작동하지 않습니다" in src) or "HTTP ERROR 429" in src


def _has_login_form(driver):
    selectors = [
        "input[name='username']",
        "input[name='email']",
        "input[autocomplete='username']",
        "input[aria-label*='사용자']",
        "input[aria-label*='이메일']",
        "input[aria-label*='username' i]",
        "input[type='password']",
    ]
    for sel in selectors:
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                if el.is_displayed():
                    return True
        except Exception:
            continue
    return False


def _logged_in(driver):
    url = driver.current_url
    return ("/accounts/login" not in url and "challenge" not in url
            and "two_factor" not in url and "instagram.com" in url)


def main():
    delay = int(os.environ.get("IG_LOGIN_DELAY", "600"))
    if delay > 0:
        log(f"429 레이트리밋 해제 대기: {delay}초 후 로그인 창을 엽니다...")
        time.sleep(delay)

    driver = build_driver(headless=False)
    try:
        # 1) 로그인 페이지 열기 (+429면 가볍게 재시도, 최대 6회/90초 간격)
        ready = False
        for attempt in range(1, 7):
            driver.get(LOGIN_URL)
            time.sleep(5)
            _click_by_labels(driver, ["모든 쿠키 허용", "Allow all cookies",
                                      "필수 쿠키만 허용", "Allow essential cookies"], 3)
            if _logged_in(driver) and not _has_login_form(driver):
                log("이미 로그인된 세션입니다. 종료.")
                shot(driver, "already_logged_in")
                return
            if _has_login_form(driver):
                ready = True
                break
            if _is_rate_limited(driver):
                log(f"아직 429 상태(시도 {attempt}/6). 90초 후 재시도...")
                shot(driver, f"still_429_{attempt}")
                time.sleep(90)
                continue
            time.sleep(8)  # 폼/429 둘 다 아니면 잠깐 더 기다려봄
            if _has_login_form(driver):
                ready = True
                break

        if not ready:
            shot(driver, "login_not_ready")
            log("로그인 폼을 띄우지 못했습니다(429 지속 가능). 잠시 후 다시 실행하세요.")
            return

        # 2) 사용자 수동 로그인 안내 → 완료까지 최대 20분 폴링(로컬, 네트워크 부담 없음)
        log("로그인 창이 준비됐습니다. 브라우저에서 직접 아이디/비밀번호를 입력해 "
            "로그인하세요. (2단계 인증/의심 로그인 화면이 나오면 함께 처리)")
        deadline = time.time() + 1200
        while time.time() < deadline:
            time.sleep(5)
            # 로그인 후 뜨는 '정보 저장/알림' 팝업은 자동으로 닫아준다
            _click_by_labels(driver, ["나중에 하기", "Not Now"], 1)
            if _logged_in(driver) and not _has_login_form(driver):
                time.sleep(2)
                shot(driver, "login_success")
                log("로그인 완료 감지! 쿠키 프로필 저장됨. 이제 카드 게시가 가능합니다.")
                return
        shot(driver, "login_timeout")
        log("20분 내 로그인 완료를 감지하지 못했습니다. 다시 실행해 주세요.")
    finally:
        time.sleep(2)
        driver.quit()


if __name__ == "__main__":
    main()
