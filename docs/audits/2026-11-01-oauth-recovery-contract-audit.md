# OAuth crash recovery 실행 계약 독립 감사

2026-11-01. 대상은 [복구 초안](../superpowers/plans/2026-11-01-oauth-crash-recovery.md)과 [승인 OAuth 설계](../superpowers/specs/2026-10-31-sns-oauth-connections-design.md), 현재 `common/operations` 구현이다. 코드·계획·schema·운영 자료는 변경하지 않았다. 실계정·Keychain·provider·브라우저 조회와 서버 기동, 전체 suite 실행은 하지 않았다.

## 판정

초안의 보존 우선 방향은 타당하다. 그러나 **아직 그대로 구현 가능한 실행 계약은 아니다.** 신규 타입의 전달 경로, schema2 호환, 원격 작업 결과의 durable 결속, 전체 graph revision, 모든 writer의 잠금 강제를 먼저 확정해야 한다. 아래 P0/P1은 구현자가 임의로 메워서는 안 되는 결정이다. 현재 구현에 신규 기능이 없다는 사실 자체를 결함으로 세지 않고, 계획이 기존 API에 연결될 때 생기는 구체적 공백을 구분했다.

## 1. P0 — owned ref가 저장·조회·서비스 전 경로에서 끊긴다

근거: `oauth_models.py:145`의 `CredentialRef`는 여섯 필드와 고정 `autosns.oauth` namespace만 허용한다. `oauth_store.py:23`의 `_ref`는 이 타입만 받고, `:168`은 `CredentialRef(**payload)`로 복원한다. `managed_connections.py:52,105,119,149,160,170`도 같은 계약이다. `credential_backend.py:20`의 validator와 `oauth_service.py:142`는 owned wrapper를 거부한다. managed catalog도 `managed_connections.py:34`에서 기존 타입의 직접 속성을 읽는다.

초안의 `OwnedCredentialRef(ref, workspace_id, root_binding, stage_id)`를 기존 함수에 주면 `invalid_credential_ref`가 난다. `.ref`만 벗겨 저장하면 stage identity를 잃고 이후 `backend.get(ref)`는 legacy 주소를 조회한다. `OwnedStageBackend`는 `read_owned`를 제시하지만 서비스는 `get`만 호출한다. 단순 fixture 변경으로 해결되지 않는다.

최소 수정안:

- 비공개 `StoredCredentialRef = CredentialRef | OwnedCredentialRef`와 버전·종류를 구별하는 정확한 encode/decode 함수를 하나씩 정의한다. schema1의 여섯 필드 legacy dict와 schema2의 tagged owned dict를 구별하고 unknown 필드는 blocker다. owned의 equality/hash는 owner·root·stage·기존 ref 전부를 포함한다.
- `_validate_context_ref`, attempt·proposal·connection·lease encode/decode, generation 검사, catalog/projector, 서비스 `_checked_ref`를 변경 목록에 명시한다. 소유 검사 후에만 논리 ref의 account/platform/generation을 사용한다.
- 서비스 내부 `read_secret(stored_ref)`와 `stage_secret(...)` 계약을 정한다. legacy는 주입한 legacy backend로만 읽고, owned는 현재 owner를 검증한 scoped backend로만 읽는다. client secret은 `OAuthClientRegistration`이 legacy 타입만 허용하므로 이번 범위에서 legacy 읽기 전용으로 남길지 별도로 명시한다. 자동 wrapping은 하지 않는다.

필수 검증: owned token이 stage→attempt→proposal→confirm→reopen→refresh까지 identity 손실 없이 왕복하고, legacy 읽기는 기존 주소를 유지하며, 두 형식 사이 암묵 변환이 없어야 한다.

## 2. P0 — “확정된 미사용”과 원격 unknown을 journal에 기록할 API가 없다

