"""뉴스 외 '웹 검색' 소스. 현재는 유튜브 동영상 검색(공식 API)을 제공한다.

fetch_news 가 이 결과를 뉴스 항목과 같은 형태로 받아 소스 풀에 합친다.
(제목/링크/날짜 형태가 뉴스와 동일해서 그대로 병합·정렬·중복제거된다.)

네이버 블로그/웹 검색은 무료 '네이버 검색 API' 키(developers.naver.com)가 필요하고,
인스타그램 팔로잉/검색은 공식 API 로 접근이 불가능하다(별도 안내 참조).
"""
from datetime import datetime, timezone, timedelta

from common import TOKEN_PATH, log


def _creds():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    creds = Credentials.from_authorized_user_file(TOKEN_PATH)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def youtube_search(queries, within_days=7, per_query=5, total=10):
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
