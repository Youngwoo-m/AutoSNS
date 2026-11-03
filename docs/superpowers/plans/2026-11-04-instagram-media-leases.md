# Instagram 전달용 미디어 임대 URL

승인된 Instagram 배포 구성의 바이트를 고정하고, 만료·회수 가능한 전달 URL을 발행 경계에 연결한다. 기존 4개 메뉴와 교차 게시 규칙을 유지한다. 이번 코드만으로 외부 공개나 실제 발행을 활성화하지 않는다.

1. 별도 비공개 SQLite 저장소: 명시 초기화, 불변 바이트, 문맥·자산 결속, 동일 요청 멱등 처리, 만료·회수·payload 정리 및 tombstone 보존.
2. 별도 loopback 전달 서버: 기본 비활성, GET/HEAD만, 엄격한 경로·Host·헤더, MP4 단일 Range, 고정 크기 스트리밍, 요청 및 청크별 정지/회수 확인.
3. 실제 PublicationContext와 준비물을 보유한 stager: 요청 13필드·바이트와 대조하고 승인·정지·실행 허가를 확인한 뒤만 저장한다. 조회용 허가와 발행용 허가를 구분한다.
4. 격리된 저장소·가짜 승인·HTTP 시험으로 원본 바이트, 중복 방지, 만료·회수, 권한 상실을 확인한다. 실제 자격·발행·공개 파일은 사용하지 않는다.
5. 계정별 관리 조회/회수 화면과 명시 실행 조립, 실제 DNS/TLS 전달 경로·익명 해시·Meta 수락 시험을 후속 필수 범위로 연결한다. URL token을 관리 화면·로그에 노출하지 않는다.

만료·회수는 이후 요청을 차단한다. 이미 수신한 원격 복사본의 삭제를 의미하지 않는다. 정리는 로컬 payload를 삭제하며 멱등 기록은 남긴다. 실제 서비스 기동 시에는 임대 발급과 fetch 모두 현재 검토·대상·STOP을 확인해야 한다.

## 구현·검증 기록

1~4의 저장소·stager·전달 서버·격리 시험과 5의 관리 조회/회수 패널을 구현했다. 실제 DNS/TLS·기동 조립·외부 fetch/Meta 수락은 후속 필수 범위로 남긴다.

- 운영 모듈: `python3 -m unittest discover -s tests/operations -t . -p 'test_*.py'` — 1043개, 성공(기존 skip 4개). `/private/tmp/autosns-media-lease-operations-final.log`
- 발행기: `python3 -m unittest discover -s tests/publishers -t . -p 'test_*.py'` — 369개 성공. `/private/tmp/autosns-media-lease-publishers.log`
- 웹: `node --test tests/web*.test.mjs` — 362개 성공. `/private/tmp/autosns-media-lease-web-final2.log`
- 관리 HTTP: `python3 -m unittest tests.test_web_media_leases tests.test_web_instagram_reviews tests.test_web_server -q` — 35개 성공. `/private/tmp/autosns-media-lease-admin-http.log`

첫 실행의 sandbox localhost 바인딩 차단은 허용된 격리 재시험으로 해결했다. 새 패널 생성자를 실제 앱 VM 시험에 주입하여 기존 앱 통합 시험도 재통과했다. 일부 기존 SQLite fixture의 ResourceWarning은 남아 있으며 시험 결과는 성공이다. 브라우저 로그인·실계정·유료 모델 호출은 사용하지 않았다.

관리 웹 8769를 기존 설정으로 재기동했다. 로그인 페이지 200, 무인증 현황 API 401, 관리 웹의 익명 media 경로 401을 확인했다. 실제 미디어 임대 DB는 생성되지 않았다. 기존 연결 11개 비활성 및 교차 경로 23개를 재확인했다. 이는 실제 SNS 발행이나 외부 전달 수락을 증명하지 않는다.
