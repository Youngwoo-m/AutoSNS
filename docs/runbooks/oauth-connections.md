# SNS OAuth 연결 운영 안내

채널·계정의 **공식 OAuth 연결·준비 상태**에서 개인/학과와 공식 방식을 선택한다. 전체 계정은 조회 전용이다. 도구 사용 선호의 활성 값은 실제 계정 인증이나 발행 권한이 아니다.

기본 main은 OAuth 서비스·vault·provider transport를 주입하지 않는다. 10개 방식의 catalog와 준비 차단 상태만 조회하며 연결 POST는 503이다. 앱 등록·OS 자격 저장소·정확한 HTTPS callback·scope·비용 0 증거를 개별 수락하기 전 실제 동의를 시작하지 않는다. 현재 실 OAuth와 발행 준비 완료를 뜻하지 않는다.

명시적으로 구성된 격리 환경의 순서는 계정/방식 → 준비 상태와 요청 scope 확인 → 동의 시도 → callback 임시 수신 → 같은 세션에서 돌아온 시도 직접 선택 → 연결 계속 → 주체/대상 조회 → 표시명과 원격 ID/제안 revision 확인 → 대상 확인이다. callback만으로 token 교환이나 연결 확정이 되지 않는다. 결과 화면은 `/connections/oauth-result`이고 URL query의 code/state/token을 화면에 복사하지 않는다.

연결 확인·갱신·로컬 해제·원격 해지 성공 뒤 현재 연결 목록과 CAS revision을 GET으로 다시 읽는다. POST가 성공하고 GET만 실패하면 성공 상태와 입력을 보존한다. **등록·연결 상태 조회**를 직접 눌러 확인하며 mutation을 자동 재전송하지 않는다. 401/409/503 불확실 요청은 원래 request key와 입력을 보존한다. 409 재검증은 조회 후 별도 클릭으로 새 요청을 제출한다.

로컬 연결 해제는 overlay 사용을 중단한다. 원격 권한 해지·기존 발행 자격 삭제와 다르다. Google의 프로젝트 전체 영향이 미확인이면 원격 해지를 차단한다. 신규 연결 overlay는 로컬 해제 후 목록에서 사라질 수 있다. 완료 연결은 같은 console actor의 새 로그인 세션에서 관리할 수 있지만 미완 시도의 소유권/continue는 원래 세션 결속을 유지한다.

닫기·Escape·바깥 클릭·계정 전환은 host guard를 거쳐 busy 또는 미확인 대기 요청을 보호한다. OAuth drawer의 새로고침은 busy/pending을 버리지 않는다. 브라우저 이탈도 진행 중/대기 요청을 보호한다. 기존 원고 편집/기술사/발행 패널/9개 메뉴는 유지한다.

## 격리 브라우저 검증

부모가 `.superpowers/sdd/2026-11-01-sns-oauth-connections/preview-oauth.py`를 실행한다. 임시 source/workspace/검증 webroot, 가상 비밀번호 `fixture-password`, MemoryVault, fake provider와 명시 test-only callback만 사용한다. 운영 서버·실계정·Keychain·실 provider HTTP를 사용하지 않는다. 화면 상단과 drawer에 가상 검증 경고를 표시한다.

공식 동의 링크는 클릭하지 않는다. 시도 ID를 확인한 뒤 실행 프로세스 stdin에 `{"callback":"시도ID"}`를 보내 가상 callback만 수신한다. 일반 GET은 외부 호출을 하지 않는다. `{"stop":true}`로 종료하면 임시 자료를 정리한다. 이 helper는 제품 main이 아니며 운영 배포 대상으로 복사하지 않는다.

## 적용과 원복

운영 정적 파일은 OAuth manifest의 original/desired actual SHA 및 모든 artifact/module SHA를 먼저 검증하고 전체 검증 뒤 복사한다. 시험 overlay는 OAuth → toolkit → tracked checkout 순서로 선택하며 예전 toolkit artifact를 최신 OAuth 위에 덮지 않는다. ignored manifest가 없어도 tracked checkout으로 시험하며 누락 skip을 사용하지 않는다.

8769의 오프라인 준비 화면 적용과 자료 보존 확인을 완료했다. 전체 suite·320/1280 격리 화면 검증과 실제 서버 비활성 상태 근거는 수락 기록을 따른다. 실제 OAuth lifecycle의 브라우저 수락은 별도 gate다. 원복은 호환 코드와 신규 oauth.sqlite3를 보존한 기능 비활성이다. 새 사용자 자료·unknown receipt를 과거 backup으로 지우지 않는다. 8767/8700/원본R/프로필/launchd/STOP/quota를 변경하지 않는다.


