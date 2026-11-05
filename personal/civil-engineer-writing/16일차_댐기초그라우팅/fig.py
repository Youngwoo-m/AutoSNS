"""16일차 개념도 — 댐 기초처리 그라우팅의 종류와 위치(콘크리트 중력댐·필댐, 축척 없음)."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent
FIG_NAME = '댐기초그라우팅_종류_개념도.jpg'
PRET = '/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf'
INK, GRAYC, ROCK, ROCK2, CONC, WATER, CORE, SHELL = '#263746', '#7A8790', '#CBBFA8', '#B5A78C', '#D7D9DB', '#4C8DB5', '#B98B5E', '#E3D6B8'
CUR, CON, CNT, BLK = '#B6462F', '#2F7D5B', '#C98A1B', '#6A4C93'
f = lambda z: ImageFont.truetype(PRET, z)


def holes(dr, x0, x1, y0, depth, n, col, w=4):
    for k in range(n):
        x = x0 + (x1 - x0) * k / max(n - 1, 1)
        dr.line([(x, y0), (x, y0 + depth)], fill=col, width=w)


def figure():
    W, H = 1600, 1000
    im = Image.new('RGB', (W, H), 'white'); dr = ImageDraw.Draw(im)
    dr.text((50, 26), '댐 기초처리 그라우팅 — 무엇을 어디에 넣는가(축척 없음)', font=f(38), fill=INK)
    # 왼쪽: 콘크리트 중력댐
    gy = 520
    dr.text((60, 100), '(가) 콘크리트 중력댐', font=f(28), fill=INK)
    dr.rectangle([40, gy, 780, 900], fill=ROCK)
    for y in (610, 700, 790):
        dr.line([(40, y), (780, y + 25)], fill=ROCK2, width=2)       # 절리(단순화)
    dr.rectangle([40, 300, 230, gy], fill='#DCEBF5'); dr.line([(40, 300), (230, 300)], fill=WATER, width=4)
    dr.text((55, 262), '▽ 저수위', font=f(22), fill=WATER)
    dr.polygon([(230, 180), (300, 180), (600, gy), (230, gy)], fill=CONC, outline=INK)
    dr.text((300, 380), '댐체', font=f(26), fill=INK)
    holes(dr, 330, 580, gy, 70, 7, CON)                               # 압밀
    holes(dr, 255, 285, gy, 330, 2, CUR, 5)                           # 커튼
    dr.line([(230, gy), (600, gy)], fill=CNT, width=6)                # 콘택트
    dr.line([(290, gy + 240), (400, gy + 300)], fill=CUR, width=2)
    dr.text((405, gy + 285), '커튼: 상류 쪽, 좁고 깊게', font=f(21), fill=CUR)
    dr.line([(470, gy + 75), (520, gy + 150)], fill=CON, width=2)
    dr.text((470, gy + 155), '압밀: 기초 표층, 넓고 얕게', font=f(21), fill=CON)
    dr.line([(600, gy), (650, gy - 60)], fill=CNT, width=2)
    dr.text((610, gy - 95), '콘택트: 접촉면', font=f(21), fill=CNT)
    dr.text((70, gy + 330), '침투수', font=f(20), fill=WATER)
    dr.line([(70, gy + 320), (240, gy + 200)], fill=WATER, width=3)
    # 오른쪽: 필댐(중심 코어)
    ox = 820
    dr.text((ox + 20, 100), '(나) 필댐(중심 코어형)', font=f(28), fill=INK)
    dr.rectangle([ox, gy, 1560, 900], fill=ROCK)
    for y in (620, 720, 810):
        dr.line([(ox, y + 20), (1560, y)], fill=ROCK2, width=2)
    dr.polygon([(ox + 40, gy), (1190, 200), (1240, 200), (1540, gy)], fill=SHELL, outline=INK)
    dr.polygon([(1130, gy), (1190, 200), (1240, 200), (1300, gy)], fill=CORE, outline=INK)
    dr.text((1165, 330), '코어', font=f(24), fill='white')
    dr.text((ox + 150, 420), '투수존', font=f(22), fill=INK); dr.text((1390, 420), '투수존', font=f(22), fill=INK)
    holes(dr, 1140, 1290, gy, 55, 6, BLK)                             # 블랭킷
    holes(dr, 1205, 1225, gy, 330, 2, CUR, 5)                         # 커튼
    dr.line([(1290, gy + 50), (1360, gy + 120)], fill=BLK, width=2)
    dr.text((1300, gy + 125), '블랭킷: 코어 밑 표층', font=f(21), fill=BLK)
    dr.line([(1203, gy + 230), (1100, gy + 270)], fill=CUR, width=2)
    dr.text((ox + 30, gy + 285), '커튼: 코어 중심선 아래 깊게', font=f(21), fill=CUR)
    # 아래 범례
    dr.rounded_rectangle([40, 920, 1560, 985], 12, fill='#F7F2E8')
    x = 60
    for s, c in [('커튼 = 차수·양압력 감소', CUR), ('압밀 = 지지력·변형 개선', CON), ('블랭킷 = 필댐 코어 접촉부 차수', BLK),
                 ('콘택트 = 접촉면 공극 충전', CNT), ('림 = 양안 우회 누수 차단(그림 생략)', GRAYC)]:
        dr.rectangle([x, 943, x + 22, 965], fill=c); dr.text((x + 30, 938), s, font=f(21), fill=INK)
        x += 30 + dr.textlength(s, font=f(21)) + 34
    im.save(OUT / FIG_NAME, quality=92)


if __name__ == '__main__':
    figure()
