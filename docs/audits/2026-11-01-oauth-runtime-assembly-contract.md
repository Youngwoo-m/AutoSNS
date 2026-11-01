# OAuth 자격과 기존 publisher의 실행 조립 계약 조사

2026-11-01. 이 문서는 다음 구현의 접합부를 구체화하는 **미구현 기술 계약 제안**이다. 설계·구현·실계정 실행 승인을 기록하지 않는다. [다음 산출물](2026-11-01-sns-next-deliverables.md) 1번과 [자격 경계 감사](2026-11-01-oauth-runtime-credential-boundary.md)를 출발점으로 지정된 조립 코드와 직접 의존 계약만 읽었다. 실제 설정·키·DB·콘텐츠는 읽지 않았고 코드 수정, 시험, native/Keychain, 네트워크/API, 브라우저, 발행, 커밋은 수행하지 않았다. 작성 파일은 이 문서 하나다.

## 실제 단절과 기존 DI가 표현하지 못하는 것

|현재 접합부|확인된 코드 동작|추가로 필요한 계약|
|---|---|---|
|부모 startup|`common/operations/bootstrap_config.py:44`의 `build_execution_service()`는 정적 registry/catalog만 받는다. enabled일 때 `LegacyBridge(service.registry, ...)`를 만든다. 별도 config이면 기본 child와의 불일치로 거절한다(`:71–78`).|OAuth snapshot·서버 소유 실행 등록·typed credential catalog를 하나의 assembly로 공급하는 startup DI. 부모 메모리에만 resolver를 넣는 방식은 불충분하다.|
|부모 갱신|`common/operations/execution_service.py:61`의 `refresh_registry()`는 `base_registry`에 production binding/receipt만 투영하고 store/adapter/bridge의 registry를 교체한다.|기본 registry → 동일 managed snapshot의 OAuth 투영 → production binding/receipt 투영 순서를 명시한다. adapter/bridge의 credential catalog와 assembly identity도 같이 교체한다.|
|자식 startup|`blog_runtime.py:122`, `youtube_runtime.py:108`은 각자 `default_bootstrap_config()` → `load_registry()` → 고정 catalog → `child_store()` → 기본 legacy resolver로 host를 만든다.|고정 launcher 안에서 부모와 같은 **서버 소유 assembly factory**를 호출한다. Python callable을 자식으로 직렬화하거나 stdin/env로 경로를 고르게 하지 않는다.|
|catalog|`managed_connections.py:35`는 문자열 key 아래 `credential_ref: CredentialRef`를 둔다. `legacy_bridge.py:39`는 entry의 `credential_ref`가 connection의 문자열 ref와 같아야 한다.|기호 key와 private backend ref를 별도 typed 필드로 분리한다. 단순 dict key 이름 변경만으로 동적 상태 검증을 대체하지 않는다.|
|resolver|기존 호출은 `resolver(reference, account_id=..., platform=..., scope=...)`다(`legacy_bridge.py:54`).|정확한 context/action/executor/target/세대와 permit 결속을 전달할 실행 전용 interface. `read`/`publication` 문자열만으로 동작별 권한을 판단할 수 없다.|
|실제 서비스|blog/YouTube handler가 `services_factory(connection_id, credentials)`를 호출한다(`blog_runtime.py:82`, `youtube_runtime.py:77`). Google 서비스 factory는 `googleapiclient.discovery.build(..., credentials=...)`를 사용한다.|OAuth `TokenBundle` bytes를 기존 서비스가 소비하는 자격 객체로 변환하는 명시 adapter. resolver가 TokenBundle만 반환하면 실제 접합은 끝나지 않는다.|

현재 `project_registry()`는 connected에도 `enabled=False`, `profile_ref=None`인 새 Connection을 만든다(`managed_connections.py:236`). 기존 host/worker/admission read는 enabled job, 정확한 대상, 등록 profile을 요구한다. 따라서 기존 factory에 OAuth catalog만 추가하거나 enabled 한 항목만 바꾸는 구현은 완성 조건이 아니다. 고정 `BLOG_BINDINGS`/`YOUTUBE_BINDINGS` 밖의 임의 connection ID도 현재 handler/catalog가 지원하지 않는다. 초기 범위는 기존 exact ID에 한정하고 미지원 ID는 준비상태 사유로 남겨야 한다.

## 제안하는 명시 interface

아래 이름과 서명은 구현 가이드이며 현재 존재하는 API가 아니다. legacy 경로는 기존 interface를 유지하고 managed 경로를 분리한다.

