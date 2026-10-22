from pathlib import Path
from io import BytesIO
from copy import deepcopy
import json, html
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter

OUT=Path(__file__).parent
BASE=OUT.parent
TITLE='[토목시공기술사] 서중콘크리트 품질관리와 초기균열 저감 | 하루 한 문제 2일차'
QUESTION='고온 환경이 콘크리트 품질에 미치는 영향을 설명하고, 재료·배합·운반·타설·양생 단계별 품질관리 및 초기균열 저감대책을 기술하시오.'
TAGS=['토목시공기술사','콘크리트공','서중콘크리트','콘크리트양생','소성수축균열','품질관리','기술사답안','하루한문제']
ALL=json.loads((BASE/'기출분석_2022-2026/전체465문항.json').read_text())
IDS=['127-4-5','130-4-1','137-1-1','139-4-5','140-3-4']
RELATED=[q for q in ALL if q['id'] in IDS]
SOURCES=[
('국토교통부 고시 제2025-794호(2025.12.24), KCS 14 20 41 개정','https://www.molit.go.kr/USR/I0204/m_45/dtl.jsp?idx=18722&lcmspage=1&psize=10'),
('건설기술정보시스템 CODIL, KCS 14 20 41:2025 개정전문','https://www.codil.or.kr/filebank/moct2014/202605/MOCT3537_0.PDF?nserialno=3537'),
('건설기술정보시스템 CODIL, KCS 14 20 41:2025 신구조문대비표(1.1·1.3)','https://www.codil.or.kr/filebank/moct2014/202605/MOCT3537_1.PDF?nserialno=3537'),
('FHWA-HRT-05-038(2006), Chapter 2: 증발·블리딩과 초기양생 원리','https://www.fhwa.dot.gov/publications/research/infrastructure/pavements/pccp/05038/002.cfm'),
('FHWA-RD-02-099(2005), Chapter 1: 소성수축·온도·건조수축 균열','https://www.fhwa.dot.gov/publications/research/infrastructure/pavements/pccp/02099/chapt1.cfm'),
('FHWA-HIF-18-015(2019), Curing Concrete Paving Mixtures','https://www.fhwa.dot.gov/pavement/concrete/pubs/hif18015.pdf'),
]

# The figure is drawn from authored vector-like shapes; no stock image or AI image is used.
FONT='/System/Library/Fonts/Supplemental/AppleGothic.ttf'
im=Image.new('RGB',(1600,1000),'#f7fafb');d=ImageDraw.Draw(im)
def it(x,y,s,size=32,color='#19394b'):
    d.text((x,y),s,font=ImageFont.truetype(FONT,size),fill=color)
it(70,48,'서중콘크리트: 수분과 온도를 함께 관리한다',44)
it(70,112,'기온·콘크리트 온도·습도·풍속의 조합 → 표면 증발 증가',30)
boxes=[(70,205,510,365,'응결 전','증발 > 블리딩','소성수축 위험'),(580,205,1020,365,'응결 후','수분 손실·온도차','건조수축·온도균열 위험'),(1090,205,1530,365,'관리 목표','초기 보호 → 본 양생','양생 공백 최소화')]
for x1,y1,x2,y2,a,b,c in boxes:
    d.rounded_rectangle((x1,y1,x2,y2),radius=18,fill='white',outline='#8aaab7',width=3)
    it(x1+22,y1+18,a,34);it(x1+22,y1+68,b,30);it(x1+22,y1+110,c,26)
