from pathlib import Path
ROOT=Path('/Volumes/USB256/devAPP/AutoSNS');OUT=Path(__file__).resolve().parent
from PIL import Image,ImageDraw,ImageFont
im=Image.new('RGB',(1300,650),'#f3f6fa');draw=ImageDraw.Draw(im)
fontpath=str(ROOT/'assets/FONTS/Pretendard-Bold.otf');f=lambda n:ImageFont.truetype(fontpath,n)
draw.text((45,35),'위험성평가: 위험 발견을 개선 이행으로 연결',font=f(40),fill='#112b45')
blocks=[('사전준비','대상·방법 정하기'),('요인 파악','작업·노출 확인'),('위험성 결정','허용 여부 판단'),('개선 이행','대책 수립·실행'),('후속관리','확인·공유·기록')]
for i,(a,b) in enumerate(blocks):
 x=35+i*252;draw.rounded_rectangle((x,160,x+225,340),radius=16,fill='#dce9f5' if i in (1,2,3) else '#e5e9ed',outline='#42667f',width=2)
 draw.text((x+15,185),a,font=f(29),fill='#102c46');draw.text((x+15,265),b,font=f(22),fill='#213e52')
 if i<4:draw.text((x+230,222),'→',font=f(24),fill='#285a7e')
draw.rounded_rectangle((275,365,1016,430),radius=10,fill='#dce9f5');draw.text((300,382),'법정 핵심절차: 요인 파악 → 위험성 결정 → 개선대책 수립·이행',font=f(22),fill='#173f5b')
draw.text((50,490),'사전준비·후속관리를 더한 학습용 흐름 · 법정 다섯 단계가 아님',font=f(28),fill='#4c3c17')
draw.text((50,548),'근거: 산업안전보건법 시행규칙 제37조제1항(시행 2026. 8. 1.)',font=f(23),fill='#4a5964')
im.save(OUT/'위험성평가_흐름도.png')
print('assets rendered')

from PIL import ImageOps
bg=Image.open(ROOT/'dept/naver-blog-auto/assets/banner_bg/safety.png').convert('RGB')
bg=ImageOps.fit(bg,(1080,1080));overlay=Image.new('RGBA',(1080,1080),(8,26,43,110));bg=Image.alpha_composite(bg.convert('RGBA'),overlay);dr=ImageDraw.Draw(bg)
dr.rounded_rectangle((50,600,1030,1030),radius=25,fill=(8,26,43,235))
dr.text((90,642),'건설안전기술사 · 2일차',font=f(35),fill='#bde5f6')
dr.text((90,710),'위험성평가 절차',font=f(72),fill='white')
dr.text((90,805),'위험 발견에서',font=f(54),fill='white')
dr.text((90,880),'개선 이행까지',font=f(54),fill='white')
dr.text((70,45),'재난안전과 GeoAI',font=f(34),fill='white')
bg.convert('RGB').save(OUT/'banner.png')
