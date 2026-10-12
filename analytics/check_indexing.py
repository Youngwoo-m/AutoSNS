"""발행한 주소가 구글에 색인됐는지 매일 확인한다. .venv 로 실행할 것.

구글 검색창에 주소를 넣어 보는 방식은 쓰지 않는다 — 검색은 크롤링 신호가 아니라
색인을 앞당기지 못하고, 반복 조회는 약관 위반이라 금방 차단된다. 서치콘솔
URL 검사 API 가 같은 질문에 더 정확히 답한다(색인 여부 + 사유 + 마지막 크롤).

점검 대상은 사이트맵에 올라 있는 주소다. 새 글은 사이트맵에 자동으로 들어가므로
따로 목록을 관리할 필요가 없다.

API 쿼터가 하루 2,000건·분당 600건이라 넉넉하지만, 속성당 상한(--per-site)을 두어
새 글부터 본다. 한 번 '색인됨'으로 확인된 주소는 state 에 적어 두고 다시 묻지 않는다.

사용:  python check_indexing.py            # 속성별 최신 15개
       python check_indexing.py --all      # 상한 없이 전부
       python check_indexing.py --per-site 30
"""
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analytics.common import SNAP_DIR, log, save_part  # noqa: E402

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
BASE = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE, "token_searchconsole.json")
STATE_PATH = os.path.join(SNAP_DIR, "indexing_state.json")
NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
UA = {"User-Agent": "Mozilla/5.0"}
# 색인된 것으로 보는 판정값(한국어 UI 기준). 그 밖은 '아직'으로 센다.
OK_VERDICT = "PASS"


def _creds():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    if not os.path.exists(TOKEN_PATH):
        raise RuntimeError("서치콘솔 토큰 없음 — searchconsole_auth_setup.py 로 인증하세요.")
    c = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not c.valid and c.expired and c.refresh_token:
        c.refresh(Request())
        with open(TOKEN_PATH, "w", encoding="utf-8") as f:
            f.write(c.to_json())
    return c


def _sitemap_urls(site):
    """속성의 사이트맵에서 주소를 모은다(최신순). 사이트맵 인덱스도 한 단계 따라간다."""
    out = []
    for path in (site.rstrip("/") + "/sitemap.xml", site.rstrip("/") + "/sitemap-pages.xml"):
        try:
            with urllib.request.urlopen(urllib.request.Request(path, headers=UA), timeout=20) as r:
                root = ET.fromstring(r.read())
        except Exception:
            continue
        for loc in root.findall(".//s:loc", NS):
            u = (loc.text or "").strip()
            if u.endswith(".xml"):            # 사이트맵 인덱스
                try:
                    with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=20) as r2:
                        for l2 in ET.fromstring(r2.read()).findall(".//s:loc", NS):
                            if l2.text:
                                out.append(l2.text.strip())
                except Exception:
                    pass
            elif u:
                out.append(u)
    seen, uniq = set(), []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def _load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"indexed": []}


def _save_state(st):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def inspect(svc, site, url):
    r = svc.urlInspection().index().inspect(body={
        "inspectionUrl": url, "siteUrl": site, "languageCode": "ko"}).execute()
    idx = r["inspectionResult"]["indexStatusResult"]
    return {"verdict": idx.get("verdict", ""), "coverage": idx.get("coverageState", ""),
            "crawled": (idx.get("lastCrawlTime") or "")[:10]}


def main(argv):
    from googleapiclient.discovery import build
    per_site = 15
    if "--all" in argv:
        per_site = 10_000
    if "--per-site" in argv:
        per_site = int(argv[argv.index("--per-site") + 1])

    svc = build("searchconsole", "v1", credentials=_creds(), cache_discovery=False)
    sites = [x["siteUrl"] for x in svc.sites().list().execute().get("siteEntry", [])]
    state = _load_state()
    known = set(state.get("indexed", []))

    report, pending = [], []
    for site in sites:
        urls = [u for u in _sitemap_urls(site) if u not in known][:per_site]
        done = 0
        for u in urls:
            try:
                got = inspect(svc, site, u)
            except Exception as e:
                log(f"  검사 실패({type(e).__name__}) {u[-50:]}")
                continue
            if got["verdict"] == OK_VERDICT:
                known.add(u)
                done += 1
            else:
                pending.append({"site": site, "url": u, **got})
            time.sleep(0.4)                     # 분당 한도에 여유를 둔다
        report.append({"site": site, "검사": len(urls), "색인확인": done,
                       "미색인": len(urls) - done})
        log(f"  {site}: {len(urls)}건 검사 → 색인 {done} / 미색인 {len(urls) - done}")

    state["indexed"] = sorted(known)
    _save_state(state)

    data = {"per_site": report, "pending": pending[:50],
            "indexed_total": len(known)}
    log(f"색인 점검: 누적 색인 확인 {len(known)}건, 이번에 미색인 {len(pending)}건")
    save_part("indexing", data, allow_empty=True)

    if pending:
        print("\n미색인 주소(최대 20개):")
        for p in pending[:20]:
            print(f"  [{p['coverage']}] {p['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
