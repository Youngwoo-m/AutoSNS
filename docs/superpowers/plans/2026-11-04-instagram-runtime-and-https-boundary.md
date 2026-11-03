# Instagram 서비스 조립과 외부 HTTPS 경계

승인된 Mac·휴대폰 외부 접속 및 계정별 발행 목표의 다음 단계다. 실제 도메인은 확인 중이며 지금 외부 노출·실계정 호출은 시작하지 않는다.

1. InstagramApiClient와 공식 SDK 계약을 대조하고 고정 graph.facebook.com HTTPS transport를 구현한다. 기본 비활성, 재시도·리다이렉트·환경 프록시 없이 Authorization 헤더만 사용한다. 캐러셀 children 직렬화는 공식 SDK와 맞춘다.
2. 매 발행 문맥마다 고정되는 미디어 factory와 명시 조립 함수를 구현한다. 실제 검토·STOP·실행 허가를 합성하고 기본 기동/저장소 초기화는 하지 않는다.
3. 관리 웹에 명시 HTTPS origin 정책을 추가한다. 기존 loopback 모드는 유지하고, 별도 고정 hostname·HTTPS Origin·Secure/HttpOnly/Strict 쿠키·외부 내부키 차단을 한 묶음으로 적용한다. 전달 헤더에서 보안 정책을 유도하지 않는다.
4. 격리 fake HTTPS·loopback HTTP로 요청 형식, 비밀값 차단, 인증·Host/Origin·cookie·OAuth callback 경계를 검증한다. 기존 관리 웹은 로컬 정책 그대로 둔다.
5. 도메인 답변 후 실제 접속 수단과 DNS/TLS·proxy 설정을 구체화한다. 실제 OAuth 권한/운영 서비스 등록, 공개 미디어 fetch·Meta 수락, Mac·휴대폰 실접속, 나머지 채널/성과/이행/종합 수락은 필수 후속 범위로 유지한다.

## 구현·검증

1~4 코드와 격리 시험을 완료했다. 공식 SDK의 list 폼 JSON 인코딩과 맞춰 client의 캐러셀 children 직렬화를 변경했고 기존 client/미디어 계약 시험도 함께 갱신했다. 실제 API 요청은 하지 않았다.

- 발행기 전체: 381개 성공. `/private/tmp/autosns-instagram-runtime-publishers.log`
- 외부 정책·실제 임시 loopback HTTP·기존 웹 서버·채널 준비 상태·production main/application: 80개 성공. `/private/tmp/autosns-external-boundary-final.log`
- 실제 관리 workspace에서 `production_main.py --check --public-origin https://console.example.com` 구문 점검 성공. 이 예시 hostname으로 네트워크를 열지 않았다. 실행·제작·이미지·음성·영상·성과 비활성, native probe 및 할당량 변경 없음.
- 8769는 기존 로컬 정책으로 재기동했다. `/login` 200, 무인증 채널 준비 상태 API 401, 로컬 응답에 외부 HSTS 없음.

5의 실제 도메인 선택·TLS/proxy·외부망 수락은 미완료이며 사용자에게 도메인 여부를 비동기 질문했다. 기존 게시·스케줄·자격·교차 경로는 변경하지 않았다. 전체 프로그램 목표는 계속 진행 중이다.
