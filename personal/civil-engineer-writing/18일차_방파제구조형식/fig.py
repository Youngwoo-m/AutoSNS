"""18일차 개념도 — 방파제 구조형식별 단면(경사식·소파블록 피복·직립식·혼성식, 축척 없음)."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent
FIG_NAME = '방파제_구조형식_단면개념도.jpg'
PRET = '/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf'
INK, GRAYC, SEA, SEAF, BED = '#263746', '#7A8790', '#4C8DB5', '#DCEBF5', '#D9CDB2'
CORE, ARMOR, BLOCK, CAIS, CAP, FOOT = '#B9AE98', '#8F8573', '#9AA7B0', '#D7D9DB', '#BFC4C8', '#6F7F8C'
RED, GRN = '#B6462F', '#2F7D5B'
f = lambda z: ImageFont.truetype(PRET, z)


def panel(dr, ox, oy, title, note, kind):
    w, h = 740, 400
    dr.rounded_rectangle([ox, oy, ox + w, oy + h], 14, outline='#C9D2D8', width=2)
    dr.text((ox + 20, oy + 14), title, font=f(28), fill=INK)
    sea_y, bed_y = oy + 170, oy + 330
    dr.rectangle([ox + 2, sea_y, ox + w - 2, bed_y], fill=SEAF)
    dr.line([(ox + 2, sea_y), (ox + w - 2, sea_y)], fill=SEA, width=3)
    dr.rectangle([ox + 2, bed_y, ox + w - 2, oy + h - 2], fill=BED)
    dr.text((ox + 24, sea_y - 30), '외해 ▽', font=f(20), fill=SEA)
    dr.text((ox + w - 110, sea_y - 30), '▽ 항내', font=f(20), fill=SEA)
    cx = ox + w // 2
    if kind in ('rubble', 'block'):
        top = oy + 120
        dr.polygon([(cx - 260, bed_y), (cx - 60, top), (cx + 60, top), (cx + 230, bed_y)], fill=CORE)
        if kind == 'rubble':
            dr.polygon([(cx - 260, bed_y), (cx - 60, top), (cx - 40, top), (cx - 222, bed_y)], fill=ARMOR)
            dr.text((cx - 250, oy + 200), '피복석', font=f(21), fill=INK)
        else:
            crest = top - 21                      # 블록 윗면 = 상치콘크리트 윗면
            for layer in (0, 1):
                for k in range(7):
                    t = k / 6; x = cx - 250 + 40 * layer + 120 * t; y = bed_y - 21 - (bed_y - 21 - crest) * t
                    dr.ellipse([x - 21, y - 21, x + 21, y + 21], fill=BLOCK, outline=INK)
            dr.text((cx - 300, oy + 345), '소파블록(테트라포드 등) 2층 피복', font=f(20), fill=INK)
            dr.line([(cx - 151, top - 50), (cx - 69, top - 50)], fill=RED, width=3)
            dr.text((cx - 330, top - 62), '어깨폭: 블록 2개 이상', font=f(18), fill=RED)
        dr.rectangle([cx - 60, top - 40, cx + 60, top], fill=CAP, outline=INK)
        dr.text((cx - 48, top - 36), '상치콘크리트', font=f(17), fill=INK)
        dr.text((cx - 20, oy + 250), '사석', font=f(22), fill=INK)
    elif kind == 'vertical':
        dr.rectangle([cx - 70, oy + 110, cx + 70, bed_y], fill=CAIS, outline=INK, width=2)
        dr.rectangle([cx - 70, oy + 80, cx + 70, oy + 110], fill=CAP, outline=INK)
        dr.text((cx - 40, oy + 220), '케이슨', font=f(24), fill=INK)
        dr.text((cx - 45, oy + 255), '(속채움)', font=f(18), fill=GRAYC)
        dr.rectangle([cx - 90, bed_y - 8, cx + 90, bed_y], fill=FOOT)
        dr.line([(cx - 190, oy + 130), (cx - 80, oy + 130)], fill=RED, width=4); dr.polygon([(cx - 200, oy + 130), (cx - 182, oy + 120), (cx - 182, oy + 140)], fill=RED)
        dr.text((cx - 300, oy + 100), '파랑 반사', font=f(20), fill=RED)
    else:  # composite
        mound = bed_y - 70
        dr.polygon([(cx - 280, bed_y), (cx - 170, mound), (cx + 150, mound), (cx + 260, bed_y)], fill=CORE)
        for x in (cx - 160, cx - 120, cx + 100, cx + 140):
            dr.rectangle([x - 18, mound - 22, x + 18, mound], fill=FOOT, outline=INK)
        dr.rectangle([cx - 70, oy + 110, cx + 70, mound], fill=CAIS, outline=INK, width=2)
        dr.rectangle([cx - 70, oy + 80, cx + 70, oy + 110], fill=CAP, outline=INK)
        dr.text((cx - 40, oy + 165), '케이슨', font=f(24), fill=INK)
        dr.text((cx - 70, mound + 20), '사석 마운드', font=f(21), fill=INK)
        dr.text((cx - 270, mound - 52), '근고블록', font=f(19), fill=INK)
    dr.text((ox + 20, oy + h + 10), note, font=f(21), fill=GRN)


def figure():
    W, H = 1600, 1080
    im = Image.new('RGB', (W, H), 'white'); dr = ImageDraw.Draw(im)
    dr.text((40, 22), '방파제 구조형식별 단면 — 파랑을 무엇으로 막는가(축척 없음)', font=f(38), fill=INK)
    panel(dr, 40, 90, '(가) 경사식(사석식)', '사면에서 파를 부숴 에너지 소산 · 검토: 피복재 안정중량', 'rubble')
    panel(dr, 820, 90, '(나) 경사식(소파블록 피복)', '블록 공극·맞물림으로 소파 · 검토: 블록 중량·어깨폭·마루높이', 'block')
    panel(dr, 40, 580, '(다) 직립식(케이슨식)', '벽체로 파를 반사, 자중·마찰로 저항 · 검토: 활동·전도·지지력', 'vertical')
    panel(dr, 820, 580, '(라) 혼성식', '사석 마운드 위에 직립부 · 검토: 마운드 피복 + 직립부 안정 + 세굴', 'composite')
    im.save(OUT / FIG_NAME, quality=90)


if __name__ == '__main__':
    figure(); print('ok')
