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
TITLE=D['title'];PDF='03일차_굴착면기울기_답안예시_따라쓰기.pdf';CDN='https://geoai-na.netlify.app/safety-questions/materials/day03/'
QNET=Q['source']
JO=lambda n:'https://www.law.go.kr/LSW/lsSideInfoP.do?docCls=jo&amp;joBrNo=00&amp;joNo=%04d&amp;lsiSeq=273603&amp;urlMode=lsScJoRltInfoR'%n
BYL=lambda n:'https://www.law.go.kr/LSW/lsBylInfoPLinkR.do?lsiSeq=273603&amp;lsNm=%EC%82%B0%EC%97%85%EC%95%88%EC%A0%84%EB%B3%B4%EA%B1%B4%EA%B8%B0%EC%A4%80%EC%97%90%EA%B4%80%ED%95%9C%EA%B7%9C%EC%B9%99&amp;bylNo=NNNN&amp;bylBrNo=00&amp;bylCls=BE&amp;bylEfYd=&amp;bylEfYdYn=Y'.replace('NNNN','%04d'%n)
NEWS='https://www.yna.co.kr/view/AKR20261016147300530'
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
lines=[]
for t in wrap('굴착면 기울기 기준, 사전조사, 붕괴재해 예방대책',13):lines.append((t,13))
lines.append(('제139회 제3교시 5번 · 학습용 답안 예시',11))
for i,s in enumerate(D['answer_sections'],1):
 for t in wrap(f"{i}. {s['title']}",13):lines.append((t,13))
 for b in s['bullets']:
  for t in wrap('· '+b,12):lines.append((t,12))
lines.append(('※ 공식 정답·채점기준이 아닌 학습용 예시임',10))
chunks=[];chunk=[]
for line in lines:
 hdr=bool(re.match(r'^[1-6]\. ',line[0]))
 if len(chunk)>=19 or (hdr and len(chunk)>=17):chunks.append(chunk);chunk=[]
 chunk.append(line)
if chunk:chunks.append(chunk)
b=BytesIO();cv=canvas.Canvas(b,pagesize=(W,H));g=184/255
for chunk in chunks:
 cv.setFillColorRGB(g,g,g)
 for r,(t,sz) in enumerate(chunk):cv.setFont('KR',sz);cv.drawString(202,764-r*32.35,t)
 cv.setFont('KR',13);cv.drawString(132,731,'5')
 cv.showPage()
cv.save();b.seek(0);ov=PdfReader(b);w=PdfWriter()
for i,o in enumerate(ov.pages):
 p=deepcopy(PdfReader(template).pages[4]);p.merge_page(o)
 if i:
  nb=BytesIO();c=canvas.Canvas(nb,pagesize=(W,H));c.setFillColorRGB(1,1,1);c.rect(574,791,45,45,stroke=0,fill=1);c.setFillColorRGB(.15,.15,.15);c.setFont('KR',12);c.drawString(586,803,f'{i+1}쪽');c.save();nb.seek(0);p.merge_page(PdfReader(nb).pages[0])
 w.add_page(p)
