# SNS 운영 연결을 위한 다음 산출물 — 2026-11-01

전체 목표는 개인·학과의 기획 → 제작·독립 검토 → 예약 → 기존 교차 공개 → 공개 결과 검증 → 성과·다음 기획의 순환이다. 9개 메뉴·기술사 4종·23개 교차 규칙을 유지한다. 아래 세 산출물은 그 목표의 다음 구현 단위이며 전체 목표를 세 단위로 축소한 것이 아니다.

기존 [전체 증거 지도](2026-10-31-goal-evidence-matrix.md), [provider 준비 상태](2026-10-31-oauth-provider-readiness.md), [기존 SNS leaf 감사](2026-10-31-remaining-channel-entrypoints.md), [OAuth 설계](../superpowers/specs/2026-10-31-sns-oauth-connections-design.md)·[계획](../superpowers/plans/2026-10-31-sns-oauth-connections.md)를 현재 코드의 접합부와 대조했다. 새 전수조사·공식 문서 재검색은 하지 않았다. 실제 설정·키값·콘텐츠·DB는 읽지 않았고 브라우저·native·외부 API·발행·서버 변경·시험 실행은 하지 않았다. 이 문서는 구현 제안이며 실행 수락 기록이 아니다.

## 1. OAuth 연결을 기존 publisher가 사용할 수 있게 하는 운영 조립 패키지

**현재 끊긴 곳.** `common/operations/managed_connections.py:30`의 `credential_catalog(snapshot)`와 `:212`의 `project_registry()`는 OAuth overlay를 조립하지만 connected도 `enabled=False`로 둔다. 기존 `common/publishers/blog_runtime.py:43`, `youtube_runtime.py:38`의 resolver는 각자의 고정 legacy credential 이름만 받는다. 두 resolver는 만료 Google 자격을 읽으면서 refresh와 암호화 저장까지 수행한다. 따라서 화면에서 OAuth 동의를 마치거나 factory에 새 catalog만 넘겨서는 새 연결을 사용하지 못하며, 읽기 확인에 숨은 자격 mutation도 남는다.

**구현할 실제 산출물.** 서버가 주입하는 managed credential resolver 및 publisher 조립 factory를 만든다. 같은 `ManagedSnapshot`에서 registry·credential catalog를 만들고, 정확한 account/platform/connection/generation/target·관측 scope·기한·자격 상태를 검사한 뒤 필요한 서비스 객체에만 자격을 전달한다. `operation_lease` 존재, unknown/reauth_required/disconnected, 세대 변경, scope 부족은 backend 조회/handler 호출 전에 차단한다. read/publication을 구별하며 refresh는 기존 명시 OAuth 수명주기로 돌려보낸다. OAuth ref에서 legacy 저장소로 자동 fallback하지 않는다. 기존 legacy 경로 자체를 일괄 제거하지 않는다.

`BridgeHost.execute()`의 현재 `inspect_target/lookup/verify/publish` 경계와 permit·STOP·잠금을 그대로 이용한다(`common/publishers/bridge_host.py:41`). 부모 실행 프로세스와 고정 child bootstrap이 같은 명시 운영 조립을 사용하도록 전달 경계를 구현한다. 현재 bootstrap은 정적 base registry를 다시 읽으므로 부모에 overlay만 주입하는 구현으로 끝내지 않는다(`blog_runtime.py:124`, `youtube_runtime.py:108`). 서버 소유 등록 입력·비밀 없는 준비상태 진단·명시 기동 opt-in을 묶되 기본 미주입/발행 비활성을 유지한다. 새 secret 파일·환경변수·stdin 토큰 전달은 만들지 않는다.

**완료 조건.** 실제 사용될 factory·resolver·child bootstrap이 연결되고, 비밀 없는 준비상태 출력에서 미등록/비용미확인/권한부족/갱신필요를 구별한다. 거부 경로에서 Keychain·provider·publisher 호출이 없고, 승인된 정확한 한 연결만 기존 handler까지 도달한다는 집중 검증을 남긴다. fake를 추가하는 데 그치지 않고 기본 legacy resolver와 새 OAuth 자격 사이의 실제 코드 접합부를 완성한다. 별도 공개 승인 없이 `enabled`·실행 owner를 올리지 않는다.

**실인증 전에 가능한 범위와 의존.** 이 조립 코드는 키 없이 구현 가능하다. [crash recovery 계획](../superpowers/plans/2026-11-01-oauth-crash-recovery.md)의 자격 보존·복구 수락은 실 Keychain 사용의 선행조건이다. provider별 미완 authorize/exchange/inspect·비용0·HTTPS·앱 등록은 이 resolver가 해결한 것으로 처리하지 않는다. Naver profile 동의를 블로그 자격으로, Tistory를 OAuth API로 승격하지 않는다.

