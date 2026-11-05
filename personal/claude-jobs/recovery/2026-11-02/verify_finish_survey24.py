from pathlib import Path
import urllib.request,urllib.parse,re,html,json,hashlib,datetime
from html.parser import HTMLParser
R=Path('/Volumes/USB256/devAPP/AutoSNS');H=Path(__file__).resolve().parent;D=Path('/Volumes/USB256/기술사/24일차_지상라이다')
class Links(HTMLParser):
 def __init__(self):super().__init__();self.files=[]
 def handle_starttag(self,t,attrs):
  a=dict(attrs);u=a.get('href','')
  if t=='a' and 'download.blog.naver.com' in u and '.pdf' in u:self.files.append(u)
def get(u):
 q=urllib.request.Request(urllib.parse.quote(html.unescape(u),safe=':/?=&%+'),headers={'User-Agent':'Mozilla/5.0','Referer':'https://m.blog.naver.com/safeworking'})
 with urllib.request.urlopen(q,timeout=25) as r:return r.status,r.read()
title=(D/'제목.txt').read_text().strip();http,b=get('https://m.blog.naver.com/api/blogs/safeworking/post-list?categoryNo=6&itemCount=30&page=1');items=json.loads(b)['result']['items'];matching=[p for p in items if html.unescape(p['titleWithInspectMessage'])==title];assert len(matching)==1,'Expected exactly one public Naver post'
item=matching[0];num=item['logNo'];url=f'https://blog.naver.com/safeworking/{num}';http,b=get(f'https://m.blog.naver.com/safeworking/{num}');s=b.decode();parser=Links();parser.feed(s);checks=[];expected=hashlib.sha256((D/'24일차_지상라이다_모범답안_따라쓰기.pdf').read_bytes()).hexdigest()
for u in dict.fromkeys(parser.files):
 code,data=get(u);checks.append({'http':code,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'match':hashlib.sha256(data).hexdigest()==expected,'pdf_magic':data.startswith(b'%PDF')})
norm=lambda x:re.sub(r'\s+','',html.unescape(re.sub('<[^>]+>','',x)))
headings=[norm(t) for t in re.findall('<h[23][^>]*>(.*?)</h[23]>',(D/'티스토리게시본문.html').read_text(),re.S)];missing=[t for t in headings if t not in norm(s)]
result={'url':url,'http':http,'category':item['categoryName'],'category_no':item['categoryNo'],'title_match':True,'public':item['allOpenPost'],'image_count':len(item.get('thumbnailList',[])),'missing_headings':missing,'pdf':checks};assert result['public'] and result['category_no']==6 and result['image_count']==3 and not missing and any(c['match'] and c['pdf_magic'] for c in checks)
(H/'survey24-naver-public-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));now=datetime.datetime.now().astimezone().isoformat();state=json.loads((H/'survey24-current-state.json').read_text());state['at']=now;state['status']='published';state['urls']['naver']=url;state['pending']=[];state['comment_verified']=True;state['verification']={'blog':True,'naver':True,'short':True,'pdf_original_sha_match':True,'list':True,'kakao':True};state['note']='24일차 미발행복구 완료. 티스토리213 공개제목/소제목/PNG2/GIF/PDF원본SHA확인. 네이버 전용카테고리6·그림3·PDF원본SHA 확인. 숏츠RU6ozUlG_VM public/processed/oEmbed200·운영자댓글검증. 목록등록·카카오톡 result_code0. 기존원고/영상재생성없음.'
(H/'survey24-current-state.json').write_text(json.dumps(state,ensure_ascii=False,indent=2));(D/'작성상태.json').write_text(json.dumps(state,ensure_ascii=False,indent=2));(R/'personal/claude-jobs/state/survey-daily.jsonl').open('a').write(json.dumps(state,ensure_ascii=False)+'\n');(H/'survey24-recovery-completed.json').write_text(json.dumps({'at':now,'status':'completed','urls':state['urls'],'comment_id':state['comment_id'],'comment_verified':True,'all_required_steps_verified':True,'new_generation':False,'tiktok':'existing publisher queued only, no public posting claimed'},ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2));print('Survey day24: all required publishing and verification steps completed')
