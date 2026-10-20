"""가로 아바타를 세로 쇼츠 가운데 띠로 넣는 화면(2026-09-29 확정 시안).

HeyGen 토킹포토가 가로(16:9) 사진이라, 세로 화면에 억지로 채우면 창밖 풍경이
잘리고 인물만 남는다. 그래서 가로 장면을 통째로 가운데 띠에 두고 위·아래를
디자인으로 채운다.

  위   킥커·날짜 + 헤드라인(장면 바로 위에 붙는다 — 제목 길이와 상관없이)
  가운데 가로 장면(HeyGen 영상, 모서리 둥글게)
  아래  명패 + AI 고지 한 줄, 그 아래 자막
  맨 아래 비움 — 유튜브 제목·채널·구독 UI 가 덮는 자리

채널마다 테마만 다르다(heygen.band.theme):
  dept     학과 @smds2023      뉴스형 — 네이비·빨강·노랑
  personal 개인 @geoai-safety  종이+네이비 2단 — 아래를 어둡게 해 유튜브 흰 UI 가 보이게

만드는 방법: 정지 틀(배경·제목·명패·고지)과 자막 조각은 크롬으로 PNG 를 굽고
(글꼴·줄바꿈·형광펜을 시안 그대로 내려고), ffmpeg 로 가운데에 영상을 둥근 마스크로
얹은 뒤 자막 PNG 를 시간대별로 겹친다.
"""
import html
import os
import subprocess
import sys
import time

from common import POSTS_DIR, log

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from shared.fonts import default_font_dir, require_fonts  # noqa: E402

W, H = 1080, 1920
# 장면 자리 — 영상이 실제로 놓이는 안쪽 사각형(x, y, w, h, 모서리 반경).
# personal 은 10px 흰 테두리 안쪽에 들어간다.
SCENES = {
    "dept": (24, 640, 1032, 580, 26),
    "personal": (34, 650, 1012, 560, 12),
}
CAP_X, CAP_Y, CAP_W = 64, 1322, 840
# 오버레이(후킹·구독 유도) 자리 — 1920 기준 px. 헤드라인·장면·자막을 가리지 않게 옮긴다.
#   후킹: 킥커 위 빈 곳(헤드라인 두 줄까지 겹치지 않음)
#   구독: 끝 3초 남짓 헤드라인 자리(240~620)를 네이비 판으로 덮고 그 위에 — 장면·자막은 그대로 보인다
OVERLAY_Y = {"hook_y": 235, "cta_y": 340, "cta_panel": (236, 386)}

_FONT_CSS = """
@font-face{{font-family:K;font-weight:300;src:url("file://{d}/KoPubWorld Dotum_Pro Light.otf")}}
@font-face{{font-family:K;font-weight:500;src:url("file://{d}/KoPubWorld Dotum_Pro Medium.otf")}}
@font-face{{font-family:K;font-weight:700;src:url("file://{d}/KoPubWorld Dotum_Pro Bold.otf")}}
"""

_BASE = """
*{box-sizing:border-box;margin:0}
body{width:1080px;height:1920px;overflow:hidden;font-family:K,sans-serif;position:relative}
.top{position:absolute;left:64px;right:64px;top:240px;height:360px;display:flex;flex-direction:column;
  justify-content:flex-end}
.kick{align-self:flex-start;display:inline-flex;align-items:center;gap:14px;font-weight:700;font-size:34px;
  letter-spacing:1px}
.kick i{width:12px;height:34px;border-radius:3px}
.date{font-weight:500;font-size:30px;margin-left:10px}
h1{margin-top:26px;font-weight:700;font-size:74px;line-height:1.22;letter-spacing:-1.5px;
  word-break:keep-all;text-wrap:balance}
.scene{position:absolute;left:24px;top:640px;width:1032px;height:580px;border-radius:26px;overflow:hidden}
.row{position:absolute;left:64px;right:150px;top:1246px;display:flex;align-items:center;gap:20px}
.name{display:flex;border-radius:10px;overflow:hidden;flex:none}
.name b,.name span{padding:9px 15px;font-size:25px}
.name b{font-weight:700} .name span{font-weight:500}
.disc{font-size:23px;font-weight:300}
"""

