"""내 유튜브 '구독 채널'의 최근 영상 제목에서 재난 관련 검색어를 뽑는다.

목적: 재난안전 채널(세이프K, YTN사이언스 등)이 '지금 다루는' 구체적 사건을
      뉴스 검색어에 더해, 우리 콘텐츠가 커뮤니티 이슈와 맞물리게 한다.

핵심: 구독 피드에는 재난과 무관한 영상(일상·홍보 등)도 많으므로, 반드시
      '재난 키워드가 든 제목'만 골라 '지역+재난' 조합으로만 뽑는다(오염 방지).

유튜브 공식 API(youtube.readonly)만 쓴다. 실패하면 빈 목록을 돌려준다.
"""
import os
import sys
from datetime import datetime, timezone, timedelta

from common import TOKEN_PATH, log

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.keyword_terms import queries_from_titles  # noqa: E402


def _creds():
    # 토큰은 암호화 저장소에 있다(shared/token_store.py). 갱신본은 저장하지 않는다(예전과 같음).
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    from shared import token_store
    return token_store.load_google(TOKEN_PATH, save=False)


def _recent_titles(within_days, max_channels, per_channel):
    from googleapiclient.discovery import build
    yt = build("youtube", "v3", credentials=_creds(), cache_discovery=False)
    subs = yt.subscriptions().list(
        part="snippet", mine=True, maxResults=max_channels).execute()
    cids = [s["snippet"]["resourceId"]["channelId"] for s in subs.get("items", [])]
    if not cids:
        return []
    chs = yt.channels().list(part="contentDetails", id=",".join(cids)).execute()
    cutoff = datetime.now(timezone.utc) - timedelta(days=within_days)
    titles = []
    for ch in chs.get("items", []):
        up = ch["contentDetails"]["relatedPlaylists"]["uploads"]
        try:
            pl = yt.playlistItems().list(
                part="snippet", playlistId=up, maxResults=per_channel).execute()
        except Exception:
            continue
        for it in pl.get("items", []):
            sn = it["snippet"]
            try:
                d = datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))
            except Exception:
                continue
            if d >= cutoff:
                titles.append(sn.get("title", ""))
    return titles


def youtube_sub_keywords(within_days=10, max_channels=25, per_channel=5, limit=5):
    """구독 채널 최근 영상에서 뽑은 재난 검색어 목록. 실패 시 []。"""
    try:
        titles = _recent_titles(within_days, max_channels, per_channel)
    except Exception as e:
        log(f"구독채널 키워드 수집 실패({type(e).__name__}) → 건너뜀")
        return []
    qs = queries_from_titles(titles)
    return qs[:limit]


if __name__ == "__main__":
    for q in youtube_sub_keywords():
        print("  +", q)
