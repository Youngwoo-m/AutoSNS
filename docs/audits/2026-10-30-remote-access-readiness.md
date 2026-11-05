# Mac·휴대폰 외부 접속 준비 조사

2026-10-30. 현재 작업 사본의 비밀 아닌 소스·설정 예시·문서를 읽기 전용 조사했다. 네트워크 호출, 서버/프록시 기동, 실제 인증 파일·환경값·VPN 계정 조회, 설정 변경을 하지 않았다. 이 문서만 작성했다. 현재 소스가 제공하는 보호와 외부 접속에 필요한 후속 작업을 구분하며 실제 외부 접속이나 계정 준비가 완료됐다는 증거는 없다.

## 결론

새 운영 웹은 명시적으로 loopback 전용이다. `AX_HOST`를 외부 주소로 바꿔도 factory가 거부한다. HTTPS 외부 출처를 그대로 전달하는 일반 프록시는 현재 Host/Origin 검사에 걸린다. 따라서 단순 포트 공개나 Origin 검사 삭제로 해결할 수 없으며, 기본 loopback 보호를 유지한 채 신뢰하는 외부 접속 계층·공개 출처·세션·내부 API 경계를 별도로 설계해야 한다.

현재 사용자 확정 범위는 Mac과 휴대폰 외부 접속이다. 화면 설계는 서버를 바로 인터넷에 공개하지 않고 보호된 외부 접속 계층과 로컬 제작/브라우저 워커 연결을 별도로 설계하도록 한다(`docs/superpowers/specs/2026-10-30-account-web-screens-design.md:16`). 이전 설계 문서의 ‘이 Mac 안에서만’·‘외부에는 읽기만’ 설명은 legacy 콘솔의 배경이며, 확정된 새 운영 웹의 최종 범위를 축소하는 근거로 쓰지 않는다.

## 1. 현재 동작의 코드 근거

