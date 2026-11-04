# TikTok 영상·캡션 준비

공식 지침은 본인·팀 계정용 내부 업로드 도구를 Direct Post 부적합 사례로 명시한다. 현재 AutoSNS에 자동 공개 API 게시 가능성을 전제하지 않는다. 사용자에게 ‘완성본 전달 후 직접 게시’와 ‘TikTok 게시 연결 보류’를 질문했고 게시 방식 결정은 기다린다. 이와 독립적인 승인 범위인 콘텐츠 준비를 먼저 완성한다.

1. 저장된 원고의 TikTok 변환본/원문과 명시 선택한 MP4 하나를 고정하는 순수 준비물을 만든다. 원문·자산·미확인 대상·기존 계정/교차 경로를 보존하며 임의 공개 범위·사용 동의·API 권한은 만들지 않는다.
2. 신뢰된 고정 ffprobe의 명시 기술 검사를 구현한다. 기본 비활성, 임시 비공개 파일, 제한된 환경·시간·출력, 구조/코덱/크기/길이/fps 확인을 사용한다. 검사 결과는 현재 제작자 권한·음악 권리·TikTok 수락 증거가 아니다.
3. 저장 계획에서 원본 버전·manifest·실제 바이트·캡션·자산을 다시 결속하는 준비 서비스와 GET/명시 검사 HTTP를 연결한다. 저장 안 된 입력이나 오래된 준비물에는 검사를 적용하지 않는다.
4. 4개 메뉴 안에서 단일 MP4 명시 선택과 접힌 캡션/영상 준비 패널을 제공한다. 인증된 기존 자산 경로를 재사용하며 자동 업로드·브라우저 시작·대기열 재시도는 없다.
5. 가짜 probe·실제 격리 저장소·HTTP/DOM으로 준비·CAS·계정/원본 경계를 검증한다. 실제 native 검사 기동 및 사용자의 게시 방식 결정에 따른 후속 구현을 남긴다.

기존 `tiktok.queue`와 중지된 작업을 활성화하거나 retry 횟수를 초기화하지 않는다. 실제 게시·공개 검증·성과·외부 접속과 나머지 전체 목표는 계속 유지한다. Direct Post·Inbox Upload를 사용자 승인이나 TikTok 앱 심사의 우회로로 표시하지 않는다.

## 구현·검증 기록

로컬 준비물·명시 검사·저장 계획 결속·인증 HTTP·접힌 패널·CLI 검사기 등록을 구현했다. 원격 업로드 client나 게시 API는 추가하지 않았다. 기존 영상 선택 없는 TikTok 계획도 보존한다. 초기 준비 해시나 검사 도중 원고/계획/registry가 바뀌면 결과를 적용하지 않는다.

- 웹 전체: 422개 성공. `/private/tmp/autosns-tiktok-prep-web.log`
- 운영 모듈: 1065개 성공(기존 skip4). `/private/tmp/autosns-tiktok-prep-operations.log`
- 발행기: 433개 성공. `/private/tmp/autosns-tiktok-prep-publishers.log`
- 준비 API·기존 배포/Instagram 검토·웹 서버·기동 application: 75개 성공. `/private/tmp/autosns-tiktok-prep-http-startup.log`
- 마지막 표시/모바일 줄바꿈 조정 뒤 패널 8개 재통과. 서버 검사기 기본 비활성과 명시 클릭, 정확한 경로·계정·자산·해시·비영속 결과를 확인했다.
- 실제 기존32초 MP4를 임시 저장소에서 실제 ffprobe로 검사해1080×1920/30fps/32057ms/h264/aac 관측, 원본·저장 자산 보존 및 GET 재조회 검사 결과 미저장을 확인했다. 빈 programs/stream_groups 출력 호환 문제도 수정했다.

실제 workspace `--check`에서 제작·음성·렌더·이미지·성과·quota 변경이 꺼져 있음을 확인하고, 백업 후8769를 `production_main.py --serve --local-toolkit --tiktok-ffprobe /usr/local/bin/ffprobe`로 재기동했다. 검사기는 버튼 요청에서만 실행한다. application 기동 시 Instagram 검토 저장소 초기화가 누락되던 기존 문제도 보존 시험과 함께 수정했다. `/login`200·무인증 준비 상태API401을 확인했다. 브라우저 로그인·TikTok 접속·발행은 하지 않았다.

TikTok 게시 방식과 외부 도메인 질문은 답변 대기다. 실제 게시/공개 검증·성과와 나머지 전체 목표는 미완료다.