```python
build_runtime_assembly(*, config, base_registry, managed_store,
    runtime_registration, action_policies, clock) -> RuntimeAssembly

build_execution_service(..., assembly_supplier=None)
build_child_runtime(platform, *, deployment_registration) -> BridgeHost

bind_runtime_action(*, context, executor_id, action, assembly,
    binding_store, request_identity) -> RuntimeActionBinding

resolver.open_action(*, context, executor_id, action, binding,
    permit=None) -> contextmanager[ResolvedRuntimeCredential]

redeem_bridge(..., runtime_binding_hash=None, clock=None)
```

- `RuntimeAssembly`는 frozen 내부 객체로 `base_registry_revision`, `deployment_revision`, `managed_snapshot_generation`, `registry`, `execution_catalog`, `runtime_credential_catalog`, `action_policy_revision`을 함께 가진다. 생성은 token backend/provider 호출 0이다. snapshot 하나에서 registry와 catalog를 만들고 서로 다른 generation의 결과를 섞지 않는다. 실행 registry의 기존 base revision을 OAuth 전역 generation 문자열로 덮지 않는다.
- `assembly_supplier()`는 신뢰된 서버 startup에만 주입한다. `None`이면 현재 조립/기본 비활성 동작을 유지한다. HTTP 요청, CLI 사용자 options, argv, 환경변수에서 factory/module/root/backend/policy를 선택할 수 없다. 상태 GET가 이 supplier를 통해 token을 열거나 원격 준비상태를 갱신해서도 안 된다.
- `runtime_registration`은 exact connection → executor/module, profile symbol, 기대 target/account/provider, 승인된 action policy revision을 가진 비밀 없는 **서버 소유 입력**이다. OAuth 동의가 profile/managed owner/enabled/publication 허가를 만들어 내지 않는다. 등록을 준비해도 별도 cutover 전 enabled는 false다. profile을 legacy 연결에서 자동 상속하지 않는다.
- `build_child_runtime()`은 등록된 고정 배포 코드에서 같은 조립 함수를 호출한다. child가 independently 읽은 최신 snapshot과 부모의 action binding을 비교한다. 부모 overlay를 stdin으로 신뢰시키거나 오래된 부모 registry를 무조건 재사용하지 않는다. child registry/catalog/store/locks/resolver/services factory가 모두 동일 deployment 등록에서 나와야 한다. `config != default_bootstrap_config()`의 현재 차단을 단순 삭제하지 않는다. 지원하려면 고정 child 배포 등록과 부모 config의 equality/identity 검증을 먼저 정의한다.
- `child_store(registry, config)`의 고정 workspace, schema 확인, source-root `LockPaths`는 유지한다. 새 runtime binding 저장이 필요하면 명시 schema 변경과 초기화 경계를 별도 구현해야 한다. GET/child bootstrap에서 migration을 자동 수행하지 않는다.
- `open_action()`은 handler에 raw bytes가 아닌 기존 서비스용 **비직렬화 자격 객체**를 준다. 객체 수명은 한 action이며 resolver/factory/global cache에 토큰을 보관하지 않는다. context manager가 최신 검증과 OAuth writer guard 보유 범위를 표현한다. guard 없이 단순 `get()`만 하는 callable로 축약하지 않는다.

### typed catalog의 호환 경계

기존 `Connection.credential_ref`는 문자열이다(`models.py:74`). 이 타입을 `CredentialRef` 객체로 바꾸지 않는다. 기존 catalog의 의미도 몰래 바꾸지 않는다.

|제안 entry 타입|필수 내부 필드|허용된 resolver|
|---|---|---|
|`LegacyCredentialEntry`|`kind='legacy'`, `credential_key: str`, `account_id`, `platform`|현재 exact legacy resolver만 호출한다. 기존 문자열 equality/소유 검사를 보존한다.|
|`ManagedCredentialEntry`|`kind='managed_oauth'`, `credential_key: str`, `stored_ref: CredentialRef` 또는 recovery가 정의할 owned ref, `connection_id`, `account_id`, `platform`, `provider_id`, `connection_revision`, `credential_generation`, `target_id`, `authorization_digest`|새 runtime resolver만 호출한다. key를 legacy 토큰 이름으로 번역하지 않는다.|

