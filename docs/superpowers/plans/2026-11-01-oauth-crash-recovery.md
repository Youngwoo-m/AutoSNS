# OAuth Crash Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**상태: 실행 전 사용자 검토본.** 2026-11-01. 검토받은 OAuth 설계의 필수 crash/orphan 경계 중 빠진 항목을 보완하는 후속 실행 계획이다. 현재 구현 완료·실제 Keychain 접근·실인증 활성화 승인을 뜻하지 않는다. 이 문서 작성 단계에서는 코드·schema·계정·자격을 변경하지 않는다.

**Goal:** 명시 recovery 명령으로만, 현재 workspace가 직접 stage했고 소유가 입증되며 어떤 유효·불명확 참조에도 연결되지 않은 자격만 안전하게 정리한다.

**Architecture:** durable stage journal과 backend 항목의 workspace/stage 결속 envelope/tag를 함께 사용한다. 모든 OAuth writer와 recovery가 같은 workspace 배타 잠금을 획득하고, 한 transaction으로 읽은 전체 참조 graph를 재검증한 뒤 정확히 일치하는 항목만 정리한다. journal·소유 marker·graph 중 하나라도 불명확하면 보존한다. GET·생성자·서버 재기동에는 cleanup을 넣지 않는다.

**Tech Stack:** 기존 Python3.15/SQLite/unittest, 표준 라이브러리 fcntl·threading·HMAC·secrets, MemoryCredentialBackend와 fake native bridge. 신규 패키지·서비스0.

**Spec:** [승인 OAuth 설계](../specs/2026-10-31-sns-oauth-connections-design.md)의 자격 stage→pointer CAS·unknown 보존·자기 namespace orphan 명시 정리 요구를 보완한다. [기존 구현 계획](2026-10-31-sns-oauth-connections.md) Task2/3/5와 [운영 안내](../../runbooks/oauth-connections.md)를 함께 읽는다. 신규 workspace identity/journal/schema 계약은 아직 구현되지 않았으며 기존 schema1 계약과 구별한다. 현재 API 대조 결과를 아래 확정 계약에 반영했다.

## 현재 확인된 결손

현재 `CredentialRef(namespace, account_id, platform, connection_id, generation, kind)`에는 **workspace가 없다**. `MacKeychainBackend._identity`도 namespace를 service로, 나머지 필드를 account로 사용하므로 서로 다른 workspace가 같은 ref를 만들 수 있다. 현재 root 안 journal에 ref를 적었다는 사실만으로 그 Keychain 항목의 소유를 입증할 수 없다. put이 duplicate로 실패한 경우에도 그 ref를 cleanup하면 타 workspace/이전 자격을 삭제할 수 있다.

`OAuthConnectionService._discard_unreferenced`는 현재 프로세스의 stage 목록만 알고, stage 직후 프로세스가 종료되면 그 목록을 잃는다. `OAuthDatabase`는 schema1이고 durable stage journal이 없다. pending refresh/revoke lease의 조회 unknown/manual projection은 별도 수정됐으나, 이는 orphan 회수나 lease 해제 구현이 아니다.

## Global Constraints

- 실제 로그인·키 발급/조회·Keychain 읽기/쓰기·OS 권한 부여·플랫폼 앱 등록·과금·발행0. 개발은 fake transport/in-memory vault/임시 저장소로 검증하고 실 provider adapter는 비활성 등록한다.
- main 기본 OAuth 서비스·vault·transport 미주입, runtime 실행 비활성 유지. app secret/redirect/실 HTTPS callback 경계 미확인 시 registration_blocked다.
- ordinary GET 외부 호출0. 생성자/일반 GET/서버 재시작에서 journal 초기화·vault 조회·복구·삭제·lease 해제0. recovery는 운영자가 명시 실행하는 별도 로컬 명령만 제공한다.
- 활성·unknown·진행 중·미완 attempt/proposal/receipt/lease가 가리키는 모든 ref는 보존한다. 만료 시각·generation 크기·연결 상태 하나로 orphan을 추정하지 않는다. 원격 부수효과가 불명확한 stage도 보존한다.
- 소유 증명 없는 기존/legacy 자격 자동 삭제0. 기존 ref/key를 새 envelope로 자동 변환·교체·열거·이식0. no-marker·다른 workspace·copied marker·duplicate put·tag 불일치는 삭제0이다.
- 실제 cleanup은 신규 전용 scoped 항목에만 적용한다. 원본 registry/기존 operations·metrics DB·IntegrationStore·기존 발행 credential/profile/STOP/quota/launchd/원본R/8700을 변경하지 않는다.
- 추가 결제/API/credit 소비0. recovery는 provider refresh/revoke/inspect/재교환/발행을 호출하지 않고 OAuth request receipt를 재전송하지 않는다.
- 공유 작업트리의 파일 소유권을 지킨다. 구현 시 task별 명시 파일만 수정하며 git add -A/reset/revert 금지. 실제 적용/backup/schema 전환/OS 수락은 부모의 별도 실행 gate다.

