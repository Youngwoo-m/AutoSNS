"""로컬 HTML + 헤드리스 Chrome 으로 세로(9:16) Shorts 프레임 PNG 를 만든다.

- 장면(scene)마다 1080x1920 프레임 1장.
- KoPubWorld Dotum 폰트(@font-face), word-break:keep-all + text-wrap:pretty 로
  단어 중간 줄바꿈·한 글자 위도우를 원천 차단, JS 오토핏으로 항상 카드 안에 맞춤.
- 글자는 가운데 정렬, 약간 작게. 첫 장면은 표지(그라데이션).
- 본문 장면 하단에는 뉴스 원본 이미지(data['news_images'])를 순서대로 넣는다.

인터페이스: make_frames(data) -> [png경로], data['frames'] 채움.
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from common import BASE_DIR, POSTS_DIR, load_config, log

W, H = 1080, 1920  # Shorts 9:16

# 폰트는 setup 폴더의 공용 FONTS/ 에 있다(프로젝트 폴더의 한 단계 위).
DEFAULT_FONT_DIR = os.path.join(os.path.dirname(BASE_DIR), "FONTS")


def _esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _file_url(path):
    return "file:///" + os.path.abspath(path).replace("\\", "/")


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


HEADER_TEXT = "SMU 재난안전뉴스"   # 기본값. config.video.header_text 로 덮어씀(에디션별)


def _topbar(header):
    # 화면 상단에 크게(폭 70%로 자동 스케일) 들어가는 채널 헤더
    return (f'<div class="topbar"><span class="th">{_esc(header)}</span>'
            f'<div class="thbar"></div></div>')


def _footer_html(footer, logo, extra=""):
    # 하단: [마스코트 로고] + "세명대학교 재난안전학과"(폭 40%로 자동 스케일)
    img = f'<img class="footlogo" src="{_file_url(logo)}">' if logo else ""
    return (f'<div class="footer {extra}">{img}'
            f'<span class="foottext">{_esc(footer)}</span></div>')


def _bg_html(path):
    """장면 전체를 채우는 배경 이미지(Firefly 등) + 가독성용 어두운 스크림.

    배경이 있으면 프레임에 hasbg 클래스가 붙어 글자색이 밝게 바뀐다(_build_html).
    """
    if not path:
        return ""
    return (f'<div class="bgfill"><img src="{_file_url(path)}"></div>'
            f'<div class="scrim"></div>')


def _cover_html(idx, heading, lines, footer, logo, header, bg=""):
    title = _esc(heading) or "재난안전 브리핑"
    sub = "".join(f'<div class="csub">{_esc(s)}</div>' for s in lines)
    hasbg = " hasbg" if bg else ""
    return f"""
    <div class="frame cover{hasbg}" id="frame{idx}">
      {_bg_html(bg)}
      <div class="cbar"></div>
      {_topbar(header)}
      <div class="cinner">
        <div class="fit">
          <div class="ctitle">{title}</div>
          {sub}
        </div>
      </div>
      {_footer_html(footer, logo, "cfooter")}
    </div>"""


def _ox_mark(answer):
    """O/X 퀴즈 정답용 큰 색상 마크(초록 원 / 빨강 X). em 단위라 오토핏에 함께 스케일된다."""
    a = (answer or "").strip().upper()
    if a in ("O", "⭕"):
        return '<div class="oxmark ox-o"></div>'
    if a in ("X", "❌", "✕"):
        return '<div class="oxmark ox-x"></div>'
    return ""


def _content_html(idx, heading, lines, footer, img_path, logo, header, bg="", answer=""):
    body = "".join(f'<div class="sent">{_esc(s)}</div>' for s in lines)
    mark_html = _ox_mark(answer)
    img_html = ""
    # 배경 이미지를 쓰면 본문 중앙의 작은 뉴스 사진은 생략(배경과 중복·산만)
    if img_path and not bg:
        img_html = f'<div class="newsimg"><img src="{_file_url(img_path)}"></div>'
    hasbg = " hasbg" if bg else ""
    return f"""
    <div class="frame content{hasbg}" id="frame{idx}">
      {_bg_html(bg)}
      <div class="accent"></div>
      {_topbar(header)}
      <div class="pad">
        <div class="body-area">
          <div class="fit">
            <div class="heading">{_esc(heading)}</div>
            {mark_html}
            {body}
          </div>
        </div>
        {img_html}
        {_footer_html(footer, logo)}
      </div>
    </div>"""


def _resolve_bg(path):
    """배경 이미지 경로 정규화: 절대경로면 그대로, 상대경로면 프로젝트 기준으로."""
    if not path:
        return ""
    p = path if os.path.isabs(path) else os.path.normpath(os.path.join(BASE_DIR, path))
    if not os.path.exists(p):
        log(f"경고: 배경 이미지 없음 → 흰 배경으로 대체: {path}")
        return ""
    return p


def _build_html(scenes, footer, logo, font_dir, source_images, header, bg_images=None):
    bg_images = bg_images or {}
    blocks = []
    for i, s in enumerate(scenes):
        heading = s.get("heading", "")
        lines = s.get("lines", [])
        # 장면별 배경: scene['bg_image'] 우선, 없으면 data['bg_images'][i]
        bg = _resolve_bg(s.get("bg_image") or bg_images.get(str(i)) or "")
        if i == 0:
            blocks.append(_cover_html(i, heading, lines, footer, logo, header, bg))
        else:
            # 장면이 근거한 기사 사진만 붙인다(내용-사진 일치).
            si = s.get("src_idx")
            img = source_images.get(str(si), "") if si is not None else ""
            blocks.append(_content_html(i, heading, lines, footer, img, logo, header,
                                        bg, s.get("answer", "")))
    frames_html = "\n".join(blocks)
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
    {_font_face(font_dir)}
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ background:#fff; font-family:'KoPub','Segoe UI Emoji','Apple Color Emoji',sans-serif;
            word-break:keep-all; text-wrap:pretty; -webkit-font-smoothing:antialiased;
            text-align:center; }}
    .frame {{ width:{W}px; height:{H}px; position:relative; overflow:hidden; background:#fff; }}
    /* ---- 장면 전체 배경 이미지(Firefly 등) + 가독성 스크림 ---- */
    .bgfill {{ position:absolute; inset:0; z-index:0; }}
    .bgfill img {{ width:100%; height:100%; object-fit:cover; }}
    .scrim {{ position:absolute; inset:0; z-index:1;
             background:
               linear-gradient(180deg, rgba(6,16,34,.82) 0%, rgba(6,16,34,.34) 24%,
                 rgba(6,16,34,.34) 70%, rgba(6,16,34,.9) 100%),
               rgba(6,16,34,.40); }}
    /* 배경이 있으면 본문·헤더·푸터 글자를 밝게(사진 위 가독성) */
    .hasbg .topbar {{ z-index:4; }}
    .hasbg .topbar .th {{ color:#ffffff; text-shadow:0 3px 18px rgba(0,0,0,.55); }}
    .hasbg .content .pad {{ z-index:2; }}
    .hasbg .heading {{ color:#ffffff; text-shadow:0 3px 18px rgba(0,0,0,.6); }}
    .hasbg .sent {{ color:#eef4ff; text-shadow:0 2px 14px rgba(0,0,0,.6); }}
    .hasbg .footer .foottext {{ color:#ffffff; text-shadow:0 2px 12px rgba(0,0,0,.6); }}
    .hasbg.cover .cinner {{ z-index:2; }}
    .hasbg.cover .cfooter {{ z-index:2; }}
    /* ---- 상단 채널 헤더(폭 70%로 자동 스케일) ---- */
    /* top 을 220px 로 내려 유튜브/인스타 썸네일 상단 크롭(약 240px)에도 헤더가 보이게 함 */
    .topbar {{ position:absolute; top:220px; left:0; right:0; text-align:center; z-index:3; }}
    .topbar .th {{ display:inline-block; white-space:nowrap; font-weight:800;
             color:#12284c; letter-spacing:-2px; line-height:1; font-size:96px; }}
    .topbar .thbar {{ width:{int(W*0.34)}px; height:9px; background:#e63946; margin:20px auto 0;
             border-radius:6px; }}
    .cover .topbar .th {{ color:#ffd24a; text-shadow:0 3px 16px rgba(0,0,0,.35); }}
    /* ---- 본문 프레임 ---- */
    .content .accent {{ position:absolute; left:0; top:0; width:18px; height:100%;
             background:#e63946; }}
    .content .pad {{ position:absolute; inset:0; padding:375px 96px 235px 108px;
             display:flex; flex-direction:column; align-items:center; }}
    .body-area {{ flex:1; display:flex; flex-direction:column; justify-content:center;
             align-items:center; overflow:hidden; margin:20px 0; width:100%; }}
    .heading {{ font-weight:800; color:#12284c; font-size:2.5em; line-height:1.25;
             letter-spacing:-.5px; margin-bottom:.5em; }}
    .sent {{ font-weight:500; color:#273244; font-size:1.3em; line-height:1.5;
             margin:.36em 0; letter-spacing:-.3px; }}
    /* ---- O/X 퀴즈 정답 마크(초록 원 / 빨강 X). em 단위 → 오토핏에 함께 스케일 ---- */
    .oxmark {{ margin:.18em auto .42em; }}
    .ox-o {{ width:4.6em; height:4.6em; border:.62em solid #1fc98e; border-radius:50%;
             box-shadow:0 .16em .6em rgba(0,0,0,.45); }}
    .ox-x {{ width:4.6em; height:4.6em; position:relative; }}
    .ox-x::before, .ox-x::after {{ content:""; position:absolute; left:50%; top:50%;
             width:5.6em; height:.62em; background:#ff5764; border-radius:.31em;
             box-shadow:0 .16em .6em rgba(0,0,0,.45); }}
    .ox-x::before {{ transform:translate(-50%,-50%) rotate(45deg); }}
    .ox-x::after  {{ transform:translate(-50%,-50%) rotate(-45deg); }}
    .fit {{ font-size:40px; }}
    .newsimg {{ width:100%; margin:6px 0 20px; }}
    .newsimg img {{ width:100%; max-height:560px; object-fit:cover; border-radius:26px;
             box-shadow:0 8px 30px rgba(12,40,76,.18); }}
    .footer {{ display:flex; align-items:center; justify-content:center; gap:20px;
             width:100%; }}
    .footer .foottext {{ font-weight:800; color:#12284c; font-size:32px;
             letter-spacing:-.3px; white-space:nowrap; }}
    .footer .footlogo {{ height:64px; width:auto; }}
    .cfooter .foottext {{ color:#ffffff; }}
    /* ---- 표지 프레임 ---- */
    .cover {{ background:linear-gradient(155deg,#0b2447 0%,#19376d 55%,#2a4a86 100%);
             color:#fff; display:flex; flex-direction:column; align-items:center;
             padding:375px 100px 265px 108px; }}
    .cover .cbar {{ position:absolute; left:0; top:0; width:22px; height:100%;
             background:#e63946; }}
    .cover .cinner {{ flex:1; display:flex; flex-direction:column; justify-content:center;
             align-items:center; }}
    .cover .fit {{ font-size:48px; margin-top:44px; }}
    .ctitle {{ font-weight:800; font-size:3.0em; line-height:1.2; margin:.1em 0 .4em;
             letter-spacing:-1px; text-shadow:0 2px 18px rgba(0,0,0,.28); }}
    .csub {{ font-weight:500; font-size:1.25em; line-height:1.45; opacity:.96;
             margin:.16em 0; }}
    .cfooter {{ color:#c9d4e6; }}
    </style></head><body>
    {frames_html}
    <script>
    document.fonts.ready.then(function(){{
      // 이미지 로드까지 기다렸다가 오토핏(높이 계산 정확도)
      var imgs = Array.prototype.slice.call(document.images);
      Promise.all(imgs.map(function(im){{
        return im.complete ? Promise.resolve() : new Promise(function(res){{
          im.onload = im.onerror = res;
        }});
      }})).then(function(){{
        // 상단 헤더를 화면 폭 56%에 맞춰 자동 스케일(썸네일 세이프존 고려해 축소)
        var TARGET = {W} * 0.56;
        document.querySelectorAll('.topbar .th').forEach(function(th){{
          var w = th.getBoundingClientRect().width;
          if (w > 0) {{
            var base = parseFloat(getComputedStyle(th).fontSize);
            th.style.fontSize = (base * TARGET / w) + 'px';
          }}
        }});
        // 하단 학과명을 화면 폭 60%(기존 40%의 1.5배)로 확대 + 로고를 글자 높이에 맞춤
        var FTARGET = {W} * 0.60;
        document.querySelectorAll('.frame').forEach(function(frame){{
          var ft = frame.querySelector('.foottext');
          if (!ft) return;
          var w = ft.getBoundingClientRect().width;
          if (w > 0) {{
            var base = parseFloat(getComputedStyle(ft).fontSize);
            ft.style.fontSize = (base * FTARGET / w) + 'px';
          }}
          var logo = frame.querySelector('.footlogo');
          if (logo) {{ logo.style.height = (ft.getBoundingClientRect().height * 1.7) + 'px'; }}
        }});
        document.querySelectorAll('.frame').forEach(function(frame){{
          var fit = frame.querySelector('.fit');
          var box = frame.querySelector('.body-area') || frame.querySelector('.cinner');
          if(!fit || !box) return;
          var size = parseFloat(getComputedStyle(fit).fontSize);
          var guard = 0;
          while (fit.scrollHeight > box.clientHeight && size > 20 && guard < 500) {{
            size -= 1; fit.style.fontSize = size + 'px'; guard++;
          }}
          var g2 = 0;
          while (fit.scrollHeight > box.clientHeight && g2 < 6) {{
            fit.style.letterSpacing = (-0.3 - g2*0.2) + 'px'; g2++;
          }}
        }});
        window.__fitDone = true;
      }});
    }});
    </script>
    </body></html>"""


