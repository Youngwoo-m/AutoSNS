"""19일차 개념도 — 터널 콘크리트 라이닝 균열의 형태별 위치(단면·전개도, 축척 없음)."""
from pathlib import Path
import math
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent
FIG_NAME = '라이닝_균열형태_개념도.jpg'
PRET = '/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf'
INK, GRAYC, ROCK, SHOT, LIN = '#263746', '#7A8790', '#CFC3AA', '#B4ADA0', '#DCDFE2'
C_LONG, C_TRANS, C_SHEAR = '#B6462F', '#2E6FA8', '#2F7D5B'
f = lambda z: ImageFont.truetype(PRET, z)


def section(dr, ox, oy):
    """왼쪽: 터널 단면(마제형 단순화) — 천단·어깨·S.L·인버트 위치."""
    dr.rounded_rectangle([ox, oy, ox + 760, oy + 860], 14, outline='#C9D2D8', width=2)
    dr.text((ox + 20, oy + 14), '(가) 단면 — 균열이 잘 생기는 자리', font=f(30), fill=INK)
    cx, cy, R = ox + 380, oy + 470, 290
    dr.rectangle([ox + 2, oy + 70, ox + 758, oy + 858], fill=ROCK)
    for r, col in ((R + 70, SHOT), (R + 45, LIN)):
        dr.pieslice([cx - r, cy - r, cx + r, cy + r], 180, 360, fill=col)
        dr.rectangle([cx - r, cy, cx + r, cy + 230], fill=col)
    dr.pieslice([cx - R, cy - R, cx + R, cy + R], 180, 360, fill='white')
    dr.rectangle([cx - R, cy, cx + R, cy + 230], fill='white')
    dr.rectangle([cx - R - 45, cy + 230, cx + R + 45, cy + 300], fill=LIN)   # 인버트
    dr.line([(cx - R - 45, cy), (cx + R + 45, cy)], fill=GRAYC, width=2)
    dr.text((cx + R + 50, cy - 14), 'S.L', font=f(22), fill=INK)
    dr.text((cx - 60, cy + 245), '인버트', font=f(24), fill=INK)
    dr.text((ox + 24, oy + 80), '원지반(절리 암반)', font=f(22), fill=INK)
    dr.text((cx - 150, cy + 110), '바깥 띠: 숏크리트(·방수막)', font=f(22), fill=GRAYC)
    dr.text((cx - 150, cy + 142), '안쪽 띠: 콘크리트 라이닝', font=f(22), fill=GRAYC)
    # 천단부 ±20° 종방향 균열 영역
    r2 = R + 22
    dr.arc([cx - r2, cy - r2, cx + r2, cy + r2], 250, 290, fill=C_LONG, width=14)
    dr.text((cx - 150, cy - R - 110), '천단부 20° 범위: 종방향 균열이 많음', font=f(24), fill=C_LONG)
    # 어깨부 전단(경사) 균열
    for a in (215, 325):
        x, y = cx + r2 * math.cos(math.radians(a)), cy + r2 * math.sin(math.radians(a))
        dr.line([(x - 18, y - 18), (x + 18, y + 18)] if a == 215 else [(x + 18, y - 18), (x - 18, y + 18)], fill=C_SHEAR, width=6)
    dr.text((ox + 175, cy - 150), '어깨부: 전단(경사) 균열', font=f(22), fill=C_SHEAR)
    # 배면 공동
    dr.ellipse([cx + 40, cy - R - 64, cx + 120, cy - R - 32], fill='#F4F1EA', outline=INK, width=2)
    dr.text((cx + 130, cy - R - 64), '배면 공동 → 휨·편압', font=f(20), fill=INK)
    # S.L 부근 침강, 인버트 온도
    dr.text((ox + 105, cy + 20), 'S.L 부근: 타설 계면·침강 균열', font=f(22), fill=C_TRANS)
    dr.text((cx - 260, cy + 310), '두꺼운 인버트: 수화열 온도균열', font=f(22), fill=INK)


def development(dr, ox, oy):
    """오른쪽: 라이닝 전개도 — 한 블록(약 10 m)씩 타설, 시공이음."""
    dr.rounded_rectangle([ox, oy, ox + 760, oy + 860], 14, outline='#C9D2D8', width=2)
    dr.text((ox + 20, oy + 14), '(나) 전개도 — 라이닝을 펼쳐 본 모양', font=f(30), fill=INK)
    x0, x1, y0, y1 = ox + 90, ox + 730, oy + 130, oy + 690
    dr.rectangle([x0, y0, x1, y1], fill=LIN, outline=INK, width=2)
    labels = [('좌 S.L', y0), ('어깨', y0 + 140), ('천단', (y0 + y1) // 2), ('어깨', y1 - 140), ('우 S.L', y1)]
    for s, y in labels:
        dr.line([(x0 - 8, y), (x0, y)], fill=INK, width=2); dr.text((ox + 10, y - 14), s, font=f(20), fill=INK)
    joints = [x0 + i * 160 for i in range(5)]
    for x in joints[1:-1]:
        dr.line([(x, y0), (x, y1)], fill=GRAYC, width=3)
    dr.text((x0, y1 + 10), '시공이음(블록 길이 약 10 m, 현장 사례)', font=f(20), fill=GRAYC)
    yc = (y0 + y1) // 2
    # 종방향 균열 — 천단을 따라 길게
    dr.line([(x0 + 30, yc - 10), (x0 + 140, yc - 4), (x0 + 260, yc + 6), (x0 + 330, yc)], fill=C_LONG, width=6)
    dr.line([(x0 + 400, yc + 20), (x0 + 520, yc + 14), (x0 + 600, yc + 24)], fill=C_LONG, width=6)
    # 횡방향 균열 — 시공이음 주변·블록 중앙
    for x in (joints[1] + 22, joints[2] + 80, joints[3] - 20):
        dr.line([(x, y0 + 30), (x + 4, y0 + 200), (x - 2, y0 + 360)], fill=C_TRANS, width=6)
    # 전단 균열 — 어깨부 경사
    dr.line([(x0 + 60, y1 - 120), (x0 + 130, y1 - 190)], fill=C_SHEAR, width=6)
    dr.line([(x0 + 520, y0 + 110), (x0 + 590, y0 + 180)], fill=C_SHEAR, width=6)
    ly = y1 + 50
    for col, s in ((C_LONG, '종방향 균열: 터널 축과 나란함, 폭·길이가 큼'), (C_TRANS, '횡방향 균열: 축에 직교, 시공이음 주변'),
                   (C_SHEAR, '전단 균열: 대각선, 주로 어깨부')):
        dr.line([(ox + 30, ly + 12), (ox + 80, ly + 12)], fill=col, width=7); dr.text((ox + 92, ly), s, font=f(21), fill=INK); ly += 36


def figure():
    W, H = 1600, 1000
    im = Image.new('RGB', (W, H), 'white'); dr = ImageDraw.Draw(im)
    dr.text((40, 22), '터널 콘크리트 라이닝 균열 — 형태와 생기는 자리(축척 없음)', font=f(38), fill=INK)
    section(dr, 40, 100); development(dr, 820, 100)
    im = im.crop((0, 0, W, 980))
    im.save(OUT / FIG_NAME, quality=90)


if __name__ == '__main__':
    figure(); print('ok')
