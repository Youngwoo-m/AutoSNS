from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path('/Volumes/USB256/devAPP/AutoSNS');OUT=Path(__file__).resolve().parent
fp=str(ROOT/'assets/FONTS/Pretendard-Bold.otf');f=lambda n:ImageFont.truetype(fp,n)
W,H=1480,980;im=Image.new('RGB',(W,H),'#f3f6fa');d=ImageDraw.Draw(im)
d.text((45,26),'해체작업 붕괴 예방 흐름 — 산업안전보건법령과 건축물관리법',font=f(38),fill='#112b45')
steps=['① 사전조사','② 계획 수립','③ 작업 중 관리','④ 이상 시 조치']
lanes=[('산업안전보건법령\n(사업주 · 구축물등)','#1f5f8b',[
  '해체건물 등의 구조,\n주변 상황 등\n기록·보존\n(기준규칙 제38조, 별표 4)',
  '작업계획서 7개 항목\n근로자 주지\n작업지휘자 지정\n(제38조 ②, 제39조)',
  '무너뜨리기 전\n작업 반경 내 인원 확인\n관계자 외 출입금지\n(제384조 ①)',
  '해체계획서대로 불가·\n붕괴 우려 → 구조보강계획\n주요구조부 시공방법 변경\n→ 안전성 평가\n(제384조 ②, 제52조)']),
 ('건축물관리법\n(관리자 · 건축물)','#8a4b14',[
  '허가 원칙\n신고: 500㎡ 미만·\n12m 미만·3개 층 이하\n모두 충족\n(법 제30조 ①②)',
  '해체계획서 6개 항목\n건축사·기술사 작성\n건축위원회 심의\n(시행규칙 제12조,\n법 제30조)',
  '허가 대상: 감리자 확인\n필수확인점 사진·동영상\n일일 등록\n(법 제31·32조)',
  '시정·중지 요청\n불이행 시 허가권자 보고\n→ 작업중지 명령\n(법 제32조 ②③)'])]
x0,cw,gap=300,280,10;top=110
for i,s in enumerate(steps):
  x=x0+i*(cw+gap);d.rounded_rectangle((x,top,x+cw,top+60),12,fill='#112b45');d.text((x+cw/2,top+30),s,font=f(30),fill='white',anchor='mm')
  if i<3:d.polygon([(x+cw+1,top+18),(x+cw+gap+1,top+30),(x+cw+1,top+42)],fill='#112b45')
for li,(name,col,cells) in enumerate(lanes):
  y=200+li*380
  d.rounded_rectangle((30,y,270,y+350),16,fill=col);d.multiline_text((150,y+175),name,font=f(30),fill='white',anchor='mm',align='center',spacing=10)
  for i,t in enumerate(cells):
    x=x0+i*(cw+gap);d.rounded_rectangle((x,y,x+cw,y+350),14,fill='white',outline=col,width=4)
    d.multiline_text((x+cw/2,y+175),t,font=f(24),fill='#1d2733',anchor='mm',align='center',spacing=12)
d.text((W-30,H-22),'학습용 정리 · 2026. 11. 5. 국가법령정보센터 현행 조문 확인',font=f(20),fill='#5b6b7b',anchor='rs')
im.save(OUT/'해체작업_붕괴예방흐름.png',optimize=True);print('ok')
from PIL import ImageOps
bg=Image.open(ROOT/'channels/naver-blog-auto/assets/banner_bg/safety.png').convert('RGB')
bg=ImageOps.fit(bg,(1080,1080));ov=Image.new('RGBA',(1080,1080),(8,26,43,110));bg=Image.alpha_composite(bg.convert('RGBA'),ov);dr=ImageDraw.Draw(bg)
dr.rounded_rectangle((50,600,1030,1030),radius=25,fill=(8,26,43,235))
dr.text((90,642),'건설안전기술사 · 6일차',font=f(35),fill='#bde5f6')
dr.text((90,710),'철거·해체공사 붕괴 예방',font=f(68),fill='white')
dr.text((90,805),'사전조사와 작업계획서,',font=f(54),fill='white')
dr.text((90,880),'해체계획서까지',font=f(54),fill='white')
dr.text((70,45),'재난안전과 GeoAI',font=f(34),fill='white')
bg.convert('RGB').save(OUT/'banner.png');print('banner')
