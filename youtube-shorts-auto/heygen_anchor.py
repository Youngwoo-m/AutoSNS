"""HeyGen 토킹 아바타(아나운서) 영상 생성 — 사진 1장 + 대본 → 세로 뉴스 영상.

사전 준비: config.json 에 heygen 섹션 추가
  "heygen": { "api_key": "<HeyGen API 키>", "voice_id": "<한국어 voice id>" }

사용법:
  python heygen_anchor.py voices            # 한국어 보이스 목록(voice_id 고르기)
  python heygen_anchor.py photo my.jpg      # 사진 업로드 → talking_photo_id 출력
  python heygen_anchor.py gen <tp_id> "대본"  # 아나운서 영상 생성→다운로드(posts/)

동작 검증은 API 키가 준비되면 수행합니다(현재는 키 없이 호출 불가).
"""
import json
import os
import sys
import time
import urllib.request

from common import BASE_DIR, POSTS_DIR, load_config, log

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.fonts import DOTUM_BOLD, default_font_dir, require_fonts  # noqa: E402

API = "https://api.heygen.com"
UPLOAD = "https://upload.heygen.com/v1/talking_photo"
W, H = 1080, 1920   # 9:16 세로(인스타 릴스·쇼츠 권장 해상도)
LAYOUT_W = 720      # 레이아웃 좌표를 잡아둔 기준 폭. 실제 영상 폭에 맞춰 배율 환산한다.


def _key():
    k = load_config().get("heygen", {}).get("api_key", "")
    if not k or k.startswith("PUT_YOUR"):
        raise SystemExit("config.json 의 heygen.api_key 를 먼저 설정하세요.")
    return k


def _req(method, url, body=None, headers=None, raw=None):
    h = {"X-Api-Key": _key()}
    if headers:
        h.update(headers)
    data = raw if raw is not None else (json.dumps(body).encode() if body else None)
    if body is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def list_korean_voices():
    """한국어 보이스만 추려 voice_id 를 보여준다."""
    data = _req("GET", f"{API}/v2/voices")
    voices = data.get("data", {}).get("voices", [])
    ko = [v for v in voices if (v.get("language", "") or "").lower().startswith("korean")
          or "ko" in (v.get("language", "") or "").lower()]
    for v in ko[:30]:
        print(f"  {v.get('voice_id')}  {v.get('name')}  ({v.get('gender')}, {v.get('language')})")
    if not ko:
        print("한국어 보이스를 못 찾음 — 전체 목록에서 직접 확인하세요.")


def upload_photo(path):
    """정면 사진을 업로드해 talking_photo_id 를 받는다."""
    with open(path, "rb") as f:
        raw = f.read()
    ct = "image/png" if path.lower().endswith(".png") else "image/jpeg"
    data = _req("POST", UPLOAD, raw=raw, headers={"Content-Type": ct})
    tp = data.get("data", {}).get("talking_photo_id")
    log(f"talking_photo_id = {tp}")
    return tp


def upload_audio(path):
    """나레이션 오디오(mp3)를 업로드해 audio_asset_id 를 받는다(우리 남성 TTS 사용용)."""
    with open(path, "rb") as f:
        raw = f.read()
    data = _req("POST", "https://upload.heygen.com/v1/asset", raw=raw,
                headers={"Content-Type": "audio/mpeg"})
    aid = (data.get("data", {}) or {}).get("id") or (data.get("data", {}) or {}).get("asset_id")
    log(f"audio_asset_id = {aid}")
    return aid


