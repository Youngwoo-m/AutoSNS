# 6A 코드·정적 배포 수락 — 최신 전체 검증은 대기

2026-10-31. 6A 최종 코드 수정 `8954516`은 독립 재검토 Approved이며 테스트 프로필 격리 `88ff634`도 독립 PASS다. 기존 Pillow 설치 Python3.12 전체 시험872개가 통과했고, 실제8769/8767 정적 배포와 사용자 기술사 메뉴·건축 필터 확인까지 수행했다. 실제 모델·인증·발행은0이며 기본 실행 정책은 비활성이다.

현재 전체 작업 사본에는 병행 툴킷 Task8 통합이 진행 중이다. 이전 전체 Node195개와 후속 Task6 집중20개를 최신 전체 Node 성공으로 합치지 않는다. 따라서 최신 로컬 evidence는 `offline_ready=false`, `production_ready=false`로 전체 검증 대기를 표시한다. 6A의 코드·메뉴 배포 근거와 전체 작업 사본의 최종 준비 판정을 구분한다. [결정·보류 원문 보존](2026-10-31-phase6a-rulings.md)에 당시 결정과 잘못됐을 때 비용을 남겼다.

## 확인한 범위

`python3 -m unittest tests.integration.test_phase6a_acceptance -v`는 11개 시험을 통과했다. 모든 콘텐츠·원장·프로필 잠금 상태·가짜 원격 저장소는 임시 루트에 둔다. 실제 A5 `produce_content`/독립 source review/output link를 준비하는 `tests/operations/production_fixture.py`와 실제 A8 `ExecutionService`/`WorkerService`/승인 관문/SQLite를 소비한다. 외부 adapter `_Remote`는 시험용이다.

- 제작 1회와 독립 source review 1회에 발행 permit·연결·키·프로필 capability가 전달되지 않는다. 제작 완료 뒤 두 대상 배포가 만들어져도 별도 발행 승인이 없으면 submit은 0이다.
- 개인 Blogger와 학과 YouTube에 같은 원본 버전·제작 unit를 연결한다. 원본 소유는 개인, 두 번째 실제 게시 대상은 학과다. 대상별 승인·프로필 잠금·quota 예약을 거치고 제작 unit는 1개다.
- 다음 날 배포에도 기존 제작 unit/owner 비용 1을 재사용한다. 관측 사용량이 없으면 비용을 0으로 쓰지 않는다.
- 한 대상 성공, 다른 대상 원격 수락 뒤 응답 유실을 만든다. 후자는 unknown과 quota hold를 유지한다. 원장을 다시 열어 조회로 원격 대상·본문·시각·매체 hash를 결속하고 검증한다. 두 대상 submit은 각각 1회, unknown 대상 attempt도 1개다.
- 기본 비활성 정책의 worker tick은 원장 쓰기·adapter 읽기·submit을 모두 0으로 유지한다.

이는 가짜 원격 관측으로 **공통 원장·승인·복구 경계**를 검증한 결과다. 실제 YouTube adapter가 공개 내용 검증을 통과했다는 의미가 아니다. 실제 YouTube는 원격 미디어 bytes를 확보하지 못하면 pending/unsupported를 유지한다. 실계정의 원격 exactly-once를 보장하지 않는다.

## 23경로와 기존 TikTok 계약

등록부 23개 경로를 그대로 보존했다. enabled=true 5개, news.tiktok=false 1개, unknown 17개이며 모두 legacy owner다. 28개 고정 사건을 등록부 조건과 독립적으로 추출한 legacy 정규화 predicate에 넣고 `preview_crossposts`의 대상 집합·owner/destination·원본 버전/회차·조건/슬롯·변환 ID·지연 책임·상태를 비교했다. ID/hash 스냅샷 일치만으로 수락하지 않았다. dry는 관측 조건으로 유지하고 실발행 사건으로 바꾸지 않았다.

TikTok의 고정 저장소 소스에서 `pick` 함수와 `main`의 실패 처리 except 절만 AST로 분리했다. 원래 모듈 import·main·upload·모델·프로필·운영 큐 파일을 실행하지 않는다. video 존재 확인은 임시 파일로, 저장은 메모리 probe로 주입한다.

