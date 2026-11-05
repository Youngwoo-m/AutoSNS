from pathlib import Path
import json,hashlib,urllib.request,urllib.parse,re,html
from html.parser import HTMLParser
D=Path('/Volumes/USB256/기술사/24일차_지상라이다');H=Path(__file__).resolve().parent
class Links(HTMLParser):
 def __init__(self):super().__init__();self.urls=[]
 def handle_starttag(self,t,attrs):
  a=dict(attrs)
  for k in ['data-url','href']:
   u=a.get(k,'')
   if 'blog.kakaocdn.net' in u and (k=='data-url' or '.pdf' in u):self.urls.append(u)
def get(u):
 q=urllib.request.Request(urllib.parse.quote(html.unescape(u),safe=':/?=&%+'),headers={'User-Agent':'Mozilla/5.0'})
 with urllib.request.urlopen(q,timeout=25) as r:return r.status,r.read()
http,b=get('https://na-geoai.tistory.com/213');s=b.decode();parser=Links();parser.feed(s);source=(D/'티스토리게시본문.html').read_text();names=re.findall(r'data-ax-attach="([^"]+)"',source);expected={hashlib.sha256((D/n).read_bytes()).hexdigest():n for n in names};checks=[]
for u in dict.fromkeys(parser.urls):
 code,b=get(u);sha=hashlib.sha256(b).hexdigest();checks.append({'name':expected.get(sha),'http':code,'bytes':len(b),'sha256':sha,'pdf_magic':b.startswith(b'%PDF') if '.pdf' in u else None})
norm=lambda t:re.sub(r'\s+','',html.unescape(re.sub('<[^>]+>','',t)))
headings=[norm(t) for t in re.findall('<h[23][^>]*>(.*?)</h[23]>',source,re.S)];missing=[t for t in headings if t not in norm(s)];title=html.unescape(re.findall('<title>(.*?)</title>',s,re.S)[0]);result={'url':'https://na-geoai.tistory.com/213','http':http,'title_match':title==(D/'제목.txt').read_text().strip(),'missing_headings':missing,'assets':checks,'all_assets_match':set(expected)<={x['sha256'] for x in checks},'raw_tokens':bool(re.search(r'\[##_(?:Image|File)\|',s))};(H/'survey24-tistory-public-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2));assert result['title_match'] and not missing and result['all_assets_match'] and not result['raw_tokens']
