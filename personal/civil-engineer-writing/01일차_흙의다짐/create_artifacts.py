from pathlib import Path
from io import BytesIO
from copy import deepcopy
import json, html
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter

OUT = Path(__file__).parent
TEMPLATE = Path('/Volumes/USB256/기술사/2026기술사 답안지-1교시(안내용)_Qnet원본.pdf')
TITLE = '[토목시공기술사] 흙의 다짐·최적함수비·다짐도 | 하루 한 문제 1일차'
QUESTION = '흙의 다짐과 최적함수비를 설명하고, 다짐도 산정 방법 및 현장 품질관리 요점을 기술하시오.'
SOURCES = [
 ('FHWA NHI-05-037, 5.3.2 Compaction: 다짐곡선·건조단위중량·다짐도', 'https://www.fhwa.dot.gov/engineering/geotech/pubs/05037/05a.cfm'),
 ('국가건설기준센터 KCS 11 20 20 쌓기: 적용판·시험방법·현장 관리기준 확인', 'https://www.kcsc.re.kr/standardCode/viewer/KCS%2011%2020%2020%3A2025-12-24'),
]
pdfmetrics.registerFont(TTFont('KR', '/System/Library/Fonts/Supplemental/AppleGothic.ttf'))
W, H = float(PdfReader(TEMPLATE).pages[4].mediabox.width), float(PdfReader(TEMPLATE).pages[4].mediabox.height)
GRAY = 184/255

def text(c, x, y, s, size=12.5, gray=True):
    c.setFillColorRGB(*((GRAY,)*3 if gray else (.12,)*3))
    c.setFont('KR', size)
    c.drawString(x, y, s)

def line(c, row, s, size=12.5):
    assert pdfmetrics.stringWidth(s, 'KR', size) < 405, s
    text(c, 202, 764-row*32.35, s, size)

def curve(c, x, y, w, h, gray=True):
    color = (GRAY,)*3 if gray else (.12,)*3
    c.setStrokeColorRGB(*color); c.setLineWidth(1.1)
    c.line(x+28,y+24,x+w-8,y+24); c.line(x+28,y+24,x+28,y+h-10)
    p=c.beginPath(); p.moveTo(x+48,y+40)
    p.curveTo(x+95,y+88,x+140,y+h-5,x+180,y+h-40)
    p.curveTo(x+210,y+h-55,x+240,y+55,x+w-20,y+41)
    c.drawPath(p)
    # The curve is a qualitative sketch, not measured test results.
    c.setDash(3,3); c.line(x+155,y+24,x+155,y+h-29); c.setDash()
    text(c,x+3,y+h-5,'건조밀도',10,gray)
    text(c,x+120,y+6,'최적함수비',10,gray)
    text(c,x+w-75,y+6,'함수비 →',10,gray)
    text(c,x+172,y+h-21,'최대건조밀도',10,gray)
    text(c,x+36,y+52,'건조측',10,gray); text(c,x+239,y+52,'습윤측',10,gray)

