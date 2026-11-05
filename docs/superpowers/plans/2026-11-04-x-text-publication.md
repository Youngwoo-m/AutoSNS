# X 텍스트 게시 연결

확정 4개 메뉴와 원본/교차 경로를 유지하며 X 게시를 연결한다. 실제 앱·계정·API 비용 수락 전에는 읽기·쓰기를 모두 차단한다. 이번 개발은 실제 API 요청이나 추가 결제를 실행하지 않는다. X 미디어 업로드도 최종 목표의 후속 범위로 유지한다.

1. 공식 문서에 따른 사용자 문맥 API client와 고정 HTTPS transport. POST 한 번, 읽기는 /me와 알려진 게시물 ID만. 기본 transport·비용 gate 차단.
2. 실제 원문/계정별 변환본의 명시 text_only 준비. 공식 twitter-text 가중 길이·URL·emoji·NFC 규칙을 검증한 오프라인 구현을 사용하고 원문은 바꾸지 않는다. 외부 포트는 고정 버전·해시·라이선스 및 공식 conformance를 확인한다.
3. 별도 영속 원장·게시 결과 불명확 시 재게시 금지. 현재 소유자·비용·STOP을 검사한다. API가 t.co로 바꾼 URL은 실제 entities와 승인 원문에 정확히 대조하고 원격 원문 해시를 별도로 보존한다.
4. adapter·runtime·공통 검증·복구·기획 계획·화면을 연결한다. 소유자 API만으로 공개를 추정하지 않고 별도 현재 공개 관측을 요구한다. 원격 ID 없는 게시 검색/추정 복구는 하지 않는다.
5. 가짜 transport·실제 격리 DB·공식 문자열 conformance·HTTP/DOM으로 경로를 검증한다. 실제 자격·비용 정책·native 조립·공개 probe·실발행 및 미디어·성과는 후속 수락 범위다.

## 구현·검증 기록

1~5의 텍스트 기반 코드와 격리 시험을 구현했다. 실제 계정·유료 호출·게시·검색·브라우저 로그인은 실행하지 않았다. 가중치 구현은 고정 순수 Python 포트를 검증·수정해 사용하며 런타임 파일 읽기/네트워크/subprocess를 제거했다. 공식 twemoji 정규식과 공식 가중치 44건·URL/TLD 1,682건을 대조했다. 원문은 NFC나 줄바꿈 변환 없이 보존한다.

- 발행기 전체: 425개 성공. `/private/tmp/autosns-x-publishers-final2.log`
- 운영 전체: 1049개 성공(기존 skip 4개). `/private/tmp/autosns-x-operations.log`
- 모든 상위 웹 mjs: `node --test tests/*.mjs` 412개 성공. `/private/tmp/autosns-x-web.log`
- X 계획·기존 배포·준비 상태·서버 HTTP: 41개 성공. `/private/tmp/autosns-x-admin-http.log`
- 최종 엄격화한 URL 대응과 비활성 연결 거부는 X 서비스/runtime/evidence 30개로 재검증했다. `unwound_url`의 최종 redirect 목적지가 같다는 이유로 다른 원본 URL을 같다고 보지 않는다.

실제 W registry의 학과 X에 계획용 `text_only`를 추가하고 revision을 갱신했다. 기존 관리 승인은 새 문맥 확인이 필요할 수 있다. 연결 11개 비활성, 교차 경로 23개 모두 legacy 소유를 재확인했다. 새 계정·대상·자격·운영 스케줄은 만들거나 바꾸지 않았다. 8769는 기존 로컬 정책으로 재기동한다.

반영 전 코드/registry와 관리 DB의 일관된 백업은 `ax-console/data/deployment-backups/x-text-9f25c14.tar`, `x-text-9f25c14-operations.sqlite3`이다. 원본 R의 키·프로필·발행 자료는 백업이나 수정 대상에 넣지 않았다. 실제 권한/비용/공개 probe/native 등록과 실게시·미디어·성과, 다른 채널·제작 품질·이행·외부 접속·종합 수락은 계속 남아 있다.
