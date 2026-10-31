# 기타 SNS 연결의 공식 지원과 gate 조사

확인일: 2026-10-31. 공식 공개 문서만 열람했다. 계정/API 호출, 키 열람·발급, 로그인, 브라우저 프로필 실행, 설치, 발행, 결제·크레딧 사용은 하지 않았다. 저장소 leaf는 [기존 진입점 조사](2026-10-31-remaining-channel-entrypoints.md)를 근거로 삼았고 중복 실행하지 않았다. 아래는 서비스 제공 조건이며 실제 계정의 권한·잔액·심사 상태를 확인한 결과가 아니다.

## X

공식 API는 읽기와 쓰기를 지원한다. 사용자 발행은 `POST /2/tweets`; OAuth 1.0a user context 또는 OAuth 2.0 Authorization Code + PKCE이며 app-only bearer는 발행용이 아니다. OAuth2의 발행 최소 묶음은 `tweet.read tweet.write users.read`; 읽기 lookup은 `tweet.read users.read`다. 미디어 업로드는 `media.write`도 별도 검토한다. 기본 연결에서 DM·팔로우·좋아요 권한을 요청할 이유가 없다. [인증 매핑](https://docs.x.com/fundamentals/authentication/guides/v2-authentication-mapping), [게시 endpoint](https://docs.x.com/x-api/posts/create-post), [scope·PKCE](https://docs.x.com/fundamentals/authentication/oauth-2-0/authorization-code).

앱의 OAuth 설정·등록 redirect URI·client ID가 필요하며 confidential client는 secret을 서버에 둔다. 기본 access token은 2시간이고 `offline.access`를 요청해야 refresh token이 발급된다. refresh는 `POST https://api.x.com/2/oauth2/token`이라는 외부 인증 mutation이며 반환 자격 저장도 로컬 mutation이다. 연결 상태 조회에 숨겨 자동 수행하지 말고, refresh 가능/필요/실패를 독립 상태로 기록한다. 위 PKCE 문서는 refresh-token 발급 조건을 명시하나 이 조사에서 회전 세부 보장은 확인하지 않았으므로 새 응답 자격을 원자적으로 저장하고 동시 refresh를 직렬화하는 설계를 권장한다(설계 판단).

**유료 gate:** 현재 공식 요금은 구독형이 아닌 선불 크레딧 종량제다. 조회도 비용이 생긴다. 공개 표의 예는 Post read $0.005/resource, User read $0.010/resource, Post create $0.015/request, URL 포함 create $0.200/request다. 실제 endpoint 단가는 Developer Console 확인 사항이며 무료 일반 경로라고 판정할 수 없다. 결제수단·첫 구매 등에 붙는 프로모션도 무조건 무료가 아니다. [공식 가격](https://docs.x.com/x-api/getting-started/pricing).

따라서 기존 OAuth 자격이 있어도 `paid_gate_unverified`를 유지한다. 원격 principal inspection/게시 lookup도 비용 승인이 필요하며 추가 결제·자동충전·크레딧 소비를 연결 확인에 포함하지 않는다. developer app 접근·사용자 scope·비용 허용은 서로 별도 조건이다. 현재 계정의 앱 승인이나 비용 허용은 미확인이다.

## TikTok

읽기는 Display API `/v2/user/info/`, `/v2/video/list/`, `/v2/video/query/`를 지원한다. 최소 principal 확인은 `user.info.basic`; 공개 영상 조회를 실제 제공할 때만 `video.list`를 추가한다. 통계나 상세 프로필은 `user.info.stats`, `user.info.profile`의 별도 동의가 필요하다. [Display API](https://developers.tiktok.com/docs/en/display-api-overview), [scope 목록](https://developers.tiktok.com/docs/en/tiktok-api-scopes).

쓰기는 서로 다른 두 capability다. Direct Post는 승인된 앱과 사용자 `video.publish` 동의가 필요하며 영상·사진을 게시한다. `video.upload`의 inbox 업로드는 사용자가 TikTok 알림을 열어 편집·게시를 마쳐야 하므로 자동발행 성공으로 표시하면 안 된다. [Direct Post 시작](https://developers.tiktok.com/docs/en/content-posting-api-get-started), [Upload](https://developers.tiktok.com/docs/en/content-posting-api-reference-upload-video).

앱 심사는 완성된 외부 공개 서비스·개인정보처리방침·약관·redirect URI·scope 설명 등을 요구한다. 개인/사적 용도 앱은 승인 대상이 아니라는 지침이 있다. [앱 심사 지침](https://developers.tiktok.com/docs/en/app-review-guidelines). Direct Post audit은 별도 gate다. 미심사 client는 24시간 최대 5 사용자, 게시 당시 비공개 계정, SELF_ONLY 제한이다. 특히 자신/팀이 관리하는 계정에 올리기 위한 내부 utility는 허용되는 intended use 예시가 아니다. AutoSNS의 내부 운영 용도에 정식 공개 Direct Post 심사를 통과한다고 가정하지 않는다. [Content Sharing 지침](https://developers.tiktok.com/docs/en/content-sharing-guidelines).

같은 지침은 게시 화면의 최신 creator_info·대상 nickname 표시, 게시 가능 여부 검사, 사용자 공개범위 선택 등 UX를 요구한다. 따라서 backend가 공개범위를 임의 대체하거나 전권 자동화하는 기존 구현 존재만으로 정책 적합 판정을 내릴 수 없다. API와 웹 경로는 별도 connection/method로 표시하며 기존 웹 경로가 API audit 제한을 합법적으로 우회한다는 주장은 하지 않는다.

OAuth token endpoint는 `POST https://open.tiktokapis.com/v2/oauth/token/`; client_key/secret와 code를 교환한다. 최초 access token 24시간, refresh token 365일이며 서버 refresh가 가능하다. 응답 refresh token은 이전과 다를 수 있고 다르면 반드시 새 값을 사용해야 한다. refresh는 네트워크와 자격 저장 mutation이므로 dry inspection에서 수행하지 않는다. [토큰 관리](https://developers.tiktok.com/docs/en/oauth-user-access-token-management).

상태 확인은 `POST /v2/post/publish/status/fetch/`에 publish_id를 전달하며 `video.upload` 또는 `video.publish` scope가 필요하다. HTTP POST지만 의미상 조회이므로 transport verb만으로 발행과 동일 분류하지 않는다. 처리·검수 완료시간 보장은 없고 공개 게시 ID는 검수 완료까지 나오지 않을 수 있다. 응답 성공·PUBLISH_COMPLETE와 공개 가시성 증명을 구분한다. [게시 상태](https://developers.tiktok.com/docs/en/content-posting-api-reference-get-video-status).

이번 공식 페이지에서 Content Posting/Display의 호출별 유료 가격표는 확인하지 못했다. 이는 무제한 무료 보장이 아니다. 별도 인프라·미디어 호스팅·외부 도구 비용도 자동 허용하지 않는다. URL pull은 검증한 domain/prefix가 필요하다.

## Tistory

공식 종료 공지는 2023-12-22 게시됐으며 2023년 말부터 다음 2월 말까지 순차 종료, 유지보수 중단, API 글 작성·수정·파일 첨부·댓글 기능 종료와 에디터 직접 관리를 명시한다. 따라서 옛 OAuth/Open API 문서가 검색되거나 코드가 남아 있어도 신규 공식 API 연결 지원으로 등록하지 않는다. [공식 종료 공지](https://notice.tistory.com/2664).

공식 대안으로 안내된 것은 에디터/티스토리를 통한 직접 관리다. 이것이 브라우저 자동화에 대한 명시적 허가라는 뜻은 아니다. 현재 [티스토리 약관](https://www.tistory.com/info/contract)은 서비스 방해·약관 위반에 따른 제한과 카카오 약관/운영정책의 함께 적용을 정한다. 이번 확인만으로 정상 사용자 UI 자동화 전반의 명시적 허용 또는 일괄 금지를 확정하지 않는다. **공식 API 지원: 종료 / 브라우저 구현 가능성: 기존 코드가 존재할 수 있음 / 자동화 정책 적합성: 별도 미확인**을 구분한다.

OAuth scope·refresh를 새로 설계할 공식 Tistory API는 없다. 브라우저 방식은 로그인 세션 쿠키와 대상 블로그·작성 권한 확인이 필요하며, 세션 갱신/로그인/쿠키 저장을 읽기 확인에 숨기지 않는다. 프로필 사용은 저장소 규칙에 따라 `shared/axlock.py`의 `profile:tistory`(개인 프로필 공유) 잠금과 종료를 지켜야 한다. 이번에는 프로필을 열지 않았다. 비공개 관리 API 역공학을 공식 연결 대안으로 제안하지 않는다.

## 설계에 전달할 판정

|채널|초기 연결 표시|쓰기 활성화 전 조건|
|---|---|---|
|X|지원 API 있음, 실제 자격·유료 gate 미확인|principal·scope·app 접근·비용 승인·미디어 권한을 각각 확인|
|TikTok API|읽기/업로드/Direct Post 각각 분리|app review, 사용자 scope, intended use 적합성, Direct Post audit·UX; 내부 utility 적합성 unresolved|
|TikTok 웹|기존 구현 존재, 공식 허용 미확인|정책 판단·대상 바인딩·프로필 잠금·확인 가능한 결과 경계|
|Tistory API|공식 종료, 신규 연결 unsupported|옛 API 자격으로 활성화하지 않음|
|Tistory 웹|수동 에디터 지원, 자동화 적합성 미확인|대상 블로그·권한·정책·잠금·세션 관리 별도 확인|

Naver/Blogger/YouTube는 이번 조사 범위에서 재조사하지 않았다. 기존 구현 유무는 연결의 계정 주체·권한·발행 준비 완료를 증명하지 않는다. 이 문서는 설계 조사이며 새 connection, adapter, publish permit를 구현하거나 활성화하지 않았다.
