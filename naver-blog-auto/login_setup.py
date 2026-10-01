"""최초 1회 실행: 네이버에 '직접' 로그인해 Chrome 프로필(쿠키)을 저장한다.

브라우저 창이 뜨면 평소처럼 로그인(2단계 인증 포함)하면 된다.
로그인 성공(NID_AUT 쿠키 발급)을 자동 감지하면 알아서 저장하고 닫힌다.
비밀번호는 어디에도 저장하지 않는다. (쿠키만 chrome-profile/ 에 보관)
"""
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from common import PROFILE_DIR, log

TIMEOUT_SEC = 600  # 로그인 대기 최대 10분


def main():
    opts = Options()
    opts.add_argument(f"--user-data-dir={PROFILE_DIR}")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("--window-size=1100,900")

    driver = webdriver.Chrome(options=opts)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"},
    )
    driver.get("https://nid.naver.com/nidlogin.login")
    log("브라우저에서 네이버에 직접 로그인하세요. (2단계 인증 포함) — 최대 10분 대기. 반드시 '로그인 상태 유지'를 체크하세요")

    waited = 0
    while waited < TIMEOUT_SEC:
        jar = {c["name"]: c for c in driver.get_cookies()}
        if "NID_AUT" in jar and "NID_SES" in jar:
            # '로그인 상태 유지'를 켜지 않으면 로그인 쿠키에 만료일이 없다(세션 쿠키) —
            # 창을 닫는 순간 사라져 다음 발행에서 다시 '세션 만료'가 된다(2026-10-01 실제 발생).
            if "expiry" not in jar["NID_AUT"]:
                if waited % 20 == 0:
                    log("⚠ 로그인은 됐지만 '로그인 상태 유지'가 꺼져 있어 창을 닫으면 풀립니다. "
                        "로그아웃 후 '로그인 상태 유지'를 체크하고 다시 로그인해 주세요.")
                time.sleep(2)
                waited += 2
                continue
            log("로그인 성공 감지(로그인 상태 유지 확인)! 쿠키(프로필) 저장 중...")
            time.sleep(6)                    # 쿠키가 디스크에 쓰일 시간을 준다
            driver.quit()
            log("저장 완료. 이제 publish_naver.py / run_weekly.py 를 쓸 수 있습니다.")
            return
        time.sleep(2)
        waited += 2

    driver.quit()
    log("시간 초과: 로그인이 감지되지 않았습니다. 다시 실행해 주세요.")


if __name__ == "__main__":
    main()
