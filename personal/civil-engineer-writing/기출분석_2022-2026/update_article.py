"""Insert evidence-backed analysis into the existing introduction article."""
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
POST = ROOT.parent/'첫글_준비하기'
stats = json.loads((ROOT/'키워드집계.json').read_text())
sources = json.loads((ROOT/'회차목록.json').read_text())
questions = {q['id']: q for q in json.loads((ROOT/'전체465문항.json').read_text())}

def table(headers, rows):
    return '<div style="overflow-x:auto"><table border="1" style="border-collapse:collapse;width:100%;min-width:580px"><thead><tr>'+''.join('<th>'+h+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(c)+'</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table></div>'

def example(qid, description):
    q=questions[qid]
    return f'<a href="{html.escape(q["source"],quote=True)}" target="_blank" rel="noopener">{q["year"]}년 제{q["round"]}회 제{q["period"]}교시 {q["number"]}번</a>: {description}'

annual=[]
for year in range(2022,2027):
    year_sources=sorted([r for r in sources if r['year']==year],key=lambda r:r['round'])
    links=' · '.join(f'<a href="{html.escape(r["url"],quote=True)}" target="_blank" rel="noopener">제{r["round"]}회</a>' for r in year_sources)
    annual.append([year,links,39,54,93])
theme_rows=[]
for item in stats['themes']:
    theme_rows.append([item['theme'],*[item['by_year'][str(y)] for y in range(2022,2027)],f'<strong>{item["count"]}</strong>',f'{item["round_count"]}/15회'])
request_rows=[[i['name'],i['count'],f'{i["count"]/270*100:.1f}%'] for i in stats['essay_requests']]
rules=''.join(f'<li><strong>{i["theme"]}:</strong> {html.escape(i["rule"])}</li>' for i in stats['themes'])
request_rules=''.join(f'<li><strong>{i["name"]}:</strong> {html.escape(i["rule"])}</li>' for i in stats['essay_requests'])

section='''<section id="five-year-analysis">
<h2>4. 최근 5년 기출문제 유형 분석: 2022~2026년 465문항</h2>
<p>2026년 10월 17일을 기준으로 최신 필기시험을 포함한 <strong>2022~2026년, 제126~140회 토목시공기술사 공식 문제지 15회분</strong>을 분석했습니다. ‘최근 5년’은 2021~2025년이 아닌 이 기간을 뜻합니다. 문제지 게시 날짜를 시험 시행일로 사용하지 않았습니다.</p>
<p>집계 단위는 <strong>문제지의 문항 번호 1개</strong>입니다. 한 문항 안의 여러 요구사항을 따로 세지 않았으며, 수험생이 선택하여 작성한 답안이 아니라 <strong>출제된 전체 문항</strong>을 셌습니다.</p>
'''+table(['시행연도','큐넷 공식 문제지','제1교시','제2~4교시','연간 합계'],annual)+'''
<h3>교시별로 요구되는 답안의 길이가 다릅니다</h3>
'''+table(['구분','회차당 출제·선택','5년 출제 문항','학습 초점'],[
    ['제1교시 · 단답형','13문제 중 10문제 선택, 각 10점','195문항 · 41.9%','정의·원리·특징·핵심 관리항목을 짧고 정확하게'],
    ['제2~4교시 · 논술형','각 교시 6문제 중 4문제 선택, 각 25점','270문항 · 58.1%','질문의 여러 요구를 목차로 나누고 현장 조건·절차·대책까지 연결'],
])+'''
<p>15회 모두 <strong>13+6+6+6=31문항</strong>의 구성이었습니다. 195+270=465문항이며, 매년 3회·93문항입니다. 위 비율은 출제 문항 수의 구성비로, 배점 비중이나 학습시간 배분 비율을 뜻하지 않습니다.</p>
<h3>논술형은 ‘무엇을 설명하라는가’를 나눠 읽어보세요</h3>
<p>논술형 270문항에서 다음 표현이 포함된 문항 수를 별도로 집계했습니다. 한 문항에 원인·대책과 시공 유의사항이 함께 나올 수 있으므로 유형끼리 중복됩니다. 표에 없는 요구형도 있으며, 아래 수치는 전체 논술형을 빠짐없이 분류한 결과가 아닙니다.</p>
'''+table(['질문의 요구 표현','해당 문항 수','논술형 270문항 대비'],request_rows)+'''
<p>예를 들어 ‘원인·대책 요구’는 원인 또는 대책이라는 표현이 있는 문항을 셌습니다. 이 표현을 모두 함께 요구한 문항만을 뜻하지 않습니다. 이를 답안 연습에 적용하면 <strong>개념을 아는 것에 더해 왜 문제가 발생하는지, 현장에서 어떤 순서로 확인하고 조치할지</strong>까지 쓰는 연습이 필요하다는 해석이 가능합니다.</p>

<h2>5. 주제별 반복 출제는 어떻게 나타났을까요?</h2>
<p>아래 표는 문항 원문에 지정한 키워드가 포함되어 있는지 확인한 <strong>주제별 키워드 집계</strong>입니다. 예를 들어 교량 콘크리트 시공 문항은 교량과 콘크리트 두 그룹에 함께 포함됩니다. 키워드로 표현되지 않은 관련 문항은 빠질 수 있으므로, <strong>공종별 공식 출제 비중·배타적 분류·빈출 순위</strong>로 해석하지 않습니다.</p>
'''+table(['키워드 그룹','2022','2023','2024','2025','2026','합계','포함된 회차'],theme_rows)+'''
<p><strong>읽는 방법:</strong> 콘크리트·거푸집·양생 그룹의 82문항은 해당 검색어 중 하나 이상을 포함한 문항 수입니다. 15/15회는 매 회차에 적어도 한 문항이 있었다는 뜻이며, 한 회차에서 그만큼 많은 배점이 배정됐다는 의미는 아닙니다.</p>

<h2>6. 출제 경향을 준비 전략으로 연결해보세요</h2>
<h3>① 기본 공종은 매년 반복해서 다뤄집니다</h3>
<p>콘크리트 관련 그룹은 82문항, 지반·기초·흙막이 그룹은 64문항으로 집계됐고 두 그룹 모두 15회 전 회차에서 확인됐습니다. 신기술만 따로 공부하기보다 재료·기초 원리와 시공·품질관리의 기본 답안부터 갖춰두는 전략을 제안합니다. 이는 키워드 집계와 문항 내용을 바탕으로 한 학습 제안입니다.</p>
<h3>② 같은 주제도 현장 조건과 관리 대책을 바꿔 묻습니다</h3>
<ul><li>'''+example('126-2-5','시공 중 콘크리트 균열의 원인과 방지대책')+'''</li>
<li>'''+example('132-2-6','동절기 콘크리트의 배합과 시공관리')+'''</li>
<li>'''+example('139-4-5','하절기 타설의 문제점과 관리대책')+'''</li>
<li>'''+example('140-3-4','고온 환경이 콘크리트에 미치는 영향과 단계별 관리')+'''</li></ul>
<p>용어별 답안을 외운 뒤에는 <strong>계절·지하수·지반 상태·주변 구조물·공간 제약</strong>을 바꿔 생각해보세요. 위 사례에서는 ‘콘크리트’라는 공통 주제 안에서도 요구하는 조건과 범위가 달라집니다.</p>
<h3>③ 상하수도와 시설물 관리도 함께 준비할 필요가 있습니다</h3>
<p>상하수도·관로 그룹은 연도별 <strong>5→7→4→9→12문항</strong>, 유지관리·노후·갱생 그룹은 <strong>4→4→1→5→9문항</strong>이었습니다. 두 그룹 모두 이 분석 기간에서는 2026년의 집계가 가장 많았습니다. 다만 해마다 꾸준히 늘어난 것은 아니며, 이 5개년 수치로 다음 시험의 증가를 예측하지는 않습니다.</p>
<ul><li>'''+example('128-4-6','노후 상수관의 문제점과 관로 상황별 갱생')+'''</li>
<li>'''+example('137-3-4','하수관로 갱생공법과 선정 조건')+'''</li>
<li>'''+example('139-4-4','노후 하수관로의 상태평가와 개·보수공법 선정')+'''</li>
<li>'''+example('140-2-2','노후 교량받침의 보수·교체 절차와 유의사항')+'''</li></ul>
<p>신설 공사의 시공순서뿐 아니라 <strong>상태 확인 → 원인 판단 → 보수·갱생공법 선정 → 시공·검증</strong>으로 이어지는 답안도 연습해보세요.</p>
<h3>④ 스마트기술은 기존 공종의 적용 문제와 연결됩니다</h3>
<p>스마트·디지털 그룹은 총 <strong>15문항, 11개 회차</strong>에서 확인됐습니다. 연도별 수치는 <strong>1→5→3→3→3문항</strong>으로, 매년 증가했다는 해석은 맞지 않습니다. 대신 실제 문항에서 어떤 시공·관리 업무에 적용하도록 묻는지를 살펴볼 만합니다.</p>
<ul><li>'''+example('129-2-1','지반굴착 안전관리에 스마트계측 활용')+'''</li>
<li>'''+example('137-4-6','관로시설의 토목 BIM 모델')+'''</li>
<li>'''+example('139-2-3','지능형 다짐의 시공·관리기준·검사')+'''</li>
<li>'''+example('140-3-6','데이터센터 토목공사 특성과 스마트건설 사업관리')+'''</li></ul>
<p>기술 명칭을 나열하기보다 <strong>적용 목적·필요한 데이터·현장 적용 절차·확인할 성능·한계</strong>를 연결하여 정리하는 방법을 제안합니다.</p>
<h3>분석을 반영한 학습 순서</h3>
<ol><li><strong>기본 답안:</strong> 콘크리트, 토공, 기초 등에서 정의·원리·관리항목을 먼저 정리합니다.</li><li><strong>조건별 응용:</strong> 원인·대책과 시공 유의사항을 현장 조건에 맞게 바꿔 씁니다.</li><li><strong>범위 확장:</strong> 상하수도·유지관리·스마트기술을 기존 공종과 연결합니다.</li><li><strong>실전 확인:</strong> 단답형과 논술형을 함께 연습하며 선택 문항 수와 교시 시간을 적용합니다.</li></ol>
<details><summary>집계 방법과 검색 규칙 보기</summary>
<p>공식 PDF의 각 페이지에서 문항 번호를 추출하고, 제1교시 1~13번과 나머지 교시 1~6번이 모두 있는지 확인했습니다. 검색 전 공백을 제거하고 영문 대소문자를 구분하지 않았습니다. 동일 그룹의 단어가 한 문항에 여러 번 있어도 그 그룹에서는 1문항으로 셉니다. ‘|’는 또는을 뜻합니다.</p>
<ul>'''+rules+'''</ul><p>논술형 요구 표현의 검색 규칙은 다음과 같습니다. 실제 의미상 모든 원인·대책형이나 비교형을 포괄하는 자동 분류는 아닙니다.</p><ul>'''+request_rules+'''</ul>
<p>공식 문제지 15개, 문항별 원문·출처·회차를 담은 465행 CSV/JSON, 검색 규칙과 일치 문항 ID를 담은 집계 JSON을 별도로 보존했습니다. 이 분석은 학습을 위한 자체 분석이며 한국산업인력공단의 공식 통계나 출제 예고가 아닙니다.</p></details>
</section>
'''

body=(POST/'게시본문.html').read_text()
start=body.find('<section id="five-year-analysis">')
if start>=0:
    end=body.index('</section>',start)+len('</section>')
    body=body[:start]+body[end:]
else:
    body=re.sub(r'<h2>([4-7])\. ',lambda m:f'<h2>{int(m[1])+3}. ',body)
anchor='<h2>7. 공부 범위를 작은 단위로 나눠보세요</h2>'
assert anchor in body
body=body.replace(anchor,section+'\n'+anchor)
old='이 글에서는 준비에 필요한 자료와 학습 순서, 하루 한 문제를 활용하는 방법을 정리합니다.'
body=body.replace(old,'이 글에서는 준비에 필요한 자료와 학습 순서, 최근 5년(2022~2026년) 465문항의 유형·주제별 집계와 출제 경향, 하루 한 문제를 활용하는 방법을 정리합니다.')
(POST/'게시본문.html').write_text(body)
preview=(POST/'블로그미리보기.html').read_text()
pos=preview.index('</h1>')+len('</h1>')
preview=preview[:pos]+body+'</body></html>'
(POST/'블로그미리보기.html').write_text(preview)
status=json.loads((POST/'작성상태.json').read_text())
status['기출분석']={'기간':'2022~2026','회차':'제126~140회','공식문제지':15,'전체문항':465,'단답형':195,'논술형':270,'방식':'문항번호 검증 및 중복 허용 키워드 집계','집계규칙과일치문항':'../기출분석_2022-2026/키워드집계.json'}
(POST/'작성상태.json').write_text(json.dumps(status,ensure_ascii=False,indent=2))
print('Updated introduction: three analysis sections, 15 official source links, 465-question corpus')
