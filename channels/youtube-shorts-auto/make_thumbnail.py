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
FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), "assets", "FONTS")

import sys as _sys  # noqa: E402
_sys.path.insert(0, os.path.dirname(os.path.dirname(BASE_DIR)))
from shared.fonts import BODY_BLACK, BODY_BOLD, DISPLAY, font_path  # noqa: E402

# 제목은 '검은고딕'(제목 전용 글꼴), 강조·보조는 Pretendard. KoPub 돋움은 본문용이라
# 썸네일처럼 작게 줄어드는 자리에서는 획이 가늘어 눈에 걸리지 않았다(2026-10-14).
FONT_BOLD = font_path(DISPLAY, FONT_DIR)          # 제목
FONT_BLACK = font_path(BODY_BLACK, FONT_DIR)      # 작은 라벨만(크게 쓰면 제목보다 굵어진다)
FONT_MED = font_path(BODY_BOLD, FONT_DIR)         # 학과명·보조
POSTS_DIR = os.path.join(BASE_DIR, "posts")

SIZES = {"shorts": (1080, 1920), "video": (1280, 720)}
INK = (255, 255, 255)
ACCENT = (250, 204, 21)          # 숫자·강조어(노랑)
LABEL_BG = (220, 38, 38)         # 학과 채널 라벨(빨강 — 속보 느낌)
LABEL_BG_GEOAI = (2, 132, 199)   # GeoAI 채널 라벨(파랑 — 블로그·배너와 같은 계열)
ACCENT_GEOAI = (56, 189, 248)    # GeoAI 강조색(하늘 — 노랑 경보색은 재난 채널 것)
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
    """뉴스 사진은 살리고 글자가 놓일 위쪽만 어둡게 덮는다.

    전체를 고르게 어둡게 하면 사진이 뭉개져 '글자만 있는 판'처럼 보인다.
    위 65%는 진하게, 아래는 거의 그대로 둬 사진이 보이게 한다."""
    W, H = size
    if photo and os.path.exists(photo):
        try:
            im = Image.open(photo).convert("RGB")
            r = max(W / im.width, H / im.height)
            im = im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))))
            im = im.crop(((im.width - W) // 2, (im.height - H) // 2,
                          (im.width - W) // 2 + W, (im.height - H) // 2 + H))
            im = im.filter(ImageFilter.GaussianBlur(1.5))
            # 위→아래로 옅어지는 검정 장막(알파 마스크)
            veil = Image.new("RGB", (W, H), (6, 10, 24))
            mask = Image.new("L", (1, H))
            md = ImageDraw.Draw(mask)
            for y in range(H):
                t = y / max(1, H - 1)
                a = 214 if t < 0.58 else max(70, int(214 - (t - 0.58) * 430))
                md.point((0, y), fill=a)
            im.paste(veil, (0, 0), mask.resize((W, H)))
            return im
        except Exception:
            pass
    bg = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(bg)
    for y in range(H):
        t = y / max(1, H - 1)
        d.line([(0, y), (W, y)],
               fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)))
    # 바탕만 있을 때는 비어 보이므로 옅은 격자를 깐다(블로그 배너와 같은 모티브).
    for x in range(0, W, int(W * 0.11)):
        d.line([(x, 0), (x, H)], fill=(255, 255, 255), width=1)
    for y in range(0, H, int(W * 0.11)):
        d.line([(0, y), (W, y)], fill=(255, 255, 255), width=1)
    return Image.blend(bg, Image.new("RGB", (W, H), BG_TOP), 0.12)


def _tape(d, W, y, h, step, color=ACCENT):
    """경보 테이프(사선 띠) — 블로그 배너와 같은 아이덴티티. 색은 채널마다 다르다."""
    for i in range(-h, W + h * 2, step * 2):
        d.polygon([(i, y + h), (i + step, y), (i + step * 2, y), (i + step, y + h)],
                  fill=color)
    d.rectangle([0, y, W, y + 2], fill=(17, 24, 39))


def _marker(d, box, color=ACCENT):
    """형광펜 느낌의 강조 박스(모서리를 살짝 비스듬히)."""
    x0, y0, x1, y1 = box
    d.polygon([(x0, y0 + 4), (x1, y0), (x1, y1 - 4), (x0, y1)], fill=color)


def _draw_lines(d, lines, font, x, y, line_h, highlight=True, stroke=0):
    """숫자가 든 조각만 노랑으로 칠하고, 사진 위에서도 읽히게 외곽선을 두른다."""
    for ln in lines:
        cx = x
        parts = re.split(r"([0-9][0-9,.]*[가-힣%]*)", ln) if highlight else [ln]
        for p in parts:
            if not p:
                continue
            color = ACCENT if (highlight and re.match(r"^[0-9]", p)) else INK
            if stroke:
                d.text((cx, y), p, font=font, fill=color,
                       stroke_width=stroke, stroke_fill=(10, 14, 28))
            else:
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
        # 대본이 없으면 제목에서 만든다. 해시태그·시리즈 꼬리표를 떼지 않으면
        # 썸네일에 '#세명대 #릴스' 가 그대로 박힌다(2026-10-14 소급 작업에서 확인).
        t = re.sub(r"#\S+", " ", data.get("title", ""))
        t = re.split(r"[|·–—]", t)[0]
        head = re.sub(r"\s+", " ", t).strip()
    return head.strip(), sub.strip()


