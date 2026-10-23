"""유튜브가 공개된 뒤(편 날짜 19:00, config.publish.time_kst) 인스타 릴스·학과 블로거·네이버 블로그·스레드에 함께 올린다.

  .venv/bin/python crosspost.py            # 오늘 공개된 편을 찾아 올린다(launchd: 화·금 19:30, 21:00 재시도)
  .venv/bin/python crosspost.py <편> --dry  # 각 채널을 '게시 직전'까지만 점검
채널별 결과를 <편>/crosspost.json 에 남겨, 다시 실행해도 이미 올린 채널은 건너뛴다.
기존 AutoSNS 게시 도구를 그대로 쓴다(인스타·스레드: insta-cardnews, 블로그: naver-blog-auto).
"""
import datetime as dt, json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
ROOT = CFG["root"]
AS = "/Volumes/USB256/devAPP/AutoSNS"
IG_DIR, NB_DIR, YT_DIR = f"{AS}/channels/insta-cardnews", f"{AS}/channels/naver-blog-auto", f"{AS}/channels/youtube-shorts-auto"
KST = dt.timezone(dt.timedelta(hours=9))
OK = ("published", "shared_unconfirmed", "dry_run")


def log(m):
    print(f"[{dt.datetime.now(KST):%m-%d %H:%M}] {m}", flush=True)


