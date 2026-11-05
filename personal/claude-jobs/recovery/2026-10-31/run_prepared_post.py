"""검토된 네 원고의 기존 발행기 호출 인자를 파일에서 읽는 운영 보조 도구."""
import argparse,json,subprocess,sys,re
from pathlib import Path
R=Path('/Volumes/USB256/devAPP/AutoSNS');HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--exam',choices=['building','safety'],required=True);p.add_argument('--day',type=int,choices=[1,2],required=True);p.add_argument('--channel',choices=['tistory','blogger','naver'],required=True);p.add_argument('--mode',choices=['dry','go'],required=True);p.add_argument('--url');a=p.parse_args()
dirs=list((R/'GeoAI_NA'/f'{a.exam}-engineer-writing').glob(f'{a.day:02}일차_*'));assert len(dirs)==1;d=dirs[0]
title=(d/'제목.txt').read_text().strip();tags=(d/'태그.txt').read_text().strip();category={'building':'건축시공기술사','safety':'건설안전기술사'}[a.exam];leaf=R/'dept/naver-blog-auto';py=str(leaf/'.venv/bin/python');job=a.exam+'-daily'
if a.channel=='tistory':
 cmd=[sys.executable,str(R/'shared/axlock.py'),'run','--job',f'{a.exam}-day{a.day}-{a.mode}','--',py,str(leaf/'tistory_post.py'),'--html',str(d/'티스토리게시본문.html'),'--title',title,'--category',category,'--tags',tags,'--'+a.mode,'--job',job]
elif a.channel=='blogger':
 cmd=[py,str(R/'personal/claude-jobs/publish_engineer_blogger.py'),'--job',job,'--html',str(d/'Blogger게시본문.html'),'--title',title,'--labels',tags,'--recovery-approval',str(HERE/'blogger-four-post-exception-approval.json'),'--'+a.mode]
else:
 assert a.url and re.fullmatch(r'https://na-geoai\.tistory\.com/\d+',a.url)
 cmd=[py,str(leaf/'naver_crosspost_personal.py'),'--tistory-url',a.url,'--category',category,'--tags',tags,'--'+a.mode,'--job',job]
logfile=HERE/f'{a.exam}-day{a.day}-{a.channel}-{a.mode}.log'
with logfile.open('w') as output:
 result=subprocess.run(cmd,cwd=R,stdout=output,stderr=subprocess.STDOUT,text=True)
report=logfile.read_text()
print(report,flush=True)
lines=[l for l in report.splitlines() if l.startswith('{')]
if lines:
 try:(HERE/f'{a.exam}-day{a.day}-{a.channel}-{a.mode}-result.json').write_text(json.dumps(json.loads(lines[-1]),ensure_ascii=False,indent=2))
 except ValueError:pass
sys.exit(result.returncode)
