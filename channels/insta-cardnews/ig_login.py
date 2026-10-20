"""인스타그램 자동 로그인 → 쿠키 프로필 저장 (1회용 셋업 보조).

자격증명은 환경변수 IG_USER / IG_PASS 로만 받는다(파일에 저장하지 않음).
로그인 후 결과를 logs/ 에 스크린샷으로 남긴다. '의심스러운 로그인'/2단계 인증
화면이 뜨면, 열린 브라우저에서 직접 마무리한 뒤 다시 실행하면 된다.
"""
import os
import time

from selenium.webdriver.common.by import By

from common import log
from post_instagram import build_driver, shot, _click_by_labels


def main():
    user = os.environ.get("IG_USER", "").strip()
    pw = os.environ.get("IG_PASS", "")
    if not user or not pw:
        raise SystemExit("환경변수 IG_USER / IG_PASS 가 필요합니다.")

    driver = build_driver(headless=False)
    try:
        driver.get("https://www.instagram.com/accounts/login/")
        time.sleep(5)
        # 쿠키 배너(있으면) 닫기
        _click_by_labels(driver, ["모든 쿠키 허용", "Allow all cookies",
                                  "필수 쿠키만 허용", "Allow essential cookies"], 3)
        time.sleep(1)

        try:
            u = driver.find_element(By.CSS_SELECTOR, "input[name='username']")
            p = driver.find_element(By.CSS_SELECTOR, "input[name='password']")
        except Exception:
            shot(driver, "login_no_form")
            log("로그인 폼을 찾지 못했습니다(이미 로그인 상태일 수 있음). 스크린샷 확인.")
            return
        u.clear(); u.send_keys(user)
        time.sleep(0.5)
        p.clear(); p.send_keys(pw)
        time.sleep(0.5)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        log("로그인 제출. 결과 대기 중...")
        time.sleep(8)

        # 로그인 후 안내 팝업들 닫기
        _click_by_labels(driver, ["나중에 하기", "Not Now", "나중에", "Save Info",
                                  "정보 저장"], 4)
        time.sleep(2)
        _click_by_labels(driver, ["나중에 하기", "Not Now"], 3)
        time.sleep(2)

        url = driver.current_url
        shot(driver, "login_result")
        if "/accounts/login" in url or "challenge" in url or "two_factor" in url:
            log(f"로그인 미완료(추정 URL={url}). 의심 로그인/2단계 인증일 수 있습니다. "
                f"열린 브라우저에서 직접 인증을 마친 뒤, 창을 닫지 말고 잠시 두세요.")
            # 사용자가 직접 마무리할 시간을 준다(최대 3분)
            for _ in range(18):
                time.sleep(10)
                if "/accounts/login" not in driver.current_url \
                        and "challenge" not in driver.current_url \
                        and "two_factor" not in driver.current_url:
                    shot(driver, "login_result_after")
                    log("로그인 완료 감지. 세션 저장됨.")
                    return
            log("3분 내 로그인 완료를 감지하지 못했습니다. 다시 시도해 주세요.")
        else:
            log(f"로그인 성공(URL={url}). 쿠키 프로필 저장 완료.")
    finally:
        time.sleep(2)
        driver.quit()


if __name__ == "__main__":
    main()
