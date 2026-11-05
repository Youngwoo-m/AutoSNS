# Threads 텍스트 발행 연결

기존 승인·원장·잠금·교차 게시를 유지하며 Threads 텍스트 발행의 순수 payload, 공식 API client, 컨테이너/게시 영속 journal, 공통 adapter와 고정 host 조립을 구현한다. 초기 범위는 명시 text-only 게시이며 이미지·영상·캐러셀과 실제 앱 등록·로그인·활성화는 후속 필수 범위로 보존한다.

- 순수 payload는 고정 원고 버전과 소유/대상 계정을 결속하고 해당 계정의 Threads 변환본을 선택한다. 자동 요약/잘라내기·자산 삭제·scope 확대는 하지 않는다. 텍스트 전용 입력임을 명시하고 길이 초과는 거부한다.
- 컨테이너 생성과 실제 게시 전에 각각 영속 상태를 기록한다. 응답 불명확 시 자동 POST 재실행하지 않는다. 생성된 컨테이너는 같은 승인 의도에서만 이어 쓴다. publish_started 이후는 읽기 조회만 가능하며 게시 응답 ID가 없으면 제목 유사성으로 완료하지 않는다.
- API는 고정 graph.threads.net 주소와 허용된 읽기/생성/게시 메서드만 제공하고 토큰은 URL·로그·예외에 넣지 않는다. 생성자/준비 단계는 I/O가 없다. 실호출은 시험하지 않는다.
- 공통 BridgeHost의 기존 승인·permit·STOP·계정/프로필 잠금을 사용한다. 새 managed 자격의 발행 차단과 기본 비활성 등록을 유지한다. 실제 SNS 정책·비용·권한 확인은 바꾸지 않는다.
- 가짜 전송/임시 journal/영속 원장으로 교차 계정·버전·멱등·동시 요청·응답 손실·재시작·미지원 매체·원격 ID/본문 확인을 검증한다. 실계정 게시와 공개 수락은 미완료로 기록한다.

공식 근거: Meta Threads Postman collection https://www.postman.com/meta/threads/overview 및 Meta sample https://github.com/fbsamples/threads_api. 생성·게시 분리와 미디어 owner/id/text/timestamp 필드를 확인했으며 확인되지 않은 API 계약은 임의로 활성화하지 않는다.
