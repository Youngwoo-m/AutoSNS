"""네이버 블로그 프로필 이미지 후보를 만든다(헤드리스 Chrome 으로 HTML 렌더링 후 캡처).

make_banner.py 와 같은 방식이라 별도 설치가 필요 없고 저작권 문제도 없다.
색은 학과 홈페이지·블로거 테마와 맞춘 네이비(#334A8E)·골드(#FFA500)·슬레이트(#272C3C).

  a 방패형   : 네이비 바탕 + 골드 방패 + '재난안전'   ← 현재 적용 중
  b 안전테이프형: 슬레이트 바탕 + 경고 사선 + '재난안전학과'
  c 엠블럼형  : 흰 바탕 + 원형 엠블럼

결과는 posts/profile_{a,b,c}.png 로 떨어진다. 실제 등록은 naver_profile.py 가 한다.
네이버는 가로 161px 섬네일로 줄이므로 글자를 크게 잡는다.
"""
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from common import POSTS_DIR

import sys as _sys  # Pretendard 글꼴(공용 shared/fonts)
_sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from shared.fonts import display_css  # noqa: E402

S = 640
NAVY, GOLD, SLATE = "#334A8E", "#FFA500", "#272C3C"

CARDS = {
    "a": f"""
<div class="card" id="a" style="background:linear-gradient(160deg,{NAVY} 0%,#1e2f63 100%)">
  <svg viewBox="0 0 100 100" class="shield"><path d="M50 8 L86 22 V50 C86 72 70 86 50 93 C30 86 14 72 14 50 V22 Z"
    fill="none" stroke="{GOLD}" stroke-width="4"/></svg>
  <div class="inner">
    <div class="en">DISASTER SAFETY</div>
    <div class="ko">재난안전</div>
    <div class="bar"></div>
    <div class="dept">세명대학교 재난안전학과</div>
  </div>
</div>""",
    "b": f"""
<div class="card" id="b" style="background:{SLATE}">
  <div class="tape"></div><div class="tape b"></div>
  <div class="inner">
    <div class="tri">▲</div>
    <div class="ko2">재난안전학과</div>
    <div class="dept2">세명대학교 · SEMYUNG UNIV.</div>
  </div>
</div>""",
    "c": f"""
<div class="card" id="c" style="background:#fff">
  <div class="inner">
    <div class="emblem"><div class="emblem-ko">재난<br>안전</div></div>
    <div class="dept3">세명대학교 재난안전학과</div>
    <div class="sub3">제천 · 충북 재난안전 소식</div>
  </div>
</div>""",
}

CSS = display_css() + f"""
 body{{margin:0;background:#eee;font-family:'Body','Apple SD Gothic Neo','Malgun Gothic',sans-serif}}
 .card{{width:{S}px;height:{S}px;position:relative;overflow:hidden;color:#fff;
   display:flex;align-items:center;justify-content:center;margin:20px}}
 .inner{{position:relative;text-align:center;z-index:2}}
 .shield{{position:absolute;width:92%;height:92%;left:4%;top:4%;opacity:.55}}
 .en{{font-size:24px;letter-spacing:7px;color:{GOLD};font-weight:700}}
 .ko{{font-size:104px;font-weight:700;letter-spacing:-4px;line-height:1.05;margin-top:6px}}
 .bar{{width:96px;height:7px;background:{GOLD};margin:18px auto 16px;border-radius:4px}}
 .dept{{font-size:27px;color:#d6e0f5;font-weight:700}}
 .tape{{position:absolute;left:0;top:0;width:100%;height:30px;
   background:repeating-linear-gradient(45deg,{GOLD} 0 34px,{SLATE} 34px 68px)}}
 .tape.b{{top:auto;bottom:0}}
 .tri{{font-size:96px;color:{GOLD};line-height:1}}
 .ko2{{font-size:86px;font-weight:700;letter-spacing:-4px;margin-top:10px}}
 .dept2{{font-size:27px;color:{GOLD};font-weight:700;margin-top:18px;letter-spacing:1px}}
 .emblem{{width:330px;height:330px;border-radius:50%;background:{NAVY};
   border:12px solid {GOLD};display:flex;align-items:center;justify-content:center;margin:0 auto}}
 .emblem-ko{{font-size:96px;font-weight:700;line-height:1.02;letter-spacing:-4px;color:#fff}}
 .dept3{{font-size:38px;font-weight:700;color:{NAVY};margin-top:30px;letter-spacing:-1px}}
 .sub3{{font-size:26px;color:#6b7280;margin-top:10px}}
"""


def main():
    html = (f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head>"
            f"<body>{''.join(CARDS.values())}</body></html>")
    page = os.path.join(POSTS_DIR, "_profile.html")
    with open(page, "w", encoding="utf-8") as f:
        f.write(html)

    opts = Options()
    for arg in ("--headless=new", f"--window-size={S + 80},{S * 3 + 200}", "--hide-scrollbars",
                "--allow-file-access-from-files", "--force-device-scale-factor=1"):
        opts.add_argument(arg)
    # 크롬이 실행마다 앱 전체(~1.4GB)를 임시 폴더에 복제하고 남기는 것을 막는다(2026-10-09)
    opts.add_argument("--disable-features=MacAppCodeSignClone")
    d = webdriver.Chrome(options=opts)
    try:
        d.get("file://" + page)
        time.sleep(1.5)
        for key in CARDS:
            out = os.path.join(POSTS_DIR, f"profile_{key}.png")
            d.find_element(By.ID, key).screenshot(out)
            print(out, os.path.getsize(out) // 1000, "KB")
    finally:
        d.quit()


if __name__ == "__main__":
    main()
