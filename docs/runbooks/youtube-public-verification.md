# YouTube 업로드와 공개 검증

서버의 미디어 factory는 고정 원고 버전의 MP4 바이트·해시·크기를 확인하고 `VerifiedYoutubeMedia` 봉투를 만든다. 업로드 SDK가 실제 원격 ID를 반환한 뒤에만 그 ID와 계정·채널·원고·자산·제목·설명을 결속하는 `youtube_upload_receipt_v1`을 제출 결과에 저장한다. 영수증은 원격 영상 바이트 해시나 시각 품질 검토 증거가 아니다.

공개 검증은 기존 영속 원장에서 성공한 제출 attempt와 해당 영수증을 직접 읽어 승인 snapshot으로 다시 계산한 준비 payload와 대조한다. 새 원격 관측의 ID·채널·공개 상태·업로드 처리·영상 처리 완료·제목·설명·시각이 모두 일치해야 verified로 전환한다. 조회 완료 시각까지의 정상 관측은 허용하지만 미래 관측은 거부한다. 예약 시각 이전에는 조회·완료하지 않는다.

변환된 YouTube 영상에 로컬 원본 해시를 원격 `media_sha256`으로 넣지 않는다. 저장되는 공개 검증 근거는 `verification_method=youtube_upload_receipt_and_public_observation`, 실제 ID·채널·공개 시각과 `media_sha256=null`이다. 전체 영수증은 제출 원장에 보존하고 공개 검증 projection에 다시 복사하지 않는다.

영수증 없는 과거 업로드, 불명확한 제출 결과, 클라이언트/adapter가 관측 안에 넣은 가짜 영수증, 수정된 제목·설명·자산, 다른 계정·채널·원격 ID는 이 경로로 완료하지 않는다. unknown의 자동 재업로드나 제목 기반 해소도 추가하지 않았다. 기존 블로그의 본문·매체 해시 검증은 유지한다.

API 필드 참고: [videos resource](https://developers.google.com/youtube/data/reference/rest/v3/videos), [videos.insert](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert). 위 영수증 결속은 프로젝트의 서버 증거 설계다.

이번 검증은 가짜 Google SDK·가짜 공개 관측과 임시 영속 원장을 사용했다. 실제 Google 자격 접근·업로드·공개 API 요청·기존 스케줄 전환은 실행하지 않았다. OAuth 자격의 발행 연결, 추가 SNS adapter, 실제 공개 수락·성과 수집·외부 접속은 계속 미완료 범위다.
