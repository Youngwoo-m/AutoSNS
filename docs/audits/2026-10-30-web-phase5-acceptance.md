# 운영 웹 5단계 수락 기록

2026-10-30. 사용자 승인 범위는 저장 성과 조회·근거 기반 기획제안 저장·계정별 경로 이행 준비다. 실제 API 수집·모델 호출·발행·운영 파일 이동은 실행하지 않는다. 코드·독립 결합 검토·실제 브라우저 수락·소유 개발 서버 반영과 자료 보존 확인을 마쳤다. 전체 자동 운영 목표는 후속 필수 항목까지 계속 개발해야 한다.

## 구현과 보존 경계

- 관리 운영 원장 v3는 유지한다. 별도 `metrics.sqlite3` schema1에 불변 관측·제안·가져오기 receipt를 저장한다. 생성자/GET는 초기화하지 않고 startup의 명시 initialize만 DB를 만든다.
- 실제0·error·unsupported·미수집·legacy_reported를 구분한다. 관측/수집/파일수정 시각은 별도이고, legacy의 시각 미확인을 mtime으로 채우지 않는다. 누적값을 기간 발생량으로 표시하지 않는다.
- 서버 수집 계약은 실제 RuntimeStore의 검증 이벤트·공개 상태·게시ID·대상/등록부를 재대조한다. 버전/manifest는 서버 source에 결합하고 원시 provider 응답은 공개하지 않는다. 실제 수집기는 미등록이며 collection_enabled=false다.
- 관련 계정 조회는 owner OR destination, 채널 집계는 실제 대상에 한 번, 제작예산 근거는 production_id당 소유 계정에 한 번 귀속한다. 예산 예약/정산을 실제 과금으로 추정하지 않아 금액·통화 미확인은 null이다.
- 최신 수집 오류/미등록은 같은 물리 게시의 이전 성공 근거와 연결하고 그 scope를 표시한다. 이전 성공값은 보존하지만 최신 수집 성공으로 위장하지 않는다.
- importer는9개 allowlist JSON만 제한 읽는다. 검색어·site/page·YouTube v 등 원본 식별 차원을 보존하고 query로 식별이 불명확한 행은 원본 위치를 유지한다. 명시 대상을 확인한 legacy는 destination만 귀속하고 원본 owner는 추정하지 않는다.
- POST 가져오기는 최신 미리보기를 재검증한다. receipt와 관측/결과를 원자 저장해 응답 유실·DB 재개방·원본 변경 뒤 같은 요청이 원래 결과를 반환한다. 다른 digest로 같은 key를 쓰면409다.
- 기획제안은 별도 draft다. 기존 ContentStore 원본 생성·승인·실행을 호출하지 않는다. 성과에서 저장한 수동 제안을 기획 보드의 AI 기록과 별도 표시한다.
- 경로 도구는 명시 allowlist의 정적 코드/alias/caller/환경 기호 참조만 보고한다. unknown 계정 fallback과 실제 이동은 없고 physical_migration_ready=false다. 공용 운영 DB·기존 .venv·토큰·로그인 폴더를 이동하지 않는다.

## 자동 시험

- S1: 신규23개. verified 성공의 관측 시각 누락 모델/append/import 거부 및 import 선행행 롤백, 실제0·불변 모델·동시 키·별도 제안·원장v3 불변을 확인했다.
- S2: 최초17개에서 검색어/영상/동적page 식별과 실제 Naver enum/target 접합 회귀를 추가했다. 최종 관련49개가 통과했다. 실제 원본은 읽기 전용 대조만 하고 저장하지 않았다.
- S3: 서비스20개. 실제 RuntimeStore 임시 원장 검증과 DB 바이트 불변, 물리 게시 중복 제거, 실제 collector 예외/None의 실패 연결 및 회복·타게시 격리를 확인했다.
- S4: localhost HTTP/receipt/순수경계13개 통과(3.232초). 인증·Origin·엄격 body/query·무쓰기 GET·미확인 계정·재전송/동시 receipt·미리보기 ID의 제안 거부·원본 생성0을 확인했다.
- S5:17개 및 실제 원본 allowlist 코드29개/alias13개/정적관계49개 조사. 두 관측의 파일 hash/mtime이 같고 subprocess/network guard 아래 외부 호출0이었다. 운영 전체 파일/호출자를 전수 조사한 것은 아니다.
- S6/S7: 성과 모듈23개와 app 포커스 연결3개를 포함한 전체 Node107개 통과(768.32633ms), 실패/skip0. 검토 당시 app은 HEAD/임시 QA webroot/아티팩트 bytes를 맞췄다. 최종 반영 후 실제 working app도 같은 bytes이며, 임시 아티팩트 없이 실제 app을 읽는 포커스/이탈 보호4개 시험도 통과했다.
- 전체 Python: `python3 -m unittest discover -s tests -p 'test_*.py'` **481개 통과**,47.291초, 실패/skip/warning0. 코드 기준e6ebfb1. 로그 `/private/tmp/autosns-phase5-final-python.log`.

