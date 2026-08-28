"""진로·퀴즈 시리즈 주간 자동 발행기 (launchd 가 매주 화요일 호출).

동작:
  - publish_schedule.json 을 읽어 '아직 미발행 + 예정일 <= 오늘'인 편 중
    가장 이른 1편만 유튜브 + 인스타그램(릴)에 동시 공개 발행한다. → 주 1편 페이싱.
    (진로 2~8편 → 퀴즈 1~10편 순으로 날짜순 자동 진행)
  - 유튜브 업로드 성공 시 published={youtube, instagram, at} 를 기록해 중복 발행을 막는다(멱등).
    ※ 유튜브 성공을 기준으로 published 를 남긴다(유튜브 재업로드로 인한 중복 방지).
      인스타는 부가 채널이라 실패해도 유튜브 발행은 유지되고, 실패 로그·수동 재시도 안내를 남긴다.
  - 예정일이 지난 편이 여러 개여도 한 번에 하나만(주 1편) 올린다.

옵션:
  --now      예정일과 무관하게 '미발행 최우선 편'을 즉시 1편 발행(수동 앞당기기).
  --dry      실제 업로드 없이 무엇을 올릴지만 출력.
  --no-ig    인스타 게시 생략(유튜브만).
"""
import datetime
import json
import os
import subprocess
import sys

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from common import BASE_DIR, log
from youtube_upload import _creds

SCHED_PATH = os.path.join(BASE_DIR, "publish_schedule.json")
CATEGORY_EDU = "27"

# 인스타그램은 별도 프로젝트(insta-cardnews)의 venv·설정·크롬 프로필로 게시한다.
IG_DIR = os.path.join(os.path.dirname(BASE_DIR), "insta-cardnews")
IG_PY = os.path.join(IG_DIR, ".venv", "bin", "python")
IG_TIMEOUT = 600   # 릴 업로드·처리·공유·첫 댓글까지 넉넉히(초)


