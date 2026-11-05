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
PDF_NAME='03일차_철골내화피복공법과검사_답안예시_따라쓰기.pdf'
FIG_NAME='내화피복_공법과검사_도식.png'
CDN='https://geoai-na.netlify.app/building-questions/materials/day03/'

def figure():
 im=Image.new('RGB',(1500,1000),'#f4f7fb');d=ImageDraw.Draw(im)
 font=str(ROOT/'common/assets/FONTS/Pretendard-Bold.otf')
 f=lambda n:ImageFont.truetype(font,n)
 d.text((72,44),'철골 내화피복: 공법별로 두께를 확인하는 방법',font=f(44),fill='#133047')
 rows=[('도장공법','팽창성 내화도료','반입 시 두께·비중 / 도막두께계','#7a4b1f'),
       ('습식 · 미장','철망 모르타르','시공 중 핀 확인 · 5 m²당 1개소','#24485f'),
       ('습식 · 뿜칠','암면 · 모르타르 · 플라스터','시공 후 코어 채취 · 1회 5개소','#24485f'),
       ('습식 · 조적','콘크리트 블록 · 돌 · 벽돌','반입 시 두께·비중 · 1회 3개소','#24485f'),
       ('건식공법','규산칼슘판 · ALC 판 · 석고보드','반입 시 두께·비중 · 1회 3개소','#2f5f3a'),
       ('타설 · 합성공법','콘크리트 · PC판 · ALC 판','특기시방서 확인','#4b3f72')]
 d.text((80,130),'구분',font=f(28),fill='#46586a');d.text((420,130),'대표 재료',font=f(28),fill='#46586a');d.text((900,130),'두께 확인',font=f(28),fill='#46586a')
 for i,(a,b,c,col) in enumerate(rows):
  y=180+i*112;d.rounded_rectangle((70,y,1430,y+92),radius=16,fill='#ffffff',outline=col,width=3)
  d.rounded_rectangle((70,y,380,y+92),radius=16,fill=col)
  d.text((92,y+26),a,font=f(32),fill='#ffffff');d.text((410,y+28),b,font=f(29),fill='#173047');d.text((890,y+28),c,font=f(29),fill='#173047')
 d.text((80,870),'빈도: 층마다 또는 바닥면적 500 m²마다 부위별 1회 · 연면적 500 m² 미만은 2회 이상 · 불합격은 덧뿜칠·재시공',font=f(26),fill='#133047')
 d.text((80,930),'KCS 41 31 50 표 1.1-1·3.2(도막두께계는 KCS 41 43 02 3.5(8))를 작성자가 정리 · 축척 없음 · 특기시방서 우선',font=f(24),fill='#46586a')
 im.save(OUT/FIG_NAME)

def make_pdf(m):
 template=Path('/Volumes/USB256/기술사/2026기술사 답안지-1교시(안내용)_Qnet원본.pdf')
 base=PdfReader(template).pages[4];w,h=float(base.mediabox.width),float(base.mediabox.height)
 pdfmetrics.registerFont(TTFont('KR','/System/Library/Fonts/Supplemental/AppleGothic.ttf'))
 buf=BytesIO();c=canvas.Canvas(buf,pagesize=(w,h));gray=184/255
 pages=m['pdf_answer_pages'];assert len(pages)>=3
 for i,lines in enumerate(pages):
  wrapped=[]
  for source in lines:
   lead=source[:len(source)-len(source.lstrip())];line=''
   for word in source.split():
    candidate=(line+' '+word) if line else lead+word
    if pdfmetrics.stringWidth(candidate,'KR',12)>400 and line:
     wrapped.append(line);line='  '+word
    else:line=candidate
   if line:wrapped.append(line)
  lines=wrapped
  assert len(lines)<=22,(i,len(lines))
  for row,line in enumerate(lines):
   size=12.0
   while pdfmetrics.stringWidth(line,'KR',size)>402 and size>10.5:size-=.25
   assert pdfmetrics.stringWidth(line,'KR',size)<=402,line
   c.setFillColorRGB(gray,gray,gray);c.setFont('KR',size);c.drawString(202,764-row*32.35,line)
  c.setFont('KR',14);c.drawString(132,731,'6')
  if i:
   c.setFillColorRGB(1,1,1);c.rect(574,791,45,45,stroke=0,fill=1)
   c.setFillColorRGB(gray,gray,gray);c.setFont('KR',13);c.drawString(587,803,str(i+1)+'쪽')
  c.showPage()
 c.save();buf.seek(0);ov=PdfReader(buf);writer=PdfWriter()
 template_readers=[PdfReader(template) for _ in ov.pages]
 for source_reader,page in zip(template_readers,ov.pages):
  bp=deepcopy(source_reader.pages[4]);bp.merge_page(page);writer.add_page(bp)
 writer.add_metadata({'/Title':m['title']+' — 따라쓰기','/Subject':'2022 제126회 건축시공기술사 제4교시 6번 학습용 답안 예시. 공식 채점기준 아님. 작성 글씨 RGB 184/184/184.'})
 with (OUT/PDF_NAME).open('wb') as stream:writer.write(stream)
 doc=pdfium.PdfDocument(str(OUT/PDF_NAME))
 for i,page in enumerate(doc):page.render(scale=1.5).to_pil().save(OUT/f'PDF-preview-{i+1}.png')
 return len(doc)

