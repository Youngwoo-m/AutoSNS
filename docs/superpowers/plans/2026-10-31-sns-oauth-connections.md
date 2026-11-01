# SNS OAuth 연결 화면 통합 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 9개 메뉴의 채널·계정에서 개인/학과별 OAuth 시작·복귀·대상확인·연결수명주기를 통합하고 공식 provider adapter를 비활성 상태로 검증한다.
**Architecture:** 서버 소유 catalog/cost gate, 별도 OAuth SQLite, Keychain backend와 provider transport를 명시 주입한다. 세션 결속 시도→callback 임시보관→same-origin continue→주체 조회→target CAS를 조합하며 원본 registry와 실행 권한은 바꾸지 않는다.
**Tech Stack:** 기존 Python3.15/unittest/SQLite/ES modules/Node test, 표준 라이브러리 macOS Security.framework binding. 새 패키지·SaaS 설치0.
**Spec:** [승인 설계](../specs/2026-10-31-sns-oauth-connections-design.md), [시안](../../../ax-console/design/oauth-connections-preview.html). 사용자2026-10-31 설계·화면 승인/계획작성 지시. 기존 최대병렬 SDD 방식 유지. 설계 승인과 목표 계속 실행 지시에 따라 원장에 근거를 남기고 가역적인 구현을 진행한다. 실제 외부 행위는 승인 범위에 포함하지 않는다.

## Global Constraints

- 실제 로그인·키 발급/조회·Keychain 읽기/쓰기·OS 권한 부여·플랫폼 앱 등록·과금·발행0. 개발은 fake transport/in-memory vault/임시 저장소로 검증하고 실 provider adapter는 비활성 등록한다.
- 개인/학과 account와 원본 owner/게시 destination을 분리한다. all은 조회만. 기존 9개 메뉴·기술사·23교차경로·원본R/8700·launchd·프로필·STOP·quota 보존.
- ordinary GET 외부 호출0. 유일한 callback GET 예외도 토큰교환0/Keychain 임시보관만이다. token·refresh·revoke·inspect는 명시 사용자 POST·세션·CSRF·비용 gate가 필요하다.
- OAuth attempt10분/일회용, callback ticket2분과 잔여시간의 최소, Strict cookie 유지. credential/code/verifier/state 원문을 DB·응답·URL·로그에 남기지 않는다. authorize URL의 state/PKCE challenge와 사용자용 CSRF 응답은 프로토콜상 필요한 제한 예외이며 access/refresh token은 아니다.
- 비용0 증거 없는 endpoint, paid/credit/unknown은 외부전송0. X·TikTok·Tistory·Naver/Google 제약을 미지원/준비안됨으로 명시한다. 비공개 API/브라우저/다른 provider로 자동우회0.
- main 기본 OAuth 서비스·vault·transport 미주입, runtime 실행 비활성 유지. app secret/redirect/실 HTTPS callback 경계 미확인 시 registration_blocked다.
- IntegrationStore는 선호만 저장한다. OAuth 상태는 W의 신규 oauth.sqlite3(schema1)에 분리하고 기존 operations schema3·metrics schema1 및 원본 registry JSON에 쓰지 않는다.
- 실제 server 적용·자격/권한·외부접속 확대는 별도 구체 체크포인트다. 6B발행/6C실성과·제작·검토/6D외부접속·이행은 필수후속이며 이 계획으로 전체목표를 완료처리하지 않는다.
- 공유코드의 명시 소유권을 지킨다. git add -A/reset/revert 금지, 서버 갱신은 부모만 수행한다. 실제 계정 프로필은 열지 않는다.

## Review Focus

1. callback replay·다른세션·교차계정·동시탭·expired state/ticket이 token교환/target변경을 만들지 않는다(Task2/5/7).
2. Keychain stage/SQLite pointer 전환 사이 crash·refresh/revoke 경합이 이전 유효자격을 잃거나 늦은 응답을 되살리지 않는다(Task2/3/5).
3. 내부키·선호 enabled·동의 성공·원격ID 존재를 사용자 동의/실권한/발행 활성으로 승격하지 않는다(Task1/5/7).
4. 제공자redirect/임의endpoint/버전/PKCE/비용미확인과 숨은refresh를 fail-closed로 막고 비밀을 가린다(Task1/4/7).
5. UI 선택취소·계정전환·늦은응답·401/409/503·새로고침이 다른계정 흐름이나 초안을 덮어쓰지 않는다(Task6/8).

