from pathlib import Path
import os,json,subprocess,re
OUT=Path(__file__).resolve().parent
law=(OUT/'법령_직접확인.txt').read_text();q=json.loads((OUT/'기출근거.json').read_text())['selected']
prompt='''건설안전기술사 첫 정기 학습글 원고를 작성하세요. 한국어. 아래 공식 근거 외 수치·법령·사건을 추가하지 마세요. 같은 주제의 기존 토목시공 글은 해체강도/시기 중심이므로 이번은 강관 동바리 시공 전 구조검토·기초침하·상하부지지·편심타설·조립/해체 안전절차에 집중하세요. '강관동바리'를 전부 파이프서포트라고 단정하지 말고 현장 유형에 따라 적용조항을 구분하세요. 파이프서포트의 3개이상 연결금지/4개이상볼트 또는 전용철물/높이3.5m초과시 높이2m이내마다2방향 수평연결재라는 조건은 정확히 쓰세요. 높이3.5m이하를 무보강허용으로 해석하지 말고 구조검토조립도공통의무는 유지. 3.5m와 2m는 파이프서포트 조건이며 시스템동바리 겹침길이규칙을 섞지마세요. 강도·해체일수 임의값 금지. 해체는 설계도서양생기간 준수와 구조안전성확인·해체계획에 따른 순서 관리로 설명하세요. 법령의 직접의무와 학습상 해설을 구분하세요.
제목: '[건설안전기술사] 거푸집·강관 동바리, 타설 전 무엇을 확인할까 | 하루 한 문제 1일차' 를 우선후보로. 태그5~10개. 학과태그·학과CTA 없음.
글 순서: 인사와 주제어 첫문장(2~3문장, 최근기사없으면 Qnet현행2023~2027출제기준과2026제140회문제 사실로 도입하되 최근보도라고 꾸미지않음)→기출문제원문/논술25점권장25분→출제의도와답안방향(해석임을밝힘)→친절한개념해설3개소제목 각2문단→법령규칙유형구분표→답안예시6절(전후hr·명사형문어체개조식, 각절4개짧은bullet; 독립목차목록없음)→놓치기쉬운점3개→공식참고자료·확인일2026-10-31·학습용단서한문단→따라쓰기PDF→요청링크는맨아래.
일반설명은 친절한 해요/합니다체, 답안작성이론은문어체, 답안6절bullet은~함/~임/~필요 명사형. 표는HTML생성시센터. 허위경력·채점경험·무근거점수보장금지. 법령조문번호 정확. 수식/가상계산은넣지않고 안전관리판단을 설명. 관련기출8문항8회는주제선정기록에만남기고 본문에동일유형8회반복이라고하지않음. 단서는끝한문단. 특정현장배치/기준하중임의도식금지. 도식은'사전검토→조립→타설감시→해체검토' 순서도만사용.
JSON만출력(코드펜스없음): {"title":str,"tags":[str],"intro":[str,str],"problem":str,"intent":[str,str],"explanations":[{"heading":str,"paragraphs":[str,str]}],"table":{"headers":[str,str,str],"rows":[[str,str,str]]},"answer_sections":[{"title":str,"bullets":[str,str,str,str]}],"pitfalls":[str,str,str],"note":str}. answer_sections의짧은bullet은PDF답안지에도그대로써야하므로한줄당대략35한글자이하(길면짧은두문장으로나눌것). 너무빈약한지시명단대신근거-확인-조치관계가드러나게. references는고정Qnet+법령이므로JSON에는추가하지말것.

공식기출문항원문:\n'''+q['question']+'\n원문URL:'+q['source']+'\n\n공식법령직접확인내용:\n'+law
(OUT/'generation-prompt.txt').write_text(prompt)
env={k:v for k,v in os.environ.items() if not k.startswith(('ANTHROPIC_','CLAUDE_CODE_USE_','AWS_','GOOGLE_','AZURE_'))}
def request(prompt,name):
 r=subprocess.run(['/usr/local/bin/claude','-p','--model','sonnet','--tools','','--setting-sources','','--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--no-session-persistence','--no-chrome','--output-format','json',prompt],cwd='/private/tmp',env=env,capture_output=True,text=True,timeout=240)
 outer=json.loads(r.stdout);(OUT/(name+'-response.json')).write_text(json.dumps(outer,ensure_ascii=False,indent=2));assert r.returncode==0 and not outer.get('is_error'),outer.get('result')
 s=outer['result'].strip();s=re.sub(r'^```(?:json)?\s*|\s*```$','',s);return json.loads(s)
d=request(prompt,'draft');(OUT/'draft.json').write_text(json.dumps(d,ensure_ascii=False,indent=2));print('draft complete',flush=True)
for i in (1,2):
 instr=f'''한국어 기술사 글 humanizer {i}차 편집. 숫자·조문번호·공식문제원문·태그·의미·조건을 그대로보존. 1차번역투/부풀린말/어투혼용,2차반복어미/군더더기/부자연스러운연결점검. 설명친절체, 답안6절명사형문어체, 답안이론문어체를지킴. 새로운사실/주장/경력추가0. JSON객체구조/모든key유지. 동일한전체JSON만반환. 원문:\n'''+json.dumps(d,ensure_ascii=False)
 d=request(instr,f'humanizer{i}');(OUT/f'humanizer{i}.json').write_text(json.dumps(d,ensure_ascii=False,indent=2));print('humanizer',i,'complete',flush=True)
(OUT/'final-content.json').write_text(json.dumps(d,ensure_ascii=False,indent=2))
