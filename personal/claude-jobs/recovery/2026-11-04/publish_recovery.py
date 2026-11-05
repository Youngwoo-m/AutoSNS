"""2026-11-04 사용자 게시 지시로 건축4·안전4·5 누락 세 편만 기존 발행기로 복구."""
import hashlib,json,os,re,sys
from pathlib import Path
ROOT=Path('/Volumes/USB256/devAPP/AutoSNS');HERE=Path(__file__).resolve().parent
APPROVAL=HERE/'approval.json'
DATE='2026-11-04';ID='2026-11-04-building4-safety4-5';REPLY='블로거에 올려봐 주세요'
SLOTS={('building-daily',4),('safety-daily',4),('safety-daily',5)}
def authorize(path,job,title,body,today,entries,ledger):
 if not path or Path(path).resolve()!=APPROVAL.resolve():raise ValueError('이번 사용자 승인 파일만 허용')
 a=json.loads(APPROVAL.read_text())
 if (today!=DATE or a.get('date')!=DATE or a.get('approval_id')!=ID or a.get('user_reply')!=REPLY or a.get('blog_id')!='7628821136256904634'):raise ValueError('날짜·승인·계정 불일치')
 targets=a.get('targets',[])
 if len(targets)!=3 or {(t.get('job'),t.get('day')) for t in targets}!=SLOTS:raise ValueError('이번 세 편 이외 예외 금지')
 exam={'building-daily':'건축시공기술사','safety-daily':'건설안전기술사'}.get(job)
 m=re.search(r'\| 하루 한 문제 ([45])일차$',title)
 if not exam or not title.startswith('['+exam+']') or not m or (job,int(m.group(1))) not in SLOTS:raise ValueError('종목·일차 불일치')
 day=int(m.group(1));target=next(t for t in targets if t['job']==job and t['day']==day);sha=hashlib.sha256(body.encode()).hexdigest()
 if target.get('title')!=title or target.get('html_sha256')!=sha:raise ValueError('정확 제목·원고 해시 불일치')
 if ledger.get('approval_id')!=ID or not isinstance(ledger.get('attempts'),dict):raise ValueError('원장 불일치')
 slot=job+':'+str(day)
 if slot in ledger['attempts']:raise ValueError('이미 시도함: 공개·예약 상태 확인 후 수동 복구 필요')
 if any(p.get('title','').startswith('['+exam+']') and re.search(r'\| 하루 한 문제 '+str(day)+r'일차$',p.get('title','')) for p in entries):raise ValueError('동일 종목·일차가 이미 공개·예약·초안에 존재')
 return {'approval_id':ID,'slot':slot,'title':title,'html_sha256':sha,'date':today,'approval_sha256':hashlib.sha256(APPROVAL.read_bytes()).hexdigest()}
def main():
 if os.environ.get('AX_LOCKED')!='1':
  os.execv(sys.executable,[sys.executable,str(ROOT/'shared/axlock.py'),'run','--job','engineer-nov4-approved-recovery','--',sys.executable,str(Path(__file__).resolve()),*sys.argv[1:]])
 sys.path.insert(0,str(ROOT/'personal/claude-jobs'))
 import publish_engineer_blogger as pub
 pub.RECOVERY_DATE=DATE;pub.RECOVERY_ID=ID;pub.RECOVERY_REPLY=REPLY;pub.RECOVERY_SLOTS=SLOTS
 pub.RECOVERY_LEDGER=HERE/'ledger.json';pub.recovery_authorization=authorize
 return pub.main()
if __name__=='__main__':
 try:sys.exit(main())
 except Exception as e:print(json.dumps({'status':'error','message':type(e).__name__+': '+str(e)},ensure_ascii=False));sys.exit(1)
