"""14일차 개념도 — 비탈면 붕괴 형태 다섯 가지(축척 없음)."""
from pathlib import Path
import math
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent
FIG_NAME = '비탈면_붕괴형태_개념도.jpg'
PRET = '/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf'
INK, RED, GRAYC, SOFT, SOIL, ROCK, WATER = '#263746', '#B6462F', '#7A8790', '#EEF3F1', '#C9B48E', '#8E949A', '#4C8DB5'
f = lambda z: ImageFont.truetype(PRET, z)


def slope_poly(ox, oy, w=420, h=230):
    """왼쪽 위가 높은 깎기 비탈면 단면. 비탈 어깨(sx,sy)~비탈 끝(tx,ty)."""
    sx, sy, tx, ty = ox + 120, oy, ox + 300, oy + h - 40
    return [(ox, oy), (sx, sy), (tx, ty), (ox + w, ty), (ox + w, oy + h), (ox, oy + h)], (sx, sy, tx, ty)


def panel(dr, ox, oy, title, sub, kind, note, im=None):
    dr.rounded_rectangle([ox - 18, oy - 78, ox + 438, oy + 330], 14, fill=SOFT)
    dr.text((ox, oy - 66), title, font=f(30), fill=INK)
    dr.text((ox, oy - 28), sub, font=f(19), fill=GRAYC)
    if kind == 'wedge':                                  # 쐐기: 정면에서 본 비탈면 + V 모양 두 절리
        dr.rectangle([ox + 20, oy + 20, ox + 400, oy + 230], fill=ROCK)
        dr.polygon([(ox + 110, oy + 20), (ox + 310, oy + 20), (ox + 210, oy + 210)], fill='#A3A9AE')
        dr.line([(ox + 110, oy + 20), (ox + 210, oy + 210)], fill=RED, width=5)
        dr.line([(ox + 310, oy + 20), (ox + 210, oy + 210)], fill=RED, width=5)
        dr.text((ox + 30, oy + 240), '정면에서 본 비탈면 · 절리 두 개가 V자로 만남', font=f(17), fill=INK)
        dr.text((ox, oy + 280), note, font=f(20), fill=RED)
        return
    poly, (sx, sy, tx, ty) = slope_poly(ox, oy + 20)
    dr.polygon(poly, fill=ROCK if kind in ('plane', 'topple') else SOIL)
    lay = Image.new('RGBA', im.size, (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
    if kind == 'circle':                                 # 원호: 어깨 뒤에서 비탈 끝으로 휘는 활동면
        cx, cy, r = tx - 40, sy - 150, 300
        a0, a1 = math.degrees(math.atan2(sy - cy, sx - 70 - cx)), math.degrees(math.atan2(ty - cy, tx + 5 - cx))
        pts = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in [a0 + (a1 - a0) * i / 40 for i in range(41)]]
        ld.line(pts, fill=RED, width=5)
    elif kind == 'plane':                                # 평면: 비탈면과 같은 방향으로 기운 불연속면
        for k in range(1, 4):
            ld.line([(sx - 60 - k * 45, sy), (tx - k * 45, ty + 20)], fill='#5E646A', width=2)
        ld.line([(sx - 60, sy), (tx, ty)], fill=RED, width=5)
    elif kind == 'topple':                               # 전도: 비탈 안쪽으로 급하게 기운 절리
        for k in range(6):
            x = sx - 30 + k * 32
            ld.line([(x, sy - 5), (x - 45, ty + 60)], fill='#5E646A', width=3)
    elif kind == 'surface':                              # 표층유실: 얇은 토층 아래 경계
        ld.line([(sx - 30, sy + 16), (tx - 8, ty + 4)], fill=RED, width=5)
    mask = Image.new('L', im.size, 0); ImageDraw.Draw(mask).polygon(poly, fill=255)
    im.paste(lay, (0, 0), Image.composite(lay.getchannel('A'), mask, mask).point(lambda v: v))
    if kind == 'circle':
        dr.line([(tx - 80, ty - 80), (tx - 20, ty - 30)], fill=RED, width=4)
        dr.polygon([(tx - 12, ty - 22), (tx - 34, ty - 30), (tx - 22, ty - 46)], fill=RED)
    elif kind == 'plane':
        dr.text((tx + 10, sy + 40), '비탈면 쪽으로', font=f(17), fill=INK); dr.text((tx + 10, sy + 64), '기운 절리', font=f(17), fill=INK)
    elif kind == 'topple':
        dr.line([(sx + 30, sy + 40), (sx + 95, sy + 10)], fill=RED, width=4)
        dr.polygon([(sx + 105, sy + 5), (sx + 84, sy + 4), (sx + 92, sy + 24)], fill=RED)
        dr.text((tx + 10, sy + 40), '비탈 안쪽으로', font=f(17), fill=INK); dr.text((tx + 10, sy + 64), '급히 기운 절리', font=f(17), fill=INK)
    elif kind == 'surface':
        for k in range(6):
            x = ox + 160 + k * 35
            dr.line([(x, oy - 10), (x - 12, oy + 20)], fill=WATER, width=3)
        dr.text((tx + 10, sy + 40), '얕은 토층', font=f(17), fill=INK)
    dr.text((ox, oy + 280), note, font=f(20), fill=RED)


def legend(dr, ox, oy):
    dr.rounded_rectangle([ox - 18, oy - 78, ox + 438, oy + 330], 14, fill='#F7F2E8')
    dr.text((ox, oy - 66), '붕괴 원인 두 갈래', font=f(30), fill=INK)
    rows = [('내적 원인 — 저항력 감소', INK), ('· 풍화·이완으로 강도 저하', GRAYC), ('· 절리·층리 등 불연속면', GRAYC),
            ('· 다짐 부족, 점토 팽창·연화', GRAYC), ('외적 원인 — 작용력 증가', INK), ('· 강우 침투·지하수위 상승', GRAYC),
            ('· 비탈 끝 굴착, 상부 성토·하중', GRAYC), ('· 지진·발파 진동, 배수 막힘', GRAYC)]
    for i, (s, c) in enumerate(rows):
        dr.text((ox, oy - 10 + i * 40), s, font=f(23 if c == INK else 21), fill=c)


def figure():
    im = Image.new('RGB', (1500, 1060), 'white'); dr = ImageDraw.Draw(im)
    dr.text((50, 26), '비탈면 붕괴 형태 — 흙 비탈면과 암반 비탈면(축척 없음)', font=f(36), fill=INK)
    panel(dr, 60, 190, '① 원호 활동', '흙·풍화토 비탈면', 'circle', '휘어진 활동면을 따라 한 덩어리로 미끄러짐', im)
    panel(dr, 545, 190, '② 평면 파괴', '암반 비탈면', 'plane', '절리 하나를 따라 미끄러짐', im)
    panel(dr, 1030, 190, '③ 쐐기 파괴', '암반 비탈면', 'wedge', '두 절리 사이 쐐기가 빠짐', im)
    panel(dr, 60, 650, '④ 전도 파괴', '암반 비탈면', 'topple', '기둥 모양 암괴가 앞으로 넘어짐', im)
    panel(dr, 545, 650, '⑤ 표층 유실', '얕은 토층(집중호우)', 'surface', '표면 흙이 빗물에 쓸려 내려감', im)
    legend(dr, 1030, 650)
    dr.text((50, 1020), '직접 작성한 개념도 · 붉은 선 = 활동면·움직임 · 형태 분류는 일반적인 교과 분류를 따랐으며 단면은 단순화함', font=f(20), fill=GRAYC)
    im.save(OUT / FIG_NAME, quality=92)


if __name__ == '__main__':
    figure()
