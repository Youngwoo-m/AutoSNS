# 2026-10-31 로컬 SNS 도구 Task8 수락 기록

현재 상태는 **로컬 도구 구현·독립 검토·전체 회귀·격리 브라우저 수락 및 개발 서버 화면 배포 완료, 실제 사용 활성화는 설계 승인 대기**다. 8769/8767의 화면은 갱신됐지만 실제 main의 toolkit 정책은 비활성이며 renderer/authorizer와 실행 서비스도 미주입이다. 이 문서는 실발행·실인증·전체 운영 준비 완료를 뜻하지 않는다.

최신 근거는 전체 Python **884 tests / 87.391s / OK / skip0**, 전체 Node **216 PASS / 실패0 / skip0**다. R1/R2는 후속 수정과 독립 검토 및 실제 화면에서 해결을 확인했다. 320/1280 폭·키보드 이동, 이미지 정상/손상 표시, 개인→학과 선택 변환문/CAS 보존, 401 재로그인·409 CAS 충돌·503 실제 SQLite 쓰기 실패와 재시도도 격리 환경에서 확인했다. 아래 초기 RED/GREEN과 보류 기록은 개발 이력이며 최신 판정을 덮어쓰지 않는다.

## Task8 최초 실행 이력 — 최종 수정 전

- RED: `python3 -m unittest tests.test_web_toolkit_server tests.integration.test_local_toolkit_acceptance -v` → 6 tests, 4 ERROR(신규 toolkit_policy kwarg 미연결), 1 FAIL(toolkit mount 미연결), 1 PASS.
- RED: `node --test tests/web_toolkit_integration.test.mjs` → 3 tests, 1 PASS(9메뉴), 2 FAIL(mount/hash binding 부재).
- 최초 GREEN 시도에서 loopback bind가 sandbox `PermissionError: [Errno 1] Operation not permitted`로 차단됐다. 같은 차단을 반복하지 않고 해당 임시 HTTP 집중 명령만 require_escalated로 실행했다. 실제 계정·프로필·기존 서버 접근은 없다.
- 중간 HTTP 검증: 6 tests, 5 PASS/1 FAIL. 첫 후보가 원제목과 같아 hash가 같았으며, 시험에서 원제목과 다른 후보를 명시적으로 선택하도록 수정했다.
- 최종 HTTP 집중: `python3 -m unittest tests.test_web_toolkit_server tests.integration.test_local_toolkit_acceptance -v` → **7 tests / OK / 2.753s**. require_escalated, 임시 source/W/webroot·loopback 임시 포트만 사용.
- 최종 Node 집중: `node --test tests/web_toolkit_integration.test.mjs tests/web_toolkit.test.mjs tests/web_app_focus.test.mjs` → **31 tests / pass 31 / fail 0 / skipped 0**, duration_ms 295.862933.
- 관련 읽기 모델 회귀: `python3 -m unittest tests.test_read_model -v` → **20 tests / OK / 0.214s**. 기존 카탈로그 id/status 및 snapshot 계약 보존을 확인했다.
- `python3 -m py_compile common/operations/provider_capabilities.py common/operations/tool_cost_policy.py common/operations/local_toolkit.py ax-console/app/web_tools.py ax-console/app/web_server.py ax-console/app/read_model.py` → exit 0.
- `git diff --check` → exit 0.

이 최초 단계에서는 전체 회귀를 아직 실행하지 않았다. 이후 실제 실행한 최신 전체 결과는 문서 상단과 「최신 통합 회귀와 반응형 화면」에 기록했다.

## 최초 집중 시험에서 확인한 경계

HTTP는 인증 401, 외부 Origin 403, 중복 query/JSON·NaN 400, 초과 body 413, 읽기 전용 POST 503을 검사했다. default toolkit/execution 비활성·renderer/authorizer 미등록과 신규 정적 모듈 3개의 인증 경계를 확인했다. 비용/target/policy 위조는 leaf 호출 전에 거부하며 비용 정책 차단도 leaf 0이다.