근거: 초안 Task2의 전이는 `intent/stored/referenced/preserved/deleted`뿐이다. `operation_id`의 타입·발급 주체·존재 테이블·상태·CAS는 없다. 현재 request receipt에는 `attempt_id`만 있고, `bind_state_key`만 start receipt와 attempt를 결속한다(`oauth_store.py:60,180–195`). continue/refresh/revoke receipt의 operation 문자열에는 대상 ID가 들어가지만 새 stage의 원격 결과를 증명하는 record는 없다. `status='unknown'` receipt로 전환하는 메서드도 없다. `_request`는 성공만 completed로 쓰고 오류에서는 pending을 남긴다(`oauth_service.py:275–296`).

특히 refresh는 provider 응답 **뒤**에 generation/ref를 만든다(`oauth_service.py:568–574`). 응답 직후 crash에서는 새 token 자체가 아직 journal에 없으며 기존 lease만 남는다. put 직후 crash에서는 intent만 보고 이 작업이 원격 호출 전 취소였는지, 원격 성공 후 저장하다 끊겼는지 구별할 수 없다. envelope 일치는 소유 증명이며 원격 결과의 확정 증명은 아니다.

최소 수정안: 비밀 없는 durable operation record를 명시한다. 최소 필드는 `operation_id`, owner, operation kind, receipt/attempt/connection/lease 결속, revision, 원격 경계 상태(`not_started`, `in_flight`, `returned`, `unknown` 등), stage IDs, terminal local outcome이다. 실제 enum·허용 전이를 확정하고 **외부 호출 전에 in_flight를 commit**한다. callback은 HTTP request receipt가 없으므로 claim/attempt에 결속한 로컬 operation ID를 별도 발급한다. 원격 상태와 local stage 상태를 한 enum으로 섞지 않는다. `returned`만으로 삭제를 허용하지 않고 참조graph와 terminal unused 증거를 함께 요구한다. 기록이 없거나 crash로 중간인 경우 preserved다.

필수 검증: 원격 호출 직전/응답 직후/put 직후 crash가 각각 어떤 record를 남기는지 표로 정하고, unknown→자동 재전송·삭제 전이가 없음을 확인한다. 기존 pending receipt를 completed로 위장하거나 lease를 해제하지 않는다.

## 3. P0 — graph revision이 없으며 기존 generation으로 대체할 수 없다

근거: `oauth_meta.generation`은 managed connection 변경에서만 증가한다(`managed_connections.py:78,154,186,208`). attempt 생성·callback·resume·payload 변경, proposal 생성/소비, request receipt 변경은 전체 graph revision을 올리지 않는다. `RecoverySnapshot` 제안 필드에도 `graph_revision`이 없지만 `mark_referenced(..., graph_revision)`와 삭제 직전 revision 비교는 이를 요구한다.

최소 수정안: schema2에 `graph_revision`을 별도 도입하고 보호graph에 영향을 주는 **모든** transaction에서 증가시킨다. `RecoverySnapshot`에 이 값을 포함한다. journal revision은 복구 관리 기록용으로 분리하고, inspect가 `mark_preserved`로 journal을 바꾸는지 여부도 확정한다. cleanup의 expected journal revision은 guard 획득 후 첫 검사에서 비교하고, 내부의 각 mark로 바뀌는 revision을 어떻게 추적할지 정한다. graph snapshot은 attempt·proposal·connection·receipt·operation·stage tables를 **한 DB connection/read transaction**에서 읽는다. 여러 public snapshot/list API 조합은 대안이 아니다.

필수 검증: attempt만 추가되어도 graph revision이 증가하고, inspect/cleanup 사이 graph 변경은 stale 판정을 내린다. journal-only 이벤트와 graph 변경을 혼동하지 않는다.

## 4. P0 — graph의 실제 필드와 edge, 정상적인 “연결 없음” 정의가 빠졌다

근거: 실제 보호 ref는 attempt payload의 `state_key_ref/verifier_ref/code_ref/ticket_ref/token_ref`, proposal payload의 `credential_ref`, connection payload의 `credential_ref`, 그 안의 중첩 `operation_lease.credential_ref`다. 현재 lease에는 **old ref 하나만** 있으며 new ref 슬롯은 없다(`managed_connections.py:151`). receipt는 직접 ref를 담지 않고 start의 `attempt_id` 또는 operation 문자열로 간접 결속한다. `snapshot().credential_refs`는 connected만 반환하므로 복구graph에 재사용하면 unknown을 누락한다(`managed_connections.py:53`).