it(70,425,'타설·마감',34);it(790,425,'표면 손상 없이 적용 가능한 시점',30)
d.line((90,505,1510,505),fill='#19394b',width=5);d.polygon([(1510,505),(1485,490),(1485,520)],fill='#19394b')
d.rounded_rectangle((80,555,790,670),radius=12,fill='#dbecef');it(110,578,'초기 보호: 차광·방풍·미세분무 등',31)
d.rounded_rectangle((740,690,1510,805),radius=12,fill='#e7eadb');it(770,716,'본 양생: 습윤 덮개·피복·양생제 등',31)
d.line((765,530,765,830),fill='#66858e',width=3)
it(70,865,'표면수·응결·마감 상태를 확인하여 양생 방법을 전환한다.',30)
it(70,925,'직접 작성한 학습용 개념도 / 시간축·수치는 축척 없음 / 적용 방법은 시방서 확인',24,'#506875')
im.save(OUT/'서중콘크리트_양생관리_개념도.jpg',quality=95,subsampling=0)

past=''.join(f'<li>{q["year"]}년 제{q["round"]}회 {q["period"]}교시 {q["number"]}번: <a href="{html.escape(q["source"],quote=True)}">{html.escape(q["question"])}</a></li>' for q in RELATED)
sourcehtml=''.join(f'<li><a href="{u}">{t}</a></li>' for t,u in SOURCES)
table='''<table border="1" style="border-collapse:collapse;width:100%"><thead><tr><th>구분</th><th>발생 원리</th><th>우선 관리</th></tr></thead><tbody><tr><td>소성수축균열</td><td>응결 전 표면 증발이 블리딩에 의한 수분 공급을 앞질러 표층 수축</td><td>타설 직후 증발 억제, 마감과 양생 사이 공백 축소</td></tr><tr><td>건조수축균열</td><td>경화 후 수분 손실에 따른 수축이 구속되어 인장응력 발생</td><td>적절한 배합·습윤양생, 이음·구속조건 검토</td></tr><tr><td>온도균열</td><td>수화열·일사·냉각에 따른 온도변형이 내·외부 구속을 받음</td><td>타설온도·온도이력·내외부 온도차와 급냉 관리</td></tr></tbody></table>'''
body=f'''<p>서중콘크리트 답안은 고온에 따른 응결 촉진과 표면 건조를 구분하고, 각 원인을 시공 단계별 대책에 연결해야 한다. 핵심은 타설온도 관리와 양생의 연속성이다. 2025년 말 개정된 서중콘크리트 적용범위도 함께 정리한다.</p>
<h2><a href="https://geoai-na.netlify.app/civil-questions/">함께 푸는 [토목시공기술사] 답안지 요청</a></h2>
<p>문제를 요청하시면 접수 순서에 따라 매일 밤 11시에 요청을 확인하고, 정답예시와 따라쓰기 PDF를 작성해 블로그에 올립니다.</p>
<h2>오늘의 문제</h2>
<p><strong>시험 종목:</strong> 토목시공기술사 / <strong>과목(학습 분류):</strong> 콘크리트공·서중 시공 / <strong>유형:</strong> 논술형 / <strong>관련 기출:</strong> 2023년 제130회 4교시 1번, 2026년 제139회 4교시 5번·제140회 3교시 4번</p>
<blockquote>{QUESTION}</blockquote>
<p><strong>관련 기출을 바탕으로 재구성한 학습용 변형문제</strong>이다. 위 문장은 기출 원문 인용이 아니며, 답안예시도 공식 정답·채점기준이 아니다. 권장 연습은 목차 5분, 작성 20분, 답안지 약 3쪽이다. 학습 분류와 시간·분량은 연습을 위한 안내이다.</p>
<h3>출제 흐름과 이번 주제</h3>
<p>2022~2026년 제126~140회 465문항에서 하절기·서중·고온 환경의 콘크리트 품질관리를 직접 묻는 문항을 다음 5건으로 분류했다. 포장에 한정한 문항과 단답형도 포함한 학습용 묶음이며, 같은 문제가 5회 반복되었다는 뜻은 아니다.</p><ul>{past}</ul>
<p>콘크리트·거푸집·양생 분야의 중복 허용 키워드 집계 82문항은 별도 분야 지표이다. 이를 이번 세부 유형의 출제 횟수나 공식 출제 비중으로 사용하지 않았다.</p>
<h2>답안 목차</h2><p>Ⅰ. 개요·적용 판단 → Ⅱ. 품질 저하와 균열 메커니즘 → Ⅲ. 단계별 품질관리 → Ⅳ. 검사·이상 시 조치 → Ⅴ. 현장 적용과 결론</p>
<h2>답안예시</h2><h3>Ⅰ. 개요와 적용 판단</h3>
<p>서중콘크리트는 높은 외부기온 때문에 슬럼프 저하와 급격한 수분 증발 등이 우려되는 환경에서 시공하는 콘크리트이다. 기온 상승은 응결을 촉진해 작업 가능 시간을 줄이고, 낮은 습도와 바람은 표면 수분 손실을 키운다. 따라서 기온만 확인하는 관리로는 부족하다.</p>
<p><strong>KCS 14 20 41:2025의 1.1(2)</strong>는 타설일의 일 평균기온이 <strong>25℃를 초과</strong>하거나, 콘크리트 타설 완료 후 <strong>24시간 이내 일 최고기온이 30℃를 초과할 것으로 예상되는 경우</strong> 서중콘크리트로 시공하도록 규정한다. 2025년 12월 24일 개정에는 최고기온 조건이 추가되었다. 1.3의 일 평균기온은 하루 중 3시간 간격의 8회 관측값을 평균한 기온이다.</p>
<p>이 수치는 서중 시공의 적용 판단 조건이다. 굳지 않은 콘크리트의 타설온도와 구별해 써야 한다. 개정 기준의 경과조치와 계약상 공사시방서를 확인하여 해당 공사 적용판을 정한다.</p>
<h3>Ⅱ. 고온이 품질에 미치는 영향</h3>
<p>고온에서는 슬럼프 손실과 응결 촉진으로 운반·압송·다짐·마감에 필요한 여유가 줄어든다. 공급이 끊기거나 이어치기가 지연되면 일체성 확보가 어려워지고, 작업성을 회복하려고 임의로 물을 더하면 승인 배합의 품질을 유지하기 어렵다. 초기 강도 발현이 빠르더라도 장기 품질까지 좋아진다고 볼 수는 없다.</p>
<p>표면 증발이 블리딩에 의한 수분 공급보다 빨라지면 응결 전 소성수축균열 위험이 커진다. 경화 후 수분 손실로 생기는 건조수축균열, 수화열과 외기 변화에 따른 온도변형이 구속되어 생기는 온도균열은 원인이 다르므로 대책도 구분한다.</p>
{table}
<!--FIGURE:서중콘크리트_양생관리_개념도.jpg-->
<figure><img src="{{{{FIGURE_URL}}}}" alt="서중콘크리트 초기보호에서 본양생까지 이어지는 수분·온도 관리 개념도" style="max-width:100%;height:auto"><figcaption>직접 작성한 개념도. 초기 보호와 본 양생의 전환 시점은 실제 표면·응결 상태에 따라 정한다.</figcaption></figure>
<h3>Ⅲ. 단계별 품질관리</h3>
<p><strong>1. 사전계획·재료·배합</strong><br>기상 예측과 현장 조건을 바탕으로 타설 구획, 공급능력, 인력·장비, 양생 자재를 함께 계획한다. 비교적 서늘한 시간대의 작업을 검토하고, 골재 차광과 혼합수 냉각 등으로 재료 온도 상승을 줄인다. 냉각수나 얼음을 사용할 때에는 배합수량에 반영한다. 고온 조건에서 필요한 강도와 작업성을 확보하도록 시험배합하며, 혼화제는 적합성·슬럼프 유지·응결 특성을 확인한다.</p>
<p><strong>2. 제조·운반·현장 인수</strong><br>출하·도착·타설 완료 시각을 연결해 기록하고, 운반차 대기와 펌프 정체를 줄인다. 현장에서는 콘크리트 온도, 슬럼프 또는 슬럼프 플로, 공기량 등 지정 항목을 검사한다. 타설온도와 운반·타설 허용시간은 해당 적용판·공사시방서의 조건으로 관리하며, 현장 임의 가수로 슬럼프 저하를 보정하지 않는다.</p>
<p><strong>3. 타설·다짐·마감</strong><br>거푸집·철근·타설면의 가열과 건조 상태를 확인한다. 필요한 사전 습윤은 고인 물이 남지 않도록 시행한다. 타설 구획과 공급 간격을 조절해 연속성을 확보하고, 응결 전에 적절히 다짐한다. 블리딩수와 표면 상태를 확인한 뒤 마감하며, 마감 편의를 위한 표면 살수로 물을 문질러 넣지 않는다.</p>
<p><strong>4. 초기 보호·본 양생</strong><br>건조 위험이 크면 마감 전후의 노출 구간부터 보호한다. 현장에 맞게 차광·방풍·미세분무 등을 적용하되, 분무가 표면 페이스트를 씻거나 물을 고이게 하지 않도록 한다. 표면을 손상하지 않고 적용할 수 있는 시점에 습윤 덮개·피복·승인된 양생제 등의 본 양생으로 이어간다. 증발억제제를 사용할 때에는 제품의 용도와 시방조건을 확인하며 본 양생을 대신한다고 판단하지 않는다.</p>
<p>습윤 덮개는 마르지 않게 유지하고 가장자리·이음부·탈형면의 노출을 점검한다. 양생제는 피막의 연속성과 후속 도장·접착 공정의 적합성을 확인한다. 차가운 물에 의한 급냉과 피복의 급격한 제거도 피한다. 양생 종료는 정해진 시간만 세는 방식보다 적용 기준의 기간·온도·강도 조건과 구조물 상태를 함께 확인해 결정한다.</p>
<h3>Ⅳ. 검사와 이상 시 조치</h3>
<p>기온·습도·풍속, 콘크리트 온도와 타설 이력, 양생 시작·방법·유지상태를 같은 구획별 기록으로 연결한다. 강도 확인용 공시체는 목적에 맞게 제작·양생하고, 표준양생과 현장양생 결과의 의미를 구별한다. 시험체의 결과만으로 모든 부재의 실제 온도·양생 상태를 대신 판단하지 않는다.</p>
<p>기준에서 벗어난 콘크리트는 적용 절차에 따라 타설을 보류하고 책임기술자와 반입·배합·시간·온도 기록을 검토한다. 균열이 발견되면 위치·폭·깊이·진행성·발생시기를 조사하고 원인을 판단한다. 구조성능·수밀성·내구성 요구를 확인한 뒤 보수·보강 또는 추가 검사를 정한다.</p>
<h3>Ⅴ. 현장 적용과 결론</h3>
<p>교량 바닥판과 포장처럼 노출면이 넓은 부재는 마감 장비와 양생 장비의 간격이 벌어지지 않도록 관리한다. 두꺼운 부재는 표면 건조뿐 아니라 수화열·구속조건을 검토하여 온도균열 관리계획을 더한다. 대책은 ‘냉각한다’, ‘양생한다’에서 끝내지 말고 대상·시점·확인 항목까지 써야 한다.</p>
<p>서중 시공의 핵심은 재료와 운반 단계에서 온도 상승을 줄이고, 타설·마감·양생을 끊김 없이 연결하는 것이다. 수분 손실 억제와 온도변형 제어를 병행하고, 검사와 기록으로 관리 효과를 확인한다.</p>
<h2>핵심 암기어</h2><p>적용 판단 · 온도·시간 · 임의 가수 금지 · 양생 연속성 · 검사·기록</p>
<h2>답안 자가점검</h2><ul><li>개정된 일 평균기온과 타설 후 최고기온 조건을 구분했는가?</li><li>소성수축·건조수축·온도균열을 원인과 대책으로 연결했는가?</li><li>재료·배합부터 운반·타설·양생까지 빠진 단계가 없는가?</li><li>초기 보호에서 본 양생으로 넘어가는 시점을 적었는가?</li><li>검사·이상 시 조치와 기록까지 답안에 담았는가?</li></ul>
<h2>따라쓰기 PDF</h2><p><a href="{{{{PDF_URL}}}}">서중콘크리트 답안예시 따라쓰기 PDF 다운로드(3쪽)</a></p><p>Q-net 원본 답안지의 실제 작성면에 답안·도식·표를 옅은 회색(#B8B8B8)으로 배치했다. 인쇄된 서식은 유지했으며, 본문 내용을 시험 답안 분량으로 압축했다. 출력 후 문장뿐 아니라 목차와 도식의 위치도 함께 연습한다.</p>
<h2>공식 참고자료</h2><ul>{sourcehtml}</ul><p>관련 기출 원문은 위 Q-net 링크에서 확인할 수 있다. 기준 확인일은 2026년 10월 18일이다. KCS 적용범위는 2025년 12월 24일 개정 내용에 따랐다. FHWA 자료는 수분·온도 관리의 원리 참고용이며, 해외 수치를 국내 공사의 합격기준으로 전용하지 않는다.</p>
<p>{' '.join('#'+t for t in TAGS)}</p>'''
(OUT/'게시본문.html').write_text(body)
(OUT/'브라우저게시본문.html').write_text(body)
preview=body.replace('{{FIGURE_URL}}','서중콘크리트_양생관리_개념도.jpg').replace('{{PDF_URL}}','02일차_서중콘크리트_답안예시_따라쓰기.pdf')
(OUT/'블로그미리보기.html').write_text(f'<!doctype html><html lang="ko"><meta charset="utf-8"><title>{TITLE}</title><style>body{{max-width:900px;margin:40px auto;padding:0 24px;font:17px/1.85 AppleGothic,sans-serif;color:#24333d}}h1{{font-size:30px}}h2{{margin-top:42px;color:#176977}}th,td{{padding:12px}}blockquote{{padding:18px;background:#edf4f5;border-left:4px solid #176977;margin:20px 0}}a{{color:#176977}}figcaption{{font-size:14px;color:#52616a}}</style><h1>{TITLE}</h1>{preview}</html>')
(OUT/'제목.txt').write_text(TITLE+'\n')
(OUT/'태그.txt').write_text(','.join(TAGS)+'\n')