buf=BytesIO(); c=canvas.Canvas(buf,pagesize=(W,H))
rows={
0:('흙의 다짐·최적함수비·다짐도',13),
1:('Ⅰ. 다짐의 정의 및 목적',14),
2:('기계적 에너지로 공극의 공기를 줄여 흙을 치밀화한다.',12),
3:('지지력 확보와 침하 억제를 목적으로 한다.',12.5),
4:('Ⅱ. 최적함수비와 최대건조밀도',14),
5:('정해진 다짐에너지에서 건조밀도가 최대가 되는',12.5),
6:('함수비를 최적함수비라 한다. 흙·시험방법에 따라 변한다.',12),
12:('위 그림은 전형적인 개념도이며 실측값·축척은 없다.',11),
13:('Ⅲ. 다짐도 산정',14),
14:('ρd = ρ / (1 + w)',14),
15:('ρd: 건조밀도, ρ: 습윤밀도 [같은 단위, Mg/m³]',12),
16:('w: 물의 질량 / 건조토 질량 [소수, 12% → 0.12]',12),
17:('다짐도 Rc = (현장 ρd / 실내 ρd,max) × 100 [%]',12.5),
18:('가상 예: ρ=2.016 Mg/m³, w=0.12이면 ρd=1.800',12),
19:('실내 ρd,max=1.900 Mg/m³이면 Rc=94.7%',12.5),
20:('합격 여부는 해당 부위·재료·시방기준으로 판단한다.',12),
}
for r,(s,z) in rows.items(): line(c,r,s,z)
text(c,132,731,'1',14)
curve(c,208,385,385,145)
c.showPage()
rows={
0:('현장 품질관리와 답안 작성 유의사항',13),
1:('Ⅳ. 현장 품질관리',14),
2:('① 재료: 토질·입도·함수비와 부적합재료 확인',12.5),
3:('② 시험: 재료별 실내 다짐곡선·기준 건조밀도 확보',12),
4:('③ 시험시공: 장비·층두께·속도·횟수 등 결정',12.5),
5:('④ 시공: 함수비 조절, 균일 포설·다짐, 배수 관리',12),
6:('⑤ 검사: 함수비와 현장밀도 측정 후 다짐도 평가',12),
7:('⑥ 미달: 원인 확인 → 보완·재다짐 → 재시험',12.5),
8:('Ⅴ. 혼동하기 쉬운 개념',14),
14:('Ⅵ. 실무 유의사항 및 결론',14),
15:('· 기준 실내시험과 현장 재료의 대응성을 확인한다.',12),
16:('· 다짐도만으로 지지력·침하 성능을 단정하지 않는다.',12),
17:('· 요구 다짐도·함수비 범위·시험빈도는 적용기준 확인',11.5),
18:('재료·함수비·장비·층두께를 함께 관리하고 검증한다.',12),
19:('학습용 창작 연습문제·답안 예시 / 공식 채점기준 아님',11),
20:('참고: FHWA NHI-05-037, KCS 11 20 20 (본문 링크)',10.5),
}
for r,(s,z) in rows.items(): line(c,r,s,z)
text(c,132,731,'1',14)
# Small comparison table placed between the existing template's rules.
xs=[202,310,605]; ys=[485,453,421,389,357,325]
c.setStrokeColorRGB(GRAY,GRAY,GRAY)
for x in xs: c.line(x,ys[-1],x,ys[0])
for y in ys: c.line(xs[0],y,xs[-1],y)
table=[('구분','핵심 의미'),('다짐','기계적 에너지로 주로 공기 배출'),('압밀','하중으로 간극수 배출·시간 의존'),('다짐도','현장 건조밀도 / 실내 최대건조밀도'),('상대밀도','최대·최소 간극비로 조밀함 평가')]
for i,(a,b) in enumerate(table):
    text(c,208,ys[i]-21,a,11.5); text(c,316,ys[i]-21,b,10.5)
c.save(); buf.seek(0)
overlay=PdfReader(buf); writer=PdfWriter()
for i in range(2):
    p=deepcopy(PdfReader(TEMPLATE).pages[4]); p.merge_page(overlay.pages[i])
    if i:
        b=BytesIO(); cc=canvas.Canvas(b,pagesize=(W,H)); cc.setFillColorRGB(1,1,1)
        cc.rect(574,791,45,45,stroke=0,fill=1); text(cc,587,803,'2쪽',13,False)
        cc.save(); b.seek(0); p.merge_page(PdfReader(b).pages[0])
    writer.add_page(p)
writer.add_metadata({'/Title':TITLE+' - 따라쓰기', '/Subject':'창작 연습문제. 공식 채점기준 아님. 작성 글씨 RGB 184/184/184.'})
with (OUT/'01일차_흙의다짐_답안예시_따라쓰기.pdf').open('wb') as f: writer.write(f)

# Blog diagram is code-native SVG and does not require image generation.
svg='''<svg xmlns="http://www.w3.org/2000/svg" width="900" height="400" viewBox="0 0 900 400" role="img" aria-label="전형적인 함수비-건조밀도 개념도">
<rect width="900" height="400" fill="white"/><g stroke="#263746" stroke-width="3" fill="none"><path d="M100 320H840M100 320V45"/><path d="M150 280C290 100 400 55 480 110S650 260 800 280" stroke="#176977" stroke-width="5"/><path d="M442 320V97" stroke-dasharray="8 8"/></g><g font-family="AppleGothic,sans-serif" fill="#263746" font-size="24"><text x="25" y="30">건조밀도</text><text x="720" y="363">함수비 →</text><text x="370" y="355">최적함수비</text><text x="480" y="77">최대건조밀도</text><text x="190" y="255">건조측</text><text x="650" y="255">습윤측</text><text x="100" y="395" font-size="20">일정한 흙·다짐에너지에서의 전형적 개념도 / 실측 데이터·축척 없음</text></g></svg>'''
(OUT/'다짐곡선_개념도.svg').write_text(svg)
im=Image.new('RGB',(1800,800),'white'); draw=ImageDraw.Draw(im)
def xy(p): return tuple(int(v*2) for v in p)
def path(points, color, width=3): draw.line([xy(p) for p in points],fill=color,width=width*2)
path([(100,45),(100,320),(840,320)],'#263746')
pts=[]
for p0,p1,p2,p3 in [((150,280),(290,100),(400,55),(480,110)),((480,110),(560,165),(650,260),(800,280))]:
    for i in range(101):
        t=i/100; u=1-t
        pts.append(tuple(u**3*p0[j]+3*u*u*t*p1[j]+3*u*t*t*p2[j]+t**3*p3[j] for j in range(2)))