CSV import는 동일 receipt를 재사용하며 운영 operations.sqlite3 bytes를 보존한다. 변경된 원문/digest는 409이고 관측은 legacy_reported다. HTTP에 내부 import plan과 원본 source provenance를 공개하지 않는다. CAS 저장은 전체 원고 필드를 보존하고 새 revision에 기존 review를 복사하지 않으며 stale expected_revision은 409다.

Task8 최초 검증(최종 검토 전)은 artifact editor 모듈을 DOM harness에서 열어 toolkit-stage CustomEvent→깨끗한 hash/context 재검증→title/가짜 본문 후보 초안 반영→기존 fullpayload(expected_revision 포함) 저장을 실행했다. 당시 가짜 계약에서 variants·sources·series·status 보존과 미리보기 후 수정/늦은 응답의 후보 미반영, 타이핑 focus 유지도 확인했다. accounts/planning/analytics/schedule의 도구 범위를 분리하며 render는 HTTP를 보내지 않는다. 기존 9개 nav와 기술사 메뉴를 유지한다.

최초 단계에서는 320/1280 폭의 CSS 계약만 자동 검사했고 실제 브라우저·썸네일 출력은 미확인이었다. 이후 폭·키보드 이동·화면 증거와 격리 이미지 검사/출력은 별도로 확인했다. 파일 존재만으로 renderer 등록이나 현재 운영 환경 준비를 인정하지 않는 경계는 유지한다. console 전체 무오류 판정을 추가로 주장하지 않는다.

## 준비 상태를 분리한 판정

| 항목 | 상태 | 범위 |
|---|---|---|
| local_rules_ready | 코드·격리 수락 통과, 화면 배포 완료 | 실제 8769 정책은 비활성. 관리 원본 분석 사용 활성화는 별도 설계 승인 대기 |
| manual_csv_ready | 코드·격리 수락 통과, 화면 배포 완료 | 0·중복·401/503 재시도 검증. 실제 관리 DB 가져오기는 미실행 |
| thumbnail_environment_ready | 격리 Pillow 환경 검증, 실제 서버 미등록 | 정상/손상 검사 및 PNG 출력 증거가 있으나 실제 main renderer/authorizer None |
| local_toolkit_enabled | false | 8769/8767 기본값 유지, 격리 QA에서만 명시 주입 |
| live_collection_ready | false | 실수집·원격 읽기 권한 확인 없음 |
| production_ready | false | 로컬 사용 활성화·SNS 실권한/실발행·6B~D 및 건축 운영 수락 미완료 |

## 보호 및 미완료

시작 HEAD와 staged 경로, held6 각각의 actual original SHA 및 artifact SHA는 Task8 manifest에 기록했다. 시작 시 actual held6==desired HEAD였음을 byte 단위 비교했다. 집중 검증은 actual held SHA==original SHA 및 잘못된 원본 hash가 partial overlay 전에 차단됨을 검사했다. 이 최초 단계의 작업자는 실제 held6 변경·실서버 restart·stage·commit을 수행하지 않았다. 이후 부모의 보호 배포는 「개발 서버 화면 배포」에 별도로 기록했다. 별도 기술사 라벨 artifact와 6A audit 수정은 부모/다른 작업자의 소유이며 변경하지 않았다.

신규 최상위 메뉴·발행기·예약 실행·model/provider fallback·credential I/O는 추가하지 않았다. 개인 subscription_only, 기존 23경로·TikTok 큐·STOP·unknown·Blog5/YouTube2·기술사 일차/친구 요청/PDF 경계를 보존한다. 6B~6D 실제 운영 목표와 건축시공 필수 후속, 실인증·실수집·게시 검증은 미완료다.

최종 검토에서 최초 Node 시험의 본문 후보 계약이 실제 서버의 hashtags 계약과 다른 것으로 확인했다. 최종 수정에서 실제 서비스 응답 형태를 소비하여 제목과 명시 선택 변환문 태그만 반영하고, original·다른 변환문·sources·series·status를 보존하도록 바꿨다. 아래 후속 시험/브라우저/배포 증거가 수정 후 판정이며 위 최초 결과를 재사용한 것이 아니다.