# Three-page answer, same original Q-net writing face on every page.
pdfmetrics.registerFont(TTFont('KR',FONT))
template=PdfReader('/Volumes/USB256/기술사/2026기술사 답안지-1교시(안내용)_Qnet원본.pdf')
W,H=map(float,(template.pages[4].mediabox.width,template.pages[4].mediabox.height))
G=184/255
buf=BytesIO();c=canvas.Canvas(buf,pagesize=(W,H))
def tx(x,y,s,z=12):
    assert pdfmetrics.stringWidth(s,'KR',z)<405,(s,z)
    c.setFillColorRGB(G,G,G);c.setFont('KR',z);c.drawString(x,y,s)
def row(i,s,z=12):tx(202,764-i*32.35,s,z)
pages=[[
'서중콘크리트 품질관리와 초기균열 저감 [연습 1/3]',
'Ⅰ. 개요 및 적용 판단',
'고온은 응결을 촉진하고 표면 건조를 증가시킨다.',
'슬럼프 손실·작업시간 감소·초기균열에 대비한다.',
'KCS 14 20 41:2025 (2025.12.24 개정) 적용:',
'타설일 일 평균기온 25℃ 초과 또는 타설 완료 후',
'24시간 내 일 최고기온 30℃ 초과 예상 시 적용한다.',
'적용 기온과 콘크리트의 타설온도는 구별한다.',
'Ⅱ. 품질 저하 및 균열 메커니즘',
'① 고온 → 응결 촉진·슬럼프 손실 → 작업성 저하',
'② 공급 지연 → 다짐·이어치기 여유 감소',
'③ 임의 가수 → 승인 배합의 품질 확보 곤란',
'④ 수분 손실·온도변형과 구속 → 균열 위험',
None,None,None,None,None,None,
'초기 보호에서 본 양생까지 공백을 줄인다.',
'기온·콘크리트 온도·습도·풍속을 함께 확인한다.'
],[
'서중콘크리트 단계별 관리 [연습 2/3]',
'Ⅲ. 단계별 품질관리',
'1. 사전계획·재료·배합',
'기상·공급능력·구획·인력·양생 자재를 계획한다.',
'골재 차광·혼합수 냉각 등으로 온도 상승을 줄인다.',
'냉각수·얼음은 배합수량에 반영하여 관리한다.',
'고온 시험배합으로 강도·작업성·응결을 확인한다.',
'혼화제 적합성과 슬럼프 유지 성능을 검토한다.',
'2. 제조·운반·현장 인수',
'출하·도착·타설 완료 시각을 연결하여 기록한다.',
'대기·압송 정체를 줄이고 임의 가수를 금지한다.',
'온도·슬럼프(플로)·공기량 등 지정 항목을 검사한다.',
'타설온도·허용시간은 적용 시방서의 조건을 따른다.',
'3. 타설·다짐·마감',
'거푸집·철근·타설면의 가열·건조를 확인한다.',
'사전 습윤 시 고인 물이 남지 않도록 한다.',
'공급 간격을 조절하고 응결 전 적절히 다짐한다.',
'블리딩수와 표면 상태를 확인한 뒤 마감한다.',
'마감용 살수로 물을 표면에 문질러 넣지 않는다.',
'노출면이 넓으면 마감·양생 장비 간격을 관리한다.',
'두꺼운 부재는 수화열·구속조건을 추가 검토한다.'
],[
'양생·검사·현장 적용 [연습 3/3]',
'4. 초기 보호와 본 양생',
'차광·방풍·미세분무 등으로 조기 증발을 억제한다.',
'분무 시 표면 세굴과 고인 물 발생을 방지한다.',
'표면 손상 없이 적용 가능한 시점에 본 양생한다.',
'습윤 덮개·피복·승인 양생제 등을 현장에 맞게 쓴다.',
'덮개의 건조, 가장자리·탈형면 노출을 점검한다.',
'급냉을 피하고 양생제의 후속 공정 적합성을 확인한다.',
'양생 종료는 적용 기준·강도·온도·상태로 판단한다.',
'Ⅳ. 균열 구분 및 검사·조치',
None,None,None,None,
'기상·콘크리트 온도·시간·양생 이력을 기록한다.',
'공시체의 목적을 구분하고 지정 방법으로 양생한다.',
'기준 이탈 시 타설 보류·기록 검토·적정 조치한다.',
'균열은 폭·깊이·진행성·원인 확인 후 보수 판단한다.',
'Ⅴ. 결론: 온도·시간·양생 연속성을 함께 관리한다.',
'학습용 기출 변형 답안 / 공식 정답·채점기준 아님',
'참고: KCS 14 20 41:2025, FHWA 양생 자료(본문)'
]]
for n,rr in enumerate(pages):
    for i,s in enumerate(rr):
        if s:row(i,s,13 if i==1 else 11.5)
    tx(132,731,'2',13)
    c.setStrokeColorRGB(G,G,G);c.setLineWidth(1)
    if n==0:
        # Fits within six original writing rows, all authored strokes gray.
        for x,y,w,h,label in [(210,265,170,58,'応결 전: 증발 > 블리딩'.replace('応','응')),(420,265,175,58,'소성수축 위험 증가'),(210,185,170,48,'차광·방풍·미세분무'),(420,185,175,48,'습윤·피복·양생제')]:
            c.rect(x,y,w,h);tx(x+8,y+h/2-4,label,10.5)
        c.line(381,294,418,294);c.line(410,299,418,294);c.line(410,289,418,294)
        c.line(295,265,295,235);c.line(295,209,417,209);c.line(409,214,417,209);c.line(409,204,417,209)
        tx(219,166,'초기 보호 → 표면 상태 확인 → 본 양생 (개념도)',10.5)
    if n==2:
        xs=[202,290,435,605];ys=[453,421,389,357]
        for x in xs:c.line(x,ys[-1],x,ys[0])
        for y in ys:c.line(xs[0],y,xs[-1],y)
        vals=[('소성수축','응결 전 표면 건조','조기 증발 억제'),('건조수축','경화 후 수분 손실','배합·습윤·구속 관리'),('온도균열','온도변형의 구속','온도이력·급냉 관리')]
        for j,vs in enumerate(vals):
            for k,s in enumerate(vs):tx(xs[k]+6,ys[j]-21,s,10)
    c.showPage()
