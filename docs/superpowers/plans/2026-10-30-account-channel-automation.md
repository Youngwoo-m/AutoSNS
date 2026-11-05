# 계정별 채널 자동 운영 Implementation Plan

> **에이전트 구현자:** 필수 하위 스킬은 `superpowers:subagent-driven-development`(사용자가 요청한 병렬 방식) 또는 `superpowers:executing-plans`다. 각 작업을 체크박스로 추적하고, 독립 작업만 병렬화한다. 이 문서는 향후 구현 계획이며 지금 실행하는 지시가 아니다.

**Goal:** 개인·학과 계정의 기획부터 공개 검증·성과까지 추적하며 현재 교차 게시를 보존하는 자동 운영 기반을 구축한다.

**Architecture:** 기존 Python·AX 콘솔·axlock·채널 발행기를 재사용한다. 계정 등록부와 실행 컨텍스트를 먼저 통일하고 SQLite 원장·대상별 배포·복구를 연결한 다음 폴더·데이터를 분리한다. 한 작업·교차 게시 경로의 실행 주인은 항상 하나다.

**Tech Stack:** 기존 Python 3 환경, 표준 라이브러리 `sqlite3`, `dataclasses`, `enum`, `unittest`, `zoneinfo`, 기존 Selenium·채널 API 실행 환경. 새 패키지 설치를 이 계획 작성 단계에서 수행하지 않는다.

**Spec:** [승인된 설계](../specs/2026-10-30-account-channel-automation-design.md), [현황 근거](../../audits/2026-10-30-account-automation.md).

## Global Constraints

- 사용자 결정: 현재 교차 게시 방식 유지. A(실행 규칙 통일 후 폴더 분리) 선택.
- 사용자에게 보이는 모든 글은 한국어로 쓴다.
- 실제 로그인 디렉터리는 `~/.autosns-login/dept`, `~/.autosns-login/personal` 그대로 유지한다.
- 모든 브라우저·발행은 기존 `axlock`을 거치고, 비상 정지 중 신규 게시를 시작하지 않는다.
- TikTok 기준선은 공개 예정 후 30분, 최소 3시간 간격, 07:00 이상 23:00 미만이다. 최신 기준선과 대조하며 두 번 지연하지 않는다.
- 비활성 작업·기존 승인 수준·한도·비밀 키 이름을 임의로 변경하지 않는다.
- 원격 결과 `unknown`은 미게시로 간주하지 않는다. lease 만료만으로 재게시하지 않는다.
- 계정·정책·대상 확인 실패 시 다른 계정 기본값으로 넘어가지 않는다.
- 새 원장의 유일한 상태 기준은 SQLite, 원문·미디어는 파일이다. legacy 작업은 전환 전 기존 상태를 유지한다.
- 운영 main의 미커밋 파일을 보존한다. 구현은 격리 워크트리에서 하고 `git add .`·`git add -A`를 사용하지 않는다.
- 이번 승인 범위는 점검·설계·계획이다. 구현 착수, launchd 변경, 인증·공개 시험·발행·푸시는 수행하지 않는다.

## Review Focus

1. 부모 프로세스에 학과 환경변수가 남아 있어도 개인 실행 대상을 바꾸지 않아야 한다 → T2 시험.
2. 외부 목록 반영 지연·동일 제목·후보 다수에서 결과를 임의 연결하거나 재게시하지 않아야 한다 → T8 시험.
3. STOP이 프로필 대기 중 설정되고 다른 프로세스가 해제되어도 정지 순서가 뒤집히지 않아야 한다 → T7 시험.
4. 버전 변경·자산 순서·일정 이동이 기존 승인 또는 배포 키를 악용해 재게시를 만들지 않아야 한다 → T3·T5 시험.
5. USB 분리·DB 저장 실패·옛 백업 복구가 공개 게시 이력을 잊고 재개하는 계기가 되지 않아야 한다 → T5·T15 시험.

## 구현 경계와 파일 지도

모든 경로는 저장소 루트 기준이다. 신규 파일은 계획이며 아직 생성하지 않았다. `common.operations`는 저장소 루트에서 실행되는 관리 프로세스에서만 import한다. 옛 `common.py`를 쓰는 발행기는 별도 subprocess로 격리하여 동일 프로세스의 모듈 이름 충돌을 피한다. `common/__init__.py`를 추가하거나 옛 import 전체를 일괄 변경하지 않는다.

| 책임 | 신규/수정 위치 | 단일 소유자 |
|---|---|---|
| 기준선·계정·정책 계약 | `common/operations/models.py`, `registry.py`, `context.py`, `target_guard.py`, `approvals.py`, `crossposts.py`, `baseline.py` | A |
| 상태·실행·복구 | `common/operations/schema.sql`, `ledger.py`, `dispatch.py`, `publication_gate.py`, `quota.py`, `recovery.py`, `legacy_import.py` | B |
| 채널 연결·제작 | `common/publishers/` 신규 어댑터, `common/operations/production.py`, 기존 채널의 명시된 진입점 | C(필요 시 채널별 분할) |
| 통합·구조·성과·전환 | `ax-console/app/server.py`, `publishers.py`, 기존 wrapper·공용 잠금, `common/operations/metrics.py`, `layout.py`, `cutover.py`, `backup.py` | 통합 담당 |
| 시험·fixture | `tests/operations/`, `tests/publishers/`, `tests/integration/` | 각 기능 소유자, 공용 helper는 A |

관리 모듈은 import 시 DB·로그·브라우저·산출물 디렉터리를 만들지 않는다. DB 연결은 워커별로 열며 네트워크 호출 중 트랜잭션을 유지하지 않는다. 대상별 실제 계정·채널 ID는 기준선에서 가져오고 시험에는 가짜 ID만 사용한다.

각 묶음은 별도 시험·커밋으로 검토할 수 있지만 같은 계정 컨텍스트·원장·게시 관문에 의존하므로, 인터페이스가 서로 다른 독립 계획으로 갈라지지 않게 하나의 상위 계획에서 관리한다.

## 공통 계약: T2에서 먼저 고정

