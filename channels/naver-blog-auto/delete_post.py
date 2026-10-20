"""블로그에서 특정 제목의 최근 글을 찾아 삭제한다. (로그인 프로필 사용)

사용: python delete_post.py "<제목 일부>"
인자가 없으면 블로그 글 관리 페이지만 열어 스크린샷을 남긴다(탐색용).
"""
import sys
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from common import load_config, log
from publish_naver import build_driver, shot, click_if_present

BLOG_ID = "studs23"  # 실제 블로그 주소 ID (로그인 ID smuds 와 다름)


def main():
    log_no = sys.argv[1] if len(sys.argv) > 1 else ""
    do_delete = "--go" in sys.argv
    d = build_driver(False)
    try:
        d.get(f"https://blog.naver.com/{BLOG_ID}/{log_no}")
        time.sleep(5)
        try:
            d.switch_to.alert.accept()
        except Exception:
            pass
        try:
            WebDriverWait(d, 15).until(
                EC.frame_to_be_available_and_switch_to_it((By.ID, "mainFrame")))
            time.sleep(2)
        except Exception:
            log("mainFrame 없음")
        # '삭제' 버튼/링크 후보 덤프
        cands = d.find_elements(
            By.XPATH, "//a[normalize-space(text())='삭제'] | "
                      "//button[normalize-space(text())='삭제'] | "
                      "//*[normalize-space(text())='삭제']")
        log(f"'삭제' 후보 {len(cands)}개")
        shot(d, "postpage")
        if do_delete:
            # 화면에 보이는 '삭제' 링크만 클릭
            visible = [c for c in cands if c.is_displayed()]
            log(f"보이는 삭제 후보 {len(visible)}개")
            if visible:
                c = visible[-1]
                d.execute_script("arguments[0].scrollIntoView({block:'center'});", c)
                time.sleep(0.5)
                c.click()
                log("삭제 링크 클릭 → 확인 팝업 대기")
                time.sleep(2)
                shot(d, "confirm_popup")
                # 확인 팝업의 모든 버튼/링크 덤프
                for b in d.find_elements(By.XPATH, "//button | //a"):
                    t = (b.text or "").strip()
                    if t in ("삭제", "확인", "취소") and b.is_displayed():
                        log(f"팝업 버튼: '{t}' class={b.get_attribute('class')}")
                # 확인(삭제) 클릭 — 방금 클릭한 링크가 아닌, 팝업 안의 삭제 버튼
                btns = [b for b in d.find_elements(By.XPATH, "//button")
                        if (b.text or "").strip() == "삭제" and b.is_displayed()]
                if btns:
                    btns[-1].click()
                    log("확인 팝업 '삭제' 클릭")
                    time.sleep(3)
                shot(d, "after_delete")
    finally:
        d.quit()


if __name__ == "__main__":
    main()
