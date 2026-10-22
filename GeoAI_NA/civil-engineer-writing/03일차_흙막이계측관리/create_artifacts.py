from pathlib import Path
from io import BytesIO
import json, html
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter

OUT=Path(__file__).parent
BASE=Path('/Volumes/USB256/devAPP/AutoSNS/GeoAI_NA/civil-engineer-writing')
DAY=3
FIG='흙막이_계측기_배치_개념도.jpg'
PDF='03일차_흙막이계측관리_답안예시_따라쓰기.pdf'
TITLE='[토목시공기술사] 흙막이 공사의 계측관리 | 하루 한 문제 3일차'
QUESTION='흙막이 공사의 계측관리'
TAGS=['토목시공기술사','기초·흙막이','흙막이계측','지중경사계','정보화시공','기술사답안','하루한문제']
ALL=json.loads((BASE/'기출분석_2022-2026/전체465문항.json').read_text())
IDS=['127-3-4','129-2-1','132-3-2','137-1-6']
RELATED=[q for q in ALL if q['id'] in IDS]
SOURCES=[
('국가건설기준센터 KCS 11 10 15 시공 중 지반계측(표준시방서) — 현행판은 센터에서 확인','https://www.kcsc.re.kr'),
('국가건설기준센터 KDS 11 10 15 지반계측(설계기준) — 현행판은 센터에서 확인','https://www.kcsc.re.kr'),
('국가법령정보센터, 지하안전관리에 관한 특별법','https://www.law.go.kr/법령/지하안전관리에관한특별법'),
('TRB E-Circular EC-129(2008), Use of Inclinometers for Geotechnical Instrumentation on Transportation Projects','https://onlinepubs.trb.org/onlinepubs/circulars/ec129.pdf'),
]

FONT='/System/Library/Fonts/Supplemental/AppleGothic.ttf'
f=lambda s:ImageFont.truetype(FONT,s)
im=Image.new('RGB',(1600,1000),'#f7fafb');d=ImageDraw.Draw(im)
def it(x,y,s,size=28,color='#19394b'):d.text((x,y),s,font=f(size),fill=color)
it(70,40,'흙막이 계측: 벽체·지보재·배면지반·인접구조물·지하수를 함께 본다',38)
# ground and excavation
d.rectangle((70,260,1530,880),fill='#efe6d6')
d.rectangle((640,260,1000,740),fill='#f7fafb')  # excavated pit
d.line((640,740,1000,740),fill='#19394b',width=3)
d.rectangle((620,200,640,830),fill='#6b7f89');d.rectangle((1000,200,1020,830),fill='#6b7f89')  # walls
for y in (340,480,620): d.rectangle((640,y,1000,y+16),fill='#9aa9b0')  # struts
d.line((70,260,620,260),fill='#19394b',width=3);d.line((1020,260,1530,260),fill='#19394b',width=3)
it(700,690,'굴착 바닥',26);it(1030,790,'근입부',22,'#506875')
# adjacent building
d.rectangle((180,110,420,260),fill='#dbe3e8',outline='#19394b',width=3);it(230,170,'인접 건물',26)
# instruments
def pin(x,y,n):d.ellipse((x-20,y-20,x+20,y+20),fill='#176977');it(x-9,y-17,str(n),26,'white')
d.line((560,260,560,840),fill='#176977',width=6);pin(560,880-20,1)       # inclinometer behind wall
d.line((470,260,470,760),fill='#2f7fb0',width=4);pin(470,780,2)          # water level
pin(820,348,3)                                                         # strut load cell
pin(300,250,4)                                                         # settlement point
pin(420,140,5)                                                         # tiltmeter on building
pin(630,600,6)                                                         # wall strain
legend=['① 지중경사계: 벽체·배면 수평변위','② 지하수위계(간극수압계): 수위·수압','③ 하중계: 버팀보·앵커 축력','④ 지표침하계: 배면 침하','⑤ 건물경사계·균열계: 인접구조물','⑥ 변형률계: 벽체·띠장 응력']
for i,s in enumerate(legend): it(1080,300+i*62,s,25)
it(70,930,'직접 작성한 학습용 개념도 / 축척·실제 배치 간격 아님 / 배치·빈도·관리기준은 설계도서·계측계획서를 따른다',22,'#506875')
im.save(OUT/FIG,quality=95,subsampling=0)

