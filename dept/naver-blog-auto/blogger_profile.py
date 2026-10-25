"""블로거 사용자 프로필(GeoAI_NA) 사진을 바꾼다.

블로거 API 로는 프로필 사진을 못 바꾼다(users 는 읽기 전용). 그래서 브라우저로 한다.
로그인 세션은 youtube-shorts-auto/chrome-profile-youtube (ds2eye@gmail.com) 를 쓴다.

화면 흐름에서 걸리는 부분:
  · '컴퓨터에서 업로드' 는 구글 피커의 드라이브 업로드라 자동화가 번거롭다.
    대신 'URL로 업로드' 를 쓰고 공개 URL 을 넣는다(네이버 블로그 프로필 이미지 URL 이
    공개로 열려 있어 그대로 쓸 수 있다 — 구글이 받아서 자기 서버로 복사한다).
  · URL 입력칸은 docs.google.com/picker iframe 안에 있다(상위 문서에서는 안 보인다).
  · 확인 버튼 이름은 '삽입' 이고, 이 화면은 항목별 자동 저장이라 하단에 '저장' 이 없다.
    삽입을 누르는 순간 반영된다.

주의: 이 프로필은 SMU재난안전학과·재난안전과 GeoAI 두 블로그가 함께 쓴다.
      smuds2026 은 테마 CSS 에서 Profile 가젯을 숨겨 놨으므로(assets/blogger/theme.css)
      블로그 사이드바에는 안 나오고 블로거 프로필 페이지·작성자 표시에만 보인다.

사용:  ./.venv/bin/python blogger_profile.py --url https://.../profile_a.png
"""
import argparse
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

PROFILE_DIR = "/Volumes/USB256/devAPP/AutoSNS/channels/youtube-shorts-auto/chrome-profile-youtube"
EDIT_URL = "https://www.blogger.com/profile/edit"
PICKER = "docs.google.com/picker"


def build_driver(headless=False):
    o = Options()
    o.add_argument(f"--user-data-dir={PROFILE_DIR}")
    o.add_argument("--disable-blink-features=AutomationControlled")
    o.add_experimental_option("excludeSwitches", ["enable-automation"])
    o.add_argument("--window-size=1400,1000")
    o.add_argument("--lang=ko-KR")
    if headless:
        o.add_argument("--headless=new")
    # 크롬이 실행마다 앱 전체(~1.4GB)를 임시 폴더에 복제하고 남기는 것을 막는다(2026-10-09)
    o.add_argument("--disable-features=MacAppCodeSignClone")
    return webdriver.Chrome(options=o)


def _picker_input(d):
    """피커 iframe 으로 들어가 URL 입력칸을 돌려준다."""
    d.switch_to.default_content()
    for f in d.find_elements(By.TAG_NAME, "iframe"):
        if PICKER not in (f.get_attribute("src") or ""):
            continue
        d.switch_to.frame(f)
        for e in d.find_elements(By.CSS_SELECTOR, "input[type=text]"):
            if e.is_displayed():
                return e
        d.switch_to.default_content()
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="공개로 열려 있는 이미지 URL")
    a = ap.parse_args()

    d = build_driver()
    try:
        d.get(EDIT_URL)
        time.sleep(8)
        had = "프로필 사진 없음" in d.find_element(By.TAG_NAME, "body").text
        print("변경 전 프로필 사진:", "없음" if had else "있음")

        d.find_element(By.XPATH, "//*[contains(text(),'URL로 업로드')]").click()
        time.sleep(4)
        box = _picker_input(d)
        if box is None:
            raise SystemExit("❌ URL 입력칸을 못 찾았습니다(피커 구조 변경?)")
        box.click()
        box.send_keys(a.url)
        time.sleep(4)            # 미리보기가 뜰 때까지 기다린다

        for e in d.find_elements(By.CSS_SELECTOR, "div[role=button], button"):
            if (e.text or "").strip() == "삽입" and e.is_displayed():
                e.click()
                break
        else:
            raise SystemExit("❌ '삽입' 버튼을 못 찾았습니다 — URL 을 읽지 못했을 수 있습니다")
        time.sleep(6)

        d.switch_to.default_content()
        d.get(EDIT_URL)
        time.sleep(8)
        still_empty = "프로필 사진 없음" in d.find_element(By.TAG_NAME, "body").text
        if still_empty:
            raise SystemExit("❌ 반영되지 않았습니다")
        print("✅ 프로필 사진 반영 완료")
    finally:
        d.quit()


if __name__ == "__main__":
    main()