## Review Focus

1. journal intent 직후·backend put 직후·SQLite pointer 전환 직후·delete 직후 crash에서 유효/불명확 자격을 잃지 않는가(Task2/4/5).
2. 동일 ref를 가진 다른 workspace·복제한 marker·legacy 항목·duplicate put을 이 workspace의 orphan으로 오인하지 않는가(Task1/2/5).
3. recovery의 graph 조회와 삭제 사이 writer가 stage를 참조하거나 새 generation을 활성화하지 못하는가(Task3/5).
4. active/unknown/미완 attempt/proposal/lease/receipt 내부 ref 또는 알 수 없는 schema가 graph에서 빠져 삭제되지 않는가(Task2/4/5).
5. GET·재시작·기한 만료·dry-run·중복 recovery가 숨은 native I/O·삭제·provider 재전송·lease 해제를 만들지 않는가(Task4/5).

---

## 파일별 책임과 제안 계약

|파일|책임|
|---|---|
|신규 `common/operations/oauth_stage_models.py`|비공개 소유·stage 모델과 안전한 report DTO|
|신규 `common/operations/oauth_workspace.py`|명시 초기화 marker·canonical root binding 검증과 writer/recovery 공용 잠금|
|신규 `common/operations/oauth_stage_backend.py`|workspace/stage scoped backend 주소와 인증된 envelope; legacy backend와 명시 분리|
|신규 stage backend 안의 Memory/Keychain scoped adapter|기존 `SecurityFrameworkBridge.add/copy/delete(service,account,...)`를 주입받아 전용 주소로만 접근. 기존 legacy validator·backend 변경0|
|신규 `common/operations/oauth_stage_store.py`|durable stage journal 및 recovery event/CAS, 전체 참조 graph snapshot|
|수정 `common/operations/oauth_store.py`, `managed_connections.py`|명시 schema2 전환과 owned ref 직렬화/검증, commit과 journal 연결|
|수정 `common/operations/oauth_service.py`|모든 writer의 공용 lock·stage journal 경유, 기존 GET 순수성 유지|
|신규 `common/operations/oauth_recovery.py`|명시 inspect/cleanup 명령과 보수적 판정, HTTP route 없음|
|신규 `tests/operations/test_oauth_workspace.py`, `test_oauth_stage_backend.py`, `test_oauth_stage_store.py`, `test_oauth_recovery.py`|각 계약과 crash/소유/경합 검증|
|수정 `tests/operations/test_oauth_service.py`, `tests/test_web_oauth.py`|writer 통합·GET/native0·기존 lifecycle 계약 회귀|
|수정 `docs/runbooks/oauth-connections.md`, `docs/audits/2026-11-01-oauth-connections-acceptance.md`|미구현/격리 검증/OS 수락/readiness 및 복구 명령·보존 한계|

새 모델은 `CredentialRef`와 혼용하지 않는다. `WorkspaceOwner(workspace_id, root_binding, format_version)`와 `OwnedCredentialRef(ref: CredentialRef, workspace_id, root_binding, stage_id)`는 immutable/private repr다. scoped backend identity는 owner+stage+기존 ref 전체에 결속한 별도 `autosns.oauth.stage.v1` service/account 주소로 만든다. 기존 `autosns.oauth` 항목과 주소가 충돌하면 안 된다. 소유 key·payload·tag·ref 원문은 public HTTP/로그/report에 싣지 않는다.

