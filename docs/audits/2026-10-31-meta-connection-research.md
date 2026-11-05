# Meta 채널 연결 공식 근거 조사

2026-10-31. 공개 공식 문서만 조회했다. 실제 계정 접속, API 실행, 키·토큰 조회, 앱 생성, 설치, 게시, 연결 변경은 하지 않았다. 기존 구현 판정은 [남은 채널 진입점 감사](2026-10-31-remaining-channel-entrypoints.md)를 따른다. 이 문서는 연결 설계 근거이며 managed 지원·연결 성공·발행 수락을 뜻하지 않는다.

## 확인 범위와 근거 한계

Meta Developer 본문은 아래 주소들에서 429 또는 접근 실패였다. 따라서 공식 Meta Postman workspace의 공개 문서를 보조 1차 자료로 사용했다. Postman 컬렉션 스스로 최신 기능 전체를 보장하지 않는다고 안내한다. 검색에 노출된 제3자 가이드·복제 문서는 근거로 채택하지 않았다.

- [Instagram Login](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/)
- [Threads 토큰과 권한](https://developers.facebook.com/docs/threads/get-started/get-access-tokens-and-permissions/)
- [Pages 시작](https://developers.facebook.com/docs/pages-api/getting-started/)
- [권한 reference](https://developers.facebook.com/docs/permissions/)
- [App Review](https://developers.facebook.com/docs/apps/review/)
- [Facebook 장기 토큰](https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived/)

**아래 scope는 연결 설계 후보다. endpoint별 필수권한·종속권한 전체를 검증한 최소 집합으로 승인하면 안 된다.** 실제 앱의 승인·역할·계정 유형은 모두 미확인이다.

## Instagram

공식 컬렉션은 두 연결 방식을 별도로 설명한다. [Meta Instagram 공식 문서](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api?entity=request-23987686-1ff01566-3509-48bd-a0f4-8571a91ccfdf)

|경로|확인된 대상과 연결|권한 설계 후보|
|---|---|---|
|Instagram API with Instagram Login|Business·Creator 전문 계정|기본 조회 `instagram_business_basic`; 발행 추가 `instagram_business_content_publish`. 댓글·메시지 권한은 별도 기능이므로 일괄 요청하지 않는다|
|Instagram API with Facebook Login|전문 Instagram 계정과 연결된 Facebook Page. 일반 소비자 계정 지원 안 함|계정 탐색·기본 조회 후보 `pages_show_list`, `instagram_basic`, `pages_read_engagement`; 발행 후보 `instagram_content_publish` 추가|

Instagram Login의 위 권한 이름은 [공식 폴더](https://www.postman.com/meta/instagram/folder/1z5vxzu/instagram-api-with-instagram-login)에 확인된다. Facebook Login을 전면 폐기된 경로로 취급하거나 두 경로의 scope·토큰을 혼용할 근거가 없다. Instagram Login에서 Page 연결이 불필요한지, endpoint별 최소 scope 및 OAuth redirect 상세는 Developer 본문을 다시 확인해야 한다.

Facebook Login 예제는 User Token으로 Page 목록·Page token·연결된 IG ID를 얻는다. Reel 예제는 공개 영상 URL을 받아 container 생성 → 상태 조회 → `media_publish`로 진행한다. container ID와 게시된 media ID는 다르다. [공식 토큰·Reel 예제](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api?entity=request-23987686-fc851f39-7194-4522-a475-2cea8de46d16)

설계 결정: 기존 `graph_api.py`의 Facebook Graph 계열 경로를 유지할지 별도 Instagram Login 연결을 추가할지 먼저 정한다. connection에는 login 방식, 토큰 종류, 원격 IG ID, 연결 Page ID(해당 시), 승인 scope를 구별해 기록해야 한다. 기존 감사상 dry_run의 container POST는 외부 mutation이다. 로컬 prepare와 분리하고 공개 미디어 호스팅도 별도 승인·비용 항목으로 둔다. 이는 공식 계정에 실제 검증한 결과가 아닌 설계 제안이다.

## Threads

[Meta 공식 workspace](https://www.postman.com/meta/threads/overview)는 공식임을 명시한다. [시작 문서](https://www.postman.com/meta/threads/documentation/dht3nzz/threads-api)는 Threads use case를 가진 Meta 앱, 사용자 동의, Authorization Code 기반 OAuth를 설명한다. Threads App ID·Secret을 사용하며 code 교환 시 redirect URI가 최초 요청과 일치해야 한다. Instagram/Facebook 연결을 재사용할 수 있다는 근거는 없다.

기본 연결 후보는 `threads_basic`, 발행 추가 후보는 `threads_content_publish`다. 댓글·인사이트·삭제·검색 등은 이번 범위에 일괄 포함하지 않는다. 공식 문서는 `threads_basic`으로 단기→장기 교환과 미만료 장기 token refresh가 가능하다고 설명한다. 정확한 endpoint별 최소 scope·계정 유형 제약·최소 refresh 시점은 추가 확인이 필요하다. [공식 권한·토큰 문서](https://www.postman.com/meta/threads/documentation/dht3nzz/threads-api?entity=folder-34203612-995a4593-61de-4558-9b26-6c8becae85e4)

**부수효과:** 공식 텍스트 예제의 `auto_publish_text=true`는 container 생성과 동시에 게시한다. 이를 준비·연결 확인·dry_run에 쓰면 안 된다. 이미지·영상 URL은 공개 접근이 필요하며 별도 `threads_publish` 단계도 제공한다. [공식 생성·발행 예제](https://www.postman.com/meta/threads/documentation/dht3nzz/threads-api?entity=request-34203612-b4339073-a559-4e15-9ffe-974d6f0451ec)

설계 결정: connection inspection은 발행 요청과 분리한다. refresh는 HTTP GET이어도 인증 상태 갱신이므로 단순 읽기 검사에서 자동 실행하지 않는다. 장기 토큰 만료·refresh·저장·재동의를 별도 작업으로 모델링한다. 기존 브라우저 leaf의 published 추정값 대신 원격 ID·lookup·verify가 필요하다. 위 문서의 예제 만료 숫자는 실제 계정의 유효기간 보장으로 사용하지 않는다.

## Facebook

확인한 공식 예제는 User Token으로 관리 Page와 해당 Page Access Token을 얻는 **Pages** 연결이다. Page token이 특정 Page를 대표하며 결과에 Page ID와 tasks가 포함된다. [Meta Facebook 공식 토큰 문서](https://www.postman.com/meta/facebook/documentation/r56bjfd/facebook-api?entity=request-23987686-0b79260c-96bd-49de-875b-6076213785fc)

일반 개인 타임라인 발행을 같은 연결로 지원한다고 판단할 근거는 확보하지 못했다. `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`는 후속 공식 권한 reference에서 대조할 **후보 이름**이며 이번 공개 본문으로 endpoint별 최소 조합·종속권한을 검증하지 못했다. Page 읽기와 글쓰기 권한을 묶어 자동 요청하면 안 된다.

설계 결정: Facebook을 추가한다면 목적지는 우선 명시적인 Page ID로 한정하는 설계안을 검토한다. 실제 Page 존재·관리 tasks·승인 scope는 미확인 상태로 남긴다. 기존 감사에서 Facebook leaf/managed adapter는 없으므로 token 존재 가정만으로 ready로 올릴 수 없다.

## 심사·테스트·비용과 후속 게이트

OAuth 연결 화면부터 통합 개발하는 방향을 전제로 한다. 앱 등록·권한 점검을 먼저 완료해야만 화면 설계를 할 수 있다는 뜻은 아니다. 아래 unknown을 화면·backend 계약에서 숨기지 않고 표현한다. 우리 앱 ID·Secret·등록 callback URI·계정별 credential 보유 여부는 읽지 않았으며 모두 미확인이다.

|flow|이번 공식 자료에서 확인한 OAuth 계약|미확인·설계 처리|
|---|---|---|
|Instagram Login|독립 login 경로와 `instagram_business_*` 권한 계열|정확한 authorize/token URL, callback 응답·오류, state 지원, PKCE 지원, 등록 redirect URI 제약은 본문 재확인 필요. Facebook Login endpoint를 대신 끼우지 않는다|
|Instagram with Facebook Login / Facebook Pages|User Token → 관리 Page 및 Page Token을 얻는 구분|정확한 버전별 authorize/token URL, callback·state·PKCE 및 localhost/HTTPS/정확일치 제약은 이번 확보 자료로 미확인. 두 기능의 scope와 대상 ID 계약은 별도 유지한다|
|Threads|Authorization Code 교환은 `https://graph.threads.net/oauth/access_token`; 장기 교환은 `/access_token`의 `th_exchange_token`, refresh는 `/refresh_access_token`의 `th_refresh_token`. code callback과 동일한 redirect URI를 token 교환에 사용|정확한 authorize URL·state 지원·PKCE 지원·redirect 등록 형식과 localhost 허용은 이번 본문에서 미확인. callback은 code 수신과 token 교환을 별도 backend 단계로 설계하고 공식 검증 전 활성화하지 않는다|

state는 서버가 발급한 일회성 연결 시도와 사용자 세션·provider·대상 account를 묶어 검증하는 설계 요구사항으로 둔다. 이것은 provider별 공식 지원을 확인했다는 주장이 아니다. PKCE도 지원 확인 없이 필수 파라미터를 추측해 넣지 않는다. callback query/code/token을 UI 로그·URL 기록·감사 원문에 남기지 않는 저장 경계가 필요하다. consent 완료가 곧 발행 permission·원격 계정 검증 완료라는 가정 없이 화면에서 각 상태를 표시한다.

App Review, Standard/Advanced Access, 개발 모드의 역할별 접근 범위, Business Verification, 정기 데이터 이용 점검·audit 의무는 이번에 해당 공식 본문을 확보하지 못했다. **본인 계정이면 심사 없이 운영 가능**, **테스트 모드면 게시가 비공개**, **인증된 앱이면 모든 permission 사용 가능** 같은 단정을 하지 않는다. 실제 앱 설정 화면 열람도 이번 조사에서는 하지 않았다.

세 채널의 API 호출·심사·사업자 인증 관련 추가 요금표를 공식 문서로 확인하지 못했다. 따라서 비용은 **미확인**이며 무료로 표기하지 않는다. 공개 미디어 저장·전송, 실행 서버, 유료 중계 서비스를 채택할 경우의 비용은 API 사용료와 별도다. 호출·발행 제한 수치도 이번 자료로 운영 보장값을 확정하지 않았다.

연결 구현 전에 필요한 결정은 (1) 계정별 Instagram login 경로, (2) Threads 독립 connection, (3) Facebook Page 지원 여부와 대상, (4) 읽기 동의와 발행 동의 분리, (5) 앱 역할·심사 상태의 증거 필드, (6) refresh 허가·실패·재동의 정책, (7) 공개 미디어 호스팅 및 비용 승인 범위다. 공식 본문 재검증 전에는 각 connection을 `unverified`로 유지하고 실발행 readiness와 분리한다.