모든 dataclass는 frozen이며 `common/operations/models.py`에 정의한다. JSON 직렬화는 UTF-8·키 정렬·명시적 스키마 버전으로 고정한다. 문서의 `dict`는 아래 필수 필드를 갖는 JSON 객체다. 파일·설정 스키마는 같은 파일의 타입 및 `registry.py` 검증이 소유한다.

| 타입 | 필드·값 |
|---|---|
| `ExecutionRequest` | run_id, job_id, owner_account_id, content_id, content_revision, connection_id, schedule_slot, publication_purpose, action, dry_run, crosspost_rule_id(선택) |
| `ExecutionContext` | 요청의 필드 + destination_account_id, platform, target_id, credential_ref, profile_ref, expected_login_subject, policy_revision. 대상·자격증명 덮어쓰기 입력 없음 |
| `Registry` | revision, accounts, credentials, profiles, connections, jobs, policies, crossposts 매핑. jobs에 executor_id·schedule_owner·execution_owner·enabled 포함 |
| `RunLease` | run_id, worker_id, generation:int, expires_at:aware datetime |
| `SubmissionPermit` | delivery_id, attempt_id, lease_generation, context_hash, approval_hash, expires_at, nonce. 원장에서 유효·소비 여부 확인, 로그에 nonce 출력 금지 |
| `SubmissionResult` | status(uploaded/scheduled/published), remote_id, url, target_id, scheduled_at(선택). verified 아님 |
| `LookupResult` | kind(matched/absent/ambiguous/unavailable), candidates(게시 ID·대상·시각·콘텐츠 지문), evidence_ref |
| `VerificationResult` | status(pending/verified/mismatch/needs_auth/unsupported), remote_id, target_id, checked_at, evidence_ref |
| `ContractError` | ValueError 하위, code:str. 알 수 없는 계정·인증/프로필 소유 불일치·대상 불일치 구별 |

`Registry`의 연결은 account_id, platform, target_id, credential_ref, profile_ref, capabilities, enabled, auth_checked_at, last_success_at을 구분한다. `common`은 내부 작업 소유자만 가능하고 공개 연결의 계정은 dept/personal만 허용한다. 승인 subject는 원문·변환본·자산 해시·소유/대상·공개 옵션·일정 조건·정책 버전을 포함한다. 일정 조건 밖 변경은 재승인한다.

`PublicationAdapter` 프로토콜은 `inspect_target(ctx)->dict`, `prepare(ctx, snapshot:dict)->dict`, `submit(ctx, payload:dict, permit:SubmissionPermit)->SubmissionResult`, `lookup(ctx, fingerprint:str)->LookupResult`, `verify(ctx, remote_id:str, snapshot:dict)->VerificationResult`다. `snapshot`은 content_id, revision, owner_account_id, original, variants, assets(path/hash), reviews, options, schedule_condition을 가진 불변 사본이다.

Ledger의 run 요청 dict 필수 필드는 job_id,scheduled_at_utc,phase,source,request_kind이며 유일키는 (job_id,scheduled_at_utc,phase)다. delivery 요청 dict 필수는 run_id,content_id,revision,owner_account_id,connection_id,destination_account_id,publication_purpose,schedule_slot,policy_revision이며 유일키는 (content_id,revision,connection_id,publication_purpose,schedule_slot)다. 재시도는 기존 delivery_id를 사용한다. 새 revision이라도 기존 공개 게시 수정/재발행 의도를 구분하지 않으면 새 delivery를 자동 생성하지 않는다.

fixture helper는 T2의 `tests/operations/helpers.py`에 `registry()->Registry`, `request(**overrides)->ExecutionRequest`, `content(**overrides)->dict`, `context(**overrides)->ExecutionContext`, `snapshot(**overrides)->dict`, `FakeAdapter`를 정의한다. FakeAdapter는 `submit_calls`, `lookup_calls`와 사전 지정 결과·예외를 가지며 네트워크를 사용하지 않는다. 테스트의 `store`는 임시 디렉터리의 T5 `Ledger`다. 실제 비밀·로그인 프로필 fixture를 만들지 않는다.

## 의존성과 병렬 진행

```text
T1 기준선 → T2 공통 계약
              ├→ T3 승인 ─────────────┐
              ├→ T4 교차 게시 ────────┤
              └→ T5 원장 → T6 제출 ──┴→ T7 관문 → T8 복구 → T9 통합
T9 → T10 블로그 / T11 영상·소셜 / T12 제작 (계약·파일 분리 후 병렬)
T10~12 → T13 데이터·폴더 이행
T9 이후 T14 성과·기획은 fixture 기반 병렬 가능
T13 + T14 + 모든 adapter 결과 → T15 전환·복구·전체 수락
```

통합 담당 1명과 동시 실행 가능한 에이전트 3명 이내로 나눈다. T2에서 타입·시그니처를 고정한 후 T3·T4·T5를 병렬화한다. T10·T11·T12는 신규 어댑터·시험 파일만 각자 소유하고 `server.py`·공용 잠금·같은 legacy 파일은 통합 담당이 순서대로 반영한다. 실제 프로필·DB·launchd·데이터 전환은 직렬이다. 모든 작업자는 다른 작업자의 변경을 되돌리지 않는다.

## 공통 작업 절차

각 T의 체크박스는 나열한 단일 검증 가능한 행동이다. 시험 파일에는 아래 명시한 이름과 assertions를 구현한다. 명령은 **향후 구현 단계에서** 해당 워크트리 루트에서 실행한다. 현재 파일이 없으므로 계획 작성 단계에서 실행하거나 통과했다고 보고하지 않는다.

실패 확인은 `ModuleNotFoundError`, 정의되지 않은 인터페이스 또는 해당 요구의 assertion 실패여야 한다. 환경·네트워크·인증 오류는 기대한 RED가 아니다. 통과 확인은 지정 unittest의 `OK`, 부작용 mock 호출 수, DB 행·상태 assertions 모두로 판단한다.

각 작업 마지막 커밋은 그 작업 Files에 적힌 경로만 `git add <명시한 경로들>`로 추가하고 `git diff --cached --check`·`git diff --cached --stat` 후 수행한다. 커밋 제목은 아래 지정한 한국어 문장을 사용한다. 파일 이동 작업에서는 이동 전·후 경로와 관련 호출자를 함께 추가한다.

