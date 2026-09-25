"""B롤 클립을 로컬에서 만든다(생성 모델 없이 HTML/CSS + ffmpeg).

숏폼 장면 배경으로 쓸 8초짜리 세로 클립을 그린다. 생성 모델과 달리 색·폰트·
구도를 완전히 통제할 수 있고 비용이 들지 않는다. 대신 실사는 못 만든다 —
재난안전 콘텐츠에서는 오히려 도해풍이 안전하다(VEO_PROMPTS.md 참고).

방식: 장면을 t(0~1)로 그리는 JS 함수로 두고, t 를 일정 간격으로 올리며 매 프레임
캡처한 뒤 ffmpeg 로 잇는다. CSS 애니메이션을 벽시계로 찍으면 프레임이 불규칙해서
t 를 직접 먹인다. t=0 과 t=1 의 그림이 같아야 반복 재생이 끊기지 않는다.

사용:  ./.venv/bin/python make_broll.py flood            → posts/broll/flood.mp4
       ./.venv/bin/python make_broll.py flood --seconds 8
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
NAVY, SLATE, AMBER = "#334A8E", "#272C3C", "#FFA500"

# ── 장면 ────────────────────────────────────────────────────────────────
# 각 장면은 draw(t) 를 가진 JS. t 는 0→1 이고, 끝과 처음이 이어져야 한다.

FLOOD = """
const sky = document.getElementById('sky');
const rainC = document.getElementById('rain');
const rx = rainC.getContext('2d');
const water = document.getElementById('water');
const waveC = document.getElementById('wave');
const wx = waveC.getContext('2d');
const far = document.getElementById('far');
const near = document.getElementById('near');

// 빗줄기: 각자 다른 속도로 떨어지고, 화면을 벗어나면 위로 돌아온다.
const drops = [];
for (let i = 0; i < 420; i++) {
  drops.push({x: Math.random()*W, y: Math.random()*H,
              len: 26 + Math.random()*54, sp: 0.9 + Math.random()*0.9,
              a: 0.10 + Math.random()*0.30});
}

window.draw = function (t) {
  // 비에 젖은 하늘: 아주 느리게 밝기가 오간다(번개가 아니라 구름 흐름 정도)
  const b = 0.92 + 0.08 * Math.sin(t * Math.PI * 2);
  sky.style.filter = `brightness(${b})`;

  // 원경/근경 패럴랙스 — 근경이 더 많이 움직여 깊이가 생긴다
  far.style.transform  = `translateX(${-12 * Math.sin(t * Math.PI * 2)}px)`;
  near.style.transform = `translateX(${-34 * Math.sin(t * Math.PI * 2)}px)`;

  // 빗줄기
  rx.clearRect(0, 0, W, H);
  rx.lineCap = 'round';
  for (const d of drops) {
    const y = (d.y + t * H * 2.2 * d.sp) % (H + 120) - 60;
    rx.strokeStyle = `rgba(200,220,255,${d.a})`;
    rx.lineWidth = 2.0;
    rx.beginPath(); rx.moveTo(d.x, y); rx.lineTo(d.x - 9, y + d.len); rx.stroke();
  }

  // 수위: 8초 동안 아주 조금 차오른다(t=1 에서 t=0 으로 돌아갈 때 튀지 않게
  // 사인으로 오르내린다)
  const rise = 40 * (1 - Math.cos(t * Math.PI * 2)) / 2;
  water.style.height = (420 + rise) + 'px';

  // 수면 물결 + 가로등 반영
  wx.clearRect(0, 0, W, waveC.height);
  for (let layer = 0; layer < 3; layer++) {
    wx.beginPath();
    const amp = 7 - layer * 2, off = layer * 26, sp = 1 + layer * 0.6;
    for (let x = 0; x <= W; x += 6) {
      const y = off + amp * Math.sin((x / 110) + t * Math.PI * 2 * sp);
      x === 0 ? wx.moveTo(x, y) : wx.lineTo(x, y);
    }
    wx.strokeStyle = `rgba(255,165,0,${0.20 - layer * 0.05})`;
    wx.lineWidth = 3; wx.stroke();
  }
};
"""

SCENES = {"flood": ("집중호우 도시 침수", FLOOD)}

BODY = f"""
<div id="stage">
  <div id="sky"></div>
  <div id="far"></div>
  <div id="near"></div>
  <div id="lamp"></div>
  <canvas id="rain" width="{W}" height="{H}"></canvas>
  <div id="water"><canvas id="wave" width="{W}" height="90"></canvas></div>
  <div id="vig"></div>