## 2. 기존 추가 SNS 한 경로를 managed 원장까지 연결하는 단일 효과 구현

**첫 구현 단위는 학과 Threads 텍스트 교차 게시**를 권장한다. 새 미디어 호스팅·영상 변환·Graph container가 필요 없고 기존 `_compose()`/`compose()`와 브라우저 leaf가 있다. 원본 소유는 개인일 수도 있고 목적지는 학과라는 기존 의미를 유지한다. 이 선택은 브라우저 자동화의 정책 적합성 또는 실제 DOM 유효성을 확인했다는 뜻이 아니다. 해당 수락 전 실경로는 계속 비활성이다.

**현재 끊긴 곳.** `common/publishers/__init__.py:2`는 Blog5·YouTube2만 조립한다. `dept/insta-cardnews/post_threads.py:89`의 `post()`는 설정·작성·submit을 묶고, 버튼 클릭 후 대기만으로 published를 반환한다. 원격 ID·본문·주체·공개 가시성 관측이 없다. 기존 wrapper 전체를 publish handler로 등록하면 실제 공개 검증과 unknown 복구가 생기지 않는다.

**구현할 실제 산출물.** 기존 leaf를 순수 문자열 준비, 계정/대상 inspection, 명시 submit, 읽기 observation으로 분리하고 `ThreadsAdapter`·고정 runtime/handler를 추가한다. frozen content revision/manifest·destination·예상 로그인 주체를 기존 `PublicationContext`에 결속한다. prepare/dry에서는 브라우저·클립보드·작성창을 열지 않는다. 게시 클릭은 permit을 소비한 한 handler에 두며 프로필은 `shared/axlock.py`의 학과 공유 잠금 아래 열고 종료한다. 추가 댓글·수정·다른 SNS 호출은 그 허가에 섞지 않는다.

관측은 실제 제출 대상의 canonical URL/원격 ID·계정·본문·가시성 근거를 돌려주도록 구현한다. 확인 불가능하면 unsupported/pending/unknown이며 published/verified로 추정하지 않는다. 제출 후 응답 유실은 재게시 대신 lookup으로 보낸다. 안정된 ID와 강한 lookup을 얻을 수 없으면 그 한계를 명시하고 자동 재시도는 막는다. 이후 실제 브라우저 읽기 수락에서 관측 가능성이 확인되어야 쓰기 수락으로 넘어간다.

**완료 조건.** 실제 leaf에 연결되는 adapter/runtime가 존재하고 `common/operations/crossposts.py`의 기존 intent → adapter → permit handler → runtime ledger/verification 경로를 통과한다. 초기 등록은 shadow/비활성으로 둔다. `entrypoints.py:74`·`legacy_fences.py:23`의 caller fence를 해당 경로에 연결하되 전 caller 수락 전 managed owner 전환을 막는다. 기존 `geoai.threads` 등 관련 predicate·enabled=null·owner/delay·다른 23개 규칙을 보존한다. 콘솔·직접 CLI·교차 wrapper가 같은 경로를 중복 발행하지 않는 집중 검증이 필요하다.

**남은 SNS를 보존하는 후속 순서.** 이 단일 효과 경계를 Instagram carousel/reel, X, TikTok web/API에 적용하되 각 leaf 감사의 별도 mutation을 그대로 분리한다. Instagram Graph의 dry container 생성·댓글, X의 refresh/media upload, TikTok의 creator UX·업로드·poll·중복원장/큐 retry를 하나의 publish 허가에 감싸지 않는다. TikTok 30분·3시간·게시창·hold·tries와 단일 retry owner를 보존한다. Facebook은 기존 leaf가 없으므로 별도 Pages 구현이 필요하며, 개인 목적지의 미구현을 학과 leaf 재사용만으로 완료 표시하지 않는다. 비용/정책 차단은 계속 개별 추적한다.

## 3. 검증된 게시물 하나의 실제 성과를 다음 기획까지 연결하는 collector

**현재 끊긴 곳.** `common/operations/metrics.py:28`은 verified 공개 원장·불변 대상·원격 ID로 `MetricsContext`를 만들고 `:73`의 collector 주입, `:93`의 저장을 제공한다. 그러나 `ax-console/app/web_metrics.py:55`는 조회/가져오기/제안 저장뿐이고 수집 실행 경로가 없다. 기존 `metrics_normalization.py:1`은 수동 CSV count 정규화다. `common/analytics/collect_youtube.py:67`의 RSS fallback은 과거 조회수 또는 신규0을 만들므로 그대로 managed 실측으로 감싸면 안 된다.

