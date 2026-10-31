# Google OAuth overlay 호환성 조사

확인일: 2026-10-31. 공개 Google 공식 문서만 조회했다. 기존 YouTube/Blogger 자격 파일·토큰·계정·로그인을 읽지 않았고 실제 API·OAuth·refresh·revoke 호출도 하지 않았다. 코드 구현·앱 생성·설정 변경·발행·커밋은 하지 않았다. [Meta 조사](2026-10-31-meta-connection-research.md), [기타 SNS 조사](2026-10-31-other-sns-connection-research.md)와 같은 설계 근거 문서다.

## 판정

**설계상 결합 가능하다.** 단, 새 OAuth overlay의 동의와 고정 대상 검증을 기존 발행 자격의 소유권·scope·활성화 증거로 간주하면 안 된다. 기존 토큰을 복사·재사용·확장하지 않고 별도 자격 저장 경계에 새 연결을 두며, 학과/개인 등 운영 슬롯의 사전 승인된 `channelId`/`blogId`와 원격 응답 ID를 정확히 비교하는 방식이다. 이는 문서에서 도출한 설계 판단이며 실제 계정 연결 성공을 확인한 결과가 아니다.

Google 로그인 이메일·표시명·`login_hint`는 대상 채널/블로그의 권한 증명이 아니다. 대상 불일치·빈 목록·부분 동의·scope 부족은 연결 보류로 두고 기본 계정으로 대체하지 않는다. 검증 실패 시 기존 발행 경로도 자동 변경하지 않는다.

## 공식 근거와 적용 경계