- 18개 큐 선택 사례: 07시 포함/23시 제외, 신규·backfill 3시간, 14일 포함/초과 제외, 4회 허용/5회 제외, posted/skipped, video 존재, not_before, hold_until, 신규→priority→not_before 정렬, backfill 뒤 3시간 내 신규 대기.
- 3개 실패 정책: 인프라 예외와 Chrome 디버깅 포트 오류는 시도 미증가, 화면 실패는 1 증가, 같은 화면 오류 2회면 다음 자정 hold와 streak 초기화. 일괄 retry/reset은 실행하지 않는다.
- 실제 `add`의 지연 식을 AST로 실행해 관리 preview의 같은 source 회차 시각과 비교한다. queue_add가 30분을 소유하고 관리 경로가 다시 enqueue하거나 30분을 더하지 않는다.
- 실제 순수 caption fallback/후처리, career Instagram/Threads, disaster texts를 실행한다. Shorts 태그 제외, 태그 상한, 원문 링크, 출처와 AI 음성/아바타 고지 보존을 검증한다. 생성형 caption 모델은 호출하지 않았다.

**부모 작업의 2026-10-31 범위 결정:** 6A는 기존 TikTok 큐 유지와 관리 관측·차단 근거를 수락한다. 관리 TikTok selector/adapter와 전체 23경로의 실제 전환은 6B 필수 잔여다. 관리 큐 전체 기능 동치·23경로 실운영 완료를 주장하지 않는다. social 변환은 legacy 순수 구간 실행과 관리 transform ID/계약 보존까지 확인했으며, 모든 관리 변환기의 실출력 동치는 6B에 남는다.

## 7개 연결별 지원과 미실행 근거

`구현/fixture`는 A6/A7 소스와 담당 집중 시험 보고에 근거한다. 현재 A10에서 그 전체 명령을 다시 실행한 결과가 아니다. 최종 전체 검증 결과는 아래 별도 절에 기록한다. 실인증·실발행 칸의 미실행을 fixture로 채우지 않는다.

| 연결 | 구현 | transport fixture | 순수 준비 | 실인증 | 실발행 | 공개 검증 | 내용 검증 | 성과 | 후처리 |
|---|---|---|---|---|---|---|---|---|---|
| dept.blogger | 고정 leaf·Google service | A6 fixture 근거 | 변환 구현·fixture | 미실행 | 미실행 | 관측 구현·실미확인 | 본문/매체 근거 필요 | 실수집 미확인 | legacy 다중효과 분해 잔여 |
| personal.blogger | 별도 개인 credential binding | A6 fixture 근거 | 변환 구현·fixture | 미실행 | 미실행 | 관측 구현·실미확인 | 출처·HTML bytes 정합 필요 | 실수집 미확인 | legacy 다중효과 분해 잔여 |
| dept.naver_blog | 학과 DOM leaf | A6 fixture 근거 | 입력·업로드 없는 변환 | 미실행 | 미실행 | selector 실미확인 | 원격 매체 bytes 미확인 | 실수집 미확인 | 대상별 분해 잔여 |
| personal.naver_blog | safeworking DOM leaf | A6 fixture 근거 | 카테고리/출처 보존 | 미실행 | 미실행 | selector 실미확인 | 구성/원격 매체 실미확인 | 실수집 미확인 | 대상별 분해 잔여 |
| personal.tistory | TinyMCE·첨부 leaf | A6 fixture 근거 | 순수 준비·fixture | 미실행 | 미실행 | exact ID 관측·실미확인 | 원격 첨부 bytes 미확인 | 실수집 미확인 | 강한 ID 없는 조회 미지원 |
| dept.youtube | 업로드·예약 leaf | A7 fixture 근거 | metadata/media 계약 | 미실행 | 미실행 | 예약은 공개 전 | 미디어 bytes 없으면 pending | 실수집 미확인 | 썸네일/playlist/comment/caption/public switch/TikTok 별도 승인 잔여 |
| personal.youtube | 개인 credential·채널 고정 | A7 fixture 근거 | metadata/media 계약 | 미실행 | 미실행 | 예약은 공개 전 | 미디어 bytes 없으면 pending | 실수집 미확인 | 같은 별도 승인·완료 근거 필요 |

Blogger의 새 local asset upload, Naver/Tistory의 ID 없는 강한 원격 부재 증명, 실제 DOM 불변 ID/selector, YouTube의 공개 매체 정합은 미지원/미확인 경계를 유지한다. 표시명·이메일·제목·URL 유사성이나 로컬 승인 hash로 채우지 않는다. 후처리 intent가 있다는 사실을 완료로 세지 않는다.

## 실구독·검토·품질 수락