w.add_metadata({'/Title':TITLE+' - 따라쓰기','/Subject':'제139회 제3교시5번 학습용 답안 예시. 작성글씨 RGB184/184/184. 원본 Q-net 답안지 보존.'})
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
 P=[image('banner.png','굴착면 기울기 기준과 붕괴 예방',bl),'<p><small>배너: AI 생성 디오라마 배경(학습용 이미지).</small></p>',paras(D['intro']),
 '<p><small>글머리 근거: <a href="'+NEWS+'">연합뉴스 「노동장관, 부산 건축 현장 불시방문 “비탈면 붕괴 예방 미흡”」</a>(2026년 10월 16일, 2026년 11월 1일 확인).</small></p>',
 '<h2>문제</h2>','<p>2026년 제139회 건설안전기술사 제3교시 5번 · <a href="'+QNET+'">Q-net 공식 문제지</a></p>','<blockquote><p>'+esc(D['problem'])+'</p></blockquote>','<p>논술형 · 25점 · 권장 작성시간 25분</p>',
 '<h2>출제 의도와 답안 방향</h2>','<p>'+esc(D['intent'][0])+'</p><blockquote><p><strong>답안 작성 요령</strong> — '+esc(D['intent'][1])+'</p></blockquote>']
 for i,x in enumerate(D['explanations']):
  P+=['<h2>'+esc(x['heading'])+'</h2>',paras(x['paragraphs'])]
  if i==0:P+=[image('굴착면기울기_단면도.png','지반 종류별 굴착면 기울기 단면도: 높이 3.0m일 때 모래 5.4m, 연암 및 풍화암 3.0m, 경암 1.5m, 그 밖의 흙 3.6m',bl),'<p style="text-align:center"><small>굴착면 기울기 단면 개략도(네 단면 모두 같은 축척).</small></p>','<h3>굴착면 기울기로 수평거리 계산해 보기</h3>','<p>'+esc(D['calc_intro'])+'</p>',table(D['calc_table']),'<p>'+esc(D['calc_after'])+'</p>','<p>근거: <a href="'+BYL(11)+'">산업안전보건기준에 관한 규칙 별표 11</a>(개정 2023. 11. 14.), <a href="'+JO(339)+'">제339조</a>.</p>']
 P+=['<h3>조문과 답안 위치를 맞춰 보면</h3>',table(D['table']),'<h2>답안 예시</h2>','<hr>']
 for i,s in enumerate(D['answer_sections'],1):P+=['<h3>'+str(i)+'. '+esc(s['title'])+'</h3>','<ul>'+''.join('<li>'+esc(v)+'</li>' for v in s['bullets'])+'</ul>']
 P+=['<hr>','<h2>놓치기 쉬운 점</h2>','<ul>'+''.join('<li>'+esc(x)+'</li>' for x in D['pitfalls'])+'</ul>','<h2>참고자료와 확인일</h2>',
 '<ul><li><a href="'+QNET+'">Q-net — 2026년 제139회 건설안전기술사 공식 문제지</a></li>'
 '<li><a href="'+JO(38)+'">국가법령정보센터 — 산업안전보건기준에 관한 규칙 제38조(사전조사 및 작업계획서의 작성 등)</a></li>'
 '<li><a href="'+BYL(4)+'">같은 규칙 별표 4(사전조사 및 작업계획서 내용, 개정 2025. 9. 1.)</a></li>'
 '<li><a href="'+BYL(11)+'">같은 규칙 별표 11(굴착면의 기울기 기준, 개정 2023. 11. 14.)</a></li>'
 '<li><a href="'+JO(338)+'">제338조</a> · <a href="'+JO(339)+'">제339조</a> · <a href="'+JO(340)+'">제340조</a> · <a href="'+JO(341)+'">제341조</a> · <a href="'+JO(342)+'">제342조</a>(굴착작업 위험방지 관련 조문)</li>'
 '<li><a href="'+NEWS+'">연합뉴스(2026. 10. 16.) — 고용노동부 장관 건설현장 불시 점검, 붕괴 위험 현장 집중 점검·감독 계획</a></li></ul>',
 '<p>법령 기준: 산업안전보건기준에 관한 규칙(시행 2026. 3. 2., 고용노동부령 제450호). 자료 확인일: 2026년 11월 1일. '+esc(D['note'])+'</p>','<h2>따라쓰기 PDF</h2>']
 P+=['<p><a href="'+CDN+PDF+'">3일차 굴착면 기울기 답안 예시·따라쓰기 PDF 내려받기</a></p>'] if bl else ['<p data-ax-attach="'+PDF+'"></p>']
 P+=['<p>Q-net 원본 답안지 작성면에 옅은 회색으로 작성한 '+str(len(doc))+'쪽 자료입니다.</p>','<h2><a href="https://geoai-na.netlify.app/safety-questions/">함께 푸는 [건설안전기술사] 답안지 요청</a></h2>','<p>문제를 요청하시면 접수 순서에 따라 매일 밤 11시에 요청을 확인하고, 정답예시와 따라쓰기 PDF를 작성해 블로그에 올립니다.</p>']
 return '\n'.join(P)
for n,bl in [('티스토리게시본문.html',False),('Blogger게시본문.html',True)]:(OUT/n).write_text(body(bl))
(OUT/'미리보기.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><title>'+esc(TITLE)+'</title><style>body{font-family:AppleGothic,sans-serif;max-width:850px;margin:36px auto;padding:0 20px;line-height:1.9}th,td{padding:8px}img{max-width:100%}blockquote{border-left:4px solid #4782ab;padding-left:15px}</style><h1>'+esc(TITLE)+'</h1>'+body(True).replace(CDN,'./')+'</html>')
(OUT/'제목.txt').write_text(TITLE+'\n');(OUT/'태그.txt').write_text(','.join(D['tags'])+'\n')
(OUT/'답안예시_줄배치.json').write_text(json.dumps({'pages':[[{'text':t,'font_size':s} for t,s in c] for c in chunks],'gray':'#B8B8B8','template_page_index':4},ensure_ascii=False,indent=2))
print('PDF pages',len(doc),'rows',len(lines))
