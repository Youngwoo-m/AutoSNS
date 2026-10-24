"""제목/날짜로 재난안전 테마의 배너 이미지(PNG)를 만든다.

별도 설치 없이, 헤드리스 Chrome 으로 HTML 배너를 렌더링해 캡처한다.
직접 만든 디자인이라 저작권 걱정이 없고 항상 주제와 일치한다.

디자인: '경보 테이프' — 검정 바탕에 안전 표지(노랑/검정 사선) 모티브.
학과명은 config.blog.banner_dept 로 바꿀 수 있다(없으면 아래 기본값).

모양은 기본이 정사각(1080x1080)이다. 네이버 블로그 앨범형·네이버 검색 썸네일·카톡
공유 카드가 모두 가운데를 정사각으로 잘라 쓰기 때문이다. 2.4:1 가로 배너를 쓰던 때는
좌우 29%씩 잘려 나가 제목 앞뒤와 학과명이 통째로 사라졌다(2026-10-13 확인).
가로 배너가 필요하면 config.blog.banner_shape="wide" 로 되돌린다.
"""
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from common import POSTS_DIR, load_config, log, start_chrome

import sys as _sys  # KoPub 글꼴(공용 shared/fonts)
_sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from shared.fonts import display_css  # noqa: E402

DEFAULT_DEPT = "세명대학교 재난안전학과"
DEFAULT_SHAPE = "square"

HTML = """<!doctype html><html><head><meta charset="utf-8"><style>""" + display_css(doubled=True) + """
  body {{ margin:0; padding:0; background:#fff; }}
  #banner {{
    width:1000px; height:420px; box-sizing:border-box; padding:52px 56px 48px;
    background:#111827; color:#fff;
    font-family:'Body','Apple SD Gothic Neo','Malgun Gothic','맑은 고딕',sans-serif;
    position:relative; overflow:hidden; display:flex; flex-direction:column;
  }}
  /* 위·아래 안전 테이프(노랑/검정 사선) */
  .tape {{
    position:absolute; left:0; top:0; width:100%; height:20px;
    background:repeating-linear-gradient(45deg,#facc15 0 26px,#111827 26px 52px);
  }}
  .tape.b {{ top:auto; bottom:0; }}
  .badge {{ font-family:'Body';
    display:inline-block; align-self:flex-start; border:3px solid #facc15; color:#facc15;
    font-weight:700; padding:8px 22px; font-size:27px; letter-spacing:3px;
  }}
  .mid {{ flex:1; display:flex; align-items:center; }}
  .title {{
    font-family:'Display'; font-size:{size}px; font-weight:400; line-height:1.26; max-width:720px;
    letter-spacing:-.5px; word-break:keep-all;   /* 한글이 단어 중간에서 끊기지 않게 */
  }}
  .foot {{ font-family:'Body'; font-size:27px; color:#9ca3af; }}
  .dept {{ color:#facc15; font-weight:700; }}
  .icon {{
    position:absolute; right:52px; top:50%; transform:translateY(-50%);
    font-size:200px; opacity:.13;
  }}
</style></head><body>
  <div id="banner">
    <div class="tape"></div>
    <div class="tape b"></div>
    <div class="badge">{badge}</div>
    <div class="mid"><div class="title">{title}</div></div>
    <div class="foot"><span class="dept">{dept}</span> · {date}</div>
    <div class="icon">⚠️</div>
  </div>
</body></html>"""


