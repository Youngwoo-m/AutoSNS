# 운영 웹 4단계 사전 점검

기준: 2026-10-30, 3단계 `661f2cd` 이후. 잠금·복구·채널 실행기를 세 에이전트가 독립적으로 읽기 전용 조사했다. 아래는 구현 완료가 아니라 확인된 제약이다.

## 실행 계약

`common/operations/models.py`의 현재 컨텍스트는 `dry_run=True`, `scope=plan`, `execution_enabled=False`만 허용한다. 계획 승인을 실제 제출 권한으로 바꾸면 안 된다. `dispatch.py`, `publication_gate.py`, `recovery.py`, `production.py`, `common/publishers/`는 아직 없다. 현재 웹이 보여 주는 계획은 원격 예약이 아니다.

## 잠금과 STOP

- `shared`는 `common/shared` 링크다. `axlock.py`의 파일 위치 기반 ROOT는 워크트리에서 가져오면 운영 원본과 다른 STOP·잠금을 가리킨다. 루트별 인스턴스가 필요하며 전역 ROOT 변경은 스레드 간 혼선을 만든다.
- 프로필 별칭은 개인·학과의 공통 자원으로 묶이고 사람이 연 동일 프로필을 기다린다. 이 동작을 보존한다.
- `status()`는 죽은 대기자를 정리하므로 순수 GET에서 그대로 부르지 않는다.
- 기존 STOP 읽기는 부재·손상·접근 실패를 구별하지 않는다. 실제 실행 관문은 clear/stopped/unknown으로 나누고 unknown에서도 제출을 차단해야 한다.
- 기존 실행기는 잠금 대기 전 STOP을 확인한다. 대기 중 정지를 놓치지 않으려면 획득 후·제출 직전 재확인과 STOP 작성/허가 소비의 공통 제어 잠금이 필요하다.
- 새 웹만 바꾸어 모든 기존 작업이 새 제어 잠금을 준수한다고 주장할 수 없다. 기존 8700 서버·래퍼 이행 및 재시작은 운영 전환 단계에서 별도 검증한다.

## 채널 실행기의 재사용 한계

| 채널 | 기존 실행 경로 | 보완해야 할 근거 |
|---|---|---|
| Blogger | 학과 `post_blogger.py`, 개인 `geoai_blogger.py` | 실제 blog ID·권한·게시 ID 조회와 공개 본문 검증 |
| Naver | `publish_naver.py`, `naver_crosspost_personal.py` | 편집기 검증과 공개 검증 분리, 개인 safeworking·프로필 강제 |
| Tistory | `tistory_post.py`, `tistory_crosspost.py` | RSS 제목 일치만으로 unknown 해소 금지, 첨부·카테고리 보존 |
| YouTube | `youtube_upload.py`, `geoai_short_post.py` | 학과도 실제 채널 확인, 예약과 공개 검증 구분 |
| Instagram | `post_instagram.py`, `insta-manual/graph_api.py` | 브라우저 릴과 API 캐러셀 기능 구분, 대상·조회·검증 |
| Threads | `post_threads.py`, `threads_cli.py`, `threads_post.py` | ‘게시 완료(추정)’ 대신 게시 ID·공개 근거 |
| X | `x_post.py` | 인증 subject·게시 ID 조회·공개 검증 |
| TikTok | 직접 API·`tiktok_web.py`·`tiktok_queue.py` | 실행 주인 단일화, 캡션 일부 일치로 성공 판정 금지 |
| Facebook | 독립 실행기 확인되지 않음 | Page 대상·권한·게시/조회 어댑터 신규 구현 |

기존 dry 옵션은 안전한 미리보기와 다르다. Naver/Tistory/Instagram/Threads/TikTok은 브라우저 입력·파일 전송·자동저장을 일으킬 수 있다. Instagram Graph dry도 원격 컨테이너를 만든다. TikTok `_confirm_posted`는 버튼을 클릭하므로 읽기 전용 검증기로 사용하지 않는다. legacy import 자체가 파일 생성·설정/비밀값 해석으로 이어지는 경로도 있다.

## 제작과 구독 비용

`run_claude_job.sh`는 원고 작성부터 실제 발행까지 가능한 광범위한 권한으로 실행한다. 관리 제작기로 그대로 호출하지 않는다. `drafter.review`의 자체 검토는 독립 검산 증거가 아니다.

2026-10-30 16시경 API 키·대체 인증 환경을 제외한 도구 없는 Claude 구독 최소 요청은 성공했다. 그러나 `common/shared/llm.py`는 구독 실패 시 설정의 Anthropic 키로 전환할 수 있다. 환경변수에서 키 하나를 지우는 것만으로 내부 추가 비용을 막았다고 할 수 없다. 관리 제작에는 구독 전용 공급자 정책과 실패 시 중단이 필요하다. 이 점검으로 실제 발행·기존 코드·스케줄·키는 변경하지 않았다.

## 다음 단계에 반영할 결정

실제 운영과 같은 원장·lease·permit·복구 계약을 만든다. 가짜 어댑터는 시험 주입에만 쓰며 별도의 시뮬레이션 전용 제품/DB를 만들지 않는다. 4단계 기본 배포에서는 실제 실행을 계속 비활성으로 두고, 채널별 실제 연결·운영 스케줄 전환·외부 접속은 후속 검증과 활성화 절차로 남긴다. Codex의 Metricool/vidIQ 설치는 독립 웹 서버의 인증 권한이 아니다.
