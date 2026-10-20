"""로그인 세션(쿠키)이 아직 유효한지, 글쓰기 에디터까지 진입되는지 점검한다.

발행은 하지 않는다. 종료코드 0=정상, 1=세션 만료/문제.
"""
import sys
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from common import load_config, log
from publish_naver import build_driver


def main():
    cfg = load_config()
    d = build_driver(headless=True)
    try:
        d.get(f"https://blog.naver.com/GoBlogWrite.naver?blogId={cfg['naver_id']}")
        time.sleep(5)
        try:
            d.switch_to.alert.accept()
        except Exception:
            pass
        url = d.current_url
        if "nidlogin" in url or "nid.naver.com" in url:
            log("❌ 로그인 세션 만료 → login_setup.py 재실행 필요")
            return 1
        try:
            WebDriverWait(d, 15).until(
                EC.frame_to_be_available_and_switch_to_it((By.ID, "mainFrame")))
            time.sleep(2)
            d.find_element(
                By.CSS_SELECTOR, ".se-section-documentTitle .se-text-paragraph")
            log("✅ 로그인 정상 + 에디터 진입 성공 (자동 발행 준비 완료)")
            return 0
        except Exception:
            log("⚠️ 로그인은 됐으나 에디터 진입 실패(에디터 구조 변경 가능)")
            return 1
    finally:
        d.quit()


if __name__ == "__main__":
    sys.exit(main())
