from pathlib import Path
import json,hashlib,datetime
O=Path(__file__).resolve().parent
assets=['banner.png','위험성평가_흐름도.png','02일차_위험성평가_답안예시_따라쓰기.pdf']
manus=['티스토리게시본문.html','Blogger게시본문.html','final-content.json','제목.txt','태그.txt']
def info(n):
 p=O/n
 return {'name':n,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
m={'day':2,'title':(O/'제목.txt').read_text().strip(),'public_assets':[dict(info(n),intended_public_url='https://geoai-na.netlify.app/safety-questions/materials/day02/'+n) for n in assets],'manuscripts':{n:info(n) for n in manus},'review':{'calc':'pending','source':'pending'},'model':'Claude Max subscription, actual model claude-sonnet-5-5','humanizer_passes':2,'new_paid_api':False,'new_image_generation':False,'image_note':'기존 AI배경 재사용 및 Pillow 직접 도식'}
(O/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2))
print(json.dumps(m,ensure_ascii=False,indent=2))
