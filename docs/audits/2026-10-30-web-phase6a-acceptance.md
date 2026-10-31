# 6A 실행 연결 수락 — 통합 진행 중

2026-10-31 현재 **집중 fixture 검증 단계**다. A8 fix1(commit 2ced4dc)은 독립 검토를 통과했고 전체 Python 806개가 통과했다. A9 후속 수정과 Node·release CLI·브라우저/배포 확인은 진행 중이다. `production_ready=false`를 유지하며 실제 계정 로그인·발행·운영 스케줄 전환·폴더 이동은 수행하지 않았다. 이 문서는 6A 오프라인 범위의 근거와 후속 수락 조건을 분리해 기록한다.

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

## 최종 전체 검증 — 대기

부모 작업이 전달한 실제 결과만 반영한다. HTTP 집중 78개와 전체 Python 806개가 통과했다. A9 반복 새로고침에서 unknown 버전4가 queued 버전3으로 되돌아가는 지적의 후속 수정은 진행 중이다. Node·최종 release CLI·브라우저 최종 확인·배포 확인은 대기이며, 후속 코드 변경이 기존 시험 결과에 영향을 주는지는 최종 통합에서 확인한다.

| 명령 | 현재 실제 결과 |
|---|---|
| `python3 -m unittest tests.test_web_execution tests.test_web_execution_server tests.test_web_server tests.test_web_operations -v` | 78개 OK, 24.402초, 실패/오류/skip 0. 부모 elevated 실행, 로그 `/private/tmp/phase6a-http-final.log` 확인 |
| `python3 -m unittest discover -s tests -p 'test_*.py'` | 806개 OK, 90.352초, 실패/오류/skip 0. 부모 elevated 실행 session 29299 exit0, 로그 `/private/tmp/phase6a-python-full.log` 확인 |
| `node --test tests/*.mjs` | 대기 — 전체 suite 미실행 |
| `python3 -m common.tools.check_operations_release --evidence /private/tmp/phase6a-offline-evidence.json --mode offline` | 대기 — 최종 evidence 파일 미생성 |
| 브라우저 최종 확인·배포 확인 | 대기 — HTTP fixture 결과로 대체하지 않음 |

`offline_ready`는 서버 기준선·분리된 시험 선언/fixture 지원 범위와 미전환 차단 근거를 분류한다. 실인증·실발행·배포 승인으로 쓰지 않는다. 현재 `production_ready=false`, `live_ledger_verification_pending` 하드 게이트와 backup/restore 수락 잔여를 유지한다.

## 6B–6D 및 운영 필수 잔여

- 6B: 전체 caller/leaf/다중 부수효과·공식 권한·TikTok 관리 실행기와 23경로 전환. disabled/unknown·기존 자동 진행 수준을 유지하며 경로별 승인·잠금·quota를 독립 확인한다.
- 6C–6D: 승인 계획의 후속 계층, 실제 모델/검토·미디어/PDF 품질·백업 복구·운영 전환 체크포인트. 원본 R·키·로그인 디렉터리·venv는 별도 수락 없이 이동하지 않는다.
- 외부 접속: 사용자 선택의 Mac·휴대폰 외부 접속은 필수 최종 요구다. localhost fixture/웹 검증으로 완료하거나 삭제하지 않는다.
- 롤백: 새 remote ID·unknown·attempt·quota·제작 unit 이력과 요청 receipt를 잊는 과거 DB 덮어쓰기/legacy 재개를 거부한다. 실제 복구 시험과 양쪽 원장 보존 대조는 다음 운영 체크포인트다.

근거: `tests/integration/test_phase6a_acceptance.py`, `tests/integration/fixtures/phase6a-crosspost-events.json`, `docs/audits/2026-10-30-live-entrypoint-readiness.md`, `docs/runbooks/execution-entrypoint-inventory.json`, `.superpowers/sdd/2026-10-30-web-phase6a/task-6-report.md`, `task-7-report.md`, `task-10-preparation-report.md`. 이 문서의 상태는 실제 전체 결과와 독립 검토 전까지 진행 중이다.