def generate(talking_photo_id, script=None, voice_id=None, audio_asset_id=None, wait=True):
    """아나운서 영상 생성 → (선택)완료까지 대기 후 다운로드.

    audio_asset_id 를 주면 그 오디오로 립싱크(우리 남성 TTS). 없으면 HeyGen TTS(text)."""
    cfg = load_config().get("heygen", {})
    if audio_asset_id:
        voice = {"type": "audio", "audio_asset_id": audio_asset_id}
    else:
        voice_id = voice_id or cfg.get("voice_id")
        if not voice_id:
            raise SystemExit("voice_id 또는 audio_asset_id 가 필요합니다.")
        voice = {"type": "text", "input_text": script, "voice_id": voice_id}
        # 말 속도(0.5~1.5, 기본 1.0). 낮을수록 천천히 — 뉴스 전달력·자막 가독성↑
        try:
            spd = float(cfg.get("voice_speed", 1.0))
        except (TypeError, ValueError):
            spd = 1.0
        if spd and abs(spd - 1.0) > 1e-6:
            voice["speed"] = max(0.5, min(1.5, spd))
    vin = {
        "character": {"type": "talking_photo", "talking_photo_id": talking_photo_id},
        "voice": voice,
    }
    bg = (load_config().get("heygen", {}) or {}).get("background")
    if bg:                       # {"type":"color","value":"#008000"} 또는 image_asset_id
        vin["background"] = bg
    body = {"video_inputs": [vin], "dimension": {"width": W, "height": H}}
    res = _req("POST", f"{API}/v2/video/generate", body=body)
    vid = res.get("data", {}).get("video_id")
    log(f"video_id = {vid} (생성 요청됨)")
    if not wait:
        return {"video_id": vid}
    return await_video(vid, cfg)


def await_video(vid, cfg=None):
    """이미 요청된 HeyGen 영상을 기다렸다가 내려받는다.

    시간 초과로 놓친 건도 이 함수로 이어받을 수 있다(크레딧은 요청 시점에 나가므로,
    다시 만들지 말고 완성본을 받아 쓴다). 2026-09-16 큐가 밀려 20분을 넘긴 적이 있다."""
    cfg = cfg if cfg is not None else load_config().get("heygen", {})
    try:
        waits = int(float(cfg.get("wait_minutes", 10)) * 12)
    except (TypeError, ValueError):
        waits = 120
    url = None
    for _ in range(waits):
        st = _req("GET", f"{API}/v1/video_status.get?video_id={vid}")
        d = st.get("data", {})
        status = d.get("status")
        if status == "completed":
            url = d.get("video_url")
            break
        if status == "failed":
            raise SystemExit(f"생성 실패: {d.get('error')}")
        log(f"  상태: {status}...")
        time.sleep(5)
    if not url:
        raise SystemExit(f"시간 초과({waits*5//60}분) — video_id={vid} 로 나중에 "
                         "이어받을 수 있습니다(geoai_video.py 의 heygen_video_id).")
    out = os.path.join(POSTS_DIR, f"anchor_{vid}.mp4")
    urllib.request.urlretrieve(url, out)
    log(f"다운로드 완료: {out}")
    return {"video_id": vid, "path": out, "url": url}


def add_title(video_in, title, out):
    """영상 상단에 제목 바만 합성(수동 CLI 용).

    레이아웃이 갈라지지 않게 compose_news_layout 을 그대로 쓴다(관련화면·자막 생략)."""
    return compose_news_layout(video_in, out, title)


def _font():
    import shutil
    f = os.path.join(POSTS_DIR, "_kopub_bold.otf")
    if not os.path.exists(f):
        d = require_fonts(default_font_dir(BASE_DIR), (DOTUM_BOLD,))
        shutil.copy(os.path.join(d, DOTUM_BOLD), f)
    return f


def _esc(t):
    return (t or "").replace("[", "").replace("]", "").replace("\\", "") \
        .replace(":", "\\:").replace("'", "").replace("%", "")


_TW_CACHE = {}
_TW_THRESH = bytes(0 if v <= 40 else 255 for v in range(256))


def _text_width(text, size):
    """drawtext 로 실제 렌더했을 때의 글자 폭(px).

    폰트 메트릭 라이브러리(PIL 등) 없이, 검은 캔버스에 흰 글자를 그려
    raw gray 픽셀을 스캔한다. 세이프존 계산은 추정치가 아니라 실측이어야 한다.
    """
    key = (text, size)
    if key in _TW_CACHE:
        return _TW_CACHE[key]
    import subprocess
    import imageio_ffmpeg
    cw, ch = 2400, max(int(size * 2.4), 80)
    vf = (f"drawtext=fontfile='{_font()}':text='{_esc(text)}':"
          f"fontcolor=white:fontsize={size}:x=40:y=20")
    p = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
                        "-f", "lavfi", "-i", f"color=black:s={cw}x{ch}:d=0.1", "-vf", vf,
                        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                       capture_output=True)
    b, xmin, xmax = p.stdout, cw, -1
    if len(b) >= cw * ch:
        for y in range(ch):
            row = b[y * cw:(y + 1) * cw].translate(_TW_THRESH)
            r = row.rstrip(b"\x00")
            if not r:
                continue
            xmax = max(xmax, len(r) - 1)
            xmin = min(xmin, len(r) - len(r.lstrip(b"\x00")))
    w = (xmax - xmin + 1) if xmax >= 0 else int(len(text) * size * 0.9)
    _TW_CACHE[key] = w
    return w


