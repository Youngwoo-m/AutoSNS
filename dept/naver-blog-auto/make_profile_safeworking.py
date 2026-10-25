"""개인 네이버 블로그(safeworking) 프로필 이미지 후보를 만든다 — 토목·측량 기술사 공부와 GeoAI.

make_profile_image.py(학과 계정용)와 같은 방식(헤드리스 Chrome 으로 HTML 렌더링 후 캡처)이다.
학과 계정의 네이비·골드와 구분되게 짙은 녹색(#1F4E3D)과 모래색(#E8DCC2)을 쓴다.
글꼴은 Pretendard Bold(assets/FONTS) 하나로, 굵기 대신 크기와 색으로 위계를 준다.

  a 삼각점형 : 녹색 바탕 + 삼각점 표지(삼각형·십자) + '토목·측량'
  b 등고선형 : 모래색 바탕 + 등고선 + '토목·측량'
  c 십자선형 : 녹색 원 + 측량 망원경 십자선 + '토목 측량'

결과는 posts/safeworking/profile_{a,b,c}.png. 실제 등록은 naver_profile.py 가 한다(확인 후).
네이버는 가로 161px 섬네일로 줄이므로 글자를 크게 잡는다.
"""
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
# 워크트리에는 글꼴(git 제외)이 없을 수 있어 main 폴더 것을 대신 쓴다
FONT_CANDIDATES = (
    os.path.join(ROOT, "assets", "FONTS", "Pretendard-Bold.otf"),
    "/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf",
)
OUT_DIR = os.path.join(HERE, "posts", "safeworking")

S = 640
GREEN, DEEP, SAND, INK = "#1F4E3D", "#143528", "#E8DCC2", "#2B2A26"


def _font():
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    raise SystemExit("Pretendard-Bold.otf 가 assets/FONTS 에 없습니다.")


CONTOURS = "".join(
    f'<ellipse cx="320" cy="330" rx="{r}" ry="{int(r * 0.78)}" fill="none" stroke="{GREEN}" '
    f'stroke-opacity="{0.10 + 0.05 * i:.2f}" stroke-width="3" transform="rotate(-18 320 330)"/>'
    for i, r in enumerate(range(80, 400, 42))
)

CARDS = {
    "a": f"""
<div class="card" id="a" style="background:linear-gradient(160deg,{GREEN} 0%,{DEEP} 100%)">
  <svg viewBox="0 0 100 100" class="mark"><path d="M50 12 L86 78 H14 Z" fill="none" stroke="{SAND}" stroke-width="3.5"/>
    <circle cx="50" cy="30" r="3" fill="{SAND}"/></svg>
  <div class="inner">
    <div class="ko">토목·측량</div>
    <div class="bar"></div>
    <div class="sub">기술사 공부 · 현장 · GeoAI</div>
  </div>
</div>""",
    "b": f"""
<div class="card" id="b" style="background:{SAND}">
  <svg viewBox="0 0 640 640" class="full">{CONTOURS}</svg>
  <div class="inner dark">
    <div class="ko">토목·측량</div>
    <div class="bar g"></div>
    <div class="sub g">기술사 공부 · 현장 · GeoAI</div>
  </div>
</div>""",
    "c": f"""
<div class="card" id="c" style="background:{SAND}">
  <div class="inner">
    <div class="lens">
      <svg viewBox="0 0 100 100" class="cross"><circle cx="50" cy="50" r="46" fill="none" stroke="{SAND}" stroke-opacity=".22" stroke-width="1.6"/>
        <path d="M50 4 V96 M4 50 H96" stroke="{SAND}" stroke-opacity=".22" stroke-width="1.6"/>
        <path d="M30 40 H70 M36 60 H64" stroke="{SAND}" stroke-opacity=".22" stroke-width="1.6"/></svg>
      <div class="ko c">토목<br>측량</div>
    </div>
    <div class="sub3">기술사 공부 · 현장 · GeoAI</div>
  </div>
</div>""",
}

CSS = f"""
 @font-face{{font-family:'PB';src:url('file://{_font()}') format('opentype');}}
 body{{margin:0;background:#eee;font-family:'PB','Apple SD Gothic Neo',sans-serif}}
 .card{{width:{S}px;height:{S}px;position:relative;overflow:hidden;color:{SAND};
   display:flex;align-items:center;justify-content:center;margin:20px}}
 .mark{{position:absolute;width:78%;height:78%;left:11%;top:6%;opacity:.35}}
 .full{{position:absolute;inset:0;width:100%;height:100%}}
 .inner{{position:relative;text-align:center;z-index:2}}
 .inner.dark{{color:{GREEN}}}
 .ko{{font-size:120px;letter-spacing:-5px;line-height:1.05;margin-top:70px}}
 .ko.c{{font-size:112px;color:{SAND};margin:0;position:relative;z-index:2}}
 .bar{{width:96px;height:8px;background:{SAND};margin:20px auto 18px;border-radius:4px}}
 .bar.g{{background:{GREEN}}}
 .sub{{font-size:30px;color:#cfe0d6}}
 .sub.g{{color:{INK}}}
 .lens{{width:420px;height:420px;border-radius:50%;background:{GREEN};border:14px solid {DEEP};
   display:flex;align-items:center;justify-content:center;margin:0 auto;position:relative}}
 .cross{{position:absolute;inset:0;width:100%;height:100%}}
 .sub3{{font-size:30px;color:{GREEN};margin-top:26px}}
"""


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    html = (f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head>"
            f"<body>{''.join(CARDS.values())}</body></html>")
    page = os.path.join(OUT_DIR, "_profile.html")
    with open(page, "w", encoding="utf-8") as f:
        f.write(html)

    opts = Options()
    for arg in ("--headless=new", f"--window-size={S + 80},{S * 3 + 200}", "--hide-scrollbars",
                "--allow-file-access-from-files", "--force-device-scale-factor=1",
                "--disable-features=MacAppCodeSignClone"):
        opts.add_argument(arg)
    d = webdriver.Chrome(options=opts)
    try:
        d.get("file://" + page)
        time.sleep(1.5)
        for key in CARDS:
            out = os.path.join(OUT_DIR, f"profile_{key}.png")
            d.find_element(By.ID, key).screenshot(out)
            print(out, os.path.getsize(out) // 1000, "KB")
    finally:
        d.quit()


if __name__ == "__main__":
    main()