_THEME = {
    "dept": """
body{color:#fff;background:radial-gradient(120% 60% at 50% 0%,#15305e 0%,#0B1C3A 62%),#0B1C3A}
body:before{content:"";position:absolute;inset:0;opacity:.07;background-size:60px 60px;
  background-image:linear-gradient(#fff 1px,transparent 1px),linear-gradient(90deg,#fff 1px,transparent 1px)}
.kick{color:#FFD24A} .kick i{background:#E63946} .date{color:#fff;opacity:.65}
.scene{background:#0B1C3A;box-shadow:0 18px 50px rgba(0,0,0,.45);border:2px solid rgba(255,255,255,.14)}
.bar{position:absolute;left:24px;top:624px;width:180px;height:8px;border-radius:4px;background:#E63946}
.name b{background:#E63946;color:#fff} .name span{background:#fff;color:#0B1C3A}
.disc{color:#fff;opacity:.7}
""",
    "personal": """
body{color:#0b1c3a;background:#F3EFE6}
body:before{content:"";position:absolute;inset:0;opacity:.10;background-size:36px 36px;
  background-image:radial-gradient(#0b1c3a 1.4px,transparent 1.6px)}
.low{position:absolute;left:0;right:0;top:930px;bottom:0;background:linear-gradient(180deg,#0b1c3a 0%,#0e2a4a 100%)}
.kick{color:#0E7C86} .kick i{background:#0E7C86} .date{color:#0b1c3a;opacity:.55}
.scene{background:#fff;border:10px solid #fff;border-radius:22px;box-shadow:0 22px 50px rgba(11,28,58,.35)}
.name b{background:#0E7C86;color:#fff} .name span{background:#F3EFE6;color:#0b1c3a}
.disc{color:#fff;opacity:.7}
""",
}

# 자막 조각 — 투명 바탕에 한 조각씩 굽는다
_CAP = {
    "dept": ".cap{color:#fff;text-shadow:0 3px 12px rgba(0,0,0,.5)} .cap em{color:#FFD24A}",
    "personal": (".cap{color:#fff} .cap em{color:#0b1c3a;background:linear-gradient(transparent 12%,"
                 "#FFE08A 12%,#FFE08A 92%,transparent 92%);padding:0 6px;border-radius:4px}"),
}
_CAP_BASE = """
*{box-sizing:border-box;margin:0} html,body{background:transparent}
.cap{width:%dpx;font-family:K,sans-serif;font-weight:700;font-size:56px;line-height:1.32;letter-spacing:-.5px;
  word-break:keep-all;text-wrap:balance;padding:6px 0 14px}
.cap em{font-style:normal;white-space:nowrap}
""" % CAP_W


def is_band(hc):
    """이 채널이 가운데 띠 화면을 쓰는가(heygen.layout == 'band')."""
    return (hc or {}).get("layout") == "band"


def dimension(hc):
    """HeyGen 에 요청할 영상 크기 — 띠 화면이면 가로 1920x1080(사진 그대로)."""
    return {"width": 1920, "height": 1080} if is_band(hc) else None


def _theme(hc):
    t = ((hc or {}).get("band") or {}).get("theme", "dept")
    if t not in SCENES:
        raise RuntimeError(f"모르는 띠 화면 테마: {t} (가능: {', '.join(SCENES)})")
    return t


def _font_css():
    here = os.path.dirname(os.path.abspath(__file__))
    return _FONT_CSS.format(d=require_fonts(default_font_dir(here)))


def render_frame(hc, headline, kicker, date_label, out_png):
    """정지 틀(배경·킥커·헤드라인·장면 테두리·명패·고지)을 1080x1920 PNG 로 굽는다."""
    from selenium.webdriver.common.by import By
    theme = _theme(hc)
    band = (hc or {}).get("band") or {}
    esc = html.escape
    extra = '<div class="bar"></div>' if theme == "dept" else '<div class="low"></div>'
    # 화면 고지는 한 줄에 들어가는 짧은 문구 — 설명란용 disclosure_text_short 는 길어서 두 줄이 된다
    disc = band.get("disclosure") or "※ AI로 자동 생성한 아바타 영상입니다."
    page = (f'<!doctype html><html><head><meta charset="utf-8"><style>{_font_css()}{_BASE}'
            f'{_THEME[theme]}</style></head><body>{extra}'
            f'<div class="top"><div class="kick"><i></i>{esc(kicker)}'
            f'<span class="date">{esc(date_label)}</span></div><h1>{esc(headline)}</h1></div>'
            f'<div class="scene"></div>'
            f'<div class="row"><div class="name"><b>{esc(band.get("name_main", ""))}</b>'
            f'<span>{esc(band.get("name_sub", ""))}</span></div>'
            f'<div class="disc">{esc(disc)}</div></div></body></html>')
    tmp = out_png + ".html"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(page)
    d = _start((W, H))
    try:
        d.get("file://" + tmp)
        time.sleep(1.0)
        d.find_element(By.TAG_NAME, "body").screenshot(out_png)
    finally:
        d.quit()
        os.remove(tmp)
    return out_png