`StageEnvelope`는 format_version/owner/stage_id/ref 전체/payload와 HMAC tag를 결속한다. 소유 key는 명시 초기화 시에만 workspace 전용 0600 marker에 생성한다(디렉터리0700). journal에는 key·payload·raw token/code/verifier/state를 쓰지 않는다. 경로 문자열만을 owner로 쓰지 않고 무작위 workspace_id와 canonical resolved-root binding을 함께 검증한다. marker를 복사·이동해 root가 달라지면 recovery와 신규 stage를 거부하고 보존한다. workspace 물리 이행/키 보관·재결속은 별도 계획이며 자동 adoption은 없다.

journal identity만으로 소유가 증명되지 않는다. 삭제하려면 **현재 marker owner = journal owner = scoped backend identity = envelope/tag owner**가 모두 일치해야 한다. 기존 ref의 secret을 읽어 workspace를 추정하지 않는다.

## 구현 전에 고정할 상세 계약

이 절은 위 인터페이스를 보충하며 충돌 시 우선한다. 감사 근거는 [실제 API 대조](../../audits/2026-11-01-oauth-recovery-contract-audit.md)에 있다. P0 표기는 현 운영 취약점 수가 아니라 초안에서 구현자가 추측해야 했던 계약 공백이다.

### 공용 context·codec·secret dispatch

- `--workspace`는 **oauth.sqlite3를 직접 포함하는 OAuth 저장 디렉터리**다. checkout/source root가 아니다. `WorkspaceOwner(workspace_id, root_binding, format_version)`는 비밀 없는 immutable 식별자이고, `OAuthWorkspaceContext(root: Path, owner: WorkspaceOwner, key_provider: WorkspaceKeyProvider)`는 private repr의 내부 객체다. key는 owner/DB/HTTP DTO에 넣지 않는다. `initialize_workspace_owner(root)`와 `load_workspace_owner(root)`는 이 context를 반환한다. 초기화만 marker/key/lock을 만들며 일반 load/생성자/GET는 생성0이다.
- marker의 random workspace_id는 UUID4 hex, key는 CSPRNG32bytes, root_binding은 canonical resolved absolute root의 filesystem bytes에 대한 SHA256 hex다. root디렉터리0700·marker0600·regular file·symlink거부·고정version/정확필드/길이를 검사한다. 최초 생성은 O_EXCL과 fsync(file/parent), 재호출은 기존 내용을 검증하고 덮어쓰지 않는다. 잘린 marker·copied root·권한불일치는 보존/오류다. 같은 root/key가 탈취된 경우까지 방어한다고 주장하지 않는다.
- `StoredCredentialRef = CredentialRef | OwnedCredentialRef`. `encode_stored_ref(value) -> dict`, `decode_stored_ref(value) -> StoredCredentialRef`, `logical_ref(value) -> CredentialRef`를 `oauth_stage_models.py`에 정의한다. legacy는 기존 정확6필드 dict, owned는 정확 `{format:'owned_v1', ref:<legacy6dict>, workspace_id, root_binding, stage_id}`다. unknown field/version/type는 거부한다. equality/hash에 전체 owner/root/stage/ref를 포함하고 자동 unwrap 저장0이다.
- 기존 `_ref`, attempt `_decode`, proposal/connection/lease의 모든 encode/decode, `_validate_context_ref`, `_checked_ref`, generation high-water, catalog/projector에 codec을 연결한다. 계정/platform/generation은 소유 검증을 통과한 `logical_ref`로만 읽고 실제 backend주소는 전체 stored ref로 유지한다. 현재 lease/비활성 자격 차단 정책을 보존한다.
- 별도 `ScopedCredentialAddress(service, account)`와 `ScopedRawBackend.add/copy/delete(address,...)`를 stage backend 안에 둔다. service는 `autosns.oauth.stage.v1`, account는 owner/root/stage/legacy6tuple을 고정 순서·compact JSON UTF8·allow_nan=False로 인코딩한 값의 SHA256 hex다. HMAC envelope는 같은 주소 입력과 payload를 고정 version으로 결속한다. legacy validator의 namespace 제한은 완화하지 않는다. Memory scoped adapter와 주입한 기존 SecurityFrameworkBridge를 쓰는 scoped adapter를 구현하며 개발에서는 fakebridge만 사용한다.
- service의 선택적 `workspace_context`/`stage_store`/`owned_backend`는 모두 같은 canonical root여야 한다. schema1의 기존 무주입 경로는 그대로 유지한다. schema2 owned-mode의 `stage_secret(operation_id, logical_ref, payload) -> OwnedCredentialRef`는 journal→create-only owned put→stored 기록 순서다. `read_secret(stored_ref)`는 legacy를 기존 주입 backend, owned를 context검증 후 scoped backend로 dispatch한다. client_secret_ref는 이번에 legacy 읽기 전용으로 유지하며 자동변환/삭제0이다.

