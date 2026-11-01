# OAuth Crash Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**상태: 초안.** 2026-11-01. 검토받은 OAuth 설계의 필수 crash/orphan 경계 중 빠진 항목을 보완하는 후속 실행 계획이다. 현재 구현 완료·실제 Keychain 접근·실인증 활성화 승인을 뜻하지 않는다. 이 문서 작성 단계에서는 코드·schema·계정·자격을 변경하지 않는다.

**Goal:** 명시 recovery 명령으로만, 현재 workspace가 직접 stage했고 소유가 입증되며 어떤 유효·불명확 참조에도 연결되지 않은 자격만 안전하게 정리한다.

**Architecture:** durable stage journal과 backend 항목의 workspace/stage 결속 envelope/tag를 함께 사용한다. 모든 OAuth writer와 recovery가 같은 workspace 배타 잠금을 획득하고, 한 transaction으로 읽은 전체 참조 graph를 재검증한 뒤 정확히 일치하는 항목만 정리한다. journal·소유 marker·graph 중 하나라도 불명확하면 보존한다. GET·생성자·서버 재기동에는 cleanup을 넣지 않는다.

**Tech Stack:** 기존 Python3.15/SQLite/unittest, 표준 라이브러리 fcntl·threading·HMAC·secrets, MemoryCredentialBackend와 fake native bridge. 신규 패키지·서비스0.

**Spec:** [승인 OAuth 설계](../specs/2026-10-31-sns-oauth-connections-design.md)의 자격 stage→pointer CAS·unknown 보존·자기 namespace orphan 명시 정리 요구를 보완한다. [기존 구현 계획](2026-10-31-sns-oauth-connections.md) Task2/3/5와 [운영 안내](../../runbooks/oauth-connections.md)를 함께 읽는다. 이 초안의 신규 workspace identity/journal/schema 계약은 아직 구현되지 않은 제안이며 기존 schema1 계약과 구별한다.

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
|수정 `common/operations/credential_backend.py`, `keychain_backend.py`|전용 scoped exact-address 접근 지원, 기존 CredentialRef API 자동 변환0|
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

### Task1: 소유 모델·scoped backend와 marker 계약

**Files:** 신규 `oauth_stage_models.py`, `oauth_workspace.py`의 marker 부분, `oauth_stage_backend.py`; 수정 `credential_backend.py`, `keychain_backend.py`; 신규 `test_oauth_workspace.py`, `test_oauth_stage_backend.py`.

**Interfaces:** `initialize_workspace_owner(root) -> WorkspaceOwner`는 명시 초기화만 수행한다. `load_workspace_owner(root) -> WorkspaceOwner`는 검증만 하며 누락/권한/format/root 불일치 오류에서 생성하지 않는다. `OwnedStageBackend.put_owned(owner, owned_ref, payload) -> None`, `read_owned(owner, owned_ref) -> bytes`, `delete_owned(owner, owned_ref) -> None`는 정확한 scoped 주소와 envelope/tag를 검사한다. put은 create-only이고 duplicate를 성공으로 취급하지 않는다. native adapter는 explicit injection만 허용한다.

- [ ] `test_constructor_and_owner_load_never_create_marker`, `test_copied_marker_root_binding_is_rejected`, `test_same_legacy_ref_different_workspaces_have_distinct_scoped_identity`, `test_missing_marker_or_invalid_tag_never_deletes`, `test_duplicate_put_does_not_adopt_or_delete_existing_item`, `test_legacy_item_is_never_auto_wrapped`를 먼저 작성한다. marker/key/tag/payload의 repr·오류·로그 비노출도 단언한다.
- [ ] `python3 -m unittest tests.operations.test_oauth_workspace tests.operations.test_oauth_stage_backend -v` RED를 확인한다.
- [ ] Memory/fake-native로만 위 계약을 구현한다. scoped 주소 전체 일치 query를 사용하며 backend namespace 전체 열거/기존 Keychain 탐색은 추가하지 않는다. duplicate 항목은 owned라고 추정하지 않으며 보존한다.
- [ ] 같은 명령 GREEN/skip0을 확인한다. 기존 credential backend 시험으로 legacy exact-key 의미 보존을 확인하고 이 범위만 검토한다.

### Task2: durable stage journal·schema2·참조 graph

**Files:** 신규 `oauth_stage_store.py`; 수정 `oauth_store.py`, `managed_connections.py`; 신규 `test_oauth_stage_store.py`; 기존 store 회귀의 owned-ref fixture 변경만 허용.

**Interfaces:** `OAuthStageStore(root, clock)`의 생성자는 I/O0. `initialize(owner)`만 명시 schema2 migration을 수행한다. `begin_stage(owner, owned_ref, operation_id, expected_revision) -> StageRecord`, `mark_stored(stage_id, expected_revision)`, `mark_referenced(stage_id, expected_revision, graph_revision)`, `mark_preserved(stage_id, expected_revision, reason_code)`, `mark_deleted(stage_id, expected_revision)`는 CAS다. `recovery_snapshot(owner) -> RecoverySnapshot(journal_revision, stages, protected_refs, blockers)`은 단일 read transaction에서 **모든** OAuth table을 읽는다.

