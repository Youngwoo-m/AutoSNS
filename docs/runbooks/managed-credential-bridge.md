# 관리 OAuth 자격의 서버 읽기 경계

`ManagedCredentialResolver.use()`는 원본 OAuth 연결 저장소·작업공간 소유 context·인증된 owned backend를 서버가 주입해 사용하는 읽기 전용 경계다. 생성자나 발행 준비는 vault·SDK·네트워크를 호출하지 않는다. 논리 참조나 옛 토큰으로 fallback하지 않는다.

사용 시에는 정확한 작업공간 소유자, 연결 계정·플랫폼·대상·세대, connected/active 상태, 읽기 확인, 관측 scope와 저장 토큰 scope, 미래 만료를 검증한다. 자격 JSON은 크기·중복 키·형식을 검사한다. 자격을 읽은 뒤 연결과 토큰 만료를 다시 확인하고, 읽기 handler가 끝날 때까지 OAuth writer guard를 유지한다. 일반 값으로 자격을 resolve하는 API는 제공하지 않는다.

Google 변환은 `ManagedGoogleCredentialResolver.use()` 안에서만 한다. 새 동의나 refresh token·client secret·token URI를 넣지 않으며 자동 갱신에 기대지 않는다. SDK 만료 시각은 UTC로 정규화한다. 실제 API의 대상 확인과 호출 허용은 기존 서버 읽기 정책의 책임이다. 자격 읽기 자체가 API 사용이나 과금 허가를 뜻하지 않는다.

`build_managed_bridge_credential_catalog(registry, connection_ids=(...))`는 서버가 명시한 연결의 검증된 심볼 참조·계정·플랫폼만 BridgeHost에 제공한다. 자격 참조의 작업공간 증명은 실제 resolver가 검증한다. YouTube/Blogger adapter는 이 등록을 준비·읽기 대상으로 인식할 수 있다. 기존 고정 자격 별칭과 경로는 보존한다.

현재 인증 모델에는 새 자격의 발행 권한 확인 완료 상태가 없으므로 publication 범위는 항상 거부한다. adapter도 새 자격을 사용한 실제 제출 전에 미전송 실패를 반환한다. 최종 발행 permit·STOP·프로필 잠금·기존 비용 정책과 OAuth 차단을 해제하지 않았다. 기본 child bootstrap과 실제 서버에는 새 resolver를 활성화하지 않았다.

검증은 임시 작업공간 marker·메모리 owned vault·가짜 Google 자격 factory·가짜 조회 서비스·기존 child bridge 시험을 사용했다. 실제 Keychain·OAuth 로그인·자격 갱신·API·발행은 실행하지 않았다. 발행 권한 모델, 승인된 실제 공급자/앱 등록, child bootstrap과 운영 수락은 계속 필수 작업이다.