## 파일 소유와 공통 인터페이스

|Task|소유 파일/책임|
|---|---|
|1|신규 common/operations/oauth_models.py, oauth_catalog.py, oauth_policy.py; tests/operations/test_oauth_catalog.py|
|2|신규 common/operations/oauth_store.py, managed_connections.py; tests/operations/test_oauth_store.py, test_managed_connections.py|
|3|신규 common/operations/credential_backend.py, keychain_backend.py; tests/operations/test_credential_backend.py|
|4|신규 common/oauth/providers.py, transport.py, meta.py, google.py, x.py, tiktok.py, naver.py, __init__.py; tests/oauth/test_provider_contracts.py|
|5|신규 common/operations/oauth_service.py; tests/operations/test_oauth_service.py|
|6|신규 ax-console/app/web/oauth_api.js, oauth_controller.js, oauth_panel.js; tests/web_oauth.test.mjs|
|7|신규 ax-console/app/web_oauth.py, oauth_session.py; 수정 web_server.py; tests/test_web_oauth.py|
|8|수정 app.js/api.js/styles.css/index.html 및 drawer 관련 content_editor.js는 필요한 연결부만, tests/helpers/staged_web.mjs의 검증 overlay 우선순위; tests/web_oauth_integration.test.mjs, tests/integration/test_oauth_connections.py; 운영안내/수락 문서|

아래 반환 dict는 JSON-safe지만 credential ref를 담은 private 구조는 public projection에서 제외한다. 시간은 timezone 있는 UTC ISO, clock은 주입한다. 아래 고정 모델과 API 필드를 공유하고 구현 편의상 이름을 임의 변경하지 않는다. 입력 오류는 기존 StoreError/ConflictError와 고정 코드, 비밀 원문 예외전달0.

### 고정 private 모델 필드

- `OperationRule(operation, method, endpoint, contract_status, cost_kind, evidence_revision, checked_at)`: 문자열 필드, endpoint는고정HTTPS또는미지원시None. cost_kind는 no_additional_cost/paid/credits/unknown.
- `ProviderDefinition(id, platform, login_method, operations, read_scopes, publication_scopes, pkce_mode, redirect_policy, policy_reasons)`: operations/scopes/reasons는불변tuple, pkce_mode는s256/unsupported/unconfirmed, 미확인은준비차단.
- `AttemptContext(actor, session_binding, account_id, provider_id, connection_id, base_revision, connection_revision, requested_scopes, redirect_uri, client_ref, client_revision, evidence_revision)`: revision은서버현재값, connection_revision은정수,나머지는고정문자열/tuple. 요청body의동명주장은신뢰하지않는다.
- `TokenBundle(access_token, refresh_token, token_type, expires_at, scopes)`: token은private문자열, refresh/expiry는None허용,repr/JSON공개금지. scope는provider실응답을정규화한tuple.
- `CredentialRef(namespace, account_id, platform, connection_id, generation, kind)`: namespace는autosns.oauth, generation은양의정수, kind는client/code/verifier/ticket/token/state_key 중하나. public projection에서는ref전체제외.
- `OAuthClientRegistration(provider_id,client_id,client_secret_ref,redirect_uri,client_revision,approved_scopes,cost_evidence_revision,expected_project_id)`: 서버가 명시 주입한 등록값만 사용한다. secret값은없고private Keychainref만허용,정수client_revision과None허용project_id를구분한다. 요청/Host/선호설정/Keychain전체탐색으로자동구성0, main미주입이면registration_blocked.
- `CallbackClaim(attempt_id,lease_revision,expires_at,context)`: state원문없는서버전용수신lease이며finalize/fail은동일revision에서한번만허용.
- `OAuthPolicy(live_enabled=False)`: 실제실행허용만제어하며비용증거·provider등록gate를대체하지않는다. fake transport시험에서만명시True주입,production main은None유지.

