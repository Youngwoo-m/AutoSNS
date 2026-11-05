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
TITLE=D['title'];PDF='04일차_밀폐공간작업_답안예시_따라쓰기.pdf';CDN='https://geoai-na.netlify.app/safety-questions/materials/day04/'
QNET=Q['source']
JO=lambda n:'https://www.law.go.kr/LSW/lsSideInfoP.do?docCls=jo&amp;joBrNo=00&amp;joNo=%04d&amp;lsiSeq=273603&amp;urlMode=lsScJoRltInfoR'%n
JO2=lambda n:'https://www.law.go.kr/LSW/lsSideInfoP.do?docCls=jo&amp;joBrNo=02&amp;joNo=%04d&amp;lsiSeq=273603&amp;urlMode=lsScJoRltInfoR'%n
BYL=lambda n:'https://www.law.go.kr/LSW/lsBylInfoPLinkR.do?lsiSeq=273603&amp;lsNm=%EC%82%B0%EC%97%85%EC%95%88%EC%A0%84%EB%B3%B4%EA%B1%B4%EA%B8%B0%EC%A4%80%EC%97%90%EA%B4%80%ED%95%9C%EA%B7%9C%EC%B9%99&amp;bylNo=NNNN&amp;bylBrNo=00&amp;bylCls=BE&amp;bylEfYd=&amp;bylEfYdYn=Y'.replace('NNNN','%04d'%n)
NEWS='https://biz.chosun.com/real_estate/real_estate_general/2026/11/02/PAEA6N3Q6JEXXNBSWUJJMMIWNY/'
O2=json.loads((OUT/'o2_source.json').read_text())
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
groups.append([(t,13) for t in wrap('밀폐공간작업 시 산소농도 저하의 인체 영향, 작업프로그램 안전절차 및 안전점검사항',13)]+[('제134회 제3교시 3번 · 학습용 답안 예시',11)])
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
 cv.setFont('KR',13);cv.drawString(132,731,'3')
 cv.showPage()
cv.save();b.seek(0);ov=PdfReader(b);w=PdfWriter()
for i,o in enumerate(ov.pages):
 p=deepcopy(PdfReader(template).pages[4]);p.merge_page(o)
 if i:
  nb=BytesIO();c=canvas.Canvas(nb,pagesize=(W,H));c.setFillColorRGB(1,1,1);c.rect(574,791,45,45,stroke=0,fill=1);c.setFillColorRGB(.15,.15,.15);c.setFont('KR',12);c.drawString(586,803,f'{i+1}쪽');c.save();nb.seek(0);p.merge_page(PdfReader(nb).pages[0])
 w.add_page(p)