## 최종 재검토 당시 보류 이력 — 후속 해결됨

2026-10-31 수정 커밋 `9a3607d`의 집중 검증은 Node55/Python32, 작업 artifact 없는 임시 추적 파일 시험은 Node30/Python HTTP9가 통과했다. 이 숫자는 전체 회귀나 배포 수락을 뜻하지 않는다.

독립 제한 재검토와 실제 격리 브라우저 확인에서 **Important 2건이 남아 배포를 보류**했다. 변환문 선택 취소 후 다른 입력을 바꾸면 태그 버튼이 다시 활성화되어 첫 변환문에 반영될 수 있다. 첨부 이미지를 선택해도 이미지 검사 버튼이 활성화되지 않는다. 자동 시험의 통과만으로 두 문제를 통과 처리하지 않는다.

실제 격리 화면에서는 개인 원본 v3의 학과용 변환문을 명시 선택해 태그를 붙이고 기존 CAS로 v4 저장하는 정상 경로를 확인했다. 원문·개인용 변환문·출처·자산을 보존하고 검토 기록은 재사용하지 않았다. 증거는 `ax-console/design/previews/toolkit-final-variant-save.png`다. 실제 발행·추가 과금은 없으며 기존 8769/8767 서버는 변경하지 않았다.

당시 추가 수정 확인을 요청했으나, 이미 승인된 기능의 결함 수정 범위임을 재판단해 불필요한 추가 승인 요구를 철회했다. 다음 항목의 후속 수정이 두 오류의 현재 판정을 대체한다.

## 선택 상태 오류 추가 수정 검증

후속 `dafe9b2`에서 두 오류를 승인된 기능의 결함 수정으로 처리했다. 별도 추가 승인 요구는 철회했다. 선택 취소→무관한 입력→태그 적용 차단, 명시 index0 정상 처리, 이미지 선택/해제 즉시 버튼 반영의 실제 이벤트 회귀를 추가했다. 집중58개 및 전체 Node **216개 PASS / 실패0 / skip0**(`/private/tmp/toolkit-selection-full-node.log`). Python 제품코드는 이 후속에서 바뀌지 않았다.

새 격리 서버의 실제 브라우저에서 정상 이미지1280×720 표시, 손상 이미지 ‘이미지를 해석할 수 없습니다’ 표시, 개인→학과 변환문 선택취소 뒤 썸네일 제목 입력에도 태그 버튼 비활성을 확인했다. `ax-console/design/previews/toolkit-fixed-image-inspection.png`에 화면 증거를 저장했다. 이 기록이 앞선 두 오류의 미해결 상태를 대체한다. 이후 독립 검토·브라우저 수락·보호 배포 결과는 다음 항목에 기록했다. 실제 계정·발행·모델 호출 없음.

독립 선택 상태 회귀 검토: R1/R2 모두 해결, 해당 두 파일 새 잔여 지적 없음. 검토자는 focused58/전체Node216 로그를 확인했으며 suite를 중복 실행하지 않았다. 당시 실행 중이던 전체 Python 회귀는 다음 항목에서 실제 종료 결과를 확인했다.

## 최신 통합 회귀와 반응형 화면

시험 fixture를 실제 Connection 계약으로 보완한 `e58e9d1` 기준 전체 Python **884 tests / 87.391s / OK / skip0**(`/private/tmp/toolkit-latest-full-python-rerun.log`, session65632 exit0). 앞선884 중1error는 fixture 필드 누락이었으며 성공으로 세지 않았다. 전체Node216PASS는 동일 제품 bytes 기준이다.

IAB34 실제 격리 화면에서320×780 기획/편집기 scrollWidth=320, clientWidth=320, Tab으로 원본 버전 선택 이동;1280×800에서 scrollWidth=1280을 확인했다. viewport override는 reset했다. 저장 근거 조사에서 누적 표본3·기간표본1·custom정의별 분리와 근거부족을 표시했다. 가상자료이며 실수집 증거가 아니다. 화면증거 `toolkit-320-editor.png`, `toolkit-research-1280.png`. 이후 보호 배포와 401/409/503 오류 복구 브라우저 수락은 아래에 기록했다.

