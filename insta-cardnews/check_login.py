"""인스타 로그인 세션이 살아있는지 빠르게 확인한다. (게시는 하지 않음)"""
import time

from post_instagram import build_driver, shot
from common import load_config, log


def main():
    cfg = load_config()
    headless = cfg.get("instagram", {}).get("headless", False)
    driver = build_driver(headless)
    try:
        driver.get("https://www.instagram.com/")
        time.sleep(6)
        url = driver.current_url
        if "/accounts/login" in url or "login" in url:
            shot(driver, "check_not_logged_in")
            log("로그인 안 됨 → login_setup_insta.py 를 실행하세요.")
        else:
            shot(driver, "check_logged_in")
            log("로그인 세션 정상.")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
