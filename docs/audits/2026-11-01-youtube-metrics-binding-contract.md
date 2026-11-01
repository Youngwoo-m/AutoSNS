# 검증된 YouTube 게시 1건의 성과 → 다음 기획 결속 계약

작성일: 2026-11-01. [다음 산출물 3번](2026-11-01-sns-next-deliverables.md#3-검증된-게시물-하나의-실제-성과를-다음-기획까지-연결하는-collector)의 구현 접합부를 현재 소스와 대조한 문서다. 구현·설계 승인·실수집·실계정 수락 기록이 아니다. 복구 계획의 수락 여부와 독립적으로 읽을 수 있는 계약 조사이며, 해당 선행조건을 해제하지 않는다. 코드는 읽기만 했고 설정·운영 데이터·키는 읽거나 변경하지 않았다. 외부 API·브라우저·native·발행·시험·커밋은 실행하지 않았다. 아래 신규 인터페이스는 모두 제안이다.

## 현재 재사용할 정확한 API

|파일·현재 API|이미 보장하는 것|추가 구현이 필요한 경계|
|---|---|---|
|`common/operations/metrics.py`: `build_metrics_context(runtime_store, delivery_id, registry) -> MetricsContext`|verified 상태, remote ID 존재·불확실성 없음, connection의 target/destination 일치, 등록된 owner/destination, 공개 verification 이벤트의 remote/target/destination 및 검증시각, content ID/revision/manifest 확인|현재 자격 상태·generation·scope·비용/할당량·provider 응답의 실제 채널은 확인하지 않음|
|같은 파일: `collect_delivery_metrics(ctx, remote_id, collector) -> MetricResult`|서버 주입 callable `collector(ctx, remote_id)` 호출. None은 `collection.unsupported`, 예외는 `collection.error`. remote/target 불일치 거부. 서버가 새 collection ID·완료시각 부여|매 호출 새 시도이며 요청 중복 선점/조회 API 없음. `source`를 항상 `{}`로 지우므로 provider reason·missing 근거를 여기에 넣어 보존할 수 없음|
|같은 파일: `record_metrics(store, delivery_id, result, *, runtime_store=None, registry=None, observation_key=None)`|저장 직전 context 재구성. source는 서버 소유 revision/manifest/verified_at/collection_key/result_fingerprint만 저장. owner와 destination을 별도 유지|수집 전후 context 변경은 명시 비교 필요. 저장 시점의 context를 재구성하는 것만으로 수집 당시 revision/manifest가 같았음을 보장하지 않음|
|`common/operations/metrics_store.py`: `append_collection(observation, observation_key)`|명시 initialize 후 append-only 원자 비교. 동일 키·동일 payload는 기존 ID, 다르면 ConflictError. 직접 record가 만든 저장시각만 최초 값으로 보존|원격 호출 전 request 영수증·진행 상태·재시작 복구 없음. 다른 collection ID/완료시각을 가진 재수집 결과는 동일 observation key에서 충돌|
|같은 파일: `save_proposal(account_id, observation_ids, title, note, request_key)`|1~100개 중복 없는 ID, 각 observation의 owner 또는 destination에 속하는 계정만 허용. request key 동일 payload 재전송은 기존 draft 반환|verified/ok/fresh만 선택하는 정책은 없음. legacy·실패 관측도 계정 조건에 맞으면 참조 가능. 콘텐츠/승인 생성 기능 없음|
|`common/operations/metrics_models.py`: `MetricResult(status, values, observed_at, remote_id, target_id, definition_id, basis='unknown', period=None, source={}, collection_id=None, collected_at=None)`|status는 `ok/error/unsupported`, values는 유한 숫자만. ok는 관측시각·ID 필수. interval은 start/end/timezone 필수, lifetime/unknown은 period 없음. collection ID·완료시각은 쌍|`stale`, `partial`, values의 null은 현재 표현 불가. error/unsupported values는 강제로 비움. 부분 누락의 명시 근거도 없음|
|`common/operations/metrics_normalization.py`: `normalize_metric_row(row) -> MetricResult`|수동 CSV 한 count 행의 정수·음수·기간·시각 검증. `manual.csv.<platform>.<metric>.v1` 정의|YouTube 응답 정규화가 아니며 API 실측 정의로 재사용 불가|
|`common/publishers/youtube_services.py`: `GoogleYoutubeServices(service, *, media_factory, clock=None)`의 `inspect(target)`, `read_video(target, remote_id)`|inspect는 channels의 단일 mine ID와 target/expected_login_subject 일치 검사. read_video는 inspect 후 videos 한 건 조회|read_video의 part는 `snippet,status,contentDetails,processingDetails`로 statistics 없음. 반환 ID·채널의 최종 통계 결속은 별도 필요. 통계 읽기에서 submit/lookup을 호출할 이유 없음|
|같은 파일: `create_youtube_services(connection_id, credentials, *, media_loader)`|자격을 주입받아 dept.youtube/personal.youtube 서비스 조립. import 자체 외부 I/O 없음|통계 전용 조립에 미디어 로더/발행 factory를 강제하지 않는 읽기 factory 필요. legacy 토큰 resolver를 통계 collector에서 직접 호출하지 않음|
|`ax-console/app/web_metrics.py`: `handle(store, method, path, query, read_body, *, source_root, registry)`|GET `/api/v2/metrics`, GET `/import-preview`, POST `/import`, POST `/proposals`. 요청 필드 정확 일치·request key 검사, 관측 provenance allowlist 출력|수집 endpoint/collector/runtime 주입 없음. snapshot의 `collection_enabled=False`, support는 unregistered/unknown/not_collected 고정이므로 등록 사실에 따른 상태 표시 추가 필요|

`ax-console/app/web_server.py`는 인증 뒤 `handle_metrics(...)`에 store·source_root·`metrics_registry()`만 전달한다. 이 호출과 서버 factory의 주입 경계까지 연결해야 콘솔에서 실제 수집 명령이 도달한다. 기존 GET가 서비스 생성·자격 접근·원격 조회를 시작하게 바꾸지 않는다.

## 한 번의 명시 수집 흐름

1. 제안 POST `/api/v2/metrics/collect`는 정확히 `{delivery_id, request_key}`만 받는다. remote ID·target·account·connection·revision·수치·credentials는 클라이언트가 지정하지 않는다. 기존 인증/JSON 한도/저장 가능 여부 검사를 재사용한다. GET는 계속 원격 호출 0회다.
2. `build_metrics_context`로 서버 원장에서 context를 고정한다. youtube만 허용하고 비활성/미주입은 명시 거부 또는 unsupported 상태로 반환한다. verified delivery가 없으면 legacy ID를 승격하지 않는다.
3. 서버 수집 서비스가 request key와 정규화한 요청 payload를 원자 선점한다. 완료 영수증이 있으면 원격 호출 없이 같은 결과를 반환하고, 다른 delivery에 재사용한 키는 충돌시킨다. 미완료/동시 요청은 진행중으로 반환한다. 원격 읽기 후 프로세스 종료로 결과가 미저장된 경우 자동 새 수집으로 숨기지 않고 미완료 상태로 남긴다. 이후 새 명시 요청은 새 key를 사용한다.
4. [다음 산출물 1번](2026-11-01-sns-next-deliverables.md#1-oauth-연결을-기존-publisher가-사용할-수-있게-하는-운영-조립-패키지)의 resolver 경계에서 정확한 destination/connection/generation/불변 target, 관측된 읽기 scope·만료·자격 상태와 명시 비용/할당량 정책을 검사한다. 통계 조회는 읽기 작업이며 공개 permit을 소비하거나 발행을 호출하지 않는다. 숨은 refresh·legacy fallback·전체 채널 collector는 금지한다. 실제 자격 사용에는 복구 선행조건이 그대로 적용된다.
5. 통계 서비스는 로그인 주체를 target과 대조한 후 **해당 remote ID 한 건**을 조회한다. 제안 part는 `snippet,status,statistics`이며 반환 items가 정확히 한 건이고 `id == ctx.remote_id`, `snippet.channelId == ctx.target_id`인 경우만 수치 정규화로 넘긴다. public 여부도 현재 응답에서 확인한다. 사라짐/비공개/다른 채널/빈 응답은 성공 0이 아니다. 추가 channel inspection 호출도 할당량 정책에 포함한다. 정책 확인 없이 고정 무료/잔량을 추정하지 않는다.
6. 서버 시계로 조회 완료의 관측시각을 기록한다. YouTube 응답에 별도 실제 집계 기준시각이 없다면 이를 응답 수신시각으로 명확히 정의하고 데이터 최신성 보장으로 표현하지 않는다. collect 경계의 collected_at은 서버 수집 완료시각이다. 공개/업로드 시각을 observed_at으로 쓰지 않는다.
7. 수집 직후 context를 다시 구성해 고정한 context 전체와 대조한다. 결속이 바뀌면 새 대상에 결과를 옮겨 기록하지 않는다. `record_metrics(..., observation_key=<서버 namespace 요청 키>)`에서 다시 원장을 검증한 뒤 관측·request 영수증을 원자 완료한다. 원자 완료 구현이 없다면 관측 저장 성공/영수증 유실의 복구 전략을 별도로 구현해야 한다.
8. 응답은 저장 observation ID와 허용된 public 관측만 반환한다. 해당 ID를 선택한 별도 제안 저장에서 `save_proposal`을 호출한다. 수집 자체가 제안·원고·승인·예약·발행을 자동 실행하지 않는다.

기존 `record_metrics(..., observation_key=request_key)` 호출만 추가해서는 3번을 충족하지 못한다. 같은 POST를 다시 collect하면 새 collection_id/collected_at이 fingerprint에 들어가 저장 충돌과 두 번째 API 호출이 생긴다. `append_collection`의 멱등은 **같은 수집 결과의 재저장**에 해당하며 **같은 명령의 재실행 방지**와 구별해야 한다.

## 최소 추가 인터페이스와 파일 소유

|파일|다음 구현에 필요한 최소 계약(신규 이름은 제안)|
|---|---|
|`common/publishers/youtube_services.py`|`read_video_statistics(target, remote_id)`와 읽기 조립 경계. 명시 ID/채널/public 대조, 제한된 응답만 collector에 전달. inspect/read만 허용하며 원본 provider 응답·예외 문자열은 HTTP/원장에 저장하지 않음|
|신규 `common/operations/youtube_metrics.py`|서버 주입 서비스/resolver/policy/clock으로 collector factory 작성. 반환 callable은 기존 `(ctx, remote_id) -> MetricResult` 계약 유지. 요청/수집 결속을 확인한 뒤 순수 `normalize_youtube_statistics(raw, *, remote_id, target_id, observed_at)` 호출. 정의는 먼저 `youtube.views`/lifetime/`views` 1종으로 제한하면 기존 기획 집계 정의를 재사용 가능. likes/comments를 함께 도입하면 별도 정의·누락 정책·집계 허용 계약도 등록|
|`common/operations/metrics_models.py`, `metrics.py`|누락·stale 근거의 서버 소유 표현을 결정하고 모델 검증·수집·저장까지 보존. 최소 첫 구현은 viewCount 누락/비정상일 때 error+빈 values, 실제 문자열 `"0"`만 0으로 저장. null을 값으로 보존해야 한다면 명시 nullable/availability 필드를 추가하고 모든 소비자를 함께 변경. source 임의 전달 복구로 해결하지 않음|
|`common/operations/metrics_store.py`, `metrics.py`|수집 request 조회/원자 선점/완료 영수증 API 추가. key는 범위가 고정된 서버 namespace 사용. 완료된 동일 요청을 조회할 때 기존 public observation 반환. 저장 재검증·payload 충돌·append-only 유지. 진행/미완료 상태와 재기동 정책 명시|
|`ax-console/app/web_metrics.py`, `web_server.py`|`/collect` 인식과 서버 수집 서비스 주입. 기본 비활성, 등록/자격/정책 상태를 과장 없이 표시. GET 수집 금지 유지. HTTP 에러는 고정 코드로 한정하고 비밀·provider 원문 노출 금지|
|`common/operations/planning_context.py` 및 기존 제안 UI 연결부|기존 observation ID·latest_status·previous_success ID를 그대로 다음 기획 근거에 연결. freshness/누락을 실제 모델 계약에 맞게 표시. 임의 기존 성공을 현재 성공으로 승격하지 않음. 제안 저장 API는 기존 것을 재사용|

모든 파일을 동시에 바꾸는 대규모 재작성은 필요 없다. 1차 정의를 조회수 한 종류로 고정하면 통계 조회·정규화·request 영수증·서버 POST·기존 제안 연결이 최소 구현 단위다. 단, null/stale을 지원한다고 표시하려면 모델/저장/HTTP/기획 소비자까지 실제 표현이 이어져야 한다.

## 다음 기획의 evidence 연결

이미 존재하는 `build_planning_context(account_id, registry, store, *, runtime_store=None)`는 verified 관측만 metric evidence에 투영하고, `(destination, platform, target, remote_id, definition, basis, period)`로 물리 게시를 묶는다. connection 별칭·delivery·revision 차이로 같은 물리 게시를 중복 합산하지 않으며 각 원본 관측에 revision/manifest 근거가 남는다. owner는 조회 관련성과 원본 소유에 사용되고, 목적지 성과 집계는 destination에 귀속된다. 개인 소유 원고가 학과 채널에 공개된 경우 개인 조회에서 관련 근거를 볼 수 있어도 학과 성과를 개인 채널 합계로 옮기지 않는다.

현재 투영은 `latest_observation_id`, `latest_status`, `latest_metric_observation_id`, `previous_success_observation_id`, `observation_ids`를 이미 제공한다. 특히 collection.error/unsupported의 게시 단위 실패를 이전 metric 성공과 연결한다. 그러나 destination_metrics는 최신 실패 뒤에도 이전 성공 수치를 유지하므로 화면/기획기는 latest_status와 이전 성공 ID를 함께 읽어야 한다. 현재 시각에 따른 stale 판정은 없고, 누락 값도 자동 null로 바뀌지 않는다. 새로운 오류 정의만 도입해 기존 성공과 다른 그룹에 고립시키지 않도록 실패의 정의/basis/period 또는 물리 게시 실패 계약을 일관되게 정한다.

`save_proposal`에 전달하는 observation_ids는 화면에서 실제 검토한 저장 ID여야 한다. 초안 note에는 해당 ID의 정의·lifetime/interval·관측시각·최신 실패/과거 성공 구별과 해석 한계를 적는다. 요청 키는 수집 키와 별도로 유지한다. 수집 결과가 없거나 실패만 있으면 원인 확인 제안은 가능하지만 성과 우수/열위라고 해석할 수 없다. 현재 저장 검증이 계정 관련성만 보장한다는 점을 UI에서 숨기지 않는다.

## 필수 반례와 후속 집중 검증

|입력/상황|거부 또는 보존해야 할 결과|
|---|---|
|기존 `common/analytics/collect_youtube.py` RSS fallback이 지난주 views=120을 상속|현재 API 실측 관측으로 저장 금지. legacy provenance를 보존하거나 현재 수집 실패를 별도 기록. 새 collected_at으로 과거 값을 갱신한 것처럼 보이지 않음|
|RSS 신규 영상이 views=0을 생성하거나 API statistics/viewCount 누락|실제 0으로 정규화 금지. viewCount=`"0"`의 명시 응답만 0. missing/invalid는 값 없음과 error 근거 유지|
|조회수에 bool·음수·소수·빈 문자열·잘못된 숫자|YouTube count 정규화 단계 거부. 현재 범용 MetricResult의 숫자 허용만 신뢰하지 않음|
|owner=personal, destination=dept, 학과 target|개인 자격으로 바꾸지 않고 학과 destination 연결로 읽음. 저장에서 owner와 destination 둘 다 보존|
|요청 body가 다른 remote ID/target/account를 추가|허용 필드 검사로 거부. 서버 context를 클라이언트 값으로 덮지 않음|
|응답 ID는 맞지만 snippet.channelId가 다름, 로그인 주체가 다름|metrics_identity_mismatch에 해당하는 고정 오류. 값 저장/대상 자동선택/다른 채널 재시도 없음|
|원격 조회 동안 registry target·delivery remote/revision/manifest가 변경|고정 context와 재검증 context 불일치로 성공 저장 차단. 변경된 게시에 결과 재귀속 금지|
|같은 request key 동시 요청·재기동 후 재전송|하나의 명령 선점, 완료 결과 재사용. 새로운 원격 호출·collection ID를 만들어 충돌시키지 않음. 다른 payload는 conflict|
|과거 success 뒤 quota/timeout/unsupported|이전 성공을 지우거나 현재 ok로 재저장하지 않음. 최신 실패와 과거 성공 observation ID를 함께 제시|
|lifetime views를 지난 7일 증가량으로 해석|기간 성과로 전환 금지. interval은 별도 명시 API/기간/정의가 있을 때만 저장|
|제안 저장 계정이 관측 owner/destination 둘 다 아님|기존 save_proposal 검사로 거부. 근거 ID가 보존된 draft만 저장|

후속 검증은 기존 `tests/operations/test_metrics*.py`, `test_planning_context.py`, `tests/test_web_metrics.py`의 계약을 재사용하고 실제 서비스 클래스에 합성 transport를 주입해 위 경계만 집중 확인한다. 문서 작성 중 이 시험들을 실행한 것은 아니다. 실계정 수락은 실제 verified delivery 1건과 정확한 연결이 준비된 뒤 별도 수행하며, 화면 수치·저장 관측·제안 observation 귀속을 대조해야 한다. 그 전에는 collector 등록 코드나 합성 응답 성공만으로 실수집/운영 완료를 선언할 수 없다.