실제 구독 모델 실행, 실제 독립 검산·출처 검토, 학교 API/유료 모델 권한, 실계정 인증은 이번 수락에서 실행하지 않았다. 개인 구독-only 정책을 다른 API로 우회하지 않으며 학과 허용 정책은 별도로 유지한다.

A5 fixture의 source checker는 시험 provider다. 실제 출처 응답 bytes·발행일·인용 일치 수락이 아니며 해당 provenance는 별도 실자료로 확인해야 한다. source URL이 있다는 사실만으로 출처 검토 완료가 아니다.

이미지 재사용 근거·영상 1080×1920/20초·장면/글꼴·음성·AI 고지 계약과 누락 차단은 코드/fixture 범위다. 실제 Voicebox 음성, Remotion 결과, 사람의 장면별 품질 확인은 미실행이다. PDF는 기본 등록 safe parser가 없으므로 실제 안전 파싱·페이지 렌더·내용 확인을 완료했다고 표시하지 않는다. PDF 필수 작업은 검증 근거가 없으면 blocked를 유지한다.

## 실제 검증 결과와 최신 전체 판정

| 범위·명령 | 실제 결과와 한계 |
|---|---|
| 기존 Pillow 설치 Python3.12의 `-m unittest discover -s tests -p 'test_*.py'` | 872개 OK, 102.148초, 실패/오류/skip0. 부모 session1429 exit0, `/private/tmp/autosns-full-python-pillow.log` 직접 확인 |
| 기존 Python3.15 전체 실행 | 실제 로그인 브라우저 프로필 대기로 중단. session90765 exit130이며 성공 근거에서 제외 |
| `node --test tests/*.mjs` 이전 전체 결과 | 195개 pass, fail/cancelled/skipped/todo0, 2249.221225ms. `/private/tmp/phase6a-final-node-full.log` 직접 확인. 그 뒤 Task6 JS 수정이 있어 최신 전체 결과는 아님 |
| `node --test tests/web_toolkit.test.mjs` 후속 집중 결과 | Task6 fix1 보고의20개 pass, 실패/취소/skip/todo0, 152.804785ms. 전체 Node 대체 아님 |
| HTTP 집중 회귀 | 78개 OK, 24.402초, 실패/오류/skip0. `/private/tmp/phase6a-http-final.log`의 이전 보조 근거 유지 |
| 최신 Task8 통합 뒤 전체 Python/Node | 아직 미실행. 부모가 마지막 코드 commit 뒤 한 번 실행해 결과를 갱신할 예정 |
| `python3 -m common.tools.check_operations_release --evidence /private/tmp/phase6a-offline-evidence.json --mode offline` | 이번 로컬 실행 exit1. offline_ready=false/production_ready=false. 명시한 최신 전체 시험 대기 행으로 `offline:test_results_incomplete` 유지 |

최신 evidence의 code_revision은 생성 순간 HEAD `9295a54819e23bd7b8fd7f72eccd9bce34f4489f`, SHA-256은 `a0232828ce962ee1fc46481029968d6b5189fc77897b3036afea36d5c2f01268`이다. 전체23행 fixture/등록부와 source hash를 읽어 대조했고 stale 파일0이다. 이미 통과한 Python872·이전Node195·집중20·HTTP78은 그대로 보존하고 최종 Node 대기 행을 추가했으며 수치나 상태를 위조해 통과시키지 않았다.

production blocker는 전체 caller inventory, live_auth/live_publish 미수집, live 원장 결속 미완료, 실제 backup restore 미수락, CLI 실제 runtime store 부재, legacy owner다. 이 offlinefalse는 병행 Task8을 포함한 최신 전체 검증 대기이고, productionfalse는 실제 운영 권한/증거 미완료다. 두 사유를 구분한다. 최종 code_revision은 HEAD이며 모든 미커밋 파일의 무결성 인증은 아니다.

## 실제 UI·배포 확인과 미확인

