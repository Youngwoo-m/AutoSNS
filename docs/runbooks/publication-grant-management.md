# 계정별 발행 사용 승인 관리

개인 계정 연결·학과 계정 연결의 기존 OAuth 연결 상세 안에서 사용한다. 새 상위 메뉴는 추가하지 않는다. ‘발행 scope 추가 동의’, ‘해당 자격의 한시 발행 사용 승인’, ‘각 콘텐츠의 검토·실행 승인’은 별도다.

현재 운영 기동에는 관리 서비스·Google 검사 transport·앱/비용 승인 guard를 등록하지 않았다. 실제 로그인·Keychain·공급자 API·발행이나 기존 작업 전환을 이 개발로 활성화하지 않는다. 현재 연결이 없는 계정을 연결 완료로 표시하지 않는다.

## 사용 흐름

연결을 직접 선택한 뒤 발행 사용 승인 상태를 조회한다. 화면을 열거나 계정·공급자를 바꾸는 것만으로 공급자를 호출하지 않는다. 서버가 허용한 경우에만 ‘게시 권한 확인 후 발행 사용 승인’을 실행한다. 이 클릭은 현재 계정·대상·자격의 게시 권한을 읽기 API로 확인하고 제한 시간의 grant를 저장한다. 원고를 게시하지 않는다. 승인 회수는 로컬 사용 grant를 회수하며 공급자 토큰 해지나 공개 게시물 삭제가 아니다.

응답이 불명확하면 성공으로 표시하거나 변경 요청을 자동 재시도하지 않는다. 현재 상태를 다시 조회한 후 다음 동작을 선택한다. 변경 요청은 연결·registry·grant revision CAS로 중복 이력 추가를 막는다. request_key에 대한 영속 응답 재생은 제공하지 않는다.

## 서버 계약

GET `/api/v2/oauth/connections/<connection_id>/publication-grant`는 현재 소유 연결·등록·grant 상태만 읽는다. vault/API·저장소 초기화를 하지 않는다. 등록이 없거나 소유 증명이 맞지 않으면 실패한다.

POST 같은 경로의 `/approve`, `/revoke`는 사용자 쿠키·Origin·CSRF와 정확한 요청 필드를 요구한다. 필드는 `request_key`, `expected_base_revision`, `expected_connection_revision`, `expected_grant_revision`뿐이다. 클라이언트가 scope·대상·만료·증거·권한을 제출하지 않는다.

응답은 `publication_grant`(기존 safe10 DTO), `available_actions`, `reason_codes`, `base_revision`, `connection_revision`만 제공한다. 토큰·참조·지문·소유 marker·scope·검사 원문은 반환하지 않는다.

`PublicationGrantManagementService`는 명시 주입된 읽기 resolver·grant store·client 등록·verifier·authorization_guard를 사용한다. 승인 정책은 grant의 공급자 allowlist, 실제 관측 scope와 현재 등록, 자격 만료, 초기화 상태를 확인한다. 앱·계약·비용 조건은 별도 서버 guard가 승인해야 하며 기본 미등록은 거부한다. 승인·회수·자격 검사 동안 OAuth writer guard를 유지한다. 생성자·조회는 grant DB를 생성하지 않는다. 승인 TTL은 서버 정책과 실제 자격 만료 중 짧은 쪽으로 정한다.

## Google 읽기 권한 관측

YouTube는 고정 `channels.list(mine=true,part=id,status)`로 현재 채널 ID와 대상·subject 일치, `isLinked=true`, 실제 upload scope를 확인한다. 여기서 subject는 Google 사용자 ID가 아니라 기존 OAuth 연결에서 관측한 채널 ID다. Blogger는 `users/self`와 해당 blog의 `blogUserInfos.get`으로 현재 사용자·blog ID·ADMIN 또는 AUTHOR 역할을 확인한다.

이 관측은 인증·게시 권한에 관한 증거다. 남은 quota, 업로드 제한, 콘텐츠 정책 수락 또는 실제 공개 성공을 보증하지 않는다. 이후 실행 permit·STOP·프로필/계정 잠금·게시 결과 확인은 계속 필요하다.

`GooglePublicationTransport`는 기본 fetch=None이고 네트워크를 호출하지 않는다. 서버가 기존 `common.oauth.transport.urllib_fetch`를 명시 등록할 수 있는 구현을 제공한다. 고정 HTTPS GET만 허용하며 토큰은 Authorization 헤더에 넣는다. TLS 검증, proxy·redirect 차단, 최대 30초·256KiB, 중복 JSON·오류·비밀 필드 차단이 적용된다. 실제 등록 전 공급자 앱·계약·비용 증거를 별도 확인해야 한다.

## 남은 필수 범위

실제 앱·비용·OAuth 재동의 수락과 서버 조립, 부모 발행 adapter 전환·native child 등록, 실제 계정/대상 발행과 공개 검증이 남아 있다. 나머지 SNS 공급자 verifier, 전체 제작 품질·성과·자료 이행·Mac/휴대폰 외부 HTTPS·전체 종합 수락도 계속 필요하다. [기존 grant 경계](managed-publication-authority.md)와 함께 적용한다.