path(pts,'#176977',5)
peak=min(pts,key=lambda p:p[1]); px,py=peak
for y in range(int(py),320,16): path([(px,y),(px,min(y+8,320))],'#687681',2)
fontpath='/System/Library/Fonts/Supplemental/AppleGothic.ttf'
for x,y,s,size in [(25,8,'건조밀도',24),(720,337,'함수비 →',24),(px-66,337,'최적함수비',24),(px+25,py-38,'최대건조밀도',24),(190,230,'건조측',24),(650,195,'습윤측',24),(100,374,'일정한 흙·다짐에너지에서의 전형적 개념도 / 실측 데이터·축척 없음',19)]:
    draw.text(xy((x,y)),s,font=ImageFont.truetype(fontpath,size*2),fill='#263746')
im.save(OUT/'다짐곡선_개념도.png')
blogfigure='<img src="다짐곡선_개념도.png" alt="함수비와 건조밀도의 전형적 다짐곡선" style="max-width:100%;height:auto">'
sources_html=''.join(f'<li><a href="{u}">{t}</a></li>' for t,u in SOURCES)
body=f'''<p>이 글은 흙의 다짐·최적함수비·다짐도를 토목시공기술사 단답형 답안 예시로 정리했습니다. 개념도와 계산 예로 핵심을 확인하고, 현장 품질관리 절차까지 연결합니다.</p>
<h2>오늘의 문제</h2><p><strong>학습용 분야:</strong> 토공·다짐 / 1순환 / 1일차</p>
<blockquote>{QUESTION}</blockquote>
<p>창작 연습문제 · 단답형 연습. 권장: 목차 1분 + 작성 9분, 답안지 약 2쪽. 시간·분량은 학습용 권장치입니다. 아래 답안은 공식 정답이나 채점기준이 아닙니다.</p>
<h2>답안 목차</h2><p>Ⅰ. 정의·목적 → Ⅱ. 최적함수비 → Ⅲ. 다짐도 산정 → Ⅳ. 현장 관리 → Ⅴ. 개념 비교·결론</p>
<h2>답안 예시</h2><h3>Ⅰ. 다짐의 정의와 목적</h3>
<p>다짐은 기계적 에너지를 가하여 흙의 공극에 있는 공기를 줄이고 흙을 치밀하게 하는 작업이다. 지지력 확보와 침하 억제를 목적으로 한다.</p>
<h3>Ⅱ. 최적함수비와 최대건조밀도</h3>
<p>정해진 다짐에너지에서 건조밀도가 최대가 되는 함수비를 최적함수비라 한다. 그때의 값이 최대건조밀도이다. 이는 흙의 종류와 시험방법에 따라 달라진다. 전형적인 다짐곡선의 꼭짓점에서 두 값을 읽는다.</p>
<figure>{svg}<figcaption>직접 작성한 개념도. 실측 데이터가 아니며 모든 흙이 같은 곡선 모양을 갖는 것은 아니다.</figcaption></figure>
<h3>Ⅲ. 다짐도 산정</h3>
<p><strong>ρd = ρ / (1 + w)</strong><br>ρd: 건조밀도, ρ: 습윤밀도(동일한 밀도 단위 사용). w는 물의 질량을 건조토 질량으로 나눈 값이며, 식에는 12%를 0.12로 입력한다.</p>
<p><strong>다짐도 Rc(%) = 현장 건조밀도 / 실내 최대건조밀도 × 100</strong></p>
<p>학습용 가상 예: ρ=2.016 Mg/m³, w=0.12이면 ρd=1.800 Mg/m³이다. 같은 재료의 지정 실내시험에서 최대건조밀도가 1.900 Mg/m³였다면 Rc=1.800/1.900×100=94.7%이다. 이 값만으로 합격이라고 판정하지 않고 해당 부위·재료의 시방기준과 비교한다.</p>
<h3>Ⅳ. 현장 품질관리</h3>
<ol><li><strong>재료:</strong> 토질·입도·함수비·부적합재료를 확인한다.</li><li><strong>시험:</strong> 재료별 실내 다짐곡선과 기준 건조밀도를 확보한다.</li><li><strong>시험시공:</strong> 장비, 층두께, 주행속도 및 다짐횟수 등 시공조건을 정한다.</li><li><strong>시공:</strong> 함수비 조절, 균일한 포설·다짐과 배수를 관리한다.</li><li><strong>검사:</strong> 현장밀도와 함수비를 측정하여 적용 시험방법·시방기준으로 평가한다.</li><li><strong>미달 조치:</strong> 원인 확인 → 보완·재다짐 → 재시험으로 연결한다.</li></ol>
<p>국내 기준 적용 시 KCS 11 20 20과 공사시방서에서 해당 부위의 시험방법·요구 다짐도·함수비 범위·시험빈도를 확인한다. 이 글은 모든 현장에 적용되는 단일 합격 수치를 제시하지 않는다.</p>
<h3>Ⅴ. 개념 비교와 결론</h3>
<table border="1" style="border-collapse:collapse;width:100%"><thead><tr><th>개념</th><th>구분 요점</th></tr></thead><tbody><tr><td>다짐</td><td>기계적 에너지로 주로 공기 배출</td></tr><tr><td>압밀</td><td>하중에 의한 간극수 배출과 시간 의존 변형</td></tr><tr><td>다짐도</td><td>현장 건조밀도와 지정 실내시험 최대건조밀도의 비</td></tr><tr><td>상대밀도</td><td>최대·최소 간극비를 기준으로 조밀함 평가</td></tr></tbody></table>
<p>따라서 다짐은 재료·함수비·장비·층두께를 함께 관리하고 시험으로 확인한다. 다짐도와 상대밀도를 혼동하거나 다짐도만으로 지지력·침하 성능을 단정하지 않는다.</p>
<h2>핵심 암기어</h2><p>함수비 · 최대건조밀도 · 다짐도 · 시험시공 · 재시험</p>
<h2>답안 자가점검</h2><ul><li>다짐과 압밀을 구분했는가?</li><li>다짐에너지와 최적함수비의 조건을 적었는가?</li><li>함수비를 소수로 바꾸고 밀도 단위를 통일했는가?</li><li>현장과 실내 기준 재료의 대응성을 확인했는가?</li><li>품질관리와 기준 미달 시 조치까지 썼는가?</li></ul>
<h2>따라쓰기 PDF</h2><p>함께 제공한 2쪽 PDF는 기존 Q-net 원본 답안지 작성면을 사용했습니다. 작성 글씨·도식·표를 #B8B8B8 회색으로 만들어 출력 후 따라 쓸 수 있습니다. 게시할 때 티스토리 파일 첨부 메뉴로 PDF를 올리고 공개 글에서 다운로드를 확인합니다.</p>
<h2>공식 참고자료</h2><ul>{sources_html}</ul>
<p>확인일: 2026-10-17. FHWA는 기본 원리 참고용이며 해외 기준 수치를 국내 합격기준으로 전용하지 않습니다. KCSC 본문은 동적 뷰어이므로 적용판·세부 조항은 발행 시 원문에서 재확인합니다.</p>
<p>#토목시공기술사 #토공 #흙의다짐 #최적함수비 #다짐도 #기술사답안 #하루한문제</p>'''
body=body.replace(svg,blogfigure)
(OUT/'게시본문.html').write_text(body)
doc=f'<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{TITLE}</title><style>body{{max-width:860px;margin:40px auto;padding:0 20px;font:17px/1.85 AppleGothic,sans-serif;color:#24333d}}h1{{font-size:30px}}h2{{margin-top:40px;color:#176977}}th,td{{padding:10px}}svg{{width:100%;height:auto}}blockquote{{border-left:4px solid #176977;margin:20px 0;padding:16px;background:#f3f7f8}}a{{color:#176977}}</style><h1>{TITLE}</h1>{body}</html>'
(OUT/'블로그미리보기.html').write_text(doc)
(OUT/'제목.txt').write_text(TITLE+'\n')
status={'종목':'토목시공기술사','일차':1,'문제구분':'창작 연습문제','상태':'로컬 초안 및 따라쓰기 PDF 준비 / 공개 발행 전','자동화':'일정 사용자 응답 대기','model_policy':{'초안편집':'gpt-6.1-sol / medium 권장','어려운문제검토':'Astra 실제 사용 가능 시 검토, 사용 증빙 기록','이번실제모델':'실행 런타임의 모델 ID와 추론 수준을 확인할 수 없어 미기록','Astra검토':'실시하지 않음; 기본 정의와 산술 예제, 기준 수치는 단정하지 않음'},'검산':{'건조밀도':2.016/1.12,'다짐도':1.8/1.9*100},'출처':SOURCES,'PDF페이지수':2,'시각검토':'렌더링 후 기록','저장위치이유':'기존 /Volumes/USB256/기술사 는 현재 쓰기 허용 범위 밖이므로 작업공간에 보존'}
(OUT/'작성상태.json').write_text(json.dumps(status,ensure_ascii=False,indent=2))
print(json.dumps({'output':str(OUT),'pages':2,'calculation':[2.016/1.12,1.8/1.9*100]},ensure_ascii=False))
