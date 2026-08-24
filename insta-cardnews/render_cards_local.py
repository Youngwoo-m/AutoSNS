"""로컬 HTML + 헤드리스 Chrome 으로 카드뉴스 PNG 를 만든다. (Gamma 대체)

장점:
- KoPubWorld Dotum 폰트를 그대로 사용(@font-face).
- word-break:keep-all → 단어 중간에서 줄바꿈 안 됨.
- text-wrap:pretty → 마지막 줄에 한 글자만 남는 위도우를 CSS 레벨에서 차단.
- JS 오토핏 → 텍스트가 카드 밖으로 넘치면 글자 크기·자간을 자동으로 줄여 항상 맞춤.
- Gamma 크레딧 불필요, 폰트/자간/레이아웃 완전 제어.

인터페이스는 gamma_make.make_cards 와 동일: make_cards(data) -> [png경로], data['images'] 채움.
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from common import BASE_DIR, POSTS_DIR, load_config, log

CARD_PX = 1080  # 인스타 1:1 권장 해상도(2x 캡처로 실제 2160px)

# 폰트는 setup 폴더의 공용 FONTS/ 에 있다(프로젝트 폴더의 한 단계 위).
DEFAULT_FONT_DIR = os.path.join(os.path.dirname(BASE_DIR), "FONTS")


def _esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _split_card(block):
    """카드 텍스트 블록 -> (heading, [sentences...]). 첫 비어있지 않은 줄이 제목."""
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    if not lines:
        return "", []
    return lines[0], lines[1:]


def _font_face(font_dir):
    d = font_dir.replace("\\", "/")
    return f"""
    @font-face {{ font-family:'KoPub'; font-weight:300; font-style:normal;
      src:url("file:///{d}/KoPubWorld Dotum_Pro Light.otf"); }}
    @font-face {{ font-family:'KoPub'; font-weight:500; font-style:normal;
      src:url("file:///{d}/KoPubWorld Dotum_Pro Medium.otf"); }}
    @font-face {{ font-family:'KoPub'; font-weight:800; font-style:normal;
      src:url("file:///{d}/KoPubWorld Dotum_Pro Bold.otf"); }}
    """


def _cover_html(idx, heading, sents, footer):
    # 표지: 첫 줄=날짜 킥커, 둘째 줄=대표 제목(큼), 나머지=부제
    kicker = _esc(heading)
    title = _esc(sents[0]) if sents else "재난안전 뉴스"
    sub = "".join(f'<div class="csub">{_esc(s)}</div>' for s in sents[1:])
    return f"""
    <div class="card cover" id="card{idx}">
      <div class="cbar"></div>
      <div class="cinner">
        <div class="badge cbadge">⚠ 재난안전 뉴스 브리핑</div>
        <div class="fit">
          <div class="ckicker">{kicker}</div>
          <div class="ctitle">{title}</div>
          {sub}
        </div>
      </div>
      <div class="footer cfooter">{_esc(footer)}</div>
    </div>"""


def _content_html(idx, heading, sents, footer):
    body = "".join(f'<div class="sent">{_esc(s)}</div>' for s in sents)
    return f"""
    <div class="card content" id="card{idx}">
      <div class="accent"></div>
      <div class="pad">
        <div class="badge">재난안전 뉴스</div>
        <div class="body-area">
          <div class="fit">
            <div class="heading">{_esc(heading)}</div>
            {body}
          </div>
        </div>
        <div class="footer">{_esc(footer)}</div>
      </div>
    </div>"""


def _build_html(cards, footer, font_dir):
    blocks = []
    for i, c in enumerate(cards):
        heading, sents = _split_card(c)
        if i == 0:
            blocks.append(_cover_html(i, heading, sents, footer))
        else:
            blocks.append(_content_html(i, heading, sents, footer))
    cards_html = "\n".join(blocks)
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
    {_font_face(font_dir)}
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ background:#fff; font-family:'KoPub','Segoe UI Emoji','Apple Color Emoji',sans-serif;
            word-break:keep-all; text-wrap:pretty; -webkit-font-smoothing:antialiased; }}
    .card {{ width:{CARD_PX}px; height:{CARD_PX}px; position:relative; overflow:hidden;
             background:#fff; }}
    /* ---- 본문 카드 ---- */
    .content .accent {{ position:absolute; left:0; top:0; width:14px; height:100%;
             background:#e63946; }}
    .content .pad {{ position:absolute; inset:0; padding:84px 76px 68px 90px;
             display:flex; flex-direction:column; }}
    .badge {{ display:inline-block; align-self:flex-start; background:#eaf0f8; color:#12284c;
             font-weight:800; font-size:30px; padding:12px 26px; border-radius:40px;
             letter-spacing:-.3px; }}
    .body-area {{ flex:1; display:flex; flex-direction:column; justify-content:center;
             overflow:hidden; margin:26px 0; }}
    .heading {{ font-weight:800; color:#12284c; font-size:2.35em; line-height:1.24;
             letter-spacing:-.5px; margin-bottom:.55em; }}
    .sent {{ font-weight:500; color:#273244; font-size:1.15em; line-height:1.5;
             padding-left:34px; position:relative; margin:.30em 0; letter-spacing:-.3px; }}
    .sent::before {{ content:''; position:absolute; left:6px; top:.62em; width:12px;
             height:12px; border-radius:50%; background:#e63946; opacity:.85; }}
    .fit {{ font-size:40px; }}
    .footer {{ text-align:center; font-weight:300; color:#94a0b0; font-size:26px;
             letter-spacing:.3px; }}
    /* ---- 표지 카드 ---- */
    .cover {{ background:linear-gradient(135deg,#0b2447 0%,#19376d 55%,#2a4a86 100%);
             color:#fff; display:flex; flex-direction:column;
             padding:96px 84px 72px 96px; }}
    .cover .cbar {{ position:absolute; left:0; top:0; width:16px; height:100%;
             background:#e63946; }}
    .cover .cinner {{ flex:1; display:flex; flex-direction:column; justify-content:center; }}
    .cbadge {{ background:#ffb703; color:#0b2447; }}
    .cover .fit {{ font-size:40px; margin-top:36px; }}
    .ckicker {{ font-weight:500; font-size:1.05em; opacity:.9; letter-spacing:0; }}
    .ctitle {{ font-weight:800; font-size:3.1em; line-height:1.2; margin:.18em 0 .34em;
             letter-spacing:-1px; text-shadow:0 2px 16px rgba(0,0,0,.28); }}
    .csub {{ font-weight:500; font-size:1.25em; line-height:1.45; opacity:.96;
             margin:.12em 0; }}
    .cfooter {{ color:#c9d4e6; }}
    </style></head><body>
    {cards_html}
    <script>
    // 오토핏: .fit 이 body-area(또는 표지 cinner) 높이를 넘으면 글자 크기를 줄여 맞춘다.
    document.fonts.ready.then(function(){{
      document.querySelectorAll('.card').forEach(function(card){{
        var fit = card.querySelector('.fit');
        var box = card.querySelector('.body-area') || card.querySelector('.cinner');
        if(!fit || !box) return;
        var size = parseFloat(getComputedStyle(fit).fontSize);
        var guard = 0;
        while (fit.scrollHeight > box.clientHeight && size > 18 && guard < 400) {{
          size -= 1; fit.style.fontSize = size + 'px'; guard++;
        }}
        // 아주 살짝 넘치면 자간을 좁혀 마무리(한 글자 위도우 방지 보조)
        var g2 = 0;
        while (fit.scrollHeight > box.clientHeight && g2 < 6) {{
          fit.style.letterSpacing = (-0.3 - g2*0.2) + 'px'; g2++;
        }}
      }});
      window.__fitDone = true;
    }});
    </script>
    </body></html>"""