### Task1: catalog·비용·타입 계약
**Consumes:** 승인 spec와 공식 조사4종, 기존 Connection/Registry/Toolkit 비용 gate 의미. **Produces:** `ProviderDefinition`, `OperationRule`, `AttemptContext`, 비공개 repr의 `TokenBundle`, `CredentialRef`; `provider_catalog() -> tuple[ProviderDefinition,...]`, `assert_zero_cost(operation,endpoint,evidence_revision)`.
- [ ] RED: `test_catalog_separates_instagram_login_flows`, `test_unknown_cost_has_zero_transport_calls`, `test_tistory_unsupported_naver_profile_not_publish`, `test_read_scope_never_grants_execution`을 작성한다. IG2방식/Threads/Pages/X/TikTok/GoogleYT·Blogger/Naver/Tistory를 각각 구별한다.
- [ ] `python3 -m unittest tests.operations.test_oauth_catalog -v`로 신규모듈 부재 RED 확인.
- [ ] catalog는 endpoint/버전/PKCE/redirect/scope/cost/policy 증거 revision을 서버 소유로 고정한다. 공식 확인되지 않은 operation은 contract_blocked, 현재 실비용 증거 미완인 제공자는 전부 외부 실행 불가다. 입력 URL/secret/host로 catalog를 덮어쓰지 않는다.
- [ ] 같은 명령 GREEN/skip0. private model repr/직렬화에서 token·ref가 새지 않음을 단언하고 명시 파일 커밋·독립검토.

### Task2: 시도 저장·연결 overlay·CAS
**Consumes:** Task1 타입, 기존 Registry frozen 모델. **Produces:** `OAuthAttemptStore(root,clock)`, `ManagedConnectionStore(root,clock)`는 동일 oauth.sqlite3를 쓴다. `initialize()`만 schema1 생성. `create_attempt(context,state_hash,expires_at)`, `claim_callback(state_hash,provider)->CallbackClaim`, `finalize_callback(claim,code_ref,ticket_ref,expires_at)`, `fail_callback(claim,reason)`, `claim_resume(attempt_id,session_binding,expected_revision)`, `read_owned(attempt_id,session_binding)`, `list_owned(session_binding)`; `ManagedConnectionStore.snapshot()->ManagedSnapshot(base_revision,connections,credential_refs,generation)`는 단일읽기transaction으로세대일치snapshot을반환; `confirm_target(proposal,expected_base_revision,expected_connection_revision)`; `project_registry(base_registry,managed_snapshot) -> Registry`.
- [ ] RED: sqlite reopen·10분expiry·동시callback claim 한건·stage/finalize실패시state재사용0·타세션0·targetCAS409·base revision불일치·다른계정credential거부·local_disconnect 보존 시험 작성/실행: `python3 -m unittest tests.operations.test_oauth_store tests.operations.test_managed_connections -v`.
- [ ] DB는 state hash/session binding/비밀없는ref·상태·증거·revision만 저장한다. code/verifier/token/ticket 원문 저장0. 연결 generation pointer와 상태/events는 단일transaction CAS, lease/중간상태로 교환 성공 여부 불명을 unknown으로 보존한다.
- [ ] 원본registry는 변경하지 않는다. `project_registry(base_registry,snapshot)`과 `credential_catalog(snapshot)`은 반드시 같은 ManagedSnapshot에서 조립한다. projection은 account/platform/target/ref 소유·base revision 확인 후 새 Registry와 credential catalog를 조립한다. execution_enabled를 올리지 않고 기존 Ledger/ExecutionService에 자동 refresh_registry를 호출하지 않는다. UI 연결조회용 projection과 향후 실행전환을 분리한다.
- [ ] GREEN/skip0, 기존DB bytes/테이블/schema 불변과 읽기전용 생성0 검사, 명시 파일 커밋·독립검토.