w.add_metadata({'/Title':TITLE+' - 따라쓰기','/Subject':'제134회 제3교시3번 학습용 답안 예시. 작성글씨 RGB184/184/184. 원본 Q-net 답안지 보존.'})
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
 P=[image('banner.png','밀폐공간 질식 예방, 산소농도와 작업 프로그램',bl),'<p><small>배너: AI 생성 디오라마 배경(학습용 이미지).</small></p>',paras(D['intro']),
 '<p><small>글머리 근거: <a href="'+NEWS+'">조선비즈 「지하 공사장 유해가스, AI가 감지… 건설연, ‘지하 환경위험관리시스템’ 개발」</a>(2026년 11월 2일, 같은 날 확인).</small></p>',
 '<h2>문제</h2>','<p>2024년 제134회 건설안전기술사 제3교시 3번 · <a href="'+QNET+'">Q-net 공식 문제지</a></p>','<blockquote><p>'+esc(D['problem'])+'</p></blockquote>','<p>논술형 · 25점 · 권장 작성시간 25분</p>',
 '<h2>출제 의도와 답안 방향</h2>','<p>'+esc(D['intent'][0])+'</p><blockquote><p><strong>답안 작성 요령</strong> — '+esc(D['intent'][1])+'</p></blockquote>']
 for i,x in enumerate(D['explanations']):
  P+=['<h2>'+esc(x['heading'])+'</h2>',paras(x['paragraphs'][:1])]
  if i==0:P+=[table(O2['table']),'<p style="text-align:center"><small>출처: <a href="'+O2['url']+'">'+esc(O2['citation'])+'</a></small></p>']
  P+=[paras(x['paragraphs'][1:])]
  if i==1:P+=[image('적정공기_기준.png','적정공기 기준 그림: 산소 18% 이상 23.5% 미만, 이산화탄소 1.5% 미만, 일산화탄소 30ppm 미만, 황화수소 10ppm 미만',bl),'<p style="text-align:center"><small>밀폐공간 적정공기 기준(제618조제3호) 한눈에 보기.</small></p>','<h3>측정값으로 적정공기 판정해 보기</h3>','<p>'+esc(D['calc_intro'])+'</p>',table(D['calc_table']),'<p>'+esc(D['calc_after'])+'</p>']
  if i==3:P+=[image('밀폐공간_작업절차.png','밀폐공간 작업 절차 흐름도: 밀폐공간 파악과 출입금지, 작업 전 확인, 주지, 산소·유해가스 측정, 환기, 인원 점검과 감시인, 작업 중 환기, 이상 시 신고와 구출, 퇴장 점검과 기록 보존',bl),'<p style="text-align:center"><small>밀폐공간 작업 절차 흐름도(조문 번호는 산업안전보건기준에 관한 규칙).</small></p>']
 P+=['<h3>조문과 답안 위치를 맞춰 보면</h3>',table(D['table']),'<h2>답안 예시</h2>','<hr>']
 for i,s in enumerate(D['answer_sections'],1):P+=['<h3>'+str(i)+'. '+esc(s['title'])+'</h3>','<ul>'+''.join('<li>'+esc(v)+'</li>' for v in s['bullets'])+'</ul>']
 P+=['<hr>','<h2>놓치기 쉬운 점</h2>','<ul>'+''.join('<li>'+esc(x)+'</li>' for x in D['pitfalls'])+'</ul>','<h2>참고자료와 확인일</h2>',
 '<ul><li><a href="'+QNET+'">Q-net — 2024년 제134회 건설안전기술사 공식 문제지</a></li>'
 '<li><a href="'+JO(618)+'">국가법령정보센터 — 산업안전보건기준에 관한 규칙 제618조(정의)</a> · <a href="'+JO(619)+'">제619조(밀폐공간 작업 프로그램의 수립·시행)</a></li>'
 '<li><a href="'+JO2(619)+'">제619조의2(산소 및 유해가스 농도의 측정 및 기록 등, 개정 2025. 12. 1.)</a> · <a href="'+JO(620)+'">제620조</a> · <a href="'+JO(621)+'">제621조</a> · <a href="'+JO(622)+'">제622조</a> · <a href="'+JO(623)+'">제623조</a> · <a href="'+JO(624)+'">제624조</a> · <a href="'+JO(625)+'">제625조</a></li>'
 '<li><a href="'+JO(640)+'">제640조(긴급 구조훈련)</a> · <a href="'+JO(641)+'">제641조(안전한 작업방법 등의 주지)</a> · <a href="'+JO(643)+'">제643조(구출 시 공기호흡기 또는 송기마스크의 사용)</a></li>'
 '<li><a href="'+BYL(18)+'">같은 규칙 별표 18(밀폐공간, 개정 2023. 11. 14.)</a> · <a href="'+BYL(2)+'">별표 2(관리감독자의 유해·위험 방지) 제20호</a></li>'
 '<li><a href="'+O2['url']+'">'+esc(O2['citation'])+'</a> — 법적 기준이 아닌 기술지침·안내 자료</li>'
 '<li><a href="'+NEWS+'">조선비즈(2026. 11. 2.) — 한국건설기술연구원 지하 환경위험관리시스템 개발</a></li></ul>',
 '<p>법령 기준: 산업안전보건기준에 관한 규칙(시행 2026. 3. 2., 고용노동부령 제450호). 밀폐공간 조문은 2025. 12. 1. 개정·시행(고용노동부령 제454호)이 반영된 현행 조문으로 확인했어요. 자료 확인일: 2026년 11월 2일. '+esc(D['note'])+'</p>','<h2>따라쓰기 PDF</h2>']
 P+=['<p><a href="'+CDN+PDF+'">4일차 밀폐공간 작업 답안 예시·따라쓰기 PDF 내려받기</a></p>'] if bl else ['<p data-ax-attach="'+PDF+'"></p>']
 P+=['<p>Q-net 원본 답안지 작성면에 옅은 회색으로 작성한 '+str(len(doc))+'쪽 자료입니다.</p>','<h2><a href="https://geoai-na.netlify.app/safety-questions/">함께 푸는 [건설안전기술사] 답안지 요청</a></h2>','<p>문제를 요청하시면 접수 순서에 따라 매일 밤 11시에 요청을 확인하고, 정답예시와 따라쓰기 PDF를 작성해 블로그에 올립니다.</p>']
 return '\n'.join(P)
for n,bl in [('티스토리게시본문.html',False),('Blogger게시본문.html',True)]:(OUT/n).write_text(body(bl))
(OUT/'미리보기.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><title>'+esc(TITLE)+'</title><style>body{font-family:AppleGothic,sans-serif;max-width:850px;margin:36px auto;padding:0 20px;line-height:1.9}th,td{padding:8px}img{max-width:100%}blockquote{border-left:4px solid #4782ab;padding-left:15px}</style><h1>'+esc(TITLE)+'</h1>'+body(True).replace(CDN,'./')+'</html>')
(OUT/'제목.txt').write_text(TITLE+'\n');(OUT/'태그.txt').write_text(','.join(D['tags'])+'\n')
(OUT/'답안예시_줄배치.json').write_text(json.dumps({'pages':[[{'text':t,'font_size':s} for t,s in c] for c in chunks],'gray':'#B8B8B8','template_page_index':4},ensure_ascii=False,indent=2))
print('PDF pages',len(doc),'rows',len(lines))
