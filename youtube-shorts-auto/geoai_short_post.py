"""완성된 세로 숏츠 mp4 한 편을 개인 GeoAI 유튜브(@geoai-safety)에 올리고, 운영자 안내 댓글을 단다
— 클로드 자동 작업(GeoAI_NA/claude-jobs)이 쓰는 공용 도구. 회차마다 업로드 스크립트를 새로 쓰지 않는다.

토큰은 token_youtube_geoai.json(암호화 저장소)만 쓴다 — 학과 채널 token.json 을 쓰지 않는다.
업로드·댓글은 profile:youtube-personal 잠금(shared/axlock.py)을 잡은 뒤에만 한다(크롬은 열지 않음).
AX_DRY=1 이면 --go 를 --dry 로 바꾼다: 점검(길이·화면비·중복·채널)만 하고 올리지 않는다.

    ./.venv/bin/python geoai_short_post.py upload --video short.mp4 --title "… #Shorts" \
        --description-file 설명.txt --tags "a,b" [--publish-at 2026-10-19T08:00:00+09:00] --dry|--go --job <작업>
    ./.venv/bin/python geoai_short_post.py comment --video-id ID --text "자세한 답안: https://…" --dry|--go --job <작업>
    ./.venv/bin/python geoai_short_post.py check --video-id ID       # 읽기만: 공개 상태·예약 시각·채널·길이·운영자 댓글

결과는 마지막 줄에 JSON 한 줄. status:
  upload  → uploaded | scheduled | dry | duplicate | error
  comment → commented | dry | duplicate | error
  check   → ok | error
duplicate 면 같은 제목 영상(또는 이 채널의 기존 댓글)이 이미 있다는 뜻 — 다시 올리지 말고 그 video_id/comment_id 를 쓴다.
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

os.environ.setdefault("SMUDS_EDITION", "geoai")
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.dirname(BASE))

TOKEN_PATH = os.path.join(BASE, "token_youtube_geoai.json")
CHANNEL_ID = "UCbHDlxMFIackeJRwW2iTYew"     # @geoai-safety — 다른 채널 토큰이면 멈춘다
MAX_SECONDS = 20.0                          # 2026-10-17 사용자 지정: 숏츠는 20.0초 이하


def out(status, **kw):
    print(json.dumps({"status": status, **kw}, ensure_ascii=False))
    return 0 if status in ("uploaded", "scheduled", "commented", "dry", "ok", "duplicate") else 1


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height:format=duration",
                        "-of", "json", path], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe 실패: {r.stderr.strip()[:200]}")
    j = json.loads(r.stdout)
    st = (j.get("streams") or [{}])[0]
    return float(j["format"]["duration"]), st.get("width"), st.get("height")


def api():
    """(youtube, 오류 문구). 토큰이 없거나 다른 채널이면 youtube 는 None."""
    from shared import token_store
    if not token_store.exists(TOKEN_PATH):
        return None, "token_youtube_geoai.json 이 없습니다 — 사람이 youtube-shorts-auto/geoai_youtube_auth.py 로 1회 인증"
    from googleapiclient.discovery import build
    from youtube_upload import _creds
    try:
        yt = build("youtube", "v3", credentials=_creds(TOKEN_PATH), cache_discovery=False)
        ch = yt.channels().list(part="id", mine=True).execute().get("items", [])
    except Exception as e:  # noqa: BLE001
        return None, f"유튜브 인증 실패({type(e).__name__}: {str(e)[:150]}) — geoai_youtube_auth.py 로 재인증 필요"
    if not ch or ch[0]["id"] != CHANNEL_ID:
        return None, f"토큰 채널이 @geoai-safety({CHANNEL_ID})가 아닙니다: {ch[0]['id'] if ch else '채널 없음'}"
    return yt, ""


def find_by_title(yt, title, scan=150):
    """이 채널 업로드 목록(최근 scan 개)에서 같은 제목 영상 id."""
    pl = "UU" + CHANNEL_ID[2:]
    token, seen = None, 0
    while seen < scan:
        r = yt.playlistItems().list(part="snippet", playlistId=pl, maxResults=50,
                                    pageToken=token).execute()
        for it in r.get("items", []):
            sn = it["snippet"]
            if sn.get("title", "").strip() == title.strip():
                return sn["resourceId"]["videoId"]
        seen += len(r.get("items", []))
        token = r.get("nextPageToken")
        if not token:
            break
    return ""


def own_comments(yt, video_id):
    """이 채널(운영자)이 단 최상위 댓글 [(id, 본문)]."""
    found = []
    try:
        r = yt.commentThreads().list(part="snippet", videoId=video_id, maxResults=100,
                                     textFormat="plainText").execute()
    except Exception as e:  # noqa: BLE001  댓글 사용 중지·아직 처리 중 등
        raise RuntimeError(f"댓글 목록을 읽지 못했습니다: {type(e).__name__}: {str(e)[:150]}")
    for t in r.get("items", []):
        c = t["snippet"]["topLevelComment"]["snippet"]
        if (c.get("authorChannelId") or {}).get("value") == CHANNEL_ID:
            found.append((t["id"], c.get("textOriginal") or c.get("textDisplay", "")))
    return found


def video_info(yt, video_id):
    r = yt.videos().list(part="snippet,status,contentDetails", id=video_id).execute().get("items", [])
    if not r:
        return None
    v = r[0]
    return {"video_id": video_id, "channel_ok": v["snippet"]["channelId"] == CHANNEL_ID,
            "title": v["snippet"]["title"], "privacy": v["status"]["privacyStatus"],
            "publish_at": v["status"].get("publishAt", ""),
            "upload_status": v["status"].get("uploadStatus", ""),
            "duration": v["contentDetails"].get("duration", ""),
            "url": f"https://www.youtube.com/shorts/{video_id}"}


def locked(job, what, fn):
    from shared.axlock import Timeout, hold, stopped
    if stopped():
        return out("error", message="비상 정지 중이라 진행하지 않았습니다(ax-console/data/STOP.json)")
    try:
        with hold(["profile:youtube-personal"], job=f"{job}:{what}", wait=2400):
            return fn()
    except Timeout:
        return out("error", message="40분 기다려도 profile:youtube-personal 잠금이 비지 않았습니다")


def cmd_upload(a):
    desc = a.description or ""
    if a.description_file:
        desc = open(a.description_file, encoding="utf-8").read().strip()
    if not os.path.exists(a.video):
        return out("error", message=f"영상 파일이 없습니다: {a.video}")
    try:
        sec, w, h = probe(a.video)
    except Exception as e:  # noqa: BLE001
        return out("error", message=str(e))
    problems = []
    if sec > a.max_seconds:
        problems.append(f"길이 {sec:.2f}초 > {a.max_seconds}초 — 대본·장면을 줄여 다시 만들 것(배속·자르기 금지)")
    if not (w and h and h > w):
        problems.append(f"세로 영상이 아닙니다({w}x{h})")
    if len(a.title) > 100:
        problems.append(f"제목 {len(a.title)}자 > 100자")
    if len(desc) > 4900:
        problems.append(f"설명 {len(desc)}자 > 4900자")
    for name, val in (("제목", a.title), ("설명", desc)):
        if any(c in val for c in "<>"):
            problems.append(f"{name}에 유튜브가 거부하는 < > 문자가 있습니다")
    publish_at = ""
    if a.publish_at:
        try:
            t = datetime.fromisoformat(a.publish_at)
        except ValueError:
            return out("error", message=f"--publish-at 형식 오류: {a.publish_at} (예: 2026-10-19T08:00:00+09:00)")
        if t.tzinfo is None:
            problems.append("--publish-at 에 시간대(+09:00)를 넣을 것")
        elif t <= datetime.now(timezone.utc):
            problems.append(f"예약 시각 {a.publish_at} 이 이미 지났습니다 — 과거 예약은 하지 않는다")
        else:
            publish_at = t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    facts = {"video": a.video, "seconds": round(sec, 2), "size": f"{w}x{h}", "title": a.title}
    if problems:
        return out("error", message=" / ".join(problems), **facts)

    yt, err = api()
    if yt is None:
        if a.dry:   # 시험 실행에서는 토큰 없이도 파일 점검 결과를 돌려준다
            return out("dry", message=f"파일 점검 통과, 채널 점검 못 함: {err}", **facts)
        return out("error", message=err, **facts)
    dup = "" if a.allow_duplicate else find_by_title(yt, a.title)
    if dup:
        return out("duplicate", video_id=dup, url=f"https://www.youtube.com/shorts/{dup}",
                   message="같은 제목 영상이 이미 채널에 있어 올리지 않았습니다", **facts)
    status = {"privacyStatus": "private" if publish_at else a.privacy, "selfDeclaredMadeForKids": False}
    if publish_at:
        status["publishAt"] = publish_at
    if a.synthetic:
        status["containsSyntheticMedia"] = True
    body = {"snippet": {"title": a.title, "description": desc,
                        "tags": [t.strip() for t in a.tags.split(",") if t.strip()][:30],
                        "categoryId": a.category, "defaultLanguage": "ko", "defaultAudioLanguage": "ko"},
            "status": status}
    if a.dry:
        return out("dry", message="점검 통과(길이·화면비·채널·중복) — 실제라면 이 내용으로 올렸을 것",
                   privacy=status["privacyStatus"], publish_at=publish_at, **facts)

    def go():
        from googleapiclient.http import MediaFileUpload
        req = yt.videos().insert(part="snippet,status", body=body,
                                 media_body=MediaFileUpload(a.video, chunksize=8 * 1024 * 1024,
                                                            resumable=True, mimetype="video/mp4"))
        resp = None
        while resp is None:
            prog, resp = req.next_chunk()
            if prog:
                log(f"  업로드 {int(prog.progress() * 100)}%")
        vid = resp.get("id")
        if not vid:
            return out("error", message="업로드 응답에 영상 id 가 없습니다 — 채널 스튜디오에서 확인 필요", **facts)
        if a.thumbnail:
            try:
                yt.thumbnails().set(videoId=vid, media_body=a.thumbnail).execute()
            except Exception as e:  # noqa: BLE001
                log(f"  썸네일 실패(업로드는 정상): {type(e).__name__}: {str(e)[:120]}")
        info = video_info(yt, vid) or {"video_id": vid}
        if not info.get("channel_ok", True):
            return out("error", message="올라간 영상의 채널이 @geoai-safety 가 아닙니다 — 즉시 확인", **info)
        return out("scheduled" if publish_at else "uploaded", **{**facts, **info})
    return locked(a.job, "youtube_upload", go)


def cmd_comment(a):
    yt, err = api()
    if yt is None:
        return out("dry" if a.dry else "error", message=err, text=a.text)
    info = video_info(yt, a.video_id)
    if not info or not info["channel_ok"]:
        return out("error", message="@geoai-safety 채널의 영상이 아닙니다(또는 없음)", video_id=a.video_id)
    if info["privacy"] != "public":
        return out("error", message=f"아직 공개 전입니다({info['privacy']}) — 공개 확인 실행에서 다시",
                   video_id=a.video_id, publish_at=info["publish_at"])
    try:
        mine = own_comments(yt, a.video_id)
    except RuntimeError as e:
        return out("error", message=str(e), video_id=a.video_id)
    if mine:
        cid, txt = mine[0]
        return out("duplicate", video_id=a.video_id, comment_id=cid, comment_text=txt,
                   message="운영자 댓글이 이미 있어 새로 달지 않았습니다")
    if a.dry:
        return out("dry", video_id=a.video_id, comment_text=a.text, message="실제라면 이 댓글을 달았을 것")

    def go():
        body = {"snippet": {"videoId": a.video_id,
                            "topLevelComment": {"snippet": {"textOriginal": a.text}}}}
        try:
            res = yt.commentThreads().insert(part="snippet", body=body).execute()
        except Exception as e:  # noqa: BLE001
            return out("error", video_id=a.video_id, message=f"댓글 등록 실패: {type(e).__name__}: {str(e)[:200]}")
        cid = res.get("id", "")
        c = res["snippet"]["topLevelComment"]["snippet"]
        ok = (c.get("authorChannelId") or {}).get("value") == CHANNEL_ID
        return out("commented" if ok else "error", video_id=a.video_id, comment_id=cid,
                   comment_text=c.get("textOriginal", a.text), comment_verified=ok,
                   message="" if ok else "댓글 작성자가 운영자 채널이 아닙니다")
    return locked(a.job, "youtube_comment", go)


def cmd_check(a):
    yt, err = api()
    if yt is None:
        return out("error", message=err)
    info = video_info(yt, a.video_id)
    if not info:
        return out("error", message="영상을 찾지 못했습니다", video_id=a.video_id)
    try:
        info["owner_comments"] = [{"comment_id": i, "text": t} for i, t in own_comments(yt, a.video_id)]
    except RuntimeError as e:
        info["owner_comments_error"] = str(e)
    return out("ok", **info)


def main():
    ap = argparse.ArgumentParser(description="개인 GeoAI 유튜브(@geoai-safety) 숏츠 업로드·운영자 댓글")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def mode(p):
        g = p.add_mutually_exclusive_group(required=True)
        g.add_argument("--dry", action="store_true", help="점검만(올리지 않음)")
        g.add_argument("--go", action="store_true", help="실제로 올림")
        p.add_argument("--job", default="claude", help="잠금 기록에 남길 작업 이름")

    u = sub.add_parser("upload")
    u.add_argument("--video", required=True)
    u.add_argument("--title", required=True, help="#Shorts 포함 100자 이내")
    u.add_argument("--description", default="")
    u.add_argument("--description-file", default="")
    u.add_argument("--tags", default="")
    u.add_argument("--privacy", default="public", choices=["public", "unlisted", "private"])
    u.add_argument("--publish-at", default="", help="예약 공개 시각(시간대 포함). 주면 비공개로 올리고 그 시각에 공개")
    u.add_argument("--thumbnail", default="")
    u.add_argument("--category", default="27", help="기본 27(교육)")
    u.add_argument("--synthetic", action="store_true", help="유튜브 '변경·합성 콘텐츠' 신고")
    u.add_argument("--max-seconds", type=float, default=MAX_SECONDS)
    u.add_argument("--allow-duplicate", action="store_true")
    mode(u)
    c = sub.add_parser("comment")
    c.add_argument("--video-id", required=True)
    c.add_argument("--text", required=True)
    mode(c)
    k = sub.add_parser("check")
    k.add_argument("--video-id", required=True)
    a = ap.parse_args()

    if os.environ.get("AX_DRY") == "1" and getattr(a, "go", False):
        log("  AX_DRY=1 — 시험 실행이라 --go 를 --dry 로 바꿉니다")
        a.go, a.dry = False, True
    try:
        return {"upload": cmd_upload, "comment": cmd_comment, "check": cmd_check}[a.cmd](a)
    except Exception as e:  # noqa: BLE001
        return out("error", message=f"{type(e).__name__}: {str(e)[:300]}")


if __name__ == "__main__":
    sys.exit(main())
