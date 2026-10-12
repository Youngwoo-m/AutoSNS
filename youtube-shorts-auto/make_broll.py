"""B롤 클립을 로컬에서 만든다(생성 모델 없이 캔버스 + ffmpeg).

숏폼 장면 배경으로 쓸 세로 클립을 그린다. 색·폰트·구도를 완전히 통제할 수 있고
비용이 들지 않는다. 실사는 못 만들지만 재난안전 콘텐츠에서는 도해풍이 오히려
안전하다(VEO_PROMPTS.md 참고).

방식: 장면마다 draw(t) 를 두고 t(0~1)를 일정 간격으로 올리며 캡처한 뒤 ffmpeg 로
잇는다. CSS 애니메이션을 벽시계로 찍으면 프레임 간격이 흔들려서 t 를 직접 먹인다.
t=0 과 t=1 의 그림이 같아야 반복 재생이 끊기지 않는다 — 모든 움직임을
sin(t*TAU) 처럼 주기가 1인 함수로 쓰거나 % 로 감는다.

상단 40%는 비워 둔다(자막·소제목 자리). 아래쪽에 정보를 몰아 둔다.

사용:  ./.venv/bin/python make_broll.py flood
       ./.venv/bin/python make_broll.py --all
       ./.venv/bin/python make_broll.py quake --seconds 6 --fps 30
"""
import argparse
import os
import shutil
import subprocess
import time

import imageio_ffmpeg
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from common import POSTS_DIR, log

W, H = 1080, 1920

COMMON = """
const TAU = Math.PI * 2;
function bg(g0, g1) {
  const g = X.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0, g0); g.addColorStop(1, g1);
  X.fillStyle = g; X.fillRect(0, 0, W, H);
}
function vign() {
  const g = X.createRadialGradient(W/2, H*0.45, W*0.30, W/2, H*0.45, H*0.72);
  g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(1, 'rgba(0,0,0,.55)');
  X.fillStyle = g; X.fillRect(0, 0, W, H);
}
function glow(x, y, r, col, a) {
  const g = X.createRadialGradient(x, y, 0, x, y, r);
  g.addColorStop(0, `rgba(${col},${a})`); g.addColorStop(1, `rgba(${col},0)`);
  X.fillStyle = g; X.beginPath(); X.arc(x, y, r, 0, TAU); X.fill();
}
function rnd(seed) {
  let s = seed;
  return () => (s = (s * 1664525 + 1013904223) % 4294967296) / 4294967296;
}
// 도시 스카이라인(아래쪽에만). depth 가 클수록 멀고 흐리다.
function skyline(seed, baseY, hMax, col, alpha) {
  const r = rnd(seed);
  X.fillStyle = `rgba(${col},${alpha})`;
  let x = -80;
  while (x < W + 80) {
    const w = 70 + r() * 110, h = 90 + r() * hMax;
    X.fillRect(x, baseY - h, w, h);
    x += w + 26 + r() * 40;
  }
}
"""

# ── 장면들 ──────────────────────────────────────────────────────────────

FLOOD = """
const drops = [];
{ const r = rnd(7);
  for (let i=0;i<460;i++) drops.push({x:r()*W, y:r()*H, len:26+r()*54,
                                      sp:.9+r()*.9, a:.10+r()*.28}); }
window.draw = function (t) {
  bg('#111728', '#1d2947');
  skyline(3, H*0.78, 300, '51,74,142', .40);
  skyline(11, H*0.80, 220, '16,22,40', .92);
  glow(W*0.74, H*0.70, 300, '255,165,0', .30);          // 가로등
  for (const d of drops) {                               // 빗줄기
    const y = (d.y + t*H*2.2*d.sp) % (H+120) - 60;
    X.strokeStyle = `rgba(200,220,255,${d.a})`;
    X.lineWidth = 2; X.lineCap='round';
    X.beginPath(); X.moveTo(d.x,y); X.lineTo(d.x-9,y+d.len); X.stroke();
  }
  const rise = 26 * (1 - Math.cos(t*TAU)) / 2;           // 수위
  const wy = H - 400 - rise;
  const g = X.createLinearGradient(0, wy, 0, H);
  g.addColorStop(0,'rgba(51,74,142,.88)'); g.addColorStop(1,'#0c1220');
  X.fillStyle = g; X.fillRect(0, wy, W, H-wy);
  for (let l=0;l<3;l++) {                                // 수면 물결
    X.beginPath();
    const amp=7-l*2, off=wy+l*24, sp=1+l*.6;
    for (let x=0;x<=W;x+=6) {
      const y = off + amp*Math.sin(x/110 + t*TAU*sp);
      x===0 ? X.moveTo(x,y) : X.lineTo(x,y);
    }
    X.strokeStyle=`rgba(255,165,0,${.20-l*.05})`; X.lineWidth=3; X.stroke();
  }
  vign();
};
"""

