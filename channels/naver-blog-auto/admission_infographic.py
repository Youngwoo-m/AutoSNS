"""입시 시리즈 11편(실습실과 장비)에 넣을 인포그래픽을 그린다.

한 번 그려 assets/admission/ 에 PNG 로 둔다 — 발행 전에 사람이 보고 고칠 수 있게.
발행할 때 career_series 가 CDN 에 올려 본문에 넣는다(admission_topics.IMAGES).

담는 내용은 학과가 확인해 준 사실만이다(2026-09-27):
  보유 실습 기자재 = 재난안전 현장 대응용 드론, 드론 운용 시뮬레이터
기종·대수·사양은 확인하지 않았으므로 그리지 않는다. 아래쪽 '드론이 재난 현장에서
쓰이는 곳'은 학과 사정이 아니라 일반적인 쓰임이라, 그렇게 읽히도록 제목을 단다.

    ./.venv/bin/python admission_infographic.py      # assets/admission/adm-lab.png
"""
import os
import time

from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from common import BASE_DIR, log, start_chrome

import sys as _sys  # Pretendard 글꼴(공용 shared/fonts)
_sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from shared.fonts import display_css  # noqa: E402

OUT_DIR = os.path.join(BASE_DIR, "assets", "admission")
W = 1200

HTML = """<!doctype html><html><head><meta charset="utf-8"><style>""" + display_css(doubled=True) + """
  body { margin:0; background:#fff; }
  #card {
    width:%(w)dpx; box-sizing:border-box; padding:44px 48px 34px;
    background:linear-gradient(160deg,#272C3C 0%%,#334A8E 100%%);
    color:#fff; font-family:'Body','Apple SD Gothic Neo','Malgun Gothic','맑은 고딕',sans-serif;
  }
  .eyebrow { font-size:16px; letter-spacing:3px; color:#FFA500; font-weight:700; }
  h1 { margin:6px 0 30px; font-size:42px; line-height:1.25; }
  .row { display:flex; align-items:stretch; gap:18px; }
  .box {
    flex:1; background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.18);
    border-radius:18px; padding:26px 26px 24px;
  }
  .ico { display:block; }
  .step { display:inline-block; margin-top:14px; font-size:14px; font-weight:700;
          color:#272C3C; background:#FFA500; border-radius:20px; padding:4px 12px; }
  .name { font-size:30px; font-weight:700; margin:12px 0 8px; }
  .desc { font-size:19px; line-height:1.6; opacity:.88; }
  .arrow { display:flex; align-items:center; font-size:40px; color:#FFA500; }
  .sub { margin:34px 0 14px; font-size:17px; opacity:.75; letter-spacing:1px; }
  .uses { display:flex; gap:12px; }
  .use {
    flex:1; text-align:center; background:rgba(255,165,0,.12);
    border:1px solid rgba(255,165,0,.45); border-radius:14px; padding:16px 8px;
    font-size:19px; font-weight:700;
  }
  .use span { display:block; font-size:30px; margin-bottom:6px; }
  .foot { margin-top:30px; display:flex; justify-content:space-between;
          font-size:15px; opacity:.6; }
</style></head><body><div id="card">
  <div class="eyebrow">PRACTICE EQUIPMENT</div>
  <h1>재난안전학과 실습 기자재</h1>
  <div class="row">
    <div class="box">
      <svg class="ico" viewBox="0 0 64 64" width="60" height="60" fill="none" stroke="#FFA500" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
        <rect x="6" y="8" width="52" height="32" rx="3"/>
        <path d="M13 32c6-10 12 2 18-8s12-4 16-10" stroke-dasharray="3 4"/>
        <path d="M26 40v6M38 40v6"/>
        <rect x="16" y="46" width="32" height="12" rx="6"/>
        <circle cx="25" cy="52" r="2"/><circle cx="39" cy="52" r="2"/>
      </svg>
      <div class="step">STEP 1 · 먼저 익히기</div>
      <div class="name">드론 운용 시뮬레이터</div>
      <div class="desc">실제 비행 전에 조종과 운용 절차를<br>안전한 환경에서 반복해 연습합니다</div>
    </div>
    <div class="arrow">➜</div>
    <div class="box">
      <svg class="ico" viewBox="0 0 64 64" width="60" height="60" fill="none" stroke="#FFA500" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
        <rect x="24" y="26" width="16" height="12" rx="3"/>
        <path d="M24 28 14 18M40 28 50 18M24 36 14 46M40 36 50 46"/>
        <ellipse cx="12" cy="16" rx="9" ry="2.6"/><ellipse cx="52" cy="16" rx="9" ry="2.6"/>
        <ellipse cx="12" cy="48" rx="9" ry="2.6"/><ellipse cx="52" cy="48" rx="9" ry="2.6"/>
        <circle cx="32" cy="42" r="2.6"/>
      </svg>
      <div class="step">STEP 2 · 현장처럼 해보기</div>
      <div class="name">재난 현장 대응 드론</div>
      <div class="desc">익힌 운용 능력을 실제 드론으로<br>재난 현장 대응 실습에 적용합니다</div>
    </div>
  </div>
  <div class="sub">재난 현장에서 드론이 흔히 쓰이는 곳</div>
  <div class="uses">
    <div class="use"><span>📸</span>피해 현장 촬영</div>
    <div class="use"><span>🧭</span>접근 어려운 곳 확인</div>
    <div class="use"><span>🔎</span>수색 지원</div>
    <div class="use"><span>🗺️</span>현장 지도 만들기</div>
  </div>
  <div class="foot"><span>세명대학교 재난안전학과</span><span>smuds2026.blogspot.com</span></div>
</div></body></html>"""


def make_lab():
    os.makedirs(OUT_DIR, exist_ok=True)
    html_path = os.path.join(OUT_DIR, "_adm-lab.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(HTML % {"w": W})
    o = Options()
    o.add_argument("--headless=new")
    o.add_argument(f"--window-size={W + 100},900")
    o.add_argument("--force-device-scale-factor=2")
    o.add_argument("--hide-scrollbars")
    d = start_chrome(o)
    try:
        d.get("file:///" + html_path)
        time.sleep(0.8)
        out = os.path.join(OUT_DIR, "adm-lab.png")
        d.find_element(By.ID, "card").screenshot(out)
        log(f"실습 기자재 인포그래픽: {out}")
        return out
    finally:
        d.quit()
        os.remove(html_path)


if __name__ == "__main__":
    make_lab()
