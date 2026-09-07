"""무료 Google News RSS 에서 최신 재난안전 뉴스를 가져온다. (API 키 불필요)

표준 라이브러리만 사용. 반환: [{title, link, source, published(dt), published_str}]
실제 기사 목록만 돌려주므로, 생성 단계에서 '없는 사실'을 지어낼 여지를 줄인다.
(네이버 자동포스팅의 검증된 fetch_news 를 그대로 재사용.)
"""
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

from common import load_config, log

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _rss_url(query):
    q = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"


def _fetch_one(query, within_days):
    url = _rss_url(query)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read()
    root = ET.fromstring(raw)
    cutoff = datetime.now(timezone.utc) - timedelta(days=within_days)
    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        source_el = item.find("source")
        source = (source_el.text.strip() if source_el is not None and source_el.text
                  else "")
        pub_raw = item.findtext("pubDate")
        try:
            pub = parsedate_to_datetime(pub_raw)
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
        except Exception:
            pub = datetime.now(timezone.utc)
        if pub < cutoff:
            continue
        items.append({
            "title": title,
            "link": link,
            "source": source,
            "published": pub,
            "published_str": pub.astimezone().strftime("%Y-%m-%d"),
        })
    return items


def _is_blocked(item, block_sources):
    """외국/비한국 출처를 걸러낸다. (source 또는 title 에 차단 키워드 포함 시)"""
    hay = (item.get("source", "") + " " + item.get("title", "")).lower()
    return any(b.lower() in hay for b in block_sources)


# 지역명 별칭: 기사 제목/출처에 이 중 하나가 들어가면 해당 지역으로 인식한다.
REGION_ALIASES = {
    "제천": ["제천"],
    "충북": ["충북", "충청북도"],
    "충남": ["충남", "충청남도"],
    "강원": ["강원"],
    "경기": ["경기"],
    "서울": ["서울"],
    "인천": ["인천"],
}


def _region_rank(item, region_priority, exclude=()):
    """기사가 어느 우선 지역에 속하는지 순위를 매긴다.

    region_priority 앞쪽일수록 높은 우선순위(작은 값). 어디에도 안 걸리면 가장 낮은 값.
    exclude: 지역명을 '오탐'으로 포함하는 어구(예: "평택제천고속도로")를 매칭 전에 지운다.
    """
    hay = item.get("title", "") + " " + item.get("source", "")
    for term in exclude:
        hay = hay.replace(term, "")
    for rank, region in enumerate(region_priority):
        for alias in REGION_ALIASES.get(region, [region]):
            if alias in hay:
                return rank
    return len(region_priority)


def _norm_title(title):
    """제목을 비교용으로 정규화: 끝의 ' - 출처' 제거 후 한글/영숫자만 남긴다."""
    t = re.sub(r"\s*-\s*[^-]+$", "", title)      # 끝에 붙는 ' - 언론사' 제거
    return re.sub(r"[^0-9A-Za-z\uac00-\ud7a3]", "", t)


def _dedup_similar(items, threshold):
    """같은 사건을 다룬 유사 제목 기사를 하나만 남긴다(먼저 온 것 유지).

    threshold(0~1)가 높을수록 '거의 같아야' 중복으로 본다. 0 이면 병합 안 함.
    """
    if threshold <= 0:
        return items
    from difflib import SequenceMatcher
    kept, kept_norm = [], []
    for it in items:
        nt = _norm_title(it.get("title", ""))
        if any(SequenceMatcher(None, nt, k).ratio() >= threshold for k in kept_norm):
            continue
        kept.append(it)
        kept_norm.append(nt)
    return kept


