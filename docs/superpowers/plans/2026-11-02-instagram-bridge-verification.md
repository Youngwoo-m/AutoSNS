# Instagram 공통 실행·공개 관측 검증

**목표:** 기존 수동 최종 검토와 전송 원장을 공통 실행 adapter/bridge 및 공개 검증에 연결한다. 실제 전송·로그인·호스팅·기존 스케줄 전환은 활성화하지 않는다.

## 병렬 구현

- [x] 원본 전달 영수증과 관측: 전송 원장이 검증한 실제 공급자 영수증·선택 자산 순서·컨테이너 ID·게시 ID·문맥을 비밀 없는 16필드 `instagram_upload_receipt_v1`으로 보존한다. 캐러셀의 첫 소유자 API 조회에서 자식 ID/유형 순서를 private 원장에 고정하며 이후 순서 변경은 덮어쓰지 않는다. publish 성공 ID를 기록한 뒤 조회 실패 때문에 재게시하지 않는다. 초기 조회가 실패하면 공개 검증은 대기하고 읽기 조회에서만 핀 확정을 시도한다.
- [x] 순수 검증: 승인된 snapshot/context를 다시 준비하여 원본 전달 영수증과 비교한다. 실제 원격 캡션·소유 계정·미디어 유형·자식 순서·시각·공개 접근 증거를 대조한다. Meta가 변환한 미디어의 SHA를 원본 SHA라고 합성하지 않는다. 초기 캐러셀 영수증의 핀이 미확정이면 private 원장이 반환한 확정 영수증의 나머지 필드가 초기 영수증과 동일해야 한다.
- [x] adapter/runtime: 고정 개인/학과 연결, 엄격한 준비 입력·서버 자격·공통 permit/STOP 경계를 보존한다. 기본 catalog는 비어 있고 native bootstrap은 미설정이다. 알려진 게시 ID만 조회하고 실제 전송 영수증 없는 유사 게시물을 일치로 판단하지 않는다. 새 managed OAuth의 발행 차단을 유지한다.
- [x] 공통 검증/복구: Instagram 선택 자산의 로컬 fingerprint와 원격 관측을 구분한다. 최종 검증은 실제 시작된 attempt의 영수증과 공개 관측을 요구하며 안전한 실제 URL을 원장에 저장한다. 불명확한 시도의 연결 복구는 동일 영수증 기반 읽기 증거만 사용하고 새로운 POST를 만들지 않는다.
- [x] 가짜 HTTP/공급자·실제 임시 원장 통합, 회귀 검증 후 준비 상태를 갱신한다. 기존 Instagram legacy 경로 3개를 포함한 교차 규칙 23개를 유지한다.

## 신뢰 경계와 미완료 범위

캐러셀 자식 ID의 최초 핀은 신뢰된 서버의 소유자 API 관측으로 private 원장에 보존한다. 일반 사용자 API 입력으로 확정 영수증을 만들거나 바꾸지 않는다. 공개 여부는 별도의 신선한 공개 probe가 소유자 관측의 게시 ID·계정·캡션 해시·형식·자식 순서·URL과 일치할 때만 인정한다. 실제 probe/공급자 수락은 여전히 필요하다.

실제 Instagram Login·직접 resumable 영상 계약, 새 인증 문맥의 안전한 컨테이너 재결속, 호스팅 동의/회수·권한·비용·실제 게시/공개 수락, 나머지 SNS·성과·계정 경로 이행·외부 접속과 종합 검토는 전체 목표의 후속 필수 범위다. 이번 가짜 통합 검증을 전체 운영 완료로 표시하지 않는다.

## 검증·반영 기록

발행 모듈 351개, 운영 모듈 1022개(4개 건너뜀), 준비 상태 DOM 7개·HTTP 2개 시험이 통과했다. 통합 6개는 실제 client·공급자 경계·서비스·private 전송 원장·handler·adapter·RuntimeStore·최종 검증/조회 복구를 가짜 외부 공급자로 연결한다. 별도 BridgeHost 6개는 실제 RPC frame/permit·부모 FD/flock·자격 결속·STOP 거부를 검증하되 OS start-time probe만 시험 값이며 실제 child 프로세스·외부 API를 실행하지 않는다.

회귀 중 불변 bridge tuple과 JSON list 비교, 추가 관측 영수증의 비밀 필드 검증, wrong first-carousel 관측의 핀 방지와 RPC 오류 대신 안전한 대기, known-ID unknown의 로컬 최초 핀을 재현·보완했다. Instagram은 명시 선택 계약을 요구하므로 과거 Facebook 옵션을 Instagram 문맥에 재사용하는 시험 기대값은 거부로 갱신했다.

기존 8769 환경으로 재기동했고 로그인 HTTP 200·무인증 준비 상태 API HTTP 401을 확인했다. 연결 11개·enabled 연결 0개·교차 규칙 23개를 유지하며 실제 발행 서비스/probe를 추가 활성화하지 않았다. 코드와 일관된 operations/instagram-reviews DB 백업은 `ax-console/data/deployment-backups/instagram-bridge-6ed6b89*`에 보관했다.
