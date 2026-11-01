# OAuth 관리 자격과 향후 실행 resolver 경계 감사

2026-11-01. 범위: 코드 읽기, 순수 가짜 참조 재현, 기존 선택 시험 4개, 부모 수정의 독립 검토와 추가 회귀 시험 1개. 실제 계정 자격 조회·Keychain/native bridge·provider·브라우저·발행·설정 변경·커밋은 수행하지 않았다. 이 감사 작업자는 이 문서만 작성했다. 같은 작업트리에서 부모 작업자가 반영한 lease 투영 수정과 감사 시작 시점의 코드를 아래에서 구별한다.

## 판정

**향후 실행 전용 경계가 필요하다.** 현재 공개 OAuth 조회의 pending lease 차단만으로는 실행 resolver에 적용할 수 없다. 다만 현재 운영 `main()`에는 OAuth/실행 서비스가 주입되지 않고, managed 투영도 `Connection.enabled=False`이므로 이번 결과는 현재 실제 발행 경로가 열려 있다는 뜻이 아니다.

최소 선행 수정은 `managed_connections.py`에서 pending lease를 실행용 credential catalog와 registry에서 제외하는 것이다. 부모 작업자가 감사 중 이 수정을 반영했고, 마지막 절에 독립 검토 결과를 기록했다. 이것은 현재 투영 불일치를 줄이지만, 미래의 자격 읽기·실행 승인 시점에 최신 행을 다시 검사하고 세대를 결속하는 계약까지 대신하지는 않는다.

## 감사 시작 시점의 실제 경로

|단계|파일/API와 확인한 동작|실행 경계에서의 의미|
|---|---|---|
|lease 생성|`common/operations/managed_connections.py:139`, `claim_connection_operation()`은 revision/generation을 올리고 `operation_lease`를 추가한다. 기존 `state='connected'`와 active 자격 참조는 유지한다.|미완 refresh/revoke는 행의 state만으로 구별할 수 없다. durable 참조 보존 자체는 필요하다.|
|raw snapshot|같은 파일 `snapshot():41–54`는 `state=='connected'`이면 `credential_refs`에 포함한다.|감사 시작 코드에서는 pending lease 행도 실행 후보 목록에 들어갔다.|
|catalog|같은 파일 `credential_catalog():30–37`은 state/소유/namespace/kind/provider-platform을 확인한다.|lease, authorization credential status, 만료, 실행용 권한은 검사하지 않았다.|
|registry overlay|같은 파일 `project_registry():212–228`은 connected 행을 `auth_status='connected'`, 자격 key 포함, `enabled=False`로 투영한다. 원본 Registry의 연결·자격 dict를 복사한다.|pending 행의 raw ref는 비활성 실행 후보로 노출될 수 있었다. `Registry.revision`은 base revision 그대로다.|
|공개 조회|`common/operations/oauth_service.py:226–251`, `connections()`는 위 투영 뒤 pending lease를 `unknown`, authorization unknown/blocked, 실행 false, 수동 확인 사유로 바꾼다.|이 보정은 HTTP용 DTO에만 적용된다. raw snapshot/catalog/registry가 이 DTO를 통과하는 것은 아니다.|
|실행 서비스|`common/operations/execution_service.py:53–69`는 생성 시 받은 `base_registry`에서 production binding/receipt를 투영한다. `refresh_registry()`는 OAuth store를 조회하지 않는다.|OAuth store 변화가 이 서비스와 자식 bridge에 자동 전달되는 연결은 현재 없다. 이곳의 refresh를 OAuth refresh로 오해하면 안 된다.|
|HTTP 실행|`ax-console/app/web_execution.py:231–291`은 서버가 주입한 service/policy를 사용한다. POST는 service 존재와 enabled policy를 검사하며 body가 credential/registry/resolver를 선택하지 못한다.|facade에는 OAuth 자격 상태 검사나 resolver 생성 책임이 없다. GET status는 등록 메타데이터만 사용한다.|
|실제 자격 resolver 앞|`common/publishers/legacy_bridge.py:39–54`, `resolve_registered_credentials()`는 registry와 별도 catalog의 계정/platform/ref를 맞춘 뒤 resolver를 호출한다.|이 함수 자체에는 enabled/auth status/OAuth lease/generation 검사가 없다. 호출자의 기존 실행 gate를 전제로 한 legacy 경계다.|
|bridge 호출 시점|`common/publishers/bridge_host.py:54–99`에서 read는 `_credentials(...,'read')`, mutation은 `_credentials(...,'publication')`을 호출한다. mutation credential 준비는 publication guard·permit redemption 이전이다.|미래 OAuth resolver를 넣을 때 자격 읽기의 허가 경계와 provider 요청 시작의 허가 경계를 모두 명시해야 한다.|