## 실제 원본의 읽기 전용 대조

원본 `common/analytics/snapshots/parts`의9개 파일을 새 load/build로 두 번 읽었다. 파일 모두ok, 가져오기 후보978행·오류0, 등록 대상과 일치한 학과132행·귀속 미확인846행이었다. 원본 소유는978행 모두 미확인이다. 등록 대상이 부족한 자료에 계정을 추정해 넣지 않았다.

최초 대조의 전부 미귀속 결과에서 Naver `naver`/실제 등록부 `naver_blog` 및 target 표현 차이를 발견해 수정·독립 검토했다. 이후132행이 등록된 학과 대상으로 연결됐다. 전후9개 파일 내용 hash/mtime은 같고 같은 입력의 preview digest도 같았다. 소켓/subprocess guard 아래 외부 호출0, 실제 import는 실행하지 않았다. 근거 `/private/tmp/autosns-phase5-live-legacy-preview.json`.

이978행은 과거 통계/게시목록/검색·색인 근거이며 오늘 공개 실적이나 현재 verified 관측 수가 아니다.

## 실제 브라우저 수락

임시8768과 전용 `ax_phase5_fixture_session` 쿠키를 사용했다. 실제 계정·원본·인증 자료는 연결하지 않았다. 화면의 `[5단계 검증 자료]`는 fixture이며 실제 채널 실적이 아니다.

1. 1280px에서 실제0·조회 오류·미지원·과거 보고·계정 귀속·지원 상태를 구분했다. 필터 값 변경 뒤 activeElement가 해당SELECT로 유지됐다.
2. 근거 선택·개인 계정·제목/메모를 입력하고 재조회해 선택/입력이 보존됐다. 명시 저장 후 제안1개가 성과와 기획 보드에 나타났고 원본/승인은 생성되지 않았다.
3. 기획 메뉴 진입 뒤 자동 refresh가 제목 포커스를 BODY로 잃는 문제를 실제 재현해 수정했다. 새 아티팩트 reload 후 자동조회가 끝나도 activeElement=H1/page-title을 확인했다. 입력 등 다른 포커스는 빼앗지 않는 회귀시험을 추가했다.
4. 미리보기 후 임시 원본만 변경하자409가 발생하면서 미리보기·요청이 유지됐다. 명시 요청 버리기→새 미리보기→저장 후 과거 보고2개만 추가됐다.
5. 개인 보기3개, 학과 보기4개 관측으로 교차 원본이 양쪽에서 발견되고 다른 대상/미귀속 기록은 필터에 맞게 제외됐다.
6. 320px에서 viewport/body/html 폭 모두320, 긴 식별자·관측 시각·출처를 연 상세에서도 전체 가로 넘침0이었다. Escape는 상세를 닫고 SUMMARY에 포커스를 돌려줬다. 임시 viewport override는 검증 후 해제했다.
7. 브라우저 console warn/error0. 초기 QA DB는 관측6·제안1·가져오기 receipt1, 운영 원본/실행/발행 승인 각0이다. 임시 source STOP은 부재다.

이미지: `ax-console/design/previews/phase5-metrics-desktop.jpg`, `phase5-proposal-desktop.jpg`, `phase5-metrics-mobile.jpg`. DB 근거 `/private/tmp/autosns-phase5-browser-db-proof.json`.

## 독립 검토와 최종 반영

S1/S3/S5 및 S6 모듈은 지적 수정 뒤 한정 재검토를 통과했다. S2는 원본 식별 손실을 두 차례 보완한 뒤 통과했고, 실제 Naver 접합도 별도 검토를 통과했다. S4 코드 검토와 S7 제목 포커스 수정 재검토도 통과했다. 원래 지적을 현재 초록 시험으로 덮어쓰지 않았으며 각 회귀 반례를 남겼다.

최종 전체 결합 검토의 I1~I4는 단일 수정 뒤 한정 재검토에서 모두 ADDRESSED, 명세·품질 PASS이며 새 Critical/Important는 없다. 소유8769/8767 백업·갱신·보존 확인도 완료했다. 실제 운영 코드/launchd/8700/큐/키/프로필 변경은 이번 범위에 없다.

## 남은 전체 목표