### T1. 읽기 전용 기준선과 운영 차이 목록

**선행/소유:** 없음 / A. **Files:** Create `common/operations/__init__.py`, `baseline.py`, `tests/__init__.py`, `tests/operations/__init__.py`, `tests/operations/test_baseline.py`, `tests/operations/fixtures/baseline.json`; 산출 문서 `docs/migrations/account-operations-baseline.md`.
**Interface:** `capture_baseline(root:Path, launchagents:Path, disabled:dict)->dict`; `compare_catalog(baseline:dict)->list[dict]`. 비밀 파일 내용·Chrome 데이터·로그 본문은 읽지 않고 설정의 허용 필드, 링크 메타데이터, plist 실행기·일정·비활성 상태만 캡처한다. 로드·가동·최근 성공 미확인은 unknown으로 둔다.

- [ ] `test_catalog_and_plist_mismatch_is_classified`, `test_capture_does_not_activate_or_read_secrets` 작성. 점검 fixture에서 등록부 37, plist 33, catalog-only 7, plist-only 3을 각각 assert하고 `start_job.assert_not_called()`, `read_secret.assert_not_called()`를 확인한다. 실제 기준선은 최신값이며 숫자 불일치를 강제로 지우지 않는다.
- [ ] `python3 -m unittest tests.operations.test_baseline -v`로 요구 때문에 실패하는지 확인한다.
- [ ] 두 함수를 구현한다. 모든 차이에 분류·근거·확인 필요 여부를 기록하고, 숨은 교차 게시 전체와 현재 활성 상태·환경·지시문·외부 호출자를 목록화한다.
- [ ] 같은 명령의 `OK`와 원본 파일 해시·mtime 불변을 확인한다.
- [ ] 커밋: `운영: 계정별 작업과 경로의 읽기 전용 기준선 추가`.

### T2. 등록부·컨텍스트·대상 검증 계약

**선행/소유:** T1 / A. **Files:** Create `models.py`, `registry.py`, `context.py`, `target_guard.py`, `tests/operations/helpers.py`, `test_registry.py`, `test_context.py`, `test_target_guard.py`, `fixtures/registry.json`(모듈 경로는 `common/operations/`); 설정 `ax-console/config/operations.json`(운영 기본 legacy·비활성 보존).
**Interface:** 위 공통 타입; `load_registry(path:Path)->Registry`; `resolve_context(request:ExecutionRequest,registry:Registry,content_owner_account_id:str)->ExecutionContext`; `validate_observed_target(ctx:ExecutionContext,observed:dict)->None`; `legacy_environment(ctx:ExecutionContext,registry:Registry)->dict[str,str]`. 관측 dict 필수: platform,target_id,authenticated,login_subject,verification_method.

- [ ] `test_unknown_account_never_falls_back`, `test_inherited_dept_environment_does_not_change_personal`, `test_wrong_target_does_not_submit` 작성. `ContractError.code`가 unknown_account/target_mismatch인지, 개인 토큰·프로필 참조가 정확한지, `adapter.submit_calls == 0`인지 assert한다. credential/profile 소유 불일치·중복 ID·없는 참조·common 공개 연결도 거부한다.
- [ ] `python3 -m unittest tests.operations.test_registry tests.operations.test_context tests.operations.test_target_guard -v`로 RED를 확인한다.
- [ ] 타입·검증·명시적 환경 allowlist를 구현한다. 기존 비밀 키 이름을 유지하고 부모 환경의 계정 선택값은 덮어쓰지 못하게 한다. 인증·구현·사용자 활성·최근 성공은 별도 필드다.
- [ ] 같은 시험 GREEN, 개인 safeworking 대상 및 두 YouTube 연결 구분, 미인증 상태 보존을 확인한다. 이후 공통 타입 변경은 통합 담당과 합의한다.
- [ ] 커밋: `계정: 등록부와 게시 대상 검증 계약 추가`.

### T3. 불변 콘텐츠와 승인 버전

**선행/소유:** T2 / A. **Files:** Create `common/operations/approvals.py`, `tests/operations/test_approvals.py`, `fixtures/approval_policy.json`.
**Interface:** `freeze_snapshot(content:dict,asset_root:Path)->dict`; `approval_fingerprint(snapshot:dict,ctx:ExecutionContext)->str`; `is_approval_current(record:dict,snapshot:dict,ctx:ExecutionContext)->bool`; `initial_approval_decision(job_id:str,registry:Registry)->str`. record 필수 subject_hash,decision,source,approved_at,policy_revision.

- [ ] `test_content_asset_target_schedule_change_invalidates`, `test_unknown_job_requires_review`, `test_snapshot_is_not_mutated_after_edit` 작성. 각 원문·변환·자산 바이트·대상·공개 옵션·일정 조건·정책 변경 후 `is_approval_current(...) is False`, 편집 후 승인 snapshot 해시 불변을 assert한다. 의미가 같은 JSON 키 순서 변경은 해시 동일, 자산 순서가 게시 순서를 바꾸면 해시 상이를 확인한다.
- [ ] `python3 -m unittest tests.operations.test_approvals -v`로 RED를 확인한다.
- [ ] 원본 파일·자산 해시와 불변 snapshot을 저장하고 기존 작업별 자동/수동 정책만 이관한다. 새 작업·새 대상에는 자동 승인을 부여하지 않는다.
- [ ] 같은 명령 GREEN, 정책 범위 안 일정 이동만 승인 유지하는 fixture를 확인한다. 승인 해시는 허용된 schedule_condition을 포함하고, 실제 시각이 그 범위 안인지 별도 검사한다. 실제 시각 변경 자체만으로 무조건 해시를 바꾸거나 허용 범위 밖 이동을 허용하지 않는다.
- [ ] 커밋: `검토: 콘텐츠와 매체별 승인 버전을 고정`.

### T4. 교차 게시와 시각 계산의 단일 소유자

