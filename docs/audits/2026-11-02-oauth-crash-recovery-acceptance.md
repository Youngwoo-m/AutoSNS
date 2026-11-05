# OAuth crash recovery 격리 구현 수락 기록

2026-11-02 작성. **전체 회귀 통과·최종 독립 검토 대기**이다. [승인 계획](../superpowers/plans/2026-11-01-oauth-crash-recovery.md)에 따라 workspace 소유 증명, durable journal, 전체 참조 graph, 공용 writer/recovery guard, owned 서비스 경로와 명시 inspect/cleanup을 구현했다. 이 기록은 개발 worktree W의 코드·임시 fixture 검증 범위다. 운영 원본 R이나 운영 OAuth 저장 디렉터리에 적용했다는 뜻이 아니다. CLI의 `--workspace`는 `oauth.sqlite3`를 직접 포함하는 저장 디렉터리를 가리키며 source checkout과 구별한다.

사용자는 2026-11-02 격리 코드 구현을 승인했다. 실제 Keychain 접근·OS 권한 부여·SNS 로그인·운영 자격 삭제·운영 migration·발행은 실행 범위에 포함하지 않는다. 이 문서 작성 과정에서도 해당 실행은 하지 않았다. 명령 예시와 복구 보존 절차는 [운영 안내](../runbooks/oauth-connections.md)에 있다.

## readiness 판정

|단계|현재 판정|의미와 남은 조건|
|---|---|---|
|`code_ready`|전체 회귀 통과, 최종 독립 검토 대기|Task별 검토와 Python1180·Node252 전체 회귀를 확보했다. 최종 검토 전 완료 판정하지 않는다.|
|`isolated_recovery_verified`|19 SIGKILL·owned HTTP·전체 회귀 통과|임시 SQLite/durable fake 검증이다. 실 Keychain/OS 재시작 수락은 아니다.|
|`real_keychain_accepted`|미실행·미수락|실 SecurityFramework exact query, 접근권한, 실제 OS 재시작·복원은 검증하지 않았다.|
|`real_oauth_ready`|false|기본 main의 OAuth 서비스·vault·provider transport는 None이다. 실 앱 등록·callback·동의·실 provider lifecycle을 활성화하지 않았다.|
|`live_publish_ready`|false|실행 어댑터/permit 결속과 실발행 수락을 이 작업으로 충족하지 않는다.|

서비스 DI는 `workspace_context/stage_store/owned_backend`가 모두 주입되고 canonical root·owner가 일치할 때만 owned 경로를 사용한다. 생성자·일반 GET·서버 재기동에는 초기화/migration/cleanup을 연결하지 않았다. recovery HTTP route와 main 자동 주입도 없다. CLI는 명시 `--keychain`이 없으면 `backend_required/blocked`이며 Memory fallback이 없다. fake 검증의 통과로 실제 자격 저장소 사용을 자동 승인하지 않는다.

## 단계별 증거

아래 결과는 서로 다른 코드 단계·시험 묶음이다. 겹치는 시험을 합산해 고유 시험 수나 최종 branch의 전체 통과 수로 표시하지 않는다. 이 문서 작성자는 시험을 재실행하지 않았으며 실행·검토 보고를 근거로 기록했다.