def _fit_text(text, size, max_w, min_size=36):
    """max_w 안에 들어오게 폰트를 줄이고, 그래도 넘치면 말줄임(…)으로 자른다."""
    s = size
    while s > min_size and _text_width(text, s) > max_w:
        s -= 2
    if _text_width(text, s) <= max_w:
        return text, s
    t = text
    while len(t) > 4 and _text_width(t + "…", s) > max_w:
        t = t[:-1]
    return t.rstrip(" ·,.") + "…", s


def _duration(path):
    import re
    import subprocess
    import imageio_ffmpeg
    p = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-i", path],
                       capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", p.stderr)
    return (int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))) if m else 40.0


def _img_size(path):
    import re
    import subprocess
    import imageio_ffmpeg
    p = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-i", path],
                       capture_output=True, text=True)
    m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", p.stderr)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def _pick_ots_image(paths):
    """우측 '관련화면'용 최적 이미지 선택.

    로고·배너·아이콘(작거나 극단적 비율)은 제외하고 실제 사진(면적 큰 것) 우선.
    적절한 사진이 없으면 None → 우측 박스 생략(로고 노출 방지).
    """
    best, best_score = None, -1
    for p in paths or []:
        if not p or not os.path.exists(p):
            continue
        w, h = _img_size(p)
        if w < 400 or h < 300:                 # 너무 작음 → 로고/아이콘 가능성
            continue
        ar = w / max(h, 1)
        if ar > 3.0 or ar < 0.5:               # 극단 비율(가로배너·세로띠) → 제외
            continue
        score = w * h                          # 면적 큰 사진 우선
        if any(k in p.lower() for k in ("logo", "mast", "icon", "brand", "banner")):
            score *= 0.2                        # 파일명이 로고류면 감점
        if score > best_score:
            best_score, best = score, p
    return best


def _caption_chunks(script, dur, start=0.5, end_pad=0.3, maxlen=11):
    """대본을 짧은 자막 조각으로 나눠 길이에 균등 배분(근사 싱크)."""
    words = []
    for w in script.replace(",", " ").split():
        # 띄어쓰기 없는 긴 낱말(고유명사·숫자)은 그대로 두면 한 줄이 프레임을 넘는다 → 강제 줄바꿈.
        words += [w[i:i + maxlen] for i in range(0, len(w), maxlen)] if len(w) > maxlen else [w]
    chunks, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= maxlen:
            cur = (cur + " " + w).strip()
        else:
            if cur:
                chunks.append(cur)
            cur = w
    if cur:
        chunks.append(cur)
    total = sum(len(c) for c in chunks) or 1
    span = max(dur - start - end_pad, 1.0)
    acc, out = 0, []
    for c in chunks:
        t0 = start + span * acc / total
        acc += len(c)
        t1 = start + span * acc / total
        out.append((t0, t1, c))
    return out