## 중단·재시작 확인

갱신/원격 해지의 operation lease가 남으면 읽기·자격 상태를 불확실로 표시하고 수동 확인을 안내한다. GET은 DB·vault를 변경하거나 외부 작업을 재시도하지 않는다. 로컬 해제와 원격 권한 해지는 다르다.

강제 종료 후 명시 recovery의 stage journal·workspace/stage 소유 증명·공통 배타 잠금·전체 참조 graph·inspect/cleanup API와 CLI는 코드에 구현됐다. 임시 durable fake를 사용한 SIGKILL/reopen 집중 검증을 통과했으며, 최종 전체 회귀·확장 matrix·통합 수락 gate는 아직 대기다. 실제 Keychain·실 OAuth·운영 삭제·발행 수락과 구별한다. 기본 main에는 여전히 OAuth 서비스·vault·provider transport를 주입하지 않는다. 자세한 범위와 미실행 항목은 [crash recovery 수락 기록](../audits/2026-11-02-oauth-crash-recovery-acceptance.md)을 따른다.

관리 자격 projection은 operation_lease/명시 비활성 자격을 실행용 catalog에서 제외하도록 보완했다. 실행 어댑터를 연결할 때는 별도로 최신 snapshot/세대·scope·기한·permit 결속 resolver 검증이 필수다. 현재 관리 Connection.enabled는 false이며 실제 실행기로 자동 전달하지 않는다.


## 명시 recovery 사용 계약

아래 명령은 **사용법 예시이며 이번 구현에서 실제 실행하지 않았다.** 2026-11-02 승인은 격리 코드 구현에 한정된다. 실제 Keychain 읽기·쓰기·삭제, SNS 로그인, 운영 schema 전환과 발행은 포함하지 않는다.

`R`은 원본/source checkout, `W`는 **`oauth.sqlite3`를 직접 포함하는 OAuth 저장 디렉터리**다. `--workspace`에 R이나 이 개발 worktree 경로를 대신 넣지 않는다. CLI import가 가능한 호환 코드 checkout에서 실행하되 데이터 대상은 별도의 W로 지정한다. marker를 다른 W로 복사하거나 root 경로를 옮겨 재사용하면 root binding 검증에 실패한다. 자동 adoption·이식·key 재결속은 제공하지 않는다.

이미 명시 초기화된 W의 workspace ID만 확인하는 Python 예시는 다음과 같다. `load_workspace_owner`는 기존 marker를 검증하며 새 marker를 만들지 않는다. marker 전체에는 소유 key가 있으므로 `cat`하거나 로그에 복사하지 않는다. 이 예시는 ID만 출력하며 vault를 호출하지 않는다.

```bash
python3 -c 'import sys; from common.operations.oauth_workspace import load_workspace_owner; print(load_workspace_owner(sys.argv[1]).owner.workspace_id)' '/path/to/oauth-storage'
```

CLI는 `--workspace`, `--mode inspect|cleanup`, `--expected-workspace-id`를 필수로 받는다. 일반 CLI에는 backend가 기본 구성되지 않는다. 다음 형태는 `backend_required`, `status=blocked`, exit 2를 반환하며 Memory backend로 대체하지 않는다.

```bash
python3 -m common.operations.oauth_recovery --workspace '/path/to/oauth-storage' --mode inspect --expected-workspace-id '<검증한 workspace ID>'
```

실 Keychain 수락과 명시 실행 승인을 따로 마친 뒤에만 아래 `--keychain` 형태를 사용할 수 있다. 이 옵션은 lazy `SecurityFrameworkBridge`와 전용 scoped backend를 명시 구성하며 실제 후보 항목을 조회할 수 있다. 임의 module/env loader는 없다. 테스트의 `backend_factory` 주입은 격리 fake 검증용 Python API이고 production CLI 옵션이 아니다.

```bash
python3 -m common.operations.oauth_recovery --workspace '/path/to/oauth-storage' --mode inspect --expected-workspace-id '<검증한 workspace ID>' --keychain
python3 -m common.operations.oauth_recovery --workspace '/path/to/oauth-storage' --mode cleanup --expected-workspace-id '<검증한 workspace ID>' --expected-journal-revision '<inspect의 정수>' --expected-graph-revision '<inspect의 정수>' --keychain
```

`inspect`는 명시 관리 행위다. 공용 workspace guard를 잡고 후보의 소유 envelope/HMAC를 조회할 수 있지만 DB·vault 쓰기와 삭제는 0이다. guard lockfile은 생성될 수 있다. 일반 GET·생성자·재기동은 recovery를 호출하지 않는다. cleanup은 같은 owner와 inspect에서 관측한 **journal/graph 두 revision 모두**를 새 snapshot과 비교한다. stale이면 `revision_conflict`로 보존한다. 새 inspect 결과를 검토한 뒤 별도 명시 cleanup을 해야 하며 자동 재전송하지 않는다.

