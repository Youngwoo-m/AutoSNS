from pathlib import Path
import os,subprocess,json,re
p=Path(__file__).resolve().parent;d=json.loads((p/'final-content.json').read_text())
instruction='''독립검토 전 자체점검에 따른 한정 편집입니다. 원본 JSON전체같은구조로 반환하되 아래만바꾸세요. 그외문장·표·수치·조문은바꾸지말고새수치0.
1 intro를총3문장안팎으로간결하게, 인사뒤첫주제에 거푸집·강관동바리 명시. '오늘의주제어','첫정기글인만큼','최근보도근거가아니다'등내부편집설명삭제. 검증된2026제140회기출이사전검토와조립·해체를함께물었다는사실로도입. 2023~2027출제기준기간은불필요하므로삭제.
2 problem은포맷표시【...】없이공식문제원문만그대로. answer_sections제목에서앞번호삭제(HTML/PDF렌더러가번호붙임). 마지막제목의'및결론'삭제.
3 사전검토절(answer_sections2)에기존4bullet을유지하고다음두항목을안전공학적구조검토풀이로추가: 콘크리트·작업하중과타설순서별하중전달경로검토 / 부재의강도·강성및하부지반·지지층의안정성확인. 둘다숫자/식추가하지말고'필요함'형태명사형. 첫개념해설2번째문단에이내용을학습상구조검토설명으로짧게보완하되법령이항목을하나하나열거한다고주장하지말것(제330견고구조/제331구조검토/제332침하방지에근거한해석임).
4 답안의'감시자배치로'를법령범위를살려'감시자배치등으로'로. '산안규칙'약칭을'산업안전보건기준에 관한 규칙'으로.
5 note는법령판/확인일은참고자료에서별도표시하므로학습용답안예시·공식정답/채점기준아님·개별현장구조설계/작업계획대체아님이라는한문단만.
설명친절체, 답안명사형문어체그대로. 추가수치/기출추정/경력0. JSON만출력.\n'''
env={k:v for k,v in os.environ.items() if not k.startswith(('ANTHROPIC_','CLAUDE_CODE_USE_','AWS_','GOOGLE_','AZURE_'))}
r=subprocess.run(['/usr/local/bin/claude','-p','--model','sonnet','--tools','','--setting-sources','','--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--no-session-persistence','--no-chrome','--output-format','json',instruction+json.dumps(d,ensure_ascii=False)],env=env,cwd='/private/tmp',capture_output=True,text=True,timeout=240)
x=json.loads(r.stdout);(p/'targeted-edit-response.json').write_text(json.dumps(x,ensure_ascii=False,indent=2));assert r.returncode==0 and not x.get('is_error');s=re.sub(r'^```(?:json)?\s*|\s*```$','',x['result'].strip());d=json.loads(s);(p/'final-content.json').write_text(json.dumps(d,ensure_ascii=False,indent=2));print('targeted fixes complete')