def esc(s):return html.escape(str(s),quote=True)
def pars(xs):return '\n'.join('<p>'+esc(s)+'</p>' for s in xs)
def table(t):
 if not t or not t.get('headers'):return ''
 rows=['<tr>'+''.join('<th style="text-align:center">'+esc(v)+'</th>' for v in t['headers'])+'</tr>']
 rows+=['<tr>'+''.join('<td style="text-align:center">'+esc(v)+'</td>' for v in row)+'</tr>' for row in t['rows']]
 return '<table border="1" style="border-collapse:collapse;width:100%">'+''.join(rows)+'</table>'

def body(m,remote=False):
 if remote:banner='<p><img src="'+CDN+'banner.png" alt="철골 내화피복과 내화뿜칠 공법 학습 배너" style="max-width:100%;height:auto"></p>'
 else:banner='<p data-ax-attach="banner.png"></p>'
 intro='\n'.join('<p>'+x+'</p>' for x in m['intro'])  # 링크 한 개를 포함한 작성자 원고(외부 입력 아님)
 qurl='https://www.q-net.or.kr/cst006.do?id=cst00602&amp;artlSeq=5209479&amp;brdId=Q006&amp;gSite=Q'
 b=[banner,'<p><small>배너: 기존 AI 생성 디오라마 배경 위에 제목 글자를 얹은 그림이에요.</small></p>',intro,'<h2>문제</h2>','<p>기출문제: 2022년 제126회 건축시공기술사 제4교시 6번 (<a href="'+qurl+'">Q-net 공식 문제지</a>)</p>','<blockquote><p>'+esc(m['problem'])+'</p></blockquote>','<p>'+esc(m['problem_meta'])+'</p>','<h2>출제 의도와 답안 방향</h2>',pars(m['intent'][:1]),'<blockquote><p><strong>답안 작성 요령</strong> — '+esc(m['intent'][1])+'</p></blockquote>']
 for s in m['explanation']:
  b+=['<h2>'+esc(s['heading'])+'</h2>',pars(s['paragraphs']),table(s.get('table'))]
  if s.get('figure_after'):
   fg=m['figure']
   b+=['<p><img src="'+CDN+FIG_NAME+'" alt="'+esc(fg['alt'])+'" style="max-width:100%;height:auto"></p>' if remote else '<p data-ax-attach="'+FIG_NAME+'"></p>','<p><small>'+esc(fg['caption'])+'</small></p>']
 b+=['<h2>답안 예시</h2>','<hr>']
 for s in m['answer']:b+=['<h3>'+esc(s['heading'])+'</h3>','<ul>'+''.join('<li>'+esc(x)+'</li>' for x in s['bullets'])+'</ul>']
 b+=['<hr>','<h2>놓치기 쉬운 점</h2>','<ul>'+''.join('<li>'+esc(x)+'</li>' for x in m['pitfalls'])+'</ul>','<h2>참고자료와 확인일</h2>','<ul>'+''.join('<li><a href="'+esc(x['url'])+'">'+esc(x['title'])+'</a></li>' for x in m['sources'])+'</ul>','<p>자료 확인일: '+esc(m['checked_date'])+'.</p>','<p>'+esc(m['disclosure'])+'</p>','<h2>따라쓰기 PDF</h2>','<p><a href="'+CDN+PDF_NAME+'">'+PDF_NAME+'</a></p>' if remote else '<p data-ax-attach="'+PDF_NAME+'"></p>','<p>Q-net 답안지 양식 위에 답안 예시를 옅은 회색 글씨로 얹은 3쪽 PDF예요. 위에 겹쳐 따라 쓰며 분량과 줄 배치를 익혀 보세요.</p>','<h2><a href="https://geoai-na.netlify.app/building-questions/">함께 푸는 [건축시공기술사] 답안지 요청</a></h2>','<p>문제를 요청하시면 접수 순서에 따라 매일 밤 11시에 요청을 확인하고, 정답예시와 따라쓰기 PDF를 작성해 블로그에 올립니다.</p>']
 return '\n'.join(x for x in b if x)

def main():
 m=json.loads((OUT/'manuscript-final.json').read_text());figure();pages=make_pdf(m)
 (OUT/'티스토리게시본문.html').write_text(body(m));(OUT/'Blogger게시본문.html').write_text(body(m,True));(OUT/'제목.txt').write_text(m['title']+'\n');(OUT/'태그.txt').write_text(','.join(m['tags'])+'\n')
 preview='<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{max-width:850px;margin:35px auto;font:19px/1.8 -apple-system,sans-serif;color:#173047}h2{margin-top:45px}table{font-size:16px}td,th{padding:10px}img{max-width:100%}</style><body>'+body(m,True).replace(CDN,str(OUT)+'/')+'</body></html>'
 (OUT/'미리보기.html').write_text(preview)
 print('built',pages,'pages',len(body(m)),'html characters')
if __name__=='__main__':main()