past=''.join(f'<li>{q["year"]}년 제{q["round"]}회 {q["period"]}교시 {q["number"]}번({q["kind"]}): <a href="{html.escape(q["source"],quote=True)}">{html.escape(q["question"])}</a></li>' for q in RELATED)
sourcehtml=''.join(f'<li><a href="{html.escape(u,quote=True)}">{t}</a></li>' for t,u in SOURCES)
table='''<table border="1" style="border-collapse:collapse;width:100%"><thead><tr><th>계측 대상</th><th>항목</th><th>대표 계측기</th><th>판단 내용</th></tr></thead><tbody>
<tr><td>흙막이벽</td><td>깊이별 수평변위</td><td>지중경사계</td><td>최대 변위 깊이·굴착 단계별 증가</td></tr>
<tr><td>흙막이벽·띠장</td><td>응력</td><td>변형률계</td><td>부재 응력 수준과 설계값 비교</td></tr>
<tr><td>지보재</td><td>축력</td><td>하중계(버팀보·어스앵커)</td><td>축력 증가·감소, 프리로드 손실</td></tr>
<tr><td>배면지반</td><td>지표·지중 침하</td><td>지표침하계·층별침하계</td><td>침하 범위와 속도</td></tr>
<tr><td>지하수</td><td>수위·간극수압</td><td>지하수위계·간극수압계</td><td>수위 저하·유출, 토압 변화</td></tr>
<tr><td>인접구조물</td><td>기울기·균열·진동</td><td>건물경사계·균열계·진동측정기</td><td>허용 범위와 손상 진행</td></tr>
</tbody></table>'''
table2='''<table border="1" style="border-collapse:collapse;width:100%"><thead><tr><th>관찰된 조합</th><th>추정할 수 있는 원인</th><th>우선 확인</th></tr></thead><tbody>
<tr><td>경사계 변위 증가 + 지보재 축력 증가</td><td>배면 토압 증가 또는 지보 강성 부족</td><td>과굴착·지보 설치 지연·상재하중</td></tr>
<tr><td>경사계 변위 증가 + 축력 감소</td><td>지보재 이완·접합부 변형·앵커 정착 문제</td><td>잭·쐐기·띠장 접합부, 프리로드</td></tr>
<tr><td>지하수위 급저하 + 배면 침하</td><td>벽체 틈·바닥 부근 토사 유출</td><td>차수 상태·탁수 유출·굴착면 용수</td></tr>
</tbody></table>'''
body=f'''<p>흙막이 계측관리 답안은 계측기 이름을 늘어놓는 것보다 <strong>무엇을, 어디에, 언제 재고, 어떤 기준으로 판단해 조치하는지</strong>를 한 흐름으로 써야 한다. 계측은 설계 가정과 실제 거동을 비교하여 다음 굴착 단계를 결정하는 정보화시공의 근거이다.</p>
<h2><a href="https://geoai-na.netlify.app/civil-questions/">함께 푸는 [토목시공기술사] 답안지 요청</a></h2>
<p>문제를 요청하시면 접수 순서에 따라 매일 밤 11시에 요청을 확인하고, 정답예시와 따라쓰기 PDF를 작성해 블로그에 올립니다.</p>
<h2>오늘의 문제</h2>
<p><strong>시험 종목:</strong> 토목시공기술사 / <strong>과목(학습 분류):</strong> 기초·흙막이 / <strong>유형:</strong> 단답형 / <strong>관련 기출:</strong> 2025년 제137회 1교시 6번</p>
<blockquote>{QUESTION}</blockquote>
<p>위 문제는 <strong>2025년 제137회 1교시 6번 기출 원문</strong>이다. 답안예시는 학습용으로 작성한 것이며 공식 정답이나 채점기준이 아니다. 권장 연습은 목차 2분, 작성 8분, 답안지 약 1쪽 반이다. 학습 분류와 시간·분량은 연습을 위한 안내이다.</p>
<h3>출제 흐름과 이번 주제</h3>
<p>2022~2026년 제126~140회 465문항에서 흙막이·굴착 계측을 직접 묻거나 계측과 굴착 변위를 함께 다룬 문항을 다음 4건으로 분류했다. 단답형 1건과 논술형 3건이며, 같은 문제가 4회 반복되었다는 뜻은 아니다.</p><ul>{past}</ul>
<p>이 밖에 연약지반 성토 계측(제132회 1교시 3번, 제134회 1교시 3번)과 댐·교량 계측 문항도 있으나 대상 구조물이 달라 이번 묶음에서 뺐다. 기초·흙막이·연약지반 분야의 중복 허용 키워드 집계(64문항)는 분야 지표일 뿐이며 이번 세부 유형의 출제 횟수나 공식 출제 비중으로 쓰지 않았다.</p>
<h2>답안 목차</h2><p>1. 정의 → 2. 목적 → 3. 계측 항목과 기기 → 4. 배치·빈도 → 5. 관리기준과 조치 → 6. 자료 해석·유의사항</p>
<h2>답안예시</h2>
<h3>1. 정의</h3>
<p>흙막이 공사의 계측관리는 굴착에 따른 흙막이벽·지보재·배면지반·인접구조물·지하수의 거동을 측정하고, 이를 설계 예측값과 관리기준에 비교하여 시공의 안전성과 공법의 적정성을 판단하고 다음 단계 시공에 반영하는 관리이다.</p>
<h3>2. 목적</h3>
<p>첫째, 굴착 단계마다 흙막이 구조물의 안전을 확인하고 붕괴 징후를 조기에 찾는다. 둘째, 설계에서 가정한 토압·지반정수·지보 강성을 실제 거동으로 검증하여 굴착 순서나 보강을 조정한다(정보화시공). 셋째, 인접 건물·도로·지하매설물의 피해를 예방하고, 시공 전후 상태를 기록해 분쟁에 대비한다.</p>
<h3>3. 계측 항목과 계측기</h3>
{table}
<!--FIGURE:{FIG}-->
<figure><img src="{{{{FIGURE_URL}}}}" alt="흙막이 벽체 배면과 굴착부에 지중경사계·지하수위계·하중계·지표침하계·건물경사계·변형률계를 배치한 개념도" style="max-width:100%;height:auto"><figcaption>직접 작성한 개념도. 계측기 번호는 표의 항목과 대응한다. 축척과 실제 배치 간격을 나타내지 않는다.</figcaption></figure>
<h3>4. 배치와 측정 빈도</h3>
<p>계측기는 굴착이 가장 깊은 구간, 지반이 연약하거나 지하수위가 높은 구간, 인접구조물과 가까운 구간, 모서리처럼 거동이 다른 구간에 둔다. 경사계·하중계·수위계·침하계를 같은 단면에 묶어 배치하면 서로 다른 항목을 교차 확인할 수 있다. 굴착 전에 초기값을 확보하지 않으면 이후 변화량을 판단할 수 없으므로, 설치 후 안정된 초기값을 먼저 기록한다.</p>
<p>측정 빈도는 설계도서와 계측계획서에 따르되, 굴착 진행·지보재 설치와 해체·우기·이상 거동 시에는 빈도를 높인다. 굴착 완료 후 변위가 수렴하는 것을 확인하면서 단계적으로 줄인다. 이 글에서는 구체적인 측정 간격 수치를 제시하지 않는다. 적용 기준과 현장 계획서의 값으로 관리해야 하기 때문이다.</p>
<h3>5. 관리기준과 조치</h3>
<p>관리기준은 설계 해석값과 부재 허용값, 인접구조물 허용 변형을 바탕으로 설계도서에서 단계별(예: 주의·경고·위험)로 정한다. 기준값의 명칭과 수치는 공사마다 다르므로 답안에서는 단계 구분과 조치 흐름을 쓰는 것이 핵심이다.</p>
<p>1단계를 넘으면 재측정으로 오차를 배제하고 측정 빈도를 높이며 원인을 분석한다. 2단계에서는 관계자에게 보고하고 보강 방안(지보재 추가·프리로드 재도입·굴착 속도 조절 등)을 준비한다. 3단계에서는 굴착을 중지하고, 필요하면 되메움·지보 보강·그라우팅 등 응급 조치를 취한 뒤 재해석 결과에 따라 시공을 재개한다.</p>
<h3>6. 자료 해석과 유의사항</h3>
<p>계측값은 절대값과 함께 <strong>변화 속도와 경향</strong>을 본다. 기준 이하라도 증가 속도가 커지면 위험 신호로 판단한다. 모든 자료는 굴착 깊이·지보 설치 시점·강우 같은 공정 기록과 같은 시간축에 정리한다. 한 항목만으로 판단하지 말고 다음처럼 여러 항목을 함께 해석한다.</p>
{table2}
<p>계측기는 공사 중 손상되기 쉬우므로 보호 시설과 대체 측점을 준비하고, 측정자·장비·기준점이 바뀌면 그 사실을 기록한다. 최근에는 자동 계측과 실시간 경보를 결합한 스마트계측이 확대되고 있으며(제129회 2교시 1번), 이 경우에도 경보 후 확인·보고·조치 책임을 미리 정해 두어야 실제 관리로 이어진다.</p>
<h2>핵심 암기어</h2><p>정보화시공 · 초기값 · 대표 단면 묶음 배치 · 단계별 관리기준 · 변화 속도·교차 해석</p>
<h2>답안 자가점검</h2><ul><li>정의에 '측정 → 비교 → 판단 → 반영' 흐름이 들어갔는가?</li><li>벽체·지보재·배면지반·지하수·인접구조물 다섯 대상을 빠짐없이 썼는가?</li><li>계측기 배치 위치와 초기값 확보를 적었는가?</li><li>관리기준 단계별 조치를 구체적으로 썼는가?</li><li>근거 없는 기준 수치를 단정하지 않았는가?</li></ul>
<h2>따라쓰기 PDF</h2>
<!--PDF:{PDF}-->
<p><a href="{{{{PDF_URL}}}}">흙막이 계측관리 답안예시 따라쓰기 PDF 다운로드(2쪽)</a></p><p>Q-net 원본 답안지의 실제 작성면에 답안·표·도식을 옅은 회색(#B8B8B8)으로 배치했다. 인쇄된 서식은 유지했으며 본문 내용을 단답형 분량으로 압축했다.</p>
<h2>공식 참고자료</h2><ul>{sourcehtml}</ul><p>관련 기출 원문은 위 Q-net 링크에서 확인할 수 있다. 기준 확인일은 2026년 10월 19일이다. KCS 11 10 15·KDS 11 10 15는 현행 적용판의 조문을 이번 작성에서 직접 열람하지 못했으므로 기준 수치를 인용하지 않았다. 해외 자료는 계측 원리 참고용이며 국내 공사의 관리기준으로 전용하지 않는다.</p>
<p>{' '.join('#'+t.replace('·','') for t in TAGS)}</p>'''
# 티스토리: 자리표시는 발행기 네이티브 첨부, Blogger: 공개 https 주소
tis=body.replace(f'<!--FIGURE:{FIG}-->',f'<p data-ax-attach="{FIG}"></p>').replace(f'<!--PDF:{PDF}-->',f'<p data-ax-attach="{PDF}"></p>')
import re
tis=re.sub(r'<figure>.*?</figure>','<p style="font-size:14px;color:#52616a">직접 작성한 개념도. 계측기 번호는 표의 항목과 대응한다. 축척과 실제 배치 간격을 나타내지 않는다.</p>',tis,flags=re.S)
tis=re.sub(r'<p><a href="\{\{PDF_URL\}\}">[^<]*</a></p>','',tis)
(OUT/'티스토리게시본문.html').write_text(tis)
pub='https://geoai-na.netlify.app/civil-questions/materials/day03/'
blog=body.replace('{{FIGURE_URL}}',pub+'support-monitoring.jpg').replace('{{PDF_URL}}',pub+'answer-tracing.pdf')
blog=re.sub(r'<!--(FIGURE|PDF):[^>]*-->','',blog)
(OUT/'Blogger게시본문.html').write_text(blog)
preview=body.replace('{{FIGURE_URL}}',FIG).replace('{{PDF_URL}}',PDF)
(OUT/'블로그미리보기.html').write_text(f'<!doctype html><html lang="ko"><meta charset="utf-8"><title>{TITLE}</title><style>body{{max-width:900px;margin:40px auto;padding:0 24px;font:17px/1.85 AppleGothic,sans-serif;color:#24333d}}th,td{{padding:10px}}blockquote{{padding:18px;background:#edf4f5;border-left:4px solid #176977}}</style><h1>{TITLE}</h1>{preview}</html>')
(OUT/'제목.txt').write_text(TITLE+'\n');(OUT/'태그.txt').write_text(','.join(TAGS)+'\n')

