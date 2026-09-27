"""따라하기 단계를 그린 도식 PNG 를 만든다(글 본문에 넣는 '사용법 그림').

왜 직접 그리나: QGIS·AI 도구의 실제 화면을 자동으로 캡처하려면 그 프로그램을 띄워
조작해야 하고, 타사 화면을 그대로 싣는 것도 걸린다. 대신 '무엇을 어떤 순서로
누르는가'를 카드 흐름으로 그린다 — 헤드리스 Chrome 으로 직접 그리므로 비용이 없고,
본문의 따라하기 목록과 같은 값을 쓰므로 글과 그림이 어긋나지 않는다.

배너(geoai_banner.py)와 같은 방식이다. 디자인만 단계 카드용.
"""
import os
import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from common import POSTS_DIR, load_config, log, start_chrome

W = 1200                    # 폭 고정, 높이는 단계 수에 따라 늘어난다
CARD_H = 104                # 카드 한 장 높이(대략) — 창 크기 계산에만 쓴다

HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
  body {{ margin:0; background:#fff; }}
  #steps {{
    width:{w}px; box-sizing:border-box; padding:34px 38px 26px;
    background:linear-gradient(135deg,#0b1c3a 0%,#123a5e 70%,#0e5a6b 100%);
    color:#fff; font-family:'Apple SD Gothic Neo','Malgun Gothic','맑은 고딕',sans-serif;
  }}
  #head {{ font-size:15px; letter-spacing:2px; opacity:.72; margin-bottom:4px; }}
  #title {{ font-size:30px; font-weight:800; margin-bottom:22px; line-height:1.3; }}
  .row {{ display:flex; align-items:stretch; gap:14px; margin-bottom:12px; }}
  .no {{
    flex:0 0 52px; display:flex; align-items:center; justify-content:center;
    font-size:24px; font-weight:800; color:#0b1c3a;
    background:#7fd3e0; border-radius:12px;
  }}
  .card {{
    flex:1; background:rgba(255,255,255,.10); border:1px solid rgba(255,255,255,.18);
    border-radius:12px; padding:14px 18px;
  }}
  .name {{ font-size:21px; font-weight:700; margin-bottom:5px; }}
  .desc {{ font-size:17px; line-height:1.5; opacity:.9; word-break:keep-all; }}
  #foot {{ margin-top:14px; font-size:14px; opacity:.6; text-align:right; }}
</style></head><body>
<div id="steps">
  <div id="head">따라하기</div>
  <div id="title">{title}</div>
  {rows}
  <div id="foot">{brand}</div>
</div></body></html>"""

ROW = ('<div class="row"><div class="no">{n}</div>'
       '<div class="card"><div class="name">{name}</div>'
       '<div class="desc">{desc}</div></div></div>')


def _esc(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def make_steps(data, cfg=None):
    """글 데이터의 howto 단계 → 도식 PNG 경로. 단계가 없으면 None."""
    steps = data.get("howto") or []
    if not steps:
        return None
    cfg = cfg or load_config()
    brand = ((cfg.get("geoai") or {}).get("banner") or {}).get("brand", "재난안전과 GeoAI")
    title = data.get("title", "").split(" | ")[0]
    rows = "\n  ".join(ROW.format(n=i, name=_esc(n), desc=_esc(d))
                       for i, (n, d) in enumerate(steps, start=1))
    html = HTML.format(w=W, title=_esc(title), rows=rows, brand=_esc(brand))

    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    html_path = os.path.join(POSTS_DIR, f"_geoai_steps_{stamp}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    o = Options()
    o.add_argument("--headless=new")
    o.add_argument(f"--window-size={W + 100},{260 + CARD_H * len(steps)}")
    o.add_argument("--force-device-scale-factor=2")
    o.add_argument("--hide-scrollbars")
    d = start_chrome(o)
    try:
        d.get("file:///" + html_path.replace("\\", "/"))
        time.sleep(0.8)
        out = os.path.join(POSTS_DIR, f"geoai_steps_{stamp}.png")
        d.find_element(By.ID, "steps").screenshot(out)
        log(f"따라하기 도식 생성: {out} ({len(steps)}단계)")
        return out
    finally:
        d.quit()


if __name__ == "__main__":            # 단독 시험: 샘플 단계로 한 장 그려 본다
    make_steps({
        "title": "QGIS 입문 | 처음 열고 무엇부터 해보면 되나",
        "howto": [
            ("QGIS 설치", "qgis.org 에서 장기 릴리스(LTR) 판을 받아 설치합니다"),
            ("새 프로젝트", "프로젝트 > 새로 만들기 로 빈 작업창을 엽니다"),
            ("레이어 추가", "레이어 > 레이어 추가 > 벡터 레이어 에서 shp 파일을 고릅니다"),
            ("좌표계 확인", "오른쪽 아래 EPSG 표시를 눌러 EPSG:5186 인지 봅니다"),
            ("속성 보기", "레이어에서 오른쪽 클릭 > 속성 테이블 열기 로 값을 확인합니다"),
        ],
    })
