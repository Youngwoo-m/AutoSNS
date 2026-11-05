from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path('/Volumes/USB256/devAPP/AutoSNS');OUT=Path(__file__).resolve().parent
fp=str(ROOT/'assets/FONTS/Pretendard-Bold.otf');f=lambda n:ImageFont.truetype(fp,n)
W,H=1480,1000;im=Image.new('RGB',(W,H),'#f3f6fa');d=ImageDraw.Draw(im)
d.text((45,24),'강관비계 구조 기준 한눈에 보기 (산업안전보건기준에 관한 규칙 제59·60조, 별표 5)',font=f(34),fill='#112b45')
# 입면: 기둥 5열, 띠장 여러 단
gx0,gy0,gx1,gy1=230,140,780,900
cols=[gx0+i*(gx1-gx0)/4 for i in range(5)];rows=[gy1-j*(gy1-gy0)/7 for j in range(8)]
d.rectangle((gx0-40,gy1,gx1+40,gy1+18),fill='#c9b79c')
for x in cols:
  d.line([(x,gy0),(x,gy1)],fill='#244a66',width=6);d.rectangle((x-16,gy1-10,x+16,gy1),fill='#8a2c1d')
for y in rows[1:]: d.line([(gx0,y),(gx1,y)],fill='#5b84a3',width=4)
for i in range(4):
  x0,x1=cols[i],cols[i+1];d.line([(x0,rows[0]),(x1,rows[3])],fill='#d08a2c',width=3) if i%2==0 else d.line([(x0,rows[3]),(x1,rows[0])],fill='#d08a2c',width=3)
# 아래쪽 2본 구간 표시
y14=rows[2]
for x in cols: d.line([(x+9,y14),(x+9,gy1)],fill='#244a66',width=6)
# 치수
def dim_h(x0,x1,y,t):
  d.line([(x0,y),(x1,y)],fill='#8a2c1d',width=2);d.line([(x0,y-8),(x0,y+8)],fill='#8a2c1d',width=2);d.line([(x1,y-8),(x1,y+8)],fill='#8a2c1d',width=2);d.text(((x0+x1)/2-80,y-38),t,font=f(24),fill='#8a2c1d')
dim_h(cols[1],cols[2],gy0-20,'기둥 간격(띠장 방향) 1.85m 이하')
d.line([(gx1+50,rows[4]),(gx1+50,rows[5])],fill='#8a2c1d',width=3);d.text((gx1+62,rows[5]+4),'띠장',font=f(24),fill='#8a2c1d');d.text((gx1+62,rows[5]+34),'간격',font=f(24),fill='#8a2c1d');d.text((gx1+62,rows[5]+64),'2.0m',font=f(24),fill='#8a2c1d');d.text((gx1+62,rows[5]+94),'이하',font=f(24),fill='#8a2c1d')
# 31m 표시
d.line([(gx0-70,gy0),(gx0-70,y14)],fill='#14532d',width=4);d.text((40,(gy0+y14)/2-60),'제일\n윗부분\n에서 31m',font=f(26),fill='#14532d')
d.line([(gx0-70,y14),(gx0-70,gy1)],fill='#7a1f14',width=4);d.text((40,(y14+gy1)/2-40),'그 아래\n기둥은\n2개 강관',font=f(26),fill='#7a1f14')
d.line([(gx0-85,y14),(gx1+20,y14)],fill='#14532d',width=2)
# 오른쪽 상자
bx=930
items=[('장선 방향 기둥 간격','1.5m 이하'),('비계기둥 간 적재하중','400kg 이하'),('벽이음 — 단관비계','수직 5m · 수평 5m'),('벽이음 — 틀비계(높이 5m 미만 제외)','수직 6m · 수평 8m'),('밑둥','밑받침철물·깔판·받침목'),('보강','교차 가새, 원칙은 쌍줄'),('가공전로 근접','이설 또는 절연용 방호구')]
for i,(a,b) in enumerate(items):
  y=130+i*112;d.rounded_rectangle((bx,y,W-40,y+96),radius=14,fill='#dcebf7',outline='#244a66',width=2)
  d.text((bx+18,y+10),a,font=f(24),fill='#102c46');d.text((bx+18,y+48),b,font=f(30),fill='#8a2c1d')
d.text((45,945),'근거: 산업안전보건기준에 관한 규칙(국가법령정보센터 현행, 2026-11-03 확인). 그림은 비례가 맞지 않는 개념도예요. 시스템비계 벽 연결재는 제조사 기준(제69조제5호).',font=f(20),fill='#4a5964')
im.save(OUT/'강관비계_구조기준.png');print('ok')

from PIL import ImageOps
bg=Image.open(ROOT/'channels/naver-blog-auto/assets/banner_bg/safety.png').convert('RGB')
bg=ImageOps.fit(bg,(1080,1080));ov=Image.new('RGBA',(1080,1080),(8,26,43,110));bg=Image.alpha_composite(bg.convert('RGBA'),ov);dr=ImageDraw.Draw(bg)
dr.rounded_rectangle((50,600,1030,1030),radius=25,fill=(8,26,43,235))
dr.text((90,642),'건설안전기술사 · 5일차',font=f(35),fill='#bde5f6')
dr.text((90,710),'비계 조립·해체 안전',font=f(72),fill='white')
dr.text((90,805),'강관비계와 시스템비계',font=f(54),fill='white')
dr.text((90,880),'설치 준수사항 비교',font=f(54),fill='white')
dr.text((70,45),'재난안전과 GeoAI',font=f(34),fill='white')
bg.convert('RGB').save(OUT/'banner.png')
print('banner')