### Task3: 비밀 저장소와 세대 전환 경계
**Consumes:** Task1 CredentialRef. **Produces:** `CredentialBackend.put(ref,secret:bytes)`, `get(ref)->bytes`, `delete(ref)`; `MemoryCredentialBackend`, `MacKeychainBackend(bridge)`와 내부 lazy `SecurityFrameworkBridge`. 모두 지정 namespace/account/connection/generation만 다룬다.
- [ ] RED: namespace탈출·중복generation·notfound/locked/denied·비밀repr/error누출·삭제실패·다른계정ref읽기금지 시험: `python3 -m unittest tests.operations.test_credential_backend -v`.
- [ ] 실제 macOS 구현은 표준 ctypes의 Security.framework SecItemAdd/CopyMatching/Delete와 CoreFoundation 참조수명을 좁은 bridge로 감싼다. CLI 인자/환경/평문파일에 secret전달0. [Apple SecItemAdd](https://developer.apple.com/documentation/security/secitemadd(_:_:)), [CopyMatching](https://developer.apple.com/documentation/security/secitemcopymatching(_:_:))의 공식 ABI와 local SDK를 확인하고 비공개 API를 쓰지 않는다.
- [ ] 시험은 fake native bridge로 오류/CF소유권/반환값을 검증하며 실제 Keychain에 접근하지 않는다. native adapter가 구성됐다는 사실을 OS 접근수락으로 표시하지 않는다. main 기본backend None 유지.
- [ ] GREEN/skip0·import시native호출0·명시 파일 커밋·독립검토.

### Task4: 공식 provider adapter·제한 transport
**Consumes:** Task1 catalog, Task3 backend에서 service가 꺼낸 서버전용 자격. **Produces:** `OAuthProvider.authorize(attempt,client_config) -> str`, `exchange(attempt,code,client_secret,verifier=None)->TokenBundle`, `refresh(context,bundle,client_secret)->TokenBundle`, `revoke(context,bundle,client_secret)->dict`, `inspect(context,bundle)->dict`의 표준 결과; `build_providers(catalog,transport)`; `OAuthTransport.request(operation,endpoint,params,credentials)`는 서버 고정 HTTPS endpoint만 받는다.
- [ ] RED: fake transport의 exact method/URL/query/body·PKCE·scope·redirect 일치·오류 sanitization·redirect금지·응답크기제한·비용/contract blocked 외부0을 검사: `python3 -m unittest tests.oauth.test_provider_contracts -v`.
- [ ] 공식 조사에서 확인된 operation만 endpoint/method/버전/필드로 구현한다. 누락 endpoint는 공식 문서로 확인한 계약 fixture를 먼저 추가하며 불가하면 해당 operation을 blocked로 남긴다. IG2방식/Threads/Pages는 별도 adapter 설정, X PKCE, TikTok Display와upload/directpost별capability, Google Web/Desktop구별, Naver profile-only, Tistory unsupported를 유지한다.
- [ ] allowlist HTTPS/TLS검증·timeout·제한응답·redirect거부·고정 오류로 구현한다. retry/fallback0, public정적발견과 token작업을섞지않는다. 업로드/container/댓글/게시endpoint는 adapter에없다. 실제httptransport는미주입, urllib/native호출은mock wire계약만 시험한다.
- [ ] Google project/client 영향 미확인은 원격revoke차단, Naver revoke의 paired-token/200빈응답을구별. GREEN/skip0·명시 파일 커밋·독립검토. 미완 operation은 docs/audits/2026-10-31-oauth-provider-readiness.md에 근거/해소조건으로 추적한다.

### Task5: OAuth 수명주기 조합
**Consumes:** Task1~4. **Produces:** `OAuthConnectionService(registry_supplier,client_registrations,attempt_store,connection_store,backend,providers,policy,clock)`; `catalog`, `start`, `receive_callback`, `resume_exchange`, `inspect`, `confirm_target`, `refresh`, `disconnect_local`, `revoke`, `result_for_session`의 서버전용 메서드. policy 기본 live_enabled=False. registry_supplier는 현재base Registry를반환하는서버Callable이며등록설정은 Task1 OAuthClientRegistration의provider_id별immutable mapping이다. 시작/계속/확인때현재revision을재검증하고Task2동일snapshot projection을사용한다.
- [ ] RED: fake전체흐름/거부/expiry/replay/다른세션·account/Strict-cookie없는callback/token0·resume후1회·Keychain실패·각 commit단계crash·late refresh afterdisconnect·target409 시험: `python3 -m unittest tests.operations.test_oauth_service -v`.
- [ ] state는secrets서버발급/hash저장, attempt10분. callback은 claim_callback으로수신권과lease revision을원자소비한뒤 code+ticket Keychainstage, finalize_callback으로ref를연결한다. stage/finalize실패는fail_callback으로수신권재사용없이종료하고자기namespace orphan만정리한다. DB에는비밀없는ref만저장, ticket은2분/잔여최소. receive 단계 token교환0. resume은현재세션·actor·binding·expiry·CAS claim 후1회교환한다.
- [ ] 자격은새generation Keychainstage→SQLite pointer CAS→구generation정리. 실패시이전유효연결유지, 불명확교환은unknown·자동재송신0. orphan정리는자기namespace의참조안된항목만, 실제정리는명시호출이며GET에숨기지않는다.
- [ ] principal조회는명시inspect/비용0 gate, targetproposal을immutable로동결하고confirm CAS로만적용한다. connected는vault·principal·target·소유검증완료후만. scope읽기성공/connected가execution허용을만들지않음단언.
- [ ] 모든외부작업앞cost재검증/Google revoke광범위영향차단/local해제와원격실패분리. GREEN/skip0·명시 파일 커밋·독립검토.

### Task6: OAuth drawer·계정별 제어
**Consumes:** 아래Task7 HTTP 계약. **Produces:** `createOAuthApi(request)`, `createOAuthController({api,onChange})`, `createOAuthPanel({controller,document,onClose})`; render는HTTP0, controller에`setContext/close/hasUnsavedChanges/isBusy/reloadOwnedResult` 제공.
- [ ] RED: `node --test tests/web_oauth.test.mjs`에9메뉴범위/권한·비용상태/선택취소·계정전환late-response/401409503입력보존/multitab·keyboard/응답에secret없음·미확인 provider차단 시험.
- [ ] 시안6단계를기존채널·계정drawer로구현한다. 시도시scope·비용·차단이유,실주체/target,확인후결과를분리. controllergeneration으로늦은응답무효화,실제callback은고정cleanroute에서owned result조회만한다. 동의거부/창닫음/expired는기존연결보존.
- [ ] localdisconnect와remote revoke를분리,발행버튼0/로그인준비안됨명확표시,기술scope는권한설명과함께. GREEN/skip0·명시 파일 커밋·독립검토. fake auth를진짜connected로표시하지않는다.

### Task7: 사용자 세션·CSRF·HTTP 통합
**Consumes:** Task5/6 계약, 기존Auth.check/cookie와webserver Host/Origin. **Produces:** `require_oauth_session(handler) -> SessionContext(actor,session_binding)`, `mint_csrf/verify_csrf`와 `web_oauth.recognizes/handle` 라우팅. 신규 `create_server(...,oauth_service=None,oauth_callback_policy=None)`만명시주입, main기본미주입.
- [ ] RED: `python3 -m unittest tests.test_web_oauth -v`로401/내부키만403/CSRF누락403·중복query/json400/Origin403·읽기전용503/GET외부0/callback한정crosssite·clean303/no-referrer/no-store/response로그secret0 검사.
- [ ] HTTP는 `/api/v2/oauth/catalog`, `/connections`, `/csrf`, `/result`, `/attempts/{id}` GET과 `/attempts`·`/attempts/{id}/continue`·`/inspect`·`/targets/{proposal}/confirm`·`/connections/{id}/{refresh,disconnect,revoke}` POST. 요청은현재account/예상base+connectionrevision/requestkey 및필요payload만허용; endpoint/clientsecret/임의target·actor주입거부. catalog/result/attempts도cookie세션필수,내부키대체0.
- [ ] sessionbinding은기존검증된cookie의단방향digest,actor=console_user. CSRF는서버프로세스전용난수키로세션과기한에HMAC결속한별도토큰(응답허용),재시작시새요청필요. 기존Auth.check를완화하지않는다. query없는 `/connections/oauth-result` shell이 `/api/v2/oauth/result`로해당세션pending시도목록을조회해다중탭이면사용자직접선택;임의account/attempt노출0.
- [ ] `/oauth/callback/{provider}`만엄격한fixed callback policy에따른GET예외. code/error+state의정확catalog허용필드/중복거부·Host고정·TLS/신뢰proxy조건미충족차단. 일반요청Host/Origin/Sec-Fetch-Site검증전역완화0. fixture만명시test_only HTTP를허용하고production기동에서test_only주입거부.
- [ ] 기존 `/api/v2/connections`는oauth_service가있을때만호환items projection에추가상태를합치며없으면기존동작그대로. factory/GET는신규 DBinitialize·Keychain·secretresolver·외부호출0. 명시관리초기화만OAuthstore.initialize를실행한다.
- [ ] GREEN/skip0·기존web/auth/deliveries회귀·명시 파일 커밋·독립검토.

### HTTP 입력·응답 고정 계약

경로 ID는 서버가 발급한ID만 받는다. 아래POST는 항상 사용자 cookie/CSRF와 `request_key`를 요구하며 unknown field는400이다. 같은키/동일payload는동일결과,같은키/다른payload는409다. query account는all/personal/dept중하나이며start에서는all거부.

|경로|추가 body 필드 또는 GET 결과|
|---|---|
|POST /attempts|account_id,provider_id,connection_id,expected_base_revision,expected_connection_revision,requested_scopes|
|POST /attempts/{id}/continue·inspect|expected_revision|
|POST /targets/{proposal}/confirm|expected_base_revision,expected_connection_revision|
|POST /connections/{id}/refresh·disconnect·revoke|expected_base_revision,expected_connection_revision|
|GET /catalog|items(provider_id/platform/login_method/등록·권한·비용·정책 차단 사유), live_enabled=false|
|GET /connections|items(공개 기존 연결 필드+managed 상태/기한/scope/검증·실행비활성), base_revision|
|GET /csrf|csrf_token,expires_at; 세션별 HMAC 검증용이며 OAuth state/token과 다름|
|GET /result|items(현재세션소유 attempt_id/account_id/provider_id/state/revision/expires_at), 다른세션0|
|GET /attempts/{id}|안전한시도상태/revision/만료/차단사유/실주체·target proposal; credential/code/state 원문0|

Service메서드의사용자요청은 `SessionContext`와 위검증된body를 받는다. catalog/result는각각 `catalog(session,account)`/`result_for_session(session)`; `start(session,body)`, `resume_exchange(session,attempt_id,body)`, `inspect(session,attempt_id,body)`, `confirm_target(session,proposal_id,body)`, `refresh/disconnect_local/revoke(session,connection_id,body)`. Callback만 `receive_callback(provider_id,parameters,callback_context)`로사용자세션없이수신하고아직교환하지않는다. inspect결과는 `provider_subject`, `targets`(각target_id/target_label/관측capabilities), `observed_scopes`, `checked_at`의allowlist이며플랫폼원문응답·토큰을보내지않는다.

### Task8: 기존 앱 통합·격리 수락·배포 기록
**Consumes:** Task1~7. **Produces:** 동작하는9메뉴통합과docs/audits/2026-10-31-oauth-connections-acceptance.md, docs/runbooks/oauth-connections.md.
- [ ] 공유drawer에mode(content/oauth/legacy)를명시하고현재editorActive호환을보존한다. guard·refresh·scope선택·result route를OAuth controller와통합한다. 기존도구선호/원고/기술사/발행패널변경은연결부에한정한다.
- [ ] RED→GREEN: `node --test tests/web_oauth_integration.test.mjs tests/web_oauth.test.mjs tests/web_app_focus.test.mjs tests/test_content_editor.mjs`; `python3 -m unittest tests.integration.test_oauth_connections tests.test_web_oauth -v`. fake provider로screen→attempt→crosssitecallback→continue→inspect→targetconfirm→재기동/revoke경합을실제store/HTTP로실행한다. cookie없음/다른계정/paid/unknown의외부0,기존3DB/원본registry보존을단언한다.
- [ ] 운영서버가참조하는app/api/editor/styles/index는필요시SHA검증별도artifact로보호한다. 제품시험은overlay없으면tracked파일fallback(ignored artifact 강제 의존 및 누락 시 skip 금지)으로실행한다. partialcopy전일괄SHA검증을유지한다.
- [ ] 최종통합뒤각Python/Node전체suite를한번실행하고actual환경skip/실행수/로그를정확기록한다. 기존10/62/33·884/216을새코드성공으로재사용하지않는다. 구체실패/변경이없으면중복실행하지않는다.
- [ ] 부모가임시source/workspace/webroot+fakeauth+fakeprovider로브라우저320/1280·keyboard·401409503·multitab/accountlate-response·취소/revoke종류·screen캡처를확인한다. 실비밀·Keychain·provider호출0.
- [ ] 최종독립검토후owned8769백업/적용/restart를직렬수행한다. mainOAuth는미주입상태로가용성/준비차단만표시하고실계정동의는시작하지않는다. 실제OS자격접근·앱등록·HTTPS콜백/권한·cost0수락은후속별도명시체크포인트다. 8767/8700/R/프로필/스케줄변경0.
- [ ] DB/자산/registry/공개이력보존검증,원복은호환코드·신규oauthDB보존전제의기능비활성.사용자새자료/unknown을과거backup으로지우지않는다. 최종문서에code_ready/deployed/real_oauth_ready/live_publish_ready를분리한다.

## 병렬 실행과 작성자 자체검토

Task1·2·3은고정위계인터페이스아래독립파일로병렬(실제 3개 슬롯). Task4는Task1후,Task6은HTTP계약고정후mock독립,Task5는1~4후,Task7은5/6후,Task8통합·배포는부모직렬이다. 요청된최대병렬방식은유지하되서로다른기능이같은webserver/app을수정하지않는다.

자체검토: spec의callback/세션·비용·Keychain/SQLite·provider제약·UI·원복은각Task로대응했다. DB분리는기존schema3하드코딩을불필요하게변경하지않는계획상구체화다.제공자별미완계약은readiness문서로보존하며없는지원/비용0을발명하지않는다.이 계획은 구현 전 검토 대기 상태다.

작성자 최종 자체검토: backend/UI 접점 대조에서 발견한 동일 ManagedSnapshot projection, 서버 소유 client 등록 입력, callback claim→stage→finalize, staged_web helper 소유권을 반영했다. 각 task의 소비/산출 이름과 HTTP body를 대조했으며 새 구현·실계정 호출은 하지 않았다. 실제 provider별 미확인 operation은 readiness tracker에 남기고 실연결 완료로 표시하지 않는다.

## 구현 중 계약 구체화

서버 재시작·동시성·동일 요청 재시도를 만족하려면 generation 예약/PKCE ref 결속/lifecycle lease와 안전한 public 응답 receipt가 필요하다. 별도 OAuth DB 안에서 이 API를 추가하며 실제 연결·발행 권한을 확장하지 않는다. `CredentialRef.kind=state_key`는 OAuth state 원문 대신 Keychain의 서명 키만 가리킨다. HMAC 입력은 durable receipt ID와 동결 context이며 state는 hash로만 DB 저장한다. authorize URL은 저장하지 않고 유효한 동일 요청에서 재구성한다. 이 구체화와 비용은 구현 원장에 기록한다.

인증 관측 공개 metadata는 observed_scopes/credential_expires_at/read_status/publication_status/credential_status의 strict authorization 구조로 고정한다. 값이 없으면 미확인, 요청 scope로 실제 동의를 합성하지 않는다. 미완 시도는 같은 세션에 결속하고 완료 연결의 수명주기는 새 로그인 후에도 동일 서버 actor의 완료 근거·현재 포인터를 검증해 관리한다. 실제 계정 권한의 자동 확대는 없다.

Task8 시험 의존 소유권 구체화: tests/web_app_focus.test.mjs의 새 guard VM context와 tests/integration/test_local_toolkit_acceptance.py의 product_webroot optional overlay 선택도 갱신한다. 최신 OAuth artifact 우선·배포 후 desired actual 허용·artifact 없는 tracked checkout 재현성을 함께 보존한다. 실제 old/desired fixture의 부분 복사 차단 검증은 제거하지 않는다.