### schema owner·operation·graph revision

- 유일한 전환 함수 `migrate_to_owned_schema(context)`는 공용 guard 아래 owner검증 후 schema1→2를 한 transaction으로 수행한다. schema0이면 기존 명시 초기화를 먼저 수행한다. 일반 `OAuthDatabase.initialize()`는 기존1/2를 보존하고 schema2를1로 내리지 않는다. updated `_db` reader는1/2를 지원한다. schema2의 **모든 write**는 같은 context의 held guard를 요구하고 없으면 `oauth_guard_required`다. schema1을 GET에서2로 변환하지 않는다. unknown version은 거부한다.
- schema2 추가 table은 `oauth_workspace_owner`, `oauth_stage_journal`, `oauth_operation_records`, `oauth_recovery_events`, `oauth_graph_meta`다. 기존 테이블을 삭제하지 않는다. journal/meta에 별도 monotonic `journal_revision`, `graph_revision`을 둔다. 기존 `oauth_meta.generation`은 managed 의미를 유지하며 graph revision으로 재사용하지 않는다.
- `OperationRecord`는 operation_id(UUID4hex), owner identity, kind(start/callback/continue/inspect/confirm/refresh/disconnect/revoke), receipt_id/attempt_id/connection_id/lease_id(선택), stage_ids, revision, remote_state, local_outcome을 갖는다. `begin_operation(...)`, `mark_remote_boundary(id, expected_revision, state)`, `finish_operation(id, expected_revision, outcome)`를 CAS로 제공한다. `remote_state=local_only|not_started|in_flight|returned|unknown`, `local_outcome=pending|referenced|unused|unknown`. remote in_flight는 provider 호출 전에 commit, returned는 유효 응답 수신 후 commit한다. 강제종료가 in_flight를 남기면 보존하고 자동재전송0이다. unknown→unused 자동승격0, pending/unknown receipt를 completed로 위장0이다. callback은 HTTP request receipt 없이 claim/attempt에 결속한 별도 local operation을 생성한다.
- stage `operation_id`는 위 record의 FK이며 임의 문자열이 아니다. 반환된 remote 응답만으로 unused가 되지 않는다. `unused`는 저장·CAS의 확정된 실패/미참조라는 terminal local 기록일 때만 허용한다. stage와 operation의 pending/unknown, 현재 lease 연관 항목은 모두 보존한다. provider응답 직후 기록전 crash도 보존한다.
- attempts/proposals/connections/request_receipts/operation_records의 INSERT/UPDATE/DELETE를 감지하는 명시 schema2 SQLite triggers로 graph_revision을 증가시킨다. stage edge/상태가 graph 보호 판정에 영향을 주는 journal 변경도 증가시킨다. journal 전용 회수 event는 journal_revision만 증가시킨다. migration은 기존 row의 보호graph를 유효하게 초기화한다. triggers는 일반 GET에 설치하지 않는다.
- `_db`와 stage store가 같은 connection을 쓰는 내부 unit-of-work를 제공한다. pointer/attempt/proposal의 ref전환과 해당 referenced journal mark는 같은 transaction에서 수행한다. read API 여러 개를 이어붙인 graph snapshot은 금지한다. snapshot 전체에 journal_revision과 graph_revision을 같이 담는다.

### 실제 보호graph·삭제·공통 잠금

