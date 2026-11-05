from pathlib import Path
import os,json,subprocess,re
OUT=Path(__file__).resolve().parent
sources=json.loads((OUT/'official-source-extract.json').read_text())
context='\n'.join(x['section']+' '+x['content'] for x in sources)
prompt='''당신은 건축시공기술사 수험생용 해설 초안 작성자입니다. 본인의 자격·경력·현장경험·채점경험을 만들어내지 않습니다. 아래 확인된 공식자료만으로 한국어 원고를 작성하세요. 계산/수식을 새로 넣지 마세요.
출력은 설명이나 마크다운울타리 없는 JSON 객체만: {"title":str,"tags":[str],"intro":[문단2개],"problem":str,"intent":[문단2개],"explanation":[{"heading":str,"paragraphs":[str],"table":{"headers":[str],"rows":[[str]]}}],"answer":[{"heading":str,"bullets":[str]}],"pitfalls":[str3개],"sources":[{"title":str,"url":str}],"disclosure":str,"pdf_answer_pages":[[str],[str],[str]]}.
제목: [건축시공기술사] 한중콘크리트 타설 전 점검과 초기동해 방지 | 하루 한 문제 1일차
문제 원문 반드시 그대로: 한중콘크리트 타설 전 현장 점검사항과 초기 동해 방지 대책에 대하여 설명하시오.
기출: 2024년 제132회 제3교시 1번, 논술형25점, 권장작성시간25분(학습 제안, 시험공식문제지의 교시100분과구별).
글 구성: 글머리2~3문장(안녕하세요 뒤 첫문장에한중콘크리트); 문제; 출제의도/답안방향; 개념해설(줄글·문제맞는소제목·온도구분표·타설전점검표); 구분선사이답안예시(5~7장, 문어체·명사형 개조식); 놓치기쉬운점3; 참고자료와 확인일; 따라쓰기PDF; 요청링크.
intro는2문단이되전체3문장안팎. 최근이슈를지어내지않고큐넷종목별안내의제140회2026실기예정기간11월14~28일을짧게연결(종목/지역별공고확인안내). 공식일정은 https://www.q-net.or.kr/crf005.do?gId=&gSite=Q&id=crf00503s02&jmCd=0510&jmInfoDivCcd=B0 에확인. 건축연습시작에현장점검형문제연습의의의로연결하되시험출제예측은금지.
기출문제출처 https://www.q-net.or.kr/cst006.do?id=cst00602&artlSeq=5212827&brdId=Q006&gSite=Q . 문제지2페이지(0기준)원본직접시각확인, 로컬132.pdf와공식원격PDF해시동일. 주제근거한중문자열8문항7회차(126,129,132,135,136,137,138), 공식출제비중/동일유형빈도라고주장금지. 본문에빈도집계수치꼭넣을필요없고원고상태에만저장. 학습분야는태그/메타에만, 본문문제위표시금지.
기존토목8일차한중콘크리트와차별: 배합계산·적산온도·토목8일차표반복을빼고, 건축구조체타설전공종간확인(보양/철근·거푸집/이음/동결지반/설비관통부/양생설비·온도측정·공시체·승인기록)과초기동해방지에집중. 설비관통부등은저자의학습용점검정리임을명확히, 시방서직접의무조항이라고만들지말것.
설명은친절한해요체. 답안예시는문어체개조식(예:~확인,~계획수립,~유지필요). 답안작성이론이있으면문어체. '만점/채점자가반드시/무조건합격' 금지. 별도의답안목차절을두지말것. 내부작업도구/AI작성과정설명 금지. 현행법령을모두확인했다는포괄주장금지.
검증된소스:
1) KCS14 20 40:2024, KCSC공식개정이력last_yn=Y 날짜2024-12-30, 공개원문API docCodeKCS14 20 40,ymd2024-12-30. 독자링크 https://www.kcsc.re.kr/standardCode/viewer/KCS%2014%2020%2040:2024-12-30 . 구조적으로확인된원문수치는아래콘텍스트뿐. 표3.4-1 '소요압축강도'를거푸집/동바리해체강도와동일시하지말것. 초기양생종료승인뒤하중/해체는별도검토. 막연한5MPa면모든양생끝표현금지. 계속/자주포화부위15/12/10MPa와보통노출5MPa 조건표그대로유지. 300이하/300초과800이하/800초과 경계정확히. 타설온도5~20℃와가혹기상또는두께300mm이하의최저10℃구별. 초기양생5℃이상 소요강도도달후2일0℃이상, 구조체온도와외기/보온공간온도구별. 고정양생몇일공식값을제안하지말것. KCS14공통콘크리트기준은건축에도관련되며KCS41및사업시방서적용체계구분.
2) 국토부공식안내2026-02-11 https://www.law.go.kr/LSW/cgmExpcInfoP.do?cgmExpcDatSeq=2339185&mode=2&ofiClsCd=350102 에서적용조건·동결재료·시멘트직접가열금지·타설5~20·조건부10도·빙설제거·지반해동·바람차단직접확인. 부처의안내이며그자체새로운법적기준이라고주장금지.
3) 개정고시제2024-879호2024-12-30 https://law.go.kr/LSW/flDownload.do?flSeq=148098945 및KCSC https://kcsc.re.kr/board/notdetail/6639 . 구성재료2.1/배합2.2.2개정은2025-01-01적용,그외경과조치는계약도서확인. 이1일차는배합계산이범위아니므로상세새수치추가금지.
자료확인일2026-10-31. 마지막단서한문단: 학습용답안예시/공식채점기준아님/기출원문확인/도식은저자정리·축척없음/프로젝트의적용판과계약조건별도확인. PDF문어체·개조식으로동일답안요지를3쪽에기재. pdf_answer_pages는각18줄이내, 한줄한글약29자이내, 총45~52줄, 답안구성/핵심수치본문과동일, 1쪽제목·개요/점검,2쪽점검/대책,3쪽양생/종료/놓치기쉬운점. PDF에참고소스짧은줄1개와학습용예시단서포함. LaTeX/수학식없음.
공식기준발췌(표를산술예제로확장금지):
'''+context
(OUT/'claude-generation-prompt.txt').write_text(prompt)
env={k:v for k,v in os.environ.items() if not k.startswith(('ANTHROPIC_','CLAUDE_CODE_USE_','AWS_','GOOGLE_','AZURE_'))}
args=['/usr/local/bin/claude','-p','--model','sonnet','--tools','','--setting-sources','','--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--no-session-persistence','--no-chrome','--output-format','json',prompt]
r=subprocess.run(args,cwd='/private/tmp',env=env,capture_output=True,text=True,timeout=240)
try:d=json.loads(r.stdout)
except Exception:raise RuntimeError('Claude response unavailable, no fallback')
(OUT/'claude-generation-result.json').write_text(json.dumps(d,ensure_ascii=False,indent=2))
assert r.returncode==0 and not d.get('is_error'),d.get('result')
s=d['result'].strip();s=re.sub(r'^```(?:json)?\s*|\s*```$','',s)
m=json.loads(s);(OUT/'manuscript-v1.json').write_text(json.dumps(m,ensure_ascii=False,indent=2))
print('draft_saved',len(s),'model_usage',list(d.get('modelUsage',{})))
