"""이미 올린 영상에 첫 댓글을 달고(또는 문구를 고치고) 상단에 고정한다.

왜: 댓글은 썸네일과 달리 영상 아래에 계속 남고 링크가 클릭된다. 다만 학과 채널은
이전 문구(채널 모음 링크 없음)로 이미 댓글이 달려 있고, GeoAI 채널은 기능이 꺼져
있어 아예 없다. 그래서 '없으면 달고, 있으면 고친다'로 처리한다.

한꺼번에 수십 개를 달면 스팸처럼 보인다. 조회 상위 몇 편까지만 한다(기본 10편).

사용:
    python backfill_comments.py --top 10            # 시험 실행(아무것도 바꾸지 않음)
    python backfill_comments.py --top 10 --go
    python backfill_comments.py --top 10 --go --geoai
    python backfill_comments.py --top 10 --go --no-pin
"""
import argparse
import copy
import datetime
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.dirname(BASE_DIR))

import common  # noqa: E402
from common import log  # noqa: E402
from youtube_upload import comment_text  # noqa: E402

TOKENS = {"dept": os.path.join(BASE_DIR, "token.json"),
          "geoai": os.path.join(BASE_DIR, "token_youtube_geoai.json")}
PROFILES = {"dept": "chrome-profile-youtube-dept", "geoai": "chrome-profile-youtube"}
STATE = os.path.join(BASE_DIR, "comment_backfill.json")
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly",
          "https://www.googleapis.com/auth/yt-analytics.readonly",
          "https://www.googleapis.com/auth/youtube.force-ssl"]


def _creds(path):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    c = Credentials.from_authorized_user_file(path, SCOPES)
    if not c.valid and c.expired and c.refresh_token:
        c.refresh(Request())
    return c


def _state():
    if os.path.exists(STATE):
        try:
            return json.load(open(STATE, encoding="utf-8"))
        except Exception:
            pass
    return {}


def _mark(vid, what):
    s = _state()
    s[vid] = what
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)


def _mine(yt, video_id, channel_id):
    """이 채널이 단 최상위 댓글(있으면)."""
    try:
        r = yt.commentThreads().list(part="snippet", videoId=video_id,
                                     maxResults=50, order="time").execute()
    except Exception as e:  # 댓글이 꺼진 영상 등
        log(f"  댓글 조회 실패: {type(e).__name__}: {str(e)[:80]}")
        return None
    for it in r.get("items", []):
        sn = it["snippet"]["topLevelComment"]["snippet"]
        if (sn.get("authorChannelId") or {}).get("value") == channel_id:
            return {"id": it["snippet"]["topLevelComment"]["id"],
                    "text": sn.get("textOriginal", "")}
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geoai", action="store_true")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--no-pin", action="store_true")
    a = ap.parse_args()
    from googleapiclient.discovery import build

    key = "geoai" if a.geoai else "dept"
    creds = _creds(TOKENS[key])
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    ya = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    ch = yt.channels().list(part="snippet", mine=True).execute()["items"][0]
    channel_id, channel_name = ch["id"], ch["snippet"]["title"]

    cfg = common.load_config()
    if a.geoai:
        cfg = common._deep_merge(copy.deepcopy(cfg), cfg["editions"]["geoai"])
    want = comment_text({}, cfg)

    end = datetime.date.today()
    start = end - datetime.timedelta(days=a.days)
    rows = ya.reports().query(ids="channel==MINE", startDate=str(start), endDate=str(end),
                              metrics="views", dimensions="video", sort="-views",
                              maxResults=a.top).execute().get("rows", [])
    done = _state()
    log(f"{channel_name}: 상위 {len(rows)}편{'' if a.go else ' [시험 실행]'}")
    log(f"문구: {want.splitlines()[0][:50]}…")

    for vid, views in rows:
        if done.get(vid):
            log(f"  건너뜀(처리함: {done[vid]}) {vid} 조회 {views}")
            continue
        mine = _mine(yt, vid, channel_id)
        act = "그대로" if (mine and mine["text"].strip() == want.strip()) else (
            "문구 교체" if mine else "새로 달기")
        log(f"  {vid} 조회 {views:>5} → {act}")
        if act == "그대로" or not a.go:
            continue
        try:
            if mine:
                yt.comments().update(part="snippet", body={
                    "id": mine["id"], "snippet": {"textOriginal": want}}).execute()
            else:
                yt.commentThreads().insert(part="snippet", body={"snippet": {
                    "videoId": vid,
                    "topLevelComment": {"snippet": {"textOriginal": want}}}}).execute()
        except Exception as e:  # noqa: BLE001
            log(f"    실패: {type(e).__name__}: {str(e)[:120]} — 여기서 멈춥니다")
            break
        if not a.no_pin:
            try:
                from pin_comment import pin
                r = pin(vid, go=True, profile_dir=os.path.join(BASE_DIR, PROFILES[key]))
                log(f"    고정: {r.get('status')}")
            except Exception as e:  # noqa: BLE001
                log(f"    고정 실패(댓글은 남음): {type(e).__name__}")
        _mark(vid, act)


if __name__ == "__main__":
    main()