- [ ] schema1→2 명시 전환·중복 초기화·unknown schema 거부·schema1 GET 미전환·비밀 없는 journal·crash 직후 intent/stored durable·journal CAS·graph 세대 일치 RED를 작성한다. schema2에는 owner metadata와 stage/events table을 추가하고 기존 OAuth table의 데이터를 삭제하지 않는다. 기존 operations schema3/metrics schema1과 registry bytes 불변을 단언한다.
- [ ] `test_graph_protects_active_unknown_and_every_attempt_proposal_receipt_lease_ref`에서 연결 active credential, operation lease old/new ref, 모든 미완/unknown attempt의 code/ticket/verifier/state_key/token ref, 미소비 proposal과 pending/unknown receipt가 결속하는 ref를 보호한다. 완료/만료 row에 ref가 남아 있어도 자동 제외하지 않는다. 미지 payload/ref 형식·누락된 연결·graph 파싱 오류는 snapshot blocker로 전체 삭제를 거부한다.
- [ ] `python3 -m unittest tests.operations.test_oauth_stage_store tests.operations.test_oauth_store tests.operations.test_managed_connections -v` RED→GREEN을 확인한다.
- [ ] journal intent를 backend put **전에** commit한다. 소유 marker가 없거나 다른 workspace이면 intent 생성0. pointer/attempt/proposal 연결과 journal referenced 전환은 가능한 경우 같은 SQLite transaction에 둔다. 불가능한 중간 crash도 graph가 ref를 보호하도록 한다. 기존 ref는 legacy protected로 읽으며 새 owned-ref 형식을 엄격히 구분한다.

### Task3: 공통 writer/recovery 배타 잠금

**Files:** `oauth_workspace.py` 잠금 부분; `oauth_service.py`; 신규 workspace 시험과 기존 service 시험.

**Interfaces:** `oauth_write_guard(owner, root, timeout) -> context manager`는 동일 canonical workspace/owner에 대해 process 간 `flock`과 thread 내 직렬화를 결합한다. 생성자·GET는 획득/파일 생성하지 않는다. start/callback/continue/inspect-confirm pointer 전환/refresh/disconnect/revoke/정리 writer와 recovery가 동일 guard를 사용한다.

- [ ] 별도 프로세스 recovery가 graph를 읽은 후 정지시켜 writer 진입이 막히고, writer가 stage→commit 중이면 recovery가 기다리거나 busy로 끝나는 RED를 작성한다. thread·process 경쟁 모두 포함한다. 프로세스 종료 시 OS lock만 풀리고 durable pending/unknown은 그대로 남는지 검사한다.
- [ ] 잠금은 journal intent 전부터 backend stage·pointer CAS·journal 전환까지 보호한다. recovery는 snapshot→항목 소유 검사→즉시 graph 재검증→delete→journal 결과까지 같은 guard를 유지한다. 잠금을 timeout/기한만 보고 강제로 빼앗거나 lease를 지우지 않는다. callback도 동일 writer 경계에 포함해 정리 중 참조 추가를 막는다.
- [ ] 서로 다른 workspace는 scoped backend identity가 분리되어야 한다. 복제 marker/같은 owner의 다른 root는 Task1 검증으로 진입 자체를 거부한다. legacy/unscoped 항목은 이 잠금이 타 writer를 통제한다고 가정하지 않고 cleanup에서 제외한다.
- [ ] `python3 -m unittest tests.operations.test_oauth_workspace tests.operations.test_oauth_service -v` GREEN/skip0. 잠금은 `workspace guard`를 가장 바깥에서 유지한다. journal/graph용 짧은 SQLite transaction을 닫은 뒤 scoped backend 작업을 하고, 결과 기록은 새 짧은 transaction으로 수행한다. native I/O 중 SQLite transaction은 유지하지 않는다. guard 안에서는 다른 writer가 graph를 바꾸지 못하고, 삭제 직전 새 snapshot의 revision을 다시 비교한다. 기존 callback/provider lease/CAS의 중복 호출 차단을 완화하지 않는다.

### Task4: 명시 recovery 판정·idempotency와 service journal 통합

**Files:** 신규 `oauth_recovery.py`; 수정 `oauth_service.py`; 신규 `test_oauth_recovery.py`와 service stage/crash 시험.

**Interfaces:** `inspect_recovery(owner, journal, owned_backend, guard) -> RecoveryReport`는 **명시 호출** 때만 후보를 점검한다. `cleanup_recovery(..., expected_journal_revision) -> RecoveryReport`는 같은 guard와 최신 snapshot으로 다시 판정한다. CLI는 `python3 -m common.operations.oauth_recovery --workspace <임시W> --mode inspect|cleanup --expected-workspace-id <id>`이며 cleanup에는 `--expected-journal-revision <int>`도 필요하다. root/actor/owner 입력은 설정 marker로 검증하고 HTTP route에는 연결하지 않는다. report는 안전한 개수·고정 reason·revision만 반환하며 payload/key/ref를 노출하지 않는다.

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

Task1→Task2→Task3→Task4→Task5 순서다. 새 소유 모델/잠금/graph에 강한 의존이 있어 동시에 service/store를 변경하지 않는다. 구현 착수 시 선택된 실행 방식과 파일 소유권을 별도 원장에 기록한다. 이 문서 작성에서는 작업자·자식·커밋·구현을 시작하지 않는다.

자체 검토: durable journal(Task2), workspace/stage envelope 소유 증명과 현재 namespace 결손(Task1), writer/recovery 배타 lock(Task3), active/unknown/attempt/proposal/receipt/lease 보호graph(Task2/4), explicit-only recovery/GET 순수성(Task4/5), crash·다른W·duplicate·no-marker 보존(Task5)을 모두 대응했다. legacy 자동 이식/삭제·lease 자동 해제·실 provider 재전송은 범위 밖이다. 초안의 schema2/OwnedCredentialRef·새 scoped backend 계약을 실제 schema1/기존 CredentialRef가 이미 제공한다고 주장하지 않는다.