|공식 URL|확인한 내용|설계 적용|
|---|---|---|
|[Desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app)|Desktop app client의 macOS/Linux/Windows loopback listener 사용, 임의 가용 port, authorization code와 PKCE 지원. `S256` 권장. OOB 복사/붙여넣기 폐기|로컬 설치형 연결을 택하면 Desktop client + loopback + PKCE S256 후보. client secret을 데스크톱에서 비밀로 유지할 수 있다고 가정하지 않는다|
|[Web server OAuth](https://developers.google.com/identity/protocols/oauth2/web-server)|기밀 정보·상태를 보관할 서버용 code flow. redirect URI는 등록값과 scheme·대소문자·후행 slash까지 일치. localhost HTTP는 HTTPS 규칙의 예외이며 테스트 예시 존재|Web client에 Desktop의 임의 port 규칙을 이식하지 않는다. 서버형이면 등록 callback과 backend code 교환을 사용한다. loopback 주소라는 이유만으로 client 유형을 결정하지 않는다|
|[Loopback migration](https://developers.google.com/identity/protocols/oauth2/resources/loopback-migration)|모바일·Chrome app client의 loopback 폐기와 Desktop의 계속 지원을 구분|모든 Google client에서 loopback이 금지되었다거나 모두 허용된다는 주장 금지|
|[OAuth 개요](https://developers.google.com/identity/protocols/oauth2)|External + Testing의 refresh token은 기본 신원 scope만인 예외 외에는 7일 만료. 계정/client당 refresh token 수 제한·오래된 token 무효화 가능|YouTube/Blogger scope를 포함한 Testing 연결을 장기 무인 운영 준비 완료로 표시하지 않는다. Production도 영구 token 보장은 아니다|
|[OAuth 검증 안내](https://support.google.com/cloud/answer/13463073)|sensitive/restricted scope와 앱 공개 방식에 따라 검증 조건이 달라지고 Console에서 scope 분류 표시|테스트 사용자·개인 용도·조직 내부 예외와 실제 앱 심사 상태를 따로 확인해야 한다. 본인 계정이라는 이유로 무조건 심사 면제 판정하지 않는다|

새 연결은 일회성 `state`를 로컬 사용자 세션·provider·요청 슬롯·시도 만료와 묶고 callback에서 검증하는 설계가 필요하다. Desktop PKCE 지원 근거를 Web client의 모든 SDK/구성에서 자동 지원된다는 주장으로 확장하지 않는다. Web PKCE 채택은 선정 라이브러리·client 유형의 공식 지원을 구현 전에 추가 확인한다.

## scope와 고정 대상 검증

YouTube 읽기 후보는 `https://www.googleapis.com/auth/youtube.readonly`, 업로드의 좁은 후보는 `https://www.googleapis.com/auth/youtube.upload`다. [인증 가이드](https://developers.google.com/youtube/v3/guides/authentication), [videos.insert 허용 scope](https://developers.google.com/youtube/v3/docs/videos/insert). 연결 검사만을 위해 upload·youtube 전체 관리 권한을 요청하지 않는다. 읽기 동의는 기존 upload token의 권한 확장이나 해당 token의 현재 유효성을 증명하지 않는다.

[channels.list](https://developers.google.com/youtube/v3/docs/channels/list)의 `mine=true`는 인증 사용자의 채널만 반환한다. 새 읽기 연결로 `part=id` 등 필요한 최소 응답을 얻어 승인된 `channelId`와 비교할 수 있다(설계 판단). 단순 `id=예정채널` 공개 조회는 그 채널을 관리한다는 증명이 아니다. YouTube의 사용자/브랜드 채널 선택과 실제 반환 채널은 계정 상태에 달리므로 이번에 확정하지 않았다. upload-only 자격으로 같은 검증이 가능하다고 가정해 추가 scope를 자동 요구하지 않는다.

Blogger 읽기는 `https://www.googleapis.com/auth/blogger.readonly`, 게시에는 `https://www.googleapis.com/auth/blogger`가 필요하다. [blogs.listByUser](https://developers.google.com/blogger/docs/3.0/reference/blogs/listByUser)는 `userId=self`, `fetchUserInfo` 및 view를 제공한다. [BlogUserInfos](https://developers.google.com/blogger/docs/3.0/reference/blogUserInfos)는 userId/blogId/hasAdminAccess를 제공한다. 승인된 `blogId`와 사용자별 정보를 대조하는 읽기 검증 후보로 삼되 목록에 존재한다는 사실만으로 게시 권한을 보장하지 않는다. 게시 자체는 [posts.insert](https://developers.google.com/blogger/docs/3.0/reference/posts/insert)의 별도 동의·권한 gate다. [Blogger 사용 안내](https://developers.google.com/blogger/docs/3.0/using)는 공개 데이터 조회와 private 데이터 OAuth를 구분하므로 공개 블로그 조회 성공을 사용자 연결 성공으로 취급하지 않는다.

## refresh·연결 해제의 기존 발행 영향

[Web server OAuth](https://developers.google.com/identity/protocols/oauth2/web-server)는 offline access와 refresh token을 통한 갱신, token revoke를 설명한다. **같은 project에서 revoke하면 해당 사용자가 그 project에 부여한 scope와 그 아래 client들의 access/refresh token까지 무효화할 수 있다고 명시한다.** 따라서 새 client ID만 발급하면 기존 발행과 완전히 격리된다는 보장은 없다.

설계 판단: 기존 발행을 보호하려면 별도 project 격리 여부를 먼저 결정한다. overlay의 로컬 연결 해제와 Google grant 원격 revoke를 다른 작업으로 표시하고, 기존 project를 공유한 상태에서 원격 revoke를 자동 실행하지 않는다. 같은 project의 incremental authorization도 기존 grant와 합쳐질 수 있으므로 권한 격리 대안으로 간주하지 않는다. 새 token 발급 반복도 기존 token 수 제한에 영향을 줄 수 있다.

refresh는 원격 인증 mutation과 자격 저장 mutation이다. 상태 조회·dry inspection에 숨기지 않는다. 새 overlay 자격만 별도로 저장하고 동시 refresh를 직렬화하며 원자적 교체·실패 후 재동의 상태를 설계한다. 만료 시 기존 발행 token을 fallback으로 가져오지 않는다. 이 문서는 실제 refresh/revoke를 승인하거나 실행하지 않는다.

## 비용·quota와 미확인 항목

[YouTube quota 문서](https://developers.google.com/youtube/v3/determine_quota_cost)는 호출이 quota를 소비하고, 확인 시점 기본 배정은 search/upload 각각 100회/일, 나머지 합계 10,000 units/일이라고 안내한다. `channels.list`는 1 unit이다. 이는 가격표나 무제한 무료 보장이 아니다. 현재 [videos.insert](https://developers.google.com/youtube/v3/docs/videos/insert)는 미검증 API project 업로드의 private 강제가 없다고 안내한다. 옛 private 강제·업로드 1,600 units 수치를 현재 근거 없이 재사용하지 않는다. OAuth 앱 검증과 quota 확대·정책 audit은 같은 상태가 아니다.

위 quota 수치는 공개 문서의 현재 관찰이며 기존 runtime의 quota 상수·배포 설정을 수정할 근거로 사용하지 않는다. 실제 project 권한·quota는 검증하지 않았다.

Google OAuth/Blogger의 이 조사 문서에서 호출별 추가 요금·심사비가 항상 0이라는 보장은 확인하지 못했다. 따라서 **추가 비용 0: 미검증**이다. 실제 project의 quota·billing·앱 유형·API 활성화·scope 심사·테스트 사용자·기존 project 공유 여부는 전부 미확인이다. 서버·공개 미디어 호스팅·제3자 중계 비용도 별도다. 비용 승인 없이 유료 서비스·quota 구매·결제수단 등록을 연결 과정에 넣지 않는다.

구현 전 결정 사항은 client 유형, 기존 발행과 project 격리, 승인된 고정 대상 ID의 출처, 연결용 최소 읽기 scope, 재동의/refresh/revoke 허용 경계다. 이번 결과는 OAuth-first 설계 승인용이며 연결·발행 readiness는 계속 미확인으로 유지한다.