**선행/소유:** T2 / A, T3와 순차 또는 다른 담당의 신규 파일만 병렬. **Files:** Create `common/operations/crossposts.py`, `ax-console/config/crossposts.json`, `tests/operations/test_crossposts.py`, `fixtures/crossposts.json`.
**Interface:** `crosspost_intents(event:dict,registry:Registry)->tuple[dict,...]`; `earliest_post_time(rule:dict,source_public_at:datetime,last_destination_post_at:datetime|None)->datetime`. event는 content_id,revision,owner_account_id,source_connection_id,phase,slot,source_public_at. intent는 rule_id,content_id,revision,owner_account_id,connection_id,not_before,transform_id. 규칙 필수 destination·enabled·delivery_owner·delay_seconds·min_gap_seconds·window·allowed_slots.

- [ ] `test_legacy_route_creates_no_managed_intent`, `test_evening_threads_only`, `test_tiktok_time_is_applied_once` 작성. legacy/disabled 결과 `()`, 아침 Threads 0·저녁 1, 공개 08:00→08:30, 직전 게시 07:00이면 10:00, 계산 결과 23:00→다음 날 07:00을 assert한다. 원본 personal·도착 dept를 함께 보존한다.
- [ ] `python3 -m unittest tests.operations.test_crossposts -v`로 RED를 확인한다.
- [ ] 기존 경로를 규칙으로 표현한다. 최초에는 TikTok 큐 정렬·최대 대기·시도 횟수까지 새로 구현하지 않고 legacy 소유로 관측만 한다. 4개 점검 예시 외 추가 경로도 T1 목록에서 빠짐없이 매핑한다.
- [ ] 같은 명령 GREEN, 비활성 연결·규칙 보존과 지연 이중 적용 없음, 원본 예약이 공개 성공으로 표시되지 않음을 확인한다.
- [ ] 커밋: `배포: 기존 교차 게시 경로와 시간 규칙 보존`.

### T5. SQLite 원장·상태 전이·한도 예약 기반

**선행/소유:** T2 / B. **Files:** Create `common/operations/schema.sql`, `ledger.py`, `tests/operations/test_ledger.py`.
**Interface:** `Ledger(path:Path)`는 I/O 없음; `.initialize()->None`, `.create_or_get_run(request:dict)->dict`, `.create_or_get_delivery(request:dict)->dict`, `.transition_delivery(delivery_id:str,expected_version:int,expected_states:frozenset[str],new_state:str,event:dict)->dict`, `.get_run(id:str)->dict`, `.get_delivery(id:str)->dict`, `.list_runs()->list[dict]`, `.list_deliveries(run_id:str)->list[dict]`, `.events(delivery_id:str)->list[dict]`. `StateConflict`는 models에 정의한다.

- [ ] `test_two_connections_deduplicate`, `test_cas_conflict_preserves_events`, `test_storage_failure_rolls_back_state` 작성. 같은 회차 run_id 동일·행 1, 같은 version의 두 전이 중 하나만 성공, event 삽입 실패 시 상태·version·event 모두 원상태를 assert한다. 별도 connection·재오픈·파일 분리 오류를 포함한다.
- [ ] `python3 -m unittest tests.operations.test_ledger -v`로 RED를 확인한다.
- [ ] jobs/triggers/runs/contents/revisions/deliveries/attempts/approvals/quota_reservations/events/incidents/metrics·legacy_mappings를 버전 있는 스키마로 만들고 UNIQUE·외래키·상태 전이표·CAS를 적용한다. 원격 호출 중 transaction을 잡지 않는다. permit 만료·한도·lease·세대·같은 대상/승인 해시 검사는 원장에서 일회성으로 소비한다. 상태 enum 값은 승인 설계의 제안 값으로 통일하고 임의 동의어를 만들지 않는다.
- [ ] 같은 명령 GREEN, import 시 파일 생성 없음·저널 모드 및 로컬 USB 잠금 검증 항목을 기록한다. 가짜/임시 파일시스템 시험을 실제 USB 내구성 증거로 대체하지 않는다.
- [ ] 커밋: `실행: 영속 원장과 원자적 상태 전이 추가`.

### T6. 회차 제출·단일 실행자·lease

**선행/소유:** T5 / B. **Files:** Create `common/operations/dispatch.py`, `tests/operations/test_dispatch.py`.
**Interface:** `submit_trigger(store:Ledger,request:dict,registry:Registry)->dict`; `claim_next_run(store:Ledger,worker_id:str,now:datetime,lease_seconds:int)->RunLease|None`; `heartbeat(store:Ledger,lease:RunLease,now:datetime)->bool`. request: job_id,scheduled_at(aware),phase,source,request_kind(resume/new_publication),mode(shadow/live/dry).

- [ ] `test_same_occurrence_claimed_once`, `test_prepare_and_verify_are_distinct`, `test_expired_lease_is_not_redispatched` 작성. 같은 회차 ID 동일·claim 1, prepare/verify ID 상이, shadow 행 생성 0, legacy 작업의 managed dispatch 거부, 오래된 generation heartbeat False를 assert한다.
- [ ] `python3 -m unittest tests.operations.test_dispatch -v`로 RED를 확인한다.
- [ ] Asia/Seoul 회차를 aware UTC로 정규화하며 phase를 유일키에 포함한다. naive datetime은 거부한다. schedule_owner와 execution_owner를 별도로 검사하고 lease 만료는 복구 대상으로 표시한다.
- [ ] 같은 명령 GREEN, 시각 표기만 다른 동일 순간의 중복과 수동 resume/new publication 구별을 확인한다.
- [ ] 커밋: `실행: 회차 중복 방지와 단일 워커 소유권 추가`.

### T7. 게시 관문·STOP·한도·예산

**선행/소유:** T3~T6 / B(신규 모듈), 통합 담당(기존 axlock). **Files:** Create `common/operations/publication_gate.py`, `quota.py`, `tests/operations/test_publication_gate.py`; Modify `common/shared/axlock.py`의 set_stop/clear_stop·실행 직전 확인. server STOP 경로는 T9에서 연결한다.
**Interface:** `reserve_quota(store,ctx:ExecutionContext,observed_usage:dict,now:datetime)->str`; `authorize_submission(store,ctx,snapshot:dict,approval:dict,lease:RunLease,reservation_id:str,now:datetime)->SubmissionPermit`; `consume_permit(store,permit:SubmissionPermit,ctx)->None`; `settle_quota(store,reservation_id:str,outcome:str)->None`. 모든 store는 Ledger. quota 예약 키는 대상·공용 API·소유 계정 제작비를 각각 구분한다.

