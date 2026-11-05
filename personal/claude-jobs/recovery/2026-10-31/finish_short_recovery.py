"""현재 한 건의 승인된 발행이 잠금을 통과한 뒤 검증·댓글·기록만 마무리한다."""
from pathlib import Path
import datetime,json,subprocess,time,urllib.request,urllib.parse
ROOT=Path('/Volumes/USB256/devAPP/AutoSNS')
OUT=ROOT/'GeoAI_NA/claude-jobs/recovery/2026-10-31/least-squares-short'
PYTHON=ROOT/'dept/youtube-shorts-auto/.venv/bin/python'
TOOL=ROOT/'dept/youtube-shorts-auto/geoai_short_post.py'
AXLOCK=ROOT/'shared/axlock.py'

def save(name,data):
 (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2))

def tool(args,job):
 p=subprocess.run(['python3',str(AXLOCK),'run','--job',job,'--',str(PYTHON),str(TOOL),*args],cwd=ROOT,capture_output=True,text=True)
 lines=p.stdout.strip().splitlines()
 try:return json.loads(lines[-1])
 except Exception:return {'status':'error','reason':'tool_result_unavailable','exit':p.returncode}

def main():
 if (OUT/'recovery-completed.json').exists():return
 admission=(OUT/'final-admission.json').stat().st_mtime
 deadline=time.time()+2400
 while time.time()<deadline:
  f=OUT/'upload-result.json'
  if f.exists() and f.stat().st_mtime>=admission:
   try:r=json.loads(f.read_text());break
   except (ValueError,OSError):pass
  time.sleep(5)
 else:
  save('completion-monitor.json',{'status':'waiting_profile_timeout','published_confirmed':False});return
 if r.get('status') not in ('uploaded','duplicate') or not r.get('video_id'):
  save('completion-monitor.json',{'status':'upload_not_confirmed','result':r});return
 vid=r['video_id'];info={}
 for _ in range(8):
  info=tool(['check','--video-id',vid],'engineer-recovery-check')
  save('post-upload-check.json',info)
  if info.get('privacy')=='public' and info.get('channel_ok') is True and info.get('upload_status')=='processed':break
  time.sleep(10)
 else:
  save('completion-monitor.json',{'status':'public_processing_unconfirmed','video_id':vid,'check':info});return
 expected=(OUT/'제목.txt').read_text().strip()
 if info.get('title')!=expected:
  save('completion-monitor.json',{'status':'title_mismatch_manual_review','check':info});return
 url='https://www.youtube.com/shorts/'+vid
 public={}
 try:
  endpoint='https://www.youtube.com/oembed?'+urllib.parse.urlencode({'url':'https://www.youtube.com/watch?v='+vid,'format':'json'})
  with urllib.request.urlopen(urllib.request.Request(endpoint,headers={'User-Agent':'Mozilla/5.0'}),timeout=30) as response:
   body=json.load(response);public={'http_status':response.status,'title':body.get('title'),'author_name':body.get('author_name'),'author_url':body.get('author_url')}
 except Exception as exc:public={'status':'unavailable','error_type':type(exc).__name__}
 save('public-oembed-check.json',public)
 comment=tool(['comment','--video-id',vid,'--text','관련 학습자료(창작 연습문제·따라쓰기 PDF): https://na-geoai.tistory.com/42','--go','--job','engineer-least-squares-recovery'],'engineer-recovery-comment')
 save('comment-result.json',comment)
 now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()
 record={'at':now,'status':'published','title':expected,'urls':{'short':url,'related_blog':'https://na-geoai.tistory.com/42'},'topic':'최소제곱법·경중률','recovery_for':'과거 미사용 최소제곱 숏츠; 정기 일차카운터 변경 없음','video_id':vid,'calc':{'verdict':'ok','independent_examples':2},'review':{'verdict':'fix','fixed':6,'sources_opened':6},'humanizer':'2회','public_check':info,'oembed':public,'comment':comment,'new_paid_api_or_image_credits':0}
 with (ROOT/'personal/claude-jobs/state/engineer-backlog-recovery.jsonl').open('a') as stream:stream.write(json.dumps(record,ensure_ascii=False)+'\n')
 source=ROOT/'GeoAI_NA/engineer-video-output/premade/2026-10-29-survey-am'
 (source/'used.txt').write_text(now+'\n최소제곱법 과거 미사용분 수정 복구\n'+url+'\n원본 대신 검토된 recovery/2026-10-31/least-squares-short/short.mp4 사용\n')
 save('recovery-completed.json',record)
 statefile=OUT.parent/'실행상태.json';state=json.loads(statefile.read_text());state['status']='partial_completed_remaining_blocked';state['short'].update(status='published',url=url,privacy='public',comment_verified=comment.get('comment_verified',False));state['publication_completed_this_recovery']=1;statefile.write_text(json.dumps(state,ensure_ascii=False,indent=2))
 print(json.dumps({'status':'published','url':url,'comment':comment.get('status'),'remaining':'Blogger daily cap; building content corrections; daily1 not authored'},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