def render_captions(hc, chunks, out_dir):
    """자막 조각마다 투명 PNG 를 굽는다 → [(t0, t1, png)]. 크롬 한 번으로 모두 굽는다."""
    from selenium.webdriver.common.by import By
    theme = _theme(hc)
    os.makedirs(out_dir, exist_ok=True)
    tmp = os.path.join(out_dir, "_cap.html")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(f'<!doctype html><html><head><meta charset="utf-8"><style>{_font_css()}{_CAP_BASE}'
                f'{_CAP[theme]}</style></head><body><div class="cap" id="c"></div></body></html>')
    d = _start((CAP_W + 40, 400))
    out = []
    try:
        # 바탕을 투명으로 — 자막 조각만 영상 위에 얹기 위해
        d.execute_cdp_cmd("Emulation.setDefaultBackgroundColorOverride",
                          {"color": {"r": 0, "g": 0, "b": 0, "a": 0}})
        d.get("file://" + tmp)
        time.sleep(0.8)
        el = d.find_element(By.ID, "c")
        for i, (t0, t1, text) in enumerate(chunks):
            d.execute_script("arguments[0].textContent = arguments[1];", el, text)
            time.sleep(0.05)
            p = os.path.join(out_dir, f"cap_{i:03d}.png")
            el.screenshot(p)
            out.append((t0, t1, p))
    finally:
        d.quit()
        os.remove(tmp)
    return out


def _start(size):
    """render_frames.py 와 같은 방식으로 크롬을 띄우고, 안쪽 크기를 정확히 size 로 맞춘다."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    o = Options()
    o.add_argument("--headless=new")
    o.add_argument(f"--window-size={size[0]},{size[1]}")
    o.add_argument("--hide-scrollbars")
    o.add_argument("--allow-file-access-from-files")
    o.add_argument("--lang=ko-KR")
    o.add_argument("--force-device-scale-factor=1")
    # 크롬이 실행마다 앱 전체(~1.4GB)를 임시 폴더에 복제하고 남기는 것을 막는다(2026-10-09)
    o.add_argument("--disable-features=MacAppCodeSignClone")
    d = webdriver.Chrome(options=o)
    try:                                   # 창 테두리만큼 늘려 안쪽이 size 가 되게
        dh = d.execute_script("return window.outerHeight - window.innerHeight") or 0
        d.set_window_size(size[0], size[1] + dh)
    except Exception:
        pass
    return d


def _mask(w, h, r, out_png):
    """둥근 사각 마스크(흰=보임) — 영상 모서리를 틀과 같게 깎는다."""
    from PIL import Image, ImageDraw
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    m.save(out_png)
    return out_png


def compose(hc, video_in, out, headline, kicker, date_label, script_chunks, dur):
    """틀 + 가운데 영상 + 자막을 합쳐 1080x1920 쇼츠를 만든다."""
    theme = _theme(hc)
    x, y, w, h, r = SCENES[theme]
    work = os.path.join(POSTS_DIR, f"_band_{int(time.time())}")
    os.makedirs(work, exist_ok=True)
    frame = render_frame(hc, headline, kicker, date_label, os.path.join(work, "frame.png"))
    mask = _mask(w, h, r, os.path.join(work, "mask.png"))
    caps = render_captions(hc, script_chunks or [], work) if script_chunks else []

    inputs = ["-loop", "1", "-i", frame, "-i", video_in, "-loop", "1", "-i", mask]
    for _, _, p in caps:
        inputs += ["-i", p]
    f = [f"[1:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,format=rgba[v]",
         "[2:v]format=gray[m]",
         "[v][m]alphamerge[vr]",
         f"[0:v][vr]overlay={x}:{y}:shortest=1[b0]"]
    last = "b0"
    for i, (t0, t1, _) in enumerate(caps):
        nxt = f"b{i + 1}"
        f.append(f"[{last}][{i + 3}:v]overlay={CAP_X}:{CAP_Y}:enable='between(t,{t0:.2f},{t1:.2f})'[{nxt}]")
        last = nxt
    f.append(f"[{last}]format=yuv420p[out]")
    import imageio_ffmpeg                 # 다른 합성과 같은 ffmpeg(launchd PATH 에 없을 수 있다)
    cmd = ([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error"] + inputs +
           ["-filter_complex", ";".join(f), "-map", "[out]", "-map", "1:a?",
            "-t", f"{dur:.2f}", "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out])
    subprocess.run(cmd, check=True)
    log(f"띠 화면 합성: {out} ({theme}, 자막 {len(caps)}조각)")
    try:                                    # 중간 파일 정리(실패해도 영상은 정상)
        for n in os.listdir(work):
            os.remove(os.path.join(work, n))
        os.rmdir(work)
    except Exception:
        pass
    return out
