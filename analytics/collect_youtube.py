"""유튜브 업로드 목록을 수집한다. youtube-shorts-auto/.venv 로 실행할 것.

발행 토큰(youtube-shorts-auto/token.json)의 youtube.readonly 스코프를 그대로 쓴다.
읽기만 하며 업로드·수정은 하지 않는다.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analytics.common import ROOT_DIR, log, save_part  # noqa: E402

from google.auth.transport.requests import Request      # noqa: E402
from google.oauth2.credentials import Credentials       # noqa: E402
from googleapiclient.discovery import build             # noqa: E402

TOKEN = os.path.join(ROOT_DIR, "youtube-shorts-auto", "token.json")
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def _secs(iso):
    """PT1M30S 형태의 길이를 초로. 숏츠(60초 이하) 판정에 쓴다."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mi, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + s


def collect():
    creds = Credentials.from_authorized_user_file(TOKEN, SCOPES)
    if not creds.valid:
        creds.refresh(Request())
        with open(TOKEN, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    yt = build("youtube", "v3", credentials=creds)

    ch = yt.channels().list(part="snippet,contentDetails,statistics", mine=True).execute()
    info = ch["items"][0]
    uploads = info["contentDetails"]["relatedPlaylists"]["uploads"]

    vids, token = [], None
    while True:
        r = yt.playlistItems().list(part="contentDetails", playlistId=uploads,
                                    maxResults=50, pageToken=token).execute()
        vids += [x["contentDetails"]["videoId"] for x in r["items"]]
        token = r.get("nextPageToken")
        if not token:
            break

    items = []
    for i in range(0, len(vids), 50):
        d = yt.videos().list(part="snippet,contentDetails,status,statistics",
                             id=",".join(vids[i:i + 50])).execute()
        for x in d["items"]:
            secs = _secs(x["contentDetails"].get("duration"))
            items.append({
                "id": x["id"],
                "title": x["snippet"]["title"],
                "date": x["snippet"]["publishedAt"][:10],
                "type": "숏츠" if secs <= 60 else "영상",
                "seconds": secs,
                "privacy": x["status"]["privacyStatus"],
                "views": int(x["statistics"].get("viewCount", 0) or 0),
                "likes": int(x["statistics"].get("likeCount", 0) or 0),
                "url": f"https://www.youtube.com/watch?v={x['id']}",
            })

    stats = info["statistics"]
    return {
        "channel": {
            "title": info["snippet"]["title"],
            "handle": info["snippet"].get("customUrl", ""),
            "subscribers": int(stats.get("subscriberCount", 0) or 0),
            "total_views": int(stats.get("viewCount", 0) or 0),
        },
        "items": sorted(items, key=lambda x: x["date"], reverse=True),
    }


if __name__ == "__main__":
    data = collect()
    log(f"유튜브 구독자 {data['channel']['subscribers']}명, 영상 {len(data['items'])}편")
    save_part("youtube", data)
