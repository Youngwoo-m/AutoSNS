from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageEnhance
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
bg=Image.open(ROOT/'channels/naver-blog-auto/assets/banner_bg/winter.png').convert('RGB').resize((1080,1080))
bg=ImageEnhance.Brightness(bg).enhance(0.55)
d=ImageDraw.Draw(bg);F=str(ROOT/'common/assets/FONTS/Pretendard-Bold.otf');f=lambda n:ImageFont.truetype(F,n)
d.rounded_rectangle((74,72,530,150),radius=20,fill='#f2c45a');d.text((104,90),'건축시공기술사 · 5일차',font=f(34),fill='#1d2a35')
for i,t in enumerate(['벽체 결로','종류와 원인','결로방지 대책']):d.text((74,280+i*112),t,font=f(84),fill='#ffffff')
d.text((78,930),'재난안전과 GeoAI · 하루 한 문제',font=f(36),fill='#f2c45a')
bg.save(OUT/'banner.png')
