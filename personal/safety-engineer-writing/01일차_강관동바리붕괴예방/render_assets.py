from pathlib import Path
import sys
ROOT=Path('/Volumes/USB256/devAPP/AutoSNS');OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'dept/naver-blog-auto'))
import make_banner as m
m.POSTS_DIR=str(OUT)
m.load_config=lambda:{'blog':{'banner_dept':'재난안전과 GeoAI','banner_shape':'square'}}
m.make_banner('거푸집·강관 동바리 타설 전 확인사항','2026년 10월 31일',badge='건설안전기술사 · 1일차',shape='square',bg=str(ROOT/'dept/naver-blog-auto/assets/banner_bg/safety.png'))
from PIL import Image,ImageDraw,ImageFont
im=Image.new('RGB',(1200,650),'#f3f6fa');draw=ImageDraw.Draw(im)
fontpath=str(ROOT/'assets/FONTS/Pretendard-Bold.otf')
f=lambda n:ImageFont.truetype(fontpath,n)
draw.text((50,35),'강관 동바리 안전관리: 확인 → 조치 → 기록',font=f(38),fill='#112b45')
blocks=[('사전검토','하중·지반·부재 검토\n구조검토 → 조립도'),('조립 확인','침하·이탈·편심 방지\n유형별 연결·가새 확인'),('타설 감시','작업 전 이상 보수\n이상 시 중지·대피'),('해체 검토','양생·지지상태 확인\n계획에 따른 순서 관리')]
for i,(a,b) in enumerate(blocks):
 x=50+i*280;draw.rounded_rectangle((x,150,x+255,360),radius=18,fill='#dce9f5',outline='#42667f',width=3)
 draw.text((x+22,175),a,font=f(29),fill='#102c46');draw.multiline_text((x+18,240),b,font=f(22),fill='#213e52',spacing=13)
 if i<3:
  draw.line((x+258,250,x+277,250),fill='#285a7e',width=3);draw.polygon([(x+277,250),(x+269,244),(x+269,256)],fill='#285a7e')
draw.rounded_rectangle((80,425,1120,550),radius=12,fill='#fff4d9',outline='#bb9242',width=2)
draw.text((110,448),'법령 수치만 외우지 말고, 구조검토·조립도와 현장 상태를 함께 확인',font=f(27),fill='#4c3c17')
draw.text((110,495),'직접 작성한 학습용 순서도 · 실제 구조설계·작업계획을 대신하지 않음',font=f(22),fill='#4c3c17')
draw.text((55,597),'근거: 산업안전보건기준에 관한 규칙 제331조·제332조·제332조의2·제333조·제334조',font=f(20),fill='#4a5964')
im.save(OUT/'동바리_단계별확인.png')
print('assets rendered',OUT)
