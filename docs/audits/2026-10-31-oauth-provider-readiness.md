# OAuth provider adapter 준비 상태

2026-11-01 Task4. 실제 계정·키·Keychain·프로필·provider API 호출·발행·설치 0. 아래 wire 검증은 명시 주입한 fake fetch와 시험용 비용 규칙만 사용했다. production catalog의 모든 비용은 unknown이며 authorize를 포함한 실제 외부 동작은 차단된다. main에는 transport/provider를 주입하지 않는다.

## 확인된 좁은 계약과 미완 추적

|제공자|구현된 wire 계약|차단과 해소 조건|
|---|---|---|
|Instagram Login|없음|독립 authorize/token/inspect/refresh/revoke URL·버전·필드·state·PKCE·redirect를 공식 자료로 확인해야 한다. Facebook Login URL로 대체하지 않는다.|
|Instagram Facebook Login|없음|Facebook 버전별 URL, Page/IG 탐색·토큰·tasks·scope 및 callback/PKCE 확인 필요. Instagram Login 자격과 혼합 금지.|
|Facebook Pages|없음|authorize/token 및 Page principal/targets/tasks 최소 projection 계약 확인 필요. 개인 타임라인 미지원.|
|Threads|code exchange POST graph.threads.net/oauth/access_token의 client_id/client_secret/code/grant_type/redirect_uri|authorize/state/PKCE/redirect 등록과 principal 미확인. refresh URL은 catalog에 있으나 token 종류·최소 갱신 시점 및 수명 검증 미완으로 adapter refresh 차단. 장기교환을 숨겨 추가 실행하지 않음.|
|X|confidential client refresh POST api.x.com/2/oauth2/token, Basic 인증 및 refresh_token/grant_type|authorize/code exchange의 완결 PKCE fixture와 public-client 분기, inspect/revoke 미구현. catalog에 없는 URL을 추정하지 않음. offline.access는 별도 동의이며 현재 기본 scope에 추가하지 않음. 유료/크레딧 gate 미확인으로 principal 조회도 차단.|
|TikTok|Web code exchange와 refresh POST open.tiktokapis.com/v2/oauth/token/, client_key/client_secret, code/redirect_uri 또는 refresh_token, comma scope 및 반환 refresh token 회전|authorize/inspect/revoke 미확인 catalog 차단. mobile/Desktop PKCE로 자동 대체하지 않음. Display·inbox upload·Direct Post는 서로 별도 capability. 내부 utility intended use, 심사/audit/creator UX 미해결.|
|YouTube/Blogger|없음|Web 계약 catalog URL 미확인, Desktop/loopback/PKCE를 가져오지 않음. 최소 읽기 principal/channelId/blogId 계약 fixture 필요. 기존 project/client grant 영향과 격리 미확인으로 원격 revoke 계속 차단.|
|Naver profile|authorize; token exchange/refresh; revoke; Bearer 회원 프로필 inspect|**exchange는 원래 state 원문이 필수**. 현재 승인된 callback 재개 wrapper는 context/client_config만 제공하고 DB에는 state hash만 남기므로 실제 흐름에서 exchange를 차단한다. 원문을 DB/로그에 저장해 해결하지 않음. 세션 재개와 hash-only 원칙을 양립시키는 별도 설계 필요. missing-state 시험 외부 0. inspect는 provider_subject와 targets=[]만 반환하며 블로그 소유·발행 증거를 만들지 않음.|
|Tistory|없음|공식 API 종료, unsupported 유지. 브라우저·비공개 API fallback 0.|

Naver revoke는 POST /oauth2.0/revoke의 client_id/client_secret/token/token_type_hint 계약이며 빈 HTTP 200을 성공으로 처리한다. 결과 impact는 paired_access_refresh_tokens다. 폐기를 브라우저 로그아웃이나 블로그 자격 삭제로 표시하지 않는다. 오래된 grant_type=delete 요청은 구현하지 않았다.

모든 제공자는 실제 앱 등록, 승인 scope, 정확한 HTTPS callback, OS 저장 접근, 비용 0 증거 및 목적/정책 수락 전 real_oauth_ready=false/live_publish_ready=false다. 이 문서는 미완 항목을 제거하거나 향후 전체 목표를 완료 처리하지 않는다.

## 근거

기존 [Meta 조사](2026-10-31-meta-connection-research.md), [기타 SNS 조사](2026-10-31-other-sns-connection-research.md), [Google 조사](2026-10-31-google-oauth-compatibility.md), [네이버 조사](2026-10-31-naver-oauth-compatibility.md)의 확인 범위를 따른다.

추가 공개 문서 읽기(2026-11-01, 계정/API 실행 아님): [X OAuth2](https://docs.x.com/fundamentals/authentication/oauth-2-0/authorization-code)는 confidential client의 Authorization header와 public client의 body client_id 구분, refresh endpoint와 offline.access를 확인했다. [TikTok token management](https://developers.tiktok.com/docs/en/oauth-user-access-token-management)는 Web redirect_uri와 client_key, 모바일/Desktop 전용 code_verifier, 쉼표 scope 및 refresh 회전 필드를 확인했다. 가격 0은 확인하지 않았다.

## 안전 경계와 검증

OAuthTransport(catalog, fetch=None)는 기본 미구성이다. fixture fetch는 urllib Request와 timeout/TLS context를 받아 응답 객체를 반환하며 redirect를 수행하지 않아야 한다. 실제 사용용 urllib_fetch도 별도 명시 주입해야 하며 고정 HTTPS, 기본 TLS 검증, proxy/쿠키 0, redirect 거부, timeout<=30초, 응답<=262144 bytes, retry/fallback 0이다. 응답 URL 변경·3xx·비정상 JSON·provider error·큰 응답은 고정 오류로 변환한다. 실제 urllib_fetch는 실행하지 않았다.

`python3 -m unittest tests.oauth.test_provider_contracts -v`: 15 tests, PASS, skip 0. default catalog 비용/계약 차단 외부 0; exact URL/method/form/header, Naver scope 생략·redirect 일치·빈 revoke·프로필-only, TikTok refresh 회전, X Basic, PKCE 미확인 거부, Threads refresh 차단, 오류/리다이렉트/크기/재시도 0을 검증했다. 실 provider 성공이나 배포 완료의 증거는 아니다.
