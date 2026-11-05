from pathlib import Path
import json,html,re
from io import BytesIO
from copy import deepcopy
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader,PdfWriter
import pypdfium2 as pdfium
OUT=Path(__file__).resolve().parent
D=json.loads((OUT/'final-content.json').read_text())
Q=json.loads((OUT/'기출근거.json').read_text())['selected'];D['problem']=Q['question']
TITLE=D['title'];PDF='05일차_비계조립해체_답안예시_따라쓰기.pdf';CDN='https://geoai-na.netlify.app/safety-questions/materials/day05/'
QNET=Q['source']
JO=lambda n:'https://www.law.go.kr/LSW/lsSideInfoP.do?docCls=jo&amp;joBrNo=00&amp;joNo=%04d&amp;lsiSeq=273603&amp;urlMode=lsScJoRltInfoR'%n
BYL5='https://www.law.go.kr/LSW/lsBylInfoPLinkR.do?lsiSeq=273603&amp;lsNm=%EC%82%B0%EC%97%85%EC%95%88%EC%A0%84%EB%B3%B4%EA%B1%B4%EA%B8%B0%EC%A4%80%EC%97%90%EA%B4%80%ED%95%9C%EA%B7%9C%EC%B9%99&amp;bylNo=0005&amp;bylBrNo=00&amp;bylCls=BE&amp;bylEfYd=&amp;bylEfYdYn=Y'
NEWS='http://www.kookje.co.kr/news2011/asp/newsbody.asp?code=0300&amp;key=20261023.22006006673'
esc=lambda s:html.escape(str(s))
pdfmetrics.registerFont(TTFont('KR','/System/Library/Fonts/Supplemental/AppleGothic.ttf'))
template=Path('/Volumes/USB256/기술사/2026기술사 답안지-1교시(안내용)_Qnet원본.pdf');page=PdfReader(template).pages[4];W,H=float(page.mediabox.width),float(page.mediabox.height)
def wrap(text,size=12,max_width=403):
 out=[];cur=''
 for ch in text:
  if pdfmetrics.stringWidth(cur+ch,'KR',size)>max_width and cur:out.append(cur);cur='  '+ch
  else:cur+=ch
 if cur:out.append(cur)
 return out
groups=[]
groups.append([(t,13) for t in wrap('강관비계·시스템비계 조립·해체 시 재해유형과 안전대책, 각각의 설치(조립) 시 준수사항',13)]+[('제139회 제2교시 5번 · 학습용 답안 예시',11)])
for i,s in enumerate(D['answer_sections'],1):
 groups.append([(t,13) for t in wrap(f"{i}. {s['title']}",13)]+['HDR'])
 for b in s['bullets']:groups.append([(t,12) for t in wrap('· '+b,12)])
groups.append([('※ 공식 정답·채점기준이 아닌 학습용 예시임',10)])
lines=[x for g in groups for x in g if x!='HDR']
chunks=[];chunk=[]
for gi,g in enumerate(groups):
 hdr='HDR' in g;g=[x for x in g if x!='HDR']
 need=len(g)+(len(groups[gi+1]) if hdr and gi+1<len(groups) else 0)
 if len(chunk)+need>21:chunks.append(chunk);chunk=[]
 chunk+=g
if chunk:chunks.append(chunk)
b=BytesIO();cv=canvas.Canvas(b,pagesize=(W,H));g=184/255
for chunk in chunks:
 cv.setFillColorRGB(g,g,g)
 for r,(t,sz) in enumerate(chunk):cv.setFont('KR',sz);cv.drawString(202,764-r*32.35,t)
 cv.setFont('KR',13);cv.drawString(132,731,'2')
 cv.showPage()
cv.save();b.seek(0);ov=PdfReader(b);w=PdfWriter()
for i,o in enumerate(ov.pages):
 p=deepcopy(PdfReader(template).pages[4]);p.merge_page(o)
 if i:
  nb=BytesIO();c=canvas.Canvas(nb,pagesize=(W,H));c.setFillColorRGB(1,1,1);c.rect(574,791,45,45,stroke=0,fill=1);c.setFillColorRGB(.15,.15,.15);c.setFont('KR',12);c.drawString(586,803,f'{i+1}쪽');c.save();nb.seek(0);p.merge_page(PdfReader(nb).pages[0])
 w.add_page(p)
