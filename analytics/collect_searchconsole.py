"""구글 서치콘솔에서 Blogger 블로그의 검색 유입(질의·페이지)을 가져온다.

왜: 우리가 올린 글이 '어떤 검색어로' 발견되는지는 서치콘솔에만 있다. 3줄 요약·FAQ 같은
    답변형 최적화가 실제로 먹히는지 확인하려면 이 데이터가 필요하다.
    (네이버 블로그는 서치콘솔 대상이 아니다 — 구글 색인이 되는 Blogger 만 본다.)

인증: scope=webmasters.readonly. 유튜브와 같은 client_secret.json 을 쓰고 토큰은 따로 둔다.
      최초 1회 인증은 사람이 해야 하므로 searchconsole_auth_setup.py 를 사용자가 실행한다.

결과: snapshots/parts/searchconsole.json
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analytics.common import log, save_part  # noqa: E402

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
BASE = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE, "token_searchconsole.json")
CLIENT_SECRET = os.path.join(os.path.dirname(BASE), "youtube-shorts-auto", "client_secret.json")
SITE_URL = "https://smusafety.blogspot.com/"
DAYS = 28            # 서치콘솔은 2~3일 지연이 있어 넉넉히 본다
TOP_N = 20


def _creds():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    if not os.path.exists(TOKEN_PATH):
        raise RuntimeError("서치콘솔 토큰 없음 — python searchconsole_auth_setup.py 로 인증하세요.")
    c = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not c.valid and c.expired and c.refresh_token:
        c.refresh(Request())
        with open(TOKEN_PATH, "w", encoding="utf-8") as f:
            f.write(c.to_json())
    return c


def _query(svc, site, start, end, dimension, limit):
    r = svc.searchanalytics().query(siteUrl=site, body={
        "startDate": start, "endDate": end,
        "dimensions": [dimension], "rowLimit": limit,
        "type": "web"}).execute()
    return r.get("rows", [])


def collect(site=SITE_URL, days=DAYS):
    from googleapiclient.discovery import build
    end = datetime.date.today()
    start = end - datetime.timedelta(days=days)
    svc = build("searchconsole", "v1", credentials=_creds(), cache_discovery=False)
    queries = _query(svc, site, str(start), str(end), "query", TOP_N)
    pages = _query(svc, site, str(start), str(end), "page", 10)
    items = [{"query": r["keys"][0], "clicks": r["clicks"], "impressions": r["impressions"],
              "ctr": round(r["ctr"] * 100, 1), "position": round(r["position"], 1)}
             for r in queries]
    data = {
        "site": site,
        "period": {"start": str(start), "end": str(end)},
        "items": items,
        "pages": [{"page": r["keys"][0], "clicks": r["clicks"],
                   "impressions": r["impressions"]} for r in pages],
        "totals": {"clicks": sum(r["clicks"] for r in queries),
                   "impressions": sum(r["impressions"] for r in queries)},
    }
    log(f"서치콘솔: 질의 {len(items)}건, 클릭 {data['totals']['clicks']:.0f}, "
        f"노출 {data['totals']['impressions']:.0f} ({start}~{end})")
    return data


def main():
    try:
        save_part("searchconsole", collect())
    except Exception as e:
        log(f"서치콘솔 수집 건너뜀: {type(e).__name__}: {str(e)[:120]}")


if __name__ == "__main__":
    main()