def compose_news_layout(video_in, out, title, ots_image=None, script=None, dur=None,
                        dept=None, kicker="세명대 재난안전 뉴스", mascot=True):
    """아나운서 영상에 상단 제목바 + (선택)우측 관련화면 + (선택)하단 자막 + 좌하단 캐릭터 합성.

    좌표는 720x1280 기준으로 잡되, 실제 입력 영상 폭에 맞춰 배율 환산한다.
    (HeyGen 이 플랜에 따라 요청한 1080x1920 대신 720p 로 내려주는 경우가 있어,
     모듈 상수 W 가 아니라 받은 영상의 실제 크기를 기준으로 삼는다.)

    확정 디자인(2026-08):
      · 상단: 풀폭 네이비바(@0.92)+빨간 띠. 킥커(노랑)+헤드라인(흰) 중앙·하단정렬.
      · 우측: 4:3 관련화면(라벨 없음, 남색 테두리).
      · 하단: 자막을 명패 바로 위(y=h-462, 네이비 칩).
      · 좌하단: SMU 캐릭터(118px)를 명패 높이에 맞춰 왼쪽 정렬.
    새 아바타에는 '세명대학교 재난안전학과' 명패가 이미 찍혀 있어 dept 텍스트는 기본 미표시.
    """
    import subprocess
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    fnt = _font()
    vw, vh = _img_size(video_in)
    s = (vw / LAYOUT_W) if vw else 1.0

    def px(v):
        return int(round(v * s))

    # ---- 상단 제목바: 풀폭 네이비 + 빨간 띠, 킥커+헤드라인 중앙·하단정렬 ----
    head_txt, head_sz = _fit_text(_esc(title), px(50), px(640), min_size=px(32))
    title_f = (
        f"drawbox=x=0:y=0:w=iw:h={px(196)}:color=0x0B1C3A@0.92:t=fill,"
        f"drawbox=x=0:y={px(196)}:w=iw:h={px(7)}:color=0xE63946:t=fill,"
        f"drawtext=fontfile='{fnt}':text='{_esc(kicker)}':fontcolor=0xFFD24A:"
        f"fontsize={px(30)}:x=(w-text_w)/2:y={px(90)},"
        f"drawtext=fontfile='{fnt}':text='{head_txt}':fontcolor=white:"
        f"fontsize={head_sz}:x=(w-text_w)/2:y={px(130)}")
    # ---- 우측 관련화면 4:3(라벨 없음, 남색 테두리) ----
    ots_border = (f"drawbox=x={px(423)}:y={px(283)}:w={px(274)}:h={px(207)}:"
                  f"color=0x0B1C3A:t={px(5)}")
    # ---- 하단 자막: 명패 바로 위(네이비 칩), 인스타/쇼츠 UI 위 안전영역 ----
    caps = ""
    if script and dur:
        chunks = _caption_chunks(script, dur)
        cap_sz, cap_max_w = px(52), px(480)   # 우측 관련화면·버튼에 닿지 않게 공통 크기 산정
        widest = max((_text_width(c, cap_sz) for _, _, c in chunks), default=0)
        if widest > cap_max_w:
            cap_sz = max(px(38), int(cap_sz * cap_max_w / widest) // 2 * 2)
        for t0, t1, c in chunks:
            caps += (f",drawtext=fontfile='{fnt}':text='{_esc(c)}':fontcolor=white:fontsize={cap_sz}:"
                     f"borderw={px(4)}:bordercolor=black:box=1:boxcolor=0x0B1C3A@0.82:"
                     f"boxborderw={px(16)}:x=(w-text_w)/2:y=h-{px(462)}:"
                     f"enable='between(t,{t0:.2f},{t1:.2f})'")
    # ---- (선택) 명패 텍스트 — 새 아바타는 명패가 찍혀 있어 기본 미표시 ----
    # 채널 명패 — 아바타 책상면에 채널 이름을 얹는다(GeoAI 채널처럼 사진에 명패가 없는
    # 아바타용). 좌표는 2026-09-16 에 실제 렌더 화면에서 맞췄다: 자막(y=h-462)보다
    # 아래, 책상 상단선(1080폭 기준 y≈1470)보다 살짝 아래에 놓아 책상에 놓인 것처럼 보이게.
    dept_f = ""
    if dept:
        dept_f = (f",drawbox=x={px(150)}:y={px(1000)}:w={px(420)}:h={px(78)}:"
                  f"color=0x0B1C3A@1.0:t=fill"
                  f",drawtext=fontfile='{fnt}':text='{_esc(dept)}':fontcolor=white:"
                  f"fontsize={px(40)}:x=(w-text_w)/2:y={px(1015)}")

    # ---- 입력·필터 그래프 구성(관련화면·캐릭터는 있을 때만 오버레이) ----
    inputs = ["-i", video_in]
    scale_defs, overlays = [], []
    label, nxt = "0:v", 1
    ots_ok = bool(ots_image and os.path.exists(ots_image))
    if ots_ok:
        inputs += ["-i", ots_image]
        scale_defs.append(f"[{nxt}:v]scale={px(268)}:{px(201)}:"
                          f"force_original_aspect_ratio=increase,crop={px(268)}:{px(201)},setsar=1[ots]")
        overlays.append(f"[{label}][ots]overlay={px(426)}:{px(286)}[v{nxt}]")
        label = f"v{nxt}"; nxt += 1
    # 캐릭터는 학과 채널 브랜딩이라, 다른 채널(GeoAI)에서는 끈다(mascot=False).
    mascot_png = os.path.join(BASE_DIR, "legal", "mascot.png")
    if mascot and os.path.exists(mascot_png):
        inputs += ["-i", mascot_png]
        scale_defs.append(f"[{nxt}:v]scale={px(118)}:{px(118)}[mas]")
        overlays.append(f"[{label}][mas]overlay={px(10)}:{px(882)}[v{nxt}]")
        label = f"v{nxt}"; nxt += 1
    draw = title_f + ("," + ots_border if ots_ok else "") + caps + dept_f
    segs = scale_defs + overlays + [f"[{label}]{draw}[out]"]
    fc = ";".join(segs)
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", *inputs,
                    "-filter_complex", fc, "-map", "[out]", "-map", "0:a",
                    "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", out], check=True)
    return out


