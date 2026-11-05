from pathlib import Path
import json,urllib.request,urllib.parse,re,html,hashlib,datetime
from html.parser import HTMLParser
R=Path('/Volumes/USB256/devAPP/AutoSNS');H=Path(__file__).resolve().parent
class Assets(HTMLParser):
 def __init__(self):super().__init__();self.urls=[]
 def handle_starttag(self,t,attrs):
  a=dict(attrs)
  for k in ['href','src']:
   u=a.get(k,'')
   if '/materials/day03/' in u:self.urls.append(u)
def get(u):
 q=urllib.request.Request(urllib.parse.quote(html.unescape(u),safe=':/?=&%'),headers={'User-Agent':'Mozilla/5.0'})
 with urllib.request.urlopen(q,timeout=30) as r:return r.status,r.read(),r.headers.get('Content-Type','')
now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat();out=[]
for ex in ['building','safety']:
 d=next((R/'GeoAI_NA'/f'{ex}-engineer-writing').glob('03일차_*'));result=json.loads((H/f'{ex}-day3-blogger-go-result.json').read_text());assert result['status']=='published';url=result['url'];status,b,ctype=get(url);s=b.decode();title=html.unescape(re.findall('<title>(.*?)</title>',s,re.S)[0]);expectedtitle=(d/'제목.txt').read_text().strip();body=(d/'Blogger게시본문.html').read_text();norm=lambda x:re.sub(r'\s+','',html.unescape(re.sub('<[^>]+>','',x)))
 headings=[norm(t) for t in re.findall(r'<h[23][^>]*>(.*?)</h[23]>',body,re.S)];missing=[t for t in headings if t not in norm(s)];assert not missing and expectedtitle in title
 names=re.findall(r'data-ax-attach="([^"]+)"',(d/'티스토리게시본문.html').read_text());expected={hashlib.sha256((d/n).read_bytes()).hexdigest():n for n in names};parser=Assets();parser.feed(s);checks=[]
 for u in dict.fromkeys(parser.urls):
  http,data,ct=get(u);sha=hashlib.sha256(data).hexdigest();checks.append({'name':expected.get(sha),'http':http,'sha256':sha,'bytes':len(data),'pdf_magic':data.startswith(b'%PDF') if '.pdf' in u else None})
 assert len(expected)==3 and set(expected)<={x['sha256'] for x in checks}
 row={'exam':ex,'day':3,'url':url,'http':status,'title_match':True,'missing_headings':missing,'assets':checks,'pass':True};out.append(row)
(H/'day3-blogger-public-verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
_,b,_=get('https://geoaina.blogspot.com/feeds/posts/default?alt=json&max-results=500');feed=json.loads(b)['feed'];assert not any(l['rel']=='next' for l in feed.get('link',[]));entries=feed.get('entry',[])
for row in out:
 d=next((R/'GeoAI_NA'/f"{row['exam']}-engineer-writing").glob('03일차_*'));title=(d/'제목.txt').read_text().strip();matches=[p for p in entries if p['title']['$t']==title];assert len(matches)==1
 row['public_title_copies']=1;statefile=d/'작성상태.json';state=json.loads(statefile.read_text());state['status']='published';state.setdefault('urls',{})['blogger']=row['url'];state.setdefault('verification',{})['blogger']=True;state['pending']=[];state['pending_recoveries']=[];state['updated_at']=now;state['manual_blogger_recovery']={'approval_id':'2026-11-01-building-safety-day3','public_verified':True,'duplicate_count':1};statefile.write_text(json.dumps(state,ensure_ascii=False,indent=2))
 mf=d/'manifest.json'
 if mf.exists():
  m=json.loads(mf.read_text());m['status']='published';m['public_channels']=state['urls'];m['blogger_verified']=True;mf.write_text(json.dumps(m,ensure_ascii=False,indent=2))
 entry={'at':now,'status':'published','day':3,'title':title,'urls':state['urls'],'verification':state['verification'],'calc':state.get('calc','n/a'),'review':state.get('source_review',state.get('review')),'artifacts':str(d),'pending_recoveries':[],'note':'중복확인후 Blogger 누락분만 사용자 이번두편 예외승인으로복구. 공개제목·모든소제목·그림2·PDF SHA·공개목록정확1건확인. 기존티스토리·네이버 재발행없음.'};f=R/'personal/claude-jobs/state'/f"{row['exam']}-daily.jsonl";f.open('a').write(json.dumps(entry,ensure_ascii=False)+'\n')
(H/'day3-blogger-public-verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));(H/'recovery-completed.json').write_text(json.dumps({'at':now,'status':'completed','posts':out,'duplicate_inserts':0,'archived_completed_threads':15,'general_cap_unchanged':True,'exception_scope':'건축·안전3일차두편만'},ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False,indent=2))