## 개발 서버 화면 배포

2026-10-31 11:06 KST 부모 소유8769/8767만 PID/cwd/명령/포트 확인 후 정상 종료했다. 전체 managed-workspace(WAL/자산 포함)·web-before·manifest·HEAD를 `ax-console/data/deployment-backups/toolkit-20261031T020602792714Z/`에 백업했다. held6와 기술사 label7파일을 일괄 SHA 선검증 후 적용했다. actual==HEAD 확인, git 작업트리 clean.

기존 명령으로 재시작한 managed8769(session60061)·readonly8767(session87379) 모두200 로그인 응답. operations/metrics SQLite의 integrity_check=ok, 백업 대비 전체 logical dump 동일. 원본R/8700/프로필/스케줄/실제 발행 변경 없음.

IAB35 실제8769 채널·계정에서 새 로컬 SNS 도구7기능·한국어 비용라벨·등록 연결을 표시하고, 도구 상태 확인 결과 **로컬 정책 비활성 / 외부 실행 미지원 / 실행 서비스 미연결·기본 비활성**을 확인했다. `toolkit-deployed-accounts.png` 화면 증거. 화면 배포와 toolkit/renderer 활성화는 별개이며 현 main은 정책/renderer를 주입하지 않는다. 실제 작업 사용 활성화·SNS 실권한·6B~D는 아직 미완료다. 당시 남아 있던 401/409/503 상세 오류상태 수락은 아래 후속 기록으로 해결했다.

## 오류 복구 추가 브라우저 수락

실제 격리 서버54082에서 개인 CSV의177자 원문·미리보기를 준비한 뒤 fixture 인증만 만료시켰다. CSV 가져오기에서401 로그인 안내와 원문/미리보기 보존을 확인했다. 별도 가상 로그인 후 기존 탭의 동일 요청 재시도로 추가1/중복0을 확인했다. 증거 `toolkit-csv-401-preserved.png`, `toolkit-csv-relogin-retry.png`. 실제 세션·키·계정 변경 없음.

같은 임시 ContentStore 원고v3를 편집하는 동안 다른 store 인스턴스로 v4를 저장한 후 UI의 v3 저장을 실행했다. 실제409 안내와 미저장 제목 '[가상 QA] 충돌에도 보존할 제목' 보존을 확인했다. 증거 `toolkit-editor-409-preserved.png`. DB는 임시 fixture만 변경했고 실제 관리workspace는 변경하지 않았다.이 시점의503은 controller/HTTP시험 증거만 있었으며 다음 항목에서 실제 브라우저 검증을 추가했다.

## 실제 저장 실패503 브라우저 수락

격리54082의 CSV178자 미리보기 후 **임시 fixture metrics.sqlite3만** 별도sqlite 연결의 BEGIN IMMEDIATE로 잠갔다. 실제 가져오기 쓰기 timeout이503으로 반환되어 ‘도구를 사용할 수 없습니다. 입력과 요청키는 보존됩니다.’ 안내와 원문보존을 확인했다. 잠금release marker를 만들고 process68132의 정상 exit0/rollback·close를 확인한 뒤 기존 CSV 요청을 재시도해 추가1/중복0으로 성공했다. 증거 `toolkit-csv-503-preserved.png`. 제품·실제관리DB·키·원본운영은 변경하지 않았다. 앞선503 최신브라우저 미확인 항목을 이 수락으로 대체한다.

## 현재 남은 필수 범위

[로컬 도구 활성화 설계](../superpowers/specs/2026-10-31-local-toolkit-activation-design.md)는 제안 상태이며 승인 전이다. 기동 설정 변경으로 실제 사용을 활성화했다고 표시하지 않는다. SNS 계정별 실제 인증/권한·성과 수집·제작/독립 검토·예약/공개/본문 검증·23경로 전환·건축시공을 포함한 기술사 daily/friend/PDF·보호된 외부 Mac/휴대폰 접속·폴더 및 스케줄 물리 이행은 6B~D 필수 후속이다.