현재 추가 차단도 존재한다. worker는 `common/operations/worker.py:69–78`에서 enabled 정책과 등록 profile lock을 요구하고, bridge `_connection()`은 `legacy_bridge.py:106–117`에서 profile을 요구한다. managed connected 투영은 새 `Connection`을 만들 때 profile을 넣지 않는다. 따라서 enabled만 바꾸어 현재 경로 전체가 실행된다고 단정할 수 없다. 기존 profile 잠금을 제거하거나 OAuth ref에 legacy profile을 자동 상속하는 것이 이번 감사의 해결책은 아니다.

## 현재 운영 상태와 연결되지 않은 형식

`ax-console/app/web_server.py:646–650`의 `create_server()` 기본 OAuth/실행 서비스는 `None`이고, `:694–714`에서 기본 실행 정책은 disabled다. `main():735–745`는 OAuth/실행 service·vault·provider를 인자로 주입하지 않는다. OAuth 연결 완료·refresh 완료도 `managed_connections.py`에서 execution false를 유지한다.

두 credential catalog는 아직 같은 API가 아니다.

- managed `credential_catalog()`의 dict key는 `oauth:<account>:<platform>:<connection>:<generation>` 문자열이고, entry의 `credential_ref` 값은 `CredentialRef` 객체다.
- legacy bridge는 entry의 `credential_ref`가 `connection.credential_ref` 문자열과 같아야 한다. managed catalog를 그대로 넘기면 `credential_owner_mismatch`로 거절한다.
- `common/publishers/blog_runtime.py:43–61`, `youtube_runtime.py:38–56`의 기본 resolver는 고정 `CREDENTIAL_CATALOG`와 기존 exact secret key를 사용한다. 이 코드 본문만 읽었으며 호출하지 않았다. OAuth namespace를 읽는 코드가 아니고, 실제 호출되면 기존 refresh/write가 있을 수 있으므로 OAuth fallback으로 재사용하면 안 된다.
- `build_blog_host():112–119`, `build_youtube_host():97–105`는 resolver/catalog의 명시 DI 지점이다. DI 가능성 자체를 OAuth 연동 완료로 표시하면 안 된다. 자식 bootstrap은 별도로 고정 registry를 읽으므로 부모의 메모리 overlay만 바꿔도 끝나지 않는다.

## unknown과 보존의 구별

1. 행의 `state='unknown'`이면 기존 snapshot은 실행 후보 ref를 만들지 않고, 기존 연결의 registry 투영은 credential/profile을 비운다. `test_inactive_projection_has_no_legacy_fallback_and_preserves_state`가 이 동작을 확인한다.
2. **pending lease + state connected**는 별도 경우다. 공개 DTO만 unknown으로 보정하는 것과 catalog를 차단하는 것은 다른 경계다.
3. **state connected + authorization.credential_status unknown**도 방어할 필요가 있다. 정상 완료 API는 대체로 state와 credential status를 함께 바꾸지만, raw snapshot의 실행 가능성을 state 하나로만 판정할 이유는 없다. unknown뿐 아니라 pending/stored/reauth_required도 실행 자격으로 승인하지 않는 것이 안전하다. 현재 `authorization=None`을 허용하는 저장소/표시 호환 계약과, 미래 실행에서 active 증거가 필요하다는 계약을 분리해야 한다.
4. 차단하더라도 `snapshot.connections`의 원래 credential_ref·credential_generation·operation_lease를 지우면 안 된다. service의 CAS/수동 확인과 recovery 보호 graph가 이 참조를 필요로 한다. 실행 후보 목록에서 제외하는 것과 durable 소유 정보를 삭제하는 것은 별개다.

## 최소 수정과 후속 API 제안

### 지금 가능한 범위

부모 작업자가 반영한 `common/operations/managed_connections.py` 수정은 다음 최소 계약을 다룬다. 감사 시작 코드의 줄 번호와 수정 후 줄 번호는 다르다. 세대 결속 등 미래 계약은 아래 별도 제안이며 이번 diff로 구현됐다고 주장하지 않는다.

- `snapshot().credential_refs`: operation_lease가 있는 row는 제외한다. `snapshot.connections`는 원래 참조와 lease를 그대로 보존한다.
- `credential_catalog(snapshot)`: 호출자가 직접 구성한 snapshot도 방어한다. lease가 있는 row/ref를 실행용 entry로 반환하지 않는다. 기존 연결/ref 소유 검증을 유지한다. 세대 결속은 아래 미래 계약에 남는다.
- `project_registry()`: leased row는 auth unknown, enabled false, credential/profile None으로 투영한다. 영향받지 않은 legacy 연결과 원본 Registry는 바꾸지 않는다. raw row는 건드리지 않는다.
- authorization credential status 필터를 넣는다면 `None` 호환 정책을 명시한다. 최소한 명시 unknown/non-active 값을 active로 승격하지 않는다. 미래 실행이 `None`을 active로 추론해서는 안 된다.