pdfmetrics.registerFont(TTFont('KR',FONT))
SRC='/Volumes/USB256/기술사/2026기술사 답안지-1교시(안내용)_Qnet원본.pdf'
G=184/255
tpl=PdfReader(SRC);W,H=map(float,(tpl.pages[4].mediabox.width,tpl.pages[4].mediabox.height))
buf=BytesIO();c=canvas.Canvas(buf,pagesize=(W,H))
def tx(x,y,s,z=12):
    assert pdfmetrics.stringWidth(s,'KR',z)<405,(s,z)
    c.setFillColorRGB(G,G,G);c.setFont('KR',z);c.drawString(x,y,s)
def row(i,s,z=11.5):tx(202,764-i*32.35,s,z)
pages=[[
'흙막이 공사의 계측관리 [연습 1/2]',
'1. 정의',
'굴착에 따른 벽체·지보재·배면지반·인접구조물·지하수',
'거동을 측정하여 설계 예측값·관리기준과 비교하고',
'안전성·공법 적정성을 판단해 다음 시공에 반영하는 관리',
'2. 목적',
'① 단계별 안전 확인·붕괴 징후 조기 발견',
'② 설계 가정 검증 → 굴착순서·보강 조정(정보화시공)',
'③ 인접구조물 피해 예방, 시공 전후 기록으로 분쟁 대비',
'3. 계측 항목과 계측기',
None,None,None,None,None,None,None,
'※ 대상 5가지를 같은 대표 단면에 묶어 교차 확인',
'4. 배치·빈도',
'최대 굴착·연약·고수위·인접구조물 근접·모서리 구간',
'굴착 전 초기값 확보 / 굴착·지보 설치·해체·우기 시 증가',
],[
'흙막이 공사의 계측관리 [연습 2/2]',
'5. 관리기준과 조치 (기준값은 설계도서·계획서)',
None,None,None,None,None,
'1단계: 재측정·빈도 증가·원인 분석',
'2단계: 보고·보강안 준비(지보 추가·프리로드·속도 조절)',
'3단계: 굴착 중지·응급 조치(되메움·보강·그라우팅)',
'6. 자료 해석·유의사항',
'① 절대값 + 변화 속도·경향 → 증가 속도 증가 시 경계',
'② 굴착 깊이·지보 시점·강우와 같은 시간축 정리',
'③ 교차 해석: 변위↑+축력↑ → 토압 증가·지보 부족',
'    변위↑+축력↓ → 지보 이완 / 수위↓+침하 → 토사 유출',
'④ 계측기 보호·대체 측점, 측정자·장비 변경 기록',
'⑤ 스마트계측: 자동 경보 + 확인·보고·조치 책임 지정',
'7. 결론',
'계측은 측정이 아니라 판단·조치까지 이어질 때 의미가 있다.',
'학습용 답안 예시 / 공식 정답·채점기준 아님',
'참고: KCS 11 10 15, KDS 11 10 15, TRB E-C129',
]]
for n,rr in enumerate(pages):
    for i,s in enumerate(rr):
        if s:row(i,s,13 if i==0 else 11.5)
    tx(132,731,'1',13)
    c.setStrokeColorRGB(G,G,G);c.setLineWidth(1)
    if n==0:
        xs=[202,300,420,605];top=764-9*32.35-10;rh=32.35
        rows=[('대상','항목','계측기'),('흙막이벽','수평변위·응력','지중경사계·변형률계'),('지보재','축력','하중계'),('배면지반','지표·지중침하','침하계·층별침하계'),('지하수','수위·간극수압','수위계·간극수압계'),('인접구조물','기울기·균열','경사계·균열계')]
        ys=[top-k*rh for k in range(len(rows)+1)]
        for x in xs:c.line(x,ys[-1],x,ys[0])
        for y in ys:c.line(xs[0],y,xs[-1],y)
        for j,vs in enumerate(rows):
            for k,s in enumerate(vs):tx(xs[k]+5,ys[j]-21,s,10.5)
    if n==1:
        y0=764-2*32.35+10
        for k,(lab,x) in enumerate([('측정',210),('비교',300),('판단',390),('조치',480),('반영',555)]):
            c.rect(x,y0-50,62 if k<4 else 48,26);tx(x+10,y0-41,lab,11)
            if k<4:
                xe=x+(62)+(300-210-62)-2 if k<3 else 553
                c.line(x+62,y0-37,xe,y0-37)
        tx(210,764-4*32.35,'관리기준 단계: 1단계(주의) → 2단계(경고) → 3단계(위험)',10.5)
        tx(210,764-5*32.35,'명칭·수치는 공사별 설계도서·계측계획서에서 정한다',10.5)
    c.showPage()
c.save();buf.seek(0);ov=PdfReader(buf);wr=PdfWriter()
for p in ov.pages:
    page=PdfReader(SRC).pages[4];page.merge_page(p);wr.add_page(page)
wr.add_metadata({'/Title':TITLE+' - 따라쓰기','/Subject':'학습용 답안예시(제137회 1교시 6번 기출 원문). Q-net 원본 작성면 보존. 작성 글씨·표·도식 #B8B8B8.'})
with (OUT/PDF).open('wb') as fo:wr.write(fo)
print(json.dumps({'pages':len(wr.pages),'title':TITLE,'related':IDS},ensure_ascii=False))