| 항목 | 확인한 소스 | 현재 계약과 외부 적용 영향 |
|---|---|---|
| 바인딩 | `ax-console/app/web_server.py:559` create_server, `:602` main | IPv4/IPv6 loopback만 허용. AX_HOST 기본127.0.0.1, AX_PORT 기본8767. TLS listener·프록시 모드는 없음 |
| Host | `web_server.py:251` 중복 헤더 거부, `:256` Host 검사, `:594` allowed_hosts | 실제 loopback 주소:port 및 localhost:port만 허용. 외부 도메인 allowlist 설정은 없음 |
| Origin/Fetch metadata | `web_server.py:260` | Origin이 있으면 정확히 `http://`+Host여야 하며 cross-site를 거부. https 외부 Origin은 현재 불허. GET와 변경 요청 모두 공통 검증 |
| 요청 정규화 | `web_server.py:236` _validated_target | 절대 URL/이중slash/역슬래시/제어문자/경로탈출·잘못된 query·중복 민감 헤더·Transfer-Encoding 거부. 외부 계층에서 이를 우회 정규화하지 않아야 함 |
| 일반 인증 | `web_server.py:110` _VersionedAuth, `:158` _load_auth, `:301` _token | 기존 비밀번호를 재사용하되 web-v2 세션 저장소와 ax_web_session 쿠키를 별도 사용. 비밀번호 파일 버전 변경/삭제/재생성으로 기존 웹 세션 무효화 |
| 로그인 제한 | `auth.py:87` _limited, `web_server.py:543` verify | 프로세스 메모리에서 IP당1분 내 실패5회 이후 제한. 현재 전달 IP는 self.client_address[0]. 프록시 뒤에서는 프록시 IP가 됨. 임의 X-Forwarded-For를 믿는 코드는 없음 |
| 세션 | `auth.py:25`, `:111`, `:125` | 임의 토큰의 해시만 저장, 최대30일/미사용3일 만료,5분마다 사용시각 갱신. 외부 배포에서도 비밀번호 버전·로그아웃·만료 계약을 유지해야 함 |
| 쿠키 | `auth.py:155`, `:159` | Path=/; HttpOnly; SameSite=Strict; Max-Age. Secure/Domain 속성은 현재 없음. HTTPS 외부 배포용 발급/삭제 계약이 필요하며 모든 요청 헤더의 scheme을 신뢰해 결정하면 안 됨 |
| 내부 키 인증 | `web_server.py:303` _authed | 기존 파일의 X-AX-Internal과 상수시간 비교가 맞으면 일반 세션 없이 인증. 별도 scope/공개경로 분리는 없음. 프록시로 외부 요청이 loopback에서 왔다고 내부 호출로 인정해서는 안 됨 |
| 상태 변경 | `web_server.py:333` _dispatch, `:525` _post | 공통 Host/Origin 이후 인증된 관리 API. 별도 CSRF 토큰은 없으며 현재 SameSite·Origin·Fetch metadata·JSON body 검증에 의존. 외부 배포에서도 교차 출처 변경을 허용하지 않는 증거가 필요 |
| 응답 보호 | `web_server.py:208` _send_response | no-store, nosniff, no-referrer, X-Frame-Options DENY, CSP(frame-ancestors none/form-action self). CSP의 script/style unsafe-inline은 현 구현 사실. HTTPS 전용 응답 정책은 아직 없음 |
| 프런트 요청 | `ax-console/app/web/api.js:3`, `:33` | 상대 /api/v2 경로, credentials same-origin, cache no-store. 외부 웹에서 localhost API로 직접 부르는 구조가 아니며 같은 공개 출처로 전달하는 편이 현재 계약과 맞음 |
| 로컬 브라우저 워커 | `ax-console/app/browser_worker.py:4`, `:226`, `:306` | 별도127.0.0.1:8711 및 내부 키. 이 모듈은 최상위에서 키를 읽으므로 조사 중 import하지 않음. 외부에 크롬 디버깅 포트·워커 API를 공개하는 설계 근거가 없음 |
| 운영 실행 비활성 | `web_server.py:583` 부근 | ExecutionPolicy 기본 disabled, recovery adapters/probes 기본 미등록. 외부 접속 연결만으로 실제 발행 권한을 켜서는 안 됨 |

계정 필터는 개인·학과 자료의 조회 범위다. 현재 인증은 한 운영자 비밀번호/세션이며 개별 사용자별 계정 접근권한 체계라고 주장할 수 없다. 사용자가 여러 운영자 권한 분리를 요구할 경우 별도 요구 확인이 필요하다.

## 2. 저장소의 외부 접속 구성 확인 범위

- `rg --files`의 경로명과 `ax-console`, `common`, `docs`의 비밀 아닌 소스/문서에서 reverse proxy, nginx, caddy, tunnel, trusted proxy, forwarded header 관련 항목을 검색했다. 새 운영 웹에 적용되는 실행 가능한 리버스프록시/TLS/외부 접속 배포 설정은 이 조사 범위에서 찾지 못했다.
- `personal/engineer-question-worker/deploy*.py`라는 별도 배포 파일명은 존재하지만 새 운영 웹의 외부 계층이라고 연결할 근거가 없다. 다른 서비스 배포를 그대로 재사용 가능하다고 판단하지 않았다.
- 사용자 Mac의 설치 앱, 시스템 서비스, 라우터, VPN, 도메인/DNS/인증서, 방화벽, 실제 외부 포트 개방 상태는 조회하지 않았다. 저장소 내 구성 부재가 외부 인프라 전체 부재를 증명하지는 않는다.
- 실제8769/8767의 현재 프로세스·소켓·계정 상태도 이번 조사에서 확인하지 않았다. 개발 서버 반영 증거는 별도4단계 수락 기록을 따른다.

## 3. 후속 설계에 고정할 경계

