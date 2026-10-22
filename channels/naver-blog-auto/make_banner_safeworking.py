"""개인 네이버 블로그(safeworking) 대문(타이틀) 배너를 만든다 — 966x260, 프로필 이미지(a 삼각점형)와 같은 톤.

make_profile_safeworking.py 와 같은 방식(헤드리스 Chrome 으로 HTML 렌더링 후 캡처)이다.
녹색(#1F4E3D) 바탕에 모래색(#E8DCC2) 등고선·삼각점, 글꼴은 Pretendard Bold 하나.
네이버 '타이틀 꾸미기'의 이미지 칸(가로 966px)에 맞춘다. 결과: posts/safeworking/banner.png
"""
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from make_profile_safeworking import DEEP, GREEN, OUT_DIR, SAND, _font

W, H = 966, 260


def _contours():
    rings = "".join(
        f'<ellipse cx="800" cy="150" rx="{r}" ry="{int(r * 0.62)}" fill="none" stroke="{SAND}" '
        f'stroke-opacity="{max(0.05, 0.22 - 0.025 * i):.2f}" stroke-width="2" transform="rotate(-14 800 150)"/>'
        for i, r in enumerate(range(60, 560, 52))
    )
    return f'<svg class="bg" viewBox="0 0 {W} {H}">{rings}</svg>'


CSS = f"""
 @font-face{{font-family:'PB';src:url('file://{_font()}') format('opentype');}}
 body{{margin:0;font-family:'PB','Apple SD Gothic Neo',sans-serif}}
 #b{{width:{W}px;height:{H}px;position:relative;overflow:hidden;color:{SAND};
   background:linear-gradient(110deg,{GREEN} 0%,{DEEP} 100%)}}
 .bg{{position:absolute;inset:0;width:100%;height:100%}}
 .mark{{position:absolute;right:70px;top:36px;width:190px;height:190px;opacity:.9}}
 .txt{{position:absolute;left:64px;top:0;height:100%;display:flex;flex-direction:column;justify-content:center}}
 .ko{{font-size:92px;letter-spacing:-4px;line-height:1.05}}
 .bar{{width:84px;height:7px;background:{SAND};border-radius:4px;margin:16px 0 14px}}
 .sub{{font-size:27px;color:#cfe0d6}}
"""

HTML = f"""<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>
<div id="b">{_contours()}
  <svg viewBox="0 0 100 100" class="mark"><path d="M50 12 L88 82 H12 Z" fill="none" stroke="{SAND}" stroke-width="3.5"/>
    <circle cx="50" cy="32" r="3" fill="{SAND}"/></svg>
  <div class="txt"><div class="ko">토목·측량</div><div class="bar"></div>
    <div class="sub">기술사 공부 · 현장 · GeoAI</div></div>
</div></body></html>"""


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    page = os.path.join(OUT_DIR, "_banner.html")
    with open(page, "w", encoding="utf-8") as f:
        f.write(HTML)
    opts = Options()
    for arg in ("--headless=new", f"--window-size={W + 40},{H + 120}", "--hide-scrollbars",
                "--allow-file-access-from-files", "--force-device-scale-factor=1",
                "--disable-features=MacAppCodeSignClone"):
        opts.add_argument(arg)
    d = webdriver.Chrome(options=opts)
    try:
        d.get("file://" + page)
        time.sleep(1.5)
        out = os.path.join(OUT_DIR, "banner.png")
        d.find_element("id", "b").screenshot(out)
        print(out, os.path.getsize(out) // 1000, "KB")
    finally:
        d.quit()


if __name__ == "__main__":
    main()
