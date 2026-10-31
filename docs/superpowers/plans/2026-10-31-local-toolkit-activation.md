# 운영 웹 로컬 도구 활성화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 현재 Python3.15의 관리 웹8769에서 외부 호출 없는 제목·태그·조사·CSV·로컬 예약 조회를 명시 기동 옵션으로 사용 가능하게 한다.

**Architecture:** main에서만 엄격한 환경 설정을 해석해 기존 ToolkitPolicy를 주입한다. create_server 기본값과 실행 서비스 경계는 변경하지 않는다. 기존 인증·저장소·CAS·CSV receipt를 그대로 사용한다.

**Tech Stack:** 기존 Python3.15, unittest/mock, SQLite, 기존 브라우저 검증. 신규 의존 설치0.

**Spec:** [승인 설계](../specs/2026-10-31-local-toolkit-activation-design.md). 2026-10-31 사용자 A안 승인 및 실행 계획 작성 지시. 실행 방식은 기존 최대 병렬 SDD를 유지한다. 이 문서는 구현 시작 승인을 뜻하지 않는다.

## Global Constraints

- `AX_LOCAL_TOOLKIT` 미설정/`0`은 disabled, 정확히 `1`만 enabled, 그 밖의 값(빈 문자열·공백 포함)은 시작 전 오류다.
- enabled에는 명시 `AX_WORKSPACE_ROOT`가 필요하다. 없는8767 opt-in은 시작 전 거부한다. factory 기본disabled와 읽기전용 POST503은 유지한다.
- Python3.15 유지, renderer/asset_authorizer None. Pillow·폰트·패키지 자동설치0. 이미지 기능 unavailable 유지.
- ExecutionService/ExecutionPolicy·SNS 인증/refresh·원격 API·발행·launchd·원본R/8700·프로필·STOP·quota 변경0. 추가 결제/API/credit 소비0.
- 정책은 서버 기동 설정이다. HTTP body·선호 저장·GET에서 변경할 수 없다. CSV legacy_reported/미배정과 검토/발행 분리를 보존한다.
- 개인/학과 소유·등록 교차 경로·불변 target·최신 revision·CAS를 완화하지 않는다.9메뉴 유지.
- 공유 작업트리에서 명시 소유 파일만 수정한다. 타인 변경 reset/revert·git add -A 금지. 실제 서버 적용은 부모가 직렬 수행한다.

## Review Focus

1. 오타·공백·빈 환경 값이 조용히 활성/비활성으로 바뀌지 않고 소켓 생성 전 실패한다(Task1).
2. 저장소 없는 opt-in이 운영 원본을 관리 저장소로 대신 사용하지 않는다(Task1).
3. enabled가 renderer·인증·발행·외부 provider 허용으로 확대되지 않는다(Task1/2).
4. 다른 계정/미확인 교차 target/오래된 revision은 활성 후에도 차단된다(Task2).
5. 실패 재시도와 원복이 새 CSV/원고를 과거 DB로 덮어쓰지 않는다(Task2).

## 파일과 책임

| 파일 | 책임 |
|---|---|
| `ax-console/app/web_server.py` | 소켓 생성 전 환경 검증과 main의 정책 주입만 추가 |
| 신규 `tests/test_web_toolkit_startup.py` | 환경 값·저장소·factory/main 주입 및 부수효과 경계 |
| `tests/test_web_toolkit_server.py`, `tests/integration/test_local_toolkit_acceptance.py` | 필요한 활성화 회귀만 보강, 기존 제품계약 재사용 |
| `docs/runbooks/local-sns-toolkit.md`, `docs/audits/2026-10-31-local-sns-toolkit-acceptance.md` | 실제 적용·백업·원복·기능 제한 근거 갱신 |

### Task1: 명시 기동 설정과 기본 비활성 보존

**Interfaces:** `web_server._toolkit_policy_from_env(env: Mapping[str,str]) -> ToolkitPolicy`를 추가한다. 입력은 서버 환경만, 출력은 기존 `ToolkitPolicy(enabled: bool)`다. 실패는 비밀값을 포함하지 않는 한국어 SystemExit. main은 create_server 호출 전에 검증하고 `toolkit_policy=policy`만 추가한다.

- [ ] 신규 startup 시험에서 미설정/0은 false,1+workspace는 true,빈문자/공백/true/2는 SystemExit,1+workspace 미설정/빈값은 SystemExit를 단언한다.
- [ ] `python3 -m unittest tests.test_web_toolkit_startup -v`로 RED를 확인한다. 소켓·원본·auth는 mock, 실제 네트워크0.
- [ ] 해당 함수와 main 주입만 구현한다. workspace 경로 유효성은 기존 create_server가 검증하며 별도 자동생성·source fallback을 넣지 않는다.
- [ ] main 모킹으로 오류 시 create_server 호출0, 정상 시 정책과 기존 source/workspace 전달, renderer/authorizer/execution kwargs 미추가를 검증한다. 정상 serve_forever는 mock KeyboardInterrupt, server_close 호출을 확인한다.
- [ ] 신규 시험과 `python3 -m unittest tests.test_web_toolkit_server -v` GREEN. HTTP 시험은 임시 루트/가상 auth/loopback만 사용한다. 실제 factory 기본false/읽기전용503을 보존한다.
- [ ] 부모가 변경된 명시 파일만 커밋한다. 독립 리뷰는 Task1 인터페이스·설정 반례를 확인한다.

