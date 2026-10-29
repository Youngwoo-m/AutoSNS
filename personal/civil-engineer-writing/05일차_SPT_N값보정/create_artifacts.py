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
DAY=5
FIG='SPT_N값보정_개념도.jpg'
PDF='05일차_SPT_N값보정_답안예시_따라쓰기.pdf'
TITLE='[토목시공기술사] 표준관입시험(SPT) N값 보정 | 하루 한 문제 5일차'
QUESTION='표준관입시험(SPT)에서의 N값 보정'
TAGS=['토목시공기술사','표준관입시험','SPT','N값보정','지반조사','토질기초','기술사답안','하루한문제']
ALL=json.loads((BASE/'기출분석_2022-2026/전체465문항.json').read_text())
IDS=['126-1-11','132-1-12','137-1-7']
RELATED=[q for q in ALL if q['id'] in IDS]
SOURCES=[
('WSDOT Geotechnical Design Manual M 46-03.08, Chapter 5 Engineering Properties of Soil and Rock(2013), 5.5절 식 (5-1)~(5-3)','https://wsdot.wa.gov/publications/manuals/fulltext/M46-03/Chapter5.pdf'),
('공공데이터포털 — 국토교통부 지반정보 표준관입시험 데이터 설명(63.5kg 해머·76cm 낙하·30cm 관입)','https://www.data.go.kr/biz/dcat/metadata/15148686.do'),
('국가표준인증통합정보시스템(e-나라표준인증) — KS F 2307 흙의 표준 관입 시험 방법 현행판 검색','https://standard.go.kr'),
]

E_TH=63.5*9.81*0.76
N,ER,SV=18,80,0.5
N60=N*ER/60
import math
CN=min(0.77*math.log10(20/SV),2.0)
N160=CN*N60
CN2=0.77*math.log10(20/2.0)
assert abs(E_TH-473.4)<0.1 and N60==24 and abs(CN-1.234)<0.001 and abs(N160-29.6)<0.05 and abs(CN2-0.77)<1e-9

FONT='/System/Library/Fonts/Supplemental/AppleGothic.ttf'
f=lambda s:ImageFont.truetype(FONT,s)
im=Image.new('RGB',(1600,1000),'#f7fafb');d=ImageDraw.Draw(im)
def it(x,y,s,size=28,color='#19394b'):d.text((x,y),s,font=f(size),fill=color)
it(70,40,'SPT N값: 측정값 N → 에너지 보정 N60 → 상재압 보정 (N1)60',38)
# left: test apparatus
it(90,120,'① 시험 — 측정 N값',30,'#176977')
d.rectangle((300,170,380,240),fill='#8aa1ad',outline='#19394b',width=3);it(395,185,'해머 63.5kg',24)
d.line((340,240,340,330),fill='#b5452e',width=3);d.polygon([(330,320),(350,320),(340,335)],fill='#b5452e');it(395,265,'낙하고 76cm',24)
d.rectangle((300,335,380,355),fill='#19394b');it(395,330,'앤빌',22,'#506875')
d.rectangle((332,355,348,700),fill='#9aa9b1');it(395,420,'로드',22,'#506875')
d.rectangle((150,600,600,880),fill='#e2d3b6',outline=None)
d.rectangle((320,640,360,800),fill='#5f7480',outline='#19394b',width=2);it(395,690,'스플릿 스푼 샘플러',24)
d.line((300,720,300,800),fill='#19394b',width=2);d.line((292,720,308,720),fill='#19394b',width=2);d.line((292,800,308,800),fill='#19394b',width=2)
it(150,810,'30cm 관입 타격수 = N',24)
it(110,900,'시추공 바닥에서 예비 관입 뒤 측정',22,'#506875')
# right: correction flow
it(820,120,'② 보정 — 설계에 쓰는 N값',30,'#176977')
boxes=[('측정 N',''),('N60 = (ER/60%)·N','해머 에너지 효율 보정'),('(N1)60 = CN·N60','유효 상재압 보정'),('설계 상관식 적용','상대밀도·내부마찰각 등')]
for k,(a,b) in enumerate(boxes):
    y=180+k*175
    d.rounded_rectangle((850,y,1500,y+110),radius=14,fill='#ffffff' if k%3 else '#dbe9ec',outline='#19394b',width=3)
    it(880,y+18,a,30);it(880,y+64,b,22,'#506875')
    if k<3:d.line((1175,y+110,1175,y+175),fill='#19394b',width=3);d.polygon([(1165,y+160),(1185,y+160),(1175,y+175)],fill='#19394b')
