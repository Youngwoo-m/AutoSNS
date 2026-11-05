# SNS OAuth 설계 builder check

2026-10-31 · 읽기 전용 검토. 검토 대상은 `docs/superpowers/specs/2026-10-31-sns-oauth-connections-design.md`다. 실제 코드 구현·계정 연결·네트워크 호출을 수행하거나 승인하지 않았다. 아래 변경 제안은 설계 문서 보완 사항이다.

## 판정

OAuth 화면부터 UI·서버 계약·격리 검증을 함께 개발한다는 사용자 선택과 일치한다. 기존 9개 메뉴, 개인/학과 분리, 공식 미지원 Tistory 상태, 인증·읽기·발행·실행의 분리도 유지한다. 다만 아래 세 항목은 구현자가 동작을 추정해야 하므로 설계 승인 전에 구체화해야 한다. 공식 endpoint/권한 미확인을 차단 상태로 유지한 것은 누락이 아니라 올바른 gate다.

## 필수 수정

### P1 — Strict 쿠키와 callback 성공 경로가 서로 맞지 않는다

근거: 설계의 보안 계약은 callback에 현재 세션을 요구하고 Strict 쿠키 누락 시 재로그인 후 새 시도를 안내한다. 기존 `ax-console/app/auth.py:155`는 `SameSite=Strict`이며 `ax-console/app/web_server.py:278`은 `Sec-Fetch-Site=cross-site` 요청을 거부한다. 외부 OAuth 사이트에서 돌아오는 통상적인 브라우저 callback은 이 두 경계와 충돌한다. 같은 조건으로 재로그인·재시도만 하면 성공 경로가 생기지 않는다.

필수 수정: 개발 1단계의 가짜 adapter 흐름과 실제 provider 연결 수락을 구별하고, 실제 연결에는 세션 결속을 보존하는 callback 수신·재개 계약이 확정되어야 함을 명시한다. 외부 HTTPS Origin/허용 host/신뢰 프록시/Secure 쿠키와 함께 정해야 하며, callback 경로 예외의 위치·적용 헤더·허용 파라미터도 지정한다. 기존 일반 GET·POST 검사를 전역 완화하지 않는다. 아직 방식을 정하지 않는다면 해당 provider의 실연결을 `registration_blocked`로 남기고 재시도 안내가 해결책인 것처럼 표시하지 않는다. 이는 [외부 접속 경계](2026-10-31-external-access-boundary.md)의 기존 미완 항목으로, 지금 새로운 네트워크나 유료 중계를 도입할 필요는 없다.

### P1 — 토큰 교환·갱신까지 비용 0 gate의 적용 범위를 명시해야 한다

근거: 설계는 시도 생성의 scope/cost gate와 유료 principal 조회 금지는 명시하지만, callback token 교환 및 장기 토큰 교환·refresh·revoke의 비용 판정 조건은 호출 직전 계약으로 구체화하지 않는다. [Meta 조사](2026-10-31-meta-connection-research.md)는 비용 미확인을 무료로 표기하지 않으며, [기타 SNS 조사](2026-10-31-other-sns-connection-research.md)는 X principal 조회의 크레딧 소비를 별도로 차단한다. 이 자료가 모든 인증 endpoint의 유료 여부를 증명하는 것은 아니다.

필수 수정: 비용 0 제약은 authorize 이후 모든 외부 호출에도 적용한다고 명시한다. endpoint별 비용 증거·승인 범위를 시도에 고정하고 호출 시 재검증하며, 미확인은 차단한다. 동의 버튼이나 OAuth 성공을 결제수단 등록·구매·자동충전·보유 크레딧 소비의 허가로 해석하지 않는다. 무료라고 증명된 token 교환과 유료 principal 조회는 별도 gate로 처리할 수 있다. 추가 비용을 허용할지 묻는 선택지는 현재 사용자 조건과 맞지 않는다.

