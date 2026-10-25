"""로컬 HTML + 헤드리스 Chrome 으로 카드뉴스 PNG 를 만든다(Gamma 없이).

2026-09-29 다시 설계(밝은 톤): Gamma 는 편당 크레딧 30 을 쓰고, 넘긴 문장을 스스로 요약·재배치
해서 원문에 없는 말(상자 제목 등)이 생긴다. 로컬 렌더러는 Claude 가 쓴 문장을 그대로
쓰되, Gamma 카드의 좋은 점(짙은 남색 바탕, 상자형 배치, 그림 있는 표지)은 살린다.

카드 종류(generate_cards 의 구성과 같다):
  1) 표지      — 위쪽에 주제 맞춤 실사 사진(Pexels, '자료 사진' 표기) → 남색으로 녹아들고,
                  큰 제목(쉼표 앞 핵심 어구만 파란 강조) + 핵심 한두 줄
  2) 뉴스 카드 — 이모지 칸 + 소제목, 문장을 두 줄씩 묶은 상자(왼쪽 파란 띠) 최대 3개
  3) 핵심 포인트 — '포인트 N.' 줄이 있으면 번호 배지 + 제목 + 설명 상자 3개
  4) 마무리    — 요약은 체크 목록, 마지막 당부('자세한 내용은 …')는 테두리 상자
공통: 위쪽에 '제천·충북 재난안전' 칩과 쪽번호, 아래쪽에 흰색 학과 로고. 넘치면 글자 크기를
자동으로 줄인다(word-break:keep-all 로 단어 중간에서 끊지 않는다).

인터페이스는 gamma_make.make_cards 와 같다: make_cards(data) -> [png], data['images'] 채움.
"""
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from common import BASE_DIR, POSTS_DIR, load_config, log

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from shared.fonts import require_fonts  # noqa: E402
from shared.stock_video import pick_query  # noqa: E402

CARD_PX = 1080
ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
DEFAULT_FONT_DIR = os.path.join(ROOT, "assets", "FONTS")
LOGO_SRC = os.path.join(ROOT, "assets", "image", "SMU_logo.png")
CHIP = "제천·충북 재난안전"

# 표지 사진용 검색어 — 뉴스용 영상 검색어(shared.stock_video)를 그대로 쓰되 사진에 맞게 조금 바꾼다.
PHOTO_QUERY = {"heavy rain street": "heavy rain city street", "fire smoke dark": "fire smoke",
               "drone flying sky": "drone flying", "city lights night timelapse": "city night lights",
               "clouds sky timelapse": "dramatic clouds sky", "busy market street": "traditional market"}

EMOJI_RE = re.compile(r"^([\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]+)\s*")


def _e(s):
    return html.escape(s or "", quote=True)


def _url(p):
    return "file:///" + os.path.abspath(p).replace("\\", "/")


def _white_logo(out_dir):
    """파란 학과 로고를 흰색으로(남색 바탕에서 파란 글씨가 흐려진다)."""
    from PIL import Image
    out = os.path.join(out_dir, "_logo_white.png")
    if not os.path.exists(out) and os.path.exists(LOGO_SRC):
        im = Image.open(LOGO_SRC).convert("RGBA")
        white = Image.new("RGBA", im.size, (255, 255, 255, 0))
        white.putalpha(im.getchannel("A"))
        white.save(out)
    return out if os.path.exists(out) else ""


