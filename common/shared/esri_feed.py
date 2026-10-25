"""Esri ArcGIS 블로그에서 GeoAI·재난 관련 글을 모아 뉴스 항목 형태로 돌려준다.

배경: esri.com 은 일반 HTTP 요청을 403 으로 막고(RSS 도 빈 채널) 실제 브라우저만
      허용한다. 그래서 헤드리스 크롬으로 목록 페이지를 읽어 파싱한다.

필터: 블로그에는 GeoAI·재난과 무관한 글(제품 공지, UI 팁 등)이 훨씬 많으므로
      재난·AI·원격탐사 관련 키워드가 든 글만 고른다(검색 오염 방지).

반환 형태는 fetch_news 의 뉴스 항목과 동일해서 그대로 소스 풀에 합칠 수 있다.
"""
import re
from datetime import datetime, timedelta, timezone

from common import log

BLOG_URL = "https://www.esri.com/arcgis-blog/"

# GeoAI 재난관리와 맞닿은 글만 통과시키는 키워드(제목+카테고리에서 검사)
RELEVANT = [
    "flood", "wildfire", "fire", "smoke", "disaster", "emergency", "hazard",
    "earthquake", "storm", "hurricane", "typhoon", "landslide", "drought",
    "public safety", "safety", "risk", "response", "resilience", "damage",
    "evacuation", "weather", "climate",
    "ai", "artificial intelligence", "machine learning", "deep learning",
    "imagery", "remote sensing", "satellite", "sentinel", "drone", "uav",
    "geoai", "raster", "elevation", "gis", "qgis", "arcgis", "geospatial",
]

_DATE_RE = re.compile(
    r"([A-Z][a-z]{2,8})\.?\s+(\d{1,2}),\s*(\d{4})")   # 'July 22, 2026' / 'Jul 14, 2026'


def _driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    o = Options()
    o.add_argument("--headless=new")
    o.add_argument("--window-size=1400,2000")
    o.add_argument("--lang=en-US")
    o.add_argument("--disable-blink-features=AutomationControlled")
    o.add_argument(
        "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    # 크롬이 실행마다 앱 전체(~1.4GB)를 임시 폴더에 복제하고 남기는 것을 막는다(2026-10-09)
    o.add_argument("--disable-features=MacAppCodeSignClone")
    return webdriver.Chrome(options=o)


def _parse_date(text):
    m = _DATE_RE.search(text or "")
    if not m:
        return None
    for fmt in ("%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(f"{m.group(1)[:9]} {m.group(2)} {m.group(3)}",
                                     fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


_RELEVANT_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in RELEVANT) + r")\b", re.I)


def _is_relevant(text):
    """단어 경계로 매칭한다. (부분일치면 저자명 'Tait' 의 ai 같은 오탐이 생김)"""
    return bool(_RELEVANT_RE.search(text or ""))


def fetch_esri_blog(within_days=30, limit=5, wait=8):
    """ArcGIS 블로그에서 최근 GeoAI·재난 관련 글을 뉴스 항목 형태로 돌려준다."""
    import time
    from selenium.webdriver.common.by import By
    d = None
    try:
        d = _driver()
        d.get(BLOG_URL)
        time.sleep(wait)   # 봇 방어/렌더 대기
        anchors = d.find_elements(By.CSS_SELECTOR, 'a[href*="/arcgis-blog/products/"]')
        cutoff = datetime.now(timezone.utc) - timedelta(days=within_days)
        seen, items = set(), []
        for a in anchors:
            href = (a.get_attribute("href") or "").split("?")[0]
            if not href or href in seen:
                continue
            title = (a.text or "").strip()
            try:
                ctx = a.find_element(By.XPATH, "./ancestor::*[self::article or self::li "
                                               "or self::div][1]").text or ""
            except Exception:
                ctx = title
            lines = [s.strip() for s in ctx.split("\n") if s.strip()]
            if not title and len(lines) > 1:
                title = lines[1]
            if not title:
                continue
            pub = _parse_date(lines[0] if lines else "")
            if pub is None or pub < cutoff:
                continue
            # 제목 + 카테고리줄로 관련성 판단
            if not _is_relevant(f"{title} {lines[0] if lines else ''}"):
                continue
            seen.add(href)
            items.append({
                "title": f"{title} - Esri ArcGIS Blog",
                "link": href,
                "source": "ArcGIS Blog",
                "published": pub,
                "published_str": pub.strftime("%Y-%m-%d"),
            })
        items.sort(key=lambda x: x["published"], reverse=True)
        return items[:limit]
    except Exception as e:
        log(f"Esri 블로그 수집 실패({type(e).__name__}) → 건너뜀")
        return []
    finally:
        if d is not None:
            try:
                d.quit()
            except Exception:
                pass


if __name__ == "__main__":
    for it in fetch_esri_blog():
        print(f"  [{it['published_str']}] {it['title'][:70]}")
