"""VEO_PROMPTS.md 의 장면 프롬프트로 B롤 클립을 만든다 — 세명대 AI 게이트웨이(Veo).

한 번 만든 클립은 posts/broll/veo/<이름>.mp4 에 쌓아 두고 여러 영상에서 돌려 쓴다.
실사(Pexels·Pixabay)가 없는 주제의 마지막 대비책이라 매번 새로 만들지 않는다.

비용(2026-09-29 실측): veo-3.1-lite 8초 9:16 = 400 크레딧(월 12,000), 한 편 약 3.5분.
여러 편을 한꺼번에 요청하고 같이 기다린다. 실패한 요청은 크레딧이 환불된다.

  python3 veo_clips.py --list                  # 만들 수 있는 장면 이름
  python3 veo_clips.py 위성 "디지털 트윈"        # 제목에 이 말이 든 장면을 만든다
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

from common import load_config, log

HERE = os.path.dirname(os.path.abspath(__file__))
PROMPTS = os.path.join(HERE, "VEO_PROMPTS.md")
OUT_DIR = os.path.join(HERE, "posts", "broll", "veo")
BASE = "https://factchat-cloud.mindlogic.ai/v1/gateway"
MODEL = "veo-3.1-lite-generate-preview"


def load_prompts():
    """{장면 제목: 프롬프트}, 공통 규칙. 마무리 장면은 소제목 대신 '마무리 장면'으로."""
    s = open(PROMPTS, encoding="utf-8").read()
    common = re.search(r"## 공통 규칙.*?```\n(.*?)```", s, re.S).group(1).strip()
    s = s.split("## 쓰는 법")[0]          # 뒤쪽 사용법 예시는 장면이 아니다
    scenes = {}
    for m in re.finditer(r"\*\*([^*\n]+)\*\*\n```\n(.*?)```", s, re.S):
        scenes[m.group(1).strip()] = m.group(2).strip()
    m = re.search(r"## 7\. 마무리[^\n]*\n+```\n(.*?)```", s, re.S)
    if m:
        scenes["마무리 장면"] = m.group(1).strip()
    return scenes, common


def slug(title):
    return re.sub(r"[^0-9A-Za-z가-힣]+", "_", title).strip("_")


def _req(key, method, url, body=None, timeout=300):
    # 파이썬 기본 User-Agent 는 Cloudflare 가 1010(403)으로 막는다
    h = {"Authorization": f"Bearer {key}", "x-api-key": key,
         "Content-Type": "application/json", "User-Agent": "smuds-autosns/1.0"}
    r = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                               headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as f:
            return f.status, f.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _ffmpeg():
    try:
        from make_video import _ffmpeg as f
        return f()
    except Exception:          # 시스템 파이썬엔 imageio_ffmpeg 가 없다(9/29 이 때문에 두 편 잃음)
        import shutil
        return shutil.which("ffmpeg") or "/usr/local/bin/ffmpeg"


def _strip_audio(src, dst):
    """무음 오디오 트랙을 뺀다(내레이션·BGM 은 따로 입힌다)."""
    r = subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", src,
                        "-an", "-c:v", "copy", "-movflags", "+faststart", dst],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-300:])


JOBS = os.path.join(OUT_DIR, "_jobs.json")


def _load_jobs():
    try:
        return json.load(open(JOBS, encoding="utf-8"))
    except Exception:
        return {}


def _save_jobs(jobs):
    # 요청 번호를 기다리기 전에 파일에 남긴다 — 도중에 멈춰도 다시 실행하면 이어서 받는다.
    # 크레딧은 요청 때 빠지므로 번호를 잃으면 영상도 크레딧도 잃는다.
    with open(JOBS + ".part", "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=1)
    os.replace(JOBS + ".part", JOBS)


MIN_MONTHLY = 500      # 월 할당이 이만큼 남으면 멈춘다 — 대본 작성(Claude) 몫을 남기고,
                       # 사용자가 따로 산 크레딧(purchased)으로 넘어가지 않게(9/29)


def monthly_remaining(key):
    st, b = _req(key, "GET", f"{BASE}/credits/")
    return float(json.loads(b)["monthly_allocated"]["remaining"]) if st < 300 else 0.0


def _submit(key, prompt, seconds):
    need = seconds / 4 * 200 + MIN_MONTHLY
    left = monthly_remaining(key)
    if left < need:
        return None, f"월 할당 부족(남음 {left:.0f} < 필요 {need:.0f}) — 구매 크레딧은 쓰지 않음"
    for n in range(3):
        st, b = _req(key, "POST", f"{BASE}/video/generation/",
                     {"model": MODEL, "prompt": prompt,
                      "parameters": {"duration_seconds": seconds, "aspect_ratio": "9:16"}})
        if st < 300:
            return json.loads(b)["operation_id"], None
        if st < 500:
            break
        time.sleep(15 * (n + 1))      # 게이트웨이 502 는 잠깐 뒤 다시 보내면 된다
    return None, f"{st} {b[:200].decode(errors='replace')}"


def _finish(key, t, op, out):
    st, v = _req(key, "GET", f"{BASE}/video/generation/{op}/download/?model={MODEL}")
    if st >= 300 or len(v) < 10_000:
        raise RuntimeError(f"내려받기 실패 http {st}")
    raw = out.replace(".mp4", ".raw.mp4")
    with open(raw, "wb") as f:
        f.write(v)
    _strip_audio(raw, out)
    os.remove(raw)


def generate(titles, seconds=8, force=False):
    key = load_config()["llm_gateway"]["api_key"]
    scenes, common = load_prompts()
    os.makedirs(OUT_DIR, exist_ok=True)
    jobs = _load_jobs()                       # 지난번에 못 받은 요청부터 이어 받는다
    if jobs:
        log(f"이어 받기: {', '.join(jobs)}")
    for t in titles:
        out = os.path.join(OUT_DIR, slug(t) + ".mp4")
        if t in jobs or (os.path.exists(out) and not force):
            log(f"이미 있음/진행 중: {t}")
            continue
        prompt = f"{scenes[t]}\n{common}"     # 비율·길이는 parameters 로만(문장에 쓰면 글자로 찍힘)
        op, err = _submit(key, prompt, seconds)
        if not op:
            log(f"요청 실패 {t}: {err}")
            continue
        jobs[t] = {"op": op, "out": out, "at": time.strftime("%Y-%m-%d %H:%M")}
        _save_jobs(jobs)
        log(f"요청: {t} ({op})")
    t0, done = time.time(), {}
    while jobs and time.time() - t0 < 1500:
        time.sleep(10)
        for t, j in list(jobs.items()):
            st, b = _req(key, "GET", f"{BASE}/video/generation/{j['op']}/?model={MODEL}")
            status = json.loads(b).get("status") if st < 300 else None
            if status not in ("completed", "failed"):
                continue                      # 처리 중이거나 일시 오류(5xx) — 다음 차례에 다시
            if status == "completed":
                try:
                    _finish(key, t, j["op"], j["out"])
                except Exception as e:
                    log(f"받기 실패 {t}: {e} — 요청 번호는 남겨 둠, 다시 실행하면 이어 받음")
                    continue
                done[t] = j["out"]
                log(f"완료 {t} ({time.time() - t0:.0f}초): {os.path.relpath(j['out'], HERE)}")
            else:
                log(f"실패 {t}(크레딧 환불): {b[:300].decode(errors='replace')}")
            del jobs[t]
            _save_jobs(jobs)
    for t in jobs:
        log(f"아직 처리 중 {t} — 나중에 다시 실행하면 이어 받음")
    return done


# ── 뉴스판용 AI 실사 클립 창고 ─────────────────────────────────────────────
# 뉴스 장면 배경은 Pexels → Pixabay 실사를 먼저 찾고, 없을 때만 여기 클립을 쓴다
# (render_frames, 'AI 생성 영상' 표기 + 유튜브 합성 콘텐츠 신고). 열쇠는 shared/stock_video
# 의 주제 검색어와 같다. 특정 사건 현장처럼 보이지 않게 '그 주제의 일반 풍경'만 담는다 —
# 사람·차량 번호·간판·피해 장면을 넣지 않는다(2026-09-29 결정).
REAL_DIR = os.path.join(HERE, "posts", "broll_pexels", "ai")   # 경로에 broll_pexels → 글자 강화
REAL_COMMON = """Photorealistic documentary footage, natural colors, realistic lighting,
shot on a professional cinema camera. Tall vertical framing. The upper 40% of the frame
is visually simple (sky, wall or soft background) for text overlay. Slow, steady camera.
No text, no letters, no numbers, no signs, no logos, no license plates, no watermarks,
no on-screen graphics. No people's faces. No injured people, no damage victims."""
REAL_PROMPTS = {
    "forest fire smoke": "A forested mountain ridge in Korea seen from a distance, thin grey smoke drifting over the trees under a hazy sky. Wide, slow pan.",
    "heavy rain street": "Heavy rain pouring on an empty city street at dusk, water running along the curb and rippling in puddles, blurred street lights. Low static shot.",
    "storm wind trees": "Strong wind bending tall trees and roadside grass under dark storm clouds, rain streaks in the air. Slow push-in.",
    "snow winter street": "Snow falling steadily on a quiet residential street at night, street lamps glowing, fresh snow on parked cars and rooftops. Slow dolly.",
    "hot summer sun city": "Harsh midday summer sun over a city, heat haze shimmering above an asphalt road, bright white sky. Slow pan.",
    "mountain forest rain": "Rain falling on a steep forested mountain slope, mist rolling through the trees, small streams of muddy water running down. Slow tilt down.",
    "city buildings aerial": "Aerial view of a Korean city of apartment blocks and roads on a clear morning, slow drone flyover.",
    "fire smoke dark": "Close view of orange flames and rising smoke against a dark background, embers floating upward. Abstract, no buildings visible. Slow motion.",
    "drone flying sky": "A white quadcopter drone flying steadily against a partly cloudy sky over green fields, side-follow tracking shot.",
    "city lights night timelapse": "A city control room style view through a large window at night: city lights and traffic trails below, soft blue glow. Slow push-in.",
    "fire truck city": "A red fire truck parked at a fire station bay, doors open, equipment neatly stored, early morning light. Slow dolly along the truck.",
    "highway traffic night": "Highway at night with steady streams of headlights and tail lights, elevated view, gentle motion blur.",
    "busy market street": "A covered traditional market alley in Korea with stalls of fruit and vegetables, warm lights, soft background motion without faces. Slow walk-through.",
    "clouds sky timelapse": "Clouds moving across a wide blue sky over distant hills, calm timelapse.",
}


