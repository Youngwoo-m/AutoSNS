# 네이버 OAuth와 블로그 발행 호환성 확인

확인일: 2026-10-31. 공개된 네이버 공식 공지·개발 문서만 조회했다. 실제 로그인, 계정 연결, API 호출, 키 발급, 브라우저 프로필 열기, 설치, 커밋은 하지 않았다. 아래는 설계 근거이며 연결·발행 성공 검증이 아니다.

## 결론과 기존 운영 경계

네이버 로그인 OAuth를 **네이버 블로그 발행용 연결**로 표시할 근거가 없다. 로그인 방식 블로그 글쓰기 API는 2020-05-06 종료되었다. 로그인으로 회원정보 동의를 받는 것과 블로그 글을 게시할 권한은 구별한다. 종료 공지는 브라우저 자동화의 허용 여부를 증명하지 않는다. [공식 종료 공지](https://developers.naver.com/notice/article/7527)

AutoSNS 설계에서는 다음 상태를 독립적으로 취급한다.

| 구분 | 판단 |
|---|---|
| 네이버 로그인 OAuth | 회원 식별·동의한 정보 조회를 위한 별도 인증 연결로 설계 가능. 실제 애플리케이션 설정·계정·동의는 미확인 |
| 네이버 블로그 공식 OAuth 발행 | 종료된 글쓰기 API를 지원 기능으로 표시하지 않음 |
| 기존 블로그 브라우저 프로필 세션 | OAuth 토큰과 별개인 기존 운영 경로. 이 조사로 삭제·전환·실행하지 않음 |

브라우저 프로필의 로그인 쿠키 보유를 OAuth 연결 완료로 바꾸거나, OAuth 성공을 기존 블로그 발행 준비 완료로 바꾸지 않는다. 기존 운영·잠금 요구는 저장소 AGENTS.md를 따른다. 채널 진입점 조사는 [기존 감사](2026-10-31-remaining-channel-entrypoints.md)를 유지하며 중복 leaf 조사는 하지 않았다.

## URL별 확인 근거

### 1. 블로그 글쓰기 종료

- URL: https://developers.naver.com/notice/article/7527
- 제목: 블로그 오픈 API 종료 안내. 공지 등록일 2020-04-06.
- 종료 대상은 외부 서비스에서 글을 등록하던 로그인 방식 블로그 오픈 API(글쓰기), 적용일은 2020-05-06이다.
- 판단: 네이버 로그인 신규 연결에 블로그 게시 scope나 발행 capability를 붙일 수 없다. 이 공지에서 대체 블로그 게시 API나 브라우저 자동화 허용을 확인하지 않았다.

### 2. 인증 코드·토큰·폐기 API

- URL: https://developers.naver.com/docs/login/api/api.md
- 인증: GET/POST `https://nid.naver.com/oauth2.0/authorize`. 필수는 `response_type=code`, `client_id`, URL 인코딩한 등록 Callback URL인 `redirect_uri`, 애플리케이션이 생성하고 URL 인코딩한 CSRF 방지 `state`다. 문서의 `scope`는 내부 구분값으로 전송 불필요하다.
- 콜백: 성공은 `code`, `state`; 실패는 `state`, `error`, `error_description`이다.
- 발급: GET/POST `https://nid.naver.com/oauth2.0/token`; `grant_type=authorization_code`, `client_id`, `client_secret`, `code`, `state`가 필요하다. 갱신은 `grant_type=refresh_token`과 `refresh_token`을 사용한다. 만료는 응답 `expires_in`을 따른다.
- 폐기: POST `https://nid.naver.com/oauth2.0/revoke`; 필수 `client_id`, `client_secret`, `token`; 선택 `token_type_hint=access_token|refresh_token`(기본 access_token). 연결된 상대 토큰도 함께 폐기한다. 정상 결과는 본문 없는 HTTP 200이며 이미 없어진 토큰도 200일 수 있다.
- 구별: 이 문서는 별도 네이버 로그아웃 API를 제공하지 않는다고 설명한다. 토큰 폐기를 브라우저 로그아웃으로 표시하지 않는다. 오래된 `grant_type=delete` 방식을 이번 확인의 현재 폐기 계약으로 채택하지 않는다.

### 3. 상태 검증·회원정보 동의

- URL: https://developers.naver.com/docs/login/web/web.md
- 1.3–1.4: 로그인 후 기본 정보 제공 동의를 거쳐 콜백한다. 수신 `state`를 처음 생성해 세션 또는 별도 저장소에 둔 값과 비교하며 불일치 세션은 유효하지 않다.
- 1.6: 접근 토큰으로 `https://openapi.naver.com/v1/nid/me`에 Bearer 인증하여 사용자 식별값·별명·메일 등 프로필 정보를 조회한다.
- 판단: 이 회원 프로필은 디스크의 Chrome 사용자 프로필과 다른 개념이다. 회원정보 조회 성공은 브라우저 쿠키 취득·특정 블로그 소유·블로그 게시권한의 검증이 아니다.

### 4. 등록 Callback URL 일치

- URL: https://help.naver.com/service/23029/contents/19600?lang=ko
- 공식 검색 결과 본문은 등록 Callback URL과 인증 요청 `redirect_uri`의 정확한 일치를 요구한다. 직접 열기 결과에서는 고객센터의 외곽 UI만 노출되어 본문 추출이 제한되었다.
- 보강 근거: 위 API 명세 3.1도 `redirect_uri`를 애플리케이션 등록 시 입력한 Callback URL로 정의한다. 임의 redirect나 미등록 로컬 callback의 수락을 가정하지 않는다.

## 미확인·후속 설계 한계

실제 앱 등록·검수 상태, 필요한 개인정보 동의 항목, 로그인 연결 대상 주체, 서비스별 접근 가능 여부는 확인하지 않았다. 이 좁은 조사는 PKCE·OIDC 전체 계약이나 별도 제휴 API를 평가하지 않는다. 요금·법적 판단·자동화 허용 여부도 결론 내리지 않는다. 구현 시점에 해당 목적의 공식 문서를 다시 확인해야 한다.
