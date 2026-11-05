from pathlib import Path
import json,subprocess,sys
R=Path('/Volumes/USB256/devAPP/AutoSNS');HERE=Path(__file__).resolve().parent
rows=json.loads((HERE/'first-second-day-publishing-progress.json').read_text())['posts']
for ex in ['building','safety']:
 p=R/'site/geoai-site'/f'{ex}-questions/published.json';backup=HERE/f'{ex}-published.before-four-posts.json'
 if not backup.exists():backup.write_bytes(p.read_bytes())
for row in rows:
 d=next((R/'GeoAI_NA'/f"{row['exam']}-engineer-writing").glob(f"{row['day']:02}일차_*"))
 subprocess.run([sys.executable,str(R/'GeoAI_NA/engineer-question-worker/queue.py'),'--exam',row['exam'],'add-post','--url',row['urls']['tistory'],'--title',(d/'제목.txt').read_text().strip(),'--date','2026-10-31','--kind','daily','--day',str(row['day']),'--tags',(d/'태그.txt').read_text().strip(),'--pdf'],check=True,cwd=R)
subprocess.run([sys.executable,str(R/'GeoAI_NA/engineer-question-worker/deploy_full.py')],check=True,cwd=R)