**구현할 실제 산출물.** YouTube의 검증된 delivery 하나를 대상으로 서버 주입 collector와 명시 수집 명령/POST를 만든다. 기존 `youtube_services.py:90`의 원격 조회 경계에 통계 조회를 별도 추가하고, 정확한 remote ID·채널 ID·읽기 scope·비용/할당량 검사를 적용한다. 기존 전체 채널 collector나 파일 기반 토큰 경로를 import/호출해 우회하지 않는다. 자격은 1번 resolver 경계에서 받고 숨은 refresh는 하지 않는다.

provider별 결과를 `MetricResult`로 정규화해 정의·lifetime/interval·관측시각·수집시각·null/실제0·stale/error를 보존한다. 누락 statistic은 0으로 만들지 않고 RSS/이전 값은 현재 실측으로 저장하지 않는다. `record_metrics()`의 delivery 재검증·소유/목적지·content revision/manifest 결속을 재사용하고, 명시 수집 request key의 중복 처리를 구현한다. GET는 계속 원격 호출0이다. 수집 결과를 기존 저장 제안에 연결하고 observation ID를 근거로 다음 기획 초안을 저장하는 연결부까지 포함한다. 성과 읽기가 원고 생성·공개 승인을 자동으로 만들지는 않는다.

**완료 조건.** 실제 YouTube 서비스 객체를 사용할 수 있는 collector·비활성 서버 등록·명시 실행 경로가 있고 집중 계약 검증을 통과한다. 실계정 수락에서는 검증된 게시물 하나의 실제 값과 화면·저장 제안의 observation 귀속을 확인한다. 아직 verified delivery가 없다면 legacy ID를 임의로 verified로 가져오지 않고, 1번으로 연결한 기존 Blog/YouTube 공개 검증을 먼저 거친다. 다른 플랫폼 성과 collector는 같은 결속 계약으로 추가한다.

## 지금 진행할 일과 사용자 정보의 최소 경계

위 세 구현은 실키 없이 진행할 수 있다. 1번을 먼저 계약 고정하고 2번 leaf 분해와 3번 collector/정규화는 파일 소유를 나누어 병렬 개발할 수 있다. 통합과 실제 계정·프로필·발행 수락은 직렬로 수행한다. 새 전체조사나 mock 대량 추가를 선행할 이유는 없다. 제작·독립 검토·미디어/PDF·예약·나머지 SNS·실스케줄/물리 이행·외부 접속 수락은 전체 증거 지도의 후속 의무로 남는다.

실행 시 필요한 정보는 아래뿐이다. 기존 안전한 등록부/운영 증거에서 얻을 수 있는 항목을 먼저 대조하고, 사용자에게 같은 정보를 다시 요구하지 않는다. 지금 문서 작성에서는 실제 등록부·설정을 읽지 않았다.

|필요 시점|최소 정보|제공 형태|
|첫 실제 읽기/발행 대상 선택|개인/학과, 플랫폼, 불변 target ID 또는 이를 확인할 공개 URL; 원본 owner와 게시 destination|우선 읽기 전용 YouTube 한 연결과 Threads 학과 한 연결을 제안하되 실제 대상 선택은 확인된 등록 정보로 구체화|
|OAuth 연결을 실제 시작할 때|해당 provider의 앱 보유 여부/종류, 승인 scope·심사 상태, 등록된 정확한 HTTPS callback 및 Google이면 기존 project/client 공유 여부|비밀 없는 앱 등록 정보·권한/비용0 근거. 미등록이면 등록 작업 범위와 고정 callback 접속 방식을 먼저 확정|
|자격 저장소를 실제 연결할 때|사용할 기존 자격 저장 방식과 정확한 연결 참조, 해당 namespace의 OS 접근 허용|secret/token/비밀번호를 채팅에 요구하지 않음. 필요한 입력은 구현된 보호된 로컬 절차로 수행|
|최초 쓰기 수락 직전|동결 원고·자산 revision, 정확한 목적지, 비공개/예약/공개 범위·시각 및 후처리 범위|실제 검토 가능한 한 게시물과 그 별도 공개 승인. 이미 주어진 승인은 재질문하지 않고 범위 대조|

X의 비용0 근거와 TikTok의 intended use/audit/creator UX 문제는 키값 하나로 풀리지 않는다. 그 채널을 없애지 않고 차단 사유와 해소 작업을 유지한다. 이 문서와 코드 구현 완료만으로 real_oauth_ready/live_publish_ready 또는 전체 운영 완료를 선언하지 않는다.
