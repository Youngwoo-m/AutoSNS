import argparse,json,subprocess,sys
from pathlib import Path
R=Path('/Volumes/USB256/devAPP/AutoSNS');H=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--mode',choices=['dry','go'],required=True);a=p.parse_args()
approval=H/'blogger-two-post-exception-approval.json';targets=json.loads(approval.read_text())['targets']
for t in targets:
 d=Path(t['folder']);ex=t['job'].split('-')[0];cmd=[str(R/'dept/naver-blog-auto/.venv/bin/python'),str(H/'publish_two_recovery.py'),'--job',t['job'],'--html',str(d/'Blogger게시본문.html'),'--title',t['title'],'--labels',(d/'태그.txt').read_text().strip(),'--recovery-approval',str(approval),'--'+a.mode]
 result=subprocess.run(cmd,cwd=R,capture_output=True,text=True);log=result.stdout+result.stderr;(H/f'{ex}-day3-blogger-{a.mode}.log').write_text(log)
 lines=[l for l in result.stdout.splitlines() if l.startswith('{')];out=json.loads(lines[-1]) if lines else {'status':'error','message':log[-800:]};(H/f'{ex}-day3-blogger-{a.mode}-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps({'exam':ex,'returncode':result.returncode,'result':out},ensure_ascii=False),flush=True)
 if result.returncode:sys.exit(result.returncode)