초안의 “누락된 연결은 blocker”를 모든 attempt에 적용하면 신규 connection ID를 발급하고 아직 연결 row가 없는 정상 동의 시작(`oauth_service.py:335–338`)도 workspace 전체 cleanup을 영구 차단한다. 반대로 단순 재귀 `_ref` 검색은 unknown 필드/형식을 건너뛸 수 있다.

최소 수정안: table·payload version별 필수/선택 필드와 직접·간접 edge를 열거한 parser 계약을 추가한다. receipt→operation→stages, proposal→attempt, lease→operation/stages를 명시하고 stage ID로부터 **전체 owned ref**를 얻는다. 신규 attempt의 연결 row 부재와, 있어야 할 persisted proposal/operation/lease 대상의 dangling edge를 구분한다. 연결/시도 상태·만료·consumed와 무관하게 남은 ref는 보호한다. 알 수 없는 schema/JSON/필드/ref/edge를 만나면 blocker이며 부분 parse 결과로 삭제하지 않는다. generation reservation 숫자는 ref가 아니다.

필수 검증: 정상 신규 동의는 false blocker를 만들지 않고, consumed proposal/완료·만료 attempt/unknown lease의 남은 ref는 모두 보호한다. unknown nested owned payload는 전체 cleanup을 차단한다.

## 5. P1 — schema2 전환 후 현재 reader/initializer는 즉시 실패한다

근거: `OAuthDatabase.initialize()`는 version 0/1만 받고 `PRAGMA user_version=1`을 실행한다(`oauth_store.py:49–64`). `_db`는 version 1만 허용한다(`:151`). Task2는 `OAuthStageStore.initialize(owner)`의 migration만 제시하므로 그 직후 모든 기존 attempt/managed reader가 `schema_mismatch`가 된다. 현재 `_db`도 journal transaction에 공유할 connection을 받지 않아 “가능하면 같은 transaction”을 어떤 메서드로 구현할지 없다.

최소 수정안: 하나의 schema owner와 migration API를 정한다. 예를 들어 schema1 명시 초기화는 기존 DB를 1로 유지하고, **유일한** `migrate_to_owned_schema(owner)`가 1→2를 수행한다. updated readers는 1·2를 명시 지원하고 schema1 GET은 생성/변환하지 않는다. schema2 owned writer는 검증된 owner metadata·공유 guard를 요구한다. schema2를 1로 내리거나 기존 initialize가 재작성하지 못하게 한다. stage store와 기존 store가 같은 `_db`/unit-of-work를 쓰고, pointer와 referenced journal mark를 결합한 내부 transaction 메서드를 정한다. 예외 fallback을 허용하려면 crash에서 graph가 먼저 보호하는 구체적인 commit 순서를 지정한다.

필수 검증: schema1/2에서 각 public read·write API의 지원/차단 표, initialize 재실행, migration 중 실패의 원자성, unknown version 거부를 확인한다. 호환 코드 원복은 이전 schema1 전용 binary로의 단순 교체가 아니다.

## 6. P0 — 공통 잠금의 주입 위치와 store 우회 경로가 미정이다

근거: 서비스 생성자는 서로 다른 `attempt_store`/`connection_store`를 그대로 받으며 root 동일성을 검사하지 않는다(`oauth_service.py:63–68`). 저장소 write 메서드는 public이고 각자 DB transaction만 연다. Task3의 수정 파일에는 `oauth_store.py/managed_connections.py`가 없다. action 내부만 감싸면 `_request`의 `claim_request/finish_request`는 guard 밖이다. 같은 프로세스의 서로 다른 서비스 인스턴스가 각기 `threading.Lock`을 갖는 구현도 충분하지 않다.

