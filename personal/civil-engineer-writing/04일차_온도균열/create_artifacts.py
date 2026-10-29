from pathlib import Path
from io import BytesIO
import json, html, re
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter

OUT=Path(__file__).parent
BASE=Path('/Volumes/USB256/devAPP/AutoSNS/GeoAI_NA/civil-engineer-writing')
DAY=4
FIG='온도균열_구속_개념도.jpg'
PDF='04일차_온도균열_답안예시_따라쓰기.pdf'
TITLE='[토목시공기술사] 콘크리트 구조물의 온도균열 원인과 제어 | 하루 한 문제 4일차'
QUESTION='콘크리트 구조물의 온도균열 발생원인과 제어방법에 대하여 설명하시오.'
TAGS=['토목시공기술사','콘크리트','매스콘크리트','온도균열','온도균열지수','수화열','기술사답안','하루한문제']
ALL=json.loads((BASE/'기출분석_2022-2026/전체465문항.json').read_text())
IDS=['130-2-4','133-1-9','134-2-2']
RELATED=[q for q in ALL if q['id'] in IDS]
SOURCES=[
('국가건설기준센터 누리집(첫 화면) — KCS 14 20 42 매스콘크리트(표준시방서) 현행판은 센터에서 검색해 확인','https://www.kcsc.re.kr'),
('이인규·김광돈·김태욱·이준석(2010), 부상식 매스콘크리트 기초의 수화열 관리 및 온도균열 제어, 한국구조물진단유지관리공학회지 14(1)','https://www.koreascience.kr/article/JAKO201034060625707.page'),
('TRB Webinar(2018), Construction of Mass Concrete Transportation Infrastructure','https://onlinepubs.trb.org/onlinepubs/webinars/180806.pdf'),
]

FONT='/System/Library/Fonts/Supplemental/AppleGothic.ttf'
f=lambda s:ImageFont.truetype(FONT,s)
im=Image.new('RGB',(1600,1000),'#f7fafb');d=ImageDraw.Draw(im)
def it(x,y,s,size=28,color='#19394b'):d.text((x,y),s,font=f(size),fill=color)
it(70,40,'온도균열: 내부구속(초기·표면균열)과 외부구속(냉각기·관통균열)',38)
# left: internal restraint section
it(90,120,'① 내부구속 — 온도 상승기',30,'#176977')
d.rectangle((110,190,690,560),fill='#d9e2e6',outline='#19394b',width=3)
d.rectangle((260,290,540,460),fill='#f2b8a0')
it(330,355,'심부 고온·팽창',26)
for x0,y0,x1,y1 in [(110,190,690,230),(110,520,690,560)]: d.rectangle((x0,y0,x1,y1),fill='#c3d4dc')
it(130,196,'표면: 빨리 식어 덜 팽창 → 인장',22)
for x in (500,580,650):d.line((x,190,x+8,250),fill='#b5452e',width=4)
it(110,580,'심부와 표면의 온도차 ΔTi 가 클수록 표면 인장응력↑',24)
it(110,620,'균열은 주로 표면부, 비교적 얕다',24,'#506875')
# right: external restraint
it(860,120,'② 외부구속 — 온도 강하기',30,'#176977')
d.rectangle((880,300,1500,460),fill='#d9e2e6',outline='#19394b',width=3)
it(960,250,'새로 친 벽체·슬래브: 냉각되며 수축',26)
d.rectangle((860,460,1520,560),fill='#c9b99a');it(1010,490,'기존 콘크리트·암반(구속체)',26)
for x in (1050,1190,1330):d.line((x,300,x,460),fill='#b5452e',width=5)
d.line((900,380,960,380),fill='#19394b',width=3);d.polygon([(960,372),(960,388),(975,380)],fill='#19394b')
d.line((1420,380,1480,380),fill='#19394b',width=3);d.polygon([(1420,372),(1420,388),(1405,380)],fill='#19394b')
it(880,580,'평균온도가 떨어지며 수축할 때 아래가 붙잡음',24)
it(880,620,'벽 높이 방향 관통균열 → 누수·내구성 저하',24,'#506875')
# bottom: temperature history
d.line((150,900,1450,900),fill='#19394b',width=3);d.line((150,700,150,900),fill='#19394b',width=3)
it(160,690,'온도',22);it(1380,910,'재령',22)
pts=[(150+i*13,900-120*(1-(1-min(i/18,1))**2)*(1 if i<18 else max(0.15,1-(i-18)/70))) for i in range(100)]
d.line(pts,fill='#b5452e',width=4)
it(330,720,'상승: 내부구속 위험',22,'#b5452e');it(760,800,'강하: 외부구속 위험',22,'#b5452e')
it(70,950,'직접 작성한 학습용 개념도 / 축척·실제 온도값 아님 / 균열 위치와 형태는 부재 조건에 따라 다르다',22,'#506875')
im.save(OUT/FIG,quality=95,subsampling=0)

