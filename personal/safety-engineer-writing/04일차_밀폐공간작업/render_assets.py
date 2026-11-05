from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path('/Volumes/USB256/devAPP/AutoSNS');OUT=Path(__file__).resolve().parent
fp=str(ROOT/'assets/FONTS/Pretendard-Bold.otf');f=lambda n:ImageFont.truetype(fp,n)
# 1) 밀폐공간 작업 절차 흐름도(조문 번호 포함)
W,H=1480,900;im=Image.new('RGB',(W,H),'#f3f6fa');d=ImageDraw.Draw(im)
d.text((45,26),'밀폐공간 작업 절차 — 들어가기 전, 작업 중, 나온 뒤',font=f(38),fill='#112b45')
steps=[('① 밀폐공간 파악·출입금지 표지','제619조①1호 · 제622조'),('② 작업 전 확인 6항목·출입구 게시','제619조②·③'),('③ 위험성·비상연락처 주지, 숙지 확인','제641조'),
('④ 지정 측정자가 산소·유해가스 측정','제619조의2①'),('⑤ 적정공기 평가 → 부적합이면 환기 또는 공기호흡기·송기마스크','제619조의2③ · 제620조'),('⑥ 입장 인원 점검 · 감시인 외부 배치','제621조 · 제623조①③'),
('⑦ 작업 중 환기 유지 · 감시인 연락 유지','제620조 · 제623조①③'),('⑧ 이상 시 감시인이 소방관서 신고, 구출자는 공기호흡기·송기마스크','제623조② · 제643조'),('⑨ 퇴장 인원 점검 · 측정 기록 3년 보존','제621조 · 제619조의2④')]
bw,bh=430,150;gx,gy=45,105
for i,(t,r) in enumerate(steps):
  c,rw=i%3,i//3;x=gx+c*(bw+40);y=gy+rw*(bh+95)
  col='#ffe9d6' if i in(3,4) else ('#ffd9d9' if i==7 else '#dcebf7')
  d.rounded_rectangle((x,y,x+bw,y+bh),radius=18,fill=col,outline='#244a66',width=3)
  words=t;lines=[];cur=''
  for w in words.split(' '):
    nxt=(cur+' '+w).strip()
    if d.textlength(nxt,font=f(27))>bw-36: lines.append(cur);cur=w
    else: cur=nxt
  lines.append(cur)
  for k,l in enumerate(lines): d.text((x+18,y+16+k*36),l,font=f(27),fill='#102c46')
  d.text((x+18,y+bh-42),r,font=f(22),fill='#8a2c1d')
  if c<2: d.polygon([(x+bw+8,y+bh/2-14),(x+bw+32,y+bh/2),(x+bw+8,y+bh/2+14)],fill='#244a66')
  elif rw<2: d.line([(x+bw/2,y+bh+8),(x+bw/2,y+bh+40),(gx+bw/2,y+bh+40),(gx+bw/2,y+bh+87)],fill='#244a66',width=4);d.polygon([(gx+bw/2-12,y+bh+75),(gx+bw/2+12,y+bh+75),(gx+bw/2,y+bh+92)],fill='#244a66')
d.text((45,840),'근거: 산업안전보건기준에 관한 규칙 제3편 제10장(시행 2026. 3. 2.) · 2025. 12. 1. 개정(제454호) 반영 · 작업을 멈췄다 다시 시작할 때도 ④부터',font=f(21),fill='#4a5964')
im.save(OUT/'밀폐공간_작업절차.png')
# 2) 적정공기 기준 막대
W,H=1480,560;im=Image.new('RGB',(W,H),'#f3f6fa');d=ImageDraw.Draw(im)
d.text((45,26),'적정공기 기준(제618조제3호) — 네 가지를 모두 만족해야 적정공기예요',font=f(36),fill='#112b45')
x0,x1=300,1400;lo,hi=14.0,26.0;X=lambda v:x0+(v-lo)/(hi-lo)*(x1-x0);y=120
d.text((45,y+12),'산소(O₂)',font=f(30),fill='#102c46')
d.rectangle((X(lo),y,X(18),y+60),fill='#f2b8b0');d.rectangle((X(18),y,X(23.5),y+60),fill='#a9d8b8');d.rectangle((X(23.5),y,X(hi),y+60),fill='#f6d39a')
for v in (16,18,20,21,23.5,25):
  d.line([(X(v),y+60),(X(v),y+72)],fill='#244a66',width=3);d.text((X(v)-22,y+76),f'{v:g}%',font=f(22),fill='#173f5b')
d.text((X(14.3),y+14),'산소결핍(18% 미만)',font=f(24),fill='#7a1f14');d.text((X(18.4),y+14),'적정: 18% 이상 23.5% 미만',font=f(24),fill='#14532d');d.text((X(23.7),y+14),'23.5% 이상',font=f(22),fill='#7a4a00')
rows=[('이산화탄소(CO₂)','1.5% 미만 (= 15,000 ppm 미만)'),('일산화탄소(CO)','30 ppm 미만'),('황화수소(H₂S)','10 ppm 미만')]
for i,(a,b) in enumerate(rows):
  yy=260+i*70;d.text((45,yy+10),a,font=f(30),fill='#102c46');d.rounded_rectangle((X(lo),yy,x1,yy+56),radius=12,fill='#e3eef7',outline='#244a66',width=2);d.text((X(lo)+24,yy+12),b,font=f(28),fill='#173f5b')
d.text((45,490),'1% = 10,000 ppm. 산소 23.5% 이상도 적정공기가 아니에요. 별표 18 제14호는 같은 경계값으로 밀폐공간 장소를 정해요.',font=f(22),fill='#4a5964')
im.save(OUT/'적정공기_기준.png')
print('ok')
from PIL import ImageOps
bg=Image.open(ROOT/'channels/naver-blog-auto/assets/banner_bg/safety.png').convert('RGB')
bg=ImageOps.fit(bg,(1080,1080));ov=Image.new('RGBA',(1080,1080),(8,26,43,110));bg=Image.alpha_composite(bg.convert('RGBA'),ov);dr=ImageDraw.Draw(bg)
dr.rounded_rectangle((50,600,1030,1030),radius=25,fill=(8,26,43,235))
dr.text((90,642),'건설안전기술사 · 4일차',font=f(35),fill='#bde5f6')
dr.text((90,710),'밀폐공간 질식 예방',font=f(72),fill='white')
dr.text((90,805),'산소농도 영향과',font=f(54),fill='white')
dr.text((90,880),'작업 프로그램 안전절차',font=f(54),fill='white')
dr.text((70,45),'재난안전과 GeoAI',font=f(34),fill='white')
bg.convert('RGB').save(OUT/'banner.png')
print('banner')
