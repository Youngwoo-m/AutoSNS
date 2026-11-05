# 웹 화면 1단계 — 기존 조회 API 준비 점검

- 상태: 정적 코드 점검 완료. 화면 확정 대기 중의 독립 준비 작업이며 제품 코드는 수정하지 않았다.
- 범위: 현재 워크트리의 `ax-console/app/server.py`, `common/shared/axlock.py`, 관련 인증 코드를 읽었다. 실제 API·서버·계정·브라우저·모델·발행을 호출하지 않았다.
- 화면 근거: [화면 구성안](../superpowers/specs/2026-10-30-account-web-screens-design.md).

## 기존 경로의 실제 동작

줄번호는 점검 시 워크트리 기준이다. GET이라는 이유만으로 콘텐츠·운영 상태에 쓰기가 없다고 간주하지 않는다.

| GET 경로 | 데이터·함수 근거 | 부작용·해석 주의 |
|---|---|---|
| `/api/meta` | `server.py:68` meta, accounts.json·ACTIONS | 파일 읽기. status 누락을 '연결됨'으로 대체하므로 인증 확인 증거가 아님 |
| `/api/contents` | `server.py:1080` contents → `:1066` _sync_status → `:1053` csave | 상태 변화 시 meta·원문·변환본 파일을 다시 저장. 순수 콘텐츠 조회가 아님 |
| `/api/tasks` | server.py의 GET 분기 → load | 저장된 작업 목록. 완료 코드가 실제 공개·내용 검증 완료를 증명하지 않음 |
| `/api/automations` | `server.py:517` automations → _launchd/catalog/codex_jobs | launchctl 조회·plist·TOML·로그 mtime 읽기. 예외 시 오케스트레이터 로그 기록 가능. last는 성공 시각이 아님 |
| `/api/schedule` | `server.py:725` schedule_view → load/automations/codex_jobs | 위 조회 부작용을 상속. 계산된 실행 일정이며 플랫폼 원격 예약을 확인한 결과가 아님 |
| `/api/incidents` | `server.py:1523` incidents_view | 저장된 사건·설정 읽기, 조치 가능 여부를 메모리에 추가. 이 GET은 감시기·모델을 실행하지 않음 |
| `/api/orchestrator` | `axlock.py:227` status + 로그 끝 16KB | PID 확인 후 죽은 waiting JSON 삭제. 읽기 전용 잠금 스냅샷으로 그대로 사용할 수 없음 |
| `/api/google` | `server.py:917` google_view | GSTATE 캐시·설정 외 키체인/복호화 자식 프로세스, gh auth status 네트워크 조회, Tistory 쿠키DB 임시 복사·조회·프로세스 확인 가능. GET 자체 Google 토큰 갱신은 없음 |
| `/api/settings` | `server.py:400` settings_view | 비밀값은 반환하지 않지만 이름·존재 여부를 얻으려고 키체인/복호화 프로세스를 사용할 수 있음. skills/plugins 목록은 Claude 설정 기준이며 Codex 설치 목록과 다름 |
| `/api/proposals` | `server.py:1742` proposals_view | 최근 제안 파일·메모리 읽기. 새 기획 모델 호출은 POST 경로임 |
| `/api/agents` | `server.py:1441` agents_view | 설정·현재 월 사용량 파일 읽기와 합산. 모델 호출 없음 |
| `/api/questions` | `server.py:582` question_queues | 측량·토목 상태 두 개만 읽음. 건축·안전 요청을 포함한 전체 분야 집계로 쓰면 안 됨 |

## 화면 연결 전에 구별해야 할 경계

1. 콘텐츠·배포 조회와 상태 동기화/저장을 분리해야 한다. 화면을 새로고침했다는 이유로 원고·버전 파일을 덮어쓰지 않아야 한다.
2. 잠금 상태 표시와 오래된 잠금 기록 정리를 분리해야 한다. 실제 PID/잠금의 소유권은 기존 axlock이 기준이다.
3. '설정에 존재', '인증 확인', '사용자 활성', '최근 성공', '실제 공개', '내용 확인'을 서로 다른 필드로 해석해야 한다.
4. 콘솔·launchd 일정은 로컬 실행 계획이다. YouTube 등의 원격 예약 상태와 같은 배지로 통합하지 않는다.
5. 계정·설정 화면을 읽는 것과 키체인 접근·CLI 네트워크 확인을 구분하고, 마지막 확인 결과/시각과 명시적 갱신을 표현해야 한다.
6. 기존 목록에 없는 채널별 배포·교차 게시 규칙·게시물 성과는 있다고 가정하지 않는다. 아직 미지원/미수집인 항목을 샘플이나 0으로 채우지 않는다.
7. 인증 보호는 유지한다. 인증 세션의 마지막 사용 시각 갱신 같은 보안 메타데이터와 콘텐츠·배포·운영 정책 변경은 구별하며, '읽기 전용'을 이유로 인증을 우회하지 않는다.

## 서버 시작의 별도 부작용

`server.py:2169` 이후 기본 시작은 내부키 준비, 실행 중 상태 정리, 초안 상태 재설정, scheduler/watcher/Google 검사 background를 시작한다. 따라서 기존 서버를 시험용으로 한 번 켜는 것도 단순 조회 검증이 아니다.

`AX_NO_BG=1`은 background와 시작 시 일부 상태 변경을 막지만 `/api/contents` 자체의 저장 부작용까지 제거하지 않는다. 향후 시험은 임시 데이터·가짜 인증/실행기로 수행하고 운영 원본에 새 서버를 병렬로 붙이지 않아야 한다.

## 현재 결론과 남은 선행 결정

화면 시안은 실제 발행 미연결 상태를 유지한다. 화면 승인 후 기존 실행 계획을 갱신할 때 위 차이를 조회 계층·상태 모델·시험 범위에 반영한다. 지금은 새로운 API를 구현하거나 기존 GET 동작을 바꾸지 않았다.

사용자에게 요청한 화면 확정 및 접속 범위 답변은 아직 수신하지 않았다. 이 점검으로 화면 승인이나 외부 접속 승인을 대신하지 않는다.
