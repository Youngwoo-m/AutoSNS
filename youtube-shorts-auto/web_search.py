"""뉴스 외 '웹 검색' 소스. 현재는 유튜브 동영상 검색(공식 API)을 제공한다.

fetch_news 가 이 결과를 뉴스 항목과 같은 형태로 받아 소스 풀에 합친다.
(제목/링크/날짜 형태가 뉴스와 동일해서 그대로 병합·정렬·중복제거된다.)

네이버 블로그/웹 검색은 무료 '네이버 검색 API' 키(developers.naver.com)가 필요하고,
인스타그램 팔로잉/검색은 공식 API 로 접근이 불가능하다(별도 안내 참조).
"""
import os
import sys
from datetime import datetime, timezone, timedelta

from common import TOKEN_PATH, log


def _creds():
    # 토큰은 암호화 저장소에 있다(shared/token_store.py). 갱신본은 저장하지 않는다(예전과 같음).
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    from shared import token_store
    return token_store.load_google(TOKEN_PATH, save=False)


# 우리 채널 — 검색 결과에 우리 영상이 다시 잡혀 '출처'로 재인용되는 것을 막는다.
# (2026-09-27 확인: AI판 수집 8건에 우리 [SMU 재난안전뉴스] 영상이 섞여 있었다)
OWN_CHANNELS = {
    "UCyB8hWjVghfgzZgj8fwmZrQ",   # 세명대학교 재난안전학과
    "UCbHDlxMFIackeJRwW2iTYew",   # 재난안전과 GeoAI
}


def youtube_search(queries, within_days=7, per_query=5, total=10, exclude_channels=()):
    """검색어로 최근 유튜브 동영상을 찾아 뉴스와 같은 형태의 항목으로 돌려준다.

    주의: 유튜브 search API 는 호출당 할당량 100유닛을 쓴다(쿼리 5개면 500유닛/회).
          하루 기본 할당 10,000유닛이라 주간 실행에는 충분하다.
    """
    try:
        from googleapiclient.discovery import build
        yt = build("youtube", "v3", credentials=_creds(), cache_discovery=False)
    except Exception as e:
        log(f"유튜브 검색 초기화 실패({type(e).__name__}) → 건너뜀")
        return []
    after = (datetime.now(timezone.utc) - timedelta(days=within_days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    skip = OWN_CHANNELS | set(exclude_channels or ())
    seen, items = set(), []
    for q in queries:
        try:
            r = yt.search().list(
                part="snippet", q=q, type="video", order="date",
                maxResults=per_query, publishedAfter=after,
                regionCode="KR", relevanceLanguage="ko").execute()
        except Exception as e:
            log(f"유튜브 검색 실패(q='{q}': {type(e).__name__})")
            continue
        for it in r.get("items", []):
            vid = (it.get("id") or {}).get("videoId")
            if not vid or vid in seen:
                continue
            seen.add(vid)
            sn = it["snippet"]
            if sn.get("channelId") in skip:
                continue
            try:
                pub = datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))
            except Exception:
                pub = datetime.now(timezone.utc)
            ch = sn.get("channelTitle", "")
            items.append({
                "title": f"{sn.get('title','')} - {ch} (YouTube)",
                "link": f"https://youtu.be/{vid}",
                "source": "YouTube",
                "published": pub,
                "published_str": pub.astimezone().strftime("%Y-%m-%d"),
            })
    items.sort(key=lambda x: x["published"], reverse=True)
    return items[:total]


if __name__ == "__main__":
    from common import load_config
    qs = load_config().get("news", {}).get("queries", ["GeoAI 재난"])
    for it in youtube_search(qs):
        print(f"  [{it['published_str']}] {it['title'][:60]}")