- parser는 table/지원 payload version별로 필드를 검사한다. 직접 ref: attempt의 state_key_ref/verifier_ref/code_ref/ticket_ref/token_ref, proposal의 credential_ref, connection의 credential_ref 및 operation_lease.credential_ref. 간접 edge: receipt→operation→stage_ids, proposal→attempt, lease→operation→stage_ids. `snapshot().credential_refs`는 실행용 filtered view라 graph의 입력으로 쓰지 않는다. generation 숫자는 ref가 아니다.
- 상태·기한·consumed 여부와 무관하게 저장된 직접 ref는 모두 보호한다. pending/unknown operation의 stage edge도 보호한다. terminal unused operation의 stage edge만 후보 판정을 허용하되 다른 edge가 있으면 보존한다. 정상 신규 attempt는 connection row가 없을 수 있다. 이미 존재해야 할 proposal→attempt/lease→operation 등의 dangling edge, unknown JSON/field/ref/version은 전체 cleanup blocker다. 이전 schema1 기록에 operation_id가 없는 경우 legacy-protected로 보존하며 fabricated record를 만들지 않는다.
- 공용 guard는 canonical OAuth root를 key로 한 프로세스 registry의 RLock과 동일 lockfile의 flock을 결합한다. 획득 timeout은 monotonic 기반 고정 `oauth_workspace_busy`; 강제 lease해제0이다. fork 이후 inherited context/held token은 재사용을 거부한다. schema2 store `_db(write=True)`가 held context를 검사해 direct public store writer도 우회하지 못하게 한다. `_request`의 claim/action/finish 전체, callback claim/종료, migration·journal/event writer를 포함한다. 순서는 guard→짧은DB transaction이며 native작업 중 DB transaction은 닫는다.
- `inspect_recovery`는 명시 호출이라 owned read를 할 수 있지만 DB/vault write/delete0인 관측이다. candidate 판정과 reason/count/revisions만 반환한다. cleanup은 expected journal **및 graph revision**을 guard획득 후 비교한다. command에 `--expected-graph-revision <int>`를 추가한다. 내부 처리 후 최신revision을 새로 읽어 다음후보에 사용한다. 후보목록/ownership proof를 public report나 CLI argv로 반사하지 않는다.
- stage 저장상태(intent/stored/referenced)는 operation outcome과 별개다. cleanup event는 `delete_intent|absent|deleted|denied|locked|unavailable|preserved`를 가진다. owner/tag/전체graph/unused를 확인한 뒤 stage_revision/graph_revision/고정reason을 담은 delete_intent를 commit하고 exact delete를 수행한다. 삭제 직후 crash는 다음 명시 실행의 absent로 기록하며 과거 delete성공이라고 과장하지 않는다. not_found는 absent, denied/locked/unavailable는 보존이며 성공집계0이다. intent만 있고 backend에 항목이 없는 경우도 absent로 구분한다.
- 기존 `_delete`/`_discard_unreferenced`는 **owned ref에 대해 실제 삭제하지 않고 보존**한다. 모든 owned delete는 recovery의 guard/journal/전체graph를 통과한다. legacy lifecycle의 기존삭제 동작은 확대하지 않는다. 완료 attempt/consumed proposal에 역사 ref가 남으면 계속 보호하므로 회수 가능한 항목이 적을 수 있다. 역사 ref 퇴역·legacy namespace 열거/이식은 별도 범위이며 누락을 회수 성공으로 표시하지 않는다.

추가 필수 시험: owned token의 stage→attempt→proposal→confirm→reopen→refresh 왕복; schema1/2 각 read/write 지원·guard우회거부·원자 migration실패; operation remote boundary별 crash/unknown 자동재전송0; attempt만 변경해도 graphrevision증가; 정상 신규 connection부재와 dangling edge 구별; direct store writer/thread/process 경합; inspect쓰기0·delete_intent/absent/locked/중복 회수. 아래 Task1~5에 같은 파일 소유로 포함한다.

### Task1: 소유 모델·scoped backend와 marker 계약

**Files:** 신규 `oauth_stage_models.py`, `oauth_workspace.py`의 marker 부분, `oauth_stage_backend.py`; 기존 `credential_backend.py`, `keychain_backend.py`는 참조만 하고 변경하지 않음; 신규 `test_oauth_workspace.py`, `test_oauth_stage_backend.py`.

**Interfaces:** `initialize_workspace_owner(root) -> OAuthWorkspaceContext`는 명시 초기화만 수행한다. `load_workspace_owner(root) -> OAuthWorkspaceContext`는 검증만 하며 누락/권한/format/root 불일치 오류에서 생성하지 않는다. `OwnedStageBackend(context, raw_backend)`가 제공하는 `put_owned(owned_ref, payload) -> None`, `read_owned(owned_ref) -> bytes`, `delete_owned(owned_ref) -> None`는 정확한 scoped 주소와 envelope/tag를 검사한다. put은 create-only이고 duplicate를 성공으로 취급하지 않는다. native adapter는 explicit injection만 허용한다.

