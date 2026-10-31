# 계정 운영 실행 전환 절차 — 6A에서는 전환 금지

2026-10-31 현재 6A 코드 최종 재검토와 정적 배포를 마쳤고 일부 실제 UI를 확인했다. 기본 실행 정책은 비활성이고 production-ready 판정은 false다. 병행 Task8의 최신 전체 검증 대기로 현재 전체 작업 사본 offline-ready도 false다. 이 문서는 이후 작업별 전환 체크포인트의 조건을 기록한다. 문서대로 읽는 것만으로 운영 등록부 변경·launchd 재등록·실계정 로그인·발행·백업 복원 권한이 생기지 않는다.

## 현재 확인과 판단

고정 W의 등록부와 진입점 목록을 읽고 필요한 증거를 분리한다. `common.operations.cutover.assess_cutover`와 `common.tools.check_operations_release.check_release`는 조회·분류만 하고 운영 owner·큐·STOP·파일을 변경하지 않는다. 실제처럼 생긴 URL/ID 또는 `trusted=true` 자체 선언은 실증거가 아니다.

최종 전체 검증 후에 생성할 비밀 없는 evidence 파일은 다음 항목을 각각 가진다.

- code_revision, test_results, connection_matrix
- entrypoint_inventory_hash, crosspost_baseline_hash
- producer_policy_evidence, adapter_transport_evidence
- live_auth_evidence, live_publish_evidence, rollback_evidence

connection_matrix는 블로그 5개와 YouTube 2개의 구현·transport fixture·순수 검사·실인증·실발행·공개·내용·성과·후처리를 분리한다. 비어 있는 live 증거는 미확인이다. fixture/실자료를 같은 통과 칸에 합치지 않는다.

부모가 허용한 로컬 evidence를 `/private/tmp/phase6a-offline-evidence.json`에 갱신했다. 실제 Python872·이전Node195·후속집중20·HTTP78과 최신 전체 Node 대기를 구분한다. code_revision은 생성 시점9295a54819e23bd7b8fd7f72eccd9bce34f4489f이며 release CLI는 exit1/offline_ready=false/production_ready=false다. 이전 Node 결과를 이후 수정까지 포함한 전체 통과로 바꾸지 않는다. 분류기 단위시험의 임시 입력,6A 정적 배포 근거, 전체 작업 사본의 최종 검증을 구분한다.

## 작업 하나의 전환 전 조건

1. 원본 소유 계정과 실제 게시 대상 계정을 불변 ID로 확인한다. 표시명·이메일·제목·URL로 대상을 추정하지 않는다. 대상이 미확인이면 needs_auth/needs_review로 닫는다.
2. console·launchd·direct CLI·내부 함수·큐 add·후처리·예약 공개 전환까지 해당 작업의 모든 caller/leaf를 목록화한다. 하나라도 미분리/미등록/legacy side effect가 남으면 owner를 바꾸지 않는다. inventory의 summary 한 행만 true로 바꾸어 우회하지 않는다.
3. 원본 콘텐츠/버전·출처 bytes·제작 unit·독립 검산/출처 검토를 확인한다. 제작 완료·계획 승인·발행 승인은 별도다. 구독-only 제한을 제작/검토 내부 API로 우회하지 않는다.
4. 순수 prepare/inspect에 원격 쓰기·draft/editor 입력·media container 생성·공개 전환이 없는지 검증한다. permit 전에 공개 버튼만 제외하고 다른 쓰기를 허용하지 않는다.
5. 대상별 최신 원문·승인 hash·실인증·예약 조건·프로필 잠금·quota가 맞을 때만 일회성 permit을 발급한다. 승인된 대상의 submit 1회, 다른 계정 키/프로필 접근 0을 입증한다.
6. 원격 수락 뒤 응답 유실/DB 기록 실패는 unknown으로 남긴다. 재시작은 조회가 먼저다. 원격 ID·대상·시간·본문·매체를 결속한 뒤만 해소하고 원본이나 성공한 형제를 재전송하지 않는다.
7. 재난 예약·upload 응답은 공개 verified가 아니다. legacy shared_unconfirmed도 내용 검증 완료가 아니다. 썸네일·playlist·comment·caption·public switch·TikTok은 별도 승인/완료 근거를 가진다.
8. 23개 경로의 조건·슬롯·원본/대상 귀속·변환·AI/태그·delay 책임·disabled/unknown 상태와 기존 승인/자동 진행 수준을 비교한다. 미확인을 활성으로 보정하지 않는다.

6A는 기존 TikTok 큐를 유지한다. 기존 순수 큐/실패 AST 계약과 관리 preview/시각/intent 차단을 검증했으나 관리 TikTok adapter/selector, 전체 23경로 전환은 6B 필수 잔여다. 이 조건을 삭제해 6A를 운영 전환 완료로 만들지 않는다.

## 실행 잠금과 STOP

