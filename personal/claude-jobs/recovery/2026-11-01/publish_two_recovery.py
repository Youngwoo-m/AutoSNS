"""사용자가 승인한 2026-11-01 건축·안전 3일차 두 편만 기존 발행기로 복구."""
import hashlib,json,os,re,sys
from pathlib import Path
ROOT=Path('/Volumes/USB256/devAPP/AutoSNS');HERE=Path(__file__).resolve().parent
APPROVAL=HERE/'blogger-two-post-exception-approval.json'
DATE='2026-11-01';ID='2026-11-01-building-safety-day3';REPLY='이번 두 편만 예외로 발행'
SLOTS={('building-daily',3),('safety-daily',3)}
def authorize(path,job,title,body,today,entries,ledger):
 if not path or Path(path).resolve()!=APPROVAL.resolve():raise ValueError('이번 사용자 승인 파일만 허용')
 a=json.loads(APPROVAL.read_text())
 if (today!=DATE or a.get('date')!=DATE or a.get('approval_id')!=ID or a.get('user_reply')!=REPLY or a.get('blog_id')!='7628821136256904634'):raise ValueError('날짜·승인·계정 불일치')
 targets=a.get('targets',[])
 if len(targets)!=2 or {(t.get('job'),t.get('day')) for t in targets}!=SLOTS:raise ValueError('이번 두 편 이외 예외 금지')
 exam={'building-daily':'건축시공기술사','safety-daily':'건설안전기술사'}.get(job)
 if not exam or not title.startswith('['+exam+']') or not title.endswith('| 하루 한 문제 3일차'):raise ValueError('종목·일차 불일치')
 target=next(t for t in targets if t['job']==job);sha=hashlib.sha256(body.encode()).hexdigest()
 if target.get('title')!=title or target.get('html_sha256')!=sha:raise ValueError('정확 제목·원고 해시 불일치')
 if ledger.get('approval_id')!=ID or not isinstance(ledger.get('attempts'),dict):raise ValueError('원장 불일치')
 slot=job+':3'
 if slot in ledger['attempts']:raise ValueError('이미 시도함: 공개·예약 상태 확인 후 수동 복구 필요')
 if any(p.get('title','').startswith('['+exam+']') and re.search(r'\| 하루 한 문제 3일차$',p.get('title','')) for p in entries):raise ValueError('동일 종목·일차가 이미 공개·예약·초안에 존재')
 return {'approval_id':ID,'slot':slot,'title':title,'html_sha256':sha,'date':today,'approval_sha256':hashlib.sha256(APPROVAL.read_bytes()).hexdigest()}
def main():
 if os.environ.get('AX_LOCKED')!='1':
  os.execv(sys.executable,[sys.executable,str(ROOT/'shared/axlock.py'),'run','--job','engineer-day3-approved-recovery','--',sys.executable,str(Path(__file__).resolve()),*sys.argv[1:]])
 sys.path.insert(0,str(ROOT/'personal/claude-jobs'))
 import publish_engineer_blogger as pub
 pub.RECOVERY_DATE=DATE;pub.RECOVERY_ID=ID;pub.RECOVERY_REPLY=REPLY;pub.RECOVERY_SLOTS=SLOTS
 pub.RECOVERY_LEDGER=HERE/'blogger-two-post-exception-ledger.json';pub.recovery_authorization=authorize
 return pub.main()
if __name__=='__main__':
 try:sys.exit(main())
 except Exception as e:print(json.dumps({'status':'error','message':type(e).__name__+': '+str(e)},ensure_ascii=False));sys.exit(1)