최소 수정안: canonical **OAuth 저장소 root**와 그 아래 `oauth.sqlite3`를 가리키는 단일 workspace context를 주입한다. 코드 checkout root/전체 운영 workspace/이 DB directory 중 무엇이 `--workspace`인지 확정한다. marker·lock·DB·stage store·attempt/managed store가 같은 canonical context임을 비밀/native I/O 없이 검사한다. 모든 writer가 guard 소유 token을 요구하거나 shared context의 guard를 획득하도록 store 메서드까지 파일 범위를 늘린다. 순서는 `workspace guard → 짧은 SQLite transaction`이다. `_request` 전체 receipt lifecycle, callback claim부터 모든 종료 기록, migration·recovery writer를 포함한다. GET·생성자는 guard 파일을 만들지 않는다. 중첩 호출은 공용 프로세스 registry/RLock 등으로 deadlock 없이 처리하고 OS flock fd 수명·fork 후 사용·timeout/busy 결과를 정의한다.

필수 검증: 같은 root의 서로 다른 service/store 인스턴스, thread, 별도 process에서 serialize되고, roots가 다른 store 조합은 거부된다. direct store writer도 recovery snapshot→delete 경계에 들어오지 못한다. journal event 자체의 write도 우회하지 않는다.

## 7. P1 — “전체 ref 보존”과 기존 즉시 삭제가 충돌한다

근거: 교환 finally는 code/ticket/verifier/state_key를 `_delete`로 직접 삭제하지만 attempt payload의 ref는 남긴다(`oauth_service.py:457`, `oauth_store.py:289`). target 교체는 이전 token을 직접 삭제하고(`oauth_service.py:512`), refresh/revoke 성공도 old ref를 직접 삭제한다(`:583`). 완료 attempt와 consumed proposal은 old token ref를 계속 보유한다. `_delete`는 저장소 삭제 오류를 삼킨다(`:150–154`). `_discard_unreferenced`는 연결 ref와 선택한 단일 attempt만 검사한다(`:156–169`).

따라서 “기존 경로를 점검”만으로는 신규 owned 항목이 전체 graph 검사를 우회해 지워질 수 있다. 반대로 모든 남은 ref를 보호하면 사용 완료 임시항목·교체된 token은 의도적으로 계속 보존되며 기존 삭제 테스트 기대도 달라진다.

최소 수정안: 이번 구현에서 owned에 대한 기존 `_delete`를 **삭제 없이 보존**으로 바꾸고 모든 owned 삭제를 recovery 경로로 제한할지 먼저 결정한다. legacy lifecycle 의미는 별도 명시하며 소유 없는 cleanup 권한을 확대하지 않는다. 남은 역사 ref 때문에 회수할 수 없는 항목은 보존 한계로 기록한다. 이후 필요하면 승인된 transaction에서 참조를 퇴역시키는 별도 계약을 마련하되, 이번 작업에서 완료/만료라는 이유로 역사 ref를 무시하지 않는다. recovery의 denied/locked/unavailable는 `_delete`의 swallow 동작을 재사용하지 않는다.

필수 검증: 성공·실패·finally·교체·refresh/revoke의 모든 경로에서 owned `delete` 호출이 journal/guard/전체 graph를 우회하지 않고, unknown stage는 정상 exception cleanup에서도 보존된다.

## 8. P1 — native scoped 주소와 HMAC key의 공급 계약이 빠졌다

근거: `MacKeychainBackend._identity`는 `validate_ref` 뒤 legacy service/account만 만든다(`keychain_backend.py:19–21`). `CredentialBackend` protocol은 legacy `put/get/delete`뿐이다. 그러나 lower bridge의 `add/copy/delete(service, account, ...)`는 이미 exact-address API다. owned service 문자열을 `CredentialRef.namespace`에 넣어 기존 backend를 재사용하면 validator에서 거부된다. `WorkspaceOwner` 제안에는 key가 없고 `OwnedStageBackend` 생성/주입 계약도 없어 `put_owned(owner,...)`의 HMAC key 출처가 정해지지 않았다.

최소 수정안: 기존 validator를 느슨하게 만들지 말고 별도 exact scoped address private 타입과 backend protocol 또는 기존 bridge를 주입한 전용 scoped adapter를 정한다. 주소의 canonical encoding, version, 길이 제한, owner/root/stage/ref 전체 결속, 문자열 연결의 모호성 방지를 명시한다. key는 private workspace context/key provider에서 얻고 `WorkspaceOwner`의 공개 식별 정보와 분리한다. marker 생성은 O_EXCL/안전한 임시파일+원자 rename/0600, 부모0700, 파일·디렉터리 fsync, symlink/일부 기록 검증까지 정의한다. intent/envelope/put duplicate는 서로 다른 사실로 남기며 기존 항목을 새 stage로 adopt하지 않는다. 개발에서는 fake bridge만 주입한다.