- [ ] `test_constructor_and_owner_load_never_create_marker`, `test_copied_marker_root_binding_is_rejected`, `test_same_legacy_ref_different_workspaces_have_distinct_scoped_identity`, `test_missing_marker_or_invalid_tag_never_deletes`, `test_duplicate_put_does_not_adopt_or_delete_existing_item`, `test_legacy_item_is_never_auto_wrapped`를 먼저 작성한다. marker/key/tag/payload의 repr·오류·로그 비노출도 단언한다.
- [ ] `python3 -m unittest tests.operations.test_oauth_workspace tests.operations.test_oauth_stage_backend -v` RED를 확인한다.
- [ ] Memory/fake-native로만 위 계약을 구현한다. scoped 주소 전체 일치 query를 사용하며 backend namespace 전체 열거/기존 Keychain 탐색은 추가하지 않는다. duplicate 항목은 owned라고 추정하지 않으며 보존한다.
- [ ] 같은 명령 GREEN/skip0을 확인한다. 기존 credential backend 시험으로 legacy exact-key 의미 보존을 확인하고 이 범위만 검토한다.

### Task2: durable stage journal·schema2·참조 graph

**Files:** 신규 `oauth_stage_store.py`; 수정 `oauth_store.py`, `managed_connections.py`; 신규 `test_oauth_stage_store.py`; 기존 store 회귀의 owned-ref fixture 변경만 허용.

**Interfaces:** `OAuthStageStore(context, clock)`의 생성자는 I/O0. `migrate_to_owned_schema(context)`만 명시 schema2 migration을 수행한다. `begin_stage(owner, owned_ref, operation_id, expected_revision) -> StageRecord`, `mark_stored(stage_id, expected_revision)`, `mark_referenced(stage_id, expected_revision, graph_revision)`, `mark_preserved(stage_id, expected_revision, reason_code)`, `mark_deleted(stage_id, expected_revision)`는 CAS다. `recovery_snapshot(owner) -> RecoverySnapshot(journal_revision, stages, protected_refs, blockers)`은 단일 read transaction에서 **모든** OAuth table을 읽는다.

- [ ] schema1→2 명시 전환·중복 초기화·unknown schema 거부·schema1 GET 미전환·비밀 없는 journal·crash 직후 intent/stored durable·journal CAS·graph 세대 일치 RED를 작성한다. schema2에는 owner metadata와 stage/events table을 추가하고 기존 OAuth table의 데이터를 삭제하지 않는다. 기존 operations schema3/metrics schema1과 registry bytes 불변을 단언한다.
- [ ] `test_graph_protects_active_unknown_and_every_attempt_proposal_receipt_lease_ref`에서 연결 active credential, operation lease old/new ref, 모든 미완/unknown attempt의 code/ticket/verifier/state_key/token ref, 미소비 proposal과 pending/unknown receipt가 결속하는 ref를 보호한다. 완료/만료 row에 ref가 남아 있어도 자동 제외하지 않는다. 미지 payload/ref 형식·누락된 연결·graph 파싱 오류는 snapshot blocker로 전체 삭제를 거부한다.
- [ ] `python3 -m unittest tests.operations.test_oauth_stage_store tests.operations.test_oauth_store tests.operations.test_managed_connections -v` RED→GREEN을 확인한다.
- [ ] journal intent를 backend put **전에** commit한다. 소유 marker가 없거나 다른 workspace이면 intent 생성0. pointer/attempt/proposal 연결과 journal referenced 전환은 가능한 경우 같은 SQLite transaction에 둔다. 불가능한 중간 crash도 graph가 ref를 보호하도록 한다. 기존 ref는 legacy protected로 읽으며 새 owned-ref 형식을 엄격히 구분한다.

### Task3: 공통 writer/recovery 배타 잠금

**Files:** `oauth_workspace.py` 잠금 부분; `oauth_service.py`, `oauth_store.py`, `managed_connections.py`, `oauth_stage_store.py`; 신규 workspace 시험과 기존 service/store 시험.

**Interfaces:** `oauth_write_guard(context: OAuthWorkspaceContext, timeout: float) -> context manager`는 동일 canonical workspace/owner에 대해 process 간 `flock`과 thread 내 직렬화를 결합한다. 생성자·GET는 획득/파일 생성하지 않는다. start/callback/continue/inspect-confirm pointer 전환/refresh/disconnect/revoke/정리 writer와 recovery가 동일 guard를 사용한다.

