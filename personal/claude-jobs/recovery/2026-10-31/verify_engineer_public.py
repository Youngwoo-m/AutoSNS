import argparse,hashlib,html,json,re,urllib.request,urllib.parse
from pathlib import Path
from html.parser import HTMLParser
class Links(HTMLParser):
 def __init__(self):super().__init__();self.items=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  for k in ('data-url','href','src'):
   u=a.get(k,'')
   if ('blog.kakaocdn.net' in u and (k=='data-url' or '.pdf' in u)) or ('geoai-na.netlify.app/' in u and '/materials/' in u):self.items.append(u)
def get(u):
 u=urllib.parse.quote(html.unescape(u),safe=':/?=&%+');q=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'})
 with urllib.request.urlopen(q,timeout=30) as r:return r.status,r.read(),r.headers.get('Content-Type','')
p=argparse.ArgumentParser();p.add_argument('--url',required=True);p.add_argument('--folder',required=True);p.add_argument('--out',required=True);a=p.parse_args();d=Path(a.folder)
status,b,typ=get(a.url);s=b.decode();title=html.unescape(re.findall('<title[^>]*>(.*?)</title>',s,re.S)[0]);expected_title=(d/'제목.txt').read_text().strip();parser=Links();parser.feed(s)
assets={hashlib.sha256(f.read_bytes()).hexdigest():f.name for f in d.iterdir() if f.name=='banner.png' or (f.suffix in ['.png','.pdf'] and not f.name.startswith(('PDF','Qnet','preview','html')) and ('흐름도' in f.name or '단계별확인' in f.name or f.suffix=='.pdf'))}
checks=[];seen=set()
for u in dict.fromkeys(parser.items):
 code,data,ctype=get(u);digest=hashlib.sha256(data).hexdigest();name=assets.get(digest)
 checks.append({'name':name,'http':code,'content_type':ctype,'bytes':len(data),'sha256':digest,'matches_local_asset':bool(name),'pdf_magic':data.startswith(b'%PDF') if '.pdf' in u else None})
 if name:seen.add(digest)
expected_html=(d/('Blogger게시본문.html' if 'blogspot' in a.url else '티스토리게시본문.html')).read_text()
def norm(text):return re.sub(r'\s+','',html.unescape(re.sub('<[^>]+>','',text)))
headings=[norm(t) for t in re.findall(r'<h[23][^>]*>(.*?)</h[23]>',expected_html,re.S)]
missing_headings=[t for t in headings if t not in norm(s)]
result={'url':a.url,'http':status,'title':title,'expected_title':expected_title,'title_match':expected_title in title,'missing_headings':missing_headings,'expected_assets':list(assets.values()),'assets':checks,'all_assets_match':set(assets)<=seen,'raw_attachment_markers':bool(re.search(r'\[##_(?:Image|File)\|',s))}
Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2));assert not missing_headings and result['title_match'] and result['all_assets_match'] and not result['raw_attachment_markers']
