from pathlib import Path
import json,os,subprocess,re
OUT=Path(__file__).resolve().parent
extract=json.loads((OUT/'official-source-extract.json').read_text())
extract=[x for x in extract if x['section'].startswith(('1.9.1','3.3.4','3.4.1','3.4.2')) and not any(c in x['text'] for c in ['60 %','185 kg','표 3.4','표 1.9'])]
prompt='''당신은 건축시공기술사 학습 해설 작성자입니다. 공공 공식자료를 아래에 제공합니다. 자격·경력·현장·채점 경험을 만들지 않습니다. 한국어 JSON 객체만 출력하고 마크다운 울타리는 쓰지 마세요.
스키마: {"title":str,"tags":[str],"intro":[문단2개],"problem":str,"intent":[문단2개],"explanation":[{"heading":str,"paragraphs":[str],"table":{"headers":[str],"rows":[[str]]}}],"answer":[{"heading":str,"bullets":[str]}],"pitfalls":[str3개],"sources":[{"title":str,"url":str}],"disclosure":str,"pdf_answer_pages":[[str],[str],[str]]}.
제목: [건축시공기술사] 콘크리트 균열, 경화 전·후와 내구성 원인별 대책 | 하루 한 문제 2일차
기출원문 정확히: 콘크리트 공사 후 시간경과에 따라 나타나는 균열을 경화 전, 경화 후 및 내구성 균열로 구분하여 균열의 원인 및 대책에 대하여 설명하시오.
2023년 제131회 제4교시 3번, 논술형 25점, 권장 작성시간25분(학습제안). 원문PDF 원격다운로드로 기존Qnet분석PDF와sha256일치 검증. 기출출처 https://www.q-net.or.kr/cst006.do?id=cst00602&artlSeq=5212271&brdId=Q006&gSite=Q .
글머리2~3문장: 인사와 첫주제어, 균열모양만보고보수방법고르는오류대신 발생시점과원인 구별의중요성. 최근사고·뉴스지어내지말고 Qnet에공개된기출문제의요구를간단히연결하고공식출처연결은 sources에서. 시험합격·고득점단정·출제예측금지.
답안구조: 경화전(소성침하/소성수축), 경화후(건조수축/수화열온도/자기수축 및 하중·구속), 내구성(탄산화·염화물침투에따른철근부식, 동결융해, 알칼리골재반응 등의원리)를 원인→대책으로연결. 내구성균열은별도'시간단계'가아니라열화기구이며경화후균열과중첩될수있음 분명히. 시점만으로원인확정금지, 균열폭만으로구조안전확정금지. 모든균열이구조균열·모든균열=철근부식이라고하지말기.
설명친절해요체, intent[0]문제해석친절체+intent[1]답안작성요령문어체('~한다'), answer 명사형개조식. 별도답안목차/핵심암기어/자가점검없음. 개념해설 소제목3~4개, 원인과대책비교표(경화전/후/내구성별, 원인·대책), 보수는원인조사·진행성/누수/구조영향평가후선정이라는수준만, 주입재·균열폭수치단정금지. 설계별허용균열폭을일률mm값으로만들지말것. 공식수치·계산식을새로넣지말것.
KCS14 20 10:2024 일반콘크리트 적용판은2024-12-30원문조회(최신판이라고검증없이주장금지). 건축에도공통적용되는콘크리트시방이며 KCS41/설계도서/특기시방 적용판과다른요구조건확인. 공식조항필요시 1.9.1 내구성,3.3.4침하균열,3.4.1양생일반,3.4.2습윤양생만인용. 세부보수처방은단정하지않음.
공식확인수준: KCS의침하균열예방은'벽·기둥의침하가거의끝난다음연속슬래브·보타설', '굳기전침하균열이면즉시다짐/재진동'이므로 굳은균열을재진동으로없애라거나 양생후에도다짐하라고하지않기. 소성수축은표면증발과블리딩관계, 방풍·차양·마감직후표면보호·적절양생. 건조수축은수분손실+구속, 단위수량관리/습윤양생/줄눈·배근설계와시공. 온도균열은내외온도차·냉각수축과구속, 타설구획·온도관리·보온조합. 자기수축은수화에따른자기건조, 배합설계·양생·구속저감검토(살수만으로완전제어단정금지). 내구성은노출환경/피복/균질한다짐/적용배합/배수/점검. 알칼리골재반응은반응성골재·알칼리·수분의관여, 적합골재·혼화재등배합검토를저자의학습해설로. 동결융해는동결환경/수분/공기량관리 등여건검토, 숫자없음. 기구별대책은학습용해설이며KCS문장그대로의일괄법적의무로쓰지말것.
Sources 2개필수: Q-net공식문제지, 국가건설기준 KCS14 20 10:2024 https://www.kcsc.re.kr/standardCode/viewer/KCS%2014%2020%2010:2024-12-30 . 확인일2026-10-31. 마지막단서한문단은 학습용답안예시/공식채점기준아님/기출원문/저자정리도식축척없음/설계도서와적용판·환경확인, 반복하지말것.
태그9개: 콘크리트균열,건축시공기술사,건축시공,소성수축균열,침하균열,건조수축균열,내구성,건축시공기술사기출,건축시공기술사답안. 기출조합1개, 답안조합1개.
PDF는 Qnet답안지 위 문어체·개조식 회색따라쓰기. pdf_answer_pages 3쪽 각17~19줄이하, 한줄한글28자전후, 제목/기출메타 2줄도포함, 총50줄안팎. 주어진문제전체를한줄에몰아넣지말기. 기출핵심요구+답안5~6개소제목과모든분류별원인·대책/조사판단/단서·출처가요약에포함되어야함. HTML answer와내용모순없게. 첫줄 '콘크리트 균열의 원인과 대책', 둘째줄 '2023년 제131회 제4교시 3번'. 권장시간등학습메타는PDF공식값오해없도록생략가능.
공식확인발췌(새수치나직접인용긴문장불필요):
'''+json.dumps(extract,ensure_ascii=False)
(OUT/'claude-generation-prompt.txt').write_text(prompt)
env={k:v for k,v in os.environ.items() if not k.startswith(('ANTHROPIC_','CLAUDE_CODE_USE_','AWS_','GOOGLE_','AZURE_'))}
r=subprocess.run(['/usr/local/bin/claude','-p','--model','sonnet','--tools','','--setting-sources','','--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--no-session-persistence','--no-chrome','--output-format','json',prompt],cwd='/private/tmp',env=env,capture_output=True,text=True,timeout=360)
d=json.loads(r.stdout);(OUT/'claude-generation-result.json').write_text(json.dumps(d,ensure_ascii=False,indent=2));assert r.returncode==0 and not d.get('is_error'),d.get('result')
s=re.sub(r'^```(?:json)?\s*|\s*```$','',d['result'].strip());m=json.loads(s);(OUT/'manuscript-v1.json').write_text(json.dumps(m,ensure_ascii=False,indent=2));print('draft_saved',len(s),'model',list(d.get('modelUsage',{})))