- [ ] 별도 프로세스 recovery가 graph를 읽은 후 정지시켜 writer 진입이 막히고, writer가 stage→commit 중이면 recovery가 기다리거나 busy로 끝나는 RED를 작성한다. thread·process 경쟁 모두 포함한다. 프로세스 종료 시 OS lock만 풀리고 durable pending/unknown은 그대로 남는지 검사한다.
- [ ] 잠금은 journal intent 전부터 backend stage·pointer CAS·journal 전환까지 보호한다. recovery는 snapshot→항목 소유 검사→즉시 graph 재검증→delete→journal 결과까지 같은 guard를 유지한다. 잠금을 timeout/기한만 보고 강제로 빼앗거나 lease를 지우지 않는다. callback도 동일 writer 경계에 포함해 정리 중 참조 추가를 막는다.
- [ ] 서로 다른 workspace는 scoped backend identity가 분리되어야 한다. 복제 marker/같은 owner의 다른 root는 Task1 검증으로 진입 자체를 거부한다. legacy/unscoped 항목은 이 잠금이 타 writer를 통제한다고 가정하지 않고 cleanup에서 제외한다.
- [ ] `python3 -m unittest tests.operations.test_oauth_workspace tests.operations.test_oauth_service -v` GREEN/skip0. 잠금은 `workspace guard`를 가장 바깥에서 유지한다. journal/graph용 짧은 SQLite transaction을 닫은 뒤 scoped backend 작업을 하고, 결과 기록은 새 짧은 transaction으로 수행한다. native I/O 중 SQLite transaction은 유지하지 않는다. guard 안에서는 다른 writer가 graph를 바꾸지 못하고, 삭제 직전 새 snapshot의 revision을 다시 비교한다. 기존 callback/provider lease/CAS의 중복 호출 차단을 완화하지 않는다.

### Task4: 명시 recovery 판정·idempotency와 service journal 통합

**Files:** 신규 `oauth_recovery.py`; 수정 `oauth_service.py`; 신규 `test_oauth_recovery.py`와 service stage/crash 시험.

**Interfaces:** `inspect_recovery(owner, journal, owned_backend, guard) -> RecoveryReport`는 **명시 호출** 때만 후보를 점검한다. `cleanup_recovery(..., expected_journal_revision, expected_graph_revision) -> RecoveryReport`는 같은 guard와 최신 snapshot으로 다시 판정한다. CLI는 `python3 -m common.operations.oauth_recovery --workspace <임시W> --mode inspect|cleanup --expected-workspace-id <id>`이며 cleanup에는 `--expected-journal-revision <int>`와 `--expected-graph-revision <int>`도 필요하다. root/actor/owner 입력은 설정 marker로 검증하고 HTTP route에는 연결하지 않는다. report는 안전한 개수·고정 reason·revision만 반환하며 payload/key/ref를 노출하지 않는다.

- [ ] 신규 stage의 `intent → stored → referenced` 전이를 service의 state_key/verifier/code/ticket/token stage에 연결한다. `put` 전 intent crash는 항목 부재로 안전히 완료 처리하되 duplicate/put 결과 불명확은 envelope/tag를 별도 입증하기 전 삭제0이다. refresh의 새 세대 stage와 old active pointer를 분리한다.
- [ ] 후보는 journal에 **현 owner가 직접 발급한 stage**로 있고, scoped 항목과 envelope/tag가 일치하고, snapshot 전체 참조graph에 없고, operation 결과도 확정된 미사용 stage일 때만 된다. 원격 성공/실패가 불명확한 stage·pending receipt/lease는 보존한다. 시간 경과만으로 후보가 되지 않는다.
- [ ] 삭제는 exact owned item만 수행한다. delete 성공→journal 기록 직전 crash는 다음 명시 호출에서 항목 부재 확인 후 idempotent하게 완료한다. delete denied/locked/storage failure는 고정 오류와 보존 상태를 기록하며 성공으로 표시하지 않는다. 조사 중 graph_revision/owner/tag가 바뀌면 삭제 전 중단한다.
- [ ] 기존 `_delete`/`_discard_unreferenced` 경로를 모두 점검해 신규 소유 증명 없는 legacy ref 삭제 권한이 recovery로 확대되지 않게 한다. 신규 cleanup 경로는 journal/guard/graph를 우회하지 않는다. 이전 활성 자격·unknown 항목을 orphan 회수 명목으로 자동 삭제하지 않는다. 기존 remote revoke/local disconnect 결과를 recovery가 성공/connected로 바꾸지 않는다.
- [ ] `test_constructor_get_restart_and_inspect_never_delete`, `test_unknown_remote_result_is_preserved`, `test_same_cleanup_twice_is_idempotent`, `test_delete_denied_is_not_reported_success`, `test_no_marker_and_legacy_ref_are_preserved` RED→GREEN. inspect는 vault 조회가 있을 수 있는 **명시 관리 행위**이며 일반 GET에 연결하지 않는다. 개발 시험에서는 Memory/fake bridge만 사용한다.

