# 로컬 SNS 도구 운영 안내

추가 SaaS 결제·유료 API·credit 소비 없이 저장된 근거를 다루는 도구다. 기존 승인 구독과 로컬 운영자원의 총비용이 0이라는 의미는 아니다. vidIQ 포함 150 credit도 사용하지 않는다.

## 현재 상태

로컬 도구 코드와 화면은 8769/8767에 보호 배포됐다. 전체 Python884(87.391s, skip0)·Node216 시험, 독립 검토, 격리 브라우저의 320/1280·401/409/503 입력 보존/복구를 확인했다. **현재 main의 로컬 정책은 비활성**이고 renderer/authorizer·실행 서비스도 미주입이다. 화면에 기능이 보이는 것과 실제 사용 가능/실인증/발행 가능은 다르다. [활성화 설계](../superpowers/specs/2026-10-31-local-toolkit-activation-design.md)는 승인 대기다.

## 현재 연결과 기본값

기존 9개 메뉴를 유지한다. 채널·계정에는 SNS 도구 상태, 콘텐츠 기획에는 저장 근거 조사, 관리 원본 편집기에는 제목·태그 후보와 이미지 검사·고정 썸네일, 성과 패널 옆에는 수동 CSV, 배포 상세와 편집기에는 예약 상태 조회를 조합한다. 기존 성과 패널과 연동 선호 설정 모듈은 수정하지 않는다.

`create_server`의 추가 인자는 kw-only `toolkit_policy=None`, `toolkit_renderer=None`, `toolkit_asset_authorizer=None`다. 기본 ToolkitPolicy는 비활성이고 renderer/authorizer는 미등록이다. 별도 관리 저장소가 없거나 명시적으로 초기화되지 않았다면 tools POST는 503이다. factory·GET·선호 저장은 외부 호출·credential 조회/refresh·subprocess를 수행하지 않는다. 새 도구의 활성화가 실행 서비스나 발행 정책을 활성화하지 않는다.

서버의 기존 ContentStore·MetricsStore·RuntimeStore와 동일 객체 및 현재 metrics 등록부를 사용한다. 비용·provider·target·policy·credential·경로·명령을 HTTP body로 주입할 수 없다. 모든 tools 경로는 기존 인증, Host/Origin, 중복 헤더, query, 중복 JSON key/NaN, 1MiB body 경계를 먼저 지난다. CSV 자체는 256KiB 제한이다.

## 명시적으로 활성화한 환경의 사용 순서

1. 조회 범위를 개인 또는 학과로 선택한다. 도구 상태 확인은 사용자가 누를 때만 조회한다. 기능 제공·설정 등록·실인증·읽기 권한·쓰기 권한은 각각 별도다.
2. 저장된 관리 원본을 열고 등록된 계정·플랫폼·대상 목록에서 연결을 선택하고 검색어를 입력한 뒤 후보를 미리 본다. 대상 계정·플랫폼 변환문이 없으면 서버가 차단한다. 도구는 검색량·경쟁도·예측 CTR을 생성하지 않는다.
3. 원본이 깨끗하고 같은 content/revision/connection/inputHash에 결속된 후보만 초안에 반영한다. 후보의 태그는 명시적으로 선택한 대상 계정·플랫폼 변환문 초안 끝에만 붙인다. 원문과 다른 변환문·출처는 보존한다. 이 단계는 저장·검토·발행을 만들지 않는다.
4. 기존 원본 저장 버튼으로 전체 payload와 expected_revision을 전송한다. 다른 쓰기가 선행하면 409이며 입력을 보존한다. 저장하면 새 revision으로 독립 검산·출처 검토를 다시 수행한다. 기존 버전의 검토를 재사용하지 않는다.
5. CSV는 파일 선택 또는 붙여넣기→미리보기→가져오기 순서다. 원문·계정·digest와 request_key가 결속된다. 실패 재시도는 같은 키를 유지하고 원문 변경 시 미리보기를 무효화한다. 관측은 legacy_reported 또는 미배정이며 승인·verified_delivery·실인증으로 승격하지 않는다. 값 0·오류·미지원·미배정은 별도로 표시한다. 동일 receipt 재시도는 운영 원장을 바꾸지 않는다.
6. 썸네일은 `landscape.v1`(1280×720), `portrait.v1`(1080×1920) 고정 템플릿만 받는다. 실제 decoder와 서버 등록 글꼴 검증 및 자산 승인/hash 확인을 통과해야 한다. 미등록 renderer/font 검증 실패는 사용 불가다. PNG는 사용자가 다운로드하며 자동 ingest·원본 저장·검토 통과를 만들지 않는다. 원고 첨부는 기존 첨부 기능으로 새 버전을 만든다.
7. 예약 조회는 저장된 배포 ID의 로컬 상태만 읽는다. unknown은 미확인 상태로 유지한다. 조회가 원격 재조회·예약 등록·queue 전환·재발행을 실행하지 않는다.

