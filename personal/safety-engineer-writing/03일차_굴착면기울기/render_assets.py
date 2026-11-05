from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageOps
ROOT=Path('/Volumes/USB256/devAPP/AutoSNS');OUT=Path(__file__).resolve().parent
fp=str(ROOT/'assets/FONTS/Pretendard-Bold.otf');f=lambda n:ImageFont.truetype(fp,n)
# 단면도: 높이 3.0m(가상)에서 지반별 수평거리
W,H=1480,600;im=Image.new('RGB',(W,H),'#f3f6fa');d=ImageDraw.Draw(im)
d.text((45,28),'지반 종류별 굴착면 기울기 — 높이 3.0m(가상 예시)일 때 수평거리',font=f(36),fill='#112b45')
soils=[('모래','1 : 1.8',1.8,'#e8d9a8'),('연암 및 풍화암','1 : 1.0',1.0,'#c9c2b4'),('경암','1 : 0.5',0.5,'#a9b0b8'),('그 밖의 흙','1 : 1.2',1.2,'#d8c39a')]
s=50; base=400; hpx=3.0*s; x0=150
for name,ratio,n,col in soils:
  run=3.0*n*s; top=(x0,base-hpx); toe=(x0+run,base)
  d.polygon([(x0-80,base-hpx),top,toe,(toe[0]+40,base),(toe[0]+40,base+30),(x0-80,base+30)],fill=col)
  d.line([(x0-80,base-hpx),top],fill='#5b4a2a',width=3); d.line([toe,(toe[0]+40,base)],fill='#5b4a2a',width=3)
  d.line([top,toe],fill='#8a2c1d',width=5)
  d.line([(x0-95,base-hpx),(x0-95,base)],fill='#244a66',width=3); d.text((x0-150,base-hpx/2-14),'3.0m',font=f(20),fill='#244a66')
  d.line([(x0,base+45),(toe[0],base+45)],fill='#244a66',width=3)
  d.text((x0,base+55),f'{3.0*n:.1f} m',font=f(26),fill='#173f5b')
  d.text((x0-70,base-hpx-78),name,font=f(28),fill='#102c46');d.text((x0-70,base-hpx-42),ratio,font=f(26),fill='#8a2c1d')
  x0+= max(run,75)+190
d.text((45,505),'갈색 선 = 굴착면, 오른쪽 아래 빈 곳 = 굴착한 공간. 수평거리 = 높이 × 기울기 뒤 숫자 · 근거: 안전보건규칙 별표 11(개정 2023. 11. 14.)',font=f(21),fill='#4a5964')
d.text((45,540),'기울기는 굴착면 높이에 대한 수평거리의 비율(별표 11 비고 1). 실제 기울기는 지반조사·설계도서로 정함',font=f(21),fill='#4a5964')
im.save(OUT/'굴착면기울기_단면도.png')
bg=Image.open(ROOT/'dept/naver-blog-auto/assets/banner_bg/survey.png').convert('RGB')
bg=ImageOps.fit(bg,(1080,1080));ov=Image.new('RGBA',(1080,1080),(8,26,43,110));bg=Image.alpha_composite(bg.convert('RGBA'),ov);dr=ImageDraw.Draw(bg)
dr.rounded_rectangle((50,600,1030,1030),radius=25,fill=(8,26,43,235))
dr.text((90,642),'건설안전기술사 · 3일차',font=f(35),fill='#bde5f6')
dr.text((90,710),'굴착면 기울기 기준',font=f(72),fill='white')
dr.text((90,805),'사전조사부터',font=f(54),fill='white')
dr.text((90,880),'붕괴 예방까지',font=f(54),fill='white')
dr.text((70,45),'재난안전과 GeoAI',font=f(34),fill='white')
bg.convert('RGB').save(OUT/'banner.png')
print('ok')