삭제 후보는 현 workspace의 journal에 등록된 `intent/stored/preserved` stage 중 operation이 확정 `unused`이고 remote state가 `local_only/not_started/returned`인 항목뿐이다. marker·journal·scoped 주소·인증 envelope의 owner/root/stage/ref 전체가 일치해야 한다. full graph의 attempt code/ticket/verifier/state_key/token, 모든 proposal, connection, lease old/new ref는 완료·만료·소비 여부와 무관하게 보호한다. pending/unknown receipt·operation·lease의 간접 참조도 보호한다. 알 수 없는 schema/ref/JSON, 끊긴 필수 관계, owner 오류는 전체 정리를 막는다. catalog에 안 보인다는 사실이나 기한·generation 크기로 unused를 추정하지 않는다.

cleanup은 전체 snapshot → 후보 exact 소유 증명 → 두 revision 재검증 → `delete_intent` → fresh graph → exact owned 삭제 → fresh graph → `deleted/absent` event와 journal 완료 순서로 진행한다. 모든 OAuth writer와 같은 guard를 유지하고 native I/O 동안 SQLite transaction은 닫는다. event만 추가하면 journal revision만 증가하며 graph는 그대로다. stage/참조 변경은 별도 graph revision을 증가시킨다. managed generation은 이 revision들과 별개이고 신규 stage까지 포함한 high-water를 보존한다.

legacy/unscoped 항목은 조회·열거·삭제·자동 envelope 변환하지 않는다. 과거 attempt/proposal과 이전 활성 자격의 직접 참조도 보존하므로 이 명령은 전체 orphan 회수를 보장하지 않는다. duplicate put 항목을 채택·덮어쓰지 않는다. denied/locked/unavailable/integrity 실패는 고정 reason으로 보존한다. `in_flight/unknown` 결과, pending receipt와 남은 lease는 재기동이나 시간 경과로 해제하지 않는다. provider refresh/revoke/exchange·OAuth request·발행을 재시도하지 않는다.

공개 JSON 필드는 `mode`, `status`, `journal_revision`, `graph_revision`, `stage_count`, `candidate_count`, `deleted_count`, `absent_count`, `preserved_count`, `already_deleted_count`, `legacy_protected_count`, `reason_counts`다. key/payload/ref/경로/원문 예외는 출력하지 않는다. `inspected/cleaned`는 exit 0, `blocked/partial`은 exit 2다. `cleaned`는 해당 journal 검사 완료이며 전체 회수나 실환경 readiness를 뜻하지 않는다. `candidate_count`는 실제 소유 증명을 시도한 수다. `deleted_count`는 backend 삭제와 metadata 완료까지 확인한 수이며 exact not-found는 `absent_count`로 구별한다. inspect의 `preserved_count`는 모든 nondeleted stage여서 absent와 겹칠 수 있고, cleanup에서는 미완료 stage 수다. 이미 deleted인 stage는 backend 재호출 없이 `already_deleted_count`로 집계한다. 삭제 뒤 journal 완료 전에 종료되면 다음 **명시** cleanup이 absent로 완료하며 과거 삭제 성공을 추정하지 않는다.

## schema 호환과 복구 보존

현재 코드는 schema1/2를 읽는다. schema2 전환은 이미 명시 초기화된 schema1 DB와 검증된 owner/context, held workspace guard 아래의 `migrate_to_owned_schema(context)`로만 수행한다. 일반 시작·GET·생성자·CLI는 marker 초기화나 migration을 수행하지 않는다. recovery HTTP route도 없다. schema1에 owned ref를 넣거나 unknown version을 허용하지 않는다.

향후 운영 전환 전에 W 전체의 일관된 백업을 별도로 확보해야 한다. DB만으로 scoped 자격이나 marker key가 복구되지 않으며 실제 Keychain 백업·복원과 root 재결속은 별도 수락 범위다. 호환 코드와 신규 DB/journal/receipt/lease를 보존한 채 기능을 비활성화하는 방식으로 원복한다. schema2를 읽지 못하는 구버전 binary로 내리거나 `user_version`을 수동으로 낮추지 않는다. 과거 백업으로 현재 W를 덮어 새 generation·credential·unknown operation/receipt를 지우지 않는다. 실패 자료와 백업을 분리 보존하고 필요한 복구를 검토한다. 초기 prototype schema2에 대한 idempotent migration은 owner 검증 뒤 무변경이며 예전 trigger를 자동 보정하지 않는다.
