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
import re
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


def _refresh_dashboard():
    """발행 기록이 바뀌면 운영 대시보드를 다시 만든다. 실패해도 발행은 막지 않는다."""
    try:
        subprocess.run([sys.executable, os.path.join(BASE_DIR, "..", "ax-console", "app", "build_dashboard.py")],
                       capture_output=True, timeout=60)
    except Exception:
        pass


def _load():
    with open(SCHED_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save(sched):
    with open(SCHED_PATH, "w", encoding="utf-8") as f:
        json.dump(sched, f, ensure_ascii=False, indent=2)
    _refresh_dashboard()


def _pick(sched, ignore_date):
    """발행할 편 1개 선택: 미발행 중 예정일 이른 순. ignore_date 면 날짜 조건 무시.

    영상 파일이 없는 편은 건너뛴다 — 한 편이 빠져도 주간 슬롯 전체가 죽지 않게.
    """
    today = datetime.date.today()
    cand = []
    for e in sched:
        if e.get("published"):
            continue
        due = datetime.date.fromisoformat(e["date"])
        if ignore_date or due <= today:
            cand.append(e)
    cand.sort(key=lambda e: e["date"])
    for e in cand:
        if os.path.exists(os.path.join(BASE_DIR, e["video"])):
            return e
        log(f"영상이 없어 건너뜁니다: [{e.get('label', e['no'])}] {e['video']}")
    return None


def _upload(ep):
    video = os.path.join(BASE_DIR, ep["video"])
    if not os.path.exists(video):
        raise FileNotFoundError(f"영상 없음: {video}")
    # 설명 = 본문 → 시리즈 몰아보기 → 채널 링크(인스타·블로그·스레드·X) → 해시태그.
    # 해시태그 줄은 맨 끝에 둔다(유튜브가 마지막 해시태그를 제목 위에 띄운다). 채널 링크는
    # 2026-10-06 X 개설 때 퀴즈·진로 설명에 하나도 없던 것을 뉴스 영상과 같게 채웠다.
    desc = ep["description"]
    try:
        from common import load_config
        yc = load_config().get("youtube", {})
        lines = desc.rstrip().splitlines()
        tags = []
        while lines and (lines[-1].strip().startswith("#") or not lines[-1].strip()):
            ln = lines.pop()
            if ln.strip():
                tags.insert(0, ln)
        parts = ["\n".join(lines).rstrip()]
        kind = "quiz" if ep.get("series") == "quiz" else "career"
        pid = (yc.get("playlists", {}) or {}).get(kind)
        label = (yc.get("playlist_labels", {}) or {}).get(kind, "시리즈 전편 보기")
        if pid:
            parts.append(f"▶ {label}: https://www.youtube.com/playlist?list={pid}")
        links = [f"{l.get('label', '').strip()}: {l['url'].strip()}"
                 for l in (yc.get("channel_links") or []) if (l.get("url") or "").strip()]
        if links:
            parts.append("\n".join(links))
        if tags:
            parts.append("\n".join(tags))
        desc = "\n\n".join(x for x in parts if x)
    except Exception:
        desc = ep["description"]
    body = {
        "snippet": {
            "title": ep["title"][:100],
            "description": desc,
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


def _threads_text(ep, url):
    """스레드 본문: 제목 + 설명 앞부분 + 유튜브 링크 + 해시태그(최대 5개).

    run_weekly.py 의 뉴스 크로스포스트와 같은 구성으로 맞췄다."""
    body = [ln.strip() for ln in ep.get("description", "").splitlines()
            if ln.strip() and not ln.strip().startswith("#")]
    # 제목의 '#Shorts' 는 유튜브 노출용이라 스레드에서는 뺀다.
    title = re.sub(r"\s*#shorts\b", "", ep.get("title", "재난안전학과 진로"), flags=re.I).strip()
    summary = next((ln for ln in body if ln != title), "")
    tags = [t for t in (ep.get("tags") or []) if t.lower() != "shorts"][:5]
    parts = [title, summary, ("▶ " + url) if url else "",
             " ".join("#" + t for t in tags)]
    return "\n\n".join(x for x in parts if x)[:500]


def _post_threads(ep, url):
    """스레드에 텍스트로 크로스포스트한다. 예외를 올리지 않고 상태 문자열만 돌려준다.

    유튜브 뉴스(run_weekly.py)에는 붙어 있었는데 진로 시리즈에는 없어서, 9월 스레드
    발행이 유튜브 22건 중 8건에 그쳤다."""
    cli = os.path.join(IG_DIR, "threads_cli.py")
    if not (os.path.exists(IG_PY) and os.path.exists(cli)):
        return "skipped: threads_cli 없음"
    text = _threads_text(ep, url)
    if not text.strip():
        return "skipped: 본문 없음"
    env = {k: v for k, v in os.environ.items() if k != "SMUDS_EDITION"}
    try:
        p = subprocess.run([IG_PY, "threads_cli.py"], cwd=IG_DIR,
                           input=json.dumps({"text": text}), text=True,
                           capture_output=True, timeout=300, env=env)
    except subprocess.TimeoutExpired:
        return "error: timeout"
    out = (p.stdout or "").strip().splitlines()
    try:
        status = json.loads(out[-1] if out else "").get("status", "unknown")
    except Exception:
        status = f"unparsed(rc={p.returncode})"
    log(f"  쓰레드 게시 상태: {status}"
        + (f" (stderr: {(p.stderr or '')[-200:]})" if status not in ("published", "dry_run") else ""))
    return status


def _post_x(ep):
    """X 에 영상을 첨부해 올린다. 예외를 올리지 않고 상태 문자열만 돌려준다."""
    try:
        from x_post import crosspost
        v = ep.get("video") or ""
        v = v if os.path.isabs(v) else os.path.join(BASE_DIR, v)
        r = crosspost({"title": ep.get("title", ""), "tags": ep.get("tags") or []}, video=v)
        if r.get("status") != "disabled":
            log(f"  X 게시 상태: {r.get('status')} {r.get('url', '')}")
        return r.get("status", "unknown")
    except Exception as e:
        log(f"  X 건너뜀(유튜브는 정상): {type(e).__name__}: {str(e)[:120]}")
        return "error"


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
    no_threads = "--no-threads" in argv
    ig_test = "--ig-test" in argv
    sched = _load()
    ep = _pick(sched, ignore_date)
    if not ep:
        log("발행할 예약 편이 없습니다(오늘 기준 미발행/예정일 없음, 또는 영상 파일 없음).")
        return
    if dry:
        ch = "유튜브" + ("" if no_ig else "+인스타") + ("" if no_threads else "+쓰레드")
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
    try:                                   # 틱톡 하루 1편 대기열(실패해도 발행은 계속)
        from tiktok_queue import add as tiktok_add
        tiktok_add(ep["video"] if os.path.isabs(ep["video"]) else os.path.join(BASE_DIR, ep["video"]),
                   ep["title"], ep.get("description", ""), ep.get("tags", []), source="publish_career")
    except Exception as e:  # noqa: BLE001
        log(f"틱톡 대기열 건너뜀: {type(e).__name__}")
    # 1-0') 자막 업로드 — 편 정보에 대본(scenes)이 있으면 그대로 자막으로 만든다.
    try:
        if ep.get("scenes"):
            from make_captions import attach as attach_caption
            attach_caption({"scenes": ep["scenes"], "video": os.path.join(BASE_DIR, ep["video"])},
                           video_id=url.rsplit("/", 1)[-1])
    except Exception as e:
        log(f"자막 업로드 건너뜀: {type(e).__name__}")
    # 1-0) 재생목록 편입(진로/퀴즈 시리즈별)
    try:
        from youtube_upload import add_to_playlist
        add_to_playlist(url.rsplit("/", 1)[-1],
                        kind=("quiz" if ep.get("series") == "quiz" else "career"))
    except Exception as e:
        log(f"재생목록 편입 건너뜀: {type(e).__name__}")
    # 1-1) 자동 첫 댓글(구독 유도·참여 마중물) — force-ssl 스코프 필요, 실패해도 발행 유지
    try:
        from youtube_upload import post_top_comment
        post_top_comment(url.rsplit("/", 1)[-1], data={"title": ep.get("title", "")})
    except Exception as e:
        log(f"자동 댓글 건너뜀(유튜브는 정상): {type(e).__name__}")
    # 2) 인스타(부가 채널) — 실패해도 유튜브 발행은 유지
    ig_status = "skipped" if no_ig else _post_instagram(ep)
    # 3) 스레드(부가 채널) — 위와 같이 실패해도 유튜브 발행은 유지
    th_status = "skipped" if no_threads else _post_threads(ep, url)
    # 4) X(부가 채널) — 영상 첨부. 설정이 꺼져 있으면 'disabled'
    x_status = _post_x(ep)

    ep["published"] = {
        "youtube": url,
        "instagram": ig_status,
        "threads": th_status,
        "x": x_status,
        "at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    _save(sched)
    log(f"[{ep.get('label', ep['no'])}] 발행 완료 — YT:{url}  IG:{ig_status}  TH:{th_status}  X:{x_status}")
    try:                        # 카카오톡 발행 알림(실패 무시)
        from kakao_notify import notify
        notify(f"[SMUDS 발행완료] 진로/퀴즈 {ep.get('label', ep['no'])}\n"
               f"{ep.get('title','')}\n{url}\n인스타: {ig_status} · 쓰레드: {th_status}", url)
    except Exception as e:
        log(f"카톡 알림 건너뜀: {type(e).__name__}")
    if ig_status not in ("published", "shared_unconfirmed", "skipped"):
        log(f"  ⚠ 인스타 재시도(수동): cd {IG_DIR} && echo '<payload>' | ./.venv/bin/python post_reel_cli.py")
    print("PUBLISHED:", ep["no"], "YT", url, "IG", ig_status, "TH", th_status)


if __name__ == "__main__":
    main(sys.argv[1:])