c.save();buf.seek(0);ov=PdfReader(buf);wr=PdfWriter()
readers=[]
for p in ov.pages:
    # A fresh reader prevents merge_page from sharing original indirect content streams.
    source=PdfReader('/Volumes/USB256/기술사/2026기술사 답안지-1교시(안내용)_Qnet원본.pdf')
    readers.append(source)
    page=source.pages[4];page.merge_page(p);wr.add_page(page)
wr.add_metadata({'/Title':TITLE+' - 따라쓰기','/Subject':'학습용 기출 변형. Q-net 원본 작성면 보존. 작성 글씨·표·도식 #B8B8B8.'})
with (OUT/'02일차_서중콘크리트_답안예시_따라쓰기.pdf').open('wb') as f:wr.write(f)
status={'작성일':'2026-10-18','일차':2,'제목':TITLE,'카테고리':{'이름':'토목시공기술사','ID':1406134},'유형':'논술형·기출 변형 학습문제','선정근거':{'기간':'2022~2026 제126~140회','전체문항':465,'직접관련5문항':RELATED,'한계':'포장·단답형 포함 학습용 묶음. 동일 문제 반복횟수·공식 비중 아님. 그룹키워드82건과 구분.'},'출처':SOURCES,'검증':{'기출':'저장된 Q-net 공식 문제지 PDF 및 layout 텍스트에서 회차·교시·번호·문구 대조','기준':'국토부 고시2025-794 개정일 및 CODIL 공식 개정전문·신구대비표 검색색인 확인. 상세PDF 다운로드는503, KCSC동적뷰어는 빈 응답. 적용범위25/30℃만 확인값으로 인용. 미검증35℃·90분 수치는 단정하지 않음.','수치':'25℃ 초과 또는 완료후24시간 내 최고30℃ 초과 예상. 평균기온≠콘크리트타설온도.','PDF':'3쪽. Q-net 원본 index4 작성면 복제·인쇄 요소 보존. 작성요소 RGB184/184/184. 렌더 검토 대기'},'모델':{'실행모델':'현재 런타임 모델 ID/추론수준 검증 수단 없어 미기록','Astra검토':'실시하지 않음. 사용했다고 주장하지 않음'},'공개발행':'상위 작업에서 처리','공개치환':{'{{FIGURE_URL}}':'배포 검증한 JPG 공개 https URL','{{PDF_URL}}':'배포 검증한 PDF 공개 https URL'}}
(OUT/'작성상태.json').write_text(json.dumps(status,ensure_ascii=False,indent=2))
print(json.dumps({'output':str(OUT),'pages':len(wr.pages),'title':TITLE},ensure_ascii=False))
