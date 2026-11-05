from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageEnhance
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
bg=Image.open(ROOT/'channels/naver-blog-auto/assets/banner_bg/safety.png').convert('RGB').resize((1080,1080))
bg=ImageEnhance.Brightness(bg).enhance(0.55)
d=ImageDraw.Draw(bg);F=str(ROOT/'common/assets/FONTS/Pretendard-Bold.otf');f=lambda n:ImageFont.truetype(F,n)
d.rounded_rectangle((74,72,530,150),radius=20,fill='#f2c45a');d.text((104,90),'건축시공기술사 · 3일차',font=f(34),fill='#1d2a35')
for i,t in enumerate(['철골 내화피복','내화뿜칠 공법과','두께 검사·보수']):d.text((74,280+i*112),t,font=f(84),fill='#ffffff')
d.text((78,930),'재난안전과 GeoAI · 하루 한 문제',font=f(36),fill='#f2c45a')
bg.save(OUT/'banner.png')
