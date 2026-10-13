"""유튜브 썸네일(숏츠 9:16 / 동영상 16:9)을 만든다. 글꼴은 KoPubWorld 돋움 Bold.

왜 따로 만드나: 지금까지 썸네일을 올리지 않아 유튜브가 영상 프레임 하나를 골라 썼다.
그 프레임은 대개 표지 카드(회색 바탕에 제목)라, 검색·채널 목록에서 다른 영상과 구분되지
않고 클릭할 이유를 주지 못한다.

설계 근거(2026-10-13 채널 분석):
- 숏츠 썸네일은 하단 25%가 유튜브 UI(제목·채널명·버튼)에 가려진다. 글자는 위 60%에 둔다.
- 작은 화면에서 읽히려면 한 줄 8~11자, 2~3줄이 한계다. 제목을 그대로 넣지 않고
  장면 1의 자막(heading)처럼 이미 짧게 다듬어진 문구를 쓴다.
- 숫자는 눈에 먼저 들어오므로 노란색으로 따로 칠한다(2천만원대, 470명 …).

사용:
    from make_thumbnail import make_thumbnail
    make_thumbnail(data, shape="shorts")      # posts/thumb_<stamp>_shorts.jpg
"""
import os
import re

from PIL import Image, ImageDraw, ImageFilter, ImageFont

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(os.path.dirname(BASE_DIR), "FONTS")
FONT_BOLD = os.path.join(FONT_DIR, "KoPubWorld Dotum_Pro Bold.otf")
FONT_MED = os.path.join(FONT_DIR, "KoPubWorld Dotum_Pro Medium.otf")
POSTS_DIR = os.path.join(BASE_DIR, "posts")

SIZES = {"shorts": (1080, 1920), "video": (1280, 720)}
INK = (255, 255, 255)
ACCENT = (250, 204, 21)          # 숫자·강조어(노랑)
LABEL_BG = (220, 38, 38)         # 학과 채널 라벨(빨강 — 속보 느낌)
LABEL_BG_GEOAI = (2, 132, 199)   # GeoAI 채널 라벨(파랑 — 블로그·배너와 같은 계열)
BG_TOP = (11, 21, 46)
BG_BOTTOM = (23, 54, 86)


def _font(path, size):
    return ImageFont.truetype(path, size)


def _wrap(draw, text, font, max_w):
    """띄어쓰기 기준으로 줄을 나눈다. 한 어절이 너무 길면 글자 단위로 쪼갠다."""
    lines, cur = [], ""
    for word in str(text).split():
        nxt = (cur + " " + word).strip()
        if draw.textlength(nxt, font=font) <= max_w or not cur:
            cur = nxt
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    out = []
    for ln in lines:
        while draw.textlength(ln, font=font) > max_w and len(ln) > 1:
            cut = len(ln) - 1
            while cut > 1 and draw.textlength(ln[:cut], font=font) > max_w:
                cut -= 1
            out.append(ln[:cut])
            ln = ln[cut:]
        out.append(ln)
    return out


def _fit(draw, text, font_path, max_w, max_lines, start, floor=40):
    """줄 수 안에 들어올 때까지 글자를 줄인다. (크게 쓰는 쪽이 클릭에 유리하다)"""
    size = start
    while size > floor:
        f = _font(font_path, size)
        lines = _wrap(draw, text, f, max_w)
        if len(lines) <= max_lines:
            return f, lines
        size -= 4
    f = _font(font_path, floor)
    return f, _wrap(draw, text, f, max_w)[:max_lines]


def _background(size, photo=None):
    """뉴스 사진이 있으면 어둡게 깔고, 없으면 남색 그라데이션."""
    W, H = size
    if photo and os.path.exists(photo):
        try:
            im = Image.open(photo).convert("RGB")
            # 짧은 변을 맞춰 가운데를 잘라 채운다(비율 유지).
            r = max(W / im.width, H / im.height)
            im = im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))))
            im = im.crop(((im.width - W) // 2, (im.height - H) // 2,
                          (im.width - W) // 2 + W, (im.height - H) // 2 + H))
            im = im.filter(ImageFilter.GaussianBlur(3))
            dark = Image.new("RGB", (W, H), (8, 14, 30))
            return Image.blend(im, dark, 0.52)
        except Exception:
            pass
    bg = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(bg)
    for y in range(H):
        t = y / max(1, H - 1)
        d.line([(0, y), (W, y)],
               fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)))
    return bg


