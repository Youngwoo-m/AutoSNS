from pathlib import Path
import json
from PIL import Image,ImageDraw,ImageFont
P=Path(__file__).resolve().parent;A=json.loads((P/'analysis.json').read_text());fn='/Volumes/USB256/devAPP/AutoSNS/FONTS/KoPubWorld Dotum_Pro Bold.otf';font=lambda n:ImageFont.truetype(fn,n)
im=Image.new('RGB',(1600,900),'#f7f9fc');d=ImageDraw.Draw(im)
d.text((80,45),'최근 5개 시행연도: 주요 기술 관련 표현의 등장',font=font(46),fill='#0f172a');d.text((80,112),'Q-net 공식 문제지 10회차·310문항 / 각 연도 62문항',font=font(28),fill='#475569')
colors=['#155e75','#6d28d9','#c2410c'];names=['GNSS·RTK·보정정보','LiDAR·레이저·점군','AI·온톨로지']
for j,(n,c) in enumerate(zip(names,colors)):
 x=100+j*490;d.rectangle((x,180,x+25,205),fill=c);d.text((x+38,174),n,font=font(28),fill='#0f172a')
for v in range(0,9,2):
 y=710-v*55;d.line((120,y,1510,y),fill='#cbd5e1',width=2);d.text((73,y-17),str(v),font=font(25),fill='#475569')
for i,y in enumerate(range(2022,2027)):
 center=270+i*265;d.text((center,735),str(y),anchor='mt',font=font(29),fill='#334155')
 for j,(n,c) in enumerate(zip(names,colors)):
  v=next(t for t in A['themes'] if t['theme']==n)['by_year'][str(y)];x=center+(j-1)*55;top=710-v*55
  if v:d.rectangle((x-22,top,x+22,710),fill=c)
  d.text((x,top-35),str(v),anchor='mt',font=font(27),fill=c)
d.text((80,815),'세로축: 관련 표현 포함 문항 수 / 그룹 간 중복 허용',font=font(26),fill='#475569');d.text((80,855),'검색 규칙에 따른 집계이며 출제 확률·공식 배점 비중을 뜻하지 않습니다.',font=font(24),fill='#475569');im.save(P/'출제경향_연도별비교.jpg',quality=95)
