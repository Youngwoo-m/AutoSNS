# 로컬 SNS 도구 운영 안내

추가 SaaS 결제·유료 API·credit 소비 없이 저장된 근거를 다루는 도구다. 기존 승인 구독과 로컬 운영자원의 총비용이 0이라는 의미는 아니다. vidIQ 포함 150 credit도 사용하지 않는다.

## 현재 연결과 기본값

기존 9개 메뉴를 유지한다. 채널·계정에는 SNS 도구 상태, 콘텐츠 기획에는 저장 근거 조사, 관리 원본 편집기에는 제목·본문 후보와 이미지 검사·고정 썸네일, 성과 패널 옆에는 수동 CSV, 배포 상세와 편집기에는 예약 상태 조회를 조합한다. 기존 성과 패널과 연동 선호 설정 모듈은 수정하지 않는다.

`create_server`의 추가 인자는 kw-only `toolkit_policy=None`, `toolkit_renderer=None`, `toolkit_asset_authorizer=None`다. 기본 ToolkitPolicy는 비활성이고 renderer/authorizer는 미등록이다. 별도 관리 저장소가 없거나 명시적으로 초기화되지 않았다면 tools POST는 503이다. factory·GET·선호 저장은 외부 호출·credential 조회/refresh·subprocess를 수행하지 않는다. 새 도구의 활성화가 실행 서비스나 발행 정책을 활성화하지 않는다.

서버의 기존 ContentStore·MetricsStore·RuntimeStore와 동일 객체 및 현재 metrics 등록부를 사용한다. 비용·provider·target·policy·credential·경로·명령을 HTTP body로 주입할 수 없다. 모든 tools 경로는 기존 인증, Host/Origin, 중복 헤더, query, 중복 JSON key/NaN, 1MiB body 경계를 먼저 지난다. CSV 자체는 256KiB 제한이다.

## 사용 순서

1. 조회 범위를 개인 또는 학과로 선택한다. 도구 상태 확인은 사용자가 누를 때만 조회한다. 기능 제공·설정 등록·실인증·읽기 권한·쓰기 권한은 각각 별도다.
2. 저장된 관리 원본을 열고 실제 등록 연결 ID와 검색어를 입력한 뒤 후보를 미리 본다. 대상 계정·플랫폼 변환문이 없으면 서버가 차단한다. 도구는 검색량·경쟁도·예측 CTR을 생성하지 않는다.
3. 원본이 깨끗하고 같은 content/revision/connection/inputHash에 결속된 후보만 초안에 반영한다. 본문은 명시적으로 선택한 변환문 텍스트를 원문 초안에 반영한다. 이 단계는 저장·검토·발행을 만들지 않는다.
4. 기존 원본 저장 버튼으로 전체 payload와 expected_revision을 전송한다. 다른 쓰기가 선행하면 409이며 입력을 보존한다. 저장하면 새 revision으로 독립 검산·출처 검토를 다시 수행한다. 기존 버전의 검토를 재사용하지 않는다.
5. CSV는 파일 선택 또는 붙여넣기→미리보기→가져오기 순서다. 원문·계정·digest와 request_key가 결속된다. 실패 재시도는 같은 키를 유지하고 원문 변경 시 미리보기를 무효화한다. 관측은 legacy_reported 또는 미배정이며 승인·verified_delivery·실인증으로 승격하지 않는다. 값 0·오류·미지원·미배정은 별도로 표시한다. 동일 receipt 재시도는 운영 원장을 바꾸지 않는다.
6. 썸네일은 `landscape.v1`(1280×720), `portrait.v1`(1080×1920) 고정 템플릿만 받는다. 실제 decoder와 서버 등록 글꼴 검증 및 자산 승인/hash 확인을 통과해야 한다. 미등록 renderer/font 검증 실패는 사용 불가다. PNG는 사용자가 다운로드하며 자동 ingest·원본 저장·검토 통과를 만들지 않는다. 원고 첨부는 기존 첨부 기능으로 새 버전을 만든다.
7. 예약 조회는 저장된 배포 ID의 로컬 상태만 읽는다. unknown은 미확인 상태로 유지한다. 조회가 원격 재조회·예약 등록·queue 전환·재발행을 실행하지 않는다.

## 보호 배포

Task8 manifest는 `.superpowers/sdd/2026-10-31-local-sns-toolkit/web-artifacts/manifest.json`이다. 이 작업 시작 시 actual held6는 당시 HEAD desired6와 같았으며 original_sha256을 새로 기록했다. 옛 6A manifest의 original SHA를 Task8 baseline으로 사용하지 않는다. 신규 toolkit 모듈 3개의 SHA도 고정한다.

실제 `app.js`, `api.js`, `content_editor.js`, `operations_panel.js`, `styles.css`, `index.html`은 작업자가 덮어쓰지 않는다. 임시 webroot 전체 복사본에 원본 SHA와 artifact SHA를 모두 검증한 후 overlay한다. 전체 검증 전 일부 파일을 복사하지 않는다. `tests/integration/test_local_toolkit_acceptance.py`의 overlay가 이 경계를 시험한다. Node helper도 최신 Task8 manifest→6A→actual 순서로 선택하고 SHA를 검증한다. 별도 검토된 기술사 표시 artifact는 부모가 함께 배포한다.

부모는 자기 소유 변경만 확인하고 held 대상은 `git hash-object -w --stdin` 및 `git update-index --cacheinfo`로 index에만 stage한다. held 실제 경로를 `git add`하지 않는다. 실제 배포는 부모가 baseline/artifact SHA를 재확인하고 서버 allowlist·owned 8769/8767의 coordinated restart를 수행하는 별도 단계다. 그 전에는 implemented와 deployed를 구분한다. 8700·실계정·실프로필·원본 source를 QA에서 사용하지 않는다.

## 검증과 남은 수락

집중 검증 명령과 실제 결과는 [Task8 수락 기록](../audits/2026-10-31-local-sns-toolkit-acceptance.md)에 기록한다. 전체 Python/Node 회귀, 독립 리뷰, 브라우저 320/1280 실측·키보드·console/screenshot, 실제 배포는 부모 담당이며 완료 전 통과로 표시하지 않는다. CSS/DOM 단위 검증은 브라우저 실측의 대체 증거가 아니다.

브라우저 QA도 임시 source/W/webroot, fixture 인증, loopback 임시 포트만 사용한다. 로컬 도구를 시험할 때만 명시적으로 ToolkitPolicy(True)를 주입한다. 실발행·외부 계정 호출·모델 호출은 0이다. 기존 axlock·STOP·permit·quota·lease와 개인 subscription_only, 학과 ProviderPolicy는 그대로 적용한다.

6B~6D 운영 목표, 실제 수집·게시·인증 확인, 건축시공 필수 후속은 이 도구 통합으로 완료되지 않는다. unknown 자동 queue·다른 전송기 우회·유료/학교 게이트웨이 fallback도 추가하지 않는다.