def _photo(data):
    """배경으로 쓸 뉴스 사진. 표지 프레임(회색 카드)은 쓰지 않는다."""
    imgs = data.get("source_images") or {}
    for k in sorted(imgs, key=lambda x: str(x)):
        if imgs[k] and os.path.exists(imgs[k]):
            return imgs[k]
    return None


def make_thumbnail(data, shape="shorts", out_path=None, label=None):
    """클릭을 끌 요소를 쌓아 올린다: 경보 테이프 → 라벨 → 세로 강조 바 → 큰 제목
    (외곽선) → 형광 강조줄 → 학과 띠. 배경 사진은 아래쪽을 살려 '사진 위의 뉴스
    자막' 처럼 보이게 한다."""
    W, H = SIZES.get(shape, SIZES["shorts"])
    head, sub = _texts(data)
    # 같은 함수를 학과 채널과 개인 GeoAI 채널이 함께 쓴다 — 브랜드가 섞이지 않게 구분한다.
    geoai = str(data.get("stamp", "")).startswith("geoai") or bool(data.get("family"))
    if geoai:
        label = label or (data.get("family") or "GeoAI")
        dept, label_bg, brand = "재난안전과 GeoAI", LABEL_BG_GEOAI, ACCENT_GEOAI
    else:
        label = label or "재난안전뉴스"
        dept, label_bg, brand = "세명대학교 재난안전학과", LABEL_BG, ACCENT

    im = _background((W, H), _photo(data))
    d = ImageDraw.Draw(im)
    pad = int(W * 0.075)
    text_w = W - pad * 2 - int(W * 0.035) if shape == "shorts" else int(W * 0.60)
    tape_h = int(H * (0.012 if shape == "shorts" else 0.022))

    _tape(d, W, 0, tape_h, int(W * 0.028), brand)              # 위 경보 테이프

    # 라벨 배지 — 모서리를 비스듬히 깎아 '속보 자막' 느낌을 준다.
    lf = _font(FONT_BLACK, int(H * 0.027) if shape == "shorts" else int(H * 0.047))
    lw = d.textlength(label, font=lf)
    bh = int(lf.size * 1.95)
    top = int(H * (0.075 if shape == "shorts" else 0.09))
    skew = int(bh * 0.22)
    d.polygon([(pad, top), (pad + lw + lf.size * 1.4, top),
               (pad + lw + lf.size * 1.4 - skew, top + bh), (pad, top + bh)], fill=label_bg)
    d.text((pad + lf.size * 0.7, top + (bh - lf.size * 1.3) / 2), label, font=lf, fill=INK)

    # 제목 — 왼쪽 세로 강조 바 + 큰 글자(외곽선). 사진 위에서도 읽히게 한다.
    hf, hlines = _fit(d, head, FONT_BOLD, text_w, 3,
                      int(W * (0.145 if shape == "shorts" else 0.092)))
    line_h = int(hf.size * 1.24)
    y0 = top + bh + int(H * 0.042)
    bar_w = int(W * 0.014)
    d.rectangle([pad, y0 + int(hf.size * 0.12), pad + bar_w,
                 y0 + line_h * len(hlines) - int(hf.size * 0.18)], fill=brand)
    tx = pad + bar_w + int(W * 0.028)
    y = _draw_lines(d, hlines, hf, tx, y0, line_h, stroke=max(3, int(hf.size * 0.055)))

    # 강조줄 — 형광펜 박스 위에 검은 글자. 숫자가 있으면 그 줄이 가장 세게 읽힌다.
    if sub:
        sf, slines = _fit(d, sub, FONT_MED, text_w - int(W * 0.04), 2,
                          int(W * (0.068 if shape == "shorts" else 0.046)))
        y += int(H * 0.018)
        for ln in slines:
            tw = d.textlength(ln, font=sf)
            box = (tx - int(sf.size * 0.3), y - int(sf.size * 0.12),
                   tx + tw + int(sf.size * 0.45), y + int(sf.size * 1.32))
            _marker(d, box, brand)
            d.text((tx, y), ln, font=sf, fill=(17, 24, 39))
            y += int(sf.size * 1.62)

    # 학과명. 16:9 는 방송 자막처럼 아래 띠로, 숏츠는 글자 묶음 바로 아래 작은 꼬리표로
    # 둔다(가로 띠를 화면 한가운데 그으면 사진을 두 동강 내 어수선해 보인다).
    df = _font(FONT_MED, int(W * (0.030 if shape == "shorts" else 0.029)))
    if shape == "shorts":
        ty = min(int(H * 0.62), y + int(H * 0.028))
        tw = d.textlength(dept, font=df)
        pill_h = int(df.size * 1.95)
        d.rectangle([pad, ty, pad + tw + df.size * 1.5, ty + pill_h], fill=(10, 16, 32))
        d.rectangle([pad, ty, pad + int(W * 0.009), ty + pill_h], fill=brand)
        d.text((pad + df.size * 0.75, ty + (pill_h - df.size * 1.3) / 2),
               dept, font=df, fill=(226, 232, 240))
    else:
        by = int(H * 0.855)
        band_h = int(df.size * 2.1)
        d.rectangle([0, by, W, by + band_h], fill=(10, 16, 32))
        d.rectangle([0, by, W, by + max(3, int(band_h * 0.07))], fill=brand)
        d.text((pad, by + (band_h - df.size * 1.3) / 2), dept, font=df, fill=(226, 232, 240))

    if shape == "shorts":                                      # 아래 경보 테이프
        _tape(d, W, H - tape_h, tape_h, int(W * 0.028), brand)

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
