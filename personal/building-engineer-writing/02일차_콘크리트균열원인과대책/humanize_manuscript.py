from pathlib import Path
import json,subprocess,os,re
OUT=Path(__file__).resolve().parent
m=json.loads((OUT/'manuscript-v1.json').read_text())
env={k:v for k,v in os.environ.items() if not k.startswith(('ANTHROPIC_','CLAUDE_CODE_USE_','AWS_','GOOGLE_','AZURE_'))}
for n in (1,2):
 required='숫자·날짜·출처·기출원문·수치·용어를 유지한다. 경화전/후는시간분류, 내구성은열화기구이며중첩되는조건을보존한다. 굳기전침하균열만다짐/재진동가능조건보존, 자기수축을살수만으로완전억제단정금지. 답안작성요령은문어체, 답안명사형. 첫차는번역투·추상명사·과장·어투혼용고침. 2차는반복어미·군더더기를다시검토. 배점25점/권장25분은공식시간과구별.'
 prompt=f'''건축시공기술사 원고 humanizer-kr {n}차. 1차는번역투·명사화·과장·어투혼용, 2차는반복·밋밋함·군더더기 재검토. 설명친절해요체, 답안/따라쓰기PDF는문어체개조식, 답안작성요령은문어체. 숫자·날짜·단위·출처·고유명사·유효한조건을바꾸지마세요. 허위경력·채점단정 금지. {required}
전체원고를다시출력하지말고정확한JSON Pointer문자열leaf교체만JSON객체로반환: {{"pass":{n},"changes":[{{"path":"/intro/0","old":"원래값전체","new":"교체문장전체","reason":"이유"}}],"notes":[]}}. 기존path만사용, 배열삽입삭제금지. 원고:\n'''+json.dumps(m,ensure_ascii=False)
 rawfile=OUT/f'humanizer-pass{n}-raw.json'
 if rawfile.exists():d=json.loads(rawfile.read_text())
 else:
  r=subprocess.run(['/usr/local/bin/claude','-p','--model','sonnet','--tools','','--setting-sources','','--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--no-session-persistence','--no-chrome','--output-format','json',prompt],cwd='/private/tmp',env=env,capture_output=True,text=True,timeout=240)
  d=json.loads(r.stdout);assert r.returncode==0 and not d.get('is_error'),d.get('result')
 (OUT/f'humanizer-pass{n}-raw.json').write_text(json.dumps(d,ensure_ascii=False,indent=2))
 s=re.sub(r'^```(?:json)?\s*|\s*```$','',d['result'].strip());ed=json.loads(s)
 for patch in ed['changes']:
  parts=patch['path'].lstrip('/').split('/');obj=m
  try:
   for part in parts[:-1]:obj=obj[int(part)] if isinstance(obj,list) else obj[part]
   key=int(parts[-1]) if isinstance(obj,list) else parts[-1]
   assert obj[key]==patch['old']
  except (IndexError,KeyError,AssertionError):
   hits=[]
   def walk(o,path=()):
    if isinstance(o,dict):
     for k,v in o.items():
      if isinstance(v,str) and v==patch['old']:hits.append((o,k,path+(str(k),)))
      elif isinstance(v,(dict,list)):walk(v,path+(str(k),))
    elif isinstance(o,list):
     for k,v in enumerate(o):
      if isinstance(v,str) and v==patch['old']:hits.append((o,k,path+(str(k),)))
      elif isinstance(v,(dict,list)):walk(v,path+(str(k),))
   walk(m);assert len(hits)==1,(patch['path'],len(hits))
   obj,key,path=hits[0];patch['resolved_path']='/'+'/'.join(path)
  obj[key]=patch['new']
 (OUT/f'humanizer-pass{n}.json').write_text(json.dumps(ed,ensure_ascii=False,indent=2));(OUT/f'manuscript-v{n+1}.json').write_text(json.dumps(m,ensure_ascii=False,indent=2))
 print('pass',n,'patches',len(ed['changes']),flush=True)
(OUT/'manuscript-final.json').write_text(json.dumps(m,ensure_ascii=False,indent=2))
