import json,time,urllib.request,wave
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PUBLIC=ROOT.parents[2]/'remotion-shorts/public/civil-day01'
while not (PUBLIC/'voice-1.wav').exists():time.sleep(5)
text='자세한 내용은 블로그에서 확인하세요.'
state=ROOT/'voice-4-clarity.json';audio=PUBLIC/'voice-4-clarity.wav'
def get(path):return json.load(urllib.request.urlopen('http://127.0.0.1:17493'+path,timeout=120))
if not audio.exists():
 if state.exists():g=json.loads(state.read_text())
 else:
  payload={'profile_id':'9ae4198e-a2c5-4604-9165-7d39adf0143c','text':text,'language':'ko','engine':'qwen','model_size':'0.6B','seed':19004,'normalize':True}
  req=urllib.request.Request('http://127.0.0.1:17493/generate',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
  g=json.load(urllib.request.urlopen(req,timeout=120));state.write_text(json.dumps(g,ensure_ascii=False,indent=2))
 print('closing_submitted',g['id'],flush=True)
 while g.get('status')!='completed':
  if g.get('status') in ['failed','cancelled']:raise RuntimeError(g)
  time.sleep(5);g=get('/history/'+g['id']);state.write_text(json.dumps(g,ensure_ascii=False,indent=2))
 audio.write_bytes(urllib.request.urlopen('http://127.0.0.1:17493/audio/'+g['id'],timeout=120).read())
with wave.open(str(audio)) as w:print('closing_duration',w.getnframes()/w.getframerate(),flush=True)
