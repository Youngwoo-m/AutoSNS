# Facebook 페이지 발행 기반

이 문서는 관리 웹의 Facebook Pages 구현 범위와 남은 연결 작업을 설명한다. 개인·학과는 AutoSNS 안의 콘텐츠 소유 계정 구분이다. **게시 대상은 Facebook 페이지이며, 개인 타임라인 게시는 지원하지 않는다.**

현재 범위는 `common/publishers/facebook_payloads.py`의 순수 텍스트 준비와 `facebook_client.py`의 주입 전송 경계다. 이 두 모듈의 가짜 전송 시험은 실제 페이지 발행 수락을 뜻하지 않는다. 기존 AutoSNS 운영 경로·자격·스케줄은 전환하지 않는다.

## 현재 구현과 미지원 범위

| 항목 | 상태 |
| --- | --- |
| 승인된 원고·버전·manifest·원본/배포 계정·페이지 ID 결속 | payload 기반 범위 |
| 명시적으로 선택한 Facebook 변형의 텍스트 준비 | payload 기반 범위 |
| 텍스트 전용 승인 시 원본 이미지·영상 제외 | 준비 계약만 지원; 원본 자산은 보존 |
| 페이지 신원·feed 텍스트 게시·알려진 게시물 조회 | 주입한 가짜 transport로 검증하는 client 경계 |
| 실제 HTTP 전송·앱 로그인·페이지 권한 부여 | 미지원·비활성 |
| Facebook 배포 계획의 UI/공통 ledger 연결 | 미지원 |
| 영속 발행 journal·BridgeHost permit·STOP 결속 | 후속 구현 필요 |
| 실제 공개 확인·공개 URL 영속 기록 | 후속 구현 필요 |
| 원격 예약·미디어 게시·성과 수집 | 미지원 |

`operations.json`에는 Facebook이 두 계정의 `catalog_candidates`로만 들어 있다. 실제 Facebook 연결·자격·발행 작업·교차 게시 규칙은 등록되어 있지 않다. 준비 현황의 Facebook 행은 미등록 안내이며 실계정 연결의 증거가 아니다.

등록부 판독기는 별도 `crossposts.json`을 합쳐 기존 **23개 교차 게시 규칙**을 읽는다. Facebook 기반을 추가한다고 이 규칙들을 대체하거나 Facebook 대상으로 자동 복제하지 않는다. 실제 페이지를 확인하기 전에는 가짜 페이지 ID나 운영 자격 참조를 넣지 않는다.

## 입력과 전송 경계

게시 원문은 승인된 콘텐츠 snapshot과 선택된 계정별 Facebook 변형에서만 준비한다. 다른 계정·버전·manifest나 중복 변형은 거부해야 한다. 텍스트를 임의로 자르거나, 원본 자산을 삭제하거나, 승인에 없는 링크·미디어 게시로 전환하지 않는다. `text_only`는 자산을 이 배포에서 제외한다는 명시 선택이며 인증·발행 승인 자체를 대신하지 않는다.

client의 API 버전은 **서버가 확인한 값을 명시적으로 지정**한다. 최신 버전을 추정하거나 URL·환경 입력으로 임의 endpoint를 고르지 않는다. 기본 `transport=None`은 실제 네트워크 전송을 제공하지 않는다. 실제 전송 구현을 주입하기 전까지 native 요청을 실행할 수 있는 상태로 표시하지 않는다.

토큰은 서버가 주입하며 Bearer 헤더 외 URL·query·본문·로그·오류 응답으로 전달하지 않는다. 실패 원문은 공개하지 않고 POST를 자동 재시도하지 않는다. 이 규칙은 실제 Facebook 앱·권한·과금 조건을 확인했다는 뜻이 아니다.

## 페이지 신원과 자격

기존 OAuth 목록의 `facebook_pages`는 `pages_show_list`, `pages_read_engagement`와 발행용 `pages_manage_posts`를 구분한다. 목록에 scope 이름이 있다는 것만으로 실제 동의·페이지 tasks·추가 비용·발행 권한이 증명되지는 않는다. 현재 공식 계약·앱 등록·HTTPS 복귀 주소·비용·페이지 tasks 관련 차단은 유지한다.

후속 실연결에서는 다음 신원을 각각 확인해야 한다.

- 로그인한 Facebook 사용자 또는 제공자 주체
- 사용자가 명시 선택한 불변 페이지 ID
- 실제 요청에 사용하는 페이지 자격과 해당 페이지의 관리 권한/tasks
- AutoSNS의 개인·학과 소유 계정과 배포 계정