def fetch_news():
    cfg = load_config().get("news", {})
    queries = cfg.get("queries", ["재난안전"])
    within = cfg.get("within_days", 7)
    max_items = cfg.get("max_items", 8)
    block_sources = cfg.get("block_sources", [])
    region_priority = cfg.get("region_priority", [])
    region_exclude = cfg.get("region_exclude", [])
    dedup_similarity = cfg.get("dedup_similarity", 0.6)

    seen, results, blocked = set(), [], 0
    for q in queries:
        try:
            for it in _fetch_one(q, within):
                key = it["title"]
                if not key or key in seen:
                    continue
                if _is_blocked(it, block_sources):
                    blocked += 1
                    continue
                seen.add(key)
                results.append(it)
        except Exception as e:
            log(f"뉴스 수집 실패(query='{q}'): {e}")
    if blocked:
        log(f"외국/차단 출처 {blocked}건 제외.")

    esri_added = []
    # Esri ArcGIS 블로그(GeoAI·재난) 글을 소스 풀에 추가 (config.news.esri_blog=true)
    if cfg.get("esri_blog", False):
        try:
            from esri_feed import fetch_esri_blog
            eb = fetch_esri_blog(within_days=cfg.get("esri_within_days", 30),
                                 limit=cfg.get("esri_max", 4))
            links = {r.get("link") for r in results}
            new = [it for it in eb if it["link"] not in links]
            results.extend(new)
            esri_added = new
            log(f"Esri 블로그 {len(new)}건 추가")
        except Exception as e:
            log(f"Esri 블로그 건너뜀({type(e).__name__})")


    # 커넥트데일리(i-eumnews) 공간정보 기사 추가 (config.news.ieum=true)

    # GeoAI 판에서 공간정보 업계 소식은 구글/네이버 검색에 잘 안 잡혀 전문지로 보완한다.

    if cfg.get("ieum", False):

        try:

            from ieum_feed import fetch_ieum_news

            ie = fetch_ieum_news(sections=cfg.get("ieum_sections", ["공간정보"]),

                                 within_days=cfg.get("ieum_within_days", 30),

                                 limit=cfg.get("ieum_max", 3))

            links = {r.get("link") for r in results}

            new = [it for it in ie if it["link"] not in links]

            results.extend(new)

            log(f"커넥트데일리 공간정보 {len(new)}건 추가")

        except Exception as e:

            log(f"커넥트데일리 건너뜀({type(e).__name__})")

    # 웹(네이버 블로그) 검색 결과를 소스 풀에 추가 (config.news.web_naver=true + 키)
    ns = cfg.get("naver_search", {})
    if cfg.get("web_naver", False) and ns.get("client_id"):
        try:
            from naver_search import naver_blog_search
            nb = naver_blog_search(queries, ns.get("client_id"), ns.get("client_secret"),
                                   within_days=within, total=cfg.get("web_max", 8),
                                   exclude_links=ns.get("exclude", []))
            links = {r.get("link") for r in results}
            new = [it for it in nb if it["link"] not in links]
            results.extend(new)
            log(f"네이버 블로그 검색 {len(new)}건 추가")
        except Exception as e:
            log(f"네이버 블로그 검색 건너뜀({type(e).__name__})")

    # 네이버 뉴스 검색(구글뉴스 외 국내 언론) 결과를 소스 풀에 추가
    # (config.news.web_naver_news=true + naver_search 키). 구글 RSS 를 보완한다.
    if cfg.get("web_naver_news", False) and ns.get("client_id"):
        try:
            from naver_search import naver_news_search
            nn = naver_news_search(queries, ns.get("client_id"), ns.get("client_secret"),
                                   within_days=within, total=cfg.get("naver_news_max", 10),
                                   exclude_links=ns.get("exclude", []))
            links = {r.get("link") for r in results}
            new = [it for it in nn if it["link"] not in links]
            results.extend(new)
            log(f"네이버 뉴스 검색 {len(new)}건 추가")
        except Exception as e:
            log(f"네이버 뉴스 검색 건너뜀({type(e).__name__})")

    # 최신순 정렬 → 유사(중복)기사 병합 → 지역 우선 안정정렬 → 상위 N건
    results.sort(key=lambda x: x["published"], reverse=True)
    before_dedup = len(results)
    results = _dedup_similar(results, dedup_similarity)
    merged = before_dedup - len(results)
    if region_priority:
        results.sort(key=lambda x: _region_rank(x, region_priority, region_exclude))
    results = results[:max_items]
    # Esri 글은 날짜가 조금 지나도 참고 가치가 커서, 최소 N건은 자리를 보장한다
    keep = cfg.get("esri_keep", 2)
    if esri_added and keep:
        have = {r.get("link") for r in results}
        missing = [e for e in esri_added[:keep] if e.get("link") not in have]
        if missing:
            results = results[:max(0, max_items - len(missing))] + missing
            log(f"Esri 글 {len(missing)}건 자리 보장(참고용)")
    if region_priority:
        matched = sum(1 for x in results
                      if _region_rank(x, region_priority, region_exclude)
                      < len(region_priority))
        log(f"뉴스 {len(results)}건 수집(최근 {within}일, 지역우선 "
            f"{' > '.join(region_priority)}; 우선지역 {matched}건, 중복 {merged}건 병합).")
    else:
        log(f"뉴스 {len(results)}건 수집(최근 {within}일, 중복 {merged}건 병합).")
    return results


if __name__ == "__main__":
    for i, n in enumerate(fetch_news(), 1):
        print(f"{i}. [{n['published_str']}] {n['title']}  ({n['source']})")
