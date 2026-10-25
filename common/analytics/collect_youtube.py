"""유튜브 업로드 목록을 수집한다. youtube-shorts-auto/.venv 로 실행할 것.

발행 토큰(youtube-shorts-auto/token.json)의 youtube.readonly 스코프를 그대로 쓴다.
읽기만 하며 업로드·수정은 하지 않는다.

Data API 하루 할당량(10,000)은 발행 쪽이 먼저 쓴다(영상 업로드 1,600 · 자막 400).
바닥나면 읽기도 403 이 되므로, 그때는 할당량을 쓰지 않는 채널 RSS 로 최근 15편을
가져온다. RSS 에는 길이·조회수가 없어 직전 수집분의 값을 물려받고, 새 영상은
제목의 #Shorts 로 유형을 추정한다. 이렇게 받은 결과는 degraded=True 로 표시해
리포트가 "일부 수치가 지난주 값"임을 알리게 한다.
"""
import os
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
from analytics.common import ROOT_DIR, load_part, log, save_part  # noqa: E402

from google.auth.transport.requests import Request      # noqa: E402
from google.oauth2.credentials import Credentials       # noqa: E402
from googleapiclient.discovery import build             # noqa: E402

TOKEN = os.path.join(ROOT_DIR, "channels", "youtube-shorts-auto", "token.json")
# 업로드 재생목록 UUyB8... 의 앞 두 글자만 UC 로 바꾸면 채널 ID 다.
CHANNEL_ID = "UCyB8hWjVghfgzZgj8fwmZrQ"
RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id=" + CHANNEL_ID
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
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


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """리다이렉트를 따라가지 않아야 숏츠 판별이 된다."""

    def redirect_request(self, *a, **k):
        return None


def is_shorts(video_id):
    """/shorts/<id> 가 200 이면 숏츠, 303 으로 /watch 로 넘기면 일반 영상이다.
    Data API 를 쓰지 않으므로 할당량이 들지 않는다."""
    req = urllib.request.Request(f"https://www.youtube.com/shorts/{video_id}",
                                 headers={"User-Agent": "Mozilla/5.0"}, method="HEAD")
    try:
        return urllib.request.build_opener(_NoRedirect).open(req, timeout=15).status == 200
    except urllib.error.HTTPError as e:
        return e.code == 200
    except Exception:
        return None                      # 판단 불가 — 제목으로 추정한다


def collect_via_rss():
    """할당량 없이 최근 15편을 읽는다. 길이·조회수는 직전 수집분에서 물려받는다."""
    prev = load_part("youtube") or {}
    known = {x["id"]: x for x in prev.get("items", [])}
    with urllib.request.urlopen(RSS_URL, timeout=30) as r:
        root = ET.fromstring(r.read())

    items = dict(known)
    for e in root.findall("a:entry", NS):
        vid = e.findtext("yt:videoId", namespaces=NS)
        title = e.findtext("a:title", namespaces=NS) or ""
        date = (e.findtext("a:published", namespaces=NS) or "")[:10]
        old = known.get(vid)
        if old:
            kind = old["type"]
        else:
            # RSS 에는 길이가 없다. 새 영상만 /shorts/ 로 확인하고, 실패하면 제목으로 추정한다.
            probe = is_shorts(vid)
            kind = ("숏츠" if probe else "영상") if probe is not None \
                else ("숏츠" if "#Shorts" in title else "영상")
        items[vid] = {
            "id": vid, "title": title, "date": date,
            "type": kind,
            "seconds": old["seconds"] if old else 0,
            "privacy": old["privacy"] if old else "public",
            "views": old["views"] if old else 0,
            "likes": old["likes"] if old else 0,
            "url": f"https://www.youtube.com/watch?v={vid}",
        }
    return {
        "channel": {**prev.get("channel", {}), "degraded": True},
        "degraded": "quota",
        "items": sorted(items.values(), key=lambda x: x["date"], reverse=True),
    }


def collect():
    # 토큰 파일은 읽기만 한다. 갱신 결과를 덮어쓰면 이 파일의 SCOPES(force-ssl 없음)로
    # 범위가 좁혀져, 같은 토큰을 쓰는 업로드·썸네일 설정이 403 으로 막힌다(2026-10-14).
    # 토큰은 암호화 저장소에 있다(shared/token_store.py) — 갱신본은 저장하지 않는다.
    from shared import token_store
    creds = token_store.google_creds(TOKEN, SCOPES)
    if not creds.valid:
        creds.refresh(Request())
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
    try:
        data = collect()
        log(f"유튜브 구독자 {data['channel']['subscribers']}명, 영상 {len(data['items'])}편")
    except Exception as e:
        reason = "할당량 초과" if "quota" in str(e).lower() else type(e).__name__
        log(f"유튜브 Data API 실패({reason}) — 할당량을 쓰지 않는 RSS 로 대체한다")
        data = collect_via_rss()
        log(f"RSS 수집: 영상 {len(data['items'])}편 (길이·조회수는 직전 값)")
    save_part("youtube", data)