로그인 사용자 ID를 페이지 ID로 간주하거나, 여러 페이지 중 첫 항목을 자동 선택하거나, 개인·학과의 다른 자격으로 fallback하지 않는다. Threads의 사용자 ID 결속을 Facebook 페이지 자격에 그대로 복사하지 않는다. 현재 관리 OAuth 자격 resolver의 publication 거부도 해제하지 않는다.

## 후속 발행·예약 연결

다음 단계에서 `facebook_services.py`, `facebook.py`, `facebook_runtime.py`를 공통 실행 원장과 연결한다. POST 전에 영속 시도 기록을 만들고, 결과 불명확 시에는 새 POST를 만들지 않아야 한다. 알려진 게시 ID만 읽기 조회하며, 목록에 없다는 사실을 미발행 증거로 간주하지 않는다.

공통 BridgeHost의 계정·대상·등록 실행기·승인 snapshot·permit·프로필 잠금·한도·중복 방지와 쓰기 직전 STOP 확인을 유지해야 한다. 실제 child bootstrap은 앱·비용·권한·페이지 tasks·공개 확인 수락 전까지 비활성으로 둔다.

원격 예약은 이번 기반에서 지원하지 않는다. 후속 통합은 공통 원장의 현지 예약 시각과 실행 조건을 사용해, 시간이 된 승인 건에 대해 단 한 번의 게시 요청을 수행하는 방식부터 연결한다. 현재 Facebook 배포가 이 공통 예약 경로까지 연결됐다고 표시하지 않는다.

UI/ledger도 후속 범위다. 현재 공통 ledger와 배포 화면의 명시 `text_only` 선택은 Threads에 한정되어 있으므로 Facebook을 단순히 플랫폼 목록에 넣는 것만으로 배포 계획이 완성되지 않는다. 승인 화면에 원본 미디어 제외를 표시하고, 계정별 실제 연결이 등록된 경우에만 선택을 허용해야 한다.

## 공개 확인

게시 API가 ID를 반환했다는 사실, 소유자 API의 `is_published` 같은 플래그, 페이지 소유자의 읽기 성공, permalink의 존재만으로 **공개 검증 완료(`verified`)를 만들지 않는다.**

후속 검증은 정확한 게시 ID·페이지 소유자·원격 본문·게시 시각을 승인된 버전과 대조하고, 실제 공개 페이지 관측과 안전한 공개 URL까지 결속해야 한다. 다른 페이지의 응답, 비공개/숨김 게시물, 오래된 글, 로그인 벽, 조회 실패, 링크만 존재하는 결과는 확인 대기로 유지한다. 원격에서 읽은 본문을 해시해야 하며 로컬 원고의 해시를 원격 증거로 채워 넣지 않는다.

공통 검증의 텍스트 전용 미디어 제외와 공개 URL 저장은 현재 Threads 전용 분기를 갖고 있다. Facebook을 지원하려면 해당 분기와 플랫폼별 URL 검증을 명시적으로 추가해야 한다. Facebook permalink 형식을 Threads URL 형식으로 바꾸거나 숫자 ID를 조합해 공개 URL을 지어내지 않는다.

## 근거와 실제 수락의 경계

공식 Meta Business SDK의 정적 계약을 추적하는 출처는 다음과 같다.

- [Page SDK 정의](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/page.py)
- [PagePost SDK 정의](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/pagepost.py)

이 정의들은 client 경계에서 사용할 페이지/게시물 필드와 메서드를 확인하는 출처다. `main`은 변경될 수 있으므로 실제 운영 API 버전을 결정하는 단계에서는 그 버전의 공식 계약과 현재 앱 권한을 다시 확인해야 한다. SDK에 필드나 메서드가 있다는 사실이 현재 앱의 사용 가능성·무료 이용·페이지 관리 권한·익명 공개 접근을 증명하지 않는다.

실제 Facebook 앱 등록, OAuth 및 페이지 토큰 전환, HTTPS 복귀, 동의 scope, 페이지 tasks, API 버전별 권한·비용 조건, 실제 게시·익명 공개 접근·성과 수집은 아직 수락되지 않았다. 이번 기반의 검증은 임시 데이터와 가짜 transport만 사용하며, 운영 브라우저·자격·실제 게시를 호출하지 않는다.
