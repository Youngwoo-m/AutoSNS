# 독립 검토 실행 계약

`run_reviews(snapshot, *, producer, authorities, runner, runtime_store, now) -> dict`는 지정 revision의 실제 ContentStore 원본과 hash·자산 bytes를 확인하고 calc→source 순서로 실행한다. source는 항상 필수이며 `authorities['require_calc_review']=True`이면 calc도 필수다. `authorities['review_authorities']`는 기존 gate와 같은 `{principal_id: ['calc'|'source', ...]}` 서버 정책이다. `fix_cycles`는 서버가 보존한 수정 회차다. 2회 이상이면 자동 검토를 진행하지 않고 `blocked/fix_cycle_limit`로 남긴다.

producer는 서버 생성 `{principal_id, execution_id}`다. 모델 결과로 producer를 지정하지 않는다. 생산자와 각 reviewer의 principal 및 provider execution은 모두 달라야 한다. 서버가 `RegisteredReviewRunner(providers, source_checker=..., calculation_runner=...)`를 만든다. providers는 principal별 callable registry다. HTTP 요청으로 authorities, checker, 계산 결과 또는 `{available,checked}`를 등록하는 경로를 두지 않는다.

source_checker(snapshot)와 calculation_runner(snapshot)는 서버가 실제 근거 조회/제한 계산을 수행한 뒤 `{available:True, checked:True, ...}`를 반환한다. 미등록·실행불가·오류는 `unclear`다. 이를 provider의 pass로 덮지 않는다. `calculate_registered_inputs`는 서버 입력의 add/subtract/multiply/divide·operands·expected·tolerance·unit schema만 계산한다. 모델 코드, Python 표현식, 셸 또는 임의 네트워크 주소를 실행하지 않는다. 실제 결과가 expected와 다르면 provider pass도 fix로 남긴다.

등록 provider는 `provider(role=..., snapshot=콘텐츠허용필드, evidence=서버도구근거, execution_id=새서버ID)`로 호출한다. 결과 JSON은 verdict(pass/fix/unclear), findings?만 허용한다. principal_id/reviewer_id/execution_id/report_hash/content_revision/checked_at 등을 자체 주장하면 unclear다. snapshot에서 connection_id/credential_ref/permit/asset_bytes 등 발행 capability를 제거한다. 원고·소유자·자산 목록이 서버 manifest 원본과 다르면 시작하지 않는다.

`SubscriptionReviewProvider(provider, request=서버ProductionRequest, policy=서버ProviderPolicy)`를 registry에 등록하면 A4의 `generate(request,prompt,policy)`를 매번 실제 새 호출한다. required_outputs는 text인 서버 review request를 사용한다. provider envelope의 실제 서버 execution_id와 모델이 작성한 text JSON을 분리한다. 실제 실행 ID를 유지하고 생산자/다른 검토와 중복이면 거부한다. capability 미확인 또는 unavailable provider는 실제 reviewer 실행 증거로 기록하지 않는다. 서버에서 principal별 독립 등록 주체를 확인해야 하며 같은 모델의 자체 신원 주장은 그 증거가 아니다.

완료 반환은 `{status:'completed', reason_code:None, producer, reports, outcomes}`다. fix 또는 unclear는 blocked다. 보고서는 publication_gate가 요구하는 9필드(role, reviewer_id, execution_id, content_id, content_revision, manifest_hash, verdict, checked_at, report_hash)로 서버가 만들고 `report_hash`를 계산한다. `RuntimeStore.record_content_evidence`의 현재 호출 계약으로 production_provenance 및 실제 실행한 independent_review를 저장한다. 별도 임의 검토 DB를 만들지 않는다. 도구/공급자가 실행되지 않은 역할은 outcomes=unclear이며 reviewer report를 지어내지 않는다.

보고서의 manifest/revision은 불변이다. 원고나 자산 변경은 새 revision 뒤 새 검토를 요구한다. 이전 pass를 새 revision에 이월하지 않는다. 검토 함수는 원고를 자동 수정하거나 발행 승인으로 바꾸지 않는다. 실제 운영 reviewer, 근거조회·계산 runner, CLI capability는 기본 등록하지 않는다. 테스트 fixture의 검토/렌더 기록은 임시 DB에만 있으며 실제 사람·운영 reviewer가 수행한 기록이 아니다.