|증거 단계|확인된 결과|범위와 한계|
|---|---|---|
|Task1 소유 primitive|신규17 + 기존 backend10 PASS|[구현](../../.superpowers/sdd/2026-11-01-oauth-crash-recovery/task1-report.md), [독립 검토](../../.superpowers/sdd/2026-11-01-oauth-crash-recovery/task1-review.md). marker·codec·scoped HMAC·legacy 보존이며 전체 삭제 권한 판정과 다르다.|
|Task3 guard 수정|guard19 + marker5 PASS|[구현](../../.superpowers/sdd/2026-11-01-oauth-crash-recovery/task3-core-report.md), [재검토](../../.superpowers/sdd/2026-11-01-oauth-crash-recovery/task3-core-rereview1.md). fork/fd 경합 수정 포함.|
|부모의 앞선 store/guard 단계|174 unit + 23 HTTP PASS|[진행 근거](../../.superpowers/sdd/2026-11-01-oauth-crash-recovery/progress.md)의 Task2 fix round1 시점이다. 이후 owned service/cleanup 변경을 포함한 최종 전체 결과가 아니다.|
|부모의 service 집중 단계|69 service PASS|owned21 + 기존 service48의 부모 집중 검증 근거다. [서비스 보고](../../.superpowers/sdd/2026-11-01-oauth-crash-recovery/task4-service-report.md)의 더 넓은 143개 묶음과 중복 합산하지 않는다. [서비스 독립 검토](../../.superpowers/sdd/2026-11-01-oauth-crash-recovery/task4-service-review.md)는 owned21을 직접 통과 확인했다.|
|Task2 event counter 정정 후|75 PASS, skip0, warnings0|[Fix round2](../../.superpowers/sdd/2026-11-01-oauth-crash-recovery/task2-report.md)는 stage43 + 기존32다. [재검토2 PASS](../../.superpowers/sdd/2026-11-01-oauth-crash-recovery/task2-rereview2.md)는 새 회귀1 직접 실행과 event INSERT/UPDATE/DELETE probe로 journal+1/graph0 계약을 확인했다.|
|부모의 cleanup/process consumer 단계|38 PASS, skip0, exit0|31 cleanup + 7 process integration. [matrix 보고](../../.superpowers/sdd/2026-11-01-oauth-crash-recovery/task5-matrix-report.md)에 부모 실행 `/private/tmp/oauth-recovery-consumer.log`, `Ran 38 tests in 15.451s / OK`를 기록했다. [cleanup 검토](../../.superpowers/sdd/2026-11-01-oauth-crash-recovery/task4-cleanup-review.md)와 [matrix 검토](../../.superpowers/sdd/2026-11-01-oauth-crash-recovery/task5-matrix-review.md)는 각각의 범위 PASS다.|

cleanup 구현 보고의 31개 RED는 당시 event INSERT가 graph까지 증가하던 생산자 계약 불일치의 이력이다. Task2 Fix round2가 event-only trigger를 정정했고 뒤의 부모 consumer38과 cleanup 독립검토31이 PASS했다. 이 이력을 현재 미해결 실패나 최종 전체 수락으로 각각 오인하지 않는다. 새 schema1→2 생성 경로를 정정했으며 이미 존재하는 prototype schema2를 자동 보정한 결과는 아니다.

## 실제 종료 검증과 보존 범위

최종 process matrix는 **8 unittest 안의 19개 SIGKILL 경계**와 namespace 격리 사례다. 기존 16개에 proposal commit 전·후와 mark_deleted commit 직후를 추가했고, before_intent는 실제 INSERT 후 commit 직전으로 강화했다. callback의 새 code 부재/정확 bytes도 직접 단언한다. 별도 spawn 자식을 실제 kill하고 `-SIGKILL`을 확인한 뒤 새 객체로 reopen했다. 정상 예외 주입을 process crash로 세지 않았다. raw/provider 호출 계수는 OAuth DB 바깥 durable SQLite에 commit하며 키·payload·ref를 출력하지 않는다.

검증은 임시 `oauth-crash-fixture-` durable fake 경로에서만 수행됐다. pointer/generation/lease/receipt와 기존 활성·역사 자격 보존, same-key pending 재요청의 remote 추가호출0, reopen/GET의 DB bytes/revision·backend/provider/guard 호출 불변, exact delete 후 journal 기록 전 종료의 absent 완료, 중복 cleanup 무쓰기를 확인했다. 모든 remote/native 경계에서 workspace guard 보유와 SQLite write transaction 비유지를 검사했다. 실제 OS Keychain이나 OS 자체 재시작의 수락 증거는 아니다.

