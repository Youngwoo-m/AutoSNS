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
CLIENT_SECRET = os.path.join(os.path.dirname(BASE), "channels", "youtube-shorts-auto", "client_secret.json")
DAYS = 28            # 서치콘솔은 2~3일 지연이 있어 넉넉히 본다
TOP_N = 20


def _token_paths():
    """token_searchconsole.json 과 token_searchconsole_<계정>.json 전부.

    속성은 계정별로 등록되므로(학과 계정·개인 계정) 토큰도 계정마다 둔다.
    searchconsole_auth_setup.py <이름> 으로 추가한다."""
    import glob
    from shared import token_store            # 토큰은 암호화 저장소에 있다(옛 파일도 찾는다)
    names = token_store.stored_names()
    first = TOKEN_PATH if (token_store.name_for(TOKEN_PATH) in names
                           or os.path.exists(TOKEN_PATH)) else None
    pre = "SEARCHCONSOLE_TOKEN_"
    rest = {p for p in glob.glob(TOKEN_PATH.replace(".json", "_*.json")) if p != TOKEN_PATH}
    rest |= {TOKEN_PATH.replace(".json", f"_{n[len(pre):].lower()}.json")
             for n in names if n.startswith(pre)}
    return [p for p in [first] + sorted(rest) if p]


def _creds(path=None):
    from shared import token_store
    path = path or TOKEN_PATH
    if not token_store.exists(path):
        raise RuntimeError("서치콘솔 토큰 없음 — python searchconsole_auth_setup.py 로 인증하세요.")
    return token_store.load_google(path, SCOPES)


def _query(svc, site, start, end, dimension, limit):
    r = svc.searchanalytics().query(siteUrl=site, body={
        "startDate": start, "endDate": end,
        "dimensions": [dimension], "rowLimit": limit,
        "type": "web"}).execute()
    return r.get("rows", [])


def _total(svc, site, start, end):
    """속성 전체 클릭·노출. 노출이 적은 검색어는 익명 처리돼 질의 행에 안 나오므로
    질의 행을 더하면 실제보다 적거나 0 이 된다 — 차원 없이 따로 합계를 받는다."""
    r = svc.searchanalytics().query(siteUrl=site, body={
        "startDate": start, "endDate": end, "type": "web"}).execute().get("rows", [])
    return (r[0]["clicks"], r[0]["impressions"]) if r else (0, 0)


def _sites(svc):
    """계정에 등록된 속성 목록. 읽기 권한이 없는 것은 건너뛴다."""
    got = svc.sites().list().execute().get("siteEntry", [])
    return [x["siteUrl"] for x in got
            if x.get("permissionLevel") not in ("siteUnverifiedUser",)]


def collect(sites=None, days=DAYS):
    from googleapiclient.discovery import build
    end = datetime.date.today()
    start = end - datetime.timedelta(days=days)

    # 계정(토큰)마다 속성 목록이 다르다. 같은 속성을 두 계정이 함께 가진 경우 먼저 나온
    # 계정으로만 조회해 중복 집계를 막는다.
    targets, seen = [], set()
    for tp in _token_paths():
        try:
            svc = build("searchconsole", "v1", credentials=_creds(tp), cache_discovery=False)
            found = sites or _sites(svc)
        except Exception as e:
            log(f"  {os.path.basename(tp)}: 인증·속성 조회 실패({type(e).__name__}) — 건너뜀")
            continue
        for site in found:
            if site not in seen:
                seen.add(site)
                targets.append((svc, site))
        log(f"  {os.path.basename(tp)}: 속성 {len(found)}곳")
    sites = [site for _, site in targets]

    items, pages, per_site = [], [], []
    for svc, site in targets:
        try:
            q = _query(svc, site, str(start), str(end), "query", TOP_N)
            p = _query(svc, site, str(start), str(end), "page", 10)
            tc, ti = _total(svc, site, str(start), str(end))
        except Exception as e:
            log(f"  {site}: 조회 실패({type(e).__name__}) — 건너뜀")
            continue
        items += [{"site": site, "query": r["keys"][0], "clicks": r["clicks"],
                   "impressions": r["impressions"], "ctr": round(r["ctr"] * 100, 1),
                   "position": round(r["position"], 1)} for r in q]
        pages += [{"site": site, "page": r["keys"][0], "clicks": r["clicks"],
                   "impressions": r["impressions"]} for r in p]
        per_site.append({"site": site, "queries": len(q),
                         "clicks": tc, "impressions": ti})
        log(f"  {site}: 질의 {len(q)}건, 클릭 {tc:.0f}, 노출 {ti:.0f}")

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
