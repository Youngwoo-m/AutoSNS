# SNS OAuth 연결 화면 통합 설계

2026-10-31 · 설계 승인 대기. 구현·실제 UI·실계정 연결·운영 수락을 완료했다는 문서가 아니다.

## 목적과 선택

- 사용자가 선택한 **OAuth 연결 화면부터 통합 개발**한다. 앱 등록 점검만 먼저 만드는 작업으로 축소하지 않는다.
- 대안 A는 등록·자격 점검을 먼저 끝낸 뒤 화면을 만드는 방식이다. 미확인을 줄이지만 사용자가 직접 연결하는 흐름의 통합 개발을 늦추므로 채택하지 않는다.
- 대안 B인 OAuth first를 선택한다. 화면·서버 계약·공식 provider adapter·격리 검증을 함께 만들고 등록 점검은 서버의 필수 배경 gate로 둔다.
- 기존 9개 메뉴와 기술사 메뉴를 유지한다. `채널·계정` 안에 OAuth drawer를 추가하며 도구 사용 선호와 실제 인증을 구별한다.
- 범위는 연결 수명주기다. OAuth 성공은 읽기 성공, 발행 승인, 실행 활성화, 추가 결제·크레딧 소비 허용을 뜻하지 않는다.

## 근거와 기존 연결점

- [Meta 조사](../../audits/2026-10-31-meta-connection-research.md), [기타 SNS 조사](../../audits/2026-10-31-other-sns-connection-research.md), [기존 진입점](../../audits/2026-10-31-remaining-channel-entrypoints.md)을 provider·scope·부수효과 경계의 입력으로 사용한다.
- [외부 접속 경계](../../audits/2026-10-31-external-access-boundary.md), [전체 목표 증거 지도](../../audits/2026-10-31-goal-evidence-matrix.md)의 미완 사항을 유지한다.
- `common/operations/registry.py`의 account/credential/profile 소유 검증과 불변 connection target을 재사용한다. 개인 원본→학과 게시 대상은 다른 축이다.
- `common/operations/integration_store.py`는 사용 선호 전용이다. `enabled_preference`, target_label, 메모를 인증·권한 증거로 승격하지 않는다.
- 기존 `Connection`은 `common/operations/models.py:69`의 frozen 모델이며 `to_dict(public=True)`는 credential/profile 참조를 숨기고 execution_enabled=False를 반환한다. target_id 존재 기반 target_status를 실주체 검증 증거와 혼동하지 않는다.
- `ax-console/app/web/api.js` → `ax-console/app/web_deliveries.py:13` → `common/operations/ledger.py:56`의 공개 목록 경로를 확장한다. 원격 target ID 확인은 별도 인증된 최소 projection으로 제공하며 비밀 참조는 공개하지 않는다.
- `common/publishers/legacy_bridge.py:39`의 resolver는 registry/catalog credential 참조의 account/platform을 확인한다. 신규 backend도 같은 소유 검증 뒤 서버에서만 해석하고 기존 plaintext resolver를 확장하지 않는다. 코드 원본 루트와 운영 workspace/등록부 root의 분리를 유지하며 브라우저 입력으로 경로·자격 resolver를 선택하지 않는다.

## 사용자 흐름과 표시

1. 개인/학과와 플랫폼을 먼저 선택한다. `all`은 조회 필터일 뿐 연결 시작 대상으로 받지 않는다. 기존 연결 선택 또는 신규 연결 제안을 구별한다.
2. 공식 방식, 지원 대상, 읽기/발행 capability, 요청 scope, 앱 심사, 알려진 비용과 미확인 비용, 준비 차단 사유를 보여준다.
3. 서버의 로컬 등록 점검이 준비되면 `공식 서비스에서 동의`를 누른다. scope 설명과 비용 0 증거 범위를 확인한 명시 POST만 연결 시도를 만든다.
4. 공식 서비스의 사용자 동의 후 callback은 code를 임시 보관하고 고정된 깨끗한 화면으로 돌아온다. 같은 사이트의 `연결 계속` POST로 원래 인증 세션을 확인한 뒤에만 token을 교환한다. 사용자가 거부하거나 창을 닫으면 취소/만료로 표시하며 기존 연결을 보존한다.
5. 허용된 별도 principal 조회로 실제 로그인 주체와 게시 대상 ID를 표시한다. 표시명만으로 계정 일치를 증명하지 않는다. 유료·크레딧 소비·비용 미확인 조회는 실행하지 않는다.
6. 기존 불변 target과 같음을 확인하거나 신규 target proposal을 확인한다. 다른 원격 계정이면 충돌을 표시하고 자동 교체하지 않는다.
7. 연결 결과에 동의된 scope·만료·재동의 필요·읽기 검증·발행 지원·실행 비활성을 각각 표시한다. 발행을 시작하는 버튼은 이 흐름에 없다.