def _load():
    with open(SCHED_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save(sched):
    with open(SCHED_PATH, "w", encoding="utf-8") as f:
        json.dump(sched, f, ensure_ascii=False, indent=2)


def _pick(sched, ignore_date):
    """발행할 편 1개 선택: 미발행 중 예정일 이른 순. ignore_date 면 날짜 조건 무시."""
    today = datetime.date.today()
    cand = []
    for e in sched:
        if e.get("published"):
            continue
        due = datetime.date.fromisoformat(e["date"])
        if ignore_date or due <= today:
            cand.append(e)
    cand.sort(key=lambda e: e["date"])
    return cand[0] if cand else None


def _upload(ep):
    video = os.path.join(BASE_DIR, ep["video"])
    if not os.path.exists(video):
        raise FileNotFoundError(f"영상 없음: {video}")
    body = {
        "snippet": {
            "title": ep["title"][:100],
            "description": ep["description"],
            "tags": ep["tags"],
            "categoryId": CATEGORY_EDU,
        },
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
    }
    yt = build("youtube", "v3", credentials=_creds())
    media = MediaFileUpload(video, chunksize=-1, resumable=True, mimetype="video/*")
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    log(f"[{ep.get('label', ep['no'])}] 유튜브 업로드 시작(public): {ep['title'][:50]}...")
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            log(f"  업로드 {int(status.progress()*100)}%")
    return f"https://youtu.be/{resp['id']}"


def _ig_caption(ep):
    """인스타 피드 본문: 설명에서 해시태그 줄(#…)을 뺀 나머지(훅·요약·링크)."""
    lines = [ln for ln in ep["description"].splitlines() if not ln.strip().startswith("#")]
    return "\n".join(lines).strip()


def _post_instagram(ep, dry=False):
    """insta-cardnews venv 로 릴 게시(subprocess). 절대 예외를 올리지 않고 상태 문자열 반환.

    dry=True 면 '공유하기' 직전까지만(브라우저를 열어 세션·업로드 플로우만 점검)."""
    if not os.path.exists(IG_PY):
        return "skipped: IG venv 없음"
    video_abs = os.path.join(BASE_DIR, ep["video"])
    payload = {
        "reel": video_abs,
        "caption": _ig_caption(ep),
        "hashtags": ep.get("tags", []),   # post_reel 이 '#' 붙여 첫 댓글로 게시
        "dry": dry,
    }
    env = {k: v for k, v in os.environ.items() if k != "SMUDS_EDITION"}
    log(f"[{ep.get('label', ep['no'])}] 인스타 릴 게시 시작...")
    try:
        p = subprocess.run([IG_PY, "post_reel_cli.py"], cwd=IG_DIR,
                           input=json.dumps(payload), text=True,
                           capture_output=True, timeout=IG_TIMEOUT, env=env)
    except subprocess.TimeoutExpired:
        return "error: timeout"
    out = (p.stdout or "").strip().splitlines()
    last = out[-1] if out else ""
    try:
        status = json.loads(last).get("status", "unknown")
    except Exception:
        status = f"unparsed(rc={p.returncode})"
    if status not in ("published", "shared_unconfirmed", "dry_run"):
        log(f"  인스타 게시 상태: {status} (stderr: {(p.stderr or '')[-200:]})")
    else:
        log(f"  인스타 게시 상태: {status}")
    return status


def main(argv):
    ignore_date = "--now" in argv
    dry = "--dry" in argv
    no_ig = "--no-ig" in argv
    ig_test = "--ig-test" in argv
    sched = _load()
    ep = _pick(sched, ignore_date)
    if not ep:
        log("발행할 예약 편이 없습니다(오늘 기준 미발행/예정일 없음).")
        return
    if dry:
        ch = "유튜브" if no_ig else "유튜브+인스타"
        log(f"[DRY] 발행 예정({ch}): [{ep.get('label', ep['no'])}] {ep['title'][:60]}  ← {ep['video']}")
        return
    if ig_test:
        # 실제 게시 없이 인스타 세션·업로드 플로우만 점검(브라우저를 열어 '공유하기' 직전까지).
        log(f"[IG-TEST] 세션·플로우 점검: [{ep.get('label', ep['no'])}] {ep['video']}")
        st = _post_instagram(ep, dry=True)
        log(f"[IG-TEST] 결과: {st} (실제 게시 안 함)")
        print("IG_TEST:", st)
        return

    # 1) 유튜브(기준 채널) — 성공해야 published 기록 → 중복 발행 방지
    url = _upload(ep)
    # 1-1) 자동 첫 댓글(구독 유도·참여 마중물) — force-ssl 스코프 필요, 실패해도 발행 유지
    try:
        from youtube_upload import post_top_comment
        post_top_comment(url.rsplit("/", 1)[-1], data={"title": ep.get("title", "")})
    except Exception as e:
        log(f"자동 댓글 건너뜀(유튜브는 정상): {type(e).__name__}")
    # 2) 인스타(부가 채널) — 실패해도 유튜브 발행은 유지
    ig_status = "skipped" if no_ig else _post_instagram(ep)

    ep["published"] = {
        "youtube": url,
        "instagram": ig_status,
        "at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    _save(sched)
    log(f"[{ep.get('label', ep['no'])}] 발행 완료 — YT:{url}  IG:{ig_status}")
    try:                        # 카카오톡 발행 알림(실패 무시)
        from kakao_notify import notify
        notify(f"[SMUDS 발행완료] 진로/퀴즈 {ep.get('label', ep['no'])}\n"
               f"{ep.get('title','')}\n{url}\n인스타: {ig_status}", url)
    except Exception as e:
        log(f"카톡 알림 건너뜀: {type(e).__name__}")
    if ig_status not in ("published", "shared_unconfirmed", "skipped"):
        log(f"  ⚠ 인스타 재시도(수동): cd {IG_DIR} && echo '<payload>' | ./.venv/bin/python post_reel_cli.py")
    print("PUBLISHED:", ep["no"], "YT", url, "IG", ig_status)


if __name__ == "__main__":
    main(sys.argv[1:])