WILDFIRE = """
const puffs = [];
{ const r = rnd(21);
  for (let i=0;i<60;i++) puffs.push({p:r(), x:W*0.60+r()*180-90,
                                     rad:60+r()*130, sp:.6+r()*.7, a:.05+r()*.10}); }
window.draw = function (t) {
  bg('#1a1424', '#2b1f2a');
  glow(W*0.66, H*0.70, 520, '255,120,40', .22);          // 능선 너머 불빛
  for (const p of puffs) {                               // 피어오르는 연기
    const u = (p.p + t*p.sp) % 1;
    const y = H*0.72 - u*H*0.55;
    const rad = p.rad * (0.5 + u*1.5);
    const a = p.a * (1-u) * 1.4;
    glow(p.x + Math.sin(u*4+p.p*9)*70, y, rad, '190,175,185', a);
  }
  X.fillStyle = '#0f0b14';                               // 앞 능선
  X.beginPath(); X.moveTo(0,H);
  for (let x=0;x<=W;x+=10) {
    const y = H*0.76 + Math.sin(x/240)*70 + Math.sin(x/70)*18;
    X.lineTo(x,y);
  }
  X.lineTo(W,H); X.closePath(); X.fill();
  glow(W*0.66, H*0.74, 180, '255,90,20', .34 + .10*Math.sin(t*TAU));
  vign();
};
"""

QUAKE = """
window.draw = function (t) {
  const sh = Math.sin(t*TAU*6) * 7;                      // 미세 진동
  X.save(); X.translate(sh, Math.cos(t*TAU*5)*5);
  bg('#141726', '#242a3f');
  skyline(5, H*0.80, 320, '51,74,142', .34);
  skyline(17, H*0.82, 240, '15,19,32', .95);
  X.restore();
  const cx = W*0.5, cy = H*0.80;                         // 동심원 파동
  for (let i=0;i<4;i++) {
    const u = (t + i/4) % 1;
    X.strokeStyle = `rgba(255,165,0,${(1-u)*0.42})`;
    X.lineWidth = 6*(1-u)+1;
    X.beginPath(); X.ellipse(cx, cy, u*W*0.95, u*W*0.34, 0, 0, TAU); X.stroke();
  }
  glow(cx, cy, 240, '255,165,0', .16);
  vign();
};
"""