- 상태는 `registration_blocked → consent_pending → callback_staged → resume_pending → token_exchanged → principal_pending → target_confirmation → connected`와 `denied/expired/error/revoked`를 사용한다.
- 별도 축으로 `read_status`, `publish_capability`, `execution_enabled=false`, `cost_gate`, `policy_gate`, `credential_health`를 유지한다. 토큰 존재만으로 connected를 확정하지 않는다.
- 준비되지 않음 화면은 필요한 입력을 구체적으로 보여준다. 앱 ID/secret/등록 redirect URI/OS 저장 승인을 임의로 채우거나 존재한다고 추정하지 않는다.
- 401은 재로그인 안내, 409는 선택·확인 내용을 보존한 재검증, 저장 장애는 기존 연결 유지로 처리한다. 계정 전환 시 이전 비동기 응답은 generation 검사로 버린다.
- drawer는 focus 진입·닫기 복귀, Escape, 키보드 순서, aria-live 오류, 320px 화면을 지원한다. 목업·스크린샷은 실제 작동 UI 증거로 표기하지 않는다.

## 컴포넌트와 저장 책임

- 신규 `oauth_connections` UI/controller/API 모듈은 drawer·상태 표시·동의 시작·결과 확인을 맡고 기존 도구 선호 편집기를 대체하지 않는다.
- 서버 `OAuthConnectionService`는 등록 gate·시도·callback·대상 제안·명시 refresh/revoke를 조정한다. provider별 adapter는 공식 authorize/token/principal/refresh/revoke 계약만 구현한다.
- provider catalog에는 login 방식·공식 endpoint/버전·scope 묶음·PKCE 확인 여부·redirect 조건·비용/정책 gate·증거 확인일을 둔다. 임의 endpoint나 legacy wrapper를 fallback으로 실행하지 않는다.
- `OAuthAttemptStore`는 시도 ID, 세션 결속, account/platform/login 방식, connection/registry revision, 요청 scope, state hash, 만료, 소비 여부를 보관한다. verifier는 비밀 저장 경계를 따른다.
- `ManagedConnectionStore`는 운영 workspace의 SQLite에 비밀 없는 principal/target 증거·scope·기한·상태·비공개 credential reference·원본 registry revision·connection revision·active generation을 저장한다. IntegrationStore 및 Keychain과 분리하고 원본 registry JSON에는 쓰지 않는다.
- `project_registry(base_registry, managed_snapshot)`은 base `Connection`을 변경하지 않고 승인된 overlay로 서버 전용 Registry를 조립한다. credential catalog도 같은 snapshot의 account/provider/platform 소유 검증을 통과한 참조만 합성한다. 원본 revision이 다르면 overlay 적용·resolver 호출을 차단한다.
- `ManagedConnectionStore.confirm_target(proposal, expected_base_revision, expected_connection_revision)`이 단일 SQLite transaction의 쓰기 주체다. 확인된 target과 credential reference를 CAS 적용하며 null target 신규 연결도 같은 절차를 따른다. 새 공개 projection에는 credential reference를 숨기고 인증 증거 상태만 추가한다.
- 권장 `CredentialBackend`는 서버 전용 macOS Keychain이며 시험은 in-memory backend를 주입한다. 브라우저/localStorage/IntegrationStore/기존 평문 `secret_env` 확장에 secret·access/refresh token을 저장하지 않는다.
- Keychain 접근 권한·실행 사용자·OS 승인·배포 후 접근성은 필수 입력과 수락 항목이다. 무인 접근이 승인됐다고 가정하지 않고 잠김/거부를 차단 상태로 반환한다.

## 서버 API와 보안 계약

