# 개인·학과별 음성 프로필 연결

기존 네 메뉴를 유지한다. 개인/학과 콘텐츠 발행 메뉴의 제작 설정 옆 접힌 음성 설정에 프로필 ID와 사용 선호를 저장한다. 설정 저장은 다음 명시 기동 준비이며 실제 Voicebox 시작·조회·합성·과금·발행을 실행하지 않는다. 개발 완성 후 종합 검토한다는 요청을 따라 승인 질문을 반복하지 않는다.

- 별도 voice-settings.sqlite3, 계정별 CAS·기본 비활성·명시 초기화. 계정·스키마·프로필 형식·추가 필드를 검증한다.
- AccountVoiceTaskService는 원고/작업에 기록된 소유자를 서버가 조회해 해당 계정의 신뢰된 VoiceTaskService에 위임한다. 웹이 계정·프로필·호스트를 지정해 합성할 수 없다. 작업별 기존 프로필 intent 결속과 원장·잠금은 유지한다.
- --enable-voicebox에서 기존 --voicebox-profile-id가 있으면 이전 공용 모드를 유지한다. 없으면 저장된 계정별 설정을 컴파일해 주입한다. 비활성 계정은 합성·재개를 거부한다. --check/defaultserve는 API·설정 활성화를 하지 않는다.
- 인증 HTTP /api/v2/accounts/{account}/voice-settings와 account별 capabilities를 연결한다. 미저장·busy·이탈 보호와 늦은 응답 계정 침범을 시험한다.
- 가짜 클라이언트·임시 저장소·인증 HTTP/DOM으로 개인·학과 분리, 공유프로필 허용, 원래 작업 재개/설정변경 거부, 기본 비활성, 기존 공용 CLI 호환성을 검증한다. 실제 Voicebox 모델·음성 수락은 별도 미완료 범위다.