def make_cards(data):
    cfg = load_config()
    lcfg = cfg.get("local_render", {})
    font_dir = lcfg.get("font_dir") or DEFAULT_FONT_DIR
    footer = cfg.get("gamma", {}).get("footer_text", "세명대학교 재난안전학과")
    cards = data["cards"]

    html_doc = _build_html(cards, footer, font_dir)
    stamp = data.get("stamp") or time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(POSTS_DIR, f"cards_{stamp}")
    os.makedirs(out_dir, exist_ok=True)
    html_path = os.path.join(out_dir, "_cards.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_doc)

    o = Options()
    o.add_argument("--headless=new")
    o.add_argument("--window-size=1200,1300")
    o.add_argument("--force-device-scale-factor=2")  # 2160px 로 선명하게
    o.add_argument("--hide-scrollbars")
    o.add_argument("--allow-file-access-from-files")
    o.add_argument("--lang=ko-KR")
    d = webdriver.Chrome(options=o)
    pngs = []
    try:
        d.get("file:///" + html_path.replace("\\", "/"))
        # 폰트 로드 + 오토핏 완료 대기
        for _ in range(40):
            time.sleep(0.25)
            if d.execute_script("return window.__fitDone === true"):
                break
        time.sleep(0.4)
        for i in range(len(cards)):
            out = os.path.join(out_dir, f"{i+1:02d}.png")
            el = d.find_element(By.ID, f"card{i}")
            # 각 카드를 뷰포트 맨 위로 올려 확실히 페인트시킨 뒤 캡처.
            # 뷰포트 밖/경계 카드가 빈 이미지로 캡처되는 문제 방지(+작으면 재시도).
            for attempt in range(4):
                d.execute_script("arguments[0].scrollIntoView({block:'start'});", el)
                time.sleep(0.35)
                el.screenshot(out)
                if os.path.getsize(out) > 8000:
                    break
                log(f"카드 {i+1} 캡처가 너무 작음(시도 {attempt+1}/4) → 재시도")
                time.sleep(0.4)
            pngs.append(out)
        # 최종 검증: 1KB 미만(인스타 거부)이 있으면 실패 처리
        tiny = [p for p in pngs if os.path.getsize(p) < 8000]
        if tiny:
            raise RuntimeError(f"빈 카드 PNG 발생: {[os.path.basename(t) for t in tiny]}")
        log(f"로컬 카드 PNG {len(pngs)}장 생성: {out_dir}")
    finally:
        d.quit()

    data["images"] = pngs
    with open(os.path.join(POSTS_DIR, f"{stamp}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return pngs


if __name__ == "__main__":
    import glob
    files = sorted(glob.glob(os.path.join(POSTS_DIR, "*.json")))
    if not files:
        raise SystemExit("먼저 generate_cards.py 를 실행하세요.")
    with open(files[-1], "r", encoding="utf-8") as f:
        d = json.load(f)
    for p in make_cards(d):
        print(p)