별도 `RuntimeCredentialCatalog`가 entry union을 소유하고 registry에는 기호 key/소유 metadata만 둔다. 기존 managed catalog의 `credential_ref` 필드를 문자열로 덮어 기존 resolver를 통과시키는 adapter는 금지한다. router는 등록된 typed kind로 분기하며 managed ref의 오류·미등록·backend 부재 시 legacy/profile/타 계정/평문 파일 fallback을 하지 않는다. `stored_ref`/소유 envelope/private token은 공개 DTO, 로그, bridge result, stdin/argv/env에 넣지 않는다. recovery의 owned ref가 도입되면 이 interface의 ref 타입을 그 계약에 맞추며 schema1 `CredentialRef`가 이미 workspace 소유 증명을 제공한다고 간주하지 않는다.

## 동적 binding, generation, permit

현재 `Registry.revision`은 base revision이고 OAuth 변경 시 그대로다. `SubmissionPermit.generation`은 worker `RunLease.generation`이며 OAuth credential generation이 아니다(`runtime_models.py:81–108`). 두 숫자를 같다고 비교하거나 하나로 합치면 안 된다.

결속을 두 층으로 나눈다. `RuntimeCredentialBinding`은 관측한 연결/자격/정책의 불변 증거이고 `RuntimeActionBinding`은 그 digest와 이미 만들어진 context/attempt를 연결한다. 전자의 hash 안에 context hash나 미래 attempt ID를 넣지 않으므로 context hash와 순환하지 않는다. 둘 다 신뢰된 서버가 고정 정책으로 만들고 전용 원장에 저장하는 비밀 없는 내부 실행 증거다. 최소 필드는 다음과 같다.

- workspace/deployment identity, base registry revision, 적용할 action policy 집합의 revision.
- connection ID, destination account, platform/provider, immutable target ID와 기대 provider subject.
- connection revision, credential generation, authorization 관측 digest, 유효기간.
- 위 세 항목은 `RuntimeCredentialBinding`에 속한다. `RuntimeActionBinding`은 그 digest, executor ID와 exact action, context fingerprint, `run_id`, 요청 identity를 가진다. publication이면 `delivery_id`, `attempt_id`, prepared hash와 approval/context hash도 연결한다. worker generation은 별도 필드로 남긴다. inspection 시점에는 미래 permit/attempt를 요구하지 않고 그 read action 자체에만 결속한다. 같은 자격 binding을 사용해도 inspect와 publish의 action binding/허가 판정은 각각 수행한다.

전역 snapshot generation은 일관된 조립/캐시 무효화 진단용이다. 다른 연결 하나의 변경만으로 모든 실행을 재승인시키지 않는다. 실제 허가는 해당 connection revision·credential generation·authorization·target·policy의 정확한 비교로 결정한다. 계정/대상/상태가 같다는 이유로 새 generation을 조용히 수용하지 않는다.

부모가 만든 binding을 child가 찾을 수 있는 작은 비밀 없는 `runtime_binding_id`만 bridge request에 추가하는 방식을 제안한다. 이는 현재 `BridgeHost.execute()`의 exact key set에 **명시 version 분기**가 필요한 protocol 변경이다. ID는 권한이 아니다. child는 고정 runtime store에서 row를 읽고 전체 context/executor/action/parent/permit 결속을 재검증한다. request가 row 내용을 제출하거나 credential key/ref/backend 경로를 선택하지 못한다. 기존 nonce pipe는 제출 permit 전용으로 유지하며 토큰 전달 통로로 확장하지 않는다.

target inspection에서 얻은 자격 세대 증거인 `RuntimeCredentialBinding`의 digest를 `PublicationContext`의 새 versioned `runtime_credential_binding_hash`에 반영한다. 이 필드는 context hash 및 publication approval의 일부여야 한다. legacy는 명시 legacy version/필드 부재로 해석한다. permit은 context hash를 통해 자격 binding에 결속된다. attempt/permit 생성 뒤 submit용 `RuntimeActionBinding`을 만들고, `redeem_bridge(..., runtime_binding_hash=...)`는 **이 action binding hash**를 bridge redemption과 같은 transaction에 기록한다. action binding의 context hash/credential binding hash/permit/prepared hash가 모두 맞아야 한다. permit의 worker generation만 검사하고 OAuth 결속을 저장하지 않는 구현은 부족하다.

관측과 submit 사이에 refresh/revoke/disconnect가 있었다면 이전 binding을 거절하고 새 대상 관측/admission/필요한 publication approval 경계로 돌린다. 이미 승인된 context의 credential generation을 뒤에서 바꾸지 않는다. 검증/복구 lookup은 별도 read action binding을 새로 만들 수 있지만 이전 delivery의 공개 의도·remote ID·원래 발행 binding 기록은 바꾸지 않는다. 새 read binding은 현재 읽기 자격만 증명하며 재발행 허가를 만들지 않는다. `AdmissionReadContext`는 발행 permit이 없으므로 현재 plan version/run/target과 action binding의 별도 fingerprint로 결속한다.

