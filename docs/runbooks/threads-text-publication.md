# Threads 텍스트 발행 경계

순수 payload는 원고 ID·버전·해시·소유자와 대상 계정의 Threads 변환본을 결속한다. `text_only=true`를 명시해야 하며 자동 요약·잘라내기·이미지 삭제는 하지 않는다. 500자 상한과 UTF-8을 확인한다. 텍스트 전용 capability를 서버가 등록한 연결에서만 계획 화면의 명시 선택을 사용할 수 있으며, 다른 채널에는 이 옵션을 저장할 수 없다. 기본 운영 등록부의 연결·권한·스케줄은 변경하지 않았다.

ThreadsServices는 컨테이너 생성과 게시 직전에 별도 SQLite journal에 상태를 저장한다. 같은 의도의 컨테이너는 다시 만들지 않고, 준비 중이면 다음 승인된 호출에서 상태만 확인한다. 게시 시작 후 응답을 잃으면 자동 POST 재실행하지 않는다. 두 POST 직전 STOP 확인 callback을 받을 수 있다. 업로드된 이미지·캐러셀·영상은 아직 지원하지 않으며 별도 필수 구현 범위다.

소유자 API에서 글·소유자·permalink가 보여도 공개로 판정하지 않는다. 별도로 등록된 public probe가 URL·원격 ID·소유자·본문 해시·신선한 시각을 증명해야 공개 후보가 된다. 공통 원장은 승인 원고·게시 ID·본문·시각을 다시 대조하고 안전한 실제 Threads URL을 저장한다. 기본 public probe는 없으므로 현재 실제 익명 공개 확인은 활성화되지 않는다.

API client는 공식 Meta 자료의 생성·게시·조회 경로와 응답 필드를 구현했다. 토큰 URL 노출 없이 사용할 인증 헤더 실계약을 충분히 확인하지 못했으므로 기본 네트워크 transport는 차단했다. 서버가 명시적으로 주입한 가짜 transport로만 시험했다. 실제 비용·앱 등록·권한·토큰·전송 수락은 아직 필요하다.

명시 host factory는 공통 BridgeHost를 사용하므로 기존 permit·STOP·계정/프로필 잠금을 유지한다. 기본 catalog는 비어 있고 child bootstrap은 미등록으로 거부한다. 새 managed OAuth 자격의 publication 차단도 유지한다. 기존 교차 규칙과 자동 작업을 켜거나 바꾸지 않는다.

검증: 가짜 전송·메모리 자격·임시 journal과 영속 실행 원장에서 생성→게시→공개 증거→URL 저장, 중복·중단·응답 손실·STOP·잘못된 소유자·공개 증거 누락을 확인했다. 실제 API·로그인·발행·익명 페이지 검증을 수행한 것이 아니다.

공식 근거: [Meta Threads Postman](https://github.com/fbsamples/threads_api/blob/main/postman/threads-api.postman_collection.json), [Meta 샘플 앱](https://github.com/fbsamples/threads_api). 샘플의 host와 현재 문서의 host가 달라 실제 transport 수락 때 함께 재확인해야 한다.

## 명시 HTTPS transport

`ThreadsHttpsTransport`는 서버 코드에서 `activate=True`로 명시 등록한 경우에만 사용할 수 있다. 기본 client의 transport=None 차단은 유지한다. 고정 TLS host·포트·허용 경로/필드/폼만 사용하고 토큰은 Authorization 헤더에만 전달하며 디버그 출력을 끈다. 리다이렉트·재시도·임의 프록시·응답 크기 초과·오류 원문 노출을 허용하지 않는다.

Bearer 헤더 처리는 [RFC 6750 §2.1](https://www.rfc-editor.org/rfc/rfc6750#section-2.1)에 따른 표준 구현이다. 실제 Threads의 수용과 .net/.com host 차이는 확인하지 않았으며 운영 기동에 자동 등록하지 않았다. 시험은 가짜 HTTPSConnection을 통해 수행했고 실제 TLS/API 요청을 하지 않았다.
