# Mac·휴대폰 HTTPS 접속

현재 기본 관리 웹은 127.0.0.1:8769이며 외부에 공개하지 않는다. 실제 도메인·TLS·proxy 설정과 Mac/휴대폰 외부망 수락은 아직 남아 있다. 이번 정책 코드와 가짜 HTTPS 헤더 시험을 실제 TLS 연결 완료로 해석하지 않는다.

## 명시 기동 정책

`production_main.py`의 `--public-origin https://<확정한-hostname>`은 별도 외부용 관리 서버에만 지정한다. 호스트는 소문자 DNS 이름이며 포트·경로·쿼리·IP 주소는 받지 않는다. `--check`에서 문법만 무변이 점검하고 `--serve`에서 정책을 주입한다. 원본 `--source-root`, 별도 `--workspace-root`와 loopback 바인딩은 유지한다. 로컬 도구·음성·이미지·영상·성과·제작 기동 옵션은 각각 독립이며 외부 출처 설정만으로 켜지지 않는다.

외부 모드에서는 고정 Host와 HTTPS Origin만 허용하고, 내부키 `X-AX-Internal` 헤더는 값과 관계없이 거부한다. Forwarded/X-Forwarded 헤더로 보안 정책·사용자 IP·허용 origin을 바꾸지 않는다. 쿠키는 기존 HttpOnly·SameSite=Strict·Path=/·Max-Age를 검증하고 Secure를 붙인다. Domain 속성은 사용하지 않는다. HSTS는 1일이다. 이 코드는 단일 운영자 인증을 유지하며 개인/학과 필터를 별도 사용자 ACL로 바꾸지 않는다.

고정 도메인 앞의 TLS 종료 proxy는 원래 Host를 정확히 전달하고 인증·본문·자산을 캐시하지 않아야 한다. 관리 웹 소켓은 외부 주소에 직접 바인딩하지 않는다. 기존 로컬 서버와 별도 loopback 포트로 운영하여 로컬 로그인과 외부 정책을 섞지 않는다. 로그인 제한은 socket peer 기준이므로 proxy 뒤에서는 사용자별 제한이 아닌 공유 제한임을 고려한다. proxy가 보내는 IP 헤더를 임의 신뢰하도록 풀지 않는다.

## OAuth와 미디어 분리

`--public-origin`은 OAuth 앱 등록·권한·callback 수락을 활성화하지 않는다. OAuth callback은 기존 `OAuthCallbackPolicy`의 정확한 redirect URI·신뢰 proxy IP·TLS 증거 검사를 추가로 통과해야 한다. 실제 앱과 도메인의 callback 설정을 별도로 검증해야 한다.

Instagram 익명 미디어 URL은 관리 서버에 연결하지 않는다. `assemble_media_delivery`의 별도 127.0.0.1 listener를 공개 미디어 hostname의 `/media/v1/` 경로에만 연결한다. 관리 서버와 미디어 서버 모두 같은 관리 workspace 아래 `media-leases` 저장소를 사용한다. 미디어 proxy는 정확한 Host를 전달하고 Forwarded/X-Forwarded 헤더를 제거하며 토큰 URL access log·캐시·변환·redirect를 사용하지 않는다. GET/HEAD/MP4 Range와 만료·회수 뒤 차단을 외부 HTTPS에서 실측한다.

현재 설치 도구 탐색에서는 cloudflared 실행 파일만 확인됐다. 설정·계정·tunnel·도메인 연결은 확인하지 않았으며 실행하지 않았다. 사용자의 도메인 선택 후 무료 방식/기존 도메인 방식과 운영 설정을 확정한다.

## 남은 실제 수락

Mac과 휴대폰 외부망에서 로그인·로그아웃·세션 만료·계정 전환·원고 저장 충돌·자산 다운로드·정지 표시·재시작을 확인한다. 위조 Host/Origin/내부키·미인증 API/자산·OAuth 실패를 함께 확인한다. 실제 공개 미디어 다운로드 바이트와 Meta 수락, 별도 SNS 운영 활성화·스케줄 전환·성과·자료 경로 이행은 여전히 필수다.

원복은 해당 외부 listener와 proxy를 중단하고 `--public-origin`을 생략한 기존 로컬 기동 설정을 사용한다. 운영 자료·키·기존 스케줄은 이 기능에서 이동하거나 변경하지 않는다.
