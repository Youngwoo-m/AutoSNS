# 건축·안전 발행 사전점검 (2026-10-31 KST)

원본 읽기/공개 HTTP 조회만 수행. 생성모델·프로필·발행·기존파일 변경·유료 호출 0. AGENTS/CLAUDE/공통규칙/양 daily 지시문/각 작성기준 읽음.

## 1. 우선 복구: 입문글 Blogger 누락

- 공개 Blogger feed `https://geoaina.blogspot.com/feeds/posts/default?alt=json&max-results=150`에서 141편 반환. 제목에 건축시공·건설안전이 들어간 글 각 0. 기존 local 입문 발행결과에도 Tistory 주소만 존재.
- 공개 `https://na-geoai.tistory.com/182`·`https://na-geoai.tistory.com/183` HTTP200, 정확한 입문 제목 및 각 questions 링크 존재 재확인.
- 지시문 personal/claude-jobs/jobs/building-daily.md 및 safety-daily.md 7행: 입문 없으면 먼저 입문부터 작성, 23행: 모든 해당 기술사 글은 개인 Tistory+Blogger 함께 공개. 의도적으로 입문을 Tistory 전용으로 제한한 근거는 발견 못함. 따라서 Blogger 누락 복구 후보임.
- 입문글은 답안 PDF를 요구하지 않으며 공개 답안목록(add-post)에 넣지 않는 것이 지시문 요구.

### 안전 입문

원본 폴더 `/Volumes/USB256/devAPP/AutoSNS/GeoAI_NA/safety-engineer-writing/첫글_준비하기/`.
`게시본문.html`은 작성상태에 10/28 00:48 Tistory183 반영본으로 명시. 기존 source-reviewer 발행직전 pass(10/28), 다듬은 수정본 fix1 반영, calc ok 기록. 독립검토 JSON 파일은 별도 발견 못했으며 작성상태 안 요약기록만 있음. 신규 independent source-reviewer 재검토를 권장.
HTML img0/첨부0/PDF0, 모든 href는 https, 로컬 경로·티스토리 서명첨부 없음. 자산 재배포 불필요. 법령·시험정보 최신 재검토 후 기존본문 Blogger 복구가 가장 단순함.

### 건축 입문

원본 폴더 `/Volumes/USB256/devAPP/AutoSNS/GeoAI_NA/building-engineer-writing/첫글_준비하기/`.
`게시본문.html`은 옛 ~이다체 원본, `수정본_새문체.html`은 새 문체. 작성상태에는 첫 새문체 버전 10/28 00:12 Tistory182 반영과, 같은 파일의 야간 재수정은 아직182 미반영(사용자확인대기)이 함께 적혀 있음. 현재 로컬 수정본을 그대로 현재 공개본문과 동일하다고 단정하면 안 됨. 실제182 공개본문을 읽고 추출한 검토용 사본 또는 명시적으로 검토된 로컬본으로 복구할 것. 두 HTML 모두 img0/첨부0/PDF0, 모든 href https, 자산배포 불필요.

## 2. 오늘 상한: 코드와 정책 차이

- config.json geoai.enabled=true, posts_per_day=2, cap_exclude_prefixes 없음.
- 공개 Blogger 오늘 두 편: 07:43:55 GeoAI 기초37 https://geoaina.blogspot.com/2026/10/geoai-37.html ; 08:13:43 토목14 https://geoaina.blogspot.com/2026/10/14.html . KST 오프셋 확인.
- dept/naver-blog-auto/geoai_daily.py 315~331: 일반 자동편성 몫2에서 `[토목시공기술사]` 및 `NaGeoAI 실제 QGIS 실습`은 별도 연재 몫으로 제외. 건축/안전은 예외에 없음. 이 계산을 적용하면 현재1/2로 추가1편 여유.
- dept/naver-blog-auto/blogger_post.py: quota:blogger-personal 잠금은 있으나 실제 cap 판정 없음. geoai_blogger.publish()도 제목중복 검사 뒤 바로 insert. 발행기 성공이 상한 준수 증거가 아님.
- 학과 post_blogger.py의 blogger.daily_limit는 개인 Blogger의 이 정책과 별개. 개인 전체2편 상한이라는 코드 단정도 틀림(토목 예외 존재). 기존 posts_per_day 및 제외목록을 바꾸지 말 것. 보수적으로 일반몫 추가1편 이상은 실행하지 말고 남은 항목을 대기시키는 것이 현재 정책과 양립함. 저녁 GeoAI 자동글과 같은몫을 사용하므로 수동복구로 밀리는 경우 사용자 보고 필요.
- 티스토리 발행기에는 자체 일일편수 상한 코드를 발견하지 못함. 플랫폼 표시/기존 정책 확인 없이 무제한 가능하다고 결론내리지 말 것.

## 3. 미작성 정기 회차와 추천문제

건축·안전 폴더에는 각각 기출분석/첫글_준비하기 두 폴더만 존재, daily state JSONL 없음. 정기1일차 준비 후보이나 과거 달력날짜만큼 여러 원고를 임의 생성하지 말 것.

### 건축: 한중콘크리트 타설 전 점검·초기동해 방지 (조건부 후보)

공식 기출 원문 2024 제132회 3교시1번: 한중콘크리트 타설 전 현장 점검사항과 초기 동해 방지 대책에 대한 논술형25점. 로컬 `GeoAI_NA/building-engineer-writing/기출분석_2022-2026/전체465문항.json` id132-3-1, `132_layout.txt`의 3교시1번 원문 일치, `132.pdf` 원본 재검토 대상.
Q-net https://www.q-net.or.kr/cst006.do?id=cst00602&artlSeq=5212827&brdId=Q006&gSite=Q .
한중 문자열은8문항·7회차(126,129,132,135,136,137,138). 다만 토목8일차 한중콘크리트 배합설계·시공관리(Tistory149/Blogger2026/10/8.html)가 이미 있음. 단순 제목만 건축으로 바꾸면 중복. 건축 구조체의 타설 전 공종간 확인·초기동해 예방 승인/기록에 한정하고 배합계산·적산온도·같은표를 반복하지 않을 때만 후보. 더 확실한 비중복 주제를 택해도 됨.