## 보호 배포와 현재 반영 상태

Task8 manifest는 `.superpowers/sdd/2026-10-31-local-sns-toolkit/web-artifacts/manifest.json`이다. 이 작업 시작 시 actual held6는 당시 HEAD desired6와 같았으며 original_sha256을 새로 기록했다. 옛 6A manifest의 original SHA를 Task8 baseline으로 사용하지 않는다. 신규 toolkit 모듈 3개의 SHA도 고정한다.

초기 구현 중 held 파일인 실제 `app.js`, `api.js`, `content_editor.js`, `operations_panel.js`, `styles.css`, `index.html`은 구현 작업자가 덮어쓰지 않고 desired artifact로 보존했다. 임시 webroot 전체 복사본에 원본 SHA와 artifact SHA를 모두 검증한 후 overlay한다. 전체 검증 전 일부 파일을 복사하지 않는다. `tests/integration/test_local_toolkit_acceptance.py`의 overlay가 이 경계를 시험한다. Node helper도 최신 Task8 manifest→6A→actual 순서로 선택하고 SHA를 검증한다. 별도 검토된 기술사 표시 artifact도 부모가 함께 배포했다.

초기 구현 커밋에서 부모는 자기 소유 변경만 확인하고 held 대상은 `git hash-object -w --stdin` 및 `git update-index --cacheinfo`로 index에만 stage했다. held 실제 경로를 `git add`하지 않았다. 부모는 baseline/artifact SHA 선검증, 전체 관리 workspace·화면 백업 후 owned 8769/8767의 coordinated restart를 완료했다. 현재 actual 정적 파일은 desired와 같다. 백업은 `ax-console/data/deployment-backups/toolkit-20261031T020602792714Z/`이며 두 DB integrity와 백업 대비 논리내용 동일을 확인했다. 이 화면 배포는 toolkit 활성화가 아니다. 8700·실계정·실프로필·원본 source를 QA에서 사용하지 않는다.

## 검증과 남은 수락

집중/전체 검증, 독립 검토, 브라우저 320/1280 실측·키보드·화면 증거 및 실제 화면 배포 결과는 [수락 기록](../audits/2026-10-31-local-sns-toolkit-acceptance.md)에 기록했다. CSS/DOM 시험과 실제 브라우저 수락을 구분하며 console 전체 무오류 판정까지 확대하지 않는다. 실제 작업 사용 활성화와 아래 운영 후속은 미완료다.

브라우저 QA도 임시 source/W/webroot, fixture 인증, loopback 임시 포트만 사용한다. 로컬 도구를 시험할 때만 명시적으로 ToolkitPolicy(True)를 주입한다. 실발행·외부 계정 호출·모델 호출은 0이다. 기존 axlock·STOP·permit·quota·lease와 개인 subscription_only, 학과 ProviderPolicy는 그대로 적용한다.

6B~6D 운영 목표, 실제 수집·게시·인증 확인, 건축시공 필수 후속은 이 도구 통합으로 완료되지 않는다. unknown 자동 queue·다른 전송기 우회·유료/학교 게이트웨이 fallback도 추가하지 않는다.