1. **기본 배포 유지:** 명시 외부 배포 설정이 없으면 지금과 같은 loopback·로컬 Host/Origin·로컬 쿠키로 실행한다. 외부 도메인 임의 추론·wildcard origin·0.0.0.0 자동 바인딩은 하지 않는다.
2. **공개 출처와 실제 소켓을 구분:** 공개 scheme/host/port allowlist를 서버 소유 설정으로 지정하고 신뢰하는 접속 계층만 전달할 수 있게 한다. 외부 클라이언트가 넣는 Forwarded/X-Forwarded-*로 인증·Secure 쿠키·Host 검사를 우회하지 못해야 한다. HTTPS Origin을 허용하려고 Origin을 제거하거나 고정 http 로컬 값으로 덮는 방식은 출처 증거를 없앤다.
3. **내부 API 분리:** 외부 요청의 X-AX-Internal을 접속 계층에서 거부/제거하고 앱에서도 외부 경로에 내부키 인증을 허용하지 않는 방어를 둔다. 브라우저 워커·디버깅·기존8700·키/토큰 파일은 공개 라우팅 대상에서 제외한다. 원격 UI의 작업은 기존 서버의 검증된 API/원장/permit으로만 전달한다.
4. **HTTPS 세션:** 외부 쿠키는 Secure+HttpOnly+SameSite와 발급/삭제의 동일 scope를 사용한다. 비밀번호 버전 무효화·동시 세션 파일 잠금·로그아웃·만료를 보존한다. 쿠키는 포트로 격리되지 않으므로 QA/실운영이 같은 호스트를 쓰면 이름/저장소를 분리해야 한다.
5. **요청·로그 경계:** 변경 요청의 동일 출처 검증을 유지하고 헤더 부재/위조/교차site 요청을 시험한다. 업로드 크기·대기시간·클라이언트 연결 종료·반복 전송·IP 제한을 프록시와 앱 양쪽에서 일치시킨다. IP는 신뢰 경계가 정해지기 전 클라이언트 헤더에서 선택하지 않는다. 비밀번호·세션·내부키·요청 본문을 접속 로그에 남기지 않는다.
6. **로컬 워커 독립:** 휴대폰 연결이 끊겨도 이미 접수한 작업을 재생성하지 않는다. 원장 request key/CAS와 조회로 결과를 회수한다. Mac sleep/워커 부재/프로필 사용 중/STOP은 명시 상태로 보이고 원격 UI 접속 성공을 실행 가능으로 해석하지 않는다.

위 항목은 제품/공급자 추천이 아닌 현재 소스 계약을 외부에서도 유지하기 위한 요구다. 외부 인프라 선택·도메인·접근 주체·접속 계층 인증 방식은 아직 확정하지 않았다.

## 4. 후속 수정 파일 지도

| 파일 | 제안 책임 | 유지할 기존 계약 |
|---|---|---|
| `ax-console/app/web_server.py` | 명시 deployment/public origin/trusted transport 주입, 외부/내부 인증 경로 분기, 로그인 제한의 신뢰 IP 전달 | loopback 기본, 중복 헤더·query·body·출처 검사, source/workspace 분리, 기본 실행 disabled |
| 신규 `ax-console/app/web_access.py` | 단일 책임의 외부 접속 정책 자료형·정규화·allowlist·신뢰 헤더 검증. import/constructor 부작용 없음 | 외부 요청값을 정책으로 승격하지 않음 |
| `ax-console/app/auth.py` 또는 신규 웹 전용 cookie adapter | HTTPS 모드의 Secure 쿠키 발급/삭제·세션 이름 분리 | 기존8700 쿠키 동작을 전역 변경하지 않음. web-v2 세션과 비밀번호 버전 계약 보존 |
| 신규 `ax-console/config/remote-access.example.json` | 비밀 없는 공개 출처/전송 모드 예시. 실제 계정/키/도메인 기본값은 넣지 않음 | 미지정이면 외부 모드 비활성 |
| 후속 선택 접속 계층의 신규 배포 예시 | TLS 종료/접근 통제, upstream loopback, 공개 경로 allowlist, 내부 헤더 차단, 로그 정제 | 8700/8711/Chrome debug 비공개. 실제 설정 적용은 별도 수락 |
| 신규 `tests/test_web_access.py`, `tests/test_remote_access_integration.py` | 아래 로컬 계약·접속 계층 통합 시험 | 실제 외부 인프라 성공을 fixture로 대체하지 않음 |
| `tests/test_web_server.py` | 기존 로컬 보호·인증 시험에 외부 모드 회귀 추가 | 기존 기본 거부 시험 계속 통과 |
| `ax-console/docs/운영웹_사용법.md`, 신규 `docs/runbooks/remote-access.md` | Mac/휴대폰 접속·재인증·세션 만료·워커 부재·철회/롤백 안내 | 실제 보호층/계정 준비 미확인을 완료로 표기하지 않음 |