SQUARE_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>""" + display_css(doubled=True) + """
  body {{ margin:0; padding:0; background:#fff; }}
  #banner {{
    width:540px; height:540px; box-sizing:border-box; padding:46px 40px 40px;
    background:#111827; color:#fff;
    font-family:'Body','Apple SD Gothic Neo','Malgun Gothic','맑은 고딕',sans-serif;
    position:relative; overflow:hidden; display:flex; flex-direction:column;
  }}
  .tape {{
    position:absolute; left:0; top:0; width:100%; height:14px;
    background:repeating-linear-gradient(45deg,#facc15 0 18px,#111827 18px 36px);
  }}
  .tape.b {{ top:auto; bottom:0; }}
  .badge {{ font-family:'Body';
    display:inline-block; align-self:flex-start; border:2px solid #facc15; color:#facc15;
    font-weight:700; padding:6px 14px; font-size:19px; letter-spacing:2px;
  }}
  /* 제목은 가운데에 크게. 어디서 잘려도 읽히도록 좌우 여백을 넉넉히 둔다. */
  .mid {{ flex:1; display:flex; align-items:center; }}
  .title {{
    font-family:'Display'; font-size:{size}px; font-weight:400; line-height:1.3; max-width:470px;
    letter-spacing:-.5px; word-break:keep-all;
  }}
  .foot {{ font-family:'Body'; font-size:20px; color:#9ca3af; }}
  .dept {{ color:#facc15; font-weight:700; }}
</style></head><body>
  <div id="banner">
    <div class="tape"></div>
    <div class="tape b"></div>
    <div class="badge">{badge}</div>
    <div class="mid"><div class="title">{title}</div></div>
    <div class="foot"><span class="dept">{dept}</span> · {date}</div>
  </div>
</body></html>"""


def _square_size(title):
    """정사각은 가로가 좁아 글자를 줄여야 세 줄 안에 들어온다.

    제목 글꼴(Pretendard Black)은 KoPub 과 크기가 비슷해 원래 값으로 돌렸다(2026-10-14)."""
    n = len(title)
    if n <= 14:
        return 64
    if n <= 22:
        return 55
    if n <= 30:
        return 47
    return 41


def _title_size(title):
    """제목이 길면 글자를 줄여 두 줄 안에 들어오게 한다."""
    n = len(title)
    if n <= 20:
        return 68
    return 60 if n <= 26 else 52


BG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "banner_bg")
# 제목 키워드 → 배경 그림(assets/banner_bg/<이름>.png). 위에서부터 먼저 맞는 것을 쓴다.
BG_RULES = [
    ("survey", ("측량", "토목", "기술사", "GNSS", "기준점", "건설")),
    ("geoai", ("GeoAI", "위성", "드론", "GIS", "지리", "AI")),
    ("winter", ("겨울", "한중", "동절기", "한파", "결빙", "동결", "제설", "눈")),
    ("wildfire", ("산불", "화재", "소방", "불")),
    ("flood", ("침수", "홍수", "호우", "태풍", "풍수해", "하천", "장마")),
    ("quake", ("지진", "붕괴", "내진", "교량", "산사태")),
    ("shelter", ("대피", "민방위", "훈련", "이재민", "구호")),
    ("safety", ("안전", "산재", "중대", "추락", "비계", "작업")),
]


def pick_bg(title):
    """제목에서 주제를 찾아 디오라마 배경 경로를 돌려준다. 맞는 주제가 없으면 None(기존 디자인)."""
    for name, words in BG_RULES:
        if any(w in title for w in words):
            path = os.path.join(BG_DIR, name + ".png")
            if os.path.exists(path):
                return path
    return None


def apply_bg(html, bg):
    """배경 그림(글자 없는 이미지)을 깔고 위에 어두운 막을 씌운다. 글자는 HTML 그대로라 깨지지 않는다.
    bg 가 없으면 html 을 그대로 돌려준다(기존 디자인)."""
    if not bg:
        return html
    url = "file://" + os.path.abspath(bg).replace("\\", "/")
    css = ('#banner{background:linear-gradient(rgba(8,12,26,.38),rgba(8,12,26,.66)),'
           'url("%s") center/cover no-repeat !important}'
           '.grid,.glow,.icon{display:none !important}.title,.foot,.badge{text-shadow:0 2px 14px rgba(0,0,0,.65)}' % url)
    return html.replace("</style>", css + "</style>", 1)


def make_banner(title, date_str, badge="DISASTER BRIEFING", shape=None, bg=None):
    # 너무 긴 제목은 배너용으로 줄임 (부제만 남김). '|'(부제|브랜드) 를 먼저 확인.
    short = title
    for sep in ("|", "–", "—", ":", "-"):
        if sep in short:
            short = short.split(sep, 1)[0].strip()
            break
    blog_cfg = (load_config().get("blog", {}) or {})
    dept = blog_cfg.get("banner_dept") or DEFAULT_DEPT
    shape = (shape or blog_cfg.get("banner_shape") or DEFAULT_SHAPE).lower()
    if shape == "square":
        html = SQUARE_HTML.format(title=short, date=date_str, dept=dept, badge=badge,
                                  size=_square_size(short))
        window = "640,700"
    else:
        html = HTML.format(title=short, date=date_str, dept=dept, badge=badge,
                           size=_title_size(short))
        window = "1100,560"
    html = apply_bg(html, pick_bg(short) if bg is None else bg)   # bg=False 면 배경 그림 없이
    html_path = os.path.join(POSTS_DIR, "_banner.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    o = Options()
    o.add_argument("--headless=new")
    o.add_argument(f"--window-size={window}")
    o.add_argument("--force-device-scale-factor=2")  # 선명하게
    o.add_argument("--hide-scrollbars")
    o.add_argument("--allow-file-access-from-files")
    d = start_chrome(o)
    try:
        d.get("file:///" + html_path.replace("\\", "/"))
        time.sleep(1.2)
        out = os.path.join(POSTS_DIR, "banner.png")
        d.find_element(By.ID, "banner").screenshot(out)
        log(f"배너 생성({shape}): {out}")
        return out
    finally:
        d.quit()


if __name__ == "__main__":
    import argparse
    import shutil
    from datetime import datetime
    ap = argparse.ArgumentParser(description="배너 PNG 한 장 만들기(티스토리·블로거 글 맨 위 그림용)")
    ap.add_argument("--title", default="거창군 AI 재난안전 실증단지, 왜 주목받나")
    ap.add_argument("--shape", choices=("square", "wide"))
    ap.add_argument("--bg", help="배경 그림 경로(없으면 제목 키워드로 자동, --no-bg 면 끔)")
    ap.add_argument("--no-bg", action="store_true")
    ap.add_argument("--out", help="결과를 복사할 경로")
    a = ap.parse_args()
    p = make_banner(a.title, f"{datetime.now():%Y년 %m월 %d일}", shape=a.shape,
                    bg=False if a.no_bg else a.bg)
    if a.out:
        shutil.copyfile(p, a.out)
        p = a.out
    print(p)
