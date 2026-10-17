"""이미 올린 영상에 새 썸네일을 입힌다(조회 많은 순).

왜: 2026-10-14 이전 영상은 썸네일을 올리지 않아 유튜브가 표지 프레임(회색 카드)을
골라 썼다. 새로 만든 썸네일을 소급 적용하면 검색·채널 목록에서의 구분이 살아난다.
노출이 없는 옛 영상은 바꿔도 달라지는 게 없으므로 조회 상위부터만 손댄다.

문구는 원본 대본(posts/*.json, USB 백업 아카이브 포함)의 장면 1 자막을 쓴다.
대본을 못 찾으면 유튜브 제목으로 만든다(글자가 길어 품질은 떨어진다).

맞춤 썸네일은 전화 인증된 채널만 가능하다. 403 이 나면 거기서 멈춘다 — 같은 오류로
20편을 두드려봐야 쿼터만 쓴다.

사용:
    python backfill_thumbnails.py --dry            # 만들기만(업로드 안 함)
    python backfill_thumbnails.py --go --top 20
    python backfill_thumbnails.py --go --geoai     # 개인 GeoAI 채널
"""
import argparse
import datetime
import difflib
import glob
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE_DIR)
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, ROOT)

from common import log  # noqa: E402
from make_thumbnail import make_thumbnail  # noqa: E402

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly",
          "https://www.googleapis.com/auth/yt-analytics.readonly",
          "https://www.googleapis.com/auth/youtube.force-ssl"]
TOKENS = {"dept": os.path.join(BASE_DIR, "token.json"),
          "geoai": os.path.join(BASE_DIR, "token_youtube_geoai.json")}
# 대본 보관 위치(현재 + USB 백업 아카이브)
POST_DIRS = [os.path.join(BASE_DIR, "posts"),
             "/Volumes/USB256/USB256_backup/AutoSNS_archive/youtube-shorts-auto",
             "/Volumes/USB256/USB256_backup/AutoSNS_archive_20260917"]
STATE = os.path.join(BASE_DIR, "thumbnail_backfill.json")


def _creds(path):
    from shared import token_store            # 토큰은 암호화 저장소에 있다
    return token_store.load_google(path, SCOPES)


def _payloads():
    out = {}
    for d in POST_DIRS:
        for f in glob.glob(os.path.join(d, "**", "*.json"), recursive=True):
            try:
                data = json.load(open(f, encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, dict) and data.get("title") and data.get("scenes"):
                out.setdefault(data["title"], data)
    return out


def _done():
    if os.path.exists(STATE):
        try:
            return set(json.load(open(STATE, encoding="utf-8")).get("done", []))
        except Exception:
            pass
    return set()


def _mark(vid):
    s = _done()
    s.add(vid)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump({"done": sorted(s)}, f, ensure_ascii=False, indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geoai", action="store_true")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--go", action="store_true", help="실제 업로드(없으면 만들기만)")
    ap.add_argument("--days", type=int, default=365)
    a = ap.parse_args()
    from googleapiclient.discovery import build

    creds = _creds(TOKENS["geoai" if a.geoai else "dept"])
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    ya = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)

    end = datetime.date.today()
    start = end - datetime.timedelta(days=a.days)
    rows = ya.reports().query(ids="channel==MINE", startDate=str(start), endDate=str(end),
                              metrics="views", dimensions="video", sort="-views",
                              maxResults=a.top).execute().get("rows", [])
    ids = [r[0] for r in rows]
    info = {}
    for i in range(0, len(ids), 50):
        for v in yt.videos().list(part="snippet,contentDetails",
                                  id=",".join(ids[i:i + 50])).execute().get("items", []):
            info[v["id"]] = v

    posts = _payloads()
    done = _done()
    log(f"{'GeoAI' if a.geoai else '학과'} 채널 상위 {len(rows)}편 — 대본 보관 {len(posts)}편, "
        f"이미 적용 {len(done)}편{'' if a.go else ' [시험 실행: 업로드 안 함]'}")

    applied = skipped = 0
    for vid, views in rows:
        v = info.get(vid, {})
        title = v.get("snippet", {}).get("title", vid)
        if vid in done:
            log(f"  건너뜀(이미 적용) {views:>5} {title[:34]}")
            skipped += 1
            continue
        base = title.split("] ", 1)[-1]
        m = difflib.get_close_matches(base, list(posts), n=1, cutoff=0.45)
        data = dict(posts[m[0]]) if m else {"title": title}
        data["stamp"] = f"bf_{vid}"
        if a.geoai:
            data.setdefault("family", "GeoAI")
        dur = v.get("contentDetails", {}).get("duration", "")
        shape = "video" if ("H" in dur or "M" in dur and not dur.startswith("PT1M")) else "shorts"
        path = make_thumbnail(data, shape=shape)
        src = "대본" if m else "제목만"
        if not a.go:
            log(f"  만듦({src}/{shape}) {views:>5} {title[:30]} → {os.path.basename(path)}")
            applied += 1
            continue
        try:
            yt.thumbnails().set(videoId=vid, media_body=path).execute()
        except Exception as e:  # noqa: BLE001
            msg = str(e)[:160]
            log(f"  실패 {title[:30]}: {type(e).__name__}: {msg}")
            if "403" in msg or "forbidden" in msg.lower():
                log("  → 맞춤 썸네일 권한이 없습니다(채널 전화 인증 필요). 여기서 멈춥니다.")
            else:
                log("  → 원인을 확인할 때까지 멈춥니다.")
            break
        _mark(vid)
        applied += 1
        log(f"  적용({src}/{shape}) 조회 {views:>5} · {title[:34]}")
    log(f"끝: 적용 {applied}편, 건너뜀 {skipped}편")


if __name__ == "__main__":
    main()