이 파일 지도는 조사 결과에 따른 제안이다. 본 조사에서 신규 실행 파일·설정·시험은 만들지 않았으며 구현 계획 승인이나 제품 선택을 대신하지 않는다.

## 5. 배포별 수락 시나리오

### 기본 로컬 배포

- 비명시 외부 주소 바인딩 거부, 로컬 Host/Origin 허용, 외부/중복 Host·Origin·cross-site·이상 request target 거부.
- 기존 비밀번호 변경/삭제/재생성 시 세션 무효, 미인증401, 원본 인증/운영 자료에 부수 쓰기 없음(의도된 세션 저장 제외).
- 기존 내부 호출은 로컬 전용 경로에서 동작하며 키가 화면/로그/응답에 노출되지 않음.

### 보호된 외부 접속 계층의 임시 통합 배포

- 허용된 HTTPS 공개 origin의 로그인/조회/저장/자산 업로드가 성공하고 외부 임의 origin·가짜 Forwarded/X-Forwarded-*·내부키 헤더는 거부된다.
- 외부 쿠키 발급/삭제 scope 일치와 Secure/HttpOnly/SameSite, 만료·로그아웃·비밀번호 버전 변경을 실제 브라우저에서 확인한다.
- 공개 주소의8700/8711/Chrome debug/운영 파일 경로는 접근 불가. 외부 세션 없이 내부키로 우회 인증 불가.
- 저장 성공 후 모바일 연결이 끊겨도 재전송 시 같은 request key/결과를 회수하고 중복 원본/배포를 생성하지 않는다.409/401/503에서도 입력을 보존한다.
- 업로드 크기 제한·연결 시간 초과·로그인 실패 제한·여러 기기 로그인/로그아웃의 관측을 확인한다. 프록시 peer IP 하나로 모든 사용자를 오인하거나 위조 IP로 제한을 우회하지 않는다.

### 실제 Mac·휴대폰 외부 경로

- Mac과 휴대폰에서 같은 보호된 주소로 접근·로그인·계정 필터·개인→학과 교차 배포 상세·원고 저장·조회·로그아웃을 확인한다. 휴대폰은 Mac과 다른 실제 접속 경로에서도 검증한다.
- 320px 세로/회전·느린 연결·백그라운드 복귀·세션 만료에서 화면/편집 보존을 확인한다. 로컬320px fixture만으로 외부 접속 성공이라 하지 않는다.
- Mac sleep/오프라인/워커 중지·프로필 점유·STOP을 실제 관측하며 명확한 대기/차단 상태로 표시한다. 접속층 재시작이 작업/lease/예약을 재생성하지 않는다.
- 접속 철회/보호층 중지 후 외부 접근이 차단되고 기존 로컬 UI·원장·잠금·스케줄이 보존된다. 원격 공개 상태를 잊는 DB 복원으로 롤백하지 않는다.

## 조사 한계

정적 소스 근거만 확보했다. HTTP/브라우저/외부 인프라 시험을 실행하지 않았고 실제 VPN·DNS·인증서·포트·접근 계정 상태는 미확인이다. 따라서 `remote_access_ready=false`다. 위 수락을 실제 선택된 배포 방식과 사용자 기기로 입증하기 전 전체 목표의 Mac/휴대폰 외부 접속 항목은 미완료로 유지한다.
