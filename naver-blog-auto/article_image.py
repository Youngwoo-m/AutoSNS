"""각 뉴스 블록에 들어갈 이미지를 준비한다.

1) 기사 URL(Google News 링크)을 헤드리스 브라우저로 열어 실제 기사로 리다이렉트시킨 뒤
   og:image 를 추출·다운로드한다.
2) 기사 이미지가 없으면 Gamma 로 그 뉴스용 이미지를 생성한다.
각 block 에 block["image"] (경로 또는 None), block["image_from"] ("article"/"gamma") 설정.
"""
import os
import time
import urllib.request
from urllib.parse import quote

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from common import POSTS_DIR, log, start_chrome

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _driver():
    o = Options()
    o.add_argument("--headless=new")
    o.add_argument("--window-size=1200,900")
    o.add_argument("--lang=ko-KR")
    o.add_argument("--disable-blink-features=AutomationControlled")
    o.set_capability("unhandledPromptBehavior", "accept")
    return start_chrome(o)


def _open_article(driver, url):
    """기사 URL 을 열고 (최종URL, og:image) 를 돌려준다.

    Google News RSS 링크는 JS 리다이렉트로 실제 기사에 도착하므로, 그때의
    current_url 을 '실제 기사 주소'로 함께 얻는다(블로그 본문 링크에 사용).
    """
    driver.get(url)
    time.sleep(5)  # Google News JS 리다이렉트 대기
    try:
        driver.switch_to.alert.accept()
    except Exception:
        pass
    final = driver.current_url or url
    og = ""
    for sel in ("meta[property='og:image']", "meta[property='og:image:url']",
                "meta[name='twitter:image']", "meta[itemprop='image']"):
        for e in driver.find_elements(By.CSS_SELECTOR, sel):
            c = (e.get_attribute("content") or "").strip()
            if c.startswith("http"):
                og = c
                break
        if og:
            break
    return final, og


def _safe_url(u):
    """URL 에 한글 등 non-ASCII 가 있으면 퍼센트 인코딩(이미 인코딩된 %xx 는 보존)."""
    try:
        u.encode("ascii")
        return u
    except UnicodeEncodeError:
        return quote(u, safe="%/:=&?~#+!$,;'@()*[]")


def _download(url, dest):
    url = _safe_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        ctype = (r.headers.get("Content-Type") or "").lower()
        data = r.read()
    # webp 는 클립보드(System.Drawing)에서 못 여니 제외, 너무 작은 것도 제외
    if "webp" in ctype or len(data) < 3000:
        return False
    with open(dest, "wb") as f:
        f.write(data)
    return True


def prepare_images(blocks, gamma_fallback=True):
    """뉴스 블록들에 이미지를 채운다."""
    d = _driver()
    try:
        for i, blk in enumerate(blocks, 1):
            # 손으로 고른 이미지는 그대로 둔다 — 출처가 법령 안내 사이트처럼 대표 이미지가
            # 로고뿐인 경우 기사 이미지를 다시 받으면 로고가 들어간다(2026-09-29 수동 글).
            if blk.get("keep_image") and blk.get("image") and os.path.exists(blk["image"]):
                log(f"[{i}] 지정 이미지 유지")
                continue
            blk["image"] = None
            blk["image_from"] = None
            try:
                final, og = _open_article(d, blk["source"]["link"])
                # 구글뉴스 리다이렉트가 아닌 '실제 기사 주소'를 링크용으로 보관
                if final and "news.google.com" not in final:
                    blk["source"]["real_link"] = final
                if og:
                    dest = os.path.join(POSTS_DIR, f"art_{i}.img")
                    if _download(og, dest):
                        blk["image"] = dest
                        blk["image_from"] = "article"
                        log(f"[{i}] 기사 이미지 확보")
                        continue
                log(f"[{i}] 기사 이미지 없음 → Gamma 대체 예정")
            except Exception as e:
                log(f"[{i}] 기사 이미지 추출 실패({type(e).__name__}) → Gamma 대체 예정")
    finally:
        d.quit()

    if gamma_fallback:
        from gamma_image import make_news_gamma_image
        for i, blk in enumerate(blocks, 1):
            if blk.get("image"):
                continue
            try:
                blk["image"] = make_news_gamma_image(blk)
                blk["image_from"] = "gamma"
                log(f"[{i}] Gamma 대체 이미지 생성")
            except Exception as e:
                log(f"[{i}] Gamma 대체 이미지 실패: {e}")
    return blocks


if __name__ == "__main__":
    import json
    import sys
    files = sorted(f for f in os.listdir(POSTS_DIR) if f.endswith(".json"))
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(POSTS_DIR, files[-1])
    data = json.load(open(path, encoding="utf-8"))
    for b in prepare_images(data.get("news_blocks", [])):
        print(b["index"], b["image_from"], b["image"])