| 확인 범위 | 근거·판정 |
|---|---|
| 최신 격리 fixture 승인/unknown | 부모 IAB22에서 원고v1/계획v1/명시 작업·회차→읽기→의도확인→체크박스→별도 승인. unknown_remote/v3 주입 뒤 원격ID/미확인/필수댓글 미시작, 변이4종 비활성·refresh 활성 DOM 확인 |
| 제작 입력v1/산출v2·Escape | 부모 IAB23에서 input hash/버전 유지, 별도 outputv2, 사용량 미확인·독립 검토 필요 확인. 선택 원고 자동 교체0, Escape 뒤 dialog0·원래 원고 버튼 포커스 복원 |
| 실제 계획 CAS409 | 부모 격리65416에서 별도 SQLite Ledger.cancel로 planv2를 만든 뒤 화면v1의 읽기 요청이 실제 CAS409. 원고/계획/요청 보존과 명시 복구 선택지 표시 확인. 전체 복구 closure 성공까지 수락한 것은 아님 |
| 실제 사용자8769 메뉴 | 부모 새 탭25에서 기술사 메뉴·건축 필터·실자료 표시 확인. [배포 화면](../../ax-console/design/previews/phase6a-deployed-engineer.png) |
| 아직 최신 브라우저에서 미확인 | 최신401/503 입력 보존, 상태 재선택의 모든 복구 분기,320px 전체 화면 overflow, 실제8767 화면 전부. 이전 QA/Node 결과를 최신 브라우저 PASS로 대체하지 않음 |

격리 UI 근거: [별도 승인](../../ax-console/design/previews/phase6a-final-approval.png), [unknown](../../ax-console/design/previews/phase6a-final-unknown.png), [제작v1/v2](../../ax-console/design/previews/phase6a-final-production.png), [계획 CAS충돌](../../ax-console/design/previews/phase6a-real-plan-conflict.png). 브라우저 수락은 부모의 실제 관찰과 `task-9-final-browser-qa.md` 기록이며 이 문서 담당자가 재실행하지 않았다. fixture UI는 실플랫폼/worker 성공이 아니다.

부모는 기존 PID13057/13063의 명령·포트를 확인해 정지한 뒤 quiesced backup `ax-console/data/deployment-backups/phase6a-quiesced-20261031T012252315404Z`를 만들었다. manifest6개를 확인해 실제 W에 적용했고 새8769 session57014/읽기전용8767 session61922를 시작했다. 이번 문서 갱신에서도6개 실제 파일이 HEAD·artifact SHA와 모두 같음을 읽기 전용으로 확인했다. 발행 서비스는 기본 미주입/비활성이며 실제 SNS 발행은0이다.

부모의 배포 전후 DB 대조: operations 기존26개 테이블의 행수가 모두0으로 동일, user_version3 유지, 추가8개 empty table(`production_bindings`, `production_attempts`, `production_output_links`, `execution_receipts`, `admission_observations`, `publication_approval_requests`, `service_run_results`, `bridge_redemptions`), integrity_check=ok. metrics는 논리 내용 동일·user_version1·integrity_check=ok다. 기존 빈 자료 보존의 실제 근거이며, 비어 있지 않은 운영 DB 복원 시험이나 원격 이력 복구 완료를 입증하지 않는다.

후속 툴킷 Task8은 현재 actual==HEAD를 새 original 기준선으로 manifest를 작성해야 한다. 예전6A original SHA를 재적용하면 이미 배포된 화면을 되돌릴 수 있다. 원래 계획 작업공간은 아직 참조가 남아 있으므로 삭제하지 않았다.

## 6B–6D 및 운영 필수 잔여

- 6B: 전체 caller/leaf/다중 부수효과·공식 권한·TikTok 관리 실행기와 23경로 전환. disabled/unknown·기존 자동 진행 수준을 유지하며 경로별 승인·잠금·quota를 독립 확인한다.
- 6C–6D: 승인 계획의 후속 계층, 실제 모델/검토·미디어/PDF 품질·백업 복구·운영 전환 체크포인트. 원본 R·키·로그인 디렉터리·venv는 별도 수락 없이 이동하지 않는다.
- 외부 접속: 사용자 선택의 Mac·휴대폰 외부 접속은 필수 최종 요구다. localhost fixture/웹 검증으로 완료하거나 삭제하지 않는다.
- 롤백: 새 remote ID·unknown·attempt·quota·제작 unit 이력과 요청 receipt를 잊는 과거 DB 덮어쓰기/legacy 재개를 거부한다. 실제 복구 시험과 양쪽 원장 보존 대조는 다음 운영 체크포인트다.

근거: `tests/integration/test_phase6a_acceptance.py`, `tests/integration/fixtures/phase6a-crosspost-events.json`, `docs/audits/2026-10-30-live-entrypoint-readiness.md`, `docs/runbooks/execution-entrypoint-inventory.json`, `.superpowers/sdd/2026-10-30-web-phase6a/task-6-report.md`, `task-7-report.md`, `task-10-preparation-report.md`. 6A 코드 독립 수락·정적 배포와 제한된 UI 확인을 기록했으며, 최신 전체 작업 사본 검증과 실운영 필수 잔여는 계속 분리한다.
