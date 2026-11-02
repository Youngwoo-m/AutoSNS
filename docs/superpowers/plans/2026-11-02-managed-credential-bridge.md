# OAuth 연결 자격과 발행기 연결

새 OAuth 연결의 작업공간 소유 자격을 기존 발행기에 전달할 서버 경계를 만든다. 기존 계정별 암호화 토큰 경로와 자동 작업은 보존한다. 실제 OAuth 정책·비용 차단·계정 로그인·발행 활성화는 변경하지 않는다. 개발 완료 후 종합 검토한다는 요청에 따라 구현을 진행한다.

- 서버 전용 resolver는 managed connection snapshot과 workspace owner를 검증한 뒤 정확한 oauth:계정:채널:연결:세대 참조만 선택한다. connected/active, 읽기 확인, 실제 관측 scope·만료·작업 lease 없음과 OwnedCredentialRef를 확인한다. 논리 legacy ref로 fallback하지 않는다.
- 자격 읽기 전후 snapshot을 다시 대조해 회전·해제·연결 변경을 거부하고 읽기 handler가 끝날 때까지 OAuth 작업공간 writer guard를 유지한다. 현재 인증 모델에는 발행 권한 확인 완료 상태가 없으므로 새 managed 자격의 publication 범위는 항상 거부한다. OwnedStageBackend의 인증된 read_owned만 명시 호출하며 생성자·registry projection·prepare는 Keychain/API에 접근하지 않는다. 비밀은 private wrapper로만 반환한다.
- Google SDK 변환은 명시 factory에서만 수행한다. 자동 refresh·scope 확대·임의 token URL을 넣지 않는다. 원래 provider·계정·대상 결속을 유지한다.
- YouTube adapter는 서버 등록부의 검증된 managed credential entry를 허용하되, 실제 자격 조회와 최종 발행 permit은 기존 bridge host가 수행한다. 새 bootstrap 기본값이나 운영 schedule을 활성화하지 않는다.
- 가짜 owned backend·가짜 Google credential factory·기존 bridge host로 타 계정/작업공간/세대·회전·범위·만료·잠금·비밀 비노출·기존 경로 호환을 시험한다. 실제 OAuth/Keychain/발행 수락은 미완료 범위다.
