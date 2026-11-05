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
PDF_NAME='01일차_한중콘크리트타설전점검_답안예시_따라쓰기.pdf'
FIG_NAME='타설전_점검과양생_흐름도.png'
CDN='https://geoai-na.netlify.app/building-questions/materials/day01/'

def figure():
 im=Image.new('RGB',(1500,960),'#f4f7fb');d=ImageDraw.Draw(im)
 font=str(ROOT/'common/assets/FONTS/Pretendard-Bold.otf')
 f=lambda n:ImageFont.truetype(font,n)
 d.text((72,48),'한중콘크리트: 타설 전 확인부터 초기양생 종료까지',font=f(44),fill='#133047')
 labels=[('① 적용 조건 확인','기온 예보·부재 두께·노출 상태'),('② 타설 전 점검','빙설·동결지반·보양·양생 준비'),('③ 타설·즉시 피복','계획된 온도 확인·바람 차단'),('④ 온도·강도 기록','취약부 온도·현장동일조건 공시체'),('⑤ 강도 확인·승인','초기양생 종료와 해체 판단 구분')]
 for i,(a,b) in enumerate(labels):
  y=155+i*145;d.rounded_rectangle((76,y,1424,y+106),radius=18,fill='#ffffff',outline='#3d6f8d',width=3)
  d.text((112,y+12),a,font=f(35),fill='#133047');d.text((600,y+30),b,font=f(31),fill='#24485f')
  if i<4:d.polygon([(740,y+111),(760,y+111),(760,y+122),(780,y+122),(750,y+140),(720,y+122),(740,y+122)],fill='#3d6f8d')
 d.text((80,920),'작성자가 정리한 학습용 절차도 · 축척 없음 · 세부 조건은 본문·적용 시방서 확인',font=f(25),fill='#46586a')
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
   line=''
   for word in source.split():
    candidate=(line+' '+word) if line else word
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
  c.setFont('KR',14);c.drawString(132,731,'1')
  if i:
   c.setFillColorRGB(1,1,1);c.rect(574,791,45,45,stroke=0,fill=1)
   c.setFillColorRGB(gray,gray,gray);c.setFont('KR',13);c.drawString(587,803,str(i+1)+'쪽')
  c.showPage()
 c.save();buf.seek(0);ov=PdfReader(buf);writer=PdfWriter()
 template_readers=[PdfReader(template) for _ in ov.pages]
 for source_reader,page in zip(template_readers,ov.pages):
  bp=deepcopy(source_reader.pages[4]);bp.merge_page(page);writer.add_page(bp)
 writer.add_metadata({'/Title':m['title']+' — 따라쓰기','/Subject':'2024 제132회 건축시공기술사 제3교시 1번 학습용 답안 예시. 공식 채점기준 아님. 작성 글씨 RGB 184/184/184.'})
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
 if remote:banner='<p><img src="'+CDN+'banner.png" alt="한중콘크리트 타설 전 점검과 초기동해 방지" style="max-width:100%;height:auto"></p>'
 else:banner='<p data-ax-attach="banner.png"></p>'
 intro=pars(m['intro'])
 qurl='https://www.q-net.or.kr/crf005.do?gId=&gSite=Q&id=crf00503s02&jmCd=0510&jmInfoDivCcd=B0'
 intro=intro.replace(esc('공식 일정('+qurl+')'),'<a href="'+esc(qurl)+'">공식 일정</a>')
 b=[banner,'<p><small>배너: AI 생성 디오라마(학습용 이미지).</small></p>',intro,'<h2>문제</h2>','<p>기출문제: 2024년 제132회 건축시공기술사 제3교시 1번 (<a href="https://www.q-net.or.kr/cst006.do?id=cst00602&amp;artlSeq=5212827&amp;brdId=Q006&amp;gSite=Q">Q-net 공식 문제지</a>)</p>','<blockquote><p>'+esc(m['problem'])+'</p></blockquote>','<p>논술형 · 25점 · 권장 작성시간 25분(학습용 제안)</p>','<h2>출제 의도와 답안 방향</h2>',pars(m['intent'][:1]),'<blockquote>'+pars(m['intent'][1:])+'</blockquote>']
 for i,s in enumerate(m['explanation']):
  b+=['<h2>'+esc(s['heading'])+'</h2>',pars(s['paragraphs']),table(s.get('table'))]
  if i==0:
   b+=['<p><img src="'+CDN+FIG_NAME+'" alt="한중콘크리트 타설 전 점검에서 초기양생 종료까지의 흐름도" style="max-width:100%;height:auto"></p>' if remote else '<p data-ax-attach="'+FIG_NAME+'"></p>','<p>타설 전 점검부터 초기양생 종료까지의 흐름을 정리한 절차도예요.</p>']
 b+=['<h2>답안 예시</h2>','<hr>']
 for s in m['answer']:b+=['<h3>'+esc(s['heading'])+'</h3>','<ul>'+''.join('<li>'+esc(x)+'</li>' for x in s['bullets'])+'</ul>']
 b+=['<hr>','<h2>놓치기 쉬운 점</h2>','<ul>'+''.join('<li>'+esc(x)+'</li>' for x in m['pitfalls'])+'</ul>','<h2>참고자료와 확인일</h2>','<ul>'+''.join('<li><a href="'+esc(x['url'])+'">'+esc(x['title'])+'</a></li>' for x in m['sources'])+'</ul>','<p>자료 확인일: 2026년 10월 31일.</p>','<h2>따라쓰기 PDF</h2>','<p><a href="'+CDN+PDF_NAME+'">'+PDF_NAME+'</a></p>' if remote else '<p data-ax-attach="'+PDF_NAME+'"></p>','<p>Q-net 답안지 양식 위에 답안 예시를 옅은 회색 글씨로 얹은 4쪽 PDF예요.</p>','<h2><a href="https://geoai-na.netlify.app/building-questions/">함께 푸는 [건축시공기술사] 답안지 요청</a></h2>','<p>문제를 요청하시면 접수 순서에 따라 매일 밤 11시에 요청을 확인하고, 답안 예시와 따라쓰기 PDF를 작성해 블로그에 올립니다.</p>','<p>'+esc(m['disclosure'])+'</p>']
 return '\n'.join(x for x in b if x)

def main():
 m=json.loads((OUT/'manuscript-final.json').read_text());figure();pages=make_pdf(m)
 (OUT/'티스토리게시본문.html').write_text(body(m));(OUT/'Blogger게시본문.html').write_text(body(m,True));(OUT/'제목.txt').write_text(m['title']+'\n');(OUT/'태그.txt').write_text(','.join(m['tags'])+'\n')
 preview='<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{max-width:850px;margin:35px auto;font:19px/1.8 -apple-system,sans-serif;color:#173047}h2{margin-top:45px}table{font-size:16px}td,th{padding:10px}img{max-width:100%}</style><body>'+body(m,True).replace(CDN,str(OUT)+'/')+'</body></html>'
 (OUT/'미리보기.html').write_text(preview)
 print('built',pages,'pages',len(body(m)),'html characters')
if __name__=='__main__':main()
