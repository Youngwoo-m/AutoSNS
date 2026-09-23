"""제목/날짜로 재난안전 테마의 배너 이미지(PNG)를 만든다.

별도 설치 없이, 헤드리스 Chrome 으로 HTML 배너를 렌더링해 캡처한다.
직접 만든 디자인이라 저작권 걱정이 없고 항상 주제와 일치한다.

디자인: '경보 테이프' — 검정 바탕에 안전 표지(노랑/검정 사선) 모티브.
학과명은 config.blog.banner_dept 로 바꿀 수 있다(없으면 아래 기본값).
"""
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from common import POSTS_DIR, load_config, log

DEFAULT_DEPT = "세명대학교 재난안전학과"

HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
  body {{ margin:0; padding:0; background:#fff; }}
  #banner {{
    width:1000px; height:420px; box-sizing:border-box; padding:60px 64px 56px;
    background:#111827; color:#fff;
    font-family:'Apple SD Gothic Neo','Malgun Gothic','맑은 고딕',sans-serif;
    position:relative; overflow:hidden; display:flex; flex-direction:column;
  }}
  /* 위·아래 안전 테이프(노랑/검정 사선) */
  .tape {{
    position:absolute; left:0; top:0; width:100%; height:20px;
    background:repeating-linear-gradient(45deg,#facc15 0 26px,#111827 26px 52px);
  }}
  .tape.b {{ top:auto; bottom:0; }}
  .badge {{
    display:inline-block; align-self:flex-start; border:3px solid #facc15; color:#facc15;
    font-weight:800; padding:8px 20px; font-size:23px; letter-spacing:3px;
  }}
  .mid {{ flex:1; display:flex; align-items:center; }}
  .title {{
    font-size:{size}px; font-weight:800; line-height:1.26; max-width:660px;
    letter-spacing:-.5px; word-break:keep-all;   /* 한글이 단어 중간에서 끊기지 않게 */
  }}
  .foot {{ font-size:24px; color:#9ca3af; }}
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


def _title_size(title):
    """제목이 길면 글자를 줄여 두 줄 안에 들어오게 한다."""
    n = len(title)
    if n <= 20:
        return 54
    return 48 if n <= 26 else 42


def make_banner(title, date_str, badge="DISASTER BRIEFING"):
    # 너무 긴 제목은 배너용으로 줄임 (부제만 남김). '|'(부제|브랜드) 를 먼저 확인.
    short = title
    for sep in ("|", "–", "—", ":", "-"):
        if sep in short:
            short = short.split(sep, 1)[0].strip()
            break
    dept = ((load_config().get("blog", {}) or {}).get("banner_dept")
            or DEFAULT_DEPT)
    html = HTML.format(title=short, date=date_str, dept=dept, badge=badge,
                       size=_title_size(short))
    html_path = os.path.join(POSTS_DIR, "_banner.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    o = Options()
    o.add_argument("--headless=new")
    o.add_argument("--window-size=1100,560")
    o.add_argument("--force-device-scale-factor=2")  # 선명하게
    o.add_argument("--hide-scrollbars")
    d = webdriver.Chrome(options=o)
    try:
        d.get("file:///" + html_path.replace("\\", "/"))
        time.sleep(1.2)
        out = os.path.join(POSTS_DIR, "banner.png")
        d.find_element(By.ID, "banner").screenshot(out)
        log(f"배너 생성: {out}")
        return out
    finally:
        d.quit()


if __name__ == "__main__":
    from datetime import datetime
    p = make_banner("2026년 6월 둘째 주 재난안전 뉴스 브리핑 – 산사태 점검부터",
                    f"{datetime.now():%Y년 %m월 %d일}")
    print(p)
