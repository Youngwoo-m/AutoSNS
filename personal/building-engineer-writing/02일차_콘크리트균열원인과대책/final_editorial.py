from pathlib import Path
import json,os,subprocess,re
p=Path(__file__).resolve().parent;m=json.loads((p/'manuscript-final.json').read_text())
prompt='''공개 건축시공기술사 원고의 마지막 문체 정리. 아래 두 필드만 수정하고 JSON {"intro":[문단2개],"disclosure":str} 반환. 기술내용/숫자/날짜/출처 보존. intro는 인사뒤 첫문장에'콘크리트 균열'과문제핵심, 2문단합쳐3문장이내, '첫주제어'같은내부편집설명삭제. disclosure는 SHA/해시/다운로드검증과정삭제, 학습용답안예시/공식채점기준아님/Qnet기출/KCS2024-12-30선택판확인2026-10-31/작성자정리도식축척없음/설계도서·적용판·환경확인한문단. 표를축척없는도식이라고하지말고표와도식구분. 과한같은문장종결반복정리.
'''+json.dumps({k:m[k] for k in ['intro','disclosure']},ensure_ascii=False)
env={k:v for k,v in os.environ.items() if not k.startswith(('ANTHROPIC_','CLAUDE_CODE_USE_','AWS_','GOOGLE_','AZURE_'))}
r=subprocess.run(['/usr/local/bin/claude','-p','--model','sonnet','--tools','','--setting-sources','','--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--no-session-persistence','--no-chrome','--output-format','json',prompt],cwd='/private/tmp',env=env,capture_output=True,text=True,timeout=180)
d=json.loads(r.stdout);assert r.returncode==0 and not d.get('is_error');(p/'final-editorial-result.json').write_text(json.dumps(d,ensure_ascii=False,indent=2));x=json.loads(re.sub(r'^```(?:json)?\s*|\s*```$','',d['result'].strip()));assert set(x)=={'intro','disclosure'};m.update(x);(p/'manuscript-final.json').write_text(json.dumps(m,ensure_ascii=False,indent=2));print('final_editorial_done')
