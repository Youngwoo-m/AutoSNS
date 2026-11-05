from pathlib import Path
import json,html,re,hashlib,datetime
from io import BytesIO
from copy import deepcopy
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader,PdfWriter
import pypdfium2 as pdfium
OUT=Path(__file__).resolve().parent
D=json.loads((OUT/'final-content.json').read_text())
D['problem']=json.loads((OUT/'기출근거.json').read_text())['selected']['question']
TITLE=D['title'];PDF='01일차_강관동바리_답안예시_따라쓰기.pdf';CDN='https://geoai-na.netlify.app/safety-questions/materials/day01/'
QNET='https://www.q-net.or.kr/cst006.do?id=cst00602&artlSeq=5274126&brdId=Q006&gSite=Q'
LAW='https://www.law.go.kr/LSW/lsLinkCommonInfo.do?lsJoLnkSeq=1028543971'
esc=lambda s:html.escape(str(s))
def intro_html():
 parts=[esc(s) for s in D['intro']]
 public_title='Q-net이 2026년 8월 24일 공개한 제140회 건설안전기술사 문제지'
 parts[1]=parts[1].replace(public_title,'<a href="'+QNET+'">'+public_title+'</a>')
 return '\n'.join('<p>'+x+'</p>' for x in parts)
pdfmetrics.registerFont(TTFont('KR','/System/Library/Fonts/Supplemental/AppleGothic.ttf'))
template=Path('/Volumes/USB256/기술사/2026기술사 답안지-1교시(안내용)_Qnet원본.pdf');page=PdfReader(template).pages[4];W,H=float(page.mediabox.width),float(page.mediabox.height)
def wrap(text,size=12,max_width=403):
 out=[];current=''
 for char in text:
  if pdfmetrics.stringWidth(current+char,'KR',size)>max_width and current:
   out.append(current);current='  '+char
  else:current+=char
 if current:out.append(current)
 return out
lines=[]
for text in wrap('강관 동바리 시공 시 사전검토와 조립·해체 안전관리',13):lines.append((text,13))
lines.append(('제140회 제2교시 5번 · 학습용 답안 예시',11))
for idx,section in enumerate(D['answer_sections'],1):
 for t in wrap(str(idx)+'. '+section['title'],13):lines.append((t,13))
 for bullet in section['bullets']:
  for t in wrap('· '+bullet,12):lines.append((t,12))
lines.append(('※ 공식 정답·채점기준이 아닌 학습용 예시임',10))
# 19개 답안선에 맞춰 흐르게 배치. 섹션 소제목이 페이지 맨끝에 혼자 남지 않도록 조정.
chunks=[];chunk=[]
for i,line in enumerate(lines):
 is_header=bool(re.match(r'^[1-6]\. ',line[0]))
 if len(chunk)>=19 or (is_header and len(chunk)>=17):chunks.append(chunk);chunk=[]
 chunk.append(line)
if chunk:chunks.append(chunk)
b=BytesIO();cv=canvas.Canvas(b,pagesize=(W,H));gray=184/255
for n,chunk in enumerate(chunks,1):
 cv.setFillColorRGB(gray,gray,gray)
 for row,(text,size) in enumerate(chunk):cv.setFont('KR',size);cv.drawString(202,764-row*32.35,text)
 cv.setFont('KR',13);cv.drawString(132,731,'5')
 cv.showPage()
cv.save();b.seek(0);overlay=PdfReader(b);writer=PdfWriter()
for i,ov in enumerate(overlay.pages):
 p=deepcopy(PdfReader(template).pages[4]);p.merge_page(ov)
 if i:
  number=BytesIO();c=canvas.Canvas(number,pagesize=(W,H));c.setFillColorRGB(1,1,1);c.rect(574,791,45,45,stroke=0,fill=1);c.setFillColorRGB(.15,.15,.15);c.setFont('KR',12);c.drawString(586,803,f'{i+1}쪽');c.save();number.seek(0);p.merge_page(PdfReader(number).pages[0])
 writer.add_page(p)
writer.add_metadata({'/Title':TITLE+' - 따라쓰기','/Subject':'제140회 제2교시5번 학습용 답안 예시. 작성글씨RGB184/184/184. 원본Qnet답안지보존.'})
with (OUT/PDF).open('wb') as stream:writer.write(stream)
doc=pdfium.PdfDocument(str(OUT/PDF))
for i in range(len(doc)):doc[i].render(scale=1.5).to_pil().save(OUT/f'PDF-{i+1}.png')

def paras(items):return '\n'.join('<p>'+esc(s)+'</p>' for s in items)
def table():
 def cells(row,tag):return '<tr>'+''.join(f'<{tag} style="text-align:center">'+esc(x).replace('\n','<br>')+f'</{tag}>' for x in row)+'</tr>'
 return '<div style="overflow-x:auto"><table border="1" style="width:100%;min-width:650px;border-collapse:collapse">'+cells(D['table']['headers'],'th')+''.join(cells(r,'td') for r in D['table']['rows'])+'</table></div>'
def image(name,alt,blogger):
 if blogger:return '<p style="text-align:center"><img src="'+CDN+name+'" alt="'+esc(alt)+'" style="max-width:100%;height:auto"></p>'
 return '<p data-ax-attach="'+name+'"></p>'
