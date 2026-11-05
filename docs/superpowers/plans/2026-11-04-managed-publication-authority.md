# 관리 OAuth 발행 사용 경계

기존 읽기 동의, 실제 토큰의 관측 scope, 대상별 게시 가능 증거, 명시 사용자 승인, 콘텐츠별 실행 permit을 분리한다. 토큰에 쓰기 scope가 있다는 이유만으로 발행을 허용하지 않는다. 현재 실제 OAuth/발행 기동은 비활성이고 이 구현으로 기본값을 바꾸지 않는다.

1. 읽기 전용 기본값을 보존하는 서버 scope 동의 정책을 추가한다. 명시 client/evidence revision과 정확한 읽기+발행 scope 조합만 재동의 대상으로 허용하며 정책 revision을 attempt와 callback에 결속한다. 기존 읽기 HMAC은 유지한다.
2. 기존 OAuth workspace 소유자에 결속된 별도 발행 사용 grant 저장소를 추가한다. 실제 공급자 관측을 검증하는 신뢰된 코드와 사용자 승인 절차만 typed evidence를 발급할 수 있다. HTTP로 권한·대상·scope를 자가 신고하여 grant를 만드는 경로는 제공하지 않는다.
3. grant를 계정·대상·공급자 주체·registry/client/evidence revision·자격 세대/참조 지문·관측 scope·만료와 대조하는 authorizer를 연결한다. resolver 기본은 publication 거부, 승인자가 있더라도 grant와 실제 token scope를 모두 확인한다.
4. 자격 use 전체의 동일 프로세스/스레드·소유·세대·만료·grant 유효성을 재검증한다. scope 종료 뒤 SDK와 복사본을 재사용하지 못하게 한다. 자동 refresh나 legacy 자격 fallback으로 승인 경계를 우회하지 않는다.
5. BridgeHost는 자격 검증 후 허가를 redeem하고 handler가 끝날 때까지 자격 범위를 유지한다. 잠금 순서는 OAuth writer → publication gate → DB이며 외부 API 동안 publication gate는 해제한다. 기존 호출형 자격과 브라우저 profile 연결은 보존한다.
6. 가짜 vault·실제 격리 grant DB·가짜 SDK/bridge로 승인/회수/만료/세대 변경/범위 종료·오류·복구를 검증한다. 실제 키·Keychain·OAuth 로그인·API/발행·운영 전환은 수행하지 않는다.

실제 공급자별 권한 검사와 grant 승인 UI, 서버 기동 설정·native 서비스 조립, 실제 재동의·게시 수락은 후속 필수 범위다. 기존 authorization.publication_status에 사용자 체크로 verified를 추가하지 않는다. TikTok 내부 업로드 도구, Naver 프로필 API, 종료된 Tistory API를 발행 grant로 우회하지 않는다. 모든 기존 교차 경로·운영 키·스케줄을 보존한다.