- [ ] `test_stop_while_waiting_prevents_submit`, `test_cross_process_stop_order`, `test_quota_reservation_competes_and_unknown_holds` 작성. STOP 선행 시 permit 0·submit 0, 두 프로세스 경쟁의 결정된 시작 순서 보존, 한도 1·관측 수동 게시 1이면 신규 예약 0, unknown이면 예약 유지, 같은 permit 재사용 거부를 assert한다.
- [ ] `python3 -m unittest tests.operations.test_publication_gate -v`로 RED를 확인한다.
- [ ] 별도 axlock 자원 `control:publish-gate`를 모든 STOP 작성·허가 발급 경로에서 공유한다. 승인·대상·정책·lease·한도를 다시 확인하고 attempt를 영속화한다. 오래된/다른 계정의 AX_LOCKED 환경만으로 검증을 우회하지 못하게 한다.
- [ ] 같은 명령 GREEN, 브라우저 잠금을 쥔 채 한도 장기 대기 없음·진행 중 요청 결과 수습 허용·신규 후속 게시 차단을 확인한다. 외부 수동 게시와 API 호출까지 원자적으로 통제한다고 주장하지 않는다.
- [ ] 커밋: `발행: 정지와 한도 및 일회성 게시 허가를 통합`.

### T8. unknown·부분 실패·공개 검증 복구

**선행/소유:** T7 / B. **Files:** Create `common/operations/recovery.py`, `verification.py`, `tests/operations/test_recovery.py`.
**Interface:** `recover_expired_runs(store,now:datetime,process_probe:Callable)->list[dict]`; `reconcile_delivery(store,delivery_id:str,adapter:PublicationAdapter,now:datetime)->dict`; `resolve_unknown(store,delivery_id:str,decision:dict,actor:str)->dict`; `verify_delivery(store,delivery_id:str,adapter:PublicationAdapter,snapshot:dict)->VerificationResult`; `retryable_delivery_ids(store,run_id:str)->list[str]`. decision kind: link_existing/confirmed_not_posted/cancel_local, 근거·담당자 필수.

- [ ] `test_success_then_response_loss_is_not_resubmitted`, `test_zero_or_multiple_candidates_require_review`, `test_partial_failure_retries_only_failed_target` 작성. 원격 성공 후 단절/재시작에도 submit 누적 1, 후보 0/2/동일 제목 다른 본문은 unknown 또는 needs_review, 성공 게시 ID·소비량 보존을 assert한다. 예약 결과는 공개 시각 전 verified가 아님을 확인한다.
- [ ] `python3 -m unittest tests.operations.test_recovery -v`로 RED를 확인한다.
- [ ] 제목 단독 매칭을 금지하고 대상·게시 ID·시각·콘텐츠/미디어 지문으로 충분한 단일 결과만 연결한다. 살아 있는 옛 프로세스·불확실 lease는 재발행하지 않는다. completed는 필수 배포 전부 verified(비게시 작업은 요구된 산출물 완료), 일부 성공+실패는 partial, unknown/인증·검토 필요는 waiting으로 집계한다.
- [ ] 같은 명령 GREEN, 검증 실패는 재생성 아닌 조회·검토 대상으로 처리하고 원격 예약 취소/로컬 취소를 구분한다.
- [ ] 커밋: `복구: 결과 불명과 부분 성공의 재개 규칙 추가`.

### T9. 관리 CLI·콘솔·legacy 진입점 연결

**선행/소유:** T8 / 통합 담당. **Files:** Create `common/operations/cli.py`, `worker.py`, `legacy_runner.py`, `tests/integration/__init__.py`, `test_entrypoints.py`; Modify `ax-console/app/server.py`, `publishers.py`, `watcher.py`, `personal/claude-jobs/run_claude_job.sh`, `install.py`, `dept/naver-blog-auto/run_geoai.sh`, `run_geoai_evening.sh`, `run_jobs.sh`, `personal/naver-blog-auto/run_tistory.sh`; 나머지 run_*.sh는 T1 호출자 목록을 명시적 이행 manifest로 확정해 한 파일씩 적용한다.
**Interface:** `worker.run_once(store,registry:Registry,adapters:dict,now:datetime)->str|None`; `legacy_runner.run_registered(executor_id:str,ctx:ExecutionContext,input_path:Path,permit:SubmissionPermit|None)->dict`. CLI: `python3 -m common.operations.cli submit --job ID --scheduled-at ISO --phase PHASE --source launchd|console --dry-run`; `worker --once --dry-run`; `status`; `reconcile --delivery ID --dry-run`. 초기 live는 전환 증거 없으면 거부한다.

- [ ] `test_launchd_console_and_direct_wrapper_share_owner`, `test_unknown_executor_does_not_spawn`, `test_legacy_environment_is_isolated` 작성. 모든 진입점 동일 회차 ID, 미등록 명령 subprocess 0, managed 작업의 직접 legacy 실행 0, shadow 실행·배포 0을 assert한다. server의 API는 기존 관리자 인증을 요구하고 요청의 account/credential override를 거부한다.
- [ ] `python3 -m unittest tests.integration.test_entrypoints -v`로 RED를 확인한다.
- [ ] 콘솔 submit/검토/상태/STOP과 watcher를 원장에 연결한다. HTTP 응답이 없어도 enqueue 성공을 재생성하지 않게 request key를 반환한다. 관리된 모든 외부 진입점은 서브프로세스/셸 검증을 포함해 같은 owner와 permit 검사를 거치며, 미연결 진입점이 있으면 legacy로 남긴다. 기존 lock guard를 지우지 않는다.
- [ ] 같은 명령 GREEN, fixture plist만 변환해 비교한다. 실제 launchd 재등록·실행·계정 로그인 없이 통합 시험한다.
- [ ] 커밋: `통합: 콘솔과 기존 진입점을 공통 실행 관문에 연결`.

### T10. 블로그 채널 어댑터