### P2 — registry와 비밀 없는 연결 상태의 쓰기·복구 주체가 불명확하다

근거: 설계는 `ConnectionStateStore`와 credential generation/reference CAS를 제안하지만, 어떤 저장소의 어떤 revision을 전환하는지 정하지 않는다. `common/operations/registry.py:1`은 파일을 변경하지 않는 판독기이고 `Connection`은 frozen 모델이다. `load_registry`는 credential reference가 registry credentials에 실제 존재하며 같은 account인지 검증한다. 신규 Keychain reference를 별도 상태 저장소에만 넣으면 기존 registry/resolver와의 일관성이 자동으로 생기지 않는다. target proposal의 confirm도 신규 connection/credential 등록 및 registry revision 변경 주체가 필요하다.

필수 수정: registry를 변경하는 서비스와 상태 저장소 간 원자성·revision 계약을 문서로 확정한다. 기존 불변 target의 자동 덮어쓰기는 금지하고, 신규 연결 확정 시 credential 소유 검증(account 및 provider/platform), target 확인, registry/state 참조 공개 순서 및 장애 복구를 명시한다. `connected`는 Keychain 기록 성공, 유효 reference 전환, principal/target 확인이 모두 완료된 뒤에만 공개한다. Keychain 실패·CAS 충돌·프로세스 중단 시 기존 연결을 유지하고 신규 시도는 실패/대기 상태로 남긴다. 설계에 이미 있는 “신규 비밀 기록 → CAS → 구세대 폐기”를 이 두 저장소에 어떻게 적용할지만 보완하면 된다.

## 이미 근거로 해결된 사항

- state의 서버 발급·hash 저장·10분 만료·일회 소비·세션/account/provider/connection 결속, 중복 callback의 원자 소비는 요구가 충분하다. account 필터 `all`을 연결 대상에 허용하지 않는 것도 적절하다.
- CSRF는 기존 Origin 검사와 별개인 동기화 토큰을 모든 사용자 mutation에 추가하도록 명시되어 있다. 내부키 인증을 브라우저 세션 또는 사용자 OAuth 동의의 대체로 허용하지 않는다는 한 문장을 추가하면 기존 이중 인증 경계와 연결하기 쉽다.
- 토큰·secret·verifier를 브라우저/IntegrationStore/평문 secret_env에 저장하지 않고 Keychain의 잠김·거부를 차단하는 방향은 맞다. 실제 OS 승인과 무인 접근 가능 여부는 수락 단계 입력이다.
- Instagram login 방식 분리, Threads 독립 connection, Facebook Pages 한정, TikTok 읽기/업로드/발행 분리, X 비용 미확인 차단, Tistory unsupported는 두 조사 문서와 모순되지 않는다. 등록·권한·PKCE 미확인을 구현자가 임의로 채울 이유가 없다.
- 공개 `Connection.target_status`가 target ID 존재만으로 verified가 되는 기존 의미와 원격 증거를 구별하겠다는 설계 방향은 맞다. 새 공개 projection에서 별도 인증 상태를 병기하고 기존 플래그를 원격 검증 증거로 재사용하지 않으면 된다.

## 선택 질문

현재 사용자에게 반드시 물어야 할 추가 질문은 없다. 위 세 항목은 안전한 차단 기본값과 기존 조사 근거로 설계자가 먼저 보완할 수 있다. provider별 계정·scope·target·등록 앱·저장 위치의 실제 입력은 이미 규정된 실연결 체크포인트에서 구체적으로 제시하면 된다. 이번 검토를 근거로 구현이나 실계정 연결을 시작하지 않는다.

## 동일 범위 재검토 — 필수 3건 반영 확인

2026-10-31. 수정된 설계 문서만 다시 읽고 위 세 지적의 해결 여부를 확인했다. 기능 범위·제품 코드는 변경하지 않았으며 실계정 동작은 수행하지 않았다.