it(820,890,'로드 길이·공경·라이너 보정은 표준 절차를 벗어난 경우 추가',22,'#506875')
it(70,950,'직접 작성한 학습용 개념도 / 축척 아님 / 보정식 적용 여부는 설계법·상관식이 요구하는 N값에 맞춘다',22,'#506875')
im.save(OUT/FIG,quality=95,subsampling=0)

past=''.join(f'<li>{q["year"]}년 제{q["round"]}회 {q["period"]}교시 {q["number"]}번({q["kind"]}): <a href="{html.escape(q["source"],quote=True)}">{html.escape(q["question"])}</a></li>' for q in RELATED)
sourcehtml=''.join(f'<li><a href="{html.escape(u,quote=True)}">{t}</a></li>' for t,u in SOURCES)
table1='''<table border="1" style="border-collapse:collapse;width:100%"><thead><tr><th>보정</th><th>식</th><th>바로잡는 요인</th></tr></thead><tbody>
<tr><td>에너지(해머 효율)</td><td>N<sub>60</sub> = (ER/60%)·N</td><td>해머 형식·낙하 방식에 따라 로드에 전달되는 에너지 차이</td></tr>
<tr><td>유효 상재압</td><td>(N<sub>1</sub>)<sub>60</sub> = C<sub>N</sub>·N<sub>60</sub>, C<sub>N</sub> = 0.77·log<sub>10</sub>(20/σ′<sub>v</sub>) &lt; 2.0 (σ′<sub>v</sub>: tsf)</td><td>같은 밀도의 모래도 깊을수록(구속압이 클수록) N값이 커지는 영향</td></tr>
<tr><td>로드 길이·공경·라이너</td><td>보정계수 곱</td><td>표준 절차를 벗어난 장비·조건(액상화 평가 등에서 중요)</td></tr>
<tr><td>포화 세립 모래(고전식)</td><td>N′ = 15 + ½(N − 15), N &gt; 15</td><td>조밀한 포화 실트질 세립 모래의 일시적 과잉간극수압</td></tr>
</tbody></table>'''
table2='''<table border="1" style="border-collapse:collapse;width:100%"><thead><tr><th>단계</th><th>계산</th><th>결과</th></tr></thead><tbody>
<tr><td>조건</td><td>측정 N = 18, 자동 해머 ER = 80%, σ′<sub>v</sub> = 0.5 tsf(약 48 kPa)</td><td>—</td></tr>
<tr><td>에너지 보정</td><td>N<sub>60</sub> = (80/60) × 18</td><td>24.0</td></tr>
<tr><td>상재압 계수</td><td>C<sub>N</sub> = 0.77 × log<sub>10</sub>(20/0.5) = 0.77 × 1.602</td><td>1.234 (&lt; 2.0)</td></tr>
<tr><td>상재압 보정</td><td>(N<sub>1</sub>)<sub>60</sub> = 1.234 × 24.0</td><td>29.6 ≒ 30</td></tr>
</tbody></table>'''
body=f'''<p>N값 보정 답안은 '해머 효율 보정, 상재압 보정'을 나열하는 데서 끝나면 답안이 얕아진다. <strong>왜 측정 N값을 그대로 쓰면 안 되는지(장비·깊이·토질), 어떤 식으로 어떤 기준값에 맞추는지(N<sub>60</sub>, (N<sub>1</sub>)<sub>60</sub>), 보정한 값을 어디에 쓰고 어디에 쓰지 말아야 하는지</strong>를 계산 예와 함께 짧게 보여 주어야 한다.</p>
<h2><a href="https://geoai-na.netlify.app/civil-questions/">함께 푸는 [토목시공기술사] 답안지 요청</a></h2>
<p>문제를 요청하시면 접수 순서에 따라 매일 밤 11시에 요청을 확인하고, 정답예시와 따라쓰기 PDF를 작성해 블로그에 올립니다.</p>
<h2>오늘의 문제</h2>
<p><strong>시험 종목:</strong> 토목시공기술사 / <strong>과목(학습 분류):</strong> 토질·기초(지반조사) / <strong>유형:</strong> 단답형 / <strong>관련 기출:</strong> 2025년 제137회 1교시 7번</p>
<blockquote>{QUESTION}</blockquote>
<p>위 문제는 <strong>2025년 제137회 1교시 7번 기출 원문</strong>이다. 답안예시는 학습용으로 작성한 것이며 공식 정답이나 채점기준이 아니다. 권장 연습은 목차 2분, 작성 8분, 답안지 약 1.5쪽이다. 학습 분류와 시간·분량은 연습을 위한 안내이다.</p>
<h3>출제 흐름과 이번 주제</h3>
<p>2022~2026년 제126~140회 465문항에서 표준관입시험(SPT)을 문제 문구에 직접 쓴 문항은 다음 3건이며 모두 1교시 단답형이다. 시험 자체(제126회), 결과로 추정할 수 있는 사항(제132회), N값 보정(제137회)으로 묻는 각도가 달라 같은 문제가 3회 반복되었다는 뜻은 아니다.</p><ul>{past}</ul>
<p>기초·흙막이·연약지반 등 지반 분야의 중복 허용 키워드 집계(64문항)는 분야 지표일 뿐이며 이번 유형의 출제 횟수나 공식 출제 비중으로 쓰지 않았다. 3일차 흙막이 계측관리가 시공 중 지반 거동을 다뤘다면, 이번 글은 설계 전 지반조사 값의 신뢰도를 다룬다. 답안의 4·5항은 제126회와 제132회 문제에도 그대로 쓸 수 있다.</p>
<h2>답안 목차</h2><p>1. 정의 → 2. 보정이 필요한 이유 → 3. 보정 방법(식) → 4. 계산 예 → 5. 활용과 유의사항</p>
<h2>답안예시</h2>
<h3>1. 정의</h3>
<p>표준관입시험(SPT)은 시추공 바닥에서 63.5kg 해머를 76cm 높이에서 떨어뜨려 스플릿 스푼 샘플러를 30cm 관입시키는 데 필요한 타격 횟수(N값)를 재는 원위치 시험이다. 시료를 함께 얻을 수 있어 지층 확인과 사질토의 상대밀도·내부마찰각 추정, 기초 지지층 판단에 널리 쓰인다. 해머 1회 낙하의 이론 위치에너지는 63.5 × 9.81 × 0.76 ≒ 473J이지만, 실제로 로드에 전달되는 에너지는 장비에 따라 이보다 작다.</p>
<h3>2. 보정이 필요한 이유</h3>
<!--FIGURE:{FIG}-->
<figure><img src="{{{{FIGURE_URL}}}}" alt="왼쪽은 63.5kg 해머가 76cm 낙하해 로드 끝 스플릿 스푼 샘플러를 30cm 관입시키는 시험 모식도, 오른쪽은 측정 N에서 N60, (N1)60, 설계 상관식 적용으로 이어지는 보정 흐름도" style="max-width:100%;height:auto"><figcaption>직접 작성한 개념도. 축척을 나타내지 않는다.</figcaption></figure>
<p>같은 지반이라도 N값은 <strong>장비</strong>(해머 형식과 낙하 방식에 따른 에너지 효율, 로드 길이, 공경, 라이너 사용)와 <strong>심도</strong>(유효 상재압), <strong>토질</strong>(자갈 혼입, 포화 세립 모래)에 따라 달라진다. 아래 출처의 WSDOT 지반설계 매뉴얼은 측정 N값이 장비와 작업자에 좌우되므로, 사용하는 설계법·상관식이 요구하는 기준에 맞게 보정한 뒤 설계에 쓰도록 하고 있다. 많은 상관식이 에너지 효율 60% 기준인 N<sub>60</sub>을 바탕으로 만들어졌기 때문이다.</p>
<h3>3. 보정 방법</h3>
{table1}
<p>에너지 보정에서 ER은 해머가 실제로 전달한 에너지를 이론 자유낙하 에너지에 대한 백분율로 나타낸 값이다. WSDOT 매뉴얼은 장비별 측정값이 없을 때 로프·캣헤드식 재래 해머는 60%, 자동 낙하 해머는 80%를 가정할 수 있게 하고, 장비별 효율은 ASTM D4633 등의 동적 측정으로 정하도록 한다. 상재압 보정식 (5-3)은 σ′<sub>v</sub>를 tsf(1 tsf ≒ 95.8 kPa) 단위로 넣는 식이며, 얕은 곳에서 계수가 지나치게 커지지 않도록 2.0 미만으로 제한한다. 상재압 보정식은 문헌마다 형태와 상한이 다르므로 답안에는 사용한 식의 출처와 단위를 함께 적는다. 로드 길이·공경·라이너 보정은 표준 절차에서 벗어난 경우에 주로 의미가 있고 액상화 평가에서는 중요할 수 있다.</p>
<p>포화된 조밀한 실트질 세립 모래에서 N &gt; 15일 때 N′ = 15 + ½(N − 15)로 줄이는 식은 Terzaghi·Peck이 제안한 것으로 국내 교재에서 흔히 다루는 고전 보정이다. 원 출처를 확인하기 전의 고전식이므로 답안에 쓸 때는 적용 토질과 조건을 함께 밝힌다.</p>
<h3>4. 계산 예</h3>
{table2}
<p>측정값 18이 장비 효율만 반영해도 24가 되고, 얕은 심도의 낮은 구속압을 반영하면 약 30이 된다. 반대로 σ′<sub>v</sub> = 2.0 tsf인 깊은 곳에서는 C<sub>N</sub> = 0.77 × log<sub>10</sub>10 = 0.77로 값이 줄어든다. 같은 측정 N이라도 장비와 깊이에 따라 설계에 쓰는 값이 달라진다는 점이 보정의 핵심이다. 계산 조건은 학습용 가정이다.</p>
<h3>5. 활용과 유의사항</h3>
<p>보정한 N값은 주로 사질토의 상대밀도·내부마찰각 추정, 얕은 기초 지지력·침하 검토, 액상화 평가에 쓰인다. 같은 매뉴얼은 N값 상관식을 원칙적으로 사질토(특히 모래)에 쓰고, 자갈이 샘플러를 막아 타격수와 마찰각이 과대평가될 수 있으며, 점토·실트 정수 추정은 예비값으로만 보도록 주의를 준다. 따라서 점성토는 베인 전단시험·일축압축시험 등으로 확인하고, 보고서에는 측정 N, 해머 형식과 ER, 적용한 보정식을 함께 적어 어떤 N값인지 구분한다. 보정은 사용하는 상관식이 요구하는 기준(N, N<sub>60</sub>, (N<sub>1</sub>)<sub>60</sub>)에 맞춰서만 적용하고, 이미 보정된 값에 다시 보정을 겹치지 않는다.</p>
<h2>핵심 암기어</h2><p>63.5kg·76cm·30cm · N<sub>60</sub> = (ER/60)·N · (N<sub>1</sub>)<sub>60</sub> = C<sub>N</sub>·N<sub>60</sub> · 로드 길이·공경·라이너 · 사질토 위주, 자갈 과대평가</p>
<h2>답안 자가점검</h2><ul><li>시험 정의에 해머 무게·낙하고·관입 길이를 정확히 썼는가?</li><li>보정이 필요한 이유를 장비·심도·토질로 나누었는가?</li><li>에너지 보정과 상재압 보정의 식, 변수, 단위를 썼는가?</li><li>계산 예로 보정 전후 값 차이를 보였는가?</li><li>보정값의 활용 범위와 점성토·자갈층 한계를 밝혔는가?</li></ul>
<h2>따라쓰기 PDF</h2>
<!--PDF:{PDF}-->
<p><a href="{{{{PDF_URL}}}}">SPT N값 보정 답안예시 따라쓰기 PDF 다운로드(2쪽)</a></p><p>Q-net 원본 답안지의 실제 작성면에 답안·표·도식을 옅은 회색(#B8B8B8)으로 배치했다. 인쇄된 서식은 유지했으며 단답형 분량에 맞춰 본문을 압축했다.</p>
<h2>공식 참고자료</h2><ul>{sourcehtml}</ul><p>관련 기출 링크는 Q-net의 회차별 문제지 게시글이다. 기준 확인일은 2026년 10월 21일이다. 보정식 (5-1)~(5-3)과 ER 가정값, 상관식 사용상 주의는 WSDOT 매뉴얼 5.5절 원문에서 확인했다. KS F 2307은 이번 작성에서 조문을 직접 열람하지 못했으므로 시험 장비·절차의 세부 규정은 현행판에서 확인해야 한다. 해외 설계 매뉴얼은 보정 원리와 식의 출처로 인용했으며, 국내 설계에 적용할 식과 계수는 해당 사업의 설계기준과 지반조사 보고서를 따른다.</p>
<p>{' '.join('#'+t.replace('·','') for t in TAGS)}</p>'''
tis=body.replace(f'<!--FIGURE:{FIG}-->',f'<p data-ax-attach="{FIG}"></p>').replace(f'<!--PDF:{PDF}-->',f'<p data-ax-attach="{PDF}"></p>')
tis=re.sub(r'<figure>.*?</figure>','<p style="font-size:14px;color:#52616a">직접 작성한 개념도. 축척을 나타내지 않는다.</p>',tis,flags=re.S)
tis=re.sub(r'<p><a href="\{\{PDF_URL\}\}">[^<]*</a></p>','',tis)
(OUT/'티스토리게시본문.html').write_text(tis)
pub='https://geoai-na.netlify.app/civil-questions/materials/day05/'
blog=body.replace('{{FIGURE_URL}}',pub+'spt-correction.jpg').replace('{{PDF_URL}}',pub+'answer-tracing.pdf')
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
'표준관입시험(SPT)에서의 N값 보정 [연습 1/2]',
'1. 정의',
'시추공 바닥에서 63.5kg 해머를 76cm 낙하시켜 스플릿',
'스푼 샘플러를 30cm 관입시키는 타격수(N값) 원위치 시험',
'→ 시료 채취 + 사질토 상대밀도·φ 추정, 지지층 판단',
'이론 낙하에너지 = 63.5×9.81×0.76 ≒ 473J (실전달은 작음)',
'2. 보정이 필요한 이유',
'① 장비: 해머 형식·낙하 방식(에너지 효율), 로드·공경·라이너',
'② 심도: 유효 상재압↑ → 같은 밀도라도 N↑',
'③ 토질: 자갈 혼입(과대), 포화 세립 모래(과잉간극수압)',
'→ 설계 상관식이 요구하는 기준값(N60 등)으로 맞춘다',
'3. 보정 방법',
None,None,None,None,None,
'· ER 측정값 없을 때(WSDOT): 재래 해머 60%, 자동 80%',
'· CN 식은 σ\'v 단위 tsf(1tsf≒95.8kPa), 문헌마다 형태 다름',
'· 로드 길이·공경·라이너: 비표준 절차·액상화 평가 시',
'· 포화 세립 모래 N이 15 초과: N\' = 15 + 0.5(N - 15) (Terzaghi·Peck)',
],[
'표준관입시험(SPT)에서의 N값 보정 [연습 2/2]',
'4. 계산 예 (학습용 가정)',
'조건: N = 18, 자동 해머 ER = 80%, σ\'v = 0.5 tsf(약 48kPa)',
'① N60 = (80/60) × 18 = 24.0',
'② CN = 0.77 × log10(20/0.5) = 0.77 × 1.602 = 1.234 (2.0 미만)',
'③ (N1)60 = 1.234 × 24.0 = 29.6 ≒ 30',
'※ 깊은 곳 σ\'v = 2.0 tsf → CN = 0.77×log10(10) = 0.77',
'5. 활용과 유의사항',
'① 활용: 사질토 상대밀도·φ, 얕은 기초 지지력·침하, 액상화',
'② 상관식은 사질토(모래) 위주, 점성토 정수는 예비값',
'   → 베인 전단·일축압축시험으로 확인',
'③ 자갈: 샘플러 막힘 → N·φ 과대평가 주의',
'④ 보고: 측정 N, 해머 형식·ER, 적용 보정식을 함께 기록',
'⑤ 상관식이 요구하는 N 기준에만 맞춰 보정, 중복 보정 금지',
'"끝"',
None,
'학습용 답안 예시 / 공식 정답·채점기준 아님',
'관련 기출: 2025 제137회 1교시 7번(원문)',
'참고: WSDOT GDM M46-03.08 Ch.5(2013) 식 5-1~5-3,',
'      KS F 2307(현행판 확인), 국토부 지반정보 설명',
]]
for n,rr in enumerate(pages):
    for i,s in enumerate(rr):
        if s:row(i,s,13 if i==0 else 11.5)
    tx(132,731,str(n+1),13)
    c.setStrokeColorRGB(G,G,G);c.setLineWidth(1)
    if n==0:
        # rows 12~16: 보정 흐름 상자 + 식
        b=lambda i:764-i*RH
        labs=[('측정 N',210,60),('N60',300,50),('(N1)60',380,62),('상관식',475,58)]
        for k,(lab,x,w) in enumerate(labs):
            c.rect(x,b(12)-6,w,24);tx(x+7,b(12),lab,11)
            if k<3:
                nx=labs[k+1][1];c.line(x+w,b(12)+6,nx,b(12)+6);c.line(nx-6,b(12)+10,nx,b(12)+6);c.line(nx-6,b(12)+2,nx,b(12)+6)
        tx(210,b(13),'에너지: N60 = (ER/60%) × N',11.5)
        tx(210,b(14),'상재압: (N1)60 = CN × N60',11.5)
        tx(210,b(15),'CN = 0.77·log10(20/σ\'v), 2.0 미만  (σ\'v: tsf)',11.5)
        tx(210,b(16),'ER: 해머 실전달 에너지 / 이론 자유낙하 에너지(%)',11)
    c.showPage()
c.save();buf.seek(0);ov=PdfReader(buf);wr=PdfWriter()
for p in ov.pages:
    page=PdfReader(SRC).pages[4];page.merge_page(p);wr.add_page(page)
wr.add_metadata({'/Title':TITLE+' - 따라쓰기','/Subject':'학습용 답안예시(제137회 1교시 7번 기출 원문). Q-net 원본 작성면 보존. 작성 글씨·표·도식 #B8B8B8.'})
with (OUT/PDF).open('wb') as fo:wr.write(fo)
print(json.dumps({'pages':len(wr.pages),'title':TITLE,'related':IDS,'calc':[E_TH,N60,CN,N160,CN2]},ensure_ascii=False))