def _cover_photo(data, out_dir):
    """표지에 쓸 주제 맞춤 사진(Pexels). 실패하면 "" → 사진 없는 표지."""
    key = (load_config().get("pexels", {}) or {}).get("api_key")
    if not key:
        return ""
    q = pick_query([data.get("title") or "", " ".join(str(c) for c in data.get("cards") or [])])
    q = PHOTO_QUERY.get(q, q.replace(" timelapse", ""))
    q = data.get("cover_query") or q      # 뉴스가 아닌 카드(채용정보 등)는 부르는 쪽이 정한다
    try:
        u = "https://api.pexels.com/v1/search?" + urllib.parse.urlencode(
            {"query": q, "orientation": "landscape", "per_page": 6})
        req = urllib.request.Request(u, headers={"Authorization": key, "User-Agent": "smuds/1.0"})
        photos = json.loads(urllib.request.urlopen(req, timeout=20).read().decode()).get("photos", [])
        # 글자가 든 사진은 표지 제목과 겹쳐 지저분하다
        photos = [p for p in photos if not re.search(r"\b(text|sign|logo|word|letter)s?\b",
                                                    (p.get("alt") or "").lower())]
        if not photos:
            return ""
        p = photos[0]
        path = os.path.join(out_dir, f"_cover_{p['id']}.jpg")
        req = urllib.request.Request(p["src"]["large2x"], headers={"User-Agent": "smuds/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r, open(path, "wb") as w:
            w.write(r.read())
        data["cover_photo"] = {"query": q, "id": p["id"], "by": p.get("photographer"),
                               "url": p.get("url")}
        log(f"표지 사진: '{q}' (Pexels {p['id']}, by {p.get('photographer')})")
        return path
    except Exception as e:
        log(f"표지 사진 실패('{q}') → 사진 없는 표지: {type(e).__name__}")
        return ""


def _split(block):
    """카드 블록 → (이모지, 제목, [문단(빈 줄로 나뉜 줄 묶음)])."""
    lines = [ln.rstrip() for ln in block.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        return "", "", []
    head = lines[0].strip()
    m = EMOJI_RE.match(head)
    emoji, title = (m.group(1), head[m.end():]) if m else ("", head)
    paras, cur = [], []
    for ln in lines[1:]:
        if ln.strip():
            cur.append(ln.strip())
        elif cur:
            paras.append(cur)
            cur = []
    if cur:
        paras.append(cur)
    return emoji, title, paras


def _chrome(idx, total):
    return (f'<div class="top"><span class="chip">{_e(CHIP)}</span>'
            f'<span class="pg">{idx + 1}/{total}</span></div>')


def _footer(logo):
    return (f'<div class="foot"><img src="{_url(logo)}"></div>' if logo
            else '<div class="foot"><span class="foottext">세명대학교 재난안전학과</span></div>')


def _title_html(title):
    """쉼표·줄표 앞 핵심 어구만 파란색으로."""
    m = re.match(r"^(.{2,14}?)([,，—–:])\s*(.+)$", title)
    if m:
        return f'<span class="hl">{_e(m.group(1))}{_e(m.group(2))}</span> {_e(m.group(3))}'
    return _e(title)


def _cover(idx, total, block, photo, logo):
    _, title, paras = _split(block)
    subs = [s for p in paras for s in p][:3]
    img = (f'<div class="photo" style="background-image:url(\'{_url(photo)}\')"></div>'
           f'<div class="photo-fade"></div><span class="stock">자료 사진</span>') if photo else \
          '<div class="nophoto"></div>'
    return f"""
    <div class="card cover" id="card{idx}">
      {img}{_chrome(idx, total)}
      <div class="cbody fit">
        <div class="ctitle">{_title_html(title)}</div>
        {''.join(f'<div class="csub">{_e(s)}</div>' for s in subs)}
      </div>
      {_footer(logo)}
    </div>"""


def _news(idx, total, block, logo):
    emoji, title, paras = _split(block)
    if len(paras) > 1:
        # 빈 줄로 나뉜 소항목(예: '🔥 화재 예방' + 설명)이면 문단마다 상자 하나. 두 줄씩
        # 기계적으로 묶으면 소항목 제목과 내용이 다른 상자로 갈렸다(9/23 추석 안전수칙).
        groups = paras[:4]
    else:
        sents = [s for p in paras for s in p]
        groups = [sents[i:i + 2] for i in range(0, len(sents), 2)][:3]

    def box(g):
        head, rest = (g[0], g[1:]) if len(g) > 1 and len(g[0]) <= 16 and len(paras) > 1 else ("", g)
        return ('<div class="box">' + (f'<div class="btitle">{_e(head)}</div>' if head else "")
                + "".join(f'<p>{_e(s)}</p>' for s in rest) + "</div>")
    boxes = "".join(box(g) for g in groups)
    return f"""
    <div class="card" id="card{idx}">
      {_chrome(idx, total)}
      <div class="body fit">
        <div class="head">{f'<span class="emo">{emoji}</span>' if emoji else ''}
          <span class="htitle">{_e(title)}</span></div>
        <div class="boxes">{boxes}</div>
      </div>
      {_footer(logo)}
    </div>"""


def _points(idx, total, block, logo):
    emoji, title, paras = _split(block)
    items = []
    for p in paras:
        m = re.match(r"^포인트\s*(\d+)\s*[.．:]\s*(.+)$", p[0])
        if m:
            items.append((m.group(1), m.group(2), p[1:]))
        elif items:
            items[-1][2].extend(p)
    rows = "".join(
        f'<div class="pt"><span class="num">{_e(n)}</span><div class="ptxt">'
        f'<div class="ptitle">{_e(t)}</div>' + "".join(f'<p>{_e(s)}</p>' for s in body[:2]) +
        "</div></div>" for n, t, body in items[:3])
    return f"""
    <div class="card" id="card{idx}">
      {_chrome(idx, total)}
      <div class="body fit">
        <div class="head">{f'<span class="emo">{emoji}</span>' if emoji else ''}
          <span class="htitle">{_e(title)}</span></div>
        <div class="pts">{rows}</div>
      </div>
      {_footer(logo)}
    </div>"""


def _closing(idx, total, block, logo):
    emoji, title, paras = _split(block)
    sents = [s for p in paras for s in p]
    # 당부 문장('자세한 내용은 프로필…', '…참고하세요')은 체크 목록이 아니라 아래 상자로.
    is_cta = lambda s: bool(re.search(r"자세한|프로필|참고|확인하세요|주목해|함께 지켜", s))
    summary = [s for s in sents if not is_cta(s)]
    cta = [s for s in sents if is_cta(s)]
    rows = "".join(f'<div class="chk"><span class="tick">✓</span><span>{_e(s)}</span></div>'
                   for s in summary[:6])
    ctab = ('<div class="cta">' + "".join(f'<p>{_e(s)}</p>' for s in cta[:2]) + "</div>") if cta else ""
    return f"""
    <div class="card" id="card{idx}">
      {_chrome(idx, total)}
      <div class="body fit">
        <div class="head">{f'<span class="emo">{emoji}</span>' if emoji else ''}
          <span class="htitle">{_e(title)}</span></div>
        <div class="chks">{rows}</div>{ctab}
      </div>
      {_footer(logo)}
    </div>"""


def _cub(inner, cls="", style=""):
    """입체 블록: 앞면(내용) + 오른쪽면 + 윗면. 두께는 --d(em). 3D 장면(.scene3d) 안에서만 입체로 보인다."""
    return (f'<div class="cub {cls}" style="{style}"><div class="cf">{inner}</div>'
            f'<i class="cr"></i><i class="ct"></i></div>')


def _info(idx, total, block, spec, logo):
    """인포그래픽 카드(infographic.plan 이 설계). 소제목은 카드 원문 그대로 쓴다.

    2026-10-23: 평면 상자 → 입체 블록(CSS 3D). 숫자 크기로 높이를 정하지 않는다 — 단위가
    다른 값이라 높이가 곧 비교로 읽히면 안 된다. 입체감은 장식이고, 글자는 앞면에 그대로."""
    emoji, title, _ = _split(block)
    t = spec.get("type")
    if t == "stat":
        its = spec.get("items")[:3]
        body = '<div class="stats n%d">' % len(its) + "".join(
            _cub(f'<div class="sval">{_e(i["value"])}</div><div class="slab">{_e(i["label"])}</div>',
                 "stat", f"--z:{k * 28}px") for k, i in enumerate(its)) + "</div>"
    elif t == "flow":
        st = spec.get("steps")[:5]
        n = len(st)
        body = f'<div class="flow n{n}">' + '<span class="arrow">&#9656;</span>'.join(
            _cub(f'<span class="snum">{k + 1}</span><span class="stxt">{_e(x)}</span>', "step",
                 f"--lift:{k * (1.1 if n <= 4 else 0.9)}em;--d:{0.7 + 0.15 * k}em")
            for k, x in enumerate(st)) + "</div>"
    else:
        l, r = spec.get("left"), spec.get("right")
        col = lambda c, cls, sty: _cub(
            f'<div class="stitle">{_e(c["title"])}</div>'
            + "".join(f'<p>{_e(x)}</p>' for x in (c.get("points") or [])[:3]), f"side {cls}", sty)
        body = (f'<div class="compare">{col(l, "left", "--d:.12em")}<span class="vs">VS</span>'
                f'{col(r, "right", "--d:.75em;--z:46px")}</div>')
    note = f'<div class="note">{_e(spec.get("note", ""))}</div>' if spec.get("note") else ""
    return f"""
    <div class="card info" id="card{idx}">
      {_chrome(idx, total)}
      <div class="body fit">
        <div class="head">{f'<span class="emo">{emoji}</span>' if emoji else ''}
          <span class="htitle">{_e(title)}</span></div>
        <div class="stage3d"><div class="scene3d">{body}</div><div class="ground"></div></div>{note}
      </div>
      {_footer(logo)}
    </div>"""


def _font_face(font_dir):
    faces = []
    for w, f in ((300, "KoPubWorld Dotum_Pro Light.otf"), (500, "KoPubWorld Dotum_Pro Medium.otf"),
                 (700, "KoPubWorld Dotum_Pro Bold.otf")):
        p = os.path.join(font_dir, f)
        if os.path.exists(p):
            faces.append(f"@font-face{{font-family:'KoPub';src:url('{_url(p)}');font-weight:{w};}}")
    # 표지 제목만 '검은고딕'으로(2026-10-14). 본문은 KoPub 그대로 — 카드가 글자 수에 따라
    # 자동 축소되긴 하지만, 본문까지 두꺼워지면 읽기가 불편하다.
    import sys as _s
    _s.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    try:
        from shared.fonts import BODY_BOLD, DISPLAY, font_path
        faces.append(f"@font-face{{font-family:'Display';src:url('{_url(font_path(DISPLAY, font_dir))}');}}")
        faces.append(f"@font-face{{font-family:'Body';font-weight:100 800;"
                     f"src:url('{_url(font_path(BODY_BOLD, font_dir))}');}}")
        faces.append(".ctitle{font-family:'Display','KoPub',sans-serif;font-weight:400;}")
        faces.append(".chip,.csub{font-family:'Body','KoPub',sans-serif;}")
    except Exception:
        pass
    return "\n".join(faces)


CSS = """
/* 밝은 톤(2026-09-29): 흰 바탕 → 옅은 하늘색, 짙은 남색 글자, 파란 강조 */
* { margin:0; padding:0; box-sizing:border-box; }
body { background:#fff; font-family:'KoPub','Apple Color Emoji',sans-serif; }
.card { width:1080px; height:1080px; position:relative; overflow:hidden; color:#12284C;
        background:linear-gradient(160deg, #FFFFFF 0%, #F4F8FE 55%, #E6EFFC 100%); }
.card::before { content:""; position:absolute; left:0; top:0; bottom:0; width:14px; background:#2F6FE4; }
.top { position:absolute; left:72px; right:72px; top:56px; display:flex; justify-content:space-between;
       align-items:center; z-index:5; }
.chip { font-weight:700; font-size:26px; color:#1E4FAF; background:#E3EDFD;
        border:1px solid #BFD4F7; padding:8px 20px; border-radius:40px; }
.pg { font-weight:500; font-size:24px; color:#8093B1; }
.foot { position:absolute; left:0; right:0; bottom:46px; text-align:center; z-index:5; }
.foot img { height:46px; }
.foottext { font-weight:500; font-size:26px; color:#8093B1; }
.body { position:absolute; left:72px; right:72px; top:140px; bottom:130px;
        display:flex; flex-direction:column; justify-content:center; font-size:40px; }
.head { display:flex; align-items:center; gap:22px; margin-bottom:.8em; }
.emo { flex:none; width:1.9em; height:1.9em; border-radius:.45em; background:#E3EDFD;
       display:flex; align-items:center; justify-content:center; font-size:1.05em; }
.htitle { font-weight:700; font-size:1.45em; line-height:1.25; color:#0E2350; word-break:keep-all;
          text-wrap:balance; }
.boxes { display:flex; flex-direction:column; gap:.55em; }
.box { background:#FFFFFF; border:1px solid #D6E3F8; border-left:8px solid #2F6FE4;
       border-radius:14px; padding:.6em .8em; box-shadow:0 4px 14px rgba(30,79,175,.07); }
.btitle { font-weight:700; font-size:.86em; line-height:1.35; margin-bottom:.15em; color:#0E2350;
          word-break:keep-all; }
.box p, .ptxt p, .cta p { font-weight:500; font-size:.82em; line-height:1.5; color:#2E3F5C;
       word-break:keep-all; text-wrap:pretty; }
.pts { display:flex; flex-direction:column; gap:.55em; }
.pt { display:flex; gap:.6em; background:#FFFFFF; border:1px solid #D6E3F8; border-radius:14px;
      padding:.6em .8em; box-shadow:0 4px 14px rgba(30,79,175,.07); }
.num { flex:none; width:1.5em; height:1.5em; border-radius:50%; background:#2F6FE4; color:#fff;
       font-weight:700; display:flex; align-items:center; justify-content:center; font-size:.9em; }
.ptitle { font-weight:700; font-size:.92em; line-height:1.35; margin-bottom:.2em; color:#0E2350;
          word-break:keep-all; }
.chks { display:flex; flex-direction:column; gap:.45em; }
.chk { display:flex; gap:.55em; align-items:flex-start; font-weight:500; font-size:.86em; line-height:1.45;
       color:#2E3F5C; word-break:keep-all; }
.tick { flex:none; width:1.25em; height:1.25em; border-radius:50%; background:#1FA864; color:#fff;
        font-weight:700; font-size:.8em; display:flex; align-items:center; justify-content:center; margin-top:.15em; }
.cta { margin-top:.9em; background:#EAF1FD; border:2px solid #2F6FE4; border-radius:14px; padding:.55em .8em; }
.cta p { color:#1E4FAF; font-weight:700; }
/* 표지 — 사진이 아래로 흰 바탕에 녹아든다 */
.cover .photo { position:absolute; left:0; right:0; top:0; height:600px; background-size:cover;
                background-position:center; }
.cover .photo-fade { position:absolute; left:0; right:0; top:330px; height:290px;
                     background:linear-gradient(180deg, rgba(255,255,255,0) 0%, #FFFFFF 94%); }
.cover .nophoto { position:absolute; inset:0;
                  background:radial-gradient(90% 70% at 80% 10%, #D8E6FC 0%, #FFFFFF 62%); }
.cover .top .chip { background:rgba(255,255,255,.88); }
.cover .top .pg { color:#fff; text-shadow:0 1px 4px rgba(0,0,0,.5); }
.stock { position:absolute; right:72px; top:118px; z-index:6; font-weight:700; font-size:22px; color:#fff;
         background:rgba(0,0,0,.55); padding:6px 14px; border-radius:8px; }
.cbody { position:absolute; left:72px; right:72px; top:560px; bottom:130px; display:flex;
         flex-direction:column; justify-content:flex-start; font-size:40px; }
.cover .nophoto ~ .cbody { top:300px; justify-content:center; }
.ctitle { font-weight:700; font-size:2.05em; line-height:1.2; margin-bottom:.35em; color:#0E2350;
          word-break:keep-all; text-wrap:balance; }
.hl { color:#2F6FE4; }
.csub { font-weight:500; font-size:.9em; line-height:1.5; color:#46597A; word-break:keep-all; }
/* 인포그래픽 카드 — 요소가 작으면 카드가 비어 보여 기본 크기를 키운다(자동 축소는 그대로) */
.card.info .body { font-size:50px; }
.card.info .head { margin-bottom:1em; }
.stats { display:flex; gap:.5em; }
.stat { flex:1; background:#FFFFFF; border:1px solid #D6E3F8; border-radius:18px; padding:.7em .5em;
        text-align:center; box-shadow:0 4px 14px rgba(30,79,175,.07); }
.stats.n1 .stat { padding:.9em .6em; }
.sval { font-weight:700; font-size:2.1em; line-height:1.1; color:#2F6FE4; letter-spacing:-.02em;
        white-space:nowrap; }
.stats.n1 .sval { font-size:3.2em; }
.stats.n3 .sval { font-size:1.6em; }
.slab { margin-top:.35em; font-weight:500; font-size:.78em; line-height:1.35; color:#2E3F5C; word-break:keep-all; }
.flow { display:flex; align-items:center; justify-content:space-between; gap:.2em; }
.step { flex:1; display:flex; flex-direction:column; align-items:center; gap:.35em; background:#FFFFFF;
        border:1px solid #D6E3F8; border-radius:16px; padding:.6em .3em; min-height:5.2em;
        box-shadow:0 4px 14px rgba(30,79,175,.07); }
.snum { width:1.5em; height:1.5em; border-radius:50%; background:#2F6FE4; color:#fff; font-weight:700;
        font-size:.8em; display:flex; align-items:center; justify-content:center; }
.stxt { font-weight:700; font-size:.78em; line-height:1.3; text-align:center; color:#0E2350; word-break:keep-all; }
.flow.n5 .stxt { font-size:.66em; }
.flow.n5 .step { padding:.55em .2em; }
.arrow { flex:none; color:#2F6FE4; font-weight:700; font-size:1em; }
.compare { display:flex; align-items:stretch; gap:.4em; }
.side { flex:1; border-radius:16px; padding:.65em .7em; }
.side.left { background:#F1F4F9; border:1px solid #DCE3EE; }
.side.right { background:#FFFFFF; border:2px solid #2F6FE4; box-shadow:0 4px 14px rgba(30,79,175,.10); }
.stitle { font-weight:700; font-size:.92em; margin-bottom:.35em; color:#0E2350; }
.side.left .stitle { color:#5B6B85; }
.side p { font-weight:500; font-size:.76em; line-height:1.45; color:#2E3F5C; margin-bottom:.25em;
          word-break:keep-all; padding-left:.8em; text-indent:-.8em; }
.side p::before { content:"· "; }
.vs { align-self:center; font-weight:700; color:#2F6FE4; font-size:.8em; }

/* 인포그래픽 입체(2026-10-23): 앞면(.cf)·오른쪽면(.cr)·윗면(.ct)으로 블록을 쌓고 장면을 비스듬히 돌린다 */
.stage3d { position:relative; height:9.4em; perspective:1500px; perspective-origin:50% 40%; }
.scene3d { position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
           transform-style:preserve-3d; transform:rotateX(-18deg) rotateY(-14deg) scale(.93); }
.ground { position:absolute; left:6%; right:2%; bottom:-.25em; height:1.1em; border-radius:50%;
          background:radial-gradient(closest-side, rgba(30,79,175,.28), rgba(30,79,175,0));
          filter:blur(6px); }
.cub { --d:.8em; --z:0px; --lift:0em; position:relative; transform-style:preserve-3d;
       transform:translateZ(var(--z)) translateY(calc(var(--lift) * -1)); }
.cub { display:flex; min-width:0; align-self:center; }
.cub.stat { background:none; border:0; box-shadow:none; padding:0; }
.cub .cf { flex:1; min-width:0; position:relative; background:linear-gradient(160deg,#FFFFFF,#EEF4FF); border:1px solid #C9DAF7;
           border-radius:.3em; }
.cub .cr, .cub .ct { position:absolute; display:block; backface-visibility:hidden; }
.cub .cr { top:0; left:100%; width:var(--d); height:100%; transform-origin:left center;
           transform:rotateY(90deg); background:linear-gradient(180deg,#3B73D6,#1E4FAF); border-radius:0 .2em .2em 0; }
.cub .ct { left:0; bottom:100%; width:100%; height:var(--d); transform-origin:center bottom;
           transform:rotateX(90deg); background:linear-gradient(90deg,#9FC0F5,#C7DBFA); border-radius:.2em .2em 0 0; }
.stats { gap:.9em; transform-style:preserve-3d; }
.stat .cf { padding:.7em .6em; text-align:center; flex:1; }
.stats .cub { flex:1 1 0; }
.stat .sval { font-size:1.5em; } .stats.n1 .sval { font-size:2.6em; } .stats.n3 .sval { font-size:1.25em; }
.flow { gap:.3em; align-items:flex-end; transform-style:preserve-3d; }
.flow .cub { flex:1 1 0; align-self:flex-end; }
.step .cf { display:flex; flex-direction:column; align-items:center; gap:.35em; padding:.6em .3em; min-height:5.2em;
            justify-content:center; box-shadow:none; border-radius:.3em; }
.flow .cub.step { padding:0 !important; }
.cub.step { flex-direction:row; align-items:stretch; gap:0; background:none; border:0; box-shadow:none; min-height:0; padding:0; }
.arrow { transform:translateZ(20px); color:#2F6FE4; font-size:.7em; margin-bottom:2.2em; }
.compare { gap:.9em; align-items:center; transform-style:preserve-3d; }
.compare .cub { flex:1 1 0; }
.side .stitle { word-break:keep-all; }
.side { background:none; border:0; box-shadow:none; padding:0; }
.side .cf { padding:.65em .7em; }
.side.left .cf { background:#F1F4F9; border-color:#DCE3EE; }
.side.left .cr { background:linear-gradient(180deg,#A9B5C8,#8593AA); }
.side.left .ct { background:linear-gradient(90deg,#D3DAE6,#E4E9F1); }
.side.right .cf { border:2px solid #2F6FE4; }
.note { margin-top:.8em; font-weight:500; font-size:.82em; line-height:1.5; color:#46597A; text-align:center;
        word-break:keep-all; }
"""

FIT_JS = """
<script>
document.fonts.ready.then(() => {
  document.querySelectorAll('.fit').forEach(el => {
    let fs = parseFloat(getComputedStyle(el).fontSize);
    const inner = () => Array.from(el.children).reduce((h, c) => h + c.getBoundingClientRect().height, 0)
                        + parseFloat(getComputedStyle(el).rowGap || 0);
    for (let i = 0; i < 40 && (el.scrollHeight > el.clientHeight + 1 || inner() > el.clientHeight); i++) {
      fs -= 1; el.style.fontSize = fs + 'px';
    }
  });
  // 큰 숫자는 한 줄로 두고, 칸보다 길면 그 숫자만 줄인다('4,200만 원'이 두 줄로 꺾였다)
  document.querySelectorAll('.sval').forEach(el => {
    let fs = parseFloat(getComputedStyle(el).fontSize);
    for (let i = 0; i < 60 && el.scrollWidth > el.clientWidth; i++) { fs -= 2; el.style.fontSize = fs + 'px'; }
  });
  window.__fitDone = true;
});
</script>"""


def _kind(i, n, block):
    if i == 0:
        return "cover"
    if re.search(r"^포인트\s*\d+\s*[.．:]", block, re.M):
        return "points"
    if i == n - 1:
        return "closing"
    return "news"


def build_html(cards, font_dir, photo, logo, infographics=None):
    n = len(cards)
    infographics = infographics or {}
    parts = []
    for i, c in enumerate(cards):
        k = _kind(i, n, c)
        spec = infographics.get(str(i + 1))
        if spec and k != "cover":
            parts.append(_info(i, n, c, spec, logo))
            continue
        parts.append(_cover(i, n, c, photo, logo) if k == "cover" else
                     _points(i, n, c, logo) if k == "points" else
                     _closing(i, n, c, logo) if k == "closing" else _news(i, n, c, logo))
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{_font_face(font_dir)}\n{CSS}'
            f'</style></head><body>{"".join(parts)}{FIT_JS}</body></html>')


def make_cards(data):
    cfg = load_config()
    font_dir = (cfg.get("local_render", {}) or {}).get("font_dir") or DEFAULT_FONT_DIR
    require_fonts(font_dir)
    cards = data["cards"]
    stamp = data.get("stamp") or time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(POSTS_DIR, f"cards_{stamp}")
    os.makedirs(out_dir, exist_ok=True)
    photo = _cover_photo(data, out_dir)
    logo = LOGO_SRC if os.path.exists(LOGO_SRC) else ""   # 밝은 바탕에선 원래 파란 로고가 또렷하다
    html_path = os.path.join(out_dir, "_cards.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(build_html(cards, font_dir, photo, logo, data.get("infographics")))

    o = Options()
    o.add_argument("--headless=new")
    o.add_argument("--window-size=1200,1300")
    o.add_argument("--force-device-scale-factor=2")   # 2160px 로 선명하게
    o.add_argument("--hide-scrollbars")
    o.add_argument("--allow-file-access-from-files")
    o.add_argument("--lang=ko-KR")
    # 크롬이 실행마다 앱 전체(~1.4GB)를 임시 폴더에 복제하고 남기는 것을 막는다(2026-10-09)
    o.add_argument("--disable-features=MacAppCodeSignClone")
    d = webdriver.Chrome(options=o)
    pngs = []
    try:
        d.get("file:///" + html_path.replace("\\", "/"))
        for _ in range(60):
            time.sleep(0.25)
            if d.execute_script("return window.__fitDone === true"):
                break
        time.sleep(0.5)
        for i in range(len(cards)):
            out = os.path.join(out_dir, f"{i + 1:02d}.png")
            el = d.find_element(By.ID, f"card{i}")
            for attempt in range(4):          # 뷰포트 밖 카드가 빈 이미지로 찍히는 문제 방지
                d.execute_script("arguments[0].scrollIntoView({block:'start'});", el)
                time.sleep(0.35)
                el.screenshot(out)
                if os.path.getsize(out) > 8000:
                    break
                time.sleep(0.4)
            pngs.append(out)
    finally:
        d.quit()
    data["images"] = pngs
    log(f"카드 PNG {len(pngs)}장 준비(로컬 렌더): {out_dir}")
    return pngs


if __name__ == "__main__":
    import glob
    files = sorted(glob.glob(os.path.join(POSTS_DIR, "*.json")))
    d = json.load(open(sys.argv[1] if len(sys.argv) > 1 else files[-1], encoding="utf-8"))
    d["stamp"] = "LOCALTEST_" + str(d.get("stamp", ""))
    print(make_cards(d))
