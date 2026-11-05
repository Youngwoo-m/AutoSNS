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
PDF_NAME='04일차_철골용접결함원인과대책_답안예시_따라쓰기.pdf'
FIG_NAME='용접결함_검사와보수_도식.png'
CDN='https://geoai-na.netlify.app/building-questions/materials/day04/'

def figure():
 im=Image.new('RGB',(1500,1060),'#f4f7fb');d=ImageDraw.Draw(im)
 font=str(ROOT/'common/assets/FONTS/Pretendard-Bold.otf')
 f=lambda n:ImageFont.truetype(font,n)
 d.text((72,44),'철골 용접결함: 어디에 생기고, 무엇으로 찾고, 어떻게 고치나',font=f(42),fill='#133047')
 d.text((80,130),'구분',font=f(28),fill='#46586a');d.text((420,130),'대표 결함',font=f(28),fill='#46586a');d.text((900,130),'검사 → 보수',font=f(28),fill='#46586a')
 rows=[('표면결함','언더컷 · 오버랩 · 피트','VT·게이지 → 보수 용접·그라인더','#7a4b1f'),
       ('표면 균열','표면균열 · 미세 균열','MT · PT → 양끝 50 mm 이상 제거','#8a2f2f'),
       ('내부결함','블로홀 · 슬래그 · 용입불량','UT · RT → 양끝 20 mm 추가 제거','#24485f'),
       ('용접 균열','저온균열 등 내부균열','UT → 양끝 50 mm 이상 제거','#4b3f72')]
 for i,(a,b,c,col) in enumerate(rows):
  y=180+i*112;d.rounded_rectangle((70,y,1430,y+92),radius=16,fill='#ffffff',outline=col,width=3)
  d.rounded_rectangle((70,y,380,y+92),radius=16,fill=col)
  d.text((92,y+26),a,font=f(32),fill='#ffffff');d.text((410,y+28),b,font=f(29),fill='#173047');d.text((890,y+28),c,font=f(28),fill='#173047')
 y=650;steps=[('용접 전','바탕 청소 · 습기 제거\n기온 -5 ℃ 이하 금지 · 예열'),('용접 중','전류 · 전압 · 방향 관리\n풍속 2 m/s 이상 방풍'),('용접 후','최소 지체시간 뒤 UT\n로트 30개 표본 판정'),('보수','예열하고 보수 용접\n재검사 합격')]
 for i,(t,b) in enumerate(steps):
  x=70+i*345;d.rounded_rectangle((x,y,x+315,y+190),radius=16,fill='#e6eef6',outline='#24485f',width=2)
  d.text((x+24,y+18),t,font=f(32),fill='#133047');d.multiline_text((x+24,y+76),b,font=f(25),fill='#173047',spacing=10)
  if i<3:d.polygon([(x+322,y+85),(x+340,y+95),(x+322,y+105)],fill='#24485f')
 d.text((80,880),'모재까지 갈라진 균열(라멜라 티어링 등)은 보수방법을 정해 책임기술자 승인(3.16.1) · 보수 후 재검사',font=f(25),fill='#133047')
 d.text((80,940),'KCS 41 31 20 3.4·3.8·3.15·3.16을 작성자가 정리 · 검사 방법 대응은 일반 원리 · 축척 없음 · 특기시방서 우선',font=f(23),fill='#46586a')
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
  c.setFont('KR',14);c.drawString(132,731,'2')
  if i:
   c.setFillColorRGB(1,1,1);c.rect(574,791,45,45,stroke=0,fill=1)
   c.setFillColorRGB(gray,gray,gray);c.setFont('KR',13);c.drawString(587,803,str(i+1)+'쪽')
  c.showPage()
 c.save();buf.seek(0);ov=PdfReader(buf);writer=PdfWriter()
 template_readers=[PdfReader(template) for _ in ov.pages]
 for source_reader,page in zip(template_readers,ov.pages):
  bp=deepcopy(source_reader.pages[4]);bp.merge_page(page);writer.add_page(bp)
 writer.add_metadata({'/Title':m['title']+' — 따라쓰기','/Subject':'2023 제129회 건축시공기술사 제4교시 2번 학습용 답안 예시. 공식 채점기준 아님. 작성 글씨 RGB 184/184/184.'})
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
 if remote:banner='<p><img src="'+CDN+'banner.png" alt="철골 용접결함 원인과 비파괴검사 학습 배너" style="max-width:100%;height:auto"></p>'
 else:banner='<p data-ax-attach="banner.png"></p>'
 intro='\n'.join('<p>'+x+'</p>' for x in m['intro'])  # 링크 한 개를 포함한 작성자 원고(외부 입력 아님)
 qurl='https://www.q-net.or.kr/cst006.do?id=cst00602&amp;artlSeq=5211599&amp;brdId=Q006&amp;gSite=Q'
 b=[banner,'<p><small>배너: 기존 AI 생성 디오라마 배경 위에 제목 글자를 얹은 그림이에요.</small></p>',intro,'<h2>문제</h2>','<p>기출문제: 2023년 제129회 건축시공기술사 제4교시 2번 (<a href="'+qurl+'">Q-net 공식 문제지</a>)</p>','<blockquote><p>'+esc(m['problem'])+'</p></blockquote>','<p>'+esc(m['problem_meta'])+'</p>','<h2>출제 의도와 답안 방향</h2>',pars(m['intent'][:1]),'<blockquote><p><strong>답안 작성 요령</strong> — '+esc(m['intent'][1])+'</p></blockquote>']
 for s in m['explanation']:
  b+=['<h2>'+esc(s['heading'])+'</h2>',pars(s['paragraphs']),table(s.get('table'))]
  if s.get('figure_after'):
   fg=m['figure']
   b+=['<p><img src="'+CDN+FIG_NAME+'" alt="'+esc(fg['alt'])+'" style="max-width:100%;height:auto"></p>' if remote else '<p data-ax-attach="'+FIG_NAME+'"></p>','<p><small>'+esc(fg['caption'])+'</small></p>']
 b+=['<h2>답안 예시</h2>','<hr>']
 for s in m['answer']:b+=['<h3>'+esc(s['heading'])+'</h3>','<ul>'+''.join('<li>'+esc(x)+'</li>' for x in s['bullets'])+'</ul>']
 b+=['<hr>','<h2>놓치기 쉬운 점</h2>','<ul>'+''.join('<li>'+esc(x)+'</li>' for x in m['pitfalls'])+'</ul>','<h2>참고자료와 확인일</h2>','<ul>'+''.join('<li><a href="'+esc(x['url'])+'">'+esc(x['title'])+'</a></li>' for x in m['sources'])+'</ul>','<p>자료 확인일: '+esc(m['checked_date'])+'.</p>','<p>'+esc(m['disclosure'])+'</p>','<h2>따라쓰기 PDF</h2>','<p><a href="'+CDN+PDF_NAME+'">'+PDF_NAME+'</a></p>' if remote else '<p data-ax-attach="'+PDF_NAME+'"></p>','<p>Q-net 답안지 양식 위에 답안 예시를 옅은 회색 글씨로 얹은 '+str(NPAGES[0])+'쪽 PDF예요. 위에 겹쳐 따라 쓰며 분량과 줄 배치를 익혀 보세요.</p>','<h2><a href="https://geoai-na.netlify.app/building-questions/">함께 푸는 [건축시공기술사] 답안지 요청</a></h2>','<p>문제를 요청하시면 접수 순서에 따라 매일 밤 11시에 요청을 확인하고, 정답예시와 따라쓰기 PDF를 작성해 블로그에 올립니다.</p>']
 return '\n'.join(x for x in b if x)

def main():
 m=json.loads((OUT/'manuscript-final.json').read_text());figure();pages=make_pdf(m);NPAGES[0]=pages
 (OUT/'티스토리게시본문.html').write_text(body(m));(OUT/'Blogger게시본문.html').write_text(body(m,True));(OUT/'제목.txt').write_text(m['title']+'\n');(OUT/'태그.txt').write_text(','.join(m['tags'])+'\n')
 preview='<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{max-width:850px;margin:35px auto;font:19px/1.8 -apple-system,sans-serif;color:#173047}h2{margin-top:45px}table{font-size:16px}td,th{padding:10px}img{max-width:100%}</style><body>'+body(m,True).replace(CDN,str(OUT)+'/')+'</body></html>'
 (OUT/'미리보기.html').write_text(preview)
 print('built',pages,'pages',len(body(m)),'html characters')
if __name__=='__main__':main()
