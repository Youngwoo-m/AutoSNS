# 관리 OAuth 발행 사용 승인 경계

현재 상태는 **운영 비활성**이다. 이 구현은 관리 OAuth 자격을 발행에 사용할 때 필요한 별도 승인 경계를 제공한다. 실제 OAuth 재동의, 공급자별 게시 권한 검사, grant 승인 화면, 운영 bootstrap과 native 서비스 조립은 아직 제공하지 않는다. 파일이 존재하거나 격리 시험이 통과했다는 이유로 운영 연결·스케줄·발행을 활성화하지 않는다.

## 읽기 연결, 발행 동의, grant, 콘텐츠 승인의 구분

| 구분 | 확인하는 내용 | 별도로 필요한 내용 |
|---|---|---|
| 관리 OAuth 읽기 연결 | workspace 소유, 현재 연결·대상·자격 세대, 관측 읽기 scope와 자격 만료 | 발행 scope 동의, 실제 대상별 게시 권한, grant |
| 발행 scope 동의 정책 | 서버가 등록한 앱·증거 revision에 대해 정확한 읽기+발행 scope 조합을 요청할 수 있는지 | 공급자의 실제 동의 결과와 권한 관측, 명시 사용자 승인 |
| 발행 사용 grant | 특정 workspace·연결·자격·대상·서버 정책에 결속된 제한 시간의 발행 자격 사용 승인 | 게시할 콘텐츠의 검토·승인, 실행 permit, STOP, 공급자별 비용·실행 관문 |
| 콘텐츠별 실행 permit | 해당 콘텐츠·배포 구성의 실행 승인 | 현재 자격·grant와 발행 직전 관문 재확인 |

토큰에 발행 scope가 들어 있다는 사실만으로 grant가 생기지 않는다. 발행 scope 동의도 콘텐츠를 게시하라는 승인이 아니다. grant가 있어도 특정 원고·자산을 검토한 것으로 처리하지 않는다.

기존 연결의 `authorization.publication_status`는 `not_checked` 또는 `blocked`를 유지한다. 사용자 체크나 로컬 상태 변경으로 `verified`를 추가하는 경로는 없다.

## 기본 거부와 공급자 제한

`PublicationScopeConsentPolicy`는 기본 등록 목록이 비어 있다. 기존 읽기 동의 경로를 유지하며, 발행 scope 요청은 서버가 명시한 policy revision과 `PublicationConsentRegistration`이 있어야 한다. 등록된 client revision, 비용 증거 revision, approved scope 집합이 현재 앱 등록과 같아야 하며 요청은 공급자 카탈로그의 정확한 읽기+발행 scope 집합이어야 한다. 해당 policy revision은 OAuth attempt와 callback 검사에 결속된다. 기존 OAuth 계약·앱 등록·비용 관문도 계속 적용된다.

`PublicationGrantPolicy`의 기본 revision은 `publication-grants-deny-v1`이고 `allowed_providers`는 빈 tuple이다. `ManagedCredentialResolver`도 `publication_authorizer`를 명시 주입하지 않으면 `scope='publication'`을 거부한다. grant DB의 존재나 읽기 연결 상태는 이 기본값을 바꾸지 않는다.

TikTok, Naver, Tistory는 발행 scope 동의 정책, grant 정책, resolver에서 별도로 차단한다. allowlist에 넣어도 우회되지 않는다. TikTok의 내부 계정 업로드 도구 적합성, Naver 프로필 API와 블로그 발행의 차이, 종료된 Tistory API 문제를 grant로 해결한 것으로 처리하지 않는다.

## 저장소와 승인 증거의 실제 계약

구현은 다음 소스에 있다.

- [`publication_grants.py`](../../common/operations/publication_grants.py): 정책·증거·문맥 자료형과 별도 승인 저장소
- [`publication_authority.py`](../../common/operations/publication_authority.py): 현재 관리 연결·앱 등록과 grant 대조
- [`managed_credentials.py`](../../common/operations/managed_credentials.py): 자격 사용 범위와 사용 중 재검증
- [`oauth_scope_consent.py`](../../common/operations/oauth_scope_consent.py): 명시 발행 scope 동의 정책