def make_frames(data):
    cfg = load_config()
    lcfg = cfg.get("local_render", {})
    font_dir = lcfg.get("font_dir") or DEFAULT_FONT_DIR
    footer = cfg.get("footer_text", "세명대학교 재난안전학과")
    # 상단 배너: data 로 넘기면 그걸 우선(개별 영상용), 없으면 config/기본값
    header = (data.get("header_text")
              or cfg.get("video", {}).get("header_text", HEADER_TEXT))
    logo = cfg.get("footer_logo", "")
    if logo and not os.path.isabs(logo):
        logo = os.path.normpath(os.path.join(BASE_DIR, logo))
    if logo and not os.path.exists(logo):
        log(f"경고: footer_logo 파일 없음 → 로고 생략: {logo}")
        logo = ""
    scenes = data["scenes"]
    source_images = data.get("source_images") or {}
    bg_images = data.get("bg_images") or {}

    html_doc = _build_html(scenes, footer, logo, font_dir, source_images, header, bg_images)
    stamp = data.get("stamp") or time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(POSTS_DIR, f"frames_{stamp}")
    os.makedirs(out_dir, exist_ok=True)
    html_path = os.path.join(out_dir, "_frames.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_doc)

    o = Options()
    o.add_argument("--headless=new")
    o.add_argument(f"--window-size={W+80},{H+80}")
    o.add_argument("--hide-scrollbars")
    o.add_argument("--allow-file-access-from-files")
    o.add_argument("--lang=ko-KR")
    d = webdriver.Chrome(options=o)
    pngs = []
    try:
        d.get("file:///" + html_path.replace("\\", "/"))
        for _ in range(60):
            time.sleep(0.25)
            if d.execute_script("return window.__fitDone === true"):
                break
        time.sleep(0.4)
        for i in range(len(scenes)):
            out = os.path.join(out_dir, f"{i+1:02d}.png")
            d.find_element(By.ID, f"frame{i}").screenshot(out)
            pngs.append(out)
        log(f"Shorts 프레임 PNG {len(pngs)}장 생성(이미지 {len(source_images)}장 포함): {out_dir}")
    finally:
        d.quit()

    data["frames"] = pngs
    with open(os.path.join(POSTS_DIR, f"{stamp}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return pngs


if __name__ == "__main__":
    import glob
    files = sorted(glob.glob(os.path.join(POSTS_DIR, "*.json")))
    if not files:
        raise SystemExit("먼저 generate_script.py 를 실행하세요.")
    with open(files[-1], "r", encoding="utf-8") as f:
        d = json.load(f)
    for p in make_frames(d):
        print(p)