공식 자료를 이번에 열어 확인한 범위:
- 국토교통부고시 제2024-879호(2024-12-30) https://www.law.go.kr/LSW/flDownload.do?flSeq=148098945 . KCS142040 포함 일부개정, 구성재료2.1·배합2.2.2는2025-01-01 적용, 기존 시행중 공사 경과조치 존재 확인.
- KCSC 공고 https://kcsc.re.kr/board/notdetail/6639 검색색인 확인. viewer https://www.kcsc.re.kr/standardCode/viewer/KCS%2014%2020%2040:2024-12-31 는 열리지만 읽을 본문0행. 따라서 타설/양생 온도·강도 표의 최신 수치를 이 조회로 검증했다고 하지 말 것. 제3자 sjxtech/ksocket는 발견했으나 공식 직접근거로 사용하지 않음.
- 건축기준의 KCS41 및 프로젝트 적용시방서를 구분할 것. KCS14를 건축에 무관하다고 단정하거나 토목판을 그대로 복사하지 말 것. 세부 수치 현행판 원문 확보는 새원고의 미해결 검토항목.

### 건설안전: 강관동바리 사전검토·조립/해체 붕괴 예방

공식 기출2026 제140회2교시5번(논술형25점). 로컬 `GeoAI_NA/safety-engineer-writing/기출분석_2022-2026/전체465문항.json` id140-2-5 및 `140_layout.txt`2교시5번에서 콘크리트 거푸집·동바리(강관동바리 기준) 사전검토와 처짐·붕괴 예방 조립/해체 유의사항을 묻는 문제 일치. `140.pdf` 시각대조 대상.
Q-net https://www.q-net.or.kr/cst006.do?id=cst00602&artlSeq=5274126&brdId=Q006&gSite=Q . 동바리8문항·8회차. 토목7일차(해체 강도·시기)와 달리 안전규칙의 강관동바리 조립 조건·침하/편심/타설감시·작업중지 체계에 집중하면 각도가 구별됨.

공식 현행조문 직접 열람:
https://www.law.go.kr/LSW/lsLinkCommonInfo.do?lsJoLnkSeq=1028543971
페이지 표제 [시행2026-03-02] [고용노동부령450호,2025-09-01 일부개정]. 조문구간328~335 직접읽음.
-331: 구조검토 후 조립도 작성·준수, 재질/단면/간격/이음 명시.
-332: 지반침하·미끄러짐 방지, 같은수직선 배치, 개구부 지지·연결철물 등.
-332의2: 파이프서포트는3개이상 연결금지, 연결시4개이상볼트 또는 전용철물, 높이3.5m초과시2m이내마다2방향 수평연결재. 강관틀/조립강주/시스템과 구별(시스템의 받침철물 겹침1/3을 강관서포트 규정으로 섞지 말 것).
-333: 출입통제·악천후 중지·안전한 조립/해체 절차.
-334: 당일전 변형/변위/침하점검, 작업중 감시와 이상시중지/대피, 골고루 분산타설, 설계양생기간 준수해체.
이 수치는 독립 calc/source 검토 전 공개원고 확정값으로 삼지 말 것.

## 4. 기존 PDF·배포 실행경로

- 전용 Python `/Volumes/USB256/devAPP/AutoSNS/GeoAI_NA/claude-jobs/.venv/bin/python` (python3.12 링크), 공통규칙에서 이 환경만 사용.
- Q-net 원본 답안지 `/Volumes/USB256/기술사/2026기술사 답안지-1교시(안내용)_Qnet원본.pdf` 실존1464367bytes.
- 가장 최근 견본 `personal/civil-engineer-writing/14일차_비탈면붕괴/make_pdf.py`: reportlab+pypdf, template pages[4] deepcopy overlay, 회색184/255, 모든page pypdfium2 scale1.6 렌더. 좌표·템플릿은 재확인 필요, 코드 그대로 새글에 실행하면 토목내용 생성하므로 복사실행 금지.
- 기존 PDF 글꼴 `/System/Library/Fonts/Supplemental/AppleGothic.ttf` 실존. 공통assets/FONTS Pretendard-Bold.otf/KoPub...Bold.otf도 있으나 reportlab TTFont지원 여부 먼저 확인. 제목/배너는 PretendardBold 규칙.
- 새 PDF 공개경로 `site/geoai-site/building-questions/materials/day01/` 또는 safety 대응. 검증한 파일만 배치.
- 배포는 `personal/engineer-question-worker/deploy.py`→deploy_full.deploy. 기존 함수까지 함께 배포해 유지(단순zip 배포 금지). `deploy_full.py --check`는 목록만, 실제deploy는 외부쓰기이므로 부모가 소유/충돌 확인 후 실행.
- 입문 Blogger복구에는 PDF/이미지가 없으므로 이 배포를 실행할 이유 없음.

## 5. 아직 미확인

발행직전 최신 queue·계정/상한 잠금, 공식 실제 PDF 시각검토, 신규 independent source-reviewer, 필요시 calc-verifier, 원고 humanizer 두차례, 배너(필요시 기존배경) 확인. 부모가 구독 최소요청 OK 확인했다고 전달받았으나 이 작업은 모델을 호출하지 않음.
