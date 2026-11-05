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
TITLE=D['title'];PDF='06일차_해체작업사전조사_답안예시_따라쓰기.pdf';CDN='https://geoai-na.web.app/safety-questions/materials/day06/'
QNET=Q['source']
JO=lambda n:'https://www.law.go.kr/LSW/lsSideInfoP.do?docCls=jo&amp;joBrNo=00&amp;joNo=%04d&amp;lsiSeq=273603&amp;urlMode=lsScJoRltInfoR'%n
BYL5='https://www.law.go.kr/LSW/lsBylInfoPLinkR.do?lsiSeq=273603&amp;lsNm=%EC%82%B0%EC%97%85%EC%95%88%EC%A0%84%EB%B3%B4%EA%B1%B4%EA%B8%B0%EC%A4%80%EC%97%90%EA%B4%80%ED%95%9C%EA%B7%9C%EC%B9%99&amp;bylNo=0005&amp;bylBrNo=00&amp;bylCls=BE&amp;bylEfYd=&amp;bylEfYdYn=Y'
NEWS='https://www.yna.co.kr/view/AKR20261102156500057'
BJ=lambda n:'https://www.law.go.kr/LSW/lsSideInfoP.do?docCls=jo&amp;joBrNo=00&amp;joNo=%04d&amp;lsiSeq=266691&amp;urlMode=lsScJoRltInfoR'%n
BR12='https://www.law.go.kr/LSW/lsSideInfoP.do?docCls=jo&amp;joBrNo=00&amp;joNo=0012&amp;lsiSeq=271531&amp;urlMode=lsScJoRltInfoR'
BYL4=BYL5.replace('bylNo=0005','bylNo=0004')
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
groups.append([(t,13) for t in wrap('건축물 등 해체작업 시 붕괴 예방을 위한 사전조사·작업계획서 내용과 안전관리 방안',13)]+[('제138회 제3교시 2번 · 학습용 답안 예시',11)])
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
w.add_metadata({'/Title':TITLE+' - 따라쓰기','/Subject':'제138회 제3교시2번 학습용 답안 예시. 작성글씨 RGB184/184/184. 원본 Q-net 답안지 보존.'})
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
 P=[image('banner.png','철거·해체공사 붕괴 예방, 사전조사와 작업계획서 내용 배너',bl),'<p><small>배너: AI 생성 디오라마 배경(학습용 이미지).</small></p>',paras(D['intro']),
 '<p><small>글머리 근거: <a href="'+NEWS+'">연합뉴스 「[울산화력 참사 1년] ③조사결과 도출까지 꼬박 1년…구조물 해체 안전망 공백 여전」</a>(2026년 11월 3일 송고, 2026년 11월 5일 확인).</small></p>',
 '<h2>문제</h2>','<p>2026년 제138회 건설안전기술사 제3교시 2번 · <a href="'+QNET+'">Q-net 공식 문제지</a></p>','<blockquote><p>'+esc(D['problem'])+'</p></blockquote>','<p>논술형 · 25점 · 권장 작성시간 25분</p>',
 '<h2>출제 의도와 답안 방향</h2>','<p>'+esc(D['intent'][0])+'</p><p>'+esc(D['intent'][1])+'</p><blockquote><p><strong>답안 작성 요령</strong> — '+esc(D['intent'][2])+'</p></blockquote>']
 for i,x in enumerate(D['explanations']):
  P+=['<h2>'+esc(x['heading'])+'</h2>',paras(x['paragraphs'][:1])]
  if i==0:P+=[table(D['law_table'])]
  P+=[paras(x['paragraphs'][1:])]
  if i==1:P+=['<h3>작업계획서 7개 항목과 확인점</h3>',table(D['plan_table']),image('해체작업_붕괴예방흐름.png','철거·해체공사 붕괴 예방 흐름도: 사전조사, 계획 수립, 작업 중 관리, 이상 시 조치 단계별 산업안전보건법령(기준규칙 제38·39·52·384조, 별표 4)과 건축물관리법(제30~32조, 시행규칙 제12조) 의무',bl),'<p style="text-align:center"><small>해체작업 붕괴 예방 흐름(산업안전보건기준에 관한 규칙·건축물관리법 조문을 바탕으로 한 학습용 정리).</small></p>']
  if i==2:P+=['<h3>허가일까 신고일까, 가상 건축물로 판정해 보기</h3>','<p>'+esc(D['check_intro'])+'</p>',table(D['check_table']),'<p>'+esc(D['check_after'])+'</p>']
 P+=['<h2>답안 예시</h2>','<hr>']
 for i,s in enumerate(D['answer_sections'],1):P+=['<h3>'+str(i)+'. '+esc(s['title'])+'</h3>','<ul>'+''.join('<li>'+esc(v)+'</li>' for v in s['bullets'])+'</ul>']
 P+=['<hr>','<h2>놓치기 쉬운 점</h2>','<ul>'+''.join('<li>'+esc(x)+'</li>' for x in D['pitfalls'])+'</ul>','<h2>참고자료와 확인일</h2>',
 '<ul><li><a href="'+QNET+'">Q-net — 2026년 제138회 건설안전기술사 공식 문제지</a></li>'
 '<li>국가법령정보센터 — 산업안전보건기준에 관한 규칙 <a href="'+JO(38)+'">제38조(사전조사 및 작업계획서의 작성 등)</a> · <a href="'+JO(39)+'">제39조(작업지휘자의 지정)</a> · <a href="'+JO(52)+'">제52조(구축물등의 안전성 평가)</a> · <a href="'+JO(384)+'">제384조(해체작업 시 준수사항)</a> · <a href="'+BYL4+'">별표 4(사전조사 및 작업계획서 내용)</a></li>'
 '<li>국가법령정보센터 — 건축물관리법 <a href="'+BJ(30)+'">제30조(건축물 해체의 허가)</a> · <a href="'+BJ(31)+'">제31조(건축물 해체공사감리자의 지정 등)</a> · <a href="'+BJ(32)+'">제32조(해체공사감리자의 업무 등)</a> · 같은 법 시행규칙 <a href="'+BR12+'">제12조(해체계획서의 작성)</a></li>'
 '<li><a href="'+NEWS+'">연합뉴스(2026. 11. 3.) — 울산화력 참사 1년, 구조물 해체 안전제도 개선 현황</a></li></ul>',
 '<p>법령 기준: 산업안전보건기준에 관한 규칙(시행 2026. 3. 2., 고용노동부령 제450호, 별표 4는 2025. 9. 1. 개정본), 건축물관리법(시행 2025. 6. 4., 법률 제20549호), 건축물관리법 시행규칙(시행 2025. 6. 2., 국토교통부령 제1495호). 제384조 제2항(구조보강계획)은 2023. 11. 14. 신설, 건축물관리법 제30조 제4~6항은 2022. 2. 3. 신설 조문이에요. 자료 확인일: 2026년 11월 5일. '+esc(D['note'])+'</p>','<h2>따라쓰기 PDF</h2>']
 P+=['<p><a href="'+CDN+PDF+'">6일차 해체작업 사전조사·작업계획서 답안 예시·따라쓰기 PDF 내려받기</a></p>'] if bl else ['<p data-ax-attach="'+PDF+'"></p>']
 P+=['<p>Q-net 원본 답안지 작성면에 옅은 회색으로 작성한 '+str(len(doc))+'쪽 자료입니다.</p>','<h2><a href="https://geoai-na.web.app/safety-questions/">함께 푸는 [건설안전기술사] 답안지 요청</a></h2>','<p>문제를 요청하시면 접수 순서에 따라 매일 밤 11시에 요청을 확인하고, 정답예시와 따라쓰기 PDF를 작성해 블로그에 올립니다.</p>']
 return '\n'.join(P)
for n,bl in [('티스토리게시본문.html',False),('Blogger게시본문.html',True)]:(OUT/n).write_text(body(bl))
(OUT/'미리보기.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><title>'+esc(TITLE)+'</title><style>body{font-family:AppleGothic,sans-serif;max-width:850px;margin:36px auto;padding:0 20px;line-height:1.9}th,td{padding:8px}img{max-width:100%}blockquote{border-left:4px solid #4782ab;padding-left:15px}</style><h1>'+esc(TITLE)+'</h1>'+body(True).replace(CDN,'./')+'</html>')
(OUT/'제목.txt').write_text(TITLE+'\n');(OUT/'태그.txt').write_text(','.join(D['tags'])+'\n')
(OUT/'답안예시_줄배치.json').write_text(json.dumps({'pages':[[{'text':t,'font_size':s} for t,s in c] for c in chunks],'gray':'#B8B8B8','template_page_index':4},ensure_ascii=False,indent=2))
print('PDF pages',len(doc),'rows',len(lines))