필수 검증: 같은 legacy logical ref의 서로 다른 owner/stage 주소가 분리되고, namespace 경로를 임의로 넘겨 legacy 항목을 읽거나 삭제할 수 없다. marker/HMAC key의 누락·권한·형식 오류는 생성·조회·삭제 권한을 만들지 않는다. root 변경 marker 거부와 같은 root/key 자체가 탈취된 경우의 신뢰 범위는 구별한다.

## 9. P1 — delete crash idempotency에는 삭제 의도와 실패 상태가 더 필요하다

근거: 계획은 delete 직후 crash를 다음 not-found로 완료 처리하지만 stage 전이에는 `deleting`/삭제 intent나 판정 당시 graph revision을 남기는 메서드가 없다. `put` duplicate가 발생한 intent, put 전 crash의 intent, 검증 후 delete 성공 기록 전 crash가 같은 상태로 남으면 “항목 없음”의 원인을 구분하기 어렵다. `mark_preserved`도 최종 상태인지 다시 평가할 수 있는 상태인지 미정이다.

최소 수정안: stage 저장 상태·작업 결과와 별도로 deletion attempt 이벤트/CAS를 정의한다. guard 안에서 owner·envelope·최신 전체 graph·operation outcome을 확인하고, 비밀 없는 delete intent에 stage revision/graph revision/판정 reason을 commit한 후 native delete를 수행한다. not-found는 항목 부재 결과로 구별해 기록하고, 과거 삭제 성공으로 과장하지 않는다. denied/locked/storage failure는 보존하며 다시 실행해도 성공으로 승격하지 않는다. unknown/tag mismatch/duplicate는 별도 reason이고, 재평가 허용 조건을 정한다. inspect가 쓰기 없는 관측인지 journal event를 남기는 관리 writer인지도 명시한다.

필수 검증: delete 직전·직후 crash, not-found/denied/locked/unavailable, 중복 cleanup, inspect 뒤 stale revision, 다중 후보 중간 실패에서 삭제 수·보존 수·revision이 일관되어야 한다.

## 격리 재현과 한계

현재 코드에 대한 작은 Python probe만 임시 디렉터리에서 실행했다. 신규 구현을 만들거나 unittest suite를 실행한 것이 아니다.

|확인|실제 결과|
|---|---|
|계획과 같은 필드의 owned wrapper를 `_ref`에 전달|`invalid_credential_ref`|
|같은 wrapper를 `validate_ref`에 전달|`credential_invalid_ref`|
|임시 schema1에 attempt만 생성 후 managed generation 비교|`0 → 0`|
|임시 DB user_version을 2로 바꾼 뒤 현 `ManagedConnectionStore.snapshot`|`schema_mismatch`|

외부 호출/native I/O는 0이며 임시 DB는 context 종료 시 삭제됐다. 이 결과는 위 연결 공백의 재현이며 신규 recovery의 안전성 수락 증거는 아니다.

## 착수 전에 필요한 최소 계약 보완 순서

1. 공용 workspace context·root 의미·owned ref codec·비밀 읽기 dispatch를 확정한다.
2. schema2 migration/reader compatibility·unit-of-work·graph revision을 확정한다.
3. durable operation과 실제 table별 graph edge/정상 누락 규칙을 확정한다.
4. store writer까지 공용 guard를 강제하고 기존 owned 직접 삭제 경로의 정책을 확정한다.
5. scoped native adapter/key provider·delete intent/CAS·report 상태를 확정한 뒤 crash matrix를 구현한다.

이 보완은 운영 cleanup 실행, 실제 Keychain 수락, 실 OAuth 활성화, 발행 승인을 의미하지 않는다. 현재 main 미주입·실행 비활성 gate를 유지한다.
