# 제작 전용 실행 서비스

`common.operations.production_startup.build_production_runtime`은 기존 웹 실행 API와 worker를 연결하는 제작 전용 조립 함수다. 기본 비활성이며 호출만으로 모델·브라우저·worker를 시작하지 않는다.

## 신뢰된 서버에서의 조립
서버가 `BootstrapConfig`, 제작 작업만 담은 `Registry`, `ExecutionCatalog`, 공급자 mapping을 주입한다. 선택적으로 `ExecutionPolicy`, clock을 주입한다. HTTP 요청으로 실행파일·공급자·정책·기동 여부를 지정하지 않는다.

- `initialize=False`가 기본이다. 없는 저장소를 만들거나 이행하지 않는다.
- 명시 `initialize=True`일 때만 관리 저장소를 초기화한다. 운영 자료 경로를 임시 시험 저장소로 사용하지 않는다.
- `runtime.service`를 기존 `create_server(..., execution_service=runtime.service)`에 주입한다. 주입만으로 worker는 실행되지 않는다.
- 제작은 명시적인 `runtime.worker.tick()` 또는 `run()`에서만 실행된다. 공급자 주입과 실제 실행 권한 확인 전에는 호출하지 않는다.
- worker 중단은 기존 `stop_event`와 drain 동작을 사용한다.

## 발행과의 경계
발행 연결·교차 게시 등록·비제작 작업·발행 phase/mutation executor·legacy caller가 섞이면 조립 전에 거부한다. 발행 adapter는 비어 있고 observe/admit/approve/verify/reconcile을 제공하지 않는다. 공급자가 없으면 작업을 실행 가능으로 표시하지 않는다.

입력 원고의 소유 계정과 revision/hash는 기존 계약으로 결속된다. 제작 결과는 새 불변 원고 버전으로 저장되며 별도의 콘텐츠 검토를 기다린다. 재접수와 프로세스 재시작으로 공급자를 자동 중복 호출하지 않는다. 생성에 성공해도 실제 발행을 의미하지 않는다.

## 현재 적용 상태
제작 전용 조립 코드와 가짜 공급자 통합 시험이 추가되었다. 8769의 기본 `web_server.main`은 이 서비스를 아직 기동하지 않는다. 실제 Claude 공급자 설치/격리 증명·구독 한도·계정별 제작 정책과 quota 관측의 연결은 후속 필수 작업이다. 이 문서는 실제 모델 호출·SNS 발행 활성화를 지시하지 않는다.

## 검증
`tests.integration.test_production_startup`은 기본 무변이, 발행 등록 거부, 계정 경계, 명시 제작, 버전 보존, 검토 대기, 재시작 중복 방지, 인증된 HTTP 접수부터 결과 조회까지를 임시 저장소·가짜 공급자로 확인한다. 실제 공급자·실계정 검증을 대신하지 않는다.

## 제작 웹 application 조립
`ax-console/app/production_application.py`의 `build_production_application`에 제작 runtime과 기존 조회용 `planning_registry`를 주입한다. 기존 채널·교차 발행 계획은 조회용 등록부로 유지하며 제작 서비스의 실행 권한에 합치지 않는다. 계정 범위 누락과 서로 다른 작업의 동일 ID 충돌은 소켓 준비 전에 거부한다.

기동 순서는 `build_production_application(...)` → 명시 `app.initialize_storage()` → 명시 `app.serve_forever()`다. build는 초기화·worker 실행을 하지 않는다. 소켓만 만들고 사용하지 않는 application은 `close()`한다. enabled인 runtime에서만 제작 worker 하나가 실행된다. `request_shutdown()`은 다른 스레드에서 호출하며 worker drain과 서버 종료를 거친다.

worker 실패와 HTTP loop 진입 실패가 겹쳐도 worker가 `BaseServer.shutdown()`에서 대기하지 않도록 공개 `service_actions` hook으로 종료한다. drain 제한을 넘기면 성공으로 간주하지 않고 `worker_not_stopped`와 stuck 상태를 보존하며 자동 재기동하지 않는다. signal 연결과 실제 공급자/기동 설정은 후속 범위다.

현재 8769의 기본 기동은 여전히 기존 모드다. 실제 제작 실행과 기본 기동 전환을 수행하지 않았다.

## 설치된 Claude Max 구독 공급자
`common.operations.installed_claude.InstalledClaudeRunner(executable, home, username, model)`은 생성만으로 인증이나 프로세스를 실행하지 않는다. 명시 `verify()`에서 실행파일 해시·버전·필수 옵션·Max 구독 인증을 확인하고 도구 없는 최소 probe를 한 번 실행한다. 성공 후 `build_production_runtime(..., subscription_runner=runner)`로 결속한다. `producers`와 동시에 지정할 수 없다. 등록 작업마다 명시된 구독 전용 정책과 필수 출력 `text`가 있어야 한다.

실행환경은 고정 HOME·USER·LOGNAME·PATH·LANG만 사용한다. 부모 API 키·토큰·게이트웨이 환경을 복사하지 않으며, 인증 방식이 `claude.ai`/`firstParty`/`max`가 아니면 생성을 거부한다. 매 생성 전 인증과 실행파일 해시를 재확인하며 API fallback이나 자동 재검증은 없다.

macOS의 현재 설치에서는 실제 바이너리 경로가 필요하다. `/usr/local/bin/claude` wrapper는 HOME에 의존하고, HOME만 전달해도 구독 인증을 찾지 못한다. 고정 USER·LOGNAME도 필요하다는 것을 최소 환경 시험에서 확인했다. 실행파일 버전 변경 시 기존 증거를 재사용하지 않는다.

2026-11-02 CLI 2.1.310에서 실제 어댑터의 명시 최소 검증이 성공했다. 이 결과는 당시 로그인과 도구 없는 응답만 증명하며 잔여 한도·향후 사용 가능·실제 콘텐츠 품질을 보장하지 않는다. 실제 콘텐츠 제작과 8769의 제작 모드 활성화는 아직 수행하지 않았다.
