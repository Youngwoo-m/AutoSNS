# 계정별 발행 사용 승인 관리

승인된 개인·학과 연결 화면 안에 발행 사용 승인 조회·명시 검사 후 승인·회수를 추가한다. 기존 4개 메뉴와 읽기 동의·발행 scope 추가 동의·콘텐츠 실행 승인을 보존한다. 구현 지속과 개발 후 종합 검토라는 사용자 지시에 따라 중간 승인 질문 없이 진행한다.

- GET `/api/v2/oauth/connections/<id>/publication-grant`: OAuth 사용자 세션, 현재 registry/overlay 소유 결속만 읽는다. vault/API/DB 초기화 없음.
- POST 같은 경로 `/approve` 또는 `/revoke`: 기존 Origin/CSRF 검증. 정확한 body는 request_key, expected_base_revision, expected_connection_revision, expected_grant_revision. target/scope/evidence/토큰/만료는 클라이언트가 제공하지 않는다. 재시도는 자동 수행하지 않으며 CAS가 중복 변경을 막는다.
- 응답: publication_grant(기존 safe10 DTO), available_actions, reason_codes, base_revision, connection_revision. 공급자 검사 미등록은 승인 가능으로 표시하지 않는다.
- 신뢰 서비스는 세션·현재 연결·소유자·자격 세대·등록 정책을 확인하고 OAuth writer 안에서 읽기 resolver를 연다. 신뢰 verifier만 실제 관측을 VerifiedPublicationEvidence로 반환한다. 대상과 주체·scope·만료를 재대조하여 승인한다. 유료 비용/앱/계약 미확인은 거부한다. 승인 TTL은 서버 정책이 정한다.
- Google verifier는 고정 읽기 endpoint에 대한 명시 주입 transport를 쓰며 토큰 실제scope·주체·대상·Blogger ADMIN/AUTHOR 권한/YouTube mine 채널을 검사한다. 네트워크 구현은 명시 등록 전 비활성이다. 가짜 transport 시험을 실제 수락으로 간주하지 않는다.
- 서버 publication service 기본 None. 실제 로그인·Keychain·API·게시·기존 스케줄 전환은 활성화하지 않는다. 기존 운영 경로는 수정하지 않는다.

서비스·공급자 검사·화면을 병렬 구현하고 root가 HTTP를 연결한다. 신규 시험과 기존 OAuth·웹·운영·발행 회귀 시험으로 확인한다. 전체 프로그램 종합 검토는 개발 완성 후 수행한다.
