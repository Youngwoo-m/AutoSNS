"""17일차 개념도 — 노후 상수도관 단면으로 본 세척·비구조적 갱생·구조적 갱생과 직접평가 등급별 개량방안(축척 없음)."""
from pathlib import Path
import math, random
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent
FIG_NAME = '상수도관갱생_단면_개념도.jpg'
PRET = '/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf'
INK, GRAYC, PIPE, RUST, WATER, EPOXY, LINER, GROUT = '#263746', '#7A8790', '#5E6B75', '#A0522D', '#CFE6F5', '#2F7D5B', '#C98A1B', '#B9B9B9'
f = lambda z: ImageFont.truetype(PRET, z)


def ring(dr, cx, cy, r0, r1, col):
    dr.ellipse([cx - r0, cy - r0, cx + r0, cy + r0], fill=col)
    dr.ellipse([cx - r1, cy - r1, cx + r1, cy + r1], fill='white')


def section(dr, cx, cy, kind):
    R, T = 150, 20                                   # 기존관 바깥 반지름, 두께
    ring(dr, cx, cy, R, R - T, PIPE)
    inner = R - T
    if kind == 'old':                                # 결절·스케일로 단면 축소
        rnd = random.Random(3)
        pts = []
        for k in range(48):
            a = 2 * math.pi * k / 48
            r = inner - 18 - rnd.random() * 28
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        dr.ellipse([cx - inner, cy - inner, cx + inner, cy + inner], fill=RUST)
        dr.polygon(pts, fill=WATER)
    elif kind == 'clean':
        dr.ellipse([cx - inner, cy - inner, cx + inner, cy + inner], fill=WATER)
    elif kind == 'nonstruct':                        # 얇은 도막
        ring(dr, cx, cy, inner, inner - 7, EPOXY)
        dr.ellipse([cx - inner + 7, cy - inner + 7, cx + inner - 7, cy + inner - 7], fill=WATER)
    elif kind == 'struct':                           # 두꺼운 라이너(현장경화·밀착·삽입관)
        ring(dr, cx, cy, inner, inner - 24, LINER)
        dr.ellipse([cx - inner + 24, cy - inner + 24, cx + inner - 24, cy + inner - 24], fill=WATER)
    # 바깥 부식(기존관이 약해진 정도)
    if kind == 'struct':
        for a in (30, 140, 250):
            x, y = cx + (R - 8) * math.cos(math.radians(a)), cy + (R - 8) * math.sin(math.radians(a))
            dr.ellipse([x - 10, y - 10, x + 10, y + 10], fill=RUST)


def figure():
    W, H = 1600, 1000
    im = Image.new('RGB', (W, H), 'white'); dr = ImageDraw.Draw(im)
    dr.text((50, 26), '노후 상수도관 — 관 상태에 따라 세척·갱생·교체를 고른다(축척 없음)', font=f(38), fill=INK)
    items = [('old', '① 노후관', '녹 결절·스케일로\n단면 축소, 적수'),
             ('clean', '② 세척', '침전물 제거\n(플러싱·피깅 등)'),
             ('nonstruct', '③ 비구조적 갱생', '얇은 도막: 에폭시·\n시멘트 모르타르'),
             ('struct', '④ 구조적 갱생', '라이너가 하중 분담:\n반전삽입·밀착·삽입관')]
    for i, (k, t, s) in enumerate(items):
        cx = 200 + i * 400; cy = 300
        section(dr, cx, cy, k)
        dr.text((cx - dr.textlength(t, font=f(30)) / 2, 470), t, font=f(30), fill=INK)
        for j, ln in enumerate(s.split('\n')):
            dr.text((cx - dr.textlength(ln, font=f(23)) / 2, 516 + j * 32), ln, font=f(23), fill=GRAYC)
    # 아래: 직접평가 등급별 개량방안
    dr.text((50, 640), '환경부 「상수관로 정밀조사 매뉴얼」(2020) 직접평가 등급별 개량방안', font=f(28), fill=INK)
    grades = [('Ⅰ', '계속 사용', '#DDE8D8'), ('Ⅱ', '세척', '#CFE6F5'), ('Ⅲ', '갱생(비구조적)', '#CFE9DC'),
              ('Ⅳ', '갱생/교체(준·완전 구조적)', '#F3E2C2'), ('Ⅴ', '교체', '#F0CFC8')]
    x = 50; wds = [230, 230, 300, 420, 230]
    for (g, s, c), w in zip(grades, wds):
        dr.rounded_rectangle([x, 690, x + w, 800], 14, fill=c, outline=INK, width=2)
        dr.text((x + w / 2 - dr.textlength(g, font=f(30)) / 2, 700), g, font=f(30), fill=INK)
        dr.text((x + w / 2 - dr.textlength(s, font=f(24)) / 2, 752), s, font=f(24), fill=INK)
        x += w + 22
    dr.text((50, 820), '주철관·덕타일주철관 판단 예(안전계수):  2.5 초과 → Ⅲ   /   1.0 초과~2.5 이하 → Ⅳ   /   1.0 이하 → Ⅴ', font=f(24), fill=INK)
    dr.text((50, 860), '안전계수 = 관의 잔존강도(설계응력) ÷ 내·외부 하중으로 생긴 응력.  ①~④는 순서가 아니라 관 상태별 선택지다.', font=f(22), fill=GRAYC)
    dr.rounded_rectangle([40, 910, 1560, 975], 12, fill='#F7F2E8')
    x = 60
    for s, c in [('기존관', PIPE), ('녹·스케일', RUST), ('비구조적 도막', EPOXY), ('구조적 라이너', LINER), ('통수 단면', WATER)]:
        dr.rectangle([x, 932, x + 22, 954], fill=c, outline=INK); dr.text((x + 30, 927), s, font=f(22), fill=INK)
        x += 30 + dr.textlength(s, font=f(22)) + 50
    im.save(OUT / FIG_NAME, quality=92)


if __name__ == '__main__':
    figure()
