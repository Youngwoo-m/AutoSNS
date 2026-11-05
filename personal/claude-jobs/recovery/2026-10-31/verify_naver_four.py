import json,re,hashlib,html,urllib.request,urllib.parse
from pathlib import Path
from html.parser import HTMLParser
R=Path('/Volumes/USB256/devAPP/AutoSNS');H=Path(__file__).resolve().parent
class A(HTMLParser):
 def __init__(self):super().__init__();self.files=[]
 def handle_starttag(self,t,attrs):
  d=dict(attrs);u=d.get('href','')
  if t=='a' and 'download.blog.naver.com' in u and '.pdf' in u:self.files.append(u)
def get(u):
 q=urllib.request.Request(urllib.parse.quote(u,safe=':/?=&%+'),headers={'User-Agent':'Mozilla/5.0','Referer':'https://m.blog.naver.com/safeworking'})
 with urllib.request.urlopen(q,timeout=30) as r:return r.status,r.read()
out=[]
for ex,cat in [('building',13),('safety',14)]:
 code,raw=get(f'https://m.blog.naver.com/api/blogs/safeworking/post-list?categoryNo={cat}&itemCount=30&page=1');data=json.loads(raw)['result']
 for day in [1,2]:
  resultfile=H/f'{ex}-day{day}-naver-go-result.json'
  if not resultfile.exists():continue
  result=json.loads(resultfile.read_text());u=result.get('url','');match=re.search(r'/(\d+)(?:\?|$)',u)
  if not match:continue
  num=int(match[1]);item=next((p for p in data['items'] if p['logNo']==num),None);assert item
  d=next((R/'GeoAI_NA'/f'{ex}-engineer-writing').glob(f'{day:02}일차_*'));title=(d/'제목.txt').read_text().strip()
  status,b=get(f'https://m.blog.naver.com/safeworking/{num}');s=b.decode();parser=A();parser.feed(s);pdf=next(d.glob('*.pdf'));digest=hashlib.sha256(pdf.read_bytes()).hexdigest();pdf_checks=[]
  for a in dict.fromkeys(parser.files):
   http,p=get(a);pdf_checks.append({'http':http,'sha256':hashlib.sha256(p).hexdigest(),'match':hashlib.sha256(p).hexdigest()==digest,'bytes':len(p),'magic':p.startswith(b'%PDF')})
  headings=[html.unescape(re.sub('<[^>]+>','',h)) for h in re.findall(r'<h[23][^>]*>(.*?)</h[23]>',(d/'티스토리게시본문.html').read_text(),re.S)]
  norm=lambda t:re.sub(r'\s+','',html.unescape(re.sub('<[^>]+>','',t)))
  missing=[h for h in headings if norm(h) not in norm(s)]
  row={'exam':ex,'day':day,'url':f'https://blog.naver.com/safeworking/{num}','title_match':item['titleWithInspectMessage']==title,'category':item['categoryName'],'category_no':item['categoryNo'],'public':item['allOpenPost'],'images':len(item.get('thumbnailList',[])),'missing_headings':missing,'pdf_checks':pdf_checks}
  row['pass']=row['title_match'] and row['category_no']==cat and row['public'] and row['images']==2 and not missing and any(p['match'] and p['magic'] for p in pdf_checks)
  out.append(row)
(H/'naver-four-public-verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False,indent=2));assert all(p['pass'] for p in out)
