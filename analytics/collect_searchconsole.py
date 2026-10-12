"""구글 서치콘솔에서 Blogger 블로그의 검색 유입(질의·페이지)을 가져온다.

왜: 우리가 올린 글이 '어떤 검색어로' 발견되는지는 서치콘솔에만 있다. 3줄 요약·FAQ 같은
    답변형 최적화가 실제로 먹히는지 확인하려면 이 데이터가 필요하다.
    (네이버 블로그는 서치콘솔 대상이 아니다 — 구글 색인이 되는 곳만 본다.)

계정에 등록된 속성을 모두 돌며 합산한다. 한 곳만 보던 때는 정작 색인이 된 티스토리가
집계에서 빠졌다(2026-10-12). 속성이 늘거나 줄어도 코드를 고칠 일이 없도록 목록을
API 에서 받아온다.

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


def _sites(svc):
    """계정에 등록된 속성 목록. 읽기 권한이 없는 것은 건너뛴다."""
    got = svc.sites().list().execute().get("siteEntry", [])
    return [x["siteUrl"] for x in got
            if x.get("permissionLevel") not in ("siteUnverifiedUser",)]


def collect(sites=None, days=DAYS):
    from googleapiclient.discovery import build
    end = datetime.date.today()
    start = end - datetime.timedelta(days=days)
    svc = build("searchconsole", "v1", credentials=_creds(), cache_discovery=False)
    sites = sites or _sites(svc)

    items, pages, per_site = [], [], []
    for site in sites:
        try:
            q = _query(svc, site, str(start), str(end), "query", TOP_N)
            p = _query(svc, site, str(start), str(end), "page", 10)
        except Exception as e:
            log(f"  {site}: 조회 실패({type(e).__name__}) — 건너뜀")
            continue
        items += [{"site": site, "query": r["keys"][0], "clicks": r["clicks"],
                   "impressions": r["impressions"], "ctr": round(r["ctr"] * 100, 1),
                   "position": round(r["position"], 1)} for r in q]
        pages += [{"site": site, "page": r["keys"][0], "clicks": r["clicks"],
                   "impressions": r["impressions"]} for r in p]
        per_site.append({"site": site, "queries": len(q),
                         "clicks": sum(r["clicks"] for r in q),
                         "impressions": sum(r["impressions"] for r in q)})
        log(f"  {site}: 질의 {len(q)}건, 클릭 {sum(r['clicks'] for r in q):.0f}, "
            f"노출 {sum(r['impressions'] for r in q):.0f}")

    items.sort(key=lambda x: (-x["impressions"], -x["clicks"]))
    pages.sort(key=lambda x: (-x["impressions"], -x["clicks"]))
    data = {
        "sites": sites,
        "period": {"start": str(start), "end": str(end)},
        "items": items[:TOP_N],
        "pages": pages[:10],
        "per_site": per_site,
        "totals": {"clicks": sum(s["clicks"] for s in per_site),
                   "impressions": sum(s["impressions"] for s in per_site)},
    }
    log(f"서치콘솔: 속성 {len(per_site)}곳, 질의 {len(items)}건, "
        f"클릭 {data['totals']['clicks']:.0f}, 노출 {data['totals']['impressions']:.0f} "
        f"({start}~{end})")
    return data


def main():
    try:
        # 0건(노출 없음)도 사실이므로 직전 수치로 덮지 않는다.
        save_part("searchconsole", collect(), allow_empty=True)
    except Exception as e:
        log(f"서치콘솔 수집 건너뜀: {type(e).__name__}: {str(e)[:120]}")


if __name__ == "__main__":
    main()