`PublicationGrantStore(workspace_context, policy=...)` 생성자는 I/O를 하지 않는다. 저장소 생성은 명시 `initialize()`에서 수행한다. 이미 초기화된 OAuth workspace 소유자를 검증하며 새 소유자나 OAuth 자격을 만들지 않는다. grant DB는 workspace 아래 `publication-grants.sqlite3`에 저장하고 권한 `0600`, application ID·schema·소유자 결속을 확인한다. 심볼릭 링크, 다른 소유자의 DB, 알 수 없는 schema 또는 잘못된 권한은 거부한다.

`PublicationGrantBinding`은 다음 내용을 결속한다.

- workspace 소유자: `workspace_id`, `root_binding`
- 현재 등록부·연결: `registry_revision`, `connection_id`, `account_id`, `platform`, `provider_id`
- 공급자 주체와 대상: `provider_subject`, `target_id`
- 현재 연결·자격: `connection_revision`, `credential_generation`, 소유 자격 참조의 `credential_fingerprint`
- 앱과 증거: `client_revision`, `evidence_revision`

참조 지문은 소유 자격 참조의 정규 직렬화에서 계산한 SHA-256이며 토큰 값의 해시가 아니다. grant 저장소는 access token·refresh token·원시 자격 참조를 받거나 보관하지 않는다.

`VerifiedPublicationEvidence`는 정확한 typed 객체만 받는다. 필드는 `binding`, `observed_scopes`, `checked_at`, `credential_expires_at`, `can_publish`, `verification_method`다. 이 자료형 자체는 공급자를 호출하거나 게시 권한을 증명하지 않는다. 후속 구현에서 신뢰된 서버의 실제 읽기 전용 공급자 검사와 명시 사용자 승인 절차가 이 객체를 생성해야 한다. HTTP dict나 클라이언트가 자가 신고한 scope·대상·권한으로 grant를 발급하는 경로는 제공하지 않는다.

`issue(evidence, expected_revision=..., actor=..., expires_at=..., now=...)`는 다음을 요구한다.

- 명시 허용된 공급자이고 `can_publish is True`일 것
- 공급자 카탈로그의 읽기 scope와 발행 scope를 모두 실제 관측했으며 알 수 없는 scope가 없을 것
- 관측 시각이 미래가 아니며 승인 시점에서 60초 이내일 것
- UTC 시각, 명시 승인자, 현재 CAS revision이 유효할 것
- 승인 만료가 미래이며 자격 만료를 넘지 않고 정책의 `max_ttl` 이내일 것. 기본 `max_ttl`은 1시간이다.

정책의 allowlist나 `verification_method` 문자열만 채워 실제 공급자 검사를 대체하면 안 된다. 발급 호출자는 현재 연결 상태와 관측·사용자 승인 전체를 같은 OAuth writer guard 안에서 유지해야 한다. 저장소가 연결·토큰을 직접 조회해 증거를 대신 구성하지는 않는다.

## 조회, 회수와 공개 응답

`current(binding, now=...)`는 결속·정책·만료가 현재와 맞을 때만 비공개 `PublicationGrant`를 반환한다. 승인 기록이 없거나 현재 조건과 다르면 `None`을 반환한다. `status(binding, now=...)`는 `blocked`, `granted`, `revoked`, `expired` 상태를 구분한다.

상태 DTO는 아래 필드만 제공한다.

`connection_id`, `account_id`, `platform`, `provider_id`, `target_id`, `revision`, `status`, `approved_at`, `expires_at`, `policy_revision`

workspace 식별 정보·경로, 자격 참조·지문, 관측 scope, 승인자, 공급자 검사 방법, 토큰 또는 공개 URL은 이 DTO에 넣지 않는다. 비공개 자료형의 `repr`과 공개 `to_dict()`도 내부 내용을 노출하지 않는다. 이 DTO를 제공하는 실제 관리 API와 승인·회수 UI는 아직 없다.

`revoke(connection_id, expected_revision=..., actor=..., now=...)`는 새 회수 이력을 추가한다. 승인과 회수 모두 연결별 최신 revision에 대한 CAS를 적용하며 과거 행을 수정하거나 삭제하지 않는다. 자격 refresh·대상 변경·앱 변경 등에 따라 결속이 달라지면 이전 grant는 현재 자격에 적용되지 않는다. 재승인은 새로운 실제 관측과 사용자 승인으로 별도 이력을 남겨야 한다.

회수는 이후 자격 사용 검사를 차단한다. 이미 끝난 원격 게시를 삭제하거나 공급자 토큰을 revoke하는 기능이 아니며, 이미 진행 중인 외부 호출을 취소한다는 보장도 없다.