## 실제 요청의 선형화와 기존 잠금 유지

현재 mutation은 credential 준비 후 publication guard를 잡고 permit을 redeem한 다음 handler를 호출한다(`bridge_host.py:82–95`). 이 분리는 유지할 가치가 있지만 token을 읽은 뒤 OAuth writer가 세대를 바꾸는 경합을 지금은 막지 못한다. 다음 범위를 하나의 명시 계약으로 추가해야 한다.

1. 부모는 기존 profile 잠금을 획득한다. worker의 `wait=2400`, 공유 profile canonicalization, 외부 로그인 브라우저 감지, parent PID/start/FD 증거를 유지한다. child는 상속된 profile FD를 검증하며 같은 잠금을 재획득하지 않는다.
2. child는 executor/module/interpreter/cwd, 요청 key, context/job/target, parent lock 증거, STOP, typed entry, action policy·binding을 **backend 접근 전에** 검사한다. generation/lease/권한 거부에서는 backend/provider/handler 0회다.
3. managed `open_action()`은 recovery 계획의 **동일 OAuth workspace writer guard**를 획득하고 최신 row를 다시 읽는다. connected, lease 없음, active authorization, exact owner/provider/target/ref/generation, action별 관측 scope·기한을 검증한다. 전용 read transaction을 닫은 뒤 scoped backend exact `get()`을 수행한다. backend envelope/ref와 TokenBundle의 scope/기한도 검사한다. native 중 SQLite transaction과 publication guard를 보유하지 않는다.
4. 자격 준비 후 OAuth guard를 유지한 상태에서 짧은 기존 publication guard를 잡는다. STOP/parent FD/fresh worker lease/시간/publication approval을 다시 확인하고 bound bridge redemption을 commit한다. 이 commit이 **이 세대로 이 한 요청을 시작할 권한**의 선형화 지점이다. OAuth writer는 이 시점까지 세대를 바꾸지 못한다. 이후 publication guard와 OAuth guard를 모두 해제하고 한 handler를 호출한다.
5. redemption 이후의 revoke/STOP/refresh는 이미 허가된 요청의 취소 성공을 뜻하지 않는다. 프로세스 종료·응답 유실은 기존 consumed permit/request_started/unknown 원장에 남긴다. 새 세대 토큰을 읽어 자동 재전송하거나 permit을 다시 만들지 않는다.

읽기 action에는 publication permit을 만들지 않는다. 동일 OAuth guard 아래 최신 검증·exact backend read와 비밀 없는 read-start binding 기록까지 수행하고 이를 read action 시작 권한의 선형화로 삼는다. guard 해제 후 한 handler를 호출한다. 이후 동시 revoke가 원격 조회의 취소 성공을 보장하지 않는 의미를 동일하게 적용한다. 이 기록은 자동 cleanup/refresh를 유발하지 않는다.

추가 잠금 순서는 **부모 profile → child OAuth workspace guard → 짧은 publication guard → 짧은 runtime DB transaction**으로 고정한다. native/provider 작업 동안 publication guard/DB transaction은 열어두지 않는다. OAuth writer/recovery는 workspace guard → OAuth DB의 기존 순서를 유지하고 profile/publication guard를 역순으로 요구하지 않아야 한다. crash recovery 계획의 “workspace guard가 가장 바깥”은 OAuth 하위 작업 기준으로 해석해야 하며, 현재 profile-first 실행과의 이 순서를 후속 설계에서 명시 대조해야 한다. 교착이 없는 전역 순서가 확정되지 않으면 구현 완료로 볼 수 없다. 대기 실패는 busy/blocked로 끝내고 lease나 다른 잠금을 강제로 해제하지 않는다.

## 서비스 adapter와 권한의 남은 경계

`OAuthConnectionService._token_bytes()`가 저장하는 형식은 `access_token/refresh_token/token_type/expires_at/scopes`인 TokenBundle 형식이다(`oauth_service.py:45`). 기존 Google resolver의 `Credentials.from_authorized_user_info()` 경로는 다른 legacy 형식과 secret_env key를 전제한다. 새 adapter는 scoped backend가 반환한 bundle을 decode/검증하고 **현재 access token만 사용하는 서비스 자격**을 만든다. runtime은 refresh token/client secret을 사용하거나 `credential.refresh()`/`secret_env.update()`를 호출하지 않는다. 저장 refresh token을 Google 자격 객체에 그대로 넣어 library의 요청 중 자동 refresh가 가능해지는 구현도 피해야 한다. 이 동작은 가짜 transport에서 만료/401을 주어 refresh 0회로 검증해야 한다.

