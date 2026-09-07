"""커넥트 데일리(i-eumnews.net)의 'Geo A.I > 공간정보' 기사를 뉴스 항목으로 돌려준다.

배경: GeoAI 판(토요일)은 구글 뉴스 RSS·네이버 검색만으로는 공간정보 업계 소식이
      잘 잡히지 않는다. 이 매체는 공간정보·GeoAI 전문지라 밀도가 높다.

수집 방식: 전체 RSS(/rss/rss_news.php) 한 번만 받아 item 의 <section>/<section2>
      필드로 원하는 섹션만 고른다(섹션별 RSS 는 제공되지 않음). 셀레니움 불필요.

반환 형태는 fetch_news 의 뉴스 항목과 같아서 그대로 소스 풀에 합칠 수 있다.
"""
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from common import log

RSS_URL = "https://www.i-eumnews.net/rss/rss_news.php"
SOURCE_NAME = "커넥트 데일리"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def _tag(block, name):
    """<link > 처럼 공백이 붙은 태그, CDATA 둘 다 처리."""
    m = re.search(rf"<{name}\s*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{name}>", block, re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def fetch_ieum_news(sections=("공간정보",), within_days=30, limit=4, timeout=20):
    """지정 섹션(section2)의 최근 기사를 뉴스 항목 형태로 돌려준다.

    sections 를 비우면 섹션 구분 없이 전체에서 최신순으로 가져온다.
    실패해도 예외를 올리지 않는다(뉴스 수집 전체가 멈추지 않도록).
    """
    try:
        req = urllib.request.Request(RSS_URL, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            xml = r.read().decode("utf-8", "replace")
    except Exception as e:
        log(f"커넥트데일리 수집 실패({type(e).__name__}) → 건너뜀")
        return []

    want = {s.strip() for s in (sections or ())}
    cutoff = datetime.now(timezone.utc) - timedelta(days=within_days)
    items = []
    for block in re.findall(r"<item>(.*?)</item>", xml, re.S):
        sec2 = _tag(block, "section2")
        if want and sec2 not in want:
            continue
        title, link = _tag(block, "title"), _tag(block, "link")
        if not (title and link):
            continue
        try:
            pub = parsedate_to_datetime(_tag(block, "pubDate"))
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if pub < cutoff:
            continue
        items.append({
            "title": f"{title} - {SOURCE_NAME}",
            "link": link,
            "source": f"{SOURCE_NAME}({sec2})" if sec2 else SOURCE_NAME,
            "published": pub,
            "published_str": pub.strftime("%Y-%m-%d"),
        })
    items.sort(key=lambda x: x["published"], reverse=True)
    return items[:limit]


if __name__ == "__main__":
    for it in fetch_ieum_news():
        print(f"  [{it['published_str']}] {it['title'][:70]}  {it['link']}")
