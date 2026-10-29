"""13일차 개념도 — 소성변형 네 종류의 횡단 형상(축척 없음)."""
from pathlib import Path
import math
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent
FIG_NAME = '소성변형_종류별_횡단형상.jpg'
PRET = '/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf'
INK, TEAL, RED, GRAYC, SOFT = '#263746', '#176977', '#B6462F', '#7A8790', '#EAF2F3'
LAYERS = [('표층·중간층', '#3E4347'), ('기층', '#8C8577'), ('보조기층', '#C2B79F'), ('노상', '#DCCFB4')]
f = lambda z: ImageFont.truetype(PRET, z)


def bump(x, c, w):
    """폭 w 인 종 모양(0~1)."""
    return math.exp(-((x - c) / w) ** 2)


def panel(dr, ox, oy, title, sub, kind, note):
    W, Hh = 700, 300
    dr.rounded_rectangle([ox - 20, oy - 70, ox + W + 20, oy + Hh + 95], 14, fill=SOFT)
    dr.text((ox, oy - 58), title, font=f(30), fill=INK)
    dr.text((ox + dr.textlength(title, font=f(30)) + 16, oy - 50), sub, font=f(20), fill=GRAYC)
    wp = (ox + 210, ox + 490)                       # 두 바퀴 자국 위치
    thick = [50, 60, 70, 120]                       # 층 두께(그림용)
    def surf(x, depth):                             # 층 경계 i 의 처짐(아래로 +)
        d = 0
        for c in wp:
            if kind == 'flow':
                d += (24 * bump(x, c, 45) - 11 * bump(x, c - 85, 30) - 11 * bump(x, c + 85, 30)) * (1 if depth == 0 else 0.15 if depth == 1 else 0)
            elif kind == 'struct':
                d += 22 * bump(x, c, 120) * (1 if depth <= 3 else 0.6)
            elif kind == 'dens':
                d += (16 * bump(x, c, 55)) * (1 if depth == 0 else 0.2 if depth == 1 else 0)
            elif kind == 'wear':
                d += (8 * bump(x, c, 70)) * (1 if depth == 0 else 0)
        return d
    xs = list(range(ox, ox + W + 1, 4))
    tops = [oy + 40]
    for t in thick: tops.append(tops[-1] + t)
    for i, (name, col) in enumerate(LAYERS):
        upper = [(x, tops[i] + surf(x, i)) for x in xs]
        lower = [(x, tops[i + 1] + surf(x, i + 1)) for x in reversed(xs)] if i < 3 else [(ox + W, oy + Hh + 40), (ox, oy + Hh + 40)]
        dr.polygon(upper + lower, fill=col)
        tc = 'white' if i == 0 else INK
        dr.text((ox + 8, tops[i] + 8 + (8 if i == 0 else 0)), name, font=f(18), fill=tc)
    # 원래 노면(점선)
    for x in range(ox, ox + W, 16): dr.line([(x, oy + 40), (x + 8, oy + 40)], fill=RED, width=2)
    # 바퀴
    for c in wp:
        dr.rounded_rectangle([c - 34, oy - 20 + surf(c, 0), c + 34, oy + 40 + surf(c, 0)], 8, fill='#1F2328')
    if kind == 'wear':                              # 표면 골재 탈리 점
        for c in wp:
            for k in range(-50, 51, 14): dr.ellipse([c + k - 3, oy + 42 + surf(c + k, 0) - 3, c + k + 3, oy + 42 + surf(c + k, 0) + 3], fill='#A9A39A')
    dr.text((ox, oy + Hh + 50), note, font=f(21), fill=RED)


def figure():
    im = Image.new('RGB', (1600, 1080), 'white'); dr = ImageDraw.Draw(im)
    dr.text((60, 30), '아스팔트 포장 소성변형 — 종류별 횡단 형상(축척 없음, 깊이 과장)', font=f(36), fill=INK)
    panel(dr, 70, 170, '① 유동(불안정) 소성변형', '표층·중간층 혼합물', 'flow', '바퀴자국 양옆이 솟음(융기) · 폭이 좁음')
    panel(dr, 830, 170, '② 구조적 소성변형', '기층 이하·노상', 'struct', '폭 넓게 처짐 · 융기 없음 · 하부층도 함께 처짐')
    panel(dr, 70, 640, '③ 압밀(추가다짐) 소성변형', '다짐 부족 층', 'dens', '융기 없이 바퀴 아래만 처짐 · 공용 초기')
    panel(dr, 830, 640, '④ 마모 소성변형', '표면', 'wear', '얕게 패이고 표면이 거칠어짐 · 체인·스파이크')
    dr.text((60, 1040), '직접 작성한 개념도 · 붉은 점선 = 원래 노면 · 근거: NCHRP Report 468(2002), Pavement Interactive "Rutting"', font=f(21), fill=GRAYC)
    im.save(OUT / FIG_NAME, quality=92)


if __name__ == '__main__':
    figure()
