from pathlib import Path
import json,urllib.request,urllib.parse,re,html,hashlib,datetime
R=Path('/Volumes/USB256/devAPP/AutoSNS');H=Path(__file__).resolve().parent
A=json.loads((H/'approval.json').read_text())
def get(u):
 import subprocess
 u=urllib.parse.quote(html.unescape(u),safe=':/?=&%')
 print('Checking '+u,flush=True)
 r=subprocess.run(['curl','-4','-f','-L','-sS','--connect-timeout','8','--max-time','20','--retry','1','-A','Mozilla/5.0',u],capture_output=True)
 if r.returncode:raise RuntimeError(u+': '+r.stderr.decode()[:200])
 return 200,r.stdout
def norm(s):return re.sub(r'\s+','',html.unescape(re.sub('<[^>]+>','',s)))
_,b=get('https://geoaina.blogspot.com/feeds/posts/default?alt=json&max-results=500');feed=json.loads(b)['feed'];assert not any(l['rel']=='next' for l in feed.get('link',[]));entries=feed.get('entry',[])
rows=[]
for t in A['targets']:
 ex=t['job'].split('-')[0];day=t['day'];d=Path(t['folder']);result=json.loads((H/f'{ex}-day{day}-blogger-go-result.json').read_text());assert result['status'] in ['published','duplicate'];url=result['url'];http,b=get(url);s=b.decode();assert t['title'] in html.unescape(re.findall('<title>(.*?)</title>',s,re.S)[0]);body=(d/'Blogger게시본문.html').read_text();assert hashlib.sha256(body.encode()).hexdigest()==t['html_sha256']
 headings=[norm(x) for x in re.findall(r'<h[23][^>]*>(.*?)</h[23]>',body,re.S)];assert all(x in norm(s) for x in headings)
 assets=list(dict.fromkeys(html.unescape(u) for u in re.findall(r'(?:href|src)="([^"]+)"',body) if f'/materials/day{day:02d}/' in u));checks=[]
 for u in assets:
  assert u in html.unescape(s)
  name=urllib.parse.unquote(urllib.parse.urlparse(u).path.rsplit('/',1)[-1]);local=d/name;assert local.exists(),name
  checks.append(dict(name=name,url=u,link_present=True,local_sha256=hashlib.sha256(local.read_bytes()).hexdigest(),download_verified=False,note='첨부 서버 연결 시간 초과: IPv4·기본 연결 모두 실패. 공개 다운로드 재확인 필요'))
 assert any(x['name'].endswith('.pdf') for x in checks)
 assert len([p for p in entries if p['title']['$t']==t['title']])==1
 rows.append(dict(job=t['job'],day=day,url=url,http=http,title_match=True,headings_verified=len(headings),assets=checks,public_title_copies=1))
(H/'public-verification.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()
for t,row in zip(A['targets'],rows):
 d=Path(t['folder']);p=d/'작성상태.json';state=json.loads(p.read_text());state.update(status='published',pending=[],pending_recoveries=[],updated_at=now);state.setdefault('urls',{})['blogger']=row['url'];state.setdefault('verification',{})['blogger']=True;state.pop('blogger_blocked',None);state['manual_blogger_recovery']={'approval_id':A['approval_id'],'public_verified':True,'duplicate_count':1,'asset_download_verified':False,'verification_note':'공개 본문과 링크 확인. 첨부 서버 연결 시간 초과로 다운로드 해시 재확인 미완료'};p.write_text(json.dumps(state,ensure_ascii=False,indent=2))
 m=d/'manifest.json'
 if m.exists():
  j=json.loads(m.read_text());j.update(status='published',public_channels=state['urls'],blogger_verified=True);m.write_text(json.dumps(j,ensure_ascii=False,indent=2))
 entry=dict(at=now,status='published',day=t['day'],title=t['title'],urls=state['urls'],verification=state['verification'],pending_recoveries=[],calc=state.get('calc','n/a'),review=state.get('source_review',state.get('review')),note='사용자 게시 지시로 Blogger 누락 사본만 이번 세 편 한정 복구. 공개 제목·소제목·첨부 링크·동일 제목 1건 확인. 첨부 서버 연결 시간 초과로 다운로드 해시 재확인 미완료. 일반 상한 유지.')
 with (R/'personal/claude-jobs/state'/f"{t['job']}.jsonl").open('a') as f:f.write(json.dumps(entry,ensure_ascii=False)+'\n')
(H/'recovery-completed.json').write_text(json.dumps(dict(at=now,status='published_with_asset_verification_pending',posts=rows,general_cap_unchanged=True),ensure_ascii=False,indent=2));print(json.dumps(rows,ensure_ascii=False))
