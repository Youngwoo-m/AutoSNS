"""이미 발행된 영상에 대본 자막을 소급해서 올린다.

posts/*.json 에 남아 있는 대본을 채널 영상과 제목으로 짝지어 자막을 만든다.
자동자막(ASR)만 있는 영상이 대상이고, 직접 올린 자막이 있으면 건너뛴다(멱등).

사용: python backfill_captions.py [--go] [--limit N]
"""
import glob
import json
import os
import re
import sys

from googleapiclient.discovery import build

from common import BASE_DIR, log
from make_captions import build_srt, upload_caption
from youtube_upload import _creds


def _norm(t):
    """제목 비교용 — 접두사·기호·공백을 걷어내고 앞부분만 본다."""
    t = re.sub(r"\[[^\]]*\]", "", t or "")          # [SMU 재난안전뉴스] 등
    t = re.sub(r"#\S+", "", t)
    t = re.sub(r"[^0-9A-Za-z가-힣]", "", t)
    return t[:28]


def _channel_videos(yt):
    ch = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0]
    up = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, tok = [], None
    while True:
        r = yt.playlistItems().list(part="snippet", playlistId=up,
                                    maxResults=50, pageToken=tok).execute()
        ids += [i["snippet"]["resourceId"]["videoId"] for i in r["items"]]
        tok = r.get("nextPageToken")
        if not tok:
            break
    out = {}
    for b in [ids[i:i + 50] for i in range(0, len(ids), 50)]:
        for v in yt.videos().list(part="snippet", id=",".join(b)).execute()["items"]:
            out[v["id"]] = v["snippet"]["title"]
    return out


def _has_manual_caption(yt, vid):
    try:
        items = yt.captions().list(part="snippet", videoId=vid).execute().get("items", [])
        return any(c["snippet"].get("trackKind") != "asr" for c in items)
    except Exception:
        return False


def run(go=False, limit=None):
    yt = build("youtube", "v3", credentials=_creds(), cache_discovery=False)
    videos = _channel_videos(yt)
    by_title = {_norm(t): vid for vid, t in videos.items()}
    done = skipped = nomatch = failed = 0
    for f in sorted(glob.glob(os.path.join(BASE_DIR, "posts", "*.json"))):
        try:
            data = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        # posts/ 에는 대본이 아닌 JSON(목록 형태 등)도 섞인다 — 10/12 그런 파일 하나에 걸려 작업 전체가 멈췄다
        if not isinstance(data, dict) or not data.get("scenes"):
            continue
        vid = data.get("video_id")
        if not vid:
            vid = by_title.get(_norm(data.get("title", "")))
        if not vid:
            nomatch += 1
            continue
        if _has_manual_caption(yt, vid):
            skipped += 1
            continue
        srt = build_srt(data)
        if not srt.strip():
            continue
        if not go:
            log(f"  [DRY] {vid} ← {os.path.basename(f)} ({videos.get(vid,'')[:34]})")
            done += 1
        else:
            r = upload_caption(vid, srt)
            if r.get("status") == "uploaded":
                done += 1
            else:
                failed += 1
        if limit and done >= limit:
            break
    log(f"{'적용' if go else 'DRY-RUN'} 완료 — 자막 {done}편, 이미있음 {skipped}편, "
        f"영상 못찾음 {nomatch}편, 실패 {failed}편")
    return {"done": done, "skipped": skipped, "nomatch": nomatch, "failed": failed}


if __name__ == "__main__":
    lim = None
    if "--limit" in sys.argv:
        lim = int(sys.argv[sys.argv.index("--limit") + 1])
    print(json.dumps(run(go="--go" in sys.argv, limit=lim), ensure_ascii=False))
