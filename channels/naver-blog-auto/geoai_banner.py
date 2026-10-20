"""GeoAI 블로그 글 머리에 넣을 가로 배너(PNG)를 만든다.

왜 Gamma 카드 대신 배너인가: 카드뉴스(16:9 다섯 장)는 글에서 차지하는 자리가 너무
컸다. 배너는 납작해 글 흐름을 끊지 않고, 헤드리스 Chrome 으로 직접 그리므로
Gamma 크레딧도 들지 않는다(make_banner.py 와 같은 방식, 디자인만 GeoAI 판).

비율을 3:1 에서 2:1 로 바꾸고 글자를 가운데로 옮겼다(2026-10-14). 구글 검색 썸네일,
카카오톡·트위터 공유 카드, 블로거 인기글 위젯이 가운데를 정사각으로 잘라 쓰는데,
3:1 은 가운데 33%만 남아 제목 앞뒤와 날짜·계열이 통째로 사라졌다. 2:1 에 가운데
정렬이면 잘린 정사각 안에 제목이 그대로 들어온다.

디자인: 짙은 남색 바탕 + 격자(위성 격자 느낌) + 가운데 제목 / 아래 계열·날짜.
"""
import os
import re
import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from common import POSTS_DIR, load_config, log

W, H = 1200, 600          # 2:1 — 정사각으로 잘려도 제목이 남는 가장 납작한 비율

import sys as _sys  # KoPub 글꼴(공용 shared/fonts)
_sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from shared.fonts import display_css, kopub_bold_css  # noqa: E402

HTML = """<!doctype html><html><head><meta charset="utf-8"><style>""" + kopub_bold_css(doubled=True) + display_css(doubled=True) + """
  body {{ margin:0; background:#fff; }}
  #banner {{
    width:{w}px; height:{h}px; box-sizing:border-box; padding:44px 52px;
    background:linear-gradient(135deg,#0b1c3a 0%,#123a5e 60%,#0e5a6b 100%);
    color:#fff; font-family:'KoPub','Apple SD Gothic Neo','Malgun Gothic','맑은 고딕',sans-serif;
    position:relative; overflow:hidden; display:flex; flex-direction:column;
    justify-content:space-between; align-items:center; text-align:center;
  }}
  /* 위성 격자 느낌의 옅은 그리드 */
  .grid {{
    position:absolute; inset:0;
    background-image:linear-gradient(rgba(255,255,255,.07) 1px,transparent 1px),
                     linear-gradient(90deg,rgba(255,255,255,.07) 1px,transparent 1px);
    background-size:60px 60px;
  }}
  .glow {{
    position:absolute; right:-80px; top:-120px; width:420px; height:420px;
    border-radius:50%; background:radial-gradient(circle,rgba(56,189,248,.35),transparent 70%);
  }}
  .kicker {{ font-family:'Body';
    position:relative; border:2px solid #38bdf8; color:#7dd3fc;
    font-weight:800; padding:6px 16px; font-size:18px; letter-spacing:2px; border-radius:4px;
  }}
  /* 가운데 정사각(가로의 50%)에 들어오도록 폭을 묶는다 — 잘려도 제목이 살아남는다. */
  .title {{
    font-family:'Display'; position:relative; font-size:{size}px; font-weight:400; line-height:1.3;
    max-width:{tw}px; letter-spacing:-.5px; word-break:keep-all;
    display:flex; align-items:center; flex:1;
  }}
  .foot {{ font-family:'Body'; position:relative; font-size:20px; color:#9fb3c8; }}
  .brand {{ color:#7dd3fc; font-weight:700; }}
</style></head><body>
  <div id="banner">
    <div class="grid"></div><div class="glow"></div>
    <div class="kicker">{kicker}</div>
    <div class="title">{title}</div>
    <div class="foot"><span class="brand">{brand}</span> · {date}</div>
  </div>
</body></html>"""


def _title_size(t):
    """폭이 절반으로 좁아졌으므로 글자도 그만큼 줄여 3줄 안에 들어오게 한다."""
    n = len(t)
    if n <= 14:
        return 50
    if n <= 22:
        return 44
    return 38 if n <= 32 else 33


def _short_title(title):
    """배너에는 부제만 남긴다('제목 | 시리즈 N편' 의 앞부분)."""
    out = title
    for sep in ("|", "–", "—"):
        if sep in out:
            out = out.split(sep, 1)[0].strip()
            break
    return out


def make_banner(data, cfg=None, size=None):
    """글 데이터 → 배너 PNG 경로. 실패하면 예외(호출부에서 이미지 없이 진행).

    size 로 비율을 바꿀 수 있다 — 유튜브 게시물은 2:5~5:2 만 받아 3:1 배너가 거부된다."""
    cfg = cfg or load_config()
    b = ((cfg.get("geoai") or {}).get("banner") or {})
    w, h = size or (W, H)
    title = _short_title(data.get("title", ""))
    kicker = data.get("family") or ("GeoAI 브리핑" if data.get("news_blocks") else "GeoAI 기초")
    html = HTML.format(w=w, h=h, title=title, size=_title_size(title),
                       tw=int(w * 0.46),          # 가운데 정사각(50%) 안쪽
                       kicker=b.get("kicker", kicker),
                       brand=b.get("brand", "재난안전과 GeoAI"),
                       date=f"{datetime.now():%Y년 %m월 %d일}")
    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    html_path = os.path.join(POSTS_DIR, f"_geoai_banner_{stamp}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    o = Options()
    o.add_argument("--headless=new")
    o.add_argument(f"--window-size={w + 100},{h + 160}")
    o.add_argument("--force-device-scale-factor=2")     # 2배로 찍어 선명하게
    o.add_argument("--hide-scrollbars")
    # 크롬이 실행마다 앱 전체(~1.4GB)를 임시 폴더에 복제하고 남기는 것을 막는다(2026-10-09)
    o.add_argument("--disable-features=MacAppCodeSignClone")
    d = webdriver.Chrome(options=o)
    try:
        d.get("file:///" + html_path.replace("\\", "/"))
        time.sleep(1.0)
        out = os.path.join(POSTS_DIR, f"geoai_banner_{stamp}_{w}x{h}.png")
        d.find_element(By.ID, "banner").screenshot(out)
        log(f"배너 생성: {out}")
        return out
    finally:
        d.quit()


if __name__ == "__main__":
    import glob, json, sys
    path = sys.argv[1] if len(sys.argv) > 1 else sorted(glob.glob(os.path.join(POSTS_DIR, "*.json")))[-1]
    print(make_banner(json.load(open(path, encoding="utf-8"))))
