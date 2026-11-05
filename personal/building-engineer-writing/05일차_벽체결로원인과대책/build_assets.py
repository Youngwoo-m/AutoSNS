from pathlib import Path
import json,html,re,hashlib
from io import BytesIO
from copy import deepcopy
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader,PdfWriter
import pypdfium2 as pdfium
from PIL import Image,ImageDraw,ImageFont
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
PDF_NAME='05일차_벽체결로원인과대책_답안예시_따라쓰기.pdf'
FIG_NAME='벽체결로_단면도식.png'
CDN='https://geoai-na.web.app/building-questions/materials/day05/'

def figure():
 im=Image.new('RGB',(1500,1060),'#f4f7fb');d=ImageDraw.Draw(im)
 font=str(ROOT/'common/assets/FONTS/Pretendard-Bold.otf')
 f=lambda n:ImageFont.truetype(font,n)
 d.text((60,36),'벽체 결로: 어디에 생기고, 무엇으로 막나 (철근콘크리트 내단열 벽 단면)',font=f(38),fill='#133047')
 # 실외 / 실내 영역
 d.rectangle((60,120,330,860),fill='#dbe8f5');d.text((90,140),'실외',font=f(34),fill='#24485f');d.text((90,190),'겨울 · 차가운 공기',font=f(24),fill='#24485f')
 d.rectangle((602,120,1440,860),fill='#fbefe2');d.text((1010,140),'실내',font=f(34),fill='#7a4b1f');d.text((1010,190),'따뜻하고 습한 공기',font=f(24),fill='#7a4b1f')
 # 콘크리트 벽
 d.rectangle((330,120,470,860),fill='#b9bec4',outline='#5c6670',width=2);d.text((345,860+8),'콘크리트',font=f(24),fill='#46586a')
 # 단열재
 d.rectangle((470,120,590,560),fill='#f6e08a',outline='#a08a2a',width=2);d.text((478,870),'단열재',font=f(24),fill='#46586a')
 d.rectangle((470,640,590,860),fill='#f6e08a',outline='#a08a2a',width=2)
 # 방습층(실내측) — 상부 연속, 하부 끊김 표시
 d.rectangle((590,120,602,560),fill='#2b7a4b');d.rectangle((590,640,602,860),fill='#2b7a4b');d.text((612,870),'방습층(실내측)',font=f(24),fill='#2b7a4b')
 # 슬래브(열교)
 d.rectangle((330,560,1440,640),fill='#9aa1a8',outline='#5c6670',width=2);d.text((900,582),'바닥 슬래브',font=f(26),fill='#ffffff')
 # 열교 화살표
 d.line((250,600,640,600),fill='#c0392b',width=6);d.polygon([(250,588),(226,600),(250,612)],fill='#c0392b')
 d.text((80,625),'열이 슬래브로',font=f(23),fill='#c0392b');d.text((80,655),'빠져나감(열교)',font=f(23),fill='#c0392b')
 # 표기 1 표면결로
 d.ellipse((575,495,645,565),outline='#c0392b',width=5);d.ellipse((575,635,645,705),outline='#c0392b',width=5)
 d.rounded_rectangle((720,250,1420,410),radius=14,fill='#ffffff',outline='#c0392b',width=3)
 d.text((740,262),'① 표면결로 — 열교 부위(벽·슬래브 접합부)',font=f(27),fill='#c0392b')
 d.multiline_text((740,310),'단열이 끊긴 곳은 실내 표면 온도가 낮아져\n이슬점 이하가 되면 표면에 물이 맺힘',font=f(24),fill='#173047',spacing=8)
 d.text((545,470),'①',font=f(30),fill='#c0392b');d.text((510,325),'②',font=f(30),fill='#4b3f72')
 # 표기 2 내부결로
 d.ellipse((455,330,505,380),outline='#4b3f72',width=5)
 d.rounded_rectangle((720,430,1420,540),radius=14,fill='#ffffff',outline='#4b3f72',width=3)
 d.text((740,442),'② 내부결로 — 단열재와 구조체 사이',font=f(27),fill='#4b3f72')
 d.text((740,488),'방습층이 끊기면 수증기가 들어가 차가운 면에서 맺힘',font=f(23),fill='#173047')
 # 수증기 화살표
 for y in (740,790):
  d.line((1000,y,640,y),fill='#7a4b1f',width=4);d.polygon([(640,y-10),(616,y),(640,y+10)],fill='#7a4b1f')
 d.text((720,810),'수증기 이동 방향(실내 → 실외)',font=f(23),fill='#7a4b1f')
 # 대책 띠
 d.rounded_rectangle((60,950,1440,1030),radius=14,fill='#e6eef6',outline='#24485f',width=2)
 d.text((80,960),'대책: 단열 연속·열교 단열보강 · 방습층 실내측 연속(겹침 50~150 mm) · 환기·습도 관리',font=f(26),fill='#133047')
 d.text((80,998),'KCS 41 42 01(2021) 3.1·3.3.1·3.6.1을 작성자가 정리한 개념도 · 축척 없음',font=f(21),fill='#46586a')
 im.save(OUT/FIG_NAME)