services factory 호출과 discovery build가 항상 외부 I/O 0이라고 추정하지 않는다. provider/라이브러리 버전에 따른 실제 build 동작을 후속 구현에서 검증하고 고정 discovery 또는 통제 transport를 사용한다. guard를 통과하기 전 서비스 생성/요청을 하지 않는다. scope와 비용 정책은 `inspect_target`, `lookup`, `verify`, `publish` 별 서버 등록으로 구분하며 기존 OAuth authorize/exchange 비용 근거를 publisher API 호출 근거로 재사용하지 않는다.

현재 `validate_authorization()`의 publication 상태는 `not_checked|blocked`뿐이고 `_authorization()`은 항상 blocked다(`oauth_models.py:240`, `oauth_service.py:177`). read verified나 필요한 scope가 있다는 사실만으로 publication allowed를 합성할 수 없다. 첫 조립의 준비상태는 계속 publication blocked여야 한다. 미래 publication 허용 증거는 별도 action policy/cutover 계약과 수락이 필요하며, 이를 도입하려면 현재 blocked의 의미/저장 schema/공개 DTO와의 우선순위도 명시해야 한다. 이 조사로 해당 결정을 승인하지 않는다.

Naver OAuth profile 동의를 BrowserBlogServices의 블로그 쓰기 자격으로 변환하지 않는다. Tistory 브라우저도 별도 profile 경로를 유지한다. OAuth token adapter의 초기 실제 접합 대상은 기존 Blogger/YouTube 서비스이며 두 브라우저 플랫폼을 OAuth 완료로 표시하지 않는다.

## 후속 집중 검증의 관찰 조건

이 조사에서는 시험을 실행하지 않았다. 구현 후 필요한 검증은 아래의 실제 연결 증거이며 fake 자체를 추가하는 것이 완료 조건은 아니다.

|검증|필수 관찰|
|---|---|
|부모/고정 child 동등 조립|동일 등록·snapshot에서 동일 assembly/binding을 얻는다. child가 base registry나 기본 legacy resolver로 회귀하면 exact managed 요청을 거절한다. 다른 root/deployment/owner도 거절한다.|
|typed catalog/실서비스 접합|정상 managed entry 한 개가 scoped backend exact get → bundle adapter → 기존 services factory/handler에 한 번 도달한다. key 혼동·ref mismatch·임의 connection ID·OAuth 실패 시 legacy get은 0회다.|
|사전 거부|lease/unknown/non-active/authorization None/만료/누락 scope/target-provider-account 불일치/오래된 binding은 backend·provider·handler 0회다. raw row/ref/lease는 보존한다.|
|경합|writer를 token read 전후와 redemption 전후에서 정지시킨 thread/process 시험으로 채택 generation과 기록된 request-start binding이 일치함을 확인한다. 단순 snapshot 두 번 읽기는 경합 증명이 아니다.|
|기존 실행 통제|profile 공유 alias/FD/부모 identity, STOP, approval 철회, worker heartbeat, permit 만료·재사용, prepared hash와 원고 revision 변경은 기존 거부를 유지한다. OAuth guard 대기 때문에 profile/STOP 통제가 우회되지 않는다.|
|숨은 mutation 0|constructor/GET/기본 bootstrap/dry/shadow는 backend/provider/native 0회. 만료/401은 refresh/write 0회이며 명시 OAuth 수명주기 필요 사유를 반환한다. redemption 뒤 실패는 새 token으로 재전송하지 않는다.|
|버전·기본값|기존 legacy bridge request/context/permit은 명시 호환 version으로 동작한다. 새 managed protocol은 binding 필수다. 주입 없음·초기 등록은 enabled false/owner 유지이며 비밀 없는 준비상태만 제공한다.|

crash recovery의 scoped 소유 증명·공용 guard 수락이 이 경계의 선행조건이다. provider 앱 등록/실 HTTPS/정책·비용0/실 Keychain/실계정 읽기/별도 공개 수락은 이 조립 문서 또는 키 없는 집중 시험으로 충족되지 않는다. 기존 9개 메뉴·23개 교차 규칙, legacy launchd, quota/원장, 운영 원본 및 실행 owner는 이 계약 조사에서 변경하지 않았다.