실제 로그인 프로필을 열거나 발행하는 작업은 저장소 `shared/axlock.py` 경유가 필수다. 기존 wrapper 첫 잠금 줄을 보존한다. 같은 학과/개인 계정의 profile 별칭은 같은 자원으로 정규화하며 사용자의 로그인 브라우저 점유를 존중한다. 입구·잠금 대기·획득 직후·각 외부 쓰기 직전에 전역 STOP을 확인한다. 계정 프로필 잠금은 실제 원격 작업이 끝날 때까지 유지한다. 공개 승인 관문과 원장 DB transaction은 원격 네트워크 대기 동안 붙잡지 않는다.

본 문서 작성과 fixture 검증에서는 운영 프로필을 열지 않았다. 실제 전환 체크포인트에서도 비상 정지 중에는 새 발행을 시작하지 않는다.

## 보존형 롤백과 복구

이전 DB 파일을 덮어쓰고 legacy wrapper를 다시 켜는 방식은 새 원격 게시를 잊어 중복을 만들 수 있다. 새 remote ID·URL·unknown·request_started attempt·quota reservation/production unit·승인·요청 receipt·불변 콘텐츠를 먼저 보존해야 한다.

분류기에 허용하는 rollback 선언은 `strategy=forward_preserving_ledger`, `preserve_remote_ids=true`, `preserve_unknown=true`, `preserve_quota=true`, `resume_legacy=false`다. 이것은 실제 복원 시험의 통과를 대신하지 않는다. restore_test, 복구 전후 모든 신규 이력 대조, 중복 submit 0, unknown/quota hold 유지 증거가 별도로 필요하다. 현재 snapshot hash만으로 실제 원격 이력 보존을 인증하지 않는다.

운영 체크포인트에서 소유 worker를 drain한 뒤 SQLite backup API와 콘텐츠/성과 자료를 함께 보존한다. 복원안은 별도 임시 위치에 적용하고 업데이트 뒤 추가된 원격·로컬 이력과 receipt를 비교한다. 살아 있는 운영 DB 덮어쓰기·원격 삭제·대기열 시도 초기화·일괄 retry·자동 legacy 재개를 제공하지 않는다. 정적 배포 전 quiesced backup은 완료했지만 실제 복원 시험은 아직 실행하지 않았다.

## 기록할 최종 결과

6A 코드 최종 수정8954516/독립 재검토 Approved, 테스트 프로필 격리88ff634/PASS, 기존 Pillow Python3.12 전체872개 OK(102.148초, session1429 exit0)를 확인했다. Python3.15의 프로필 대기 중단130은 성공이 아니다. 이전 전체 Node195 pass와 이후 Task6 집중20 pass는 별도로 기록하며, Task8 마지막 코드 뒤 전체 Python/Node를 한 번 실행할 때 최종 evidence를 재산출한다. 현재 CLI는 최신 전체 검증 미완료로 offlinefalse, 실제 운영 증거 미완료로 productionfalse다.

부모가 원PID13057/13063을 확인·정지하고 만든 quiesced backup은 `ax-console/data/deployment-backups/phase6a-quiesced-20261031T012252315404Z`다. manifest6개를 실제 W에 적용해 actual==HEAD를 확인했으며 새8769/8767 세션은57014/61922다. 사용자8769에서 기술사 메뉴·건축 필터·실자료를 확인했으나 발행 service는 미주입/비활성이다. 기존 operations26테이블 행수0 동일·schema3·추가8empty·integrityok, metrics논리동일·schema1·integrityok라는 부모 DB 대조를 보존한다. 실제 복원/원격 이력 보존 수락은 별도다.

최신 격리 승인·unknown·inputv1/outputv2·Escape/포커스·실제 planCAS409 입력보존 근거와 최신401/503·320px·전체복구closure 미확인은 [수락 현황](../audits/2026-10-30-web-phase6a-acceptance.md)에 구분했다. 후속Task8은 지금 배포된 actual==HEAD를 새 original로 삼고 옛6A manifest 원본hash를 재적용하지 않는다. 원래 계획 작업공간은 참조가 남아 있으므로 삭제하지 않는다.

실제 구독 실행·독립 검토·음성/영상 장면·PDF safe parser/렌더·출처 bytes·실계정·공식 API/DOM·후처리·외부 접속까지 후속 수락한다. Mac과 휴대폰 외부 접속은 사용자 선택의 최종 요구로 유지한다. localhost 검증으로 대체하지 않는다.

연결 문서: [결정·보류 원문 보존](../audits/2026-10-31-phase6a-rulings.md), [6A 수락 현황](../audits/2026-10-30-web-phase6a-acceptance.md), [진입점 근거](execution-entrypoint-inventory.json), [실행 경계 감사](../audits/2026-10-30-live-entrypoint-readiness.md), [운영 웹 사용법](../../ax-console/docs/운영웹_사용법.md).