def make_pdf(m):
 template=Path('/Volumes/USB256/기술사/2026기술사 답안지-1교시(안내용)_Qnet원본.pdf')
 base=PdfReader(template).pages[4];w,h=float(base.mediabox.width),float(base.mediabox.height)
 pdfmetrics.registerFont(TTFont('KR','/System/Library/Fonts/Supplemental/AppleGothic.ttf'))
 buf=BytesIO();c=canvas.Canvas(buf,pagesize=(w,h));gray=184/255
 allw=[]
 for source in m['pdf_lines']:
  if True:
   lead=source[:len(source)-len(source.lstrip())];line=''
   for word in source.split():
    candidate=(line+' '+word) if line else lead+word
    if pdfmetrics.stringWidth(candidate,'KR',12)>400 and line:
     allw.append(line);line='  '+word
    else:line=candidate
   if line:allw.append(line)
 pages=[];cur=[]
 for ln in allw:
  if len(cur)>=22 or (len(cur)>=19 and re.match(r'^\d\. ',ln)):pages.append(cur);cur=[]
  cur.append(ln)
 if cur:pages.append(cur)
 assert len(pages)>=3,len(pages)
 for i,lines in enumerate(pages):
  assert len(lines)<=22,(i,len(lines))
  for row,line in enumerate(lines):
   size=12.0
   while pdfmetrics.stringWidth(line,'KR',size)>402 and size>10.5:size-=.25
   assert pdfmetrics.stringWidth(line,'KR',size)<=402,line
   c.setFillColorRGB(gray,gray,gray);c.setFont('KR',size);c.drawString(202,764-row*32.35,line)
  c.setFont('KR',14);c.drawString(132,731,'4')
  if i:
   c.setFillColorRGB(1,1,1);c.rect(574,791,45,45,stroke=0,fill=1)
   c.setFillColorRGB(gray,gray,gray);c.setFont('KR',13);c.drawString(587,803,str(i+1)+'쪽')
  c.showPage()
 c.save();buf.seek(0);ov=PdfReader(buf);writer=PdfWriter()
 template_readers=[PdfReader(template) for _ in ov.pages]
 for source_reader,page in zip(template_readers,ov.pages):
  bp=deepcopy(source_reader.pages[4]);bp.merge_page(page);writer.add_page(bp)
 writer.add_metadata({'/Title':m['title']+' — 따라쓰기','/Subject':'2023 제130회 건축시공기술사 제2교시 4번 학습용 답안 예시. 공식 채점기준 아님. 작성 글씨 RGB 184/184/184.'})
 with (OUT/PDF_NAME).open('wb') as stream:writer.write(stream)
 doc=pdfium.PdfDocument(str(OUT/PDF_NAME))
 for i,page in enumerate(doc):page.render(scale=1.5).to_pil().save(OUT/f'PDF-preview-{i+1}.png')
 return len(doc)

NPAGES=[0]
def esc(s):return html.escape(str(s),quote=True)
def pars(xs):return '\n'.join('<p>'+esc(s)+'</p>' for s in xs)
def table(t):
 if not t or not t.get('headers'):return ''
 rows=['<tr>'+''.join('<th style="text-align:center">'+esc(v)+'</th>' for v in t['headers'])+'</tr>']
 rows+=['<tr>'+''.join('<td style="text-align:center">'+esc(v)+'</td>' for v in row)+'</tr>' for row in t['rows']]
 return '<table border="1" style="border-collapse:collapse;width:100%">'+''.join(rows)+'</table>'