def _draw_lines(d, lines, font, x, y, line_h, highlight=True):
    """숫자가 든 조각만 노랑으로 칠해 눈이 먼저 가게 한다."""
    for ln in lines:
        cx = x
        parts = re.split(r"([0-9][0-9,.]*[가-힣%]*)", ln) if highlight else [ln]
        for p in parts:
            if not p:
                continue
            color = ACCENT if (highlight and re.match(r"^[0-9]", p)) else INK
            d.text((cx, y), p, font=font, fill=color)
            cx += d.textlength(p, font=font)
        y += line_h
    return y


def _texts(data):
    """썸네일에 쓸 문구를 고른다: 장면 1 자막 > 제목."""
    scenes = data.get("scenes") or []
    head = (scenes[0].get("heading") if scenes else "") or ""
    sub = ""
    if scenes and scenes[0].get("lines"):
        sub = scenes[0]["lines"][0]
    if not head:
        head = re.split(r"[|·–—]", data.get("title", ""))[0].strip()
    return head.strip(), sub.strip()


def _photo(data):
    """배경으로 쓸 뉴스 사진. 표지 프레임(회색 카드)은 쓰지 않는다."""
    imgs = data.get("source_images") or {}
    for k in sorted(imgs, key=lambda x: str(x)):
        if imgs[k] and os.path.exists(imgs[k]):
            return imgs[k]
    return None


def make_thumbnail(data, shape="shorts", out_path=None, label=None):
    W, H = SIZES.get(shape, SIZES["shorts"])
    head, sub = _texts(data)
    # 같은 함수를 학과 채널과 개인 GeoAI 채널이 함께 쓴다 — 브랜드가 섞이지 않게 구분한다.
    geoai = str(data.get("stamp", "")).startswith("geoai") or bool(data.get("family"))
    if geoai:
        label = label or (data.get("family") or "GeoAI")
        dept, label_bg = "재난안전과 GeoAI", LABEL_BG_GEOAI
    else:
        label = label or "재난안전뉴스"
        dept, label_bg = "세명대학교 재난안전학과", LABEL_BG

    im = _background((W, H), _photo(data))
    d = ImageDraw.Draw(im)
    pad = int(W * 0.075)
    text_w = W - pad * 2 if shape == "shorts" else int(W * 0.62)

    # 라벨 배지
    lf = _font(FONT_BOLD, int(H * 0.028) if shape == "shorts" else int(H * 0.05))
    lw = d.textlength(label, font=lf)
    bh = int(lf.size * 1.9)
    top = int(H * (0.10 if shape == "shorts" else 0.10))
    d.rectangle([pad, top, pad + lw + lf.size * 1.2, top + bh], fill=label_bg)
    d.text((pad + lf.size * 0.6, top + (bh - lf.size * 1.25) / 2), label, font=lf, fill=INK)

    # 후킹 문구 — 숏츠는 아래 25%가 UI 에 가리므로 위쪽에 몰아 둔다.
    hf, hlines = _fit(d, head, FONT_BOLD, text_w, 3,
                      int(W * (0.135 if shape == "shorts" else 0.085)))
    y = top + bh + int(H * 0.045)
    y = _draw_lines(d, hlines, hf, pad, y, int(hf.size * 1.26))

    if sub:
        sf, slines = _fit(d, sub, FONT_MED, text_w, 2,
                          int(W * (0.062 if shape == "shorts" else 0.042)))
        y += int(H * 0.012)
        _draw_lines(d, slines, sf, pad, y, int(sf.size * 1.3))

    # 학과명 — 숏츠는 UI 가리는 영역 위(=60% 지점 아래쪽 여유)에 작게.
    df = _font(FONT_MED, int(W * (0.034 if shape == "shorts" else 0.030)))
    dy = int(H * (0.63 if shape == "shorts" else 0.86))
    d.text((pad, dy), dept, font=df, fill=(203, 213, 225))

    out_path = out_path or os.path.join(
        POSTS_DIR, f"thumb_{data.get('stamp', 'x')}_{shape}.jpg")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    im.convert("RGB").save(out_path, "JPEG", quality=88)   # 유튜브 상한 2MB
    return out_path


if __name__ == "__main__":
    import json
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        import glob
        path = sorted(glob.glob(os.path.join(POSTS_DIR, "2026*.json")))[-1]
    data = json.load(open(path, encoding="utf-8"))
    for shape in ("shorts", "video"):
        print(make_thumbnail(data, shape=shape))
