from pathlib import Path
import os,json,subprocess,re
OUT=Path(__file__).resolve().parent
law=(OUT/'법령_직접확인.txt').read_text();q=json.loads((OUT/'기출근거.json').read_text())['selected']
prompt='''건설안전기술사 하루 한 문제 2일차 원고. 한국어 수험생용. 제목 '[건설안전기술사] 위험성평가 절차, 위험 발견에서 개선 이행까지 | 하루 한 문제 2일차'. 태그9개: 기출 포함1개, 답안 포함1개만; 학과태그금지.
기출문제는 2022 제126회 제2교시5번 '위험성평가의 정의, 단계별 절차를 설명하시오.' 원문. 논술25점 권장25분(권장임 명시).
핵심: 위험성평가는 위험요인을 찾아 허용가능 여부를 결정하고, 허용불가능하면 개선대책 수립·이행하는 과정임. 현행 시행규칙37조1항 3개 법정 핵심절차를 정확히 구분. 학습설명은 사전준비→요인파악→위험성결정→개선수립이행→결과확인공유기록의5개 운영단계로 도식화하되 법정5단계라고 부르지 말것. 시행규칙37조의 법정 핵심절차에 사전준비와 후속관리를 더한 학습용 정리임 명시. 위험성추정/점수계산을 모든평가의 필수 독립절차라고 단정금지. 위험성은 점수자체보다 허용가능 여부와 실행 가능한 대책의 연결. 근로자참여는 단순서명수집이 아닌 실제요인확인·의견반영으로 설명하되 법령에없는세부의무를 직접의무라고 단정금지. 법령근거는 아래 실제확인자료만사용. 평가시기·보존기간·벌칙·임의위험점수·매트릭스수치·확률곱수식·고시개정안은 넣지말것. 근거없는계층순서법정의무금지. 예시로 개구부통행 시 추락위험→고정덮개 또는 안전난간 등의 공학적 방호검토→설치확인과 사용 중변화점검을 쓰되 구체설치높이/강도 기준추정금지, 현장조건따라설계기준확인문장. 안전모교육만으로추락요인제거됐다고말하지않기.
글 구조: 배너는 별도생성. 인사+주제어 첫문장 2~3문장; 글머리최근이슈는2026년개정 시행규칙37조가위험성평가의방법절차시기를규정한다는사실과확인일10월31일을 연결(추측보도금지). 기출문제원문→출제의도와답안방향(채점경험아닌학습해석 명시)→친절한 개념해설3개소제목 각2문단→법정핵심절차/학습운영단계연결3열표4행이상→답안예시6절 각4개짧은bullet(총24, PDF한줄대략35한글자)→놓치기쉬운점3개→단서마지막한문단. 답안 독립목차/반복결론금지. 일반설명해요/합니다, 답안이론문어체, 답안은명사형개조식. 허위경력채점경험점수보장0. 질문과출제의도사실숫자변경0.
JSON만출력 코드펜스0. schema {"title":str,"tags":[str],"intro":[str,str],"problem":str,"intent":[str,str],"explanations":[{"heading":str,"paragraphs":[str,str]}],"table":{"headers":[str,str,str],"rows":[[str,str,str]]},"answer_sections":[{"title":str,"bullets":[str,str,str,str]}],"pitfalls":[str,str,str],"note":str}. intent[1]은답안작성이론이므로~한다문어체. pitfalls는개념구분설명이며~적으세요등글쓰기지시금지. references는생성도구고정.

공식기출원문:\n'''+q['question']+'\n원문URL:'+q['source']+'\n\n공식법령확인내용:\n'+law
(OUT/'generation-prompt.txt').write_text(prompt)
env={k:v for k,v in os.environ.items() if not k.startswith(('ANTHROPIC_','CLAUDE_CODE_USE_','AWS_','GOOGLE_','AZURE_'))}
def request(prompt,name):
 r=subprocess.run(['/usr/local/bin/claude','-p','--model','sonnet','--tools','','--setting-sources','','--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--no-session-persistence','--no-chrome','--output-format','json',prompt],cwd='/private/tmp',env=env,capture_output=True,text=True,timeout=240)
 outer=json.loads(r.stdout);(OUT/(name+'-response.json')).write_text(json.dumps(outer,ensure_ascii=False,indent=2));assert r.returncode==0 and not outer.get('is_error'),outer.get('result')
 s=outer['result'].strip();s=re.sub(r'^```(?:json)?\s*|\s*```$','',s);return json.loads(s)
d=json.loads((OUT/'final-content.json').read_text())
prompt='한국어 기술사 원고 한정 수정. 전체 JSON 같은 schema만 반환. facts 대부분 유지. 아래 공식 시행규칙37조의3/4 확인에 따라 결과공유·기록 자체가 단지 학습선택이라는 오해를 없앤다. 법정 핵심3개를5개 학습용 운영단계로 확장한 도식 자체는 학습용이지만 공유·기록 의무 자체를 비법정이라고 표현하지 않는다. 사전준비는 학습정리, 결과공유·기록은 별도 조문 근거가 있는 후속관리라는 점으로 1~2문장 보완. 새 보존기간숫자/처벌/평가시기 추정금지. answer 3절에 별도조문근거를 짧게 반영. 일반친절체/답안명사형/이론문어체 유지. 제목·기출문제·다른수치·태그 변경금지. intro 첫문장을 안녕하세요. 위험성평가 절차는 위험을 찾는 데서 끝나지 않고 개선 이행까지 연결하는 흐름이에요. 로 바꾸어 인사후첫문장에주제어. 최근 이슈: 라는라벨삭제. answer_section title에1.같은번호접두사삭제(출력도구가번호추가). 도입의 글이라고설명하는 메타표현 줄이기.\n공식조문:'+ (OUT/'rule37-3.txt').read_text()+'\n'+(OUT/'rule37-4.txt').read_text()+'\n원고:'+json.dumps(d,ensure_ascii=False)
d=request(prompt,'targeted-edit')
(OUT/'final-content.json').write_text(json.dumps(d,ensure_ascii=False,indent=2))
print('targeted edit complete')
