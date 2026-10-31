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

Task8 최초 검증(최종 검토 전)은 artifact editor 모듈을 DOM harness에서 열어 toolkit-stage CustomEvent→깨끗한 hash/context 재검증→title/가짜 본문 후보 초안 반영→기존 fullpayload(expected_revision 포함) 저장을 실행했다. 당시 가짜 계약에서 variants·sources·series·status 보존과 미리보기 후 수정/늦은 응답의 후보 미반영, 타이핑 focus 유지도 확인했다. accounts/planning/analytics/schedule의 도구 범위를 분리하며 render는 HTTP를 보내지 않는다. 기존 9개 nav와 기술사 메뉴를 유지한다.

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

최종 검토에서 최초 Node 시험의 본문 후보 계약이 실제 서버의 hashtags 계약과 다른 것으로 확인했다. 최종 수정은 실제 서비스 응답 형태를 소비하여 제목과 명시 선택 변환문 태그만 반영하고, original·다른 변환문·sources·series·status를 보존하도록 바꾼다. 수정 후 시험/브라우저/배포 증거는 별도 갱신하며 위 최초 결과를 수정 후 성공 증거로 재사용하지 않는다.

## 최종 재검토 후 현재 판정

2026-10-31 수정 커밋 `9a3607d`의 집중 검증은 Node55/Python32, 작업 artifact 없는 임시 추적 파일 시험은 Node30/Python HTTP9가 통과했다. 이 숫자는 전체 회귀나 배포 수락을 뜻하지 않는다.

독립 제한 재검토와 실제 격리 브라우저 확인에서 **Important 2건이 남아 배포를 보류**했다. 변환문 선택 취소 후 다른 입력을 바꾸면 태그 버튼이 다시 활성화되어 첫 변환문에 반영될 수 있다. 첨부 이미지를 선택해도 이미지 검사 버튼이 활성화되지 않는다. 자동 시험의 통과만으로 두 문제를 통과 처리하지 않는다.

실제 격리 화면에서는 개인 원본 v3의 학과용 변환문을 명시 선택해 태그를 붙이고 기존 CAS로 v4 저장하는 정상 경로를 확인했다. 원문·개인용 변환문·출처·자산을 보존하고 검토 기록은 재사용하지 않았다. 증거는 `ax-console/design/previews/toolkit-final-variant-save.png`다. 실제 발행·추가 과금은 없으며 기존 8769/8767 서버는 변경하지 않았다.

최종 절차의 단일 수정 제한 이후 추가 수정을 사용자에게 확인 중이다. 이 단계는 구현 완료·운영 준비 완료로 판정하지 않는다.

## 선택 상태 오류 추가 수정 검증

후속 `dafe9b2`에서 두 오류를 승인된 기능의 결함 수정으로 처리했다. 별도 추가 승인 요구는 철회했다. 선택 취소→무관한 입력→태그 적용 차단, 명시 index0 정상 처리, 이미지 선택/해제 즉시 버튼 반영의 실제 이벤트 회귀를 추가했다. 집중58개 및 전체 Node **216개 PASS / 실패0 / skip0**(`/private/tmp/toolkit-selection-full-node.log`). Python 제품코드는 이 후속에서 바뀌지 않았다.

새 격리 서버의 실제 브라우저에서 정상 이미지1280×720 표시, 손상 이미지 ‘이미지를 해석할 수 없습니다’ 표시, 개인→학과 변환문 선택취소 뒤 썸네일 제목 입력에도 태그 버튼 비활성을 확인했다. `ax-console/design/previews/toolkit-fixed-image-inspection.png`에 화면 증거를 저장했다. 이 기록이 앞선 두 오류의 미해결 상태를 대체한다. 최신 독립 검토·나머지 브라우저 수락·보호 배포는 별도로 유지한다. 실제 계정·발행·모델 호출 없음.

독립 선택 상태 회귀 검토: R1/R2 모두 해결, 해당 두 파일 새 잔여 지적 없음. 검토자는 focused58/전체Node216 로그를 확인했으며 suite를 중복 실행하지 않았다. 전체 Python 회귀는 후속 실행 중이므로 아직 통과로 표시하지 않는다.

## 최신 통합 회귀와 반응형 화면

시험 fixture를 실제 Connection 계약으로 보완한 `e58e9d1` 기준 전체 Python **884 tests / 87.391s / OK / skip0**(`/private/tmp/toolkit-latest-full-python-rerun.log`, session65632 exit0). 앞선884 중1error는 fixture 필드 누락이었으며 성공으로 세지 않았다. 전체Node216PASS는 동일 제품 bytes 기준이다.

IAB34 실제 격리 화면에서320×780 기획/편집기 scrollWidth=320, clientWidth=320, Tab으로 원본 버전 선택 이동;1280×800에서 scrollWidth=1280을 확인했다. viewport override는 reset했다. 저장 근거 조사에서 누적 표본3·기간표본1·custom정의별 분리와 근거부족을 표시했다. 가상자료이며 실수집 증거가 아니다. 화면증거 `toolkit-320-editor.png`, `toolkit-research-1280.png`. 보호 배포 및 나머지 오류 상태의 브라우저 수락은 후속으로 남긴다.

## 개발 서버 화면 배포

2026-10-31 11:06 KST 부모 소유8769/8767만 PID/cwd/명령/포트 확인 후 정상 종료했다. 전체 managed-workspace(WAL/자산 포함)·web-before·manifest·HEAD를 `ax-console/data/deployment-backups/toolkit-20261031T020602792714Z/`에 백업했다. held6와 기술사 label7파일을 일괄 SHA 선검증 후 적용했다. actual==HEAD 확인, git 작업트리 clean.

기존 명령으로 재시작한 managed8769(session60061)·readonly8767(session87379) 모두200 로그인 응답. operations/metrics SQLite의 integrity_check=ok, 백업 대비 전체 logical dump 동일. 원본R/8700/프로필/스케줄/실제 발행 변경 없음.

IAB35 실제8769 채널·계정에서 새 로컬 SNS 도구7기능·한국어 비용라벨·등록 연결을 표시하고, 도구 상태 확인 결과 **로컬 정책 비활성 / 외부 실행 미지원 / 실행 서비스 미연결·기본 비활성**을 확인했다. `toolkit-deployed-accounts.png` 화면 증거. 화면 배포와 toolkit/renderer 활성화는 별개이며 현 main은 정책/renderer를 주입하지 않는다. 실제 작업 사용 활성화·남은 상세 오류상태 수락·6B~D는 아직 미완료다.