w.add_metadata({'/Title':TITLE+' - 따라쓰기','/Subject':'제139회 제2교시5번 학습용 답안 예시. 작성글씨 RGB184/184/184. 원본 Q-net 답안지 보존.'})
with (OUT/PDF).open('wb') as fh:w.write(fh)
doc=pdfium.PdfDocument(str(OUT/PDF))
for i in range(len(doc)):doc[i].render(scale=1.5).to_pil().save(OUT/f'PDF-{i+1}.png')
def paras(xs):return '\n'.join('<p>'+esc(x)+'</p>' for x in xs)
def table(t):
 cells=lambda row,tag:'<tr>'+''.join(f'<{tag} style="text-align:center">'+esc(x)+f'</{tag}>' for x in row)+'</tr>'
 return '<div style="overflow-x:auto"><table border="1" style="width:100%;min-width:600px;border-collapse:collapse">'+cells(t['headers'],'th')+''.join(cells(r,'td') for r in t['rows'])+'</table></div>'
def image(name,alt,bl):
 if bl:return '<p style="text-align:center"><img src="'+CDN+name+'" alt="'+esc(alt)+'" style="max-width:100%;height:auto"></p>'
 return '<p data-ax-attach="'+name+'"></p>'
def body(bl=False):
 P=[image('banner.png','비계 조립·해체 안전, 강관비계와 시스템비계 설치 준수사항 비교',bl),'<p><small>배너: AI 생성 디오라마 배경(학습용 이미지).</small></p>',paras(D['intro']),
 '<p><small>글머리 근거: <a href="'+NEWS+'">국제신문 「공공 건설현장인데…추락 안전망 없고 감독 태만 부지기수」</a>(2026년 10월 22일, 2026년 11월 3일 확인).</small></p>',
 '<h2>문제</h2>','<p>2026년 제139회 건설안전기술사 제2교시 5번 · <a href="'+QNET+'">Q-net 공식 문제지</a></p>','<blockquote><p>'+esc(D['problem'])+'</p></blockquote>','<p>논술형 · 25점 · 권장 작성시간 25분</p>',
 '<h2>출제 의도와 답안 방향</h2>','<p>'+esc(D['intent'][0])+'</p><p>'+esc(D['intent'][1])+'</p><blockquote><p><strong>답안 작성 요령</strong> — '+esc(D['intent'][2])+'</p></blockquote>']
 for i,x in enumerate(D['explanations']):
  P+=['<h2>'+esc(x['heading'])+'</h2>',paras(x['paragraphs'][:1])]
  if i==0:P+=[table(D['hazard_table'])]
  P+=[paras(x['paragraphs'][1:])]
  if i==1:P+=[image('강관비계_구조기준.png','강관비계 구조 기준 그림: 기둥 간격 띠장 방향 1.85m·장선 방향 1.5m 이하, 띠장 간격 2.0m 이하, 제일 윗부분에서 31m 아래 기둥은 2개 강관, 기둥 간 적재하중 400kg, 벽이음 단관 5m·틀비계 6m×8m',bl),'<p style="text-align:center"><small>강관비계 구조 기준 개념도(산업안전보건기준에 관한 규칙 제59·60조, 별표 5).</small></p>',image('별표5_화면.png','산업안전보건기준에 관한 규칙 별표 5 강관비계의 조립간격 표: 단관비계 수직 5m 수평 5m, 틀비계(높이 5m 미만 제외) 수직 6m 수평 8m',bl),'<p style="text-align:center"><small>별표 5 원문(국가법령정보센터, 2026년 11월 3일 확인).</small></p>','<h3>31m는 어디서부터 재나요</h3>','<p>'+esc(D['calc_intro'])+'</p>',table(D['calc_table']),'<p>'+esc(D['calc_after'])+'</p>']
  if i==2:P+=['<h3>강관비계와 시스템비계, 나란히 놓고 보기</h3>',table(D['compare_table'])]
 P+=['<h2>답안 예시</h2>','<hr>']
 for i,s in enumerate(D['answer_sections'],1):P+=['<h3>'+str(i)+'. '+esc(s['title'])+'</h3>','<ul>'+''.join('<li>'+esc(v)+'</li>' for v in s['bullets'])+'</ul>']
 P+=['<hr>','<h2>놓치기 쉬운 점</h2>','<ul>'+''.join('<li>'+esc(x)+'</li>' for x in D['pitfalls'])+'</ul>','<h2>참고자료와 확인일</h2>',
 '<ul><li><a href="'+QNET+'">Q-net — 2026년 제139회 건설안전기술사 공식 문제지</a></li>'
 '<li>국가법령정보센터 — 산업안전보건기준에 관한 규칙 <a href="'+JO(13)+'">제13조(안전난간)</a> · <a href="'+JO(14)+'">제14조(낙하물)</a> · <a href="'+JO(55)+'">제55조</a> · <a href="'+JO(56)+'">제56조(작업발판의 구조)</a> · <a href="'+JO(57)+'">제57조(비계 등의 조립·해체 및 변경)</a> · <a href="'+JO(58)+'">제58조(비계의 점검 및 보수)</a></li>'
 '<li><a href="'+JO(59)+'">제59조(강관비계 조립 시의 준수사항)</a> · <a href="'+JO(60)+'">제60조(강관비계의 구조)</a> · <a href="'+JO(62)+'">제62조(강관틀비계)</a> · <a href="'+JO(68)+'">제68조(이동식비계)</a> · <a href="'+JO(69)+'">제69조(시스템 비계의 구조)</a> · <a href="'+JO(70)+'">제70조(시스템비계의 조립 작업 시 준수사항)</a> · <a href="'+BYL5+'">별표 5(강관비계의 조립간격)</a></li>'
 '<li><a href="'+NEWS+'">국제신문(2026. 10. 22.) — 부산시 감사위원회 중소규모 공공 건설현장 감사 결과</a></li></ul>',
 '<p>법령 기준: 산업안전보건기준에 관한 규칙(국가법령정보센터 현행 표시: 시행 2026. 3. 2., 고용노동부령 제450호). 비계 관련 조문은 제59조·제60조·제13조 2023. 11. 14. 개정, 제55조 2024. 6. 28. 전문개정이 반영된 현행 조문으로 확인했어요. 자료 확인일: 2026년 11월 3일. '+esc(D['note'])+'</p>','<h2>따라쓰기 PDF</h2>']
 P+=['<p><a href="'+CDN+PDF+'">5일차 비계 조립·해체 답안 예시·따라쓰기 PDF 내려받기</a></p>'] if bl else ['<p data-ax-attach="'+PDF+'"></p>']
 P+=['<p>Q-net 원본 답안지 작성면에 옅은 회색으로 작성한 '+str(len(doc))+'쪽 자료입니다.</p>','<h2><a href="https://geoai-na.netlify.app/safety-questions/">함께 푸는 [건설안전기술사] 답안지 요청</a></h2>','<p>문제를 요청하시면 접수 순서에 따라 매일 밤 11시에 요청을 확인하고, 정답예시와 따라쓰기 PDF를 작성해 블로그에 올립니다.</p>']
 return '\n'.join(P)
for n,bl in [('티스토리게시본문.html',False),('Blogger게시본문.html',True)]:(OUT/n).write_text(body(bl))
(OUT/'미리보기.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><title>'+esc(TITLE)+'</title><style>body{font-family:AppleGothic,sans-serif;max-width:850px;margin:36px auto;padding:0 20px;line-height:1.9}th,td{padding:8px}img{max-width:100%}blockquote{border-left:4px solid #4782ab;padding-left:15px}</style><h1>'+esc(TITLE)+'</h1>'+body(True).replace(CDN,'./')+'</html>')
(OUT/'제목.txt').write_text(TITLE+'\n');(OUT/'태그.txt').write_text(','.join(D['tags'])+'\n')
(OUT/'답안예시_줄배치.json').write_text(json.dumps({'pages':[[{'text':t,'font_size':s} for t,s in c] for c in chunks],'gray':'#B8B8B8','template_page_index':4},ensure_ascii=False,indent=2))
print('PDF pages',len(doc),'rows',len(lines))
