# SNS 도구 설정과 실제 웹 연결 사이의 수락 차이

2026-10-30. 코드 기준2b91c64. 5단계 계획 검토 대기 중 수행한 읽기 전용 조사다. 설치·외부 인증·API 조회·발행·수집·원본 변경은 실행하지 않았다. 이번 조사는 후속 실제 연결 작업의 수정 지점을 좁힌다.

## 현재 근거

- `common/operations/integration_store.py:11`의 provider/platform 표는 **허용된 설정 값**이다. Metricool에 Instagram/Threads/X/Facebook/YouTube/TikTok, vidIQ에 YouTube/Instagram/TikTok, local에 Tistory 등을 저장할 수 있다. 이 표가 서비스 제공자의 실제 권한·지원 보장 또는 실행기 등록을 뜻하지 않는다.
- 같은 파일:16,19의 입력은 platform/target_label/enabled_preference/notes와 계정·provider·connection·revision뿐이다. 키·토큰을 설정 JSON으로 받지 않는다. :45의 직렬화는 `connection_status=unknown`, `execution_status=not_connected`를 명시한다. 저장 성공만으로 연결 성공을 표시하지 않는 현재 동작은 유지해야 한다.
- `ax-console/app/web_integrations.py:14`는 정확한 입력 필드만 허용한다. 새 OAuth·점검·실행 기능을 preference 필드나 자유 메모로 우회 연결하지 않는다.
- `ax-console/app/read_model.py:101`의 카탈로그는 후보 설명이다. :104의 Metricool 후보는4개 소셜 채널만 나열하고, 저장소 설정 허용표에는 YouTube/TikTok도 있다. 두 표는 현재 용도가 다르며 실제 capability가 필요할 때는 서버 소유의 한 지원 투영으로 통합해야 한다. 단순 합집합을 실제 지원으로 표시하면 안 된다.
- `common/publishers/__init__.py:2`는 빈 dict를 반환한다. `protocols.py:5`에 inspect/prepare/submit/lookup/verify 계약만 있다. 실제 플랫폼별 어댑터 구현·등록이 없다.
- `ax-console/app/web_server.py:584`에서 recovery_adapters 기본값도 빈 dict다. 관리 DB 설정 preference를 켜도 실제 worker/recovery adapter가 생성되지 않는다.
- `read_model.py:320`, `web/app.js:199`의 성과는 unavailable이며 실제 지표 수집기가 연결되지 않았다.

## 현재 등록부의 계정 범위

`ax-console/config/operations.json`을 JSON으로 정적 판독했다. 자격증명 값은 읽지 않았다.11개 연결은 전부 enabled=false/planning_enabled=true였다. 이 값은 등록 계획이며 실제 로그인·권한 유효성 근거가 아니다.

| 계정 | 등록된 계획 대상 | 등록되지 않은 사용자 요청 채널 |
|---|---|---|
| 학과 | YouTube, Blogger, Instagram, 네이버 블로그, TikTok, X, Threads | Facebook, Tistory(학과 독립 대상) |
| 개인 | Blogger, Tistory, 네이버 블로그, YouTube | Instagram, Threads, X, Facebook, TikTok(개인 독립 대상) |

미등록 채널은 설정 후보로 표시할 수 있으나 자동으로 실제 계정을 만들면 안 된다. 기존 개인 원본→학과 TikTok 등의 교차 게시와 개인 TikTok 계정 생성은 다른 요구다. 대상 계정이 실제 선택·확인되기 전에는 기존 교차 경로를 새 개인 대상에 치환하지 않는다.

## 실제 연결 시 필요한 구현 단위

1. **도구 capability 투영:** preference/플랫폼 문서상 기능/서버 구현 여부/인증 확인/실행 활성/최근 점검을 서로 다른 필드로 제공한다. 카탈로그와 설정 표의 역할을 명확히 한다. Tistory 기존 발행 방식과 Facebook 신규 Page 대상도 같은 상태 모델로 표현한다.
2. **계정별 인증 수명주기:** 서버 credential 참조를 고정하고 실제 대상·권한 점검을 수행하는 별도 경로가 필요하다. 클라이언트 credential 경로·토큰·임의 provider import를 받지 않는다. 연결/재인증/해제는 영향받는 계정·대상·작업을 반환하고 실제 상태 확인 전 성공으로 표시하지 않는다. 비밀 없는 preference를 credential 저장소로 재활용하지 않는다.
3. **서버 실행 어댑터:** 공통 PublicationAdapter를 구현한 명시적 factory 등록만 허용한다. inspect는 읽기 전용, 공개 쓰기는 permit 소비 뒤에 수행한다. 기존 local publisher를 그대로 import/실행해 inspect하는 방식을 금지한다. 단순 stdout 성공을 공개 검증으로 바꾸지 않는다.
4. **웹과 Codex 플러그인 분리:** Codex 설치 상태는 독립 웹 runtime 권한이 아니다. 상시 runtime의 공식 API/인증 제공 방식이 확보돼야 하며, 대화 도구가 있다는 이유로 인증 자료를 추출해 재사용하지 않는다. Meta/X/Tistory 권한·비용·종료 상태는 공식 문서 조사에서 미확인을 그대로 유지한다.
5. **관측과 제어 연결:** 원본 소유·배포 대상·등록 connection·실제 remote ID가 일치해야 한다. 수집기/발행기/복구기의 지원 여부는 각각 표시한다. 지원되지 않는 동작은 명시 오류를 반환하고 다른 계정/도구로 자동 우회하지 않는다.

## 후속 시험과 실제 수락 증거

| 조건 | 요구 결과 |
|---|---|
| preference 켜기만 저장 | 인증/실행은 그대로 미확인/미연결, 원격 호출0 |
| unknown account/provider/잘못된 대상 | credential 조회·subprocess·submit0 |
| 다른 계정의 실제 로그인 관측 | 대상 불일치로 차단, 인증 성공 합성0 |
| 읽기만 가능한 연결 | 읽기 가능/쓰기 불가 별도 표시, 발행 permit 발급0 |
| 유효기간 만료·권한 철회·서비스 오류 | 이전 성공과 최근 실패를 모두 표시, 새 제출 차단 |
| 해제 요청 중 unknown 게시 존재 | 이력·예약·게시 ID 보존, 해제를 미게시 증거로 취급하지 않음 |
| 동일 버튼/응답 유실 재전송 | 동일 request key/연결 ID로 기록1개, 외부 쓰기 재전송0 |
| 개인 원본→학과 대상 | 소유권 개인 유지, 대상 관측은 학과 자격증명만 사용 |
| 실제 플랫폼 활성화 | 대상별 승인 범위의 비공개/예약/공개·본문/미디어 확인과 실제 URL 증거 |

이 표는 시험 설계 요구이며 아직 실행·통과한 결과가 아니다. 실제 계정 선택·OAuth 동의·서비스 비용 경계·대상별 운영 수락을 거쳐야 전체 채널 자동 운영 완료를 주장할 수 있다. 5단계의 저장 성과 구현만으로 이 미완료 항목들을 대체하지 않는다.