def body(m,remote=False):
 if remote:banner='<p><img src="'+CDN+'banner.png" alt="벽체 결로의 종류와 결로방지 대책 학습 배너" style="max-width:100%;height:auto"></p>'
 else:banner='<p data-ax-attach="banner.png"></p>'
 intro='\n'.join('<p>'+x+'</p>' for x in m['intro'])  # 링크 한 개를 포함한 작성자 원고(외부 입력 아님)
 qurl='https://www.q-net.or.kr/cst006.do?id=cst00602&amp;artlSeq=5211871&amp;brdId=Q006&amp;gSite=Q'
 b=[banner,'<p><small>배너: AI로 만든 디오라마 배경 그림 위에 제목 글자를 얹었어요.</small></p>',intro,'<h2>문제</h2>','<p>기출문제: 2023년 제130회 건축시공기술사 제2교시 4번 (<a href="'+qurl+'">Q-net 공식 문제지</a>)</p>','<blockquote><p>'+esc(m['problem'])+'</p></blockquote>','<p>'+esc(m['problem_meta'])+'</p>','<h2>출제 의도와 답안 방향</h2>',pars(m['intent'][:1]),'<blockquote><p><strong>답안 작성 요령</strong> — '+esc(m['intent'][1])+'</p></blockquote>']
 for s in m['explanation']:
  b+=['<h2>'+esc(s['heading'])+'</h2>',pars(s['paragraphs']),table(s.get('table'))]
  if s.get('figure_after'):
   fg=m['figure']
   b+=['<p><img src="'+CDN+FIG_NAME+'" alt="'+esc(fg['alt'])+'" style="max-width:100%;height:auto"></p>' if remote else '<p data-ax-attach="'+FIG_NAME+'"></p>','<p><small>'+esc(fg['caption'])+'</small></p>']
 b+=['<h2>답안 예시</h2>','<hr>']
 for s in m['answer']:b+=['<h3>'+esc(s['heading'])+'</h3>','<ul>'+''.join('<li>'+esc(x)+'</li>' for x in s['bullets'])+'</ul>']
 b+=['<hr>','<h2>놓치기 쉬운 점</h2>','<ul>'+''.join('<li>'+esc(x)+'</li>' for x in m['pitfalls'])+'</ul>','<h2>참고자료와 확인일</h2>','<ul>'+''.join('<li><a href="'+esc(x['url'])+'">'+esc(x['title'])+'</a></li>' for x in m['sources'])+'</ul>','<p>자료 확인일: '+esc(m['checked_date'])+'.</p>','<p>'+esc(m['disclosure'])+'</p>','<h2>따라쓰기 PDF</h2>','<p><a href="'+CDN+PDF_NAME+'">'+PDF_NAME+'</a></p>' if remote else '<p data-ax-attach="'+PDF_NAME+'"></p>','<p>Q-net 답안지 양식 위에 답안 예시를 옅은 회색 글씨로 얹은 '+str(NPAGES[0])+'쪽 PDF예요. 위에 겹쳐 따라 쓰며 분량과 줄 배치를 익혀 보세요.</p>','<h2><a href="https://geoai-na.web.app/building-questions/">함께 푸는 [건축시공기술사] 답안지 요청</a></h2>','<p>문제를 요청하시면 접수 순서에 따라 매일 밤 11시에 요청을 확인하고, 정답예시와 따라쓰기 PDF를 작성해 블로그에 올립니다.</p>']
 return '\n'.join(x for x in b if x)

def main():
 m=json.loads((OUT/'manuscript-final.json').read_text());figure();pages=make_pdf(m);NPAGES[0]=pages
 (OUT/'티스토리게시본문.html').write_text(body(m));(OUT/'Blogger게시본문.html').write_text(body(m,True));(OUT/'제목.txt').write_text(m['title']+'\n');(OUT/'태그.txt').write_text(','.join(m['tags'])+'\n')
 preview='<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{max-width:850px;margin:35px auto;font:19px/1.8 -apple-system,sans-serif;color:#173047}h2{margin-top:45px}table{font-size:16px}td,th{padding:10px}img{max-width:100%}</style><body>'+body(m,True).replace(CDN,str(OUT)+'/')+'</body></html>'
 (OUT/'미리보기.html').write_text(preview)
 print('built',pages,'pages',len(body(m)),'html characters')
if __name__=='__main__':main()