**선행/소유:** T9 / C1. **Files:** Create `common/publishers/__init__.py`, `protocols.py`, `legacy_blog.py`, `blogger.py`, `naver.py`, `tistory.py`, `tests/publishers/__init__.py`, `test_blogs.py`; Modify `dept/naver-blog-auto/post_blogger.py`, `geoai_blogger.py`, `publish_naver.py`, `naver_crosspost_personal.py`, `personal/naver-blog-auto/tistory_post.py`, `tistory_crosspost.py`의 관리 진입점. `server.py` 변경은 통합 담당에게 제출한다.
**Interface:** models의 `PublicationAdapter` Protocol을 protocols.py에서 재노출하고 각 모듈 `build_adapter(registry:Registry,runner:Callable)->PublicationAdapter`를 제공한다. 토큰·프로필은 ctx에서만 해석한다. 5개 블로그 연결별로 prepare/submit/lookup/verify/기능표 시험을 각각 실행한다.

- [ ] `test_blogger_personal_target_only`, `test_safeworking_requires_personal_blog_and_profile`, `test_tistory_transform_is_preserved`, `test_import_creates_no_legacy_files` 작성. 학과 자격증명 조회 0·잘못된 대상 submit 0, 원문 URL·카테고리·AI 고지 fixture 동일, import 전후 임시 루트 파일 목록 동일을 assert한다.
- [ ] `python3 -m unittest tests.publishers.test_blogs -v`로 RED를 확인한다.
- [ ] 두 Blogger·두 네이버·개인 Tistory를 기존 환경 subprocess로 연결한다. snapshot→기존 payload 변환과 결과 정규화를 분리한다. submit 전 실제 permit 검사를 관리 진입점까지 전달하며 stdout 마지막 줄 성공만으로 verified를 만들지 않는다.
- [ ] 같은 명령 GREEN, 미지원 예약/조회/성과는 명시 unsupported, 실제 동작 없는 fixture 조회·발행만 확인한다.
- [ ] 커밋: `채널: 블로그 발행기를 계정별 배포 계약에 연결`.

### T11. 영상·소셜 어댑터와 대기열 호환

**선행/소유:** T9, T4 / C2. **Files:** Create `common/publishers/youtube.py`, `instagram.py`, `threads.py`, `tiktok.py`, `x.py`, `legacy_social.py`, `tests/publishers/test_social.py`; Modify `dept/youtube-shorts-auto/youtube_upload.py`, `geoai_short_post.py`, `tiktok_queue.py`, `tiktok_web.py`, `threads_post.py`, `x_post.py`, `dept/insta-cardnews/post_instagram.py`, `post_threads.py`, `threads_cli.py`의 관리 진입점. geoai_daily/run_jobs/disaster crosspost의 숨은 부작용 전환은 통합 담당이 순차 반영한다.
**Interface:** 모듈별 `build_adapter(registry,runner)->PublicationAdapter`; `tiktok.evaluate_legacy_queue(snapshot:dict,now:datetime)->dict`는 비교 전용이다. enqueue와 새 delivery 생성은 delivery_owner로 하나만 실행한다. YouTube(학과/개인)·Instagram·Threads·TikTok·X 각각을 별도 subTest로 어댑터 대상 확인/응답 정규화/unsupported/조회 실패 시험에 넣는다.

- [ ] `test_scheduled_youtube_is_not_verified`, `test_delay_gap_window_and_queue_order_match`, `test_managed_route_does_not_enqueue_twice`, `test_failed_tiktok_does_not_reupload_youtube` 작성. scheduled 상태의 verified_at 없음, 지연·간격·07/23시 경계·최대대기·시도·정렬 전체 baseline 동일, 원본 YouTube submit 누적 1·대상 delivery 1을 assert한다.
- [ ] `python3 -m unittest tests.publishers.test_social -v`로 RED를 확인한다.
- [ ] 계정별 실제 대상·AI 라벨·출처·매체 첨부·기존 후처리를 보존한다. TikTok 전체 큐 조건 비교 전에는 legacy owner를 유지한다. 새 큐가 지연을 계산하면 기존 add()가 다시 더하지 않게 단일 책임을 명시한다.
- [ ] 같은 명령 GREEN, 학과 채용의 Instagram·개인 Tistory 등 T1의 모든 부수효과가 명시되고 전환 전후 graph가 동일한지 확인한다.
- [ ] 커밋: `채널: 영상과 소셜 발행 및 교차 대기열을 연결`.

### T12. 기획·초안·검토·제작 실행기 분리