### Task5: crash matrix·다른 workspace·HTTP 순수성과 문서 gate

**Files:** 신규 recovery 시험, 기존 `test_oauth_service.py`, `tests/test_web_oauth.py`; 운영 안내/수락 문서.

- [ ] crash 지점별 subprocess 종료/reopen 시험을 작성한다: journal intent commit 전후, put 성공 직후, stored 기록 전후, attempt/proposal/pointer CAS 전후, 원격 refresh 응답 직후, delete 직후와 journal deleted 기록 전후. 정상 exception cleanup만 호출해 crash를 위장하지 않는다. fake provider·Memory backend의 durable 시험용 fake 저장소만 사용하며 실제 native/provider0이다.
- [ ] 서로 다른 W가 같은 legacy ref를 가진 경우, stage identity 충돌, copied marker, missing marker, backend duplicate, envelope/tag 변조, 알 수 없는 schema/ref, active/unknown/미완 graph 참조, cleanup 중 writer 경합, 중복 명령을 각각 검증한다. 보호 대상 byte/ref/generation/lease/receipt와 기존 사용자 자료가 보존되어야 한다.
- [ ] `python3 -m unittest tests.operations.test_oauth_workspace tests.operations.test_oauth_stage_backend tests.operations.test_oauth_stage_store tests.operations.test_oauth_recovery tests.operations.test_oauth_service tests.test_web_oauth -v`를 한 번 실행해 PASS/skip0과 실제 실행 수를 기록한다. GET/factory/main 미주입 시험에서 marker/journal 생성0·schema migration0·vault/native/provider0·삭제0을 단언한다. 실제 이미지/다른 전체 suite는 부모의 최종 영향 범위에 따라 별도로 한 번 실행한다.
- [ ] 문서에 code_ready/isolated_recovery_verified/real_keychain_accepted/real_oauth_ready/live_publish_ready를 구별한다. fake crash 시험을 실제 Keychain/OS 재시작 수락으로 표시하지 않는다. schema2 이전 전체 OAuth W 백업과 실패 보존·호환 코드 원복을 기록한다. DB를 과거 backup으로 덮어 신규 credential/unknown journal을 지우는 자동 원복은 금지한다.
- [ ] 독립 검토로 journal intent만을 소유 증명으로 오인하지 않는지, 보호graph 누락/TOCTOU/duplicate 삭제가 없는지 확인한다. 실 Keychain bridge의 scoped exact query·OS 접근권한·workspace 물리 이행은 별도 실환경 수락 gate로 남긴다. 이 계획의 격리 구현 완료로 실인증이나 cleanup 실행을 자동 활성화하지 않는다.

## 실행 순서와 자체 검토

Task1→Task2→Task3→Task4→Task5 순서다. 새 소유 모델/잠금/graph에 강한 의존이 있어 동시에 service/store를 변경하지 않는다. 구현 착수 시 선택된 실행 방식과 파일 소유권을 별도 원장에 기록한다. 현재 단계는 문서 검토이며, 코드 구현·운영 migration·실인증은 시작하지 않는다.

자체 검토: durable journal(Task2), workspace/stage envelope 소유 증명과 현재 namespace 결손(Task1), writer/recovery 배타 lock(Task3), active/unknown/attempt/proposal/receipt/lease 보호graph(Task2/4), explicit-only recovery/GET 순수성(Task4/5), crash·다른W·duplicate·no-marker 보존(Task5)을 모두 대응했다. legacy 자동 이식/삭제·lease 자동 해제·실 provider 재전송은 범위 밖이다. schema2/StoredCredentialRef codec·operation record·graph revision·전체 store guard·delete intent 계약을 실제 schema1/기존 CredentialRef가 이미 제공한다고 주장하지 않는다. 자체 검토에서 드러난 API 결손9건을 위 상세 계약으로 보완했다.
