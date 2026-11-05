from pathlib import Path
import json,os,re,subprocess
OUT=Path(__file__).resolve().parent
public=json.loads((OUT/'public-edit-excerpts.json').read_text())
fetch=json.loads((OUT/'before-public-fetch.json').read_text())
env={k:v for k,v in os.environ.items() if not k.startswith(('ANTHROPIC_','CLAUDE_CODE_USE_','AWS_','GOOGLE_','AZURE_'))}

def ask(prompt,label):
 r=subprocess.run(['/usr/local/bin/claude','-p','--model','sonnet','--tools','','--setting-sources','','--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--no-session-persistence','--no-chrome','--output-format','json',prompt],cwd='/private/tmp',env=env,capture_output=True,text=True,timeout=120)
 try:d=json.loads(r.stdout)
 except Exception:raise RuntimeError('subscription_output_unavailable_no_fallback')
 (OUT/(label+'-cli.json')).write_text(json.dumps(d,ensure_ascii=False,indent=2))
 assert r.returncode==0 and not d.get('is_error'),'subscription_failed_no_fallback'
 s=d.get('result','').strip();s=re.sub(r'^```(?:json)?\s*','',s);s=re.sub(r'\s*```$','',s)
 data=json.loads(s);(OUT/(label+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2));return data

payload={'source_url':public['source_url'],'http_status':fetch['http'],'body_sha256':fetch['body_sha256'],'data_class':'already publicly accessible educational article; no unpublished draft or private data','excerpts':[p['text'] for p in public['paragraphs']]}
(OUT/'egress-public-only-evidence.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2))
first=ask('''사용자가 자신의 공개 건축시공 입문글 보완을 요청했습니다. 저장소 공통규칙에 따라 Claude로 편집합니다. 아래는 https://na-geoai.tistory.com/182 에서 HTTP200으로 누구나 읽을수있는 공개 문장만 추출한 것입니다. 미공개로컬초안·자격증명·내부문서가 아닙니다.
humanizer-kr 1차: 번역투/과장/어투혼합을 줄이며 친절한 해요체로 최소수정. 사실·숫자·주제·경력·법령·새예시추가금지. 공개 연재예고문을 수정하여 글 구성은 문제와 해설, 답안 예시, 그림과 표, 놓치기 쉬운 점, 참고자료와 따라쓰기 PDF를 안내하도록 하고 독립 '답안 목차'예고와 내부문체규칙 설명은 삭제합니다. 5년/7개회차/한중콘크리트주제는그대로. 요청안내의정답예시는답안예시로표현을바꾸고기존확인시각밤11시는보존.
JSON만반환: {"pass":1,"future_paragraph":"수정된연재예고문단","request_sentence":"수정된요청안내문장","audit_notes":[],"facts_preserved":true}.
공개자료:\n'''+json.dumps(payload,ensure_ascii=False),'humanizer-pass1')
second=ask('''같은 공개 글 보완의 humanizer-kr 2차입니다. 1차에서 고친 두 문장을 다시 읽고 반복 어미/군더더기만 최소로 고치세요. 사실/숫자/용어/주제/밤11시/5년7개회차는그대로, 독립목차예고·내부편집규칙 설명은추가금지. 두 문장 외원고는전송하지않으며공개원고에서파생된수정안입니다. JSON만 {"pass":2,"future_paragraph":"...","request_sentence":"...","audit_notes":[],"facts_preserved":true}.
1차수정안:\n'''+json.dumps(first,ensure_ascii=False),'humanizer-pass2')
assert first.get('facts_preserved') and second.get('facts_preserved')
for k in ('future_paragraph','request_sentence'):assert isinstance(second[k],str) and '<' not in second[k]
print(json.dumps({'status':'edited_public_excerpts_only','model_usage':list(json.loads((OUT/'humanizer-pass2-cli.json').read_text()).get('modelUsage',{})),'pass_count':2},ensure_ascii=False))
