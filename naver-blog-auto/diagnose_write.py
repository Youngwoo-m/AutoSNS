"""글쓰기 에디터 진입 URL 후보를 점검한다. 어떤 URL이 SmartEditor 로 들어가는지 확인."""
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from common import PROFILE_DIR, load_config, log

cfg = load_config()
NID = cfg["naver_id"]

CANDIDATES = [
    f"https://blog.naver.com/{NID}?Redirect=Write",
    f"https://blog.naver.com/PostWriteForm.naver?blogId={NID}",
    f"https://blog.naver.com/GoBlogWrite.naver?blogId={NID}",
    f"https://blog.naver.com/{NID}/postwrite",
]


def build():
    o = Options()
    o.add_argument(f"--user-data-dir={PROFILE_DIR}")
    o.add_argument("--disable-blink-features=AutomationControlled")
    o.add_experimental_option("excludeSwitches", ["enable-automation"])
    o.add_argument("--window-size=1280,1000")
    o.set_capability("unhandledPromptBehavior", "accept")
    return webdriver.Chrome(options=o)


def check(driver, url):
    driver.get(url)
    time.sleep(5)
    try:
        driver.switch_to.alert.accept()
        time.sleep(1)
    except Exception:
        pass
    cur = driver.current_url
    title = driver.title
    frames = driver.find_elements(By.TAG_NAME, "iframe")
    frame_ids = [f.get_attribute("id") or f.get_attribute("name") or "?" for f in frames]
    src = driver.page_source
    markers = {
        "se-documentTitle": "se-documentTitle" in src,
        "se-section-text": "se-section-text" in src or "se-text-paragraph" in src,
        "mainFrame": "mainFrame" in src,
    }
    print(f"\n=== URL: {url}")
    print(f"  -> current_url: {cur}")
    print(f"  -> title: {title}")
    print(f"  -> iframes: {frame_ids}")
    print(f"  -> markers(top doc): {markers}")
    # mainFrame 안도 확인
    for fid in ("mainFrame",):
        try:
            driver.switch_to.frame(fid)
            s2 = driver.page_source
            print(f"  -> inside {fid}: se-documentTitle={'se-documentTitle' in s2}, "
                  f"se-text-paragraph={'se-text-paragraph' in s2}")
            driver.switch_to.default_content()
        except Exception as e:
            print(f"  -> inside {fid}: (없음/실패) {type(e).__name__}")


def main():
    d = build()
    try:
        for u in CANDIDATES:
            try:
                check(d, u)
            except Exception as e:
                print(f"\n=== URL: {u}\n  -> 예외: {type(e).__name__}: {e}")
    finally:
        d.quit()


if __name__ == "__main__":
    main()