- `GET /connections`, `/oauth/catalog`, `/oauth/attempts/{id}`는 인증된 로컬 snapshot만 반환한다. **일반 GET의 외부 호출은 0**이며 refresh/principal 조회를 숨기지 않는다.
- `POST /oauth/attempts`는 CSRF 토큰·정확한 Origin·현재 세션·account/platform·예상 revision·scope/cost gate를 검증한 뒤 짧은 수명의 공식 authorize URL을 반환한다.
- state는 고엔트로피 서버 발급값이며 저장은 hash로 한다. 시도는 **10분·일회용**, 현재 로그인 세션과 account/provider/connection에 결속한다. 사용자 입력 state·account를 신뢰하지 않는다.
- `receive_callback(provider, parameters)`는 등록된 HTTPS `/oauth/callback/{provider}`만 처리한다. 정확한 Host와 신뢰 proxy/TLS 경계는 6D에서 고정하며 이 경로의 GET만 cross-site 탐색을 허용한다. 일반 GET/POST의 Host·Origin·Sec-Fetch-Site 검사는 전역 완화하지 않는다.
- callback은 code+state 또는 error+state만 허용하고 catalog에서 검증한 응답 형식 외 파라미터·중복값·본문을 거부한다. state hash·provider·10분 만료·미소비를 검사해 원자적으로 수신권을 소비한다. 세션 쿠키 없는 수신은 인증 성공이나 token 교환을 뜻하지 않는다.
- `stage_callback(attempt, code)`는 code와 고엔트로피 일회 callback ticket을 서버 전용 Keychain 임시 namespace에 저장한다. ticket 수명은 2분과 시도 잔여시간 중 짧은 값이다. DB에는 비밀 없는 참조와 상태만 남긴다. 즉시 query 없는 고정 same-origin `/connections/oauth-result`로 303 이동하며 code/state/ticket 원문을 HTML·URL·응답·로그로 재전달하지 않는다.
- 결과 화면은 인증된 서버 snapshot에서 현재 세션 소유 시도만 조회한다. `POST /oauth/attempts/{id}/continue`의 `resume_exchange`는 CSRF·기존 세션/actor·flow/account/provider/state binding·ticket/code 유효성을 검증하고 단 한 번 소비해 token 교환한다. 내부키 인증은 사용자 세션/동의를 대체하지 못한다.
- Strict 쿠키는 유지한다. 보류 code 부재·Keychain 실패·expiry·세션/actor 불일치는 외부 전송 없이 폐기/차단하고 재인증 및 새 flow로 안내한다. 외부 callback 자체에서 세션 미확인을 우회해 교환하지 않는다. `callback_staged`는 OAuth 완료가 아니다.
- redirect URI는 catalog·앱 등록값·시도·token 교환 모두 정확히 일치해야 한다. 임의 return URL, 요청 Host/Forwarded 헤더로 URI를 만들지 않는다.
- PKCE는 provider 공식 지원을 확인한 방식에만 적용한다. 지원 시 S256 verifier/challenge를 시도에 결속하고 교환 뒤 폐기한다. X OAuth2는 확인됨이며 Meta 각 방식·TikTok은 추가 확인 전 추정하지 않는다.
- 모든 사용자 mutation POST는 동기화 CSRF 검증을 추가한다. callback 수신의 state 일회 검증과 same-origin 재개의 기존 세션 결속을 함께 만족해야 인증을 진행한다.
- `POST /oauth/attempts/{id}/inspect`는 동의 범위와 비용 gate 내 principal 조회만 한다. 업로드/container 생성/댓글/게시/공개전환을 호출하지 않는다.
- `POST /oauth/targets/{proposal}/confirm`은 account/platform/principal/target/credential generation/registry revision을 동결한 제안을 승인한다. null target도 자동 기입하지 않는다.
- target 확정은 명시 확인과 revision CAS가 필요하다. 충돌 시 409로 재확인하며 기존 target 변경은 별도 승인된 새 연결/전환 절차로 보낸다.
- `commit_credentials`는 Keychain 신규 credential generation stage → ManagedConnectionStore SQLite의 원본 registry/connection revision CAS 및 active pointer 전환 → 구세대 정리 순서다. Keychain 실패·CAS 충돌·crash 시 기존 유효 연결을 유지하고 재시작 시 자기 namespace의 비활성 orphan만 정리한다. 교환 부수효과가 불명확하면 자동 재전송 없이 unknown/manual 확인 후 새 flow로 보낸다.
- connected 공개는 Keychain 기록·유효 active reference·principal/target 확인·소유 검증이 모두 끝난 뒤다. target confirm POST는 승인된 overlay 적용만 하며 실행/발행 권한을 부여하지 않는다.
- callback/refresh/revoke는 connection별 직렬화와 generation CAS로 경쟁을 막는다. 중복 callback은 재교환하지 않고, revoke 후 늦은 refresh 응답은 저장하지 않는다.
- `assert_zero_cost(operation, endpoint, evidence_revision)`는 authorize 시작과 token/장기교환/refresh/revoke/principal 등 모든 외부 호출 직전에 서버가 실행한다. endpoint별 비용 0 증거·허용 범위를 시도에 동결하고 현재 증거로 재검증한다. unknown/paid/credit은 외부 전송 0으로 차단한다. 동의는 결제수단 등록·구매·자동충전·보유 크레딧 소비의 허가가 아니다.
- `POST /connections/{id}/refresh`와 `/revoke`는 별도 명시 mutation이다. refresh 반환 자격을 원자 교체하고 실패 시 reauth_required로 둔다. 자동 재동의·유료 재시도는 없다.
- revoke는 먼저 로컬 사용을 차단하고 진행 세대 작업을 무효화한다. provider revoke 지원·실패·원격 해지 미확인을 구별하며 로컬 삭제를 원격 revoke 성공으로 표시하지 않는다.
- 응답 allowlist는 상태·안전한 ID/label·scope·기한·오류코드만 허용한다. secret/token/code/verifier/state 원문은 응답·감사·예외·프록시 로그에서 제거한다. callback 후 query 없는 결과 URL로 이동하고 no-store/no-referrer를 적용한다.