|기존 지적|재검토 판정|수정 근거|
|P1 Strict 쿠키/callback 성공 경로|설계 수준 해결|`receive_callback`은 제한된 cross-site 수신만 처리하고, code/ticket을 Keychain에 임시 보관한 뒤 query 없는 same-origin 화면으로 이동한다. `continue` POST가 원래 세션/actor/account/provider 결속·CSRF·일회 소비를 검증한 뒤 교환한다. Strict 쿠키를 유지하며 일반 요청 검사를 전역 완화하지 않는다. ticket 만료·재사용·세션 불일치 시험도 명시했다.|
|P1 모든 인증 endpoint의 비용 0 gate|설계 수준 해결|`assert_zero_cost`를 authorize 및 token/장기교환/refresh/revoke/principal의 모든 외부 호출 직전에 실행한다. 증거 revision을 동결·재검증하고 unknown/paid/credit은 외부 전송 0으로 차단한다. 결제·보유 크레딧 소비 허가와 동의를 분리했다.|
|P2 registry/Keychain 쓰기·복구 주체|설계 수준 해결|`ManagedConnectionStore` SQLite transaction이 쓰기 주체이며 `project_registry`가 소유 검증된 overlay/credential catalog를 합성한다. 원본 registry는 변경하지 않고 base/connection revision CAS를 적용한다. Keychain stage → SQLite active pointer 전환 → 구세대 정리와 재시작 orphan 정리, connected 공개 전제도 명시했다.|

이 세 항목에 대한 추가 필수 수정이나 사용자 질문은 없다. 이는 구현·동작 검증 완료 판정이 아니다. 실제 HTTPS callback의 host/proxy/Origin/Secure 쿠키 경계 수락 및 provider별 실연결은 설계에 적힌 별도 미완 gate로 유지한다.

## 기존 채널 근거 추가의 한정 재검토

2026-10-31. Google/Naver 공식 계약 감사 두 파일과 설계의 revoke 문단·기존 채널 표·마지막 보완절만 대조했다. 전체 설계 재검토나 네트워크·제품 변경은 하지 않았다.

- **Google 기존 발행 grant에 대한 원격 철회 위험: 설계 수준 해결.** 설계는 로컬 연결 해제가 overlay 및 진행 세대만 차단하고 기존 발행 자격·프로필을 변경하지 않는다고 명시한다. 원격 revoke는 별도 동작이며 project/client 분리와 기존 grant 영향이 미확인인 동안 차단한다. 새 client만으로 격리를 보장하지 않는다는 문구도 추가했다. 이는 [Google 감사](2026-10-31-google-oauth-compatibility.md)의 같은 project 내 다른 client token 영향과 일치한다. 해당 감사의 공식 근거는 [Google Web server OAuth](https://developers.google.com/identity/protocols/oauth2/web-server)다. 실제 project 분리나 기존 token 영향이 검증되었다는 뜻은 아니다.
- **Naver 로그인 성공을 블로그 발행 가능으로 승격할 위험: 설계 수준 해결.** provider 표는 회원 프로필 OAuth와 블로그 게시를 분리하고 글쓰기 API 종료를 명시하며 로그인 성공을 발행 가능으로 표시하지 못하게 한다. 기존 브라우저 세션 경로에는 별도 정책·권한·프로필 잠금 수락을 유지한다. 이는 [Naver 감사](2026-10-31-naver-oauth-compatibility.md), 그 안의 [공식 글쓰기 API 종료 공지](https://developers.naver.com/notice/article/7527) 및 [로그인 API 문서](https://developers.naver.com/docs/login/api/api.md)와 일치한다. 종료 공지를 브라우저 자동화 허용의 근거로 사용하지 않는다.

두 위험에 대한 추가 필수 수정·사용자 질문은 없다. 실제 원격 revoke·블로그 발행·실계정 연결의 수행이나 수락은 계속 별도 미완이다.