def make_news_anchor(data, title=None, heygen_video_id=None):
    """뉴스 data → 아나운서 영상 + 제목 + 우측 관련화면 + 자막 → data['video'] 세팅.

    실패하면 예외를 올린다(호출부에서 카드 영상으로 폴백)."""
    tp = load_config().get("heygen", {}).get("talking_photo_id")
    if not tp:
        raise RuntimeError("config.heygen.talking_photo_id 가 없습니다(아바타 미설정).")
    scenes = data.get("scenes", [])
    script = " ".join(s.get("narration", "").strip() for s in scenes if s.get("narration"))
    if not script.strip():
        raise RuntimeError("나레이션이 비어 아나운서 대본을 만들 수 없습니다.")
    headline = title or (scenes[0].get("heading") if scenes else "재난안전 뉴스")
    # 우측 관련화면용 기사 이미지(best-effort)
    ots = None
    try:
        from fetch_images import fetch_images
        fetch_images(data)
        imgs = [p for p in (data.get("source_images") or {}).values() if p and os.path.exists(p)]
        ots = _pick_ots_image(imgs)            # 로고 제외·사진 우선(없으면 None→박스 생략)
        log(f"관련화면 이미지: {'선택 '+os.path.basename(ots) if ots else '적합 사진 없음 → 생략'}")
    except Exception as e:
        log(f"관련화면 이미지 수집 건너뜀: {type(e).__name__}")
    if heygen_video_id:                           # 앞서 요청해 둔 영상을 이어받는다
        log(f"기존 HeyGen 영상 이어받기: {heygen_video_id}")
        r = await_video(heygen_video_id)
    else:
        log(f"아나운서 영상 생성 시작(대본 {len(script)}자)...")
        r = generate(tp, script)                  # HeyGen 생성 + 다운로드
    dur = _duration(r["path"])
    stamp = data.get("stamp") or "anchor"
    out = os.path.join(POSTS_DIR, f"short_{stamp}.mp4")
    # 킥커(상단 띠 문구)와 캐릭터는 채널마다 다르다 — 에디션 설정으로 덮어쓴다.
    hc = load_config().get("heygen", {})
    compose_news_layout(r["path"], out, headline, ots_image=ots, script=script, dur=dur,
                        kicker=hc.get("kicker", "세명대 재난안전 뉴스"),
                        mascot=hc.get("mascot", True), dept=hc.get("dept"))
    try:                                       # 후킹(초반)·CTA(후반) 오버레이(완주율·구독 전환↑)
        from overlays import apply as apply_overlays
        apply_overlays(out, dur=dur)           # out 제자리 교체
    except Exception as e:
        log(f"오버레이 건너뜀(영상은 정상): {type(e).__name__}: {e}")
    data["video"] = out
    data["video_seconds"] = round(dur, 1)
    data["ai_disclosure"] = True             # 합성 아나운서 → 유튜브 AI 고지 자동 삽입

    log(f"아나운서 뉴스 영상 완성(제목+관련화면+자막): {out}")
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "voices":
        list_korean_voices()
    elif a[0] == "photo":
        print("talking_photo_id:", upload_photo(a[1]))
    elif a[0] == "gen":
        print(json.dumps(generate(a[1], a[2]), ensure_ascii=False))
    elif a[0] == "title":                          # title <video> <제목>
        print(add_title(a[1], a[2], a[1].replace(".mp4", "_titled.mp4")))
    else:
        print(__doc__)
