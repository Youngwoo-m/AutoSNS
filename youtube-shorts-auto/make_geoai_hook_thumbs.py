# coding: utf-8
"""이미 올린 geoai 숏츠에 질문형 썸네일(1080x1920)을 만든다. 글자는 KoPubWorld 돋움 Bold.
python make_geoai_hook_thumbs.py [영상ID ...]  — 생략하면 HOOKS 전체."""
import os,sys
from PIL import Image,ImageDraw,ImageFont
BASE=os.path.dirname(os.path.abspath(__file__))
FONT=os.path.join(os.path.dirname(BASE),'FONTS','KoPubWorld Dotum_Pro Bold.otf')
OUT=os.path.join(BASE,'assets','geoai_hook_thumbs')
def f(n): return ImageFont.truetype(FONT,n)
def wrap(d,t,font,w):
    lines,cur=[],''
    for word in t.split(' '):
        nxt=(cur+' '+word).strip()
        if d.textlength(nxt,font=font)<=w: cur=nxt
        else: lines.append(cur); cur=word
    return lines+[cur]
def card(hook,topic,path):
    im=Image.new('RGB',(1080,1920),'#13285a');d=ImageDraw.Draw(im)
    for y in range(1920):  # 위→아래 남색 그라데이션
        d.line([(0,y),(1080,y)],fill=(19+y//80,40+y//60,90+y//30))
    d.rectangle((0,0,18,1920),fill='#e63946')
    d.text((540,300),'재난안전과 GeoAI',font=f(64),fill='#ffd23f',anchor='mm')
    d.rectangle((370,350,710,358),fill='#e63946')
    big=f(118)
    # 쉼표가 있으면 쉼표 뒤에서 줄을 나눈다(의미 단위로 끊겨 읽기 쉽다)
    head,_,tail=hook.partition(', ')
    if tail and d.textlength(head+',',font=big)<=900 and d.textlength(tail,font=big)<=900: lines=[head+',',tail]
    else: lines=wrap(d,hook,big,900)
    y=960-len(lines)*150//2
    for ln in lines: d.text((540,y),ln,font=big,fill='white',anchor='mm');y+=150
    d.rounded_rectangle((140,y+40,940,y+150),radius=18,fill='#0b1a3a')
    d.text((540,y+95),topic,font=f(52),fill='#cfe0ff',anchor='mm')
    im.save(path,quality=92);return path
HOOKS={  # 영상ID: (질문, 아래 작은 주제)
 '4eHEpAZNjIc':('AI가 짠 공간분석 코드, 믿어도 될까?','생성형 AI 코드 확인 3가지'),
 'KUZadtepbZA':('오늘 저녁, 뭐 먹지?','메뉴 룰렛 앱 사용법'),
 'n7k5hK9nltU':('생성형 AI, 뭘 써야 할까?','글쓰기·검색·코드·이미지 비교'),
 'dxmRS2vxXLE':('디지털트윈, 지도와 뭐가 다를까?','GeoAI 기초'),
 'qYAnwYoLktA':('아이패드에 한글 폰트, 어떻게 넣지?','Noto Sans KR 무료 설치'),
 'G_l_1XV9kyA':('외국 논문, AI 번역 믿어도 될까?','오역 막는 방법'),
 'VkeBEAAmKfg':('엑셀 수식, 말로 시키면 될까?','AI에게 말로 시키는 법'),
 'UcRENUVgXeU':('우리 집 뒤 경사지, 위험할까?','주소 단위 경사지 위험 분석'),
 '8oXfiC9JcEU':('회의록, 아직 손으로 쓰세요?','AI로 할 일·메일까지 한번에'),
 '4ipvS7w2VyA':('사고는 왜 같은 곳에서 날까?','공간 자기상관·핫스팟 분석'),
 'EBC5fBer58c':('훈련 평가보고서, 언제 다 쓰지?','안전한국훈련 × 생성형 AI'),
 '9pFcFsur3YU':('비 측정 안 되는 곳, 강우량은?','공간 보간과 크리깅'),
 'PIds9wvb7BU':('산불, 위성으로 어떻게 볼까?','GeoAI 기초 14편'),
 'g5LGTk8EwIo':('AI가 재난을 관리하면?','도시안전 정책 변화'),
 '-Ey4Q2cH_VE':('산사태 위험지도, 어떻게 만들까?','GeoAI 기초 13편'),
 'Tpc_-KqMYWE':('훈련 실시계획서, AI가 써 줄까?','안전한국훈련 실무 2편'),
 'S764ihgMj0g':('분류·탐지·분할, 뭐가 다를까?','위성영상 딥러닝'),
 'j-GJeNkvbvw':('위성영상 분석, 내 PC 없이도?','구글 어스 엔진'),
 'DWrjAG7uuKA':('4326과 5186, 뭘 써야 할까?','좌표계 EPSG 차이'),
 'rngRZB3ZsNE':('위성 AI, 재난을 어떻게 바꿀까?','GeoAI 최신 동향'),
 'cYZ66YL4Rf4':('NDVI·NDWI·NBR, 뭘 보는 걸까?','위성 분광 지수 3분 정리'),
 'U607ztNM49k':('훈련 기본계획서, 빨리 쓰는 법은?','안전한국훈련 × 생성형 AI'),
 'zTE3Fyczjk0':('AI 답이 별로라면, 질문 탓?','프롬프트 4가지 요소'),
 'U6C5gYwElMA':('광학과 SAR, 뭐가 다를까?','위성영상 기초'),
 'Fmbhm7X8FLM':('GIS와 GeoAI, 뭐가 다를까?','규칙 기반 vs 학습 기반'),
}
if __name__=='__main__':
    os.makedirs(OUT,exist_ok=True)
    for vid in (sys.argv[1:] or HOOKS):
        h,t=HOOKS[vid];print(card(h,t,os.path.join(OUT,vid+'.jpg')))
