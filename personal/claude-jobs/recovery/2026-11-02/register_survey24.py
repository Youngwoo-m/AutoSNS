from pathlib import Path
import subprocess,sys,json,shutil
R=Path('/Volumes/USB256/devAPP/AutoSNS');H=Path(__file__).resolve().parent;D=Path('/Volumes/USB256/기술사/24일차_지상라이다')
f=R/'site/geoai-site/questions/published.json';backup=H/'survey-published-before-day24.json'
if not backup.exists():shutil.copyfile(f,backup)
subprocess.run([sys.executable,str(R/'GeoAI_NA/engineer-question-worker/queue.py'),'--exam','survey','add-post','--url','https://na-geoai.tistory.com/213','--title',(D/'제목.txt').read_text().strip(),'--date','2026-11-02','--kind','daily','--day','24','--tags',(D/'태그.txt').read_text().strip(),'--pdf'],check=True,cwd=R)
subprocess.run([sys.executable,str(R/'GeoAI_NA/engineer-question-worker/deploy_full.py')],check=True,cwd=R)