SATELLITE = """
window.draw = function (t) {
  bg('#0b1020', '#16203a');
  X.strokeStyle = 'rgba(51,74,142,.55)'; X.lineWidth = 2;   // 지표 격자(원근)
  for (let i=0;i<=14;i++) {
    const u = i/14, y = H*0.52 + Math.pow(u,2.1)*H*0.50;
    X.beginPath(); X.moveTo(0,y); X.lineTo(W,y); X.stroke();
  }
  for (let i=-7;i<=7;i++) {
    X.beginPath(); X.moveTo(W/2 + i*26, H*0.52);
    X.lineTo(W/2 + i*200, H); X.stroke();
  }
  const sy = H*0.52 + ((t*1.0)%1)*H*0.48;                   // 스캔선
  const g = X.createLinearGradient(0, sy-90, 0, sy+14);
  g.addColorStop(0,'rgba(255,165,0,0)'); g.addColorStop(1,'rgba(255,165,0,.55)');
  X.fillStyle = g; X.fillRect(0, sy-90, W, 104);
  X.strokeStyle='rgba(255,210,140,.95)'; X.lineWidth=4;
  X.beginPath(); X.moveTo(0,sy); X.lineTo(W,sy); X.stroke();
  const r = rnd(33);                                        // 탐지된 셀
  for (let i=0;i<9;i++) {
    const cy2 = H*0.56 + r()*H*0.40, cx2 = r()*W;
    const on = Math.abs(cy2 - sy) < 150 ? 1 : .18;
    X.fillStyle = `rgba(255,165,0,${0.10+0.35*on})`;
    X.fillRect(cx2-34, cy2-16, 68, 32);
  }
  glow(W*0.5, H*0.28, 360, '120,160,255', .10);
  vign();
};
"""

HEAT = """
window.draw = function (t) {
  bg('#2a2118', '#6b4a22');
  glow(W*0.5, H*0.30, 460, '255,210,120', .40 + .05*Math.sin(t*TAU)); // 태양
  X.fillStyle = '#20180f';                                   // 아스팔트
  X.fillRect(0, H*0.70, W, H*0.30);
  for (let i=0;i<9;i++) {                                    // 중앙선
    const y = H*0.74 + i*62;
    X.fillStyle='rgba(255,200,120,.30)'; X.fillRect(W/2-14, y, 28, 34);
  }
  for (let l=0;l<22;l++) {                                   // 아지랑이
    const y = H*0.62 + l*14;
    const off = Math.sin(t*TAU*2 + l*0.9)*10;
    X.fillStyle = `rgba(255,220,170,${0.05 - l*0.002})`;
    X.fillRect(off, y, W, 7);
  }
  vign();
};
"""

SNOW = """
const flakes = [];
{ const r = rnd(91);
  for (let i=0;i<300;i++) flakes.push({x:r()*W, y:r()*H, rad:2+r()*6,
                                       sp:.25+r()*.5, dr:r()*TAU, a:.30+r()*.55}); }
window.draw = function (t) {
  bg('#1c2231', '#39445c');
  skyline(13, H*0.82, 260, '70,84,112', .45);
  // 쌓인 눈. 흰색을 그대로 깔면 아래쪽 흰 글자(푸터·학과명)가 묻힌다.
  // 푸른 회색으로 낮추고 아래로 갈수록 어둡게 해서 글자 자리를 확보한다.
  { const g = X.createLinearGradient(0, H*0.82, 0, H);
    g.addColorStop(0, '#b9c6da'); g.addColorStop(1, '#4a5670');
    X.fillStyle = g; }
  X.beginPath(); X.moveTo(0,H);
  for (let x=0;x<=W;x+=12) X.lineTo(x, H*0.88 + Math.sin(x/160)*12);
  X.lineTo(W,H); X.closePath(); X.fill();
  for (const f of flakes) {                                  // 눈발
    const y = (f.y + t*H*f.sp) % (H+40) - 20;
    const x = f.x + Math.sin(t*TAU + f.dr)*26;
    X.fillStyle = `rgba(255,255,255,${f.a})`;
    X.beginPath(); X.arc(x, y, f.rad, 0, TAU); X.fill();
  }
  vign();
};
"""

DAWN = """
window.draw = function (t) {
  bg('#0e1730', '#25355c');
  const k = (1 - Math.cos(t*TAU))/2;
  glow(W*0.30, H*0.66, 520, '255,165,0', .16 + .08*k);       // 지평선 여명
  skyline(2, H*0.74, 300, '51,74,142', .30);
  skyline(23, H*0.78, 240, '11,16,30', .92);
  X.fillStyle = 'rgba(255,165,0,.55)';                       // 바닥 라인
  X.fillRect(0, H*0.885, W, 5);
  const r = rnd(44);                                         // 창문 불빛
  for (let i=0;i<40;i++) {
    const x = r()*W, y = H*0.60 + r()*H*0.24;
    const a = 0.10 + 0.22*Math.abs(Math.sin(t*TAU + i));
    X.fillStyle = `rgba(255,200,120,${a})`; X.fillRect(x, y, 7, 11);
  }
  vign();
};
"""