### Task2: 통합 수락·관리 웹 적용·원복 기록

**Consumes:** Task1 `_toolkit_policy_from_env`와 기존 create_server/LocalToolkitService/저장소 계약. **Produces:** 실제8769의 enabled capability·실행 비활성 관측, 데이터 보존 및 원복 기록.

- [ ] 기존 HTTP/통합 시험으로 paid/credits 차단·누락변환문·교차target·stale revision·CSV0/중복/오류·401/409/503 보존을 대조한다. 이미 정확한 반례가 있으면 복제 시험을 만들지 않는다. 추가 gap만 먼저 RED를 만든다.
- [ ] 실제 Python3.15에서는 `python3 -m unittest tests.test_web_toolkit_startup tests.test_web_toolkit_server -v`로 기동/HTTP·Pillow 부재의 unavailable을 확인한다. 기존 이미지 포함 회귀는 `PYTHONDONTWRITEBYTECODE=1 /Volumes/USB256/devAPP/AutoSNS/personal/claude-jobs/.venv/bin/python -m unittest tests.test_web_toolkit_startup tests.test_web_toolkit_server tests.integration.test_local_toolkit_acceptance tests.operations.test_local_toolkit tests.operations.test_tool_cost_policy -v`로 모두PASS/skip0을 확인한다. `TOOLKIT_TEST_PYTHON=/Volumes/USB256/devAPP/AutoSNS/personal/claude-jobs/.venv/bin/python node --test tests/web_toolkit.test.mjs tests/web_toolkit_integration.test.mjs`도 PASS/skip0이어야 한다. 이 시험 환경 선택은 실제 서버의 Python3.15를 변경하지 않는다. 이미지가 unavailable이면 그 상태 자체를 검증하며 성공으로 위장하지 않는다.
- [ ] 부모가 독립 검토 후 owned8769 PID/명령/cwd/포트를 재확인하고 정상 정지한다. W의 managed-workspace 전체(WAL/자산 포함)를0700 backup으로 복사한다.8767/8700/R/프로필은 정지·수정하지 않는다.
- [ ] 기존8769 기동 명령에 **`AX_LOCAL_TOOLKIT=1` 하나만 추가**해 같은Python·source/workspace로 재시작하고 실제 실행 핸들을 기록한다. 새 서비스/renderer/authorizer를 주입하지 않는다.
- [ ] 기존 로그인 아래 capability enabled·external unsupported·execution unconfigured/disabled를 확인한다. 실제 관리 원고/성과에 시험 데이터를 저장하지 않는다. 기능 동작은 임시 초기화 저장소에서 후보→선택variant→CAS 및 CSV 경로로 확인한다.
- [ ] DB integrity/user_version/논리내용과 자산 목록을 백업과 비교한다. 화면 screenshot과 상태를 수락 문서에 기록한다. 실제 데이터에 변화가 있으면 자동 복원하지 않고 보존·분석한다.
- [ ] 원복 명령은 `AX_LOCAL_TOOLKIT` 제거(또는0) 후 동일8769 재시작이다. 원복을 입증할 격리 main 시험을 추가하고, 실제 서버에서 과거 DB 복원을 실행하지 않는다.
- [ ] 사용자 안내에 활성 기능과 이미지Unavailable/legacy가져오기 필요/실발행비활성을 구분한다. SNS 연결·실성과·건축운영·6B~D는 필수후속으로 유지한다. 최종 명시 파일 커밋과 제한 리뷰로 종료한다.

## 병렬화와 자체 검토

Task1 구현과 Task2의 기존 반례·문서 준비는 파일 소유권을 나눠 병렬 가능하다. Task2 실행/재시작은 Task1 독립검토 후 부모가 직렬 처리한다. 기존 작업트리를 유지하고 기본브랜치 병합/푸시/정리하지 않는다.

작성자 자체검토: 승인설계의 기동값·저장소·비활성권한·이미지·원복은 Task1/2로 모두 대응했다. 함수/필드 이름은 실제 ToolkitPolicy/create_server와 일치한다.5개 Review Focus는 각각 시험·적용단계에 배정했다. 변경은 작은 main 경계에 한정하고 새로운 발행/예약기/인증 저장소를 만들지 않는다.