</div>
"""

CSS = f"""
 * {{ margin:0; padding:0; box-sizing:border-box; }}
 body {{ background:#000; }}
 #stage {{ position:relative; width:{W}px; height:{H}px; overflow:hidden;
   background:{SLATE}; }}
 #sky {{ position:absolute; inset:0;
   background:linear-gradient(180deg,#141a2e 0%,{SLATE} 45%,#1d2947 100%); }}
 /* 원경 빌딩 — 실루엣만, 상단 40%는 비워 자막 자리를 남긴다 */
 #far {{ position:absolute; left:-40px; right:-40px; bottom:380px; height:520px;
   background:
     repeating-linear-gradient(90deg,
       rgba(51,74,142,.55) 0 90px, transparent 90px 150px);
   -webkit-mask-image:linear-gradient(180deg,transparent 0%,#000 22%,#000 100%);
   mask-image:linear-gradient(180deg,transparent 0%,#000 22%,#000 100%); }}
 #near {{ position:absolute; left:-60px; right:-60px; bottom:400px; height:360px;
   background:
     repeating-linear-gradient(90deg,
       rgba(20,26,46,.92) 0 140px, transparent 140px 230px);
   -webkit-mask-image:linear-gradient(180deg,transparent 0%,#000 18%,#000 100%);
   mask-image:linear-gradient(180deg,transparent 0%,#000 18%,#000 100%); }}
 /* 가로등 불빛 하나 — 화면에 온기를 준다 */
 #lamp {{ position:absolute; right:180px; bottom:560px; width:380px; height:380px;
   border-radius:50%;
   background:radial-gradient(circle,rgba(255,165,0,.34) 0%,transparent 66%); }}
 #rain {{ position:absolute; inset:0; }}
 #water {{ position:absolute; left:0; right:0; bottom:0; height:420px;
   background:linear-gradient(180deg,rgba(51,74,142,.85) 0%,#0e1424 100%); }}
 #wave {{ position:absolute; left:0; top:-14px; }}
 #vig {{ position:absolute; inset:0; pointer-events:none;
   background:radial-gradient(ellipse at 50% 45%,transparent 46%,rgba(0,0,0,.55) 100%); }}
"""


def _html(scene_js):
    return (f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style>"
            f"</head><body>{BODY}<script>const W={W},H={H};{scene_js}</script></body></html>")


def render(name, seconds=8.0, fps=24):
    if name not in SCENES:
        raise SystemExit(f"모르는 장면: {name} (가능: {', '.join(SCENES)})")
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
    d = webdriver.Chrome(options=o)
    try:
        # 뷰포트를 정확히 1080x1920 으로 고정한다. 창 크기만 키우면 크롬이
        # 툴바·여백만큼 잘라내서 1080x1897 같은 홀수 높이가 나오고, 그러면
        # libx264 가 "height not divisible by 2" 로 죽는다(2026-09-26 확인).
        d.execute_cdp_cmd("Emulation.setDeviceMetricsOverride",
                          {"width": W, "height": H, "deviceScaleFactor": 1,
                           "mobile": False})
        d.get("file:///" + page.replace("\\", "/"))
        time.sleep(1.0)
        el = d.find_element(By.ID, "stage")
        for i in range(n):
            # t 는 [0,1). 마지막 프레임 다음이 첫 프레임과 이어진다.
            d.execute_script("window.draw(arguments[0]);", i / n)
            el.screenshot(os.path.join(work, f"{i:04d}.png"))
        log(f"[{label}] 프레임 {n}장 캡처")
    finally:
        d.quit()

    out_dir = os.path.join(POSTS_DIR, "broll")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{name}.mp4")
    subprocess.run([
        imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
        "-framerate", str(fps), "-i", os.path.join(work, "%04d.png"),
        # 필름 그레인과 아주 약한 블룸 — 평평한 벡터 그림에 질감을 준다
        "-vf", f"scale={W}:{H},noise=alls=6:allf=t+u,unsharp=5:5:-0.3,format=yuv420p",
        "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-r", str(fps),
        out,
    ], check=True)
    shutil.rmtree(work, ignore_errors=True)
    log(f"[{label}] 완성: {out} ({seconds}s, {fps}fps)")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("scene", choices=sorted(SCENES))
    ap.add_argument("--seconds", type=float, default=8.0)
    ap.add_argument("--fps", type=int, default=24)
    a = ap.parse_args()
    print(render(a.scene, a.seconds, a.fps))
