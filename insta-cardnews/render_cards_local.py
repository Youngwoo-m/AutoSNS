"""로컬 HTML + 헤드리스 Chrome 으로 카드뉴스 PNG 를 만든다(Gamma 없이).

2026-09-29 다시 설계: Gamma 는 편당 크레딧 30 을 쓰고, 넘긴 문장을 스스로 요약·재배치
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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.fonts import require_fonts  # noqa: E402
from shared.stock_video import pick_query  # noqa: E402

CARD_PX = 1080
ROOT = os.path.dirname(BASE_DIR)
DEFAULT_FONT_DIR = os.path.join(ROOT, "FONTS")
LOGO_SRC = os.path.join(ROOT, "image", "SMU_logo.png")
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


def _font_face(font_dir):
    faces = []
    for w, f in ((300, "KoPubWorld Dotum_Pro Light.otf"), (500, "KoPubWorld Dotum_Pro Medium.otf"),
                 (700, "KoPubWorld Dotum_Pro Bold.otf")):
        p = os.path.join(font_dir, f)
        if os.path.exists(p):
            faces.append(f"@font-face{{font-family:'KoPub';src:url('{_url(p)}');font-weight:{w};}}")
    return "\n".join(faces)


CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
body { background:#0B1C3A; font-family:'KoPub','Apple Color Emoji',sans-serif; }
.card { width:1080px; height:1080px; position:relative; overflow:hidden; color:#fff;
        background:radial-gradient(120% 90% at 85% 0%, #1B3A6E 0%, #0B1C3A 55%, #081530 100%); }
.top { position:absolute; left:72px; right:72px; top:56px; display:flex; justify-content:space-between;
       align-items:center; z-index:5; }
.chip { font-weight:700; font-size:26px; color:#CFE0FF; background:rgba(79,142,247,.18);
        border:1px solid rgba(79,142,247,.45); padding:8px 20px; border-radius:40px; }
.pg { font-weight:500; font-size:24px; color:#8FA3C2; }
.foot { position:absolute; left:0; right:0; bottom:46px; text-align:center; z-index:5; }
.foot img { height:46px; opacity:.92; }
.foottext { font-weight:500; font-size:26px; color:#8FA3C2; }
.body { position:absolute; left:72px; right:72px; top:140px; bottom:130px;
        display:flex; flex-direction:column; justify-content:center; font-size:40px; }
.head { display:flex; align-items:center; gap:22px; margin-bottom:.8em; }
.emo { flex:none; width:1.9em; height:1.9em; border-radius:.45em; background:rgba(79,142,247,.16);
       display:flex; align-items:center; justify-content:center; font-size:1.05em; }
.htitle { font-weight:700; font-size:1.45em; line-height:1.25; word-break:keep-all; text-wrap:balance; }
.boxes { display:flex; flex-direction:column; gap:.55em; }
.box { background:rgba(19,41,79,.92); border:1px solid rgba(79,142,247,.28); border-left:8px solid #4F8EF7;
       border-radius:14px; padding:.6em .8em; }
.btitle { font-weight:700; font-size:.86em; line-height:1.35; margin-bottom:.15em; color:#fff;
          word-break:keep-all; }
.box p, .ptxt p, .cta p { font-weight:500; font-size:.82em; line-height:1.5; color:#E3EBF8;
       word-break:keep-all; text-wrap:pretty; }
.pts { display:flex; flex-direction:column; gap:.55em; }
.pt { display:flex; gap:.6em; background:rgba(19,41,79,.92); border:1px solid rgba(79,142,247,.28);
      border-radius:14px; padding:.6em .8em; }
.num { flex:none; width:1.5em; height:1.5em; border-radius:50%; background:#4F8EF7; color:#fff;
       font-weight:700; display:flex; align-items:center; justify-content:center; font-size:.9em; }
.ptitle { font-weight:700; font-size:.92em; line-height:1.35; margin-bottom:.2em; word-break:keep-all; }
.chks { display:flex; flex-direction:column; gap:.45em; }
.chk { display:flex; gap:.55em; align-items:flex-start; font-weight:500; font-size:.86em; line-height:1.45;
       word-break:keep-all; }
.tick { flex:none; width:1.25em; height:1.25em; border-radius:50%; background:#2FBF71; color:#fff;
        font-weight:700; font-size:.8em; display:flex; align-items:center; justify-content:center; margin-top:.15em; }
.cta { margin-top:.9em; border:2px solid #4F8EF7; border-radius:14px; padding:.55em .8em; }
.cta p { color:#CFE0FF; }
/* 표지 */
.cover .photo { position:absolute; left:0; right:0; top:0; height:600px; background-size:cover;
                background-position:center; filter:brightness(.78) saturate(.9); }
.cover .photo-fade { position:absolute; left:0; right:0; top:300px; height:320px;
                     background:linear-gradient(180deg, rgba(11,28,58,0) 0%, #0B1C3A 92%); }
.cover .nophoto { position:absolute; inset:0;
                  background:radial-gradient(90% 70% at 80% 10%, #24488A 0%, #0B1C3A 60%); }
.stock { position:absolute; right:72px; top:118px; z-index:6; font-weight:700; font-size:22px; color:#fff;
         background:rgba(0,0,0,.55); padding:6px 14px; border-radius:8px; }
.cbody { position:absolute; left:72px; right:72px; top:560px; bottom:130px; display:flex;
         flex-direction:column; justify-content:flex-start; font-size:40px; }
.cover .nophoto ~ .cbody { top:300px; justify-content:center; }
.ctitle { font-weight:700; font-size:2.05em; line-height:1.2; margin-bottom:.35em; word-break:keep-all;
          text-wrap:balance; }
.hl { color:#6FA8FF; }
.csub { font-weight:500; font-size:.9em; line-height:1.5; color:#C9D4E6; word-break:keep-all; }
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


def build_html(cards, font_dir, photo, logo):
    n = len(cards)
    parts = []
    for i, c in enumerate(cards):
        k = _kind(i, n, c)
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
    logo = _white_logo(out_dir)
    html_path = os.path.join(out_dir, "_cards.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(build_html(cards, font_dir, photo, logo))

    o = Options()
    o.add_argument("--headless=new")
    o.add_argument("--window-size=1200,1300")
    o.add_argument("--force-device-scale-factor=2")   # 2160px 로 선명하게
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