실제 채널별 발행/조회 어댑터와 공식 인증·SNS 도구 연결, 발행 권한 없는 제작기·실제 독립 검산/출처 검토·구독 전용 격리, 모든 기존 진입점/스케줄의 단일 실행 주인 전환, 원격 예약/공개/내용 검증, 실제 API 성과 수집·계정 귀속 보완, 안전한 물리 폴더 이행, 보호된 Mac/휴대폰 외부 접속·롤백은 후속 필수 작업이다. 이번 로컬 성과·이행 준비 수락으로 전체 목표를 완료 처리하지 않는다.

## 판단 기록과 변경 비용

| 순서 | 판단 | 틀렸을 때의 비용·남은 연결 |
|---|---|---|
| 1 | 사용자 지정 병렬 작업과 파일 소유 분리 | 계약 차이는 통합 재작업으로 보완 |
| 2 | MetricsStore(root).initialize() 규약 사용 | 호출부 변경 시 관련 소비자를 함께 수정 |
| 3 | 성과 별도 DB와 원본과 다른 제안 draft | 자동 원본 전환은 후속 트랜잭션 설계 필요 |
| 4 | 관련 계정은 owner OR destination, 실적은 대상·제작비는 소유 | 잘못 합산하면 교차 게시 누락/중복이므로 시험으로 고정 |
| 5 | UI 모듈 검토와 실제 통합·브라우저 수락 분리 | 모듈 통과만으로 전체 UI 완료 처리 불가 |
| 6 | legacy 채널은 대상만 증명, 원본 소유 추정 금지 | 강한 원본 매핑 전 미귀속 자료가 남음 |
| 7 | quota 제작예산과 실제 지출 구분 | 공급자별 실과금 관측은 계속 구현해야 함 |
| 8 | 가져오기 영속 receipt를 저장소 원자 경계에 추가 | 새 테이블/초기화/동시성 검증이 추가됨 |
| 9 | S2 재검토 중 S4의 독립 receipt/auth 작업 병렬 시작 | importer 계약 변경 시 끝점 시험 조정 필요, 실제 결합은 게이트 뒤 수락 |
| 10 | preview ID는 표시 전용 | 저장/기획 근거로 쓰면 안 되며 API가 거부해야 함 |
| 11 | 실행 중 app은 보존하고 git/임시 QA에 새 통합 기록 | 최종 HEAD 재적용·서버 갱신·해시 대조를 빠뜨리면 실제 UI는 구버전 |

## 최종 결합 검토 수정과 재검증

전체 결합 검토는 네 Important를 새 반례로 확인했다. 기존469/100 초록 시험으로 완료를 판단하지 않고 단일 수정 묶음 e6ebfb1로 보완했다.

- 수집 결과가 같아도 새 시도는 새 server collection_id/완료시각을 남긴다. error→ok→같은error, ok→unsupported→동일ok가 모두3개 관측과 올바른 최신 상태를 갖는다. 같은 시도 재전송만 최초 ID/시각을 반환하고 다른 내용은 충돌한다. 직접 record의 메타/키 없는 호출은 새 시도다.
- importer의 지원 수치18종을 한국어 이름·단위로 표시하고 이름표 미정 수치도 상세에서 보존한다. 색인·계정 지표에 가짜 조회수 필드를 만들지 않는다. 비율 단위 미확인 원값과 아주 작은 소수를 임의 퍼센트/0으로 바꾸지 않는다.
- 패널/전역 인증 만료의 로그인은 새 창이다. 원래 문서의 dirty/busy/pending을 unload 보호에 연결했다. 임시 인증을 만료시킨 실제 CUA에서 POST401→새 창 로그인→원래 화면 재조회→동일 제목/메모/선택/pending 유지→기존 버튼 재시도 저장 성공을 확인했다. 실제 사용자의 인증은 건드리지 않았다. 강제 닫기/명시 이탈 뒤의 영속 복원을 제공하는 것은 아니다.
- 등록 가산 정의만 count를 합산한다. 검증된 searchconsole.performance.v1 interval 정의는 클릭/노출 비율과 노출 가중 평균 순위를 계산한다. CTR1.5 같은 단순 합산을 하지 않는다. 정의·분모·단위/기간이 미확인인 값, 고유 도달/구독자 등의 미집계 근거와 원값은 보존한다.

수정 후 부모 전체 시험은 Python481개/47.291초 OK, Node107개/768.32633ms pass·실패/skip/warning0이다. focused Python55/Node33 RED→GREEN 근거는 별도 수정 보고서에서 확인했다. 최종 한정 재검토는 I1~I4 모두 ADDRESSED·명세/품질 PASS, 새 Critical/Important0을 확인했다.