## provider별 정직한 gate

|대상|초기 계약과 차단 조건|
|---|---|
|Instagram|Instagram Login/ Facebook Login을 명시 선택·분리한다. 전문 계정 조건·endpoint별 scope·redirect·PKCE 미확인은 registration_blocked로 유지한다.|
|Threads|독립 앱/connection과 threads 권한을 쓴다. refresh GET도 외부 mutation이다. auto_publish_text를 연결 검사에 사용하지 않는다.|
|Facebook|우선 Pages 대상 설계이며 개인 타임라인 발행을 지원으로 표시하지 않는다. pages scope 후보의 최소 조합·종속권한·tasks는 미확인이다.|
|X|OAuth2 PKCE와 scope 묶음을 검증한다. paid_gate_unverified에서는 principal read도 금지한다. 인증 endpoint도 무료로 추정하지 않는다. OAuth 동의가 credit 소비 승인은 아니다.|
|TikTok|읽기·inbox upload·Direct Post를 분리한다. 내부 utility intended use 적합성 unresolved, app review/audit/creator UX 미완이면 쓰기 차단한다.|
|Tistory|공식 API 종료로 신규 OAuth 연결 unsupported. 웹 세션·정책·axlock은 별도 흐름이며 비공개 API로 우회하지 않는다.|
|Naver/Blogger/YouTube|기존 연결 표시를 유지한다. 기존 자격을 새 공용 client로 자동 이식하지 않고 provider별 공식 계약과 실주체 확인이 필요하다.|

## 검증·배포·후속 수락

- 1단계는 drawer/catalog/store와 가짜 adapter로 전체 흐름을 만든다. HTTP callback fixture는 명시적인 test-only이며 실 provider 성공 경로를 증명하지 않는다. 2단계는 공식 계약이 확인된 provider adapter를 비활성 등록하고 endpoint·scope·오류 mapping을 검증한다.
- 격리 시험은 잘못된/재사용/만료 state, 다른 세션·account, redirect 불일치, PKCE 실패, Strict 쿠키 callback 수신/303/동일 세션 재개·없는 세션 차단·ticket 만료/재사용, callback 경합, target CAS, 원본 registry revision 불일치, Keychain-stage/SQLite-CAS 단계별 crash 복구, endpoint별 비용 미확인 외부 전송0, 저장 장애·회전·revoke 경합, GET 외부호출0, 비밀 누출0을 증명한다.
- UI 시험은 거부·만료·401/409/503·다중 탭·계정 전환·키보드·모바일을 포함한다. 기존 9개 메뉴·도구 선호·registry 소유 검증 회귀를 보존한다.
- 새 단일 client 등록·redirect URI·secret 보유 여부는 미확인이다. 준비안됨을 해소하는 앱 등록/심사/OS 승인은 필수 입력이며 실제 수행은 구체 범위를 보여준 명시 체크포인트다.
- 실제 HTTPS callback 배포는 6D 외부 경계 미완 gate다. 허용 host/신뢰 proxy/HTTPS Origin/Secure 쿠키/callback 예외의 실제 수락 전 실연결은 registration_blocked다. loopback 앱을 인터넷에 직접 노출하지 않는다. provider가 loopback을 허용한다는 근거가 없으면 실연결을 차단하고 안전한 HTTPS 경계 설계·수락을 선행한다.
- 실연결은 provider·개인/학과·scope·target·비용0 여부·저장 위치·해지/복구를 제시한 별도 체크포인트 이후 하나씩 수락한다. 이번 설계 승인이 계정 동의·키 발급·발행 승인은 아니다.
- 이후 SNS 발행 adapter/성과 수집·23 crosspost 경로·기술사 4종 제작/검토·외부 Mac/휴대폰 접속·데이터/키/프로필 물리 이행·스케줄 전환과 실제 rollback을 완료해야 전체 목표를 수락할 수 있다.

## builder check 보완 기록

- [설계 검토](../../audits/2026-10-31-sns-oauth-design-builder-check.md)의 필수 3건을 반영했다. Strict 쿠키를 유지하는 callback 보관/동일 세션 재개, 모든 외부 인증 호출의 비용 0 gate, SQLite overlay와 Keychain 세대 전환·복구 주체를 명시했다. 검토 원문은 변경하지 않았으며 추가 실계정 동작은 수행하지 않았다.