def real_clip(query):
    """뉴스 장면용 AI 실사 클립(어둡게 가공한 1080×1920 사본) 경로. 없으면 None."""
    raw = os.path.join(REAL_DIR, slug(query) + ".mp4")
    if not os.path.exists(raw):
        return None
    import shutil
    root = os.path.dirname(HERE)
    if root not in sys.path:
        sys.path.insert(0, root)
    from shared import pexels
    return pexels.dim(raw, ffmpeg=shutil.which("ffmpeg") or "/usr/local/bin/ffmpeg")


def generate_real(queries, seconds=8):
    """REAL_PROMPTS 의 주제를 만들어 REAL_DIR 에 둔다. 요청·이어받기는 generate 와 같은 장부."""
    key = load_config()["llm_gateway"]["api_key"]
    os.makedirs(REAL_DIR, exist_ok=True)
    jobs = _load_jobs()
    for q in queries:
        out = os.path.join(REAL_DIR, slug(q) + ".mp4")
        name = "실사:" + q
        if name in jobs or os.path.exists(out):
            log(f"이미 있음/진행 중: {name}")
            continue
        op, err = _submit(key, f"{REAL_PROMPTS[q]}\n{REAL_COMMON}", seconds)
        if not op:
            log(f"요청 실패 {name}: {err}")
            continue
        jobs[name] = {"op": op, "out": out, "at": time.strftime("%Y-%m-%d %H:%M")}
        _save_jobs(jobs)
        log(f"요청: {name} ({op})")
    return generate([], seconds)          # 장부에 남은 것을 모두 기다려 받는다


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--seconds", type=int, default=8, choices=(4, 6, 8))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--real", nargs="*", help="뉴스판 AI 실사 클립(주제 검색어, 비우면 전부)")
    a = ap.parse_args()
    if a.real is not None:
        qs = a.real or list(REAL_PROMPTS)
        print(f"AI 실사 {len(qs)}편 (약 {len(qs) * a.seconds // 4 * 200} 크레딧)")
        generate_real(qs, a.seconds)
        sys.exit(0)
    scenes, _ = load_prompts()
    if a.list or not a.names:
        for t in scenes:
            print(("✓ " if os.path.exists(os.path.join(OUT_DIR, slug(t) + ".mp4")) else "  ") + t)
        sys.exit(0)
    picked = [t for t in scenes if any(n in t for n in a.names)]
    if not picked and not _load_jobs():
        sys.exit("맞는 장면이 없습니다: " + ", ".join(a.names))
    print(f"만들 장면 {len(picked)}편 (약 {len(picked) * a.seconds // 4 * 200} 크레딧): {', '.join(picked)}")
    generate(picked, a.seconds, a.force)