새 전용 QA의 실제 importer→저장→GET→화면에서 색인321·팔로워123·게시물7·구독자456·누적조회789·클릭률.75·평균순위2.5 표시를 확인했다. 최종 QA DB는 관측11·제안1·receipt1, 운영 원본/실행/발행승인은0이다. HEAD/아티팩트/QA app 및 UI 모듈 bytes가 같다.320/1280 화면 전체 가로 넘침0과 console warn/error0을 재확인했고 임시 크기를 해제했다.

추가 판단은 앞 표의 순서에 이어 기록한다.

| 순서 | 판단 | 틀렸을 때의 비용·남은 연결 |
|---|---|---|
| 12 | 정적 app을 공유하는 소유 읽기 전용8767도 갱신 | 짧은 재시작이 추가된다. W 없음·읽기 전용·기본 비활성은 유지 |
| 13 | 최종 검토가 유보한 실제 인증/수집/발행/제작/전환/이동/외부접속은 후속 전체 목표로 유지 | 로컬 I1~I4는 유보하지 않고 수정. 개발 서버 반영도 이번 수락에서 별도 증명 필요 |
| 14 | 수집 결과와 다른 서버 발급 시도 ID/시각 사용 | 재전송 호출자가 동일 시도 ID/키를 보존해야 하며 소실된 옛 이력은 소급 복원 불가 |
| 15 | 등록 정의만 집계하고 비율/평균은 검증된 가중 계산 | 새 정의·단위는 등록/시험이 추가될 때까지 미집계 근거로 남음 |
| 16 | 원래 문서를 유지하는 새 창 재인증과 이탈 보호 | 사용자가 경고를 무시해 닫으면 메모리 입력은 사라지며 영속 복원을 주장하지 않음 |

## 소유 개발 서버 최종 반영

기존 소유8769/8767 프로세스의 정상 종료를 확인하고 백업한 뒤 새 코드로 재시작했다. 원본8700과 기존 자동 작업은 변경하지 않았다.

- 관리 웹: `http://127.0.0.1:8769/`, 읽기 전용 웹: `http://127.0.0.1:8767/`. 두 서버의 로그인200, 인증된 성과 GET200, 미인증 성과401, 새 app/성과 모듈200 및 커밋 bytes 일치를 확인했다.
- 백업: `/Users/youngwoo/.codex/worktrees/account-automation-design/AutoSNS/ax-console/data/managed-backups/20261030-211258-phase5-v3/`. SQLite backup API로 v3 원장을 복제하고 파일 manifest를 보존했다. 원장26개 기존 테이블의 행수/정규화 hash·스키마, 관리 콘텐츠 파일과 원본의 감시 코드5개 hash가 모두 같다.
- 백업의 quick_check=ok·foreign_key_check 오류0, 임시 디렉터리로 복원한 DB의 동일 상태를 확인했다. 실제 원장이나 source에 옛 백업을 덮어쓰지 않았다.
- 새 `metrics.sqlite3`는 명시 initialize한 schema1이며 observations/proposals/import_requests 모두0이다. 실제 자료를 자동 가져오거나 QA자료를 넣지 않았다. 기존 원장 v3는 그대로다.
- 읽기 전용8767은 W 없음·writable=false, 관리8769는 writable=true다. 양쪽 collection_enabled=false이며 실제 collector/발행 adapter/probe를 등록하거나 활성화하지 않았다.
- 원본 관측 콘텐츠179개·등록 교차 경로23개와 `/api/v2/connections`의11개 연결을 확인했다.11개 execution_enabled는 전부false다. 이 건수는 오늘 발행 실적이 아니다.
- 최종 working app SHA256은 `fe97e8a15bd9d4f2825b6c20f8d6ef6ad1bcbc0eaba2f6b8b58335ca85598085`로 커밋/검증 아티팩트/QA webroot와 같다. 아티팩트를 경로에서 제외하고 실행한 실제 app 시험4개가 통과했다(113.217194ms).
- QA8768과 보조 로그인/검증 탭은 종료했고 기존 사용자 탭은 보존했다. 임시 viewport를 해제했다. 실제 비밀번호/세션/쿠키를 바꾸거나 실제 브라우저의 편집을 새로고침하지 않았다.

실행 근거: `/private/tmp/autosns-phase5-backup-state.json`, `autosns-phase5-live-smoke.json`, `autosns-phase5-deployed-app-test.log`. 향후 원복은 반영 이후 추가된 관측·제안·receipt와 원격 이력을 먼저 보존해야 하며, 옛 DB 복사만으로 최신 운영 상태가 복원된다고 보지 않는다.

**5단계 수락 결과:** local_metrics_ready=true, migration_plan_ready=true. live_collection_ready=false, physical_migration_ready=false, production_ready=false. 실제 운영 전체 완료를 의미하지 않는다.