def _cli(proj, script, payload, timeout=900):
    env = {k: v for k, v in os.environ.items() if k != "SMUDS_EDITION"}
    try:
        p = subprocess.run([f"{proj}/.venv/bin/python", script], cwd=proj, input=json.dumps(payload, ensure_ascii=False),
                           text=True, capture_output=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return "error: timeout"
    lines = [l for l in (p.stdout or "").strip().splitlines() if l.startswith("{")]
    m = re.findall(r"동영상 뉴스: (\w+)", p.stdout or "")      # 네이버 post_video.py 는 결과를 로그 줄로만 남긴다
    if not lines and m:
        return m[-1]
    try:
        return json.loads(lines[-1]).get("status", "unknown")
    except Exception:
        return f"error(rc={p.returncode}): {(p.stderr or p.stdout or '')[-200:]}"


def texts(sc, url):
    tag = sc["type"].replace(" ", "").replace("·", "")
    lines = [s["narration"] for s in sc["scenes"]]
    h = sc.get("hashtags") or {}
    hashtags = [t.lstrip("#").replace(" ", "") for t in (h.get("instagram") or [tag, "재난대응", "국민행동요령", "안전수칙", "재난안전학과"])][:5]
    topic = (h.get("threads") or tag).lstrip("#").replace(" ", "")
    caption = (f"{sc['title']}\n\n" + "\n".join("✔ " + l for l in lines) +
               f"\n\n매주 화요일 저녁 7시, 계절에 맞는 재난 대응 방법을 알려 드려요.\n"
               f"출처: 행정안전부 국민안전24 국민행동요령({sc['type']})\n"
               "※ AI 아바타·AI 생성 재현 영상이 포함되어 있습니다.")
    threads = (f"{sc['title']}\n\n" + "\n".join("✔ " + l for l in lines) + f"\n\n▶ {url}\n#{topic}")[:490]   # 스레드는 주제 태그 1개만 연결된다
    return caption, hashtags, threads


def blog_html(sc, video_id):
    sys.path.insert(0, NB_DIR)
    from geoai_blogger import video_html
    items = "".join(f"<li>{s['narration']}</li>" for s in sc["scenes"])
    return (f"<p>세명대학교 재난안전학과가 매주 화요일 계절에 맞는 재난 대응 방법을 짧은 영상으로 알려 드립니다. "
            f"이번 주 주제는 <b>{sc['type']}</b>입니다.</p>{video_html(video_id, sc['title'])}"
            f"<h3>영상 핵심 정리</h3><ul>{items}</ul>"
            f"<p>출처: 행정안전부 국민안전24 국민행동요령({sc['type']})<br>"
            "※ 인트로·아웃트로는 AI 아바타, 배경은 AI로 생성한 3D 재현 영상입니다.</p>")


def post_blogger(sc, video_id, dry):
    """학과 블로그(smuds2026.blogspot.com) — naver-blog-auto 의 학과 블로거 토큰 사용."""
    code = f"""
import json, sys
sys.path.insert(0, {NB_DIR!r})
import os; os.chdir({NB_DIR!r})
from common import load_config
import post_blogger as PB
from googleapiclient.discovery import build
p = json.loads(sys.stdin.read()); cfg = load_config(); b = cfg["blogger"]
if p["dry"]:
    print(json.dumps({{"status": "dry_run"}})); sys.exit()
svc = build("blogger", "v3", credentials=PB._creds(cfg), cache_discovery=False)
if PB._already_posted(svc, b["blog_id"], p["title"]):
    print(json.dumps({{"status": "published", "note": "duplicate"}})); sys.exit()
r = svc.posts().insert(blogId=b["blog_id"], isDraft=False, body={{"kind": "blogger#post", "title": p["title"],
    "content": p["html"], "labels": p["labels"]}}).execute()
print(json.dumps({{"status": "published", "url": r.get("url", "")}}))
"""
    payload = {"title": sc["title"], "html": blog_html(sc, video_id), "labels": ["재난대응숏츠", sc["type"]], "dry": dry}
    p = subprocess.run([f"{NB_DIR}/.venv/bin/python", "-c", code], cwd=NB_DIR, input=json.dumps(payload, ensure_ascii=False),
                       text=True, capture_output=True, timeout=300)
    lines = [l for l in p.stdout.splitlines() if l.startswith("{")]
    return json.loads(lines[-1])["status"] if lines else f"error: {(p.stderr or '')[-200:]}"


def src_url(ep_dir):
    for line in open(os.path.join(ep_dir, "source.md"), encoding="utf-8"):
        if line.startswith("http"):
            return line.strip()
    return "https://www.safekorea.go.kr/safekorea-kor/acts/nacts/nationalActionTips.do?menuSn=4"


def _yt():
    sys.path.insert(0, YT_DIR); os.chdir(YT_DIR)
    from googleapiclient.discovery import build
    import youtube_upload as YU
    return build("youtube", "v3", credentials=YU._creds(os.path.join(YT_DIR, CFG["publish"]["channel_token"])),
                 cache_discovery=False)


def ensure_public(video_id, date_str):
    """공개 시각(편 날짜 config.publish.time_kst, 19:00)이 지났는데 아직 비공개면 API 로 직접 공개한다.

    유튜브 예약(publishAt)이 거부되거나 풀린 편의 대비책(2026-10-03 산불편: 예약이 거부돼
    비공개·예약 없음 상태가 됨). 상태를 바꿀 때는 빠진 필드가 기본값으로 덮이므로
    (embeddable=False 사고) 필요한 값을 모두 함께 보낸다."""
    yt = _yt()
    items = yt.videos().list(part="status", id=video_id).execute().get("items", [])
    if not items:
        raise RuntimeError(f"유튜브에서 영상을 찾지 못함: {video_id}")
    st = items[0]["status"]
    if st["privacyStatus"] == "public":
        return "이미 공개"
    h, m = map(int, CFG["publish"]["time_kst"].split(":"))
    d = dt.date.fromisoformat(date_str)
    if dt.datetime.now(KST) < dt.datetime(d.year, d.month, d.day, h, m, tzinfo=KST):
        return "공개 시각 전"
    yt.videos().update(part="status", body={"id": video_id, "status": {
        "privacyStatus": "public", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True,
        "embeddable": True, "publicStatsViewable": True, "license": "youtube"}}).execute()
    return "API 로 공개함"


def run(ep, dry=False):
    ep_dir = os.path.join(ROOT, ep)
    sc = json.load(open(os.path.join(ep_dir, "script.json"), encoding="utf-8"))
    up = json.load(open(os.path.join(ep_dir, "upload.json")))
    if not dry:
        r = ensure_public(up["video_id"], sc["date"]); log(f"{ep}: 유튜브 — {r}")
        if r == "공개 시각 전":
            return
        if r == "API 로 공개함":
            time.sleep(60)                          # 공개가 퍼질 시간을 잠깐 준 뒤 교차 게시
    rec_p = os.path.join(ep_dir, "crosspost.json")
    rec = json.load(open(rec_p)) if os.path.exists(rec_p) else {}
    caption, tags, threads = texts(sc, up["url"])
    jobs = {
        "instagram": lambda: _cli(IG_DIR, "post_reel_cli.py", {"reel": os.path.join(ep_dir, "final.mp4"), "caption": caption,
                                                               "hashtags": tags, "ai_label": True, "dry": dry,
                                                               "cover": os.path.join(ep_dir, "thumbnail.jpg")}),
        "blogger": lambda: post_blogger(sc, up["video_id"], dry),
        "naver": lambda: _cli(NB_DIR, "post_video.py", {"title": sc["title"], "body": caption, "youtube_url": up["url"],
                                                         "sources": [{"title": f"행정안전부 국민안전24 국민행동요령 — {sc['type']}",
                                                                      "link": src_url(ep_dir), "published_str": "국민안전24"}],
                                                         "category": "동영상뉴스", "dry_run": dry,
                                                         "tags": [t.lstrip("#").replace(" ", "") for t in ((sc.get("hashtags") or {}).get("naver") or [])][:10]}),
        "threads": lambda: _cli(IG_DIR, "threads_cli.py", {"text": threads, "dry": dry}),
    }
    for name, fn in jobs.items():
        if rec.get(name) in ("published", "shared_unconfirmed"):
            continue
        st = fn(); log(f"{name}: {st}")
        if not dry:
            rec[name] = st; json.dump(rec, open(rec_p, "w"), ensure_ascii=False, indent=1)
    bad = [k for k, v in rec.items() if v not in OK]
    if not dry:
        try:
            sys.path.insert(0, YT_DIR); os.chdir(YT_DIR)
            from kakao_notify import notify
            notify(f"[재난 대응 숏츠] {sc['type']} 편 공개·교차 게시\n" +
                   "\n".join(f"{k}: {'✅' if v in OK else '❌ ' + str(v)[:60]}" for k, v in rec.items()), up["url"])
        except Exception as e:
            log(f"카톡 알림 실패: {e}")
    return bad


def today_ep():
    today = dt.datetime.now(KST).date().isoformat()
    for d in sorted(os.listdir(ROOT)):
        if d.startswith(today) and os.path.exists(os.path.join(ROOT, d, "upload.json")):
            return d


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ep = args[0] if args else today_ep()
    if not ep:
        log("오늘 공개되는 편이 없습니다"); sys.exit(0)
    run(ep, dry="--dry" in sys.argv)