삭제 허가는 journal 존재만으로 성립하지 않는다. 현 owner/root/stage/ref에 결속한 scoped 주소·HMAC, 확정 unused operation, fresh full graph와 두 revision 재검증을 모두 요구한다. 직접·간접 active/pending/unknown 참조, 과거 attempt/proposal 및 lease old/new ref와 legacy는 보존한다. full graph의 unknown schema/ref/JSON·필수 관계 오류는 전체 차단한다. backend namespace 열거, legacy 자동 wrap/이식/삭제, generation/기한에 따른 후보 추정, receipt 재전송, lease 자동 해제는 제공하지 않는다.

## 최종 gate — 결과 미기록 항목

다음 항목은 **이 문서 기준 아직 실행·결과를 확인하지 않은 대기 항목**이다. 완료 수·시험 수·PASS를 추정해 채우지 않는다. 부모가 실제 로그와 최종 검토를 확보한 뒤 이 절을 갱신한다.

|대기 gate|현재 상태|추가할 증거|
|---|---|---|
|확장 process matrix|최신 확장 결과 미기록|journal 전후·proposal CAS 전후·journal deleted 완료 뒤 경계와 callback 신규 payload 직접 단언의 실제 실행/검토 결과. 현재 승인된 16경계 수와 구별해 최종 경계 수를 기록한다.|
|owned HTTP/factory/main 순수성|확장 실행 결과 미기록|owned 주입 경로의 HTTP 검증, 기본 main None, GET/constructor의 marker/journal/migration/native/provider0 단언. 앞선 23 HTTP로 대신하지 않는다.|
|최종 영향 범위 전체 회귀|미실행 결과 대기|최종 코드의 실제 명령·수·skip·exit·로그. 단계별 PASS의 단순 합산 금지.|
|최종 whole-branch 독립 검토|미실행 결과 대기|소유 증명·graph 누락·TOCTOU·duplicate·writer 경합과 확장 시험 포함 판정, 미해결 지적 여부. Task별 PASS로 대신하지 않는다.|

## 백업·실패 보존

운영 schema 전환은 실행하지 않았다. 향후 별도 전환 시 OAuth W 전체를 일관되게 백업하고 marker/key와 scoped 자격 복구 가능성을 별도로 수락해야 한다. 현재 schema1/2 호환 코드를 유지하며 schema2를 구버전 binary 또는 수동 user_version 변경으로 내리지 않는다. 원복은 새 DB/journal/unknown receipt/lease를 보존한 기능 비활성으로 수행한다. 과거 백업을 현재 W에 덮어 신규 자격이나 결과불명 상태를 지우는 자동 복원은 금지한다. workspace 물리 이행·root 재결속·실 Keychain 백업/복원은 이 격리 구현의 수락 범위 밖이다.


## 부모의 최종 전체 회귀 — 2026-11-02

- Python: `PYTHONDONTWRITEBYTECODE=1 /Volumes/USB256/devAPP/AutoSNS/personal/claude-jobs/.venv/bin/python -m unittest discover -s tests -t .` → **1,180개 OK**, 137.506초, 실패·skip0, exit0. 기존 Pillow Python3.12 환경 사용. 로그 `/private/tmp/oauth-recovery-full-python.log`.
- Node: `node --test tests/*.test.mjs tests/test_*.mjs` → **252개 PASS**, 실패·취소·skip0, exit0. 로그 `/private/tmp/oauth-recovery-full-node.log`.
- 확장 matrix 작성자 실행8개/11.423초/OK, 실제 SIGKILL19경계. scoped 독립검토는 변경된4개명명시험과 HTTP 핵심3개를 직접 통과 확인했다. owned HTTP 작성자7개/4.580초/OK 및 discovery7개(중복없음). 이 수치를 전체 회귀 수에 더하지 않는다.
- 실제 Keychain·계정·외부 API·운영 삭제·migration·발행0. 최종whole-branch검토는 이 시점 대기이며 결과를 받은 뒤 readiness를 갱신한다.