## 자격 사용과 잠금 순서

`ManagedPublicationAuthorizer`는 현재 앱 등록에서 client revision과 증거 revision을 얻고, 관리 연결과 소유 자격 참조로 결속을 다시 구성한다. grant의 관측 scope는 현재 연결의 관측 scope와 정확히 같아야 하며 앱의 approved scope 안에 있어야 한다. 실제 자격을 읽은 후에는 token scope에 grant scope가 포함되는지, grant 만료가 실제 token 만료를 넘지 않는지도 확인한다.

resolver는 승인자 사전 확인 후에만 소유 자격을 읽고, 발행 자격 사용 전에 다시 승인자를 확인한다. `use(...)` 블록 전체에서 OAuth writer guard를 유지한다. 반환 자격의 `assert_current()`와 `assert_publication_authority()`는 현재 workspace·연결 세대·대상·만료·grant를 재검증한다. 사용 범위가 종료되거나 프로세스·스레드가 바뀌면 사용 guard가 거부한다. guard가 연결된 SDK나 자격 객체를 범위 밖으로 보관해 재사용하지 않는다. 원시 토큰을 복사하거나 로그·응답에 넣는 동작은 이 경계의 사용 계약에 포함되지 않는다.

잠금 순서는 **OAuth writer guard → publication gate → DB**다. grant 저장소도 내부에서 OAuth guard를 먼저 잡은 뒤 grant DB를 연다. 같은 스레드의 동등 workspace context 재진입을 지원한다. DB나 publication gate를 먼저 잡고 OAuth guard를 기다리는 역순을 만들지 않는다.

BridgeHost는 자격 확인 이후 permit을 redeem하고 handler가 끝날 때까지 자격 범위를 유지한다. 외부 API 실행 동안 publication gate는 해제하지만 OAuth 자격 사용 범위는 유지한다. 같은 workspace의 회수·refresh·disconnect는 이 guard 때문에 기다릴 수 있다. 자동 refresh나 legacy 자격 fallback으로 현재 승인을 우회하지 않는다.

## 후속 운영 전제

실제 전환 전에 별도 구현·검증할 범위는 다음과 같다.

- 공급자별 실제 읽기 전용 권한 검사: 관측 scope, 공급자 주체, 정확한 대상과 게시 가능 권한의 결속
- 앱·계약·비용 증거의 현재성 및 허용 공급자 정책 확정
- 발행 scope 재동의와 grant 승인을 구분하는 사용자 절차 및 승인·조회·회수 UI
- 현재 workspace와 등록부를 사용하는 명시 bootstrap 및 native publisher 서비스 조립
- 실제 토큰 수락, 대상 일치, 자산 전송과 원격 게시 결과의 별도 검증

현재 문서에는 운영 활성화 명령이나 자가 신고 증거를 만드는 예제가 없다. 기존 브라우저 로그인·크롬 프로필 잠금, 교차 게시 규칙, 운영 키, 스케줄과 비상 정지 절차는 그대로 따른다. 이 경계 작업만으로 OAuth 로그인, Keychain 접근, 원격 API 호출이나 실제 게시를 수행하지 않는다.

설계 기준은 [`관리 OAuth 발행 사용 경계 계획`](../superpowers/plans/2026-11-04-managed-publication-authority.md)이다.

## 격리 검증 기록 · 2026-11-04

운영 시험 1093개(기존 skip 4), 발행기 443개, 웹 427개, OAuth HTTP·기동 79개가 통과했다. 첫 sandbox 실행의 loopback bind 오류는 포트 사용이 허용된 격리 시험으로 재실행해 확인했다. Google 읽기 fixture를 실제 SDK 인터페이스에 맞추고 범위 종료 후 재사용 차단을 추가했으며, Facebook의 미등록 credential catalog 거부 기대값을 현재 경계와 맞췄다. 권한 검사를 완화하지 않았다. 기존 SQLite fixture의 ResourceWarning은 남아 있다.

설치된 Google SDK에서도 가짜 토큰·임시 grant DB로 apply/before_request/with_quota_project를 확인했고 refresh 및 범위 종료 후 원본·복사본 apply는 차단됐다. 네트워크·실제 OAuth/Keychain·실계정 발행 수락 시험은 아니다. 코드·관리 데이터의 전환 전 백업은 ax-console/data/deployment-backups/publication-authority-3fe05b8*에 있다. 운영 workspace에는 grant DB를 만들지 않았다.
