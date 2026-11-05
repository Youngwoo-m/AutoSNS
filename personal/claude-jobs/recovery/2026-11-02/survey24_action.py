import argparse,json,subprocess,sys
from pathlib import Path
R=Path('/Volumes/USB256/devAPP/AutoSNS');H=Path(__file__).resolve().parent;D=Path('/Volumes/USB256/기술사/24일차_지상라이다');URL='https://na-geoai.tistory.com/213'
p=argparse.ArgumentParser();p.add_argument('action',choices=['naver','short','comment']);p.add_argument('--mode',choices=['dry','go'],required=True);p.add_argument('--video-id');a=p.parse_args();leaf=R/'dept/naver-blog-auto';yt=R/'dept/youtube-shorts-auto'
if a.action=='naver':
 cmd=[str(leaf/'.venv/bin/python'),str(leaf/'naver_crosspost_personal.py'),'--tistory-url',URL,'--category','측량기술사','--tags',(D/'태그.txt').read_text().strip(),'--'+a.mode,'--job','survey-daily-recovery']
else:
 if a.action=='short':
  desc=(D/'숏츠/설명.txt').read_text().replace('{{BLOG_URL}}',URL);assert desc.splitlines()[0]==URL;description=H/'survey24-short-description.txt';description.write_text(desc)
  cmd=[str(yt/'.venv/bin/python'),str(yt/'geoai_short_post.py'),'upload','--video',str(D/'숏츠/short.mp4'),'--title',(D/'숏츠/title.txt').read_text().strip(),'--description-file',str(description),'--tags',(D/'숏츠/tags.txt').read_text().strip(),'--synthetic','--'+a.mode,'--job','survey-daily-recovery']
 else:
  assert a.video_id
  cmd=[str(yt/'.venv/bin/python'),str(yt/'geoai_short_post.py'),'comment','--video-id',a.video_id,'--text','자세한 답안과 따라쓰기 PDF: '+URL,'--'+a.mode,'--job','survey-daily-recovery']
log=H/f'survey24-{a.action}-{a.mode}.log'
with log.open('w') as f:result=subprocess.run(cmd,cwd=R,stdout=f,stderr=subprocess.STDOUT,text=True)
s=log.read_text();print(s,flush=True);lines=[l for l in s.splitlines() if l.startswith('{')]
if lines:
 try:(H/f'survey24-{a.action}-{a.mode}-result.json').write_text(json.dumps(json.loads(lines[-1]),ensure_ascii=False,indent=2))
 except ValueError:pass
sys.exit(result.returncode)
