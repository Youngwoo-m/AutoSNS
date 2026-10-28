"""이미 발행한 개인 네이버 글(safeworking)에 태그만 넣고 다시 발행한다.

글 수정 화면을 열어 본문은 건드리지 않고, '발행' 설정 창의 태그 칸에 태그를 더한 뒤 발행을 누른다.
2026-10-28 교차 발행 184·189가 태그 없이 올라가 만들었다(원인은 naver_crosspost_personal.py 에서 고침).

    python3 shared/axlock.py run --job naver-add-tags --res profile:safeworking -- \
        ./.venv/bin/python naver_add_tags.py --log-no 224456995887 --tags "dop,PDOP" --dry|--go
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# 로그인 프로필은 본 체크아웃에만 있다(워크트리에서 돌려도 본 체크아웃 프로필을 쓴다)
_MAIN = os.path.realpath(os.path.join(HERE, "..", ".."))
if "/.claude/worktrees/" in _MAIN:
    _MAIN = _MAIN.split("/.claude/worktrees/")[0]
os.environ.setdefault("AX_NAVER_PROFILE", os.path.join(_MAIN, "dept", "naver-blog-auto", "chrome-profile-safeworking"))
sys.path.insert(0, HERE)

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from common import PROFILE_DIR, log
from publish_naver import click_if_present, shot

BLOG_ID = "safeworking"


def build_driver():
    opts = Options()
    opts.add_argument(f"--user-data-dir={PROFILE_DIR}")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    # 로그인 앱(일반 크롬)과 같은 진짜 키체인으로 쿠키를 읽는다(use-mock-keychain 빼기, 2026-10-28)
    opts.add_experimental_option("excludeSwitches", ["enable-automation", "use-mock-keychain"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("--window-size=1280,1000")
    opts.add_argument("--lang=ko-KR")
    opts.add_argument("--disable-features=MacAppCodeSignClone")
    opts.set_capability("unhandledPromptBehavior", "accept")
    return webdriver.Chrome(options=opts)


def current_tags(driver):
    # 태그 칸 상자 글자에서 '#태그' 를 뽑는다(입력 칸 안내문 '#태그 입력' 은 뺀다)
    import re
    text = driver.execute_script(
        "var i=document.getElementById('tag-input');var b=i;"
        "for(var k=0;k<4&&b.parentElement;k++){b=b.parentElement;if(b.innerText.indexOf('#')>=0&&b!==i)break;}"
        "return b.innerText;")
    return [t for t in re.findall(r"#([^\s#]+)", text or "") if t != "태그"]


def add_tags(log_no, tags, go):
    driver = build_driver()
    try:
        driver.get(f"https://blog.naver.com/PostUpdateForm.naver?blogId={BLOG_ID}&logNo={log_no}")
        time.sleep(4)
        if "nidlogin" in driver.current_url or "nid.naver.com" in driver.current_url:
            raise RuntimeError("로그인 세션이 만료되었습니다(로그인-개인 앱으로 다시 로그인).")
        try:
            WebDriverWait(driver, 10).until(EC.frame_to_be_available_and_switch_to_it((By.ID, "mainFrame")))
        except Exception:
            pass
        WebDriverWait(driver, 30).until(EC.presence_of_element_located(
            (By.XPATH, "//button[contains(@class,'publish') and contains(.,'발행')] | //*[contains(@class,'publish_btn')]")))
        time.sleep(2)
        # '작성 중인 글이 있습니다' 같은 팝업이 뜨면 취소해 원래 글을 연다
        click_if_present(driver, By.XPATH, "//*[contains(@class,'se-popup')]//button[contains(.,'취소')]", 2)
        if not click_if_present(driver, By.XPATH, "//button[contains(@class,'publish') and contains(.,'발행')]", 6):
            click_if_present(driver, By.XPATH, "//*[contains(@class,'publish_btn')]", 6)
        time.sleep(2)
        tag_input = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "tag-input")))
        have = current_tags(driver)
        log(f"{log_no}: 지금 태그 {have}")
        for t in tags:
            if t in have:
                continue
            tag_input.send_keys(t)
            tag_input.send_keys(Keys.ENTER)
            time.sleep(0.3)
        time.sleep(1)
        log(f"{log_no}: 넣은 뒤 태그 {current_tags(driver)}")
        shot(driver, f"tags_{log_no}")
        if not go:
            log("DRY: 발행 누르기 전에 멈춤")
            return "dry"
        if not click_if_present(driver, By.XPATH,
                "//div[contains(@class,'layer') or contains(@class,'option')]"
                "//button[contains(@class,'confirm') and contains(.,'발행')]", 6):
            click_if_present(driver, By.XPATH, "//button[contains(@class,'confirm_btn')]", 6)
        time.sleep(5)
        shot(driver, f"tags_after_{log_no}")
        return "published"
    finally:
        driver.quit()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--log-no", required=True)
    ap.add_argument("--tags", required=True, help="쉼표로 구분")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry", action="store_true")
    g.add_argument("--go", action="store_true")
    a = ap.parse_args()
    tags = [t.strip() for t in a.tags.split(",") if t.strip()][:30]
    print(add_tags(a.log_no, tags, a.go))


if __name__ == "__main__":
    main()
