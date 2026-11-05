from pathlib import Path
import json,subprocess,os,re
OUT=Path(__file__).resolve().parent
m=json.loads((OUT/'manuscript-v1.json').read_text())
env={k:v for k,v in os.environ.items() if not k.startswith(('ANTHROPIC_','CLAUDE_CODE_USE_','AWS_','GOOGLE_','AZURE_'))}
for n in (1,2):
 required='''첫차필수수정: answer5항의 '해당 조건의 표 값으로만 종료 판단'과PDF3쪽같은문장은강도표하나만종료요건처럼보임. 조건별소요강도와온도관리확인·책임기술자승인으로판단하도록교체. PDF2쪽'가혹 기상·300mm 이하'의조건을 '가혹기상 또는 단면300mm이하'로명시. PDF3쪽300/800경계줄에단면단위mm명시. PDF3쪽놓치기쉬운점의'표3.4-1값을해체강도로혼용'을혼용금지로고쳐지시뜻반대로읽히지않게. 노출강도표첫헤더'구조물의 노출 (MPa)'는'노출 상태'로바꾸고다른세헤더에는MPa값임을명시. 외기온표행의한중적용판정요약에4℃이하뿐아니라향후24시간최저0℃이하등다른조건도함께있음을짧게명시. 자기온도기록계기록항목에는'원칙;동결위험작은경우주위기온만기록가능'예외도적절히짧게반영. disclosure의구성재료2.1/배합2.2.2개정시행일상세는문제범위와무관하므로삭제하고사업별적용판·계약경과조치확인만남기기. 기존공식수치의의미바꾸기/새사실추가금지.''' if n==1 else '2차에서는1차수정결과의사실·조건보존확인, 군더더기/반복어미/마지막단서과잉반복만살핀다. 글머리총4문장이면안녕하세요단독문장을다음문장에합쳐총3문장으로고치고, PDF의지시문은부정/금지의뜻이바뀌지않게한다. 답안명사형·이론문어체유지.'
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