past=''.join(f'<li>{q["year"]}년 제{q["round"]}회 {q["period"]}교시 {q["number"]}번({q["kind"]}): <a href="{html.escape(q["source"],quote=True)}">{html.escape(q["question"])}</a></li>' for q in RELATED)
sourcehtml=''.join(f'<li><a href="{html.escape(u,quote=True)}">{t}</a></li>' for t,u in SOURCES)
table1='''<table border="1" style="border-collapse:collapse;width:100%"><thead><tr><th>구분</th><th>내부구속 균열</th><th>외부구속 균열</th></tr></thead><tbody>
<tr><td>발생 시기</td><td>온도 상승기(타설 후 초기)</td><td>최고온도 이후 온도 강하기</td></tr>
<tr><td>원인</td><td>심부와 표면의 온도차</td><td>부재 전체 수축을 기존 콘크리트·지반이 구속</td></tr>
<tr><td>대표 부재</td><td>두꺼운 기초·매트</td><td>기초 위 벽체, 이어 친 슬래브</td></tr>
<tr><td>균열 형태</td><td>표면 위주, 비교적 얕음</td><td>일정 간격 관통균열 가능</td></tr>
<tr><td>관리 대상</td><td>내외부 온도차</td><td>최고온도·강하량·구속도·이음 간격</td></tr>
</tbody></table>'''
table2='''<table border="1" style="border-collapse:collapse;width:100%"><thead><tr><th>온도균열지수 I<sub>cr</sub></th><th>목표</th></tr></thead><tbody>
<tr><td>1.5 이상</td><td>균열 발생을 방지해야 할 경우</td></tr>
<tr><td>1.2 이상 1.5 미만</td><td>균열 발생을 제한할 경우</td></tr>
<tr><td>0.7 이상 1.2 미만</td><td>유해한 균열 발생을 제한할 경우</td></tr>
</tbody></table>'''
table3='''<table border="1" style="border-collapse:collapse;width:100%"><thead><tr><th>단계</th><th>제어방법</th><th>작용</th></tr></thead><tbody>
<tr><td>설계</td><td>균열유발줄눈, 온도철근(배력철근) 보강, 타설 블록 분할 계획</td><td>균열 위치 유도·폭 제한</td></tr>
<tr><td>재료·배합</td><td>저발열·중용열 시멘트, 플라이애시·고로슬래그 미분말 치환, 단위시멘트량 저감</td><td>발열량·최고온도 저감</td></tr>
<tr><td>시공</td><td>프리쿨링(재료 냉각), 파이프쿨링, 타설 높이·이어치기 간격 조절, 낮은 시간대 타설</td><td>타설온도·온도상승 저감, 구속 완화</td></tr>
<tr><td>양생</td><td>보온양생, 거푸집 존치, 표면 급랭·찬물 살수 방지</td><td>내외부 온도차 축소</td></tr>
<tr><td>해석·계측</td><td>수화열 해석, 온도계 매설, 온도차·온도균열지수 실시간 관리</td><td>계획 검증·양생 조정</td></tr>
</tbody></table>'''
body=f'''<p>온도균열 답안을 '수화열이 크다'에서 끝내면 원인 설명이 얕아진다. <strong>언제(상승기·강하기), 무엇이 붙잡아서(내부구속·외부구속), 어떤 지표로 판단하고(온도균열지수), 설계·재료·시공·양생 어느 단계에서 줄이는지</strong>를 한 흐름으로 써야 한다.</p>
<h2><a href="https://geoai-na.netlify.app/civil-questions/">함께 푸는 [토목시공기술사] 답안지 요청</a></h2>
<p>문제를 요청하시면 접수 순서에 따라 매일 밤 11시에 요청을 확인하고, 정답예시와 따라쓰기 PDF를 작성해 블로그에 올립니다.</p>
<h2>오늘의 문제</h2>
<p><strong>시험 종목:</strong> 토목시공기술사 / <strong>과목(학습 분류):</strong> 콘크리트공 / <strong>유형:</strong> 논술형 / <strong>관련 기출:</strong> 2023년 제130회 2교시 4번</p>
<blockquote>{QUESTION}</blockquote>
<p>위 문제는 <strong>2023년 제130회 2교시 4번 기출 원문</strong>이다. 답안예시는 학습용으로 작성한 것이며 공식 정답이나 채점기준이 아니다. 권장 연습은 목차 5분, 작성 20분, 답안지 약 3쪽이다. 학습 분류와 시간·분량은 연습을 위한 안내이다.</p>
<h3>출제 흐름과 이번 주제</h3>
<p>2022~2026년 제126~140회 465문항에서 '온도균열'을 문제 문구에 직접 쓴 문항은 다음 3건이다. 논술형 2건과 단답형 1건이며, 같은 문제가 3회 반복되었다는 뜻은 아니다.</p><ul>{past}</ul>
<p>시공 중 균열 일반(제126회 2교시 5번)과 터널 라이닝 균열(제132회 3교시 1번, 제140회 3교시 3번)도 온도 영향을 다루지만 문제의 중심이 달라 이번 묶음에서 뺐다. 콘크리트·거푸집·양생 분야의 중복 허용 키워드 집계(82문항)는 분야 지표일 뿐이며 이번 유형의 출제 횟수나 공식 출제 비중으로 쓰지 않았다. 2일차 서중콘크리트 글이 타설 직후 수분 증발과 소성수축을 다뤘다면, 이번 글은 수화열이 만드는 부재 내부 온도 분포와 구속을 다룬다.</p>
<h2>답안 목차</h2><p>1. 개요 → 2. 발생 메커니즘(내부구속·외부구속) → 3. 발생원인 → 4. 온도균열지수 → 5. 제어방법 → 6. 시공 중 관리 → 7. 결론</p>
<h2>답안예시</h2>
<h3>1. 개요</h3>
<p>온도균열은 시멘트 수화열로 콘크리트 온도가 오르내리는 동안 생기는 부피 변화가 구속되어 발생하는 인장응력이 그 재령의 인장강도를 넘을 때 생기는 균열이다. 부재 단면이 커서 수화열이 잘 빠져나가지 않는 매스콘크리트(두꺼운 기초·교각·벽체 등)에서 주로 문제가 되며, 관통균열로 이어지면 누수·철근 부식·내구성 저하의 원인이 된다.</p>
<h3>2. 발생 메커니즘</h3>
<!--FIGURE:{FIG}-->
<figure><img src="{{{{FIGURE_URL}}}}" alt="두꺼운 콘크리트 단면에서 심부 고온·표면 인장의 내부구속과, 기존 콘크리트 위 벽체가 수축하며 생기는 외부구속 관통균열, 아래에 재령에 따른 온도 상승·강하 곡선을 그린 개념도" style="max-width:100%;height:auto"><figcaption>직접 작성한 개념도. 축척과 실제 온도값을 나타내지 않는다.</figcaption></figure>
{table1}
<p>내부구속 균열은 온도가 오르는 초기에 심부가 표면보다 더 팽창하면서 표면에 인장응력이 걸려 생긴다. 외부구속 균열은 최고온도를 지난 뒤 부재 전체가 식으며 수축할 때, 먼저 친 콘크리트나 암반이 아래에서 붙잡아 생긴다. 앞의 것은 내외부 온도차, 뒤의 것은 온도 강하량과 구속 정도가 지배한다.</p>
<h3>3. 발생원인</h3>
<p><strong>재료·배합</strong>: 단위시멘트량이 많거나 조강·보통 시멘트처럼 초기 발열이 큰 시멘트를 쓰면 최고온도가 높아진다. <strong>구조 조건</strong>: 부재가 두꺼울수록 열이 빠지지 않고, 기초 위 벽체처럼 아래가 굳은 콘크리트에 붙어 있으면 외부구속이 커진다. <strong>시공</strong>: 타설온도가 높거나 한 번에 치는 높이가 크고, 이어치기 시간 간격이 길어 신구 콘크리트의 온도·강도 차가 커지면 균열 위험이 커진다. <strong>양생·환경</strong>: 거푸집을 일찍 떼거나 찬 바람·찬물로 표면이 급히 식으면 내외부 온도차가 커지고, 일교차가 큰 계절에도 같은 현상이 생긴다.</p>
<h3>4. 온도균열지수</h3>
<p>온도균열지수 I<sub>cr</sub>는 어느 재령의 콘크리트 인장강도를 그 재령에 발생한 온도응력으로 나눈 값이다(I<sub>cr</sub> = f<sub>sp</sub>(t) / σ<sub>t</sub>(t)). 값이 클수록 균열 가능성이 낮다. 아래 참고 논문(2010)이 당시 콘크리트 시방서 매스콘크리트편을 인용해 제시한 목표 구간은 다음과 같다.</p>
{table2}
<p>현행 KCS 14 20 42의 목표 구간은 이번 작성에서 조문을 직접 확인하지 못했다. 정밀하게는 수화열·온도응력 해석으로 구하고, 내부구속이 지배하는 경우에는 내외부 온도차로 어림하는 간이식도 쓰인다. 아래 참고 논문(2010)이 인용한 간이식은 I<sub>cr</sub> = 15/ΔT<sub>i</sub>(ΔT<sub>i</sub>: 심부 최고온도와 표면의 온도차, ℃)이다.</p>
<p><strong>계산 예</strong> — 이 간이식을 쓴다고 가정하면, 내외부 온도차가 12℃일 때 I<sub>cr</sub> = 15/12 = 1.25로 '균열 발생 제한' 구간이다. '균열 발생 방지(1.5 이상)'를 목표로 하면 ΔT<sub>i</sub> ≤ 15/1.5 = 10℃로 관리해야 한다. 같은 논문은 시공 사례 검토 결과 이 관계식이 균열 가능성을 과대평가하는 경향이 있다는 연구를 함께 소개하므로, 간이식은 계획 단계의 어림값으로 쓰고 중요한 구조물은 해석과 계측으로 확인한다. 현행 KCS 14 20 42의 산정식·계수는 적용판에서 확인해야 한다.</p>
<h3>5. 제어방법</h3>
<p>아래 원인·대책은 매스콘크리트 온도관리의 일반적인 설명이다. 항목별 적용 조건과 수치는 현행 KCS 14 20 42와 공사 시방서에서 확인한다.</p>
{table3}
<p>재료로 발열량 자체를 줄이는 것이 가장 근본적이고, 시공·양생 대책은 온도차와 강하 속도를 줄인다. 외부구속 균열은 온도만으로 완전히 막기 어려우므로 이음 간격과 균열유발줄눈으로 균열 위치를 정하고, 철근으로 균열 폭을 제한하는 설계 대책을 함께 쓴다. 보온양생은 내부구속에는 유리하지만 최고온도를 높일 수 있으므로 거푸집 해체 시점과 함께 해석으로 정한다.</p>
<h3>6. 시공 중 관리</h3>
<p>타설 전에 수화열 해석으로 최고온도·내외부 온도차·온도균열지수를 예측하고 타설 블록·높이·양생 방법을 정한다. 타설 중에는 콘크리트 온도와 외기온을 기록하고, 심부·표면·구속면 부근에 온도계를 묻어 실제 온도 이력을 해석값과 비교한다. 온도차가 계획을 넘으면 보온 강화, 거푸집 존치 연장, 파이프쿨링 수량 조정으로 대응하고, 균열이 생기면 폭·길이·관통 여부를 기록하여 보수 여부를 판단한다.</p>
<h3>7. 결론</h3>
<p>온도균열은 발열(재료)·온도차(양생)·구속(구조·시공)이 겹칠 때 생긴다. 답안에서는 내부구속과 외부구속을 구분하고, 온도균열지수로 목표를 정한 뒤 설계부터 계측까지 단계별 제어방법을 연결해 쓰는 것이 핵심이다.</p>
<h2>핵심 암기어</h2><p>내부구속(상승기·표면) · 외부구속(강하기·관통) · 온도균열지수 1.5/1.2/0.7 · 저발열·혼화재 치환 · 파이프쿨링·보온양생·균열유발줄눈</p>
<h2>답안 자가점검</h2><ul><li>내부구속과 외부구속을 발생 시기·원인·균열 형태로 구분했는가?</li><li>원인을 재료·구조·시공·양생 단계로 나누어 썼는가?</li><li>온도균열지수의 정의와 목표 구간을 썼는가?</li><li>제어방법을 설계·재료·시공·양생·계측으로 연결했는가?</li><li>간이식의 한계와 적용판 확인 필요성을 밝혔는가?</li></ul>
<h2>따라쓰기 PDF</h2>
<!--PDF:{PDF}-->
<p><a href="{{{{PDF_URL}}}}">온도균열 답안예시 따라쓰기 PDF 다운로드(3쪽)</a></p><p>Q-net 원본 답안지의 실제 작성면에 답안·표·도식을 옅은 회색(#B8B8B8)으로 배치했다. 인쇄된 서식은 유지했으며 본문 내용을 논술형 3쪽 분량으로 압축했다.</p>
<h2>공식 참고자료</h2><ul>{sourcehtml}</ul><p>관련 기출 링크는 Q-net의 회차별 문제지 게시글이다. 기준 확인일은 2026년 10월 20일이다. KCS 14 20 42는 현행 적용판의 조문을 이번 작성에서 직접 열람하지 못했다. 온도균열지수 목표 구간과 간이식은 위 논문이 당시 콘크리트 시방서를 인용한 내용을 따랐으며, 실제 적용 시에는 현행판과 공사 시방서를 확인해야 한다. 해외 자료는 매스콘크리트 온도관리 원리 참고용이다.</p>
<p>{' '.join('#'+t.replace('·','') for t in TAGS)}</p>'''
tis=body.replace(f'<!--FIGURE:{FIG}-->',f'<p data-ax-attach="{FIG}"></p>').replace(f'<!--PDF:{PDF}-->',f'<p data-ax-attach="{PDF}"></p>')
tis=re.sub(r'<figure>.*?</figure>','<p style="font-size:14px;color:#52616a">직접 작성한 개념도. 축척과 실제 온도값을 나타내지 않는다.</p>',tis,flags=re.S)
tis=re.sub(r'<p><a href="\{\{PDF_URL\}\}">[^<]*</a></p>','',tis)
(OUT/'티스토리게시본문.html').write_text(tis)
pub='https://geoai-na.netlify.app/civil-questions/materials/day04/'
blog=body.replace('{{FIGURE_URL}}',pub+'thermal-restraint.jpg').replace('{{PDF_URL}}',pub+'answer-tracing.pdf')
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
RH=32.35
def row(i,s,z=11.5):tx(202,764-i*RH,s,z)
pages=[[
'콘크리트 구조물의 온도균열 [연습 1/3]',
'1. 개요',
'수화열로 온도가 오르내릴 때 부피 변화가 구속되어',
'생긴 인장응력이 그 재령 인장강도를 넘으면 발생',
'매스콘크리트(두꺼운 기초·교각·벽체)에서 주로 문제',
'→ 관통균열 시 누수·철근 부식·내구성 저하',
'2. 발생 메커니즘',
None,None,None,None,None,None,
'① 내부구속: 상승기, 심부 팽창 > 표면 → 표면 인장',
'   지배요인: 내외부 온도차 ΔTi / 표면균열, 비교적 얕음',
'② 외부구속: 강하기, 전체 수축을 기존 콘크리트·암반이',
'   구속 → 일정 간격 관통균열 / 지배: 강하량·구속도',
'3. 발생원인',
'① 재료·배합: 단위시멘트량 과다, 초기 발열 큰 시멘트',
'② 구조: 부재 두께 큼, 기초 위 벽체처럼 구속 큼',
'③ 시공: 타설온도 높음, 1회 타설 높이 큼, 이어치기 지연',
'④ 양생·환경: 조기 탈형, 표면 급랭, 큰 일교차',
],[
'콘크리트 구조물의 온도균열 [연습 2/3]',
'4. 온도균열지수 Icr',
'Icr = 인장강도 fsp(t) / 온도응력 σt(t) → 클수록 안전',
None,None,None,None,
'간이식(내부구속, 참고 논문 인용): Icr = 15 / ΔTi',
'계산 예: ΔTi = 12℃ → Icr = 15/12 = 1.25 (제한 구간)',
'방지 목표 1.5 이상 → ΔTi ≤ 15/1.5 = 10℃ 관리',
'※ 간이식은 과대평가 경향 → 해석·계측으로 확인',
'※ 현행 KCS 14 20 42 산정식·계수는 적용판 확인',
'5. 제어방법',
'① 설계: 균열유발줄눈, 온도철근 보강, 블록 분할',
'② 재료: 저발열·중용열 시멘트, FA·고로슬래그 치환,',
'   단위시멘트량 저감 → 발열량·최고온도 저감',
'③ 시공: 프리쿨링, 파이프쿨링, 타설 높이·간격 조절,',
'   기온 낮은 시간대 타설 → 타설온도·상승량 저감',
'④ 양생: 보온양생, 거푸집 존치, 표면 급랭·찬물 금지',
'   → 내외부 온도차 축소 (최고온도 상승 함께 검토)',
'⑤ 외부구속은 온도만으로 못 막음 → 위치 유도·폭 제한',
],[
'콘크리트 구조물의 온도균열 [연습 3/3]',
'6. 시공 중 관리',
None,None,None,
'① 타설 전: 수화열 해석 → 최고온도·온도차·Icr 예측',
'   → 타설 블록·높이·양생 방법 결정',
'② 타설 중: 콘크리트 온도·외기온 기록',
'③ 양생 중: 심부·표면·구속면 온도계 매설',
'   실측 온도 이력과 해석값 비교',
'④ 초과 시: 보온 강화, 탈형 연기, 쿨링 수량 조정',
'⑤ 균열 시: 폭·길이·관통 여부 기록 → 보수 판단',
'7. 결론',
'온도균열 = 발열(재료) + 온도차(양생) + 구속(구조·시공)',
'내부·외부구속 구분 → Icr로 목표 설정',
'→ 설계·재료·시공·양생·계측 단계별 제어를 연결',
'"끝"',
None,
'학습용 답안 예시 / 공식 정답·채점기준 아님',
'관련 기출: 2023 제130회 2교시 4번(원문)',
'참고: KCS 14 20 42, 구조물진단학회지 14(1) 2010,',
'      TRB Webinar 2018(매스콘크리트)',
]]
for n,rr in enumerate(pages):
    for i,s in enumerate(rr):
        if s:row(i,s,13 if i==0 else 11.5)
    tx(132,731,str(n+1),13)
    c.setStrokeColorRGB(G,G,G);c.setLineWidth(1)
    if n==0:
        # rows 8~12: 내부구속(좌)·외부구속(우) 개념 단면, 글씨는 답안지 줄 기준선에 맞춘다
        b=lambda i:764-i*RH
        c.rect(210,b(11)-6,170,b(8)-b(11)+24)
        c.rect(250,b(10)-6,90,26)
        tx(262,b(10),'심부 고온',10.5)
        tx(214,b(8)+4,'표면 인장',10)
        for x in (300,330,360):c.line(x,b(8)+18,x+4,b(8)+2)
        c.rect(430,b(10)-6,160,b(8)-b(10)+12)
        c.rect(420,b(11)-6,180,26)
        tx(470,b(9),'벽체 수축',10.5);tx(445,b(11),'기존 콘크리트·암반',10)
        for x in (455,560):c.line(x,b(8)+6,x,b(10)-6)
        tx(214,b(12),'① 내부구속',11);tx(430,b(12),'② 외부구속(관통균열)',11)
    if n==1:
        xs=[202,300,600]
        rows=[('Icr','목표'),('1.5 이상','균열 발생 방지'),('1.2~1.5 미만','균열 발생 제한'),('0.7~1.2 미만','유해한 균열 발생 제한')]
        ys=[764-(3+k)*RH+21 for k in range(len(rows)+1)]
        for x in xs:c.line(x,ys[-1],x,ys[0])
        for y in ys:c.line(xs[0],y,xs[-1],y)
        for j,vs in enumerate(rows):
            for k,s in enumerate(vs):tx(xs[k]+5,764-(3+j)*RH,s,10.5)
    if n==2:
        y0=764-2*RH+6
        for k,(lab,x) in enumerate([('해석',210),('타설',300),('계측',390),('비교',480),('조치',560)]):
            c.rect(x,y0-50,58 if k<4 else 45,26);tx(x+9,y0-41,lab,11)
            if k<4:c.line(x+58,y0-37,x+90 if k<3 else 558,y0-37)
        tx(210,764-4*RH,'온도차·Icr 이 계획 범위를 넘으면 양생 조정',10.5)
    c.showPage()
c.save();buf.seek(0);ov=PdfReader(buf);wr=PdfWriter()
for p in ov.pages:
    page=PdfReader(SRC).pages[4];page.merge_page(p);wr.add_page(page)
wr.add_metadata({'/Title':TITLE+' - 따라쓰기','/Subject':'학습용 답안예시(제130회 2교시 4번 기출 원문). Q-net 원본 작성면 보존. 작성 글씨·표·도식 #B8B8B8.'})
with (OUT/PDF).open('wb') as fo:wr.write(fo)
print(json.dumps({'pages':len(wr.pages),'title':TITLE,'related':IDS},ensure_ascii=False))
