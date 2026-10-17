import json, time, urllib.request, wave
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PUBLIC=ROOT.parents[2]/'remotion-shorts/public/civil-day01'
LINES=[
 '흙 속의 공기를 줄여 치밀하게 만듭니다.',
 '함수비와 층 두께를 함께 관리하세요.',
 '잘 다져졌는지는 현장 시험으로 확인합니다.',
 '답안과 따라쓰기 자료는 블로그에서.',
]
(ROOT/'대본.txt').write_text('\n'.join(LINES)+'\n')
def request(path, data=None):
 req=urllib.request.Request('http://127.0.0.1:17493'+path, data=json.dumps(data).encode() if data else None, headers={'Content-Type':'application/json'})
 return json.load(urllib.request.urlopen(req,timeout=120))
records=[]
for i,line in enumerate(LINES,1):
 state=ROOT/f'voice-{i}.json';audio=PUBLIC/f'voice-{i}.wav'
 if not audio.exists():
  if state.exists():g=json.loads(state.read_text())
  else:
   g=request('/generate',{'profile_id':'9ae4198e-a2c5-4604-9165-7d39adf0143c','text':line,'language':'ko','engine':'qwen','model_size':'0.6B','seed':18001+i,'normalize':True})
   state.write_text(json.dumps(g,ensure_ascii=False,indent=2))
  print('submitted',i,g.get('id'),g.get('status'),flush=True)
  while g.get('status')!='completed':
   if g.get('status') in ['failed','cancelled']:raise RuntimeError(g)
   time.sleep(5);g=request('/history/'+g['id']);state.write_text(json.dumps(g,ensure_ascii=False,indent=2))
  audio.write_bytes(urllib.request.urlopen('http://127.0.0.1:17493/audio/'+g['id'],timeout=120).read())
 with wave.open(str(audio)) as w:duration=w.getnframes()/w.getframerate()
 records.append({'text':line,'duration':duration,'file':audio.name})
 print('completed',i,duration,flush=True)
(ROOT/'voice-timing.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
print('total_audio',sum(r['duration'] for r in records),flush=True)
