"""네이버 검색 API 로 블로그/웹 문서를 검색해 뉴스와 같은 형태로 돌려준다.

'네이버 검색 API'(2026-10 부터 NAVER API HUB, naverapihub.apigw.ntruss.com) 사용. 키는 config.news.naver_search 에.
블로그 검색은 postdate(작성일)가 있어 최근 글만 거를 수 있다.

fetch_news 가 이 결과를 뉴스 항목과 같은 형태(title/link/source/published)로 받아
소스 풀에 합친다. 키가 없거나 호출 실패면 빈 목록을 돌려준다(뉴스 수집엔 지장 없음).
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

from common import log

KST = timezone(timedelta(hours=9))

# 네이버 검색 API 는 짧은 시간에 몰아 쏘면 429(errorCode 012)로 거절한다.
# 질의가 29개라 딜레이 없이 돌리면 20회 언저리에서 막혔다(2026-09-21 저녁 6건 유실,
# 재현 시 21번째 요청 1.81초 지점에서 429). 간격을 두고, 막히면 쉬었다 다시 던진다.
_MIN_GAP = 0.2          # 초당 5회 — 재현에서 막힌 11.6회/초보다 넉넉히 아래
_RETRY_WAIT = 1.5       # 429 를 만나면 이만큼 쉰다(재현에서 1.2초면 회복했다)
_RETRIES = 2
_last_call = 0.0


def _api_get(url, cid, secret, what, q):
    """검색 API 를 호출해 JSON 을 돌려준다. 실패하면 이유를 남기고 None."""
    global _last_call
    req = urllib.request.Request(url, headers={
        "X-NCP-APIGW-API-KEY-ID": cid, "X-NCP-APIGW-API-KEY": secret,
        "User-Agent": "smuds/1.0"})
    for attempt in range(_RETRIES + 1):
        gap = _MIN_GAP - (time.monotonic() - _last_call)
        if gap > 0:
            time.sleep(gap)
        _last_call = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < _RETRIES:
                time.sleep(_RETRY_WAIT)
                continue
            # 무엇이 잘못됐는지 알아야 고칠 수 있다 — 코드까지 남긴다
            log(f"{what} 실패(q='{q}': HTTP {e.code})")
            return None
        except Exception as e:
            log(f"{what} 실패(q='{q}': {type(e).__name__})")
            return None
    return None


_MAX_EXPAND = 8         # 질의 하나가 펼쳐지는 최대 개수(호출 수 폭증 방지)


def _expand_query(q):
    """구글 문법 'A OR B' 질의를 네이버가 알아듣는 단순 질의 여러 개로 펼친다.

    네이버 검색 API 는 OR 을 지원하지 않아, OR 이 든 질의는 0건을 돌려준다
    (2026-09-27 확인: 기본판 26개 중 24개, 토요일 AI판 5개 전부 0건).
    구글처럼 OR 은 '바로 옆 단어끼리' 묶는다고 보고 곱집합으로 펼친다:
      '제천 재난 OR 화재 OR 호우'   → 제천 재난 / 제천 화재 / 제천 호우
      '충북 OR 충청북도 재난안전'   → 충북 재난안전 / 충청북도 재난안전
    그냥 OR 로 자르면 '화재'처럼 지역 없는 단독 질의가 생겨 전국 기사가 쏟아진다.
    """
    toks = q.split()
    groups, i = [], 0
    while i < len(toks):
        g = [toks[i]]
        while i + 2 < len(toks) and toks[i + 1] == "OR":
            g.append(toks[i + 2])
            i += 2
        groups.append(list(dict.fromkeys(g)))
        i += 1
    out = [[]]
    for g in groups:
        out = [a + [b] for a in out for b in g]
    seen, res = set(), []
    for words in out:
        w = list(dict.fromkeys(words))            # '속보 … 속보' 같은 반복 단어 정리
        s = " ".join(w)
        if s and s not in seen:
            seen.add(s)
            res.append(s)
    return res[:_MAX_EXPAND]


def _expand_all(queries):
    seen, res = set(), []
    for q in queries:
        for s in _expand_query(q):
            if s not in seen:
                seen.add(s)
                res.append(s)
    return res


def _clean(t):
    t = re.sub(r"<[^>]+>", "", t or "")
    for a, b in [("&quot;", '"'), ("&amp;", "&"), ("&lt;", "<"),
                 ("&gt;", ">"), ("&#39;", "'"), ("&nbsp;", " ")]:
        t = t.replace(a, b)
    return t.strip()


def _query_keywords(queries):
    """검색어 문자열들에서 핵심 키워드 토큰을 뽑는다(제목 필터용).

    'GeoAI OR 지오AI OR 공간정보 AI' → {GeoAI, 지오AI, 공간정보, AI}
    'AI' 처럼 너무 흔한 2글자 영문 단독어는 오탐이 많아 제외한다.
    """
    kws = set()
    for q in queries:
        for tok in re.split(r"\s+|OR|\||,", q):
            tok = tok.strip()
            if len(tok) < 2:
                continue
            if tok.isascii() and len(tok) <= 2:   # 'AI' 같은 2글자 영문 단독 제외
                continue
            kws.add(tok)
    return kws


def naver_blog_search(queries, cid, secret, within_days=7, per_query=10, total=8,
                      exclude_links=()):
    """네이버 블로그 검색 결과를 뉴스 형태 항목 리스트로 돌려준다.

    노이즈가 많아, 제목에 검색어 핵심 키워드가 실제로 든 글만 남긴다(오염 방지).
    """
    if not cid or not secret:
        return []
    keywords = _query_keywords(queries)
    cutoff = datetime.now(timezone.utc) - timedelta(days=within_days)
    seen, items = set(), []
    for q in _expand_all(queries):
        url = "https://naverapihub.apigw.ntruss.com/search/v1/blog?" + urllib.parse.urlencode(
            {"query": q, "display": per_query, "sort": "date"})
        data = _api_get(url, cid, secret, "네이버 블로그 검색", q)
        if data is None:
            continue
        for it in data.get("items", []):
            link = it.get("link", "")
            if not link or link in seen:
                continue
            # 우리 블로그 글이 다시 소스로 잡히는 '자기 인용'을 막는다
            if any(x and x in link for x in exclude_links):
                continue
            try:
                pub = datetime.strptime(it.get("postdate", ""), "%Y%m%d") \
                    .replace(tzinfo=KST).astimezone(timezone.utc)
            except Exception:
                continue
            if pub < cutoff:
                continue
            title = _clean(it.get("title", ""))
            # 제목에 검색어 핵심 키워드가 실제로 들어야 채택(느슨한 오탐 제거)
            if keywords and not any(k in title for k in keywords):
                continue
            seen.add(link)
            blogger = it.get("bloggername", "")
            items.append({
                "title": f"{title} - {blogger} (네이버블로그)",
                "link": link,
                "source": "네이버블로그",
                "published": pub,
                "published_str": pub.astimezone().strftime("%Y-%m-%d"),
            })
    items.sort(key=lambda x: x["published"], reverse=True)
    return items[:total]


def _news_source_name(link):
    """기사 원문 링크의 도메인으로 언론사 힌트를 만든다(예: yna.co.kr)."""
    try:
        host = urllib.parse.urlparse(link).netloc.replace("www.", "")
        return host or "뉴스"
    except Exception:
        return "뉴스"


def naver_news_search(queries, cid, secret, within_days=7, per_query=10, total=10,
                      exclude_links=()):
    """네이버 뉴스 검색(구글뉴스 외 국내 언론) 결과를 뉴스 항목 리스트로 돌려준다.

    구글 뉴스 RSS 를 보완한다(연합·KBS·중앙·지역신문 등 네이버 제휴 매체 폭넓게 포함).
    link 는 네이버 리다이렉트 대신 기사 원문 주소(originallink)를 우선 사용하고,
    제목에 검색어 핵심 키워드가 실제로 든 기사만 남긴다(오염 방지).
    """
    if not cid or not secret:
        return []
    from email.utils import parsedate_to_datetime
    keywords = _query_keywords(queries)
    cutoff = datetime.now(timezone.utc) - timedelta(days=within_days)
    seen, items = set(), []
    for q in _expand_all(queries):
        url = "https://naverapihub.apigw.ntruss.com/search/v1/news?" + urllib.parse.urlencode(
            {"query": q, "display": per_query, "sort": "date"})
        data = _api_get(url, cid, secret, "네이버 뉴스 검색", q)
        if data is None:
            continue
        for it in data.get("items", []):
            link = (it.get("originallink") or it.get("link") or "").strip()
            if not link or link in seen:
                continue
            if any(x and x in link for x in exclude_links):
                continue
            try:
                pub = parsedate_to_datetime(it.get("pubDate", ""))
                if pub.tzinfo is None:
                    pub = pub.replace(tzinfo=KST)
                pub = pub.astimezone(timezone.utc)
            except Exception:
                continue
            if pub < cutoff:
                continue
            title = _clean(it.get("title", ""))
            if keywords and not any(k in title for k in keywords):
                continue
            seen.add(link)
            items.append({
                "title": f"{title} - {_news_source_name(link)}",
                "link": link,
                "source": "네이버뉴스",
                "published": pub,
                "published_str": pub.astimezone().strftime("%Y-%m-%d"),
            })
    items.sort(key=lambda x: x["published"], reverse=True)
    return items[:total]


if __name__ == "__main__":
    from common import load_config
    ns = load_config().get("news", {}).get("naver_search", {})
    qs = load_config().get("news", {}).get("queries", ["재난안전"])[:3]
    print("[블로그]")
    for it in naver_blog_search(qs, ns.get("client_id"), ns.get("client_secret")):
        print(f"  [{it['published_str']}] {it['title'][:56]}")
    print("[뉴스]")
    for it in naver_news_search(qs, ns.get("client_id"), ns.get("client_secret")):
        print(f"  [{it['published_str']}] {it['title'][:56]}")