def body(blogger=False):
 pieces=[image('banner.png','거푸집·강관 동바리 타설 전 확인사항',blogger),'<p><small>배너: AI 생성 디오라마(학습용 이미지).</small></p>',intro_html(),'<h2>문제</h2>','<p>2026년 제140회 건설안전기술사 제2교시 5번 · <a href="'+QNET+'">Q-net 공식 문제지</a></p>','<blockquote><p>'+esc(D['problem'])+'</p></blockquote>','<p>논술형 · 25점 · 권장 작성시간 25분</p>','<h2>출제 의도와 답안 방향</h2>','<p>'+esc(D['intent'][0])+'</p><blockquote><p><strong>답안 작성 요령</strong> — '+esc(D['intent'][1])+'</p></blockquote>']
 for i,x in enumerate(D['explanations']):
  pieces+=['<h2>'+esc(x['heading'])+'</h2>',paras(x['paragraphs'])]
  if i==0:pieces+=[image('동바리_단계별확인.png','강관 동바리 사전검토·조립·타설감시·해체검토 순서도',blogger),'<p>검토 단계와 확인 항목을 연결한 학습용 순서도입니다.</p>']
 pieces+=['<h3>동바리 유형과 법령 적용을 구분해요</h3>',table(),'<p>근거: <a href="'+LAW+'">산업안전보건기준에 관한 규칙 제331조~제334조</a>(시행 2026년 3월 2일). 아래 법령 수치는 해당 유형의 조건이며, 구조검토와 조립도에 따른 안전조치를 대신하지 않습니다.</p>','<h2>답안 예시</h2>','<hr>']
 for idx,s in enumerate(D['answer_sections'],1):pieces+=['<h3>'+str(idx)+'. '+esc(s['title'])+'</h3>','<ul>'+''.join('<li>'+esc(v)+'</li>' for v in s['bullets'])+'</ul>']
 pieces+=['<hr>','<h2>놓치기 쉬운 점</h2>','<ul>'+''.join('<li>'+esc(x)+'</li>' for x in D['pitfalls'])+'</ul>','<h2>참고자료와 확인일</h2>','<ul><li><a href="'+QNET+'">Q-net — 제140회 건설안전기술사 공식 문제지</a></li><li><a href="'+LAW+'">국가법령정보센터 — 산업안전보건기준에 관한 규칙(제328조~제334조)</a></li></ul>','<p>자료 확인일: 2026년 10월 31일. '+esc(D['note'])+'</p>','<h2>따라쓰기 PDF</h2>']
 if blogger:pieces+=['<p><a href="'+CDN+PDF+'">1일차 강관 동바리 답안 예시·따라쓰기 PDF 내려받기</a></p>']
 else:pieces+=['<p data-ax-attach="'+PDF+'"></p>']
 pieces+=['<p>Q-net 원본 답안지 작성면에 옅은 회색(#B8B8B8)으로 작성한 '+str(len(doc))+'쪽 자료입니다.</p>','<h2><a href="https://geoai-na.netlify.app/safety-questions/">함께 푸는 [건설안전기술사] 답안지 요청</a></h2>','<p>문제를 요청하시면 접수 순서에 따라 매일 밤 11시에 요청을 확인하고, 답안 예시와 따라쓰기 PDF를 작성해 블로그에 올립니다.</p>']
 return '\n'.join(pieces)
for name,blogger in [('티스토리게시본문.html',False),('Blogger게시본문.html',True)]: (OUT/name).write_text(body(blogger))
(OUT/'미리보기.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(TITLE)+'</title><style>body{font-family:Arial,"AppleGothic",sans-serif;max-width:850px;margin:36px auto;padding:0 20px;line-height:1.9;color:#1d2c3a}h1{font-size:28px}h2{margin-top:38px}th,td{padding:10px}img{max-width:100%}blockquote{border-left:4px solid #4782ab;padding-left:15px}</style><h1>'+esc(TITLE)+'</h1>'+body(True).replace(CDN,'./')+'</html>')
(OUT/'제목.txt').write_text(TITLE+'\n');(OUT/'태그.txt').write_text(','.join(D['tags'])+'\n')
(OUT/'답안예시_줄배치.json').write_text(json.dumps({'pages':[[{'text':t,'font_size':s} for t,s in c] for c in chunks],'gray':'#B8B8B8','template_page_index':4},ensure_ascii=False,indent=2))
(OUT/'작성상태.json').write_text(json.dumps({'day':1,'status':'draft_pending_independent_calc_source_review','title':TITLE,'topic':'거푸집·강관 동바리 사전검토와 처짐·붕괴 예방','question_id':'140-2-5','field':'가설구조물·추락·낙하','selection':'동바리 문자열8문항8회차, 동일유형반복출제빈도아님','source_date':'2026-10-31','model':'Claude Max subscription sonnet, actual model in response modelUsage','humanizer':2,'calc':'pending','review':'pending','pdf_pages':len(doc),'urls':{},'keyword_trend_file':'데이터랩.txt'},ensure_ascii=False,indent=2))
print('outputs built; PDF pages',len(doc),'answer rows',len(lines))
