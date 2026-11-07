"""완성된 세로 숏츠 mp4 한 편을 학과 유튜브(@smds2023, semyungds)에 올리고 운영자 댓글을 단다
— 클로드 자동 작업 dept-crosspost 가 쓰는 공용 도구. geoai_short_post.py(개인 채널)와 같은 사용법·같은 결과 JSON.

토큰은 token.json(암호화 저장소 YOUTUBE_TOKEN_DEPT)만 쓴다 — 개인 GeoAI 토큰을 쓰지 않는다. 다른 채널 토큰이면 멈춘다.
업로드·댓글은 profile:youtube-dept 잠금(shared/axlock.py)을 잡은 뒤에만 한다(크롬은 열지 않음).
규칙은 개인 채널과 같다: 20.0초 이하, 세로 영상만, 지난 시각 예약 금지, 같은 제목 영상이 있으면 duplicate.
AX_DRY=1 이면 --go 를 --dry 로 바꾼다. 틱톡 대기열에는 넣지 않는다(개인 숏츠 업로드 때 이미 들어간다).

    ./.venv/bin/python dept_short_post.py upload --video short.mp4 --title "… #Shorts" \
        --description-file 설명.txt --tags "a,b" [--publish-at 2026-11-06T21:30:00+09:00] --dry|--go --job dept-crosspost
    ./.venv/bin/python dept_short_post.py comment --video-id ID --text "원문: https://…" --dry|--go --job dept-crosspost
    ./.venv/bin/python dept_short_post.py check --video-id ID

결과는 마지막 줄에 JSON 한 줄. status:
  upload  → uploaded | scheduled | dry | duplicate | error
  comment → commented | dry | duplicate | error
  check   → ok | error
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.dirname(os.path.dirname(BASE)))

TOKEN_PATH = os.path.join(BASE, "token.json")   # token_store.NAMES → YOUTUBE_TOKEN_DEPT
CHANNEL_ID = "UCyB8hWjVghfgzZgj8fwmZrQ"          # 학과 채널(published_history.YOUTUBE['youtube-dept'])
CHANNEL_NAME = "학과 유튜브"
LOCK = "profile:youtube-dept"
MAX_SECONDS = 20.0


def out(status, **kw):
    print(json.dumps({"status": status, **kw}, ensure_ascii=False))
    return 0 if status in ("uploaded", "scheduled", "commented", "dry", "ok", "duplicate") else 1


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def managed_state(connection="dept.youtube"):
    """관리 OAuth(dept-oauth-service 브랜치) 준비 상태 — 읽기만. 없으면 not_installed.
    발행 범위가 열리기(publication_verified) 전까지 실제 업로드는 옛 토큰으로 한다."""
    try:
        from common.publishers.managed_assembly import managed_readiness
        from common.operations.bootstrap_config import default_bootstrap_config
        from common.operations.managed_connections import ManagedConnectionStore
        snap = ManagedConnectionStore(default_bootstrap_config().workspace_root).snapshot()
        return managed_readiness(snap, (connection,))[connection]
    except ImportError:
        return {"read": "not_installed", "publication": "not_installed"}
    except Exception as e:  # noqa: BLE001
        return {"read": f"unavailable:{type(e).__name__}", "publication": "unknown"}


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
    try:
        from shared import token_store
        if not token_store.exists(TOKEN_PATH):
            return None, "학과 유튜브 토큰(YOUTUBE_TOKEN_DEPT)이 없습니다 — youtube_login_setup.py 로 1회 인증"
        from googleapiclient.discovery import build
        from youtube_upload import _creds
        yt = build("youtube", "v3", credentials=_creds(TOKEN_PATH), cache_discovery=False)
        ch = yt.channels().list(part="id", mine=True).execute().get("items", [])
    except Exception as e:  # noqa: BLE001
        return None, f"학과 유튜브 인증 실패({type(e).__name__}: {str(e)[:150]})"
    if not ch or ch[0]["id"] != CHANNEL_ID:
        return None, f"토큰 채널이 {CHANNEL_NAME}({CHANNEL_ID})가 아닙니다: {ch[0]['id'] if ch else '채널 없음'}"
    return yt, ""


def find_by_title(yt, title, scan=150):
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
    try:
        r = yt.commentThreads().list(part="snippet", videoId=video_id, maxResults=100,
                                     textFormat="plainText").execute()
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"댓글 목록을 읽지 못했습니다: {type(e).__name__}: {str(e)[:150]}")
    found = []
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
        with hold([LOCK], job=f"{job}:{what}", wait=2400):
            return fn()
    except Timeout:
        return out("error", message=f"40분 기다려도 {LOCK} 잠금이 비지 않았습니다")


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
        problems.append(f"길이 {sec:.2f}초 > {a.max_seconds}초 — 배속·자르기 금지, 올리지 않는다")
    if not (w and h and h > w):
        problems.append(f"세로 영상이 아닙니다({w}x{h})")
    if len(a.title) > 100:
        problems.append(f"제목 {len(a.title)}자 > 100자")
    if len(desc) > 4900:
        problems.append(f"설명 {len(desc)}자 > 4900자")
    for name, val in (("제목", a.title), ("설명", desc)):
        if any(c in val for c in "<>"):
            problems.append(f"{name}에 유튜브가 거부하는 < > 문자가 있습니다")
    publish_at, when = "", None
    if a.publish_at:
        try:
            when = datetime.fromisoformat(a.publish_at)
        except ValueError:
            return out("error", message=f"--publish-at 형식 오류: {a.publish_at}")
        if when.tzinfo is None:
            problems.append("--publish-at 에 시간대(+09:00)를 넣을 것")
        elif when <= datetime.now(timezone.utc):
            problems.append(f"예약 시각 {a.publish_at} 이 이미 지났습니다 — 과거 예약은 하지 않는다")
        else:
            publish_at = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    facts = {"video": a.video, "seconds": round(sec, 2), "size": f"{w}x{h}", "title": a.title}
    if problems:
        return out("error", message=" / ".join(problems), **facts)

    yt, err = api()
    if yt is None:
        if a.dry:
            return out("dry", message=f"파일 점검 통과, 채널 점검 못 함: {err}", managed=managed_state(), **facts)
        return out("error", message=err, **facts)
    dup = "" if a.allow_duplicate else find_by_title(yt, a.title)
    if dup:
        return out("duplicate", video_id=dup, url=f"https://www.youtube.com/shorts/{dup}",
                   message="같은 제목 영상이 이미 학과 채널에 있어 올리지 않았습니다", **facts)
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
                   privacy=status["privacyStatus"], publish_at=publish_at, managed=managed_state(), **facts)

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
            return out("error", message="업로드 응답에 영상 id 가 없습니다 — 스튜디오에서 확인 필요", **facts)
        if a.thumbnail:
            try:
                yt.thumbnails().set(videoId=vid, media_body=a.thumbnail).execute()
            except Exception as e:  # noqa: BLE001
                log(f"  썸네일 실패(업로드는 정상): {type(e).__name__}: {str(e)[:120]}")
        info = video_info(yt, vid) or {"video_id": vid}
        if not info.get("channel_ok", True):
            return out("error", message=f"올라간 영상의 채널이 {CHANNEL_NAME}가 아닙니다 — 즉시 확인", **info)
        return out("scheduled" if publish_at else "uploaded", **{**facts, **info})
    return locked(a.job, "youtube_upload", go)


def cmd_comment(a):
    yt, err = api()
    if yt is None:
        return out("dry" if a.dry else "error", message=err, text=a.text)
    info = video_info(yt, a.video_id)
    if not info or not info["channel_ok"]:
        return out("error", message=f"{CHANNEL_NAME} 영상이 아닙니다(또는 없음)", video_id=a.video_id)
    if info["privacy"] != "public":
        return out("error", message=f"아직 공개 전입니다({info['privacy']})", video_id=a.video_id,
                   publish_at=info["publish_at"])
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
        c = res["snippet"]["topLevelComment"]["snippet"]
        ok = (c.get("authorChannelId") or {}).get("value") == CHANNEL_ID
        return out("commented" if ok else "error", video_id=a.video_id, comment_id=res.get("id", ""),
                   comment_text=c.get("textOriginal", a.text), comment_verified=ok,
                   message="" if ok else "댓글 작성자가 학과 채널이 아닙니다")
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
    ap = argparse.ArgumentParser(description="학과 유튜브 숏츠 업로드·운영자 댓글(교차 발행)")
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
    u.add_argument("--publish-at", default="")
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
    from shared.owner_fence import require_legacy_cli
    require_legacy_cli(("dept", "youtube", "dept-short-" + a.cmd))
    if a.cmd == "upload" and a.max_seconds > MAX_SECONDS:
        return out("error", message=f"--max-seconds 는 {MAX_SECONDS}초를 넘길 수 없습니다")
    if os.environ.get("AX_DRY") == "1" and getattr(a, "go", False):
        log("  AX_DRY=1 — 시험 실행이라 --go 를 --dry 로 바꿉니다")
        a.go, a.dry = False, True
    try:
        return {"upload": cmd_upload, "comment": cmd_comment, "check": cmd_check}[a.cmd](a)
    except Exception as e:  # noqa: BLE001
        return out("error", message=f"{type(e).__name__}: {str(e)[:300]}")


if __name__ == "__main__":
    sys.exit(main())
