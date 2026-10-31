# 2026-10-31 로컬 SNS 도구 Task8 수락 기록

현재 상태는 **구현 및 집중 자동검증 완료, 전체 회귀·독립 리뷰·브라우저·배포 수락 대기**다. 이 문서는 실발행·실인증·운영 준비 완료를 뜻하지 않는다.

## 실제 실행 근거

- RED: `python3 -m unittest tests.test_web_toolkit_server tests.integration.test_local_toolkit_acceptance -v` → 6 tests, 4 ERROR(신규 toolkit_policy kwarg 미연결), 1 FAIL(toolkit mount 미연결), 1 PASS.
- RED: `node --test tests/web_toolkit_integration.test.mjs` → 3 tests, 1 PASS(9메뉴), 2 FAIL(mount/hash binding 부재).
- 최초 GREEN 시도에서 loopback bind가 sandbox `PermissionError: [Errno 1] Operation not permitted`로 차단됐다. 같은 차단을 반복하지 않고 해당 임시 HTTP 집중 명령만 require_escalated로 실행했다. 실제 계정·프로필·기존 서버 접근은 없다.
- 중간 HTTP 검증: 6 tests, 5 PASS/1 FAIL. 첫 후보가 원제목과 같아 hash가 같았으며, 시험에서 원제목과 다른 후보를 명시적으로 선택하도록 수정했다.
- 최종 HTTP 집중: `python3 -m unittest tests.test_web_toolkit_server tests.integration.test_local_toolkit_acceptance -v` → **7 tests / OK / 2.753s**. require_escalated, 임시 source/W/webroot·loopback 임시 포트만 사용.
- 최종 Node 집중: `node --test tests/web_toolkit_integration.test.mjs tests/web_toolkit.test.mjs tests/web_app_focus.test.mjs` → **31 tests / pass 31 / fail 0 / skipped 0**, duration_ms 295.862933.
- 관련 읽기 모델 회귀: `python3 -m unittest tests.test_read_model -v` → **20 tests / OK / 0.214s**. 기존 카탈로그 id/status 및 snapshot 계약 보존을 확인했다.
- `python3 -m py_compile common/operations/provider_capabilities.py common/operations/tool_cost_policy.py common/operations/local_toolkit.py ax-console/app/web_tools.py ax-console/app/web_server.py ax-console/app/read_model.py` → exit 0.
- `git diff --check` → exit 0.

전체 Python discover 및 전체 Node suite는 부모가 최종 통합 뒤 실행한다. 이 문서에 과거 단계 전체 suite 숫자를 복사하지 않았다.

## 확인한 경계

HTTP는 인증 401, 외부 Origin 403, 중복 query/JSON·NaN 400, 초과 body 413, 읽기 전용 POST 503을 검사했다. default toolkit/execution 비활성·renderer/authorizer 미등록과 신규 정적 모듈 3개의 인증 경계를 확인했다. 비용/target/policy 위조는 leaf 호출 전에 거부하며 비용 정책 차단도 leaf 0이다.

CSV import는 동일 receipt를 재사용하며 운영 operations.sqlite3 bytes를 보존한다. 변경된 원문/digest는 409이고 관측은 legacy_reported다. HTTP에 내부 import plan과 원본 source provenance를 공개하지 않는다. CAS 저장은 전체 원고 필드를 보존하고 새 revision에 기존 review를 복사하지 않으며 stale expected_revision은 409다.

Node는 실제 Task8 artifact editor 모듈을 DOM harness에서 열어 toolkit-stage CustomEvent→깨끗한 hash/context 재검증→title/선택 본문만 초안 반영→기존 fullpayload(expected_revision 포함) 저장을 실행했다. variants·sources·series·status 보존과 미리보기 후 수정/늦은 응답의 후보 미반영, 타이핑 focus 유지도 확인했다. accounts/planning/analytics/schedule의 도구 범위를 분리하며 render는 HTTP를 보내지 않는다. 기존 9개 nav와 기술사 메뉴를 유지한다.

320px용 CSS와 1280px에서도 입력 최대 폭을 제한하는 계약은 자동 검사했지만 **브라우저 실제 크기·focus traversal·console·screenshot은 아직 미확인**이다. 썸네일의 실제 출력 브라우저 수락도 미확인이다. 서버 등록 글꼴 경로의 파일 존재 여부는 True였으나 이것을 renderer 등록·글꼴 SHA/decoder 환경 검증 완료로 승격하지 않았다.

## 준비 상태를 분리한 판정

| 항목 | 상태 | 범위 |
|---|---|---|
| local_rules_ready | 집중 QA 통과 | 저장 근거 규칙·기존 CAS 연동, 실제 배포 대기 |
| manual_csv_ready | 집중 QA 통과 | 임시 초기화 저장소, 운영 반영 미실행 |
| thumbnail_environment_ready | 미확인/미등록 | 기본 renderer/authorizer None, 브라우저 실제 PNG 출력 미확인 |
| local_toolkit_enabled | false | 운영 기본값, 격리 QA에서만 명시 주입 |
| live_collection_ready | false | 실수집·원격 읽기 권한 확인 없음 |
| production_ready | false | 전체 회귀·리뷰·브라우저·배포 및 후속 운영 수락 대기 |

## 보호 및 미완료

시작 HEAD와 staged 경로, held6 각각의 actual original SHA 및 artifact SHA는 Task8 manifest에 기록했다. 시작 시 actual held6==desired HEAD였음을 byte 단위 비교했다. 집중 검증은 actual held SHA==original SHA 및 잘못된 원본 hash가 partial overlay 전에 차단됨을 검사했다. 실제 held6 변경·실서버 restart·stage·commit은 작업자가 수행하지 않았다. 별도 기술사 라벨 artifact와 6A audit 수정은 부모/다른 작업자의 소유이며 변경하지 않았다.

신규 최상위 메뉴·발행기·예약 실행·model/provider fallback·credential I/O는 추가하지 않았다. 개인 subscription_only, 기존 23경로·TikTok 큐·STOP·unknown·Blog5/YouTube2·기술사 일차/친구 요청/PDF 경계를 보존한다. 6B~6D 실제 운영 목표와 건축시공 필수 후속, 실인증·실수집·게시 검증은 미완료다.