SCENES = {
    "flood":     ("집중호우 도시 침수", FLOOD),
    "wildfire":  ("산불 연기",          WILDFIRE),
    "quake":     ("지진 진동·파동",      QUAKE),
    "satellite": ("위성 스캔(GeoAI)",   SATELLITE),
    "heat":      ("폭염 아지랑이",       HEAT),
    "snow":      ("대설·한파",           SNOW),
    "dawn":      ("새벽 도시(마무리)",    DAWN),
}


def _html(scene_js):
    return (
        "<!doctype html><html><head><meta charset='utf-8'><style>"
        "*{margin:0;padding:0}body{background:#000}"
        f"#c{{display:block;width:{W}px;height:{H}px}}</style></head><body>"
        f"<canvas id='c' width='{W}' height='{H}'></canvas><script>"
        f"const W={W},H={H};const X=document.getElementById('c').getContext('2d');"
        f"{COMMON}{scene_js}</script></body></html>")


def render(name, seconds=8.0, fps=24):
    label, js = SCENES[name]
    work = os.path.join(POSTS_DIR, f"_broll_{name}")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    page = os.path.join(work, "scene.html")
    with open(page, "w", encoding="utf-8") as f:
        f.write(_html(js))

    n = int(round(seconds * fps))
    o = Options()
    o.add_argument("--headless=new")
    o.add_argument(f"--window-size={W+60},{H+120}")
    o.add_argument("--hide-scrollbars")
    o.add_argument("--force-device-scale-factor=1")
    # 크롬이 실행마다 앱 전체(~1.4GB)를 임시 폴더에 복제하고 남기는 것을 막는다(2026-10-09)
    o.add_argument("--disable-features=MacAppCodeSignClone")
    d = webdriver.Chrome(options=o)
    try:
        # 뷰포트를 정확히 1080x1920 으로 고정한다. 창 크기만 키우면 크롬이 여백만큼
        # 잘라 1080x1897 이 나오고 libx264 가 "height not divisible by 2" 로 죽는다.
        d.execute_cdp_cmd("Emulation.setDeviceMetricsOverride",
                          {"width": W, "height": H, "deviceScaleFactor": 1,
                           "mobile": False})
        d.get("file:///" + page.replace("\\", "/"))
        time.sleep(0.8)
        el = d.find_element(By.ID, "c")
        for i in range(n):
            d.execute_script("window.draw(arguments[0]);", i / n)
            el.screenshot(os.path.join(work, f"{i:04d}.png"))
    finally:
        d.quit()

    out_dir = os.path.join(POSTS_DIR, "broll")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{name}.mp4")
    subprocess.run([
        imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
        "-framerate", str(fps), "-i", os.path.join(work, "%04d.png"),
        # 필름 그레인 — 평평한 벡터 그림에 질감을 준다
        "-vf", f"scale={W}:{H},noise=alls=6:allf=t+u,format=yuv420p",
        "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-r", str(fps),
        out,
    ], check=True)
    shutil.rmtree(work, ignore_errors=True)
    log(f"[{label}] {out} ({seconds}s, {fps}fps, {os.path.getsize(out)//1000}KB)")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("scene", nargs="?", choices=sorted(SCENES))
    ap.add_argument("--all", action="store_true", help="모든 장면을 한 번에")
    ap.add_argument("--seconds", type=float, default=8.0)
    ap.add_argument("--fps", type=int, default=24)
    a = ap.parse_args()
    if not a.all and not a.scene:
        raise SystemExit("장면 이름이나 --all 을 주세요: " + ", ".join(sorted(SCENES)))
    for nm in (sorted(SCENES) if a.all else [a.scene]):
        print(render(nm, a.seconds, a.fps))
