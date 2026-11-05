"""15일차 개념도 — 미고결 저토피 터널의 지표침하 원인과 저감대책(축척 없음)."""
from pathlib import Path
import math
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent
FIG_NAME = '저토피터널_지표침하_개념도.jpg'
PRET = '/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf'
INK, RED, GRAYC, SOIL, SOIL2, WATER, STEEL, GOLD = '#263746', '#B6462F', '#7A8790', '#D9C7A0', '#C2AB7E', '#4C8DB5', '#4A5560', '#C98A1B'
f = lambda z: ImageFont.truetype(PRET, z)


def figure():
    W, H = 1500, 1000
    im = Image.new('RGB', (W, H), 'white'); dr = ImageDraw.Draw(im)
    dr.text((50, 26), '미고결 저토피 터널 — 지표침하가 생기는 길과 막는 방법(축척 없음)', font=f(36), fill=INK)
    gy, cx, cy, r = 260, 560, 610, 140                  # 지표 높이, 터널 중심, 반지름
    # 지반(미고결 토사)과 지하수위
    dr.rectangle([60, gy, 1060, 900], fill=SOIL)
    dr.rectangle([60, 470, 1060, 900], fill=SOIL2)
    dr.line([(60, 430), (1060, 430)], fill=WATER, width=4)
    dr.text((80, 396), '▽ 지하수위', font=f(22), fill=WATER)
    # 정규분포 침하곡선(과장)
    i = 190
    pts = [(x, gy + 70 * math.exp(-((x - cx) ** 2) / (2 * i * i))) for x in range(60, 1061, 5)]
    dr.polygon([(60, gy)] + pts + [(1060, gy)], fill='white')
    dr.line([(60, gy), (1060, gy)], fill=GRAYC, width=2)
    dr.line(pts, fill=RED, width=5)
    for x, s in [(cx - i, '변곡점 x = −i'), (cx + i, '변곡점 x = +i')]:
        dr.line([(x, gy - 30), (x, gy + 60)], fill=GRAYC, width=2)
        dr.text((x - 70, gy - 62), s, font=f(19), fill=GRAYC)
    dr.text((cx + 20, gy + 66), 'S max', font=f(22), fill=RED)
    # 이완영역(굴뚝 모양)
    dr.line([(cx - r - 5, cy), (cx - 240, gy + 110), (cx + 240, gy + 110), (cx + r + 5, cy)], fill=RED, width=3)
    dr.text((cx - 225, gy + 118), '이완영역', font=f(22), fill=RED)
    # 강관다단 그라우팅(우산 모양)
    for k in range(-5, 6):
        a = math.radians(90 + k * 13)
        x0, y0 = cx + (r + 8) * math.cos(a), cy - (r + 8) * math.sin(a)
        dr.line([(x0, y0), (x0 + 30 * math.cos(a), y0 - 30 * math.sin(a))], fill=STEEL, width=5)
    dr.line([(330, 520), (cx - 95, cy - 120)], fill=STEEL, width=2)
    dr.text((80, 524), '천단 보강(강관다단 그라우팅)', font=f(20), fill=STEEL)
    # 터널
    dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill='#F4F1EA', outline=INK, width=6)
    dr.text((cx - 48, cy - 15), '터널 D', font=f(26), fill=INK)
    dr.line([(cx + r + 150, gy), (cx + r + 150, cy)], fill=INK, width=2)
    dr.line([(cx + r, cy), (cx + r + 150, cy)], fill=INK, width=1)
    dr.text((cx + r + 160, 470), 'z₀', font=f(24), fill=INK)
    dr.text((cx + r + 160, 504), '터널 중심', font=f(18), fill=INK)
    dr.text((cx + r + 160, 528), '깊이', font=f(18), fill=INK)
    # 원인 화살표
    dr.line([(cx - r - 120, cy + 60), (cx - r + 5, cy + 30)], fill=WATER, width=4)
    dr.polygon([(cx - r + 10, cy + 29), (cx - r - 12, cy + 18), (cx - r - 8, cy + 42)], fill=WATER)
    dr.text((80, cy + 70), '지하수 유입 → 세립분 유출', font=f(20), fill=WATER)
    # 오른쪽 범례
    ox = 1100
    dr.rounded_rectangle([ox - 10, 120, 1470, 940], 14, fill='#F7F2E8')
    rows = [('침하 원인', INK, 28), ('· 토피가 얕아 아칭이 약함', GRAYC, 21), ('· 미고결 토사, 짧은 자립시간', GRAYC, 21),
            ('· 막장 붕락·여굴, 굴진장 과다', GRAYC, 21), ('· 지보·인버트 폐합 지연', GRAYC, 21), ('· 지하수 유입·수위 저하', GRAYC, 21),
            ('', GRAYC, 12),
            ('저감대책', INK, 28), ('· 천단 보강: 강관다단·훠폴링', GRAYC, 21), ('· 막장 보강: 숏크리트·막장볼트', GRAYC, 21),
            ('· 분할굴착(링컷·CD), 굴진장 축소', GRAYC, 21), ('· 조기 폐합(가인버트)', GRAYC, 21), ('· 차수·지반개량 그라우팅', GRAYC, 21),
            ('· 지표·천단 계측과 단계별 대응', GRAYC, 21)]
    y = 140
    for s, c, z in rows:
        dr.text((ox + 10, y), s, font=f(z), fill=c); y += z + 26
    dr.text((50, 950), '직접 작성한 개념도 · 붉은 선 = 정규분포 침하곡선(크기 과장) · 이완영역·보강 범위는 단순화함', font=f(20), fill=GRAYC)
    im.save(OUT / FIG_NAME, quality=92)


if __name__ == '__main__':
    figure()