### 미래 실행을 연결하기 전에 필요한 별도 계약

최소한 신규 `common/operations/oauth_runtime.py` 같은 한 곳에 `resolve_runtime_credential(context, expected_binding, *, store, backend, guard, action_policy)`를 두고, `bridge_host.py`의 명시 DI resolver에서 사용하도록 제안한다. 이름은 제안이며 현재 구현된 API가 아니다.

|책임|최소 계약|연결할 파일/API|
|---|---|---|
|최신 상태 확인|자격 읽기 직전 최신 managed row를 읽고 state connected, lease 없음, token kind/namespace/owner/platform/connection/provider 일치, ref generation와 row generation 일치, active authorization과 관측된 유효기간·허용 동작을 검증한다. unknown/누락 증거는 거절한다.|신규 runtime 경계; `ManagedConnectionStore.snapshot()` 또는 단일 read transaction 전용 조회 API|
|세대 결속|base revision만 비교하지 말고 managed connection revision·credential generation·provider/target 결속을 실행 증거에 넣는다. raw ref/token은 HTTP 응답/공개 로그에 싣지 않는다.|`runtime_models.py`의 context/별도 비공개 grant, `publication_gate.py`, `execution_service.py`의 registry 공급 경계|
|경합 의미|refresh/revoke/disconnect가 자격 선택과 요청 승인 사이에 들어갈 때의 선형화 지점을 정한다. recovery 계획의 공용 writer guard와 연동해 최신 검증→해당 실행의 요청 시작 권한 기록까지 보호하거나, 동등한 CAS/lease를 제공한다. 단순 두 번 읽기로 TOCTOU가 해결됐다고 주장하지 않는다.|신규 runtime 경계, 미래 OAuth writer guard, `BridgeHost.execute()`의 credential 준비/permit redemption 경계|
|읽기와 발행 분리|`scope='read'`/`'publication'` 문자열 자체를 허가로 취급하지 않는다. 등록된 action별 정책을 따로 검증하고 현재 publication blocked를 읽기 성공으로 해제하지 않는다.|DI resolver + `BridgeHost._credentials()`의 고정 호출 문맥|
|불확실성|승인 이후 provider 결과 불명확은 기존 runtime unknown으로 보존한다. generation 변경을 이유로 이전 요청 재전송·자동 OAuth refresh/revoke를 하지 않는다.|기존 attempts/receipts/permit 및 worker unknown 처리|
|legacy 분리|OAuth 전용 resolver는 exact managed ref만 읽고, 실패 시 기존 secret_env/profile/다른 계정/평문 token으로 fallback하지 않는다. legacy resolver 기본 동작은 유지한다.|`legacy_bridge.py:resolve_registered_credentials()`의 별도 typed 경로 또는 명시 router; blog/youtube 기본 resolver 유지|

일반 GET/factory/main에는 backend 조회나 이 runtime resolver 호출을 넣지 않는다. 이 후속 계약을 준비한다고 execution enabled, OAuth live policy, client 등록, provider adapter를 활성화할 필요도 없다.

## 의미 있는 검증 사례

현재 확인된 시험과 앞으로 필요한 시험을 구분한다.

**이번 감사에서 실행한 검증:** `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest`로 아래 네 시험을 선택 실행했다. 4개 PASS, skip 0, 0.137초였다. 전체 suite는 실행하지 않았다.

- `tests.operations.test_oauth_service.OAuthServiceTests.test_pending_refresh_lease_is_unknown_read_only_after_reopen`
- `tests.operations.test_oauth_service.OAuthServiceTests.test_pending_revoke_lease_is_unknown_read_only_after_reopen`
- `tests.operations.test_managed_connections.ManagedTests.test_inactive_projection_has_no_legacy_fallback_and_preserves_state`
- `tests.test_web_execution.ExecutionFacadeTests.test_default_disabled_has_no_external_calls`

이 lease 시험들은 재개 후 GET의 vault get/put/delete를 금지하고 DB bytes·lease/ref 보존·provider 호출 목록 불변을 단언한다. 실제 OS/계정 수락 시험은 아니다.