**선행/소유:** T9, T3 / C3. **Files:** Create `common/operations/production.py`, `tests/operations/test_production.py`; Modify `ax-console/app/agents/drafter.py`, `auto_review.py`, `personal/claude-jobs/공통규칙.md`, `jobs/survey-daily.md`, `jobs/survey-shorts.md`의 관리 모드 입출력. 다른 jobs/*.md도 T1에서 확인한 명시 목록으로 한 개씩 확장한다. 모델·기존 스케줄 변경 없음.
**Interface:** `produce_content(ctx:ExecutionContext,brief:dict,executor:Callable)->dict`; `validate_production_result(result:dict)->dict`. 결과는 content snapshot·원고/미디어 path/hash·출처·수치검토·미완료 이유만 포함하고, 직접 게시 권한은 포함하지 않는다.

- [ ] `test_managed_claude_does_not_publish`, `test_missing_calculation_or_source_review_requires_review`, `test_text_edit_does_not_change_numbers_or_sources` 작성. 제작 중 adapter.submit 0, 수식 콘텐츠의 검산 누락 승인 불가, 원문 대비 숫자·날짜·출처 보존을 assert한다. 준비·공개확인 회차는 다른 phase다.
- [ ] `python3 -m unittest tests.operations.test_production -v`로 RED를 확인한다.
- [ ] 관리 모드 Claude를 제작·검토 산출물로 제한하고 발행은 T7 관문으로 이관한다. legacy 지시문을 그대로 자율 발행시키면서 managed라고 표시하지 않는다. 기존 Remotion·디오라마·폰트·합성 고지·한국어 검토 지침을 참조한다.
- [ ] 같은 명령 GREEN, 파일 없는 자산·실패 검토·미완성 음성/영상이면 approved로 진행하지 않음을 확인한다. 실제 모델·크레딧 호출은 사용하지 않는다.
- [ ] 커밋: `제작: 생성과 검토 산출물을 실제 게시에서 분리`.

### T13. 기존 상태 가져오기·계정별 경로와 코드 이행

**선행/소유:** T10~T12 / 통합 담당(이동 직렬), B(순수 import 함수만). **Files:** Create `common/operations/legacy_import.py`, `layout.py`, `environment_manifest.py`, `common/tools/audit_account_paths.py`, `tests/operations/test_migration.py`, `docs/migrations/account-paths.md`; Modify `common/shared/paths.py`, `dept/naver-blog-auto/common.py`, `dept/youtube-shorts-auto/common.py`, `dept/insta-cardnews/common.py`, 개인 참조 지시문·진입점. 실제 move 대상은 아래 명시 묶음으로 T1 manifest에 경로를 고정한다.
**Interface:** `build_import_plan(snapshot:dict,registry:Registry)->dict`; `import_snapshot(store,plan:dict)->dict`; `resolve_layout(account_id:str,root:Path)->dict`; `build_path_migration(baseline:dict)->dict`; `can_remove_alias(alias:str,callers:list[str])->bool`. 반환 layout은 config_root/content_root/media_root/history_root. import는 경로·해시·원본 ID·게시 ID를 보존한다.

- [ ] `test_import_twice_preserves_identity_and_count`, `test_legacy_done_is_not_verified`, `test_personal_paths_never_use_dept_defaults`, `test_remaining_caller_blocks_alias_removal` 작성. 두 번 import 행수 불변, done→legacy_recorded·running→복구 대기, 개인 경로의 dept 포함 False, 호출자 1개라도 있으면 alias 제거 False를 assert한다. cwd 두 곳에서 같은 해석을 확인한다.
- [ ] `python3 -m unittest tests.operations.test_migration -v`로 RED를 확인한다.
- [ ] 상태 귀속→공용 추출→코드 이동→신규 산출물 경로→과거 데이터 순으로 이행한다. `geoai_*.py`·개인 네이버는 `personal/blog-auto/`, 개인 YouTube `geoai_short_post.py`·`geoai_video.py`·`geoai_youtube_auth.py`·`geoai_community*.py`는 `personal/shorts-auto/`를 목적지로 하되 공용 기능은 common에 둔다. T1 manifest가 개인 파일·공용 파일·호환 경로의 각 원본/목적지와 호출자를 열거하기 전에는 move를 금지한다.
- [ ] 같은 명령 GREEN, 토큰·로그인 폴더·기존 .venv 이동 0을 확인한다. 실행 interpreter는 기존 경로를 유지하고 새 환경 재생성은 잠금 명세·import 검증 이후 별도 체크포인트다. 링크 제거 전 모든 caller·관찰 증거를 확인한다.
- [ ] 커밋: `구조: 계정별 코드와 데이터 소유권을 이력 보존하며 분리`.

### T14. 계정별 성과·검색어·기획 순환

**선행/소유:** T9 이후 독립 fixture 개발, T10~T12 결과 계약 통합 / 전담 담당 또는 통합 담당. **Files:** Create `common/operations/metrics.py`, `planning_context.py`, `tests/operations/test_metrics.py`; Modify `common/analytics/collect_youtube.py`, `collect_blogger.py`, `collect_searchconsole.py`, `collect_naver_stats.py`, `collect_instagram.py`, `collect_threads.py`, `collect_x.py`, `collect_web.py`, `ax-console/app/agents/planner.py`, `common/shared/published_history.py`. server.py 화면은 통합 담당만 소유한다.
**Interface:** `collect_delivery_metrics(ctx:ExecutionContext,remote_id:str,collector:Callable)->dict`; `record_metrics(store,delivery_id:str,result:dict)->None`; `build_planning_context(account_id:str,registry:Registry,store)->dict`. metrics 결과 status(ok/unsupported/error),values,observed_at,remote_id,target_id를 보존한다.

- [ ] `test_planner_uses_account_credentials_and_sites`, `test_safeworking_is_in_planning_history`, `test_error_is_not_zero_performance`, `test_crosspost_metrics_preserve_owner_and_destination` 작성. 학과 요청에 개인 토큰 조회 0, safeworking 이력 포함·미존재 개인 Instagram 생성 0, error의 values는 빈 상태이며 0으로 바꾸지 않음, personal 원본/dept 대상/remote_id 연결을 assert한다.
- [ ] `python3 -m unittest tests.operations.test_metrics -v`로 RED를 확인한다.
- [ ] 검증된 게시 ID 중심으로 성과를 수집하고 미지원·실패·실제 0을 구분한다. Search Console은 등록된 계정 토큰·허용 사이트만 조회한다. 제작 비용은 원본 계정, 채널 성과·게시량은 실제 대상에 연결한다. 기획 제안 채택의 기존 승인 범위를 확대하지 않는다.
- [ ] 같은 명령 GREEN, 주간/월간 기존 집계에 신규 이력을 중복 더하지 않으며 원본과 모든 배포를 조회할 수 있음을 확인한다.
- [ ] 커밋: `성과: 게시 ID와 계정별 기획 데이터를 연결`.

### T15. 전환·롤백·전체 수락 증거

**선행/소유:** T1~T14 / 통합 담당, 직렬. **Files:** Create `common/operations/cutover.py`, `backup.py`, `common/tools/check_operations_release.py`, `tests/integration/test_acceptance.py`, `docs/runbooks/account-operations-cutover.md`; Modify `docs/폴더지도.md`, `docs/개인계정_이동안.md`, `ax-console/docs/전체자동화_개발파이프라인.md`, `ax-console/README.md`.
**Interface:** `assess_cutover(store,job_id:str,evidence:dict)->dict`; `build_rollback_plan(store,baseline:dict)->dict`; `backup_database(source:Path,destination:Path)->dict`; `check_release(evidence:dict,spec_path:Path)->dict`. 판단 결과 allowed:bool,blockers:list[str],evidence_refs:list[str]를 반환한다. 이 함수들은 plist 재등록·계정 로그인·게시·원격 삭제를 하지 않는다.

- [ ] `test_shadow_has_no_side_effects`, `test_disabled_survives_cutover_and_rollback`, `test_unknown_or_bypass_blocks_cutover`, `test_backup_restores_without_losing_post_history`, `test_every_acceptance_case_requires_evidence` 작성. shadow 외부 호출·실행생성 0, disabled 불변, 미연결 wrapper/unknown이면 allowed False, 새 성공 ID·unknown·quota를 잊는 rollback 거부, SQLite integrity_check=ok·foreign_key_check 결과 0행을 assert한다.
- [ ] `python3 -m unittest tests.integration.test_acceptance -v`로 RED를 확인한다.
- [ ] 일관된 SQLite backup·원본 hash·mapping·권한·실행 환경·스케줄 상태를 보존하는 전환 및 복구 보고서를 구현한다. 이전 DB 복원만으로 재개하지 못하게 신규 공개 이력 reconciliation을 요구한다. 코드 rollback과 원격 예약/공개 상태 복원을 구분한다.
- [ ] `python3 -m unittest discover -s tests -p 'test_*.py' -v`와 `python3 -m common.tools.check_operations_release --evidence <비밀없는-증거.json> --mode offline`을 실행한다. unittest OK·누락 증거 0만 로컬 완료다. 실제 USB·외부 읽기·비공개/공개 시험 증거가 없으면 보고서는 `offline_ready=True, production_ready=False`를 반환한다.
- [ ] 커밋: `운영: 계정별 전환과 중복 없는 롤백의 수락 기준 추가`.

## 운영 적용 체크포인트: 향후 별도 승인 범위

T15 로컬 완료 후 다음 순서를 실제 작업별로 직렬 수행한다. 현재 계획 작성으로 이 단계를 승인하거나 실행하지 않는다.

1. 최신 기준선과 비활성 설정을 읽어 대조하고 `axlock status`로 실행·대기·STOP 확인. 진행 중·unknown·미해결 quota가 있으면 전환하지 않는다.
2. 실제 USB 환경의 SQLite 잠금·저널·일관된 backup/restore를 비발행 사본에서 검증한다. 실패하면 원장 위치/파일시스템 선택을 재설계하고 전환 중단한다.
3. 어댑터별 읽기 전용 대상·인증·기능 확인. 인증 갱신·브라우저 작업은 사용자 필요와 axlock을 따르며, 기존 `--dry`도 편집기 입력 가능성을 확인한다.
4. 승인된 한 작업에서 원래 실행 주인을 차단한 뒤 새 제출 경로를 켠다. 중단된 동안의 새 요청은 원장에 보존하되 이중 실행하지 않으며, 스케줄/제출 주인 전환이 실패하면 새 제출은 비활성으로 남긴다. 비공개 시험·예약 생성은 정확한 대상과 범위를 별도 승인받는다.
5. 승인된 공개 시험에서 대상·본문·미디어·출처·예약/공개/검증·한도·후처리를 확인한다. 관찰은 해당 작업의 완전한 기존 반복 주기 1회 이상과 준비/확인 회차 모두 포함한다. TikTok은 게시창·간격·큐 실패 시험도 포함한다.
6. 관찰 실패 시 새 제출을 멈추고 외부 결과·원장·quota를 보존한 rollback 판단을 수행한다. 알 수 없는 결과를 지운 뒤 옛 작업을 켜지 않는다.
7. 대상별 성공 증거와 이행 manifest를 갱신한 후 다음 작업으로 확장한다. 모든 caller 전환·관찰 완료 전에는 호환 링크를 제거하지 않는다.

## 설계 요구사항 → 작업 추적

| 승인 설계 | 구현·검증 작업 |
|---|---|
| §1~3 목표·책임·단일 실행 흐름 | T1·T2·T6·T9·T15 |
| §4 계정/인증/대상 | T2·T7·T10·T11 |
| §5 채널 범위·지원 상태 | T2·T10·T11·T14 |
| §6 콘텐츠·상태·영속 원장 | T3·T5·T8·T12 |
| §7 트리거·주인·응답 유실 | T5·T6·T8·T9 |
| §8 잠금·STOP·quota·예산 | T7·T9·T14·T15 |
| §9 기존 교차 게시 유지 | T1·T4·T10·T11 |
| §10 승인·제작·검토 | T3·T12 |
| §11 폴더·데이터·환경 | T2·T9·T13 |
| §12~13 이행·롤백 | T1·T13·T15 및 운영 체크포인트 |
| §14 병렬 작업 | 소유자 표·의존성 DAG·공통 계약 |
| §15 수락시험 | T2~T15의 명시 시험과 전체 수락 증거 |
| §16 승인 범위·남긴 판단 | 이 문서의 Global Constraints·운영 체크포인트 |

## 계획 완료와 구현 착수의 구분

작성자는 설계 요구 추적, 단계 단위, 타입·시그니처 일치, 다섯 Review Focus의 시험 소유자, 문서 분량을 직접 점검한다. 계획에 적힌 신규 파일·명령은 앞으로 만들고 실행할 대상이며 현재 존재하거나 통과했다고 주장하지 않는다.

사용자가 요청한 병렬 에이전트 방식을 구현 방법으로 유지한다. 계획 검토 뒤 구현 착수 요청을 받으면 T1부터 계약 선행관계를 지키며 진행한다. 이번 목표의 완료는 현황·승인 설계·본 실행 계획이 작성·검증돼 전달되는 것이며, 자동 운영 시스템 구현·운영 가동 완료를 뜻하지 않는다.

## 작성자 자체 검토 기록

- 설계 16개 절을 위 추적표로 대조했다. 채널·제작·성과·폴더·복구를 모두 포함했다.
- 15개 작업마다 신규/수정 파일, 소비·생산 인터페이스, 실패·통과 명령, 구체적 assertions, 명시 경로 커밋을 배치했다.
- 공통 모델·메서드명·상태·유일키·시간대·승인 범위를 대조하고 publication_purpose 및 일정 조건을 보완했다.
- 다섯 Review Focus 모두 소유 작업과 시험을 연결했다. 외부 시험은 별도 운영 체크포인트로 구분했다.
- 본 계획은 승인 설계와 비슷한 분량이며 전체 구현 본문을 대신하지 않는다. 현재 수행한 검증은 문서 구조·근거 링크·기존 파일 경로·범위·diff 검사이며, 미래 unittest의 통과를 뜻하지 않는다.
