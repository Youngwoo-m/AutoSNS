"""safeworking 네이버 계정 전용 Chrome 프로필(chrome-profile-safeworking)을 만든다 — 직접 로그인.

학과 계정용 chrome-profile 은 건드리지 않는다(login_setup.py 를 쓰면 그 로그인이 바뀐다).
창이 뜨면 safeworking 계정으로 로그인(2단계 인증 포함, '로그인 상태 유지' 체크)하면 자동 감지해 저장하고 닫힌다.
비밀번호는 저장하지 않는다.

    python3 shared/axlock.py run --job naver-login-safeworking --res profile:safeworking -- \
        channels/naver-blog-auto/.venv/bin/python channels/naver-blog-auto/login_setup_safeworking.py
"""
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from common import BASE_DIR, log

PROFILE = os.path.join(BASE_DIR, "chrome-profile-safeworking")
TIMEOUT_SEC = 900


def main():
    os.makedirs(PROFILE, exist_ok=True)
    opts = Options()
    opts.add_argument(f"--user-data-dir={PROFILE}")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("--window-size=1100,900")
    opts.add_argument("--disable-features=MacAppCodeSignClone")
    d = webdriver.Chrome(options=opts)
    d.get("https://nid.naver.com/nidlogin.login")
    log("safeworking 계정으로 로그인하세요('로그인 상태 유지' 체크) — 최대 15분 대기")
    waited = 0
    while waited < TIMEOUT_SEC:
        jar = {c["name"]: c for c in d.get_cookies()}
        if "NID_AUT" in jar and "NID_SES" in jar and "expiry" in jar["NID_AUT"]:
            log("로그인 감지 — 저장 중")
            time.sleep(6)
            d.get("https://blog.naver.com/safeworking")
            time.sleep(3)
            log(f"프로필 저장 완료: {PROFILE}")
            d.quit()
            return 0
        time.sleep(2)
        waited += 2
    d.quit()
    log("시간 초과 — 로그인하지 않았습니다")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