별도의 순수 메모리 fixture로 감사 시작 코드를 재현했다. pending refresh row에 대해 catalog count=1, projection auth connected/enabled false/ref 존재였다. 이 catalog를 legacy bridge에 그대로 주면 owner mismatch였다. catalog의 ref 값을 문자열에 맞춘 **가상 미래 adapter**를 넣고 `resolve_registered_credentials()`만 직접 호출했을 때 fake resolver가 1회 호출됐다. 실제 backend/provider 호출은 0이다. 이것은 resolver 함수에 추가 lease 검사가 없다는 재현이며, worker/bridge 전체 경로의 실행 허가 우회 시험이 아니다.

**최소 수정 수락 시험:** refresh/revoke 각각의 pending row를 재개하여 snapshot 실행 ref 없음, raw row ref/lease 있음, catalog 제외, projected unknown/ref None/profile None을 단언한다. 직접 조작한 snapshot/catalog도 거절하고, DB bytes와 기본 registry/무관 legacy 연결이 그대로인지 확인한다. authorization explicit unknown/non-active/None의 정책을 각각 검증한다.

**미래 runtime 전용 시험:** token backend를 호출 횟수 spy로 두고 pending lease, unknown, stale generation/revision, 만료/누락 authorization, provider/target/계정 불일치, 부족한 action 권한을 각기 거절하여 backend/provider 0회를 확인한다. 정상 active read 1회와 publication blocked 0회도 비교한다. resolver 직전 OAuth writer를 중단점에서 경쟁시키고, 한 요청이 채택한 세대와 요청 시작 기록이 일치하는지 검증한다. 이미 승인된 요청의 실패를 재전송하지 않는지 확인한다. 두 workspace/legacy fallback 및 생성자/GET 접근 0도 포함한다. token을 한번 읽어 캐시한 뒤 OAuth 변경을 무시하는 경로와 자식 bootstrap이 stale base registry를 읽는 경우를 따로 검증한다.

## crash recovery 계획과의 관계 및 불변 조건

`docs/superpowers/plans/2026-11-01-oauth-crash-recovery.md`는 소유 marker/envelope, durable journal, 전체 보호 graph, 명시 cleanup, writer/recovery 잠금을 다룬다. 이 감사의 핵심인 **실행을 위해 어떤 자격을 언제 읽고 어떤 세대로 요청을 승인하는가**는 그 계획의 cleanup 판정과 별도 책임이다. recovery 성공을 runtime 자격 유효성으로 해석하면 안 된다. 공용 guard/owned-ref 모델은 재사용할 수 있지만 runtime consumer 계약은 별도 후속 작업으로 명시해야 한다.

부모의 투영 수정과 미래 runtime 구현 모두 원본 registry, 기존 operations/metrics DB, IntegrationStore, legacy credential/profile/STOP/quota/launchd, 운영 원본 R/8700을 변경하지 않는다. 개발 검증은 fake backend/provider와 임시 W만 사용한다. unknown/lease/ref를 지우거나 자동 lease 해제·기한 기반 재시도·기존 credential 이식·토큰 fallback을 추가하지 않는다. 실제 OAuth/Keychain 수락 및 live publish 준비 여부는 이 감사나 격리 시험으로 충족되지 않는다.

## 부모의 동시 수정 독립 검토 결과

최종 확인한 `managed_connections.py` diff는 `_credential_blocked()`를 공용으로 두어 pending lease 또는 명시 non-active authorization을 snapshot 실행 refs/catalog에서 제외하고 registry 자격/profile을 비운다. `authorization=None`의 기존 호환 동작은 유지한다. base에 없는 신규 managed 연결도 connected+blocked일 때 진단용 unknown 연결로 목록에 남긴다. raw snapshot row의 lease/ref를 삭제하는 변경은 없고 writer/CAS API도 바꾸지 않는다.

첫 diff에서는 metadata가 있는 `reauth_required`/`disconnected`/`revoked`까지 auth unknown으로 덮이는 회귀를 발견했다. 부모에게 전달했고, 최종 diff는 **connected+blocked에만 unknown을 적용**하여 나머지 lifecycle 상태를 그대로 보존한다. 추가된 `tests.operations.test_managed_connections.ManagedTests.test_inactive_authorization_keeps_exact_lifecycle_status`를 독립 실행해 1개 PASS, skip 0, 0.044초를 확인했다. 이 시험의 네 상태 subtest는 unknown/reauth_required/disconnected/revoked를 다룬다. diff 재검토에서 보고한 회귀는 해소됐다. 부모가 수행하는 더 넓은 focused suite의 결과를 이 문서의 독립 실행 결과로 합산하지 않았다.

이 최소 차단 변경에서 추가 필수 결함은 발견하지 못했다. 최신 자격 읽기/요청 승인 경합과 generation 결속, action별 runtime 허가는 여전히 미래 연결 전의 별도 조건이다.
