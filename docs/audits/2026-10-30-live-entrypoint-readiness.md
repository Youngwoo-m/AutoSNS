# 실제 운영 진입점과 공통 발행 관문 연결 준비 점검

2026-10-30. 읽기 전용 소스 조사. 기준 작업 사본 `W=/Users/youngwoo/.codex/worktrees/account-automation-design/AutoSNS`, 원본 운영 자료·코드 `R=/Volumes/USB256/devAPP/AutoSNS`.

## 결론과 증거의 범위

**기존 운영 진입점은 아직 새 phase4의 실행 주인·lease·publication 승인·permit 관문에 연결되지 않았다.** 작업 사본의 공통 계약·가짜 어댑터 수락과 실제 운영 전환을 구별해야 한다. 기존 axlock의 프로필/작업 잠금·STOP을 유지하면서 모든 대상별 외부 쓰기를 새 경계에 연결하는 후속 구현이 필요하다.

다음8개 비밀 아닌 소스 파일의 SHA-256을 W/R에서 비교했고 모두 같았다: `ax-console/app/server.py`, `ax-console/app/publishers.py`, `personal/claude-jobs/run_claude_job.sh`, `dept/naver-blog-auto/run_geoai.sh`, `dept/naver-blog-auto/run_jobs.sh`, `dept/youtube-shorts-auto/run_tiktok_queue.sh`, `dept/youtube-shorts-auto/tiktok_queue.py`, `dept/disaster-shorts/tools/crosspost.py`.

반면 R에는 `common/operations/worker.py`, `dispatch.py`, `common/publishers/__init__.py`, `ax-console/config/operations.json`, `crossposts.json`이 존재하지 않았다. 아래 W의 새 관문 코드가 R의 legacy 실행에 적용됐다고 판단할 수 없다. 실제 launchd 등록/활성 상태·프로세스·계정·예약/공개 상태는 이번 조사에서 조회하지 않았다. `operations.json`의 enabled=false도 실제 legacy launchd가 꺼졌다는 근거가 아니다.

운영 명령·wrapper·Python 모듈 import·브라우저·서비스 API는 실행하지 않았다. 키·토큰·프로필·환경변수 값도 읽지 않았다. 소스 문자열 검색과 위 파일 해시, 작업 사본의 비밀 없는 등록부 JSON만 읽었다. 소스/설정 수정이나 실제 전환은 하지 않았다.

## 1. 현재 호출 그래프

행 번호는 W의 조사 시점 기준이다. 위 해시 비교 파일은 R에서도 동일하다. 나머지 파일의 R 동일성은 별도 확인하지 않았으므로 W의 코드 경로 증거로만 사용한다.

| 진입점 | 현재 호출 경로·행 | phase4 연결 판정 |
|---|---|---|
| 기존 콘솔 일반 작업 | `ax-console/app/server.py:227 run_task` → `:246 subprocess.run(act['cmd'])` | 등록된 legacy action 명령 실행. 새 dispatch/permit 호출 없음 |
| 기존 콘솔 예약 생성 | `server.py:1304` 채널별 tasks.json 행 생성 → scheduler/run_task → action=publish | 관리 원장 회차·delivery와 다른 legacy 작업 ID. 두 원장에 동시에 예약하면 중복 위험 |
| 기존 콘솔 자동 발행 | `server.py:1347 run_publish` → STOP 확인 `:1353` → axlock.hold `:1355` → `publish_call :1334` → 프로젝트별 `.venv/bin/python publishers.py` `:1338` | 기존 STOP/프로필 잠금은 있음. 새 execution_owner/일회성 permit/실제 공개 verify는 없음. `status=='published'`를 done으로 기록 `:1362` |
| 콘솔 Blogger | `publishers.py:67 blogger` → 학과 post_blogger 또는 개인 geoai_blogger → `svc.posts().insert(...isDraft=False).execute()` | 직접 외부 생성. 잘못된 account도 dept 외에는 개인 분기로 들어가므로 신규 adapter가 그대로 위임하면 안 됨 |
| 콘솔 네이버·X | `publishers.py:101 naver` → publish_naver.publish, `:114 x` → x_post | 계정별 제한 일부 존재. 서버 등록 어댑터/permit 전달 없음 |
| 개인 Claude 작업 | `personal/claude-jobs/run_claude_job.sh:3` → R/shared/axlock.py run --job claude.$1 → `:17~18` AX_HOUR 기준 모델/회차 지시문 선택 → `:55` claude -p | 준비/확인 등 기존 회차 의미를 보존해야 함. 자율 도구가 발행할 수 있는 legacy 지시문을 managed 제작기로 표시하면 안 됨 |
| GeoAI 아침/저녁 | `dept/naver-blog-auto/run_geoai.sh:3`/`run_geoai_evening.sh:3` → axlock → geoai_daily.py --go (저녁 --no-video) | wrapper 잠금만으로 새 원장 승인을 통과한 것은 아님. 제작/개인 Blogger/영상/커뮤니티/학과 Threads 분해 필요 |
| 학과 채용 블로그 | `run_jobs.sh:3` → axlock → `:22 jobs_work24.py --go` → `:25 jobs_insta.py --latest --go` → `:32 tistory_jobs.py --latest --go` | 한 wrapper에 학과 네이버·Instagram과 개인 Tistory 부수효과가 묶임. 대상 하나의 permit으로 전체 실행 금지 |
| TikTok 큐 실행 | `run_tiktok_queue.sh:3` → axlock → `:13 pick` 사전 검사 → `:16 tiktok_queue.py` → `tiktok_queue.py:196 upload(...post=True)` | 큐의 실제 제출은 legacy 직접 실행. 전체 큐 강제 실행/시도 초기화로 이행하면 안 됨 |
| 개인 숏츠 | `geoai_short_post.py:121` 자체 shared.axlock 사용 → 업로드 → `:213 tiktok_queue.add` | 자체 프로필 보호는 존재하나 phase4 permit 없음. 업로드 성공과 학과 큐 추가를 다른 delivery로 분리해야 함 |
| 일반 YouTube 업로드 | `youtube_upload.py:247 upload` → 업로드 → `:351~353 tiktok_queue.add` | 일반 업로드에 숨은 학과 큐 부수효과. 관리 route와 기존 add() 양쪽에서 생성하지 않도록 단일 책임 필요 |
| 재난 숏츠 업로드 | `dept/disaster-shorts/tools/publish.py:55 upload` → 예약 업로드, 예약 거부 시 비공개 fallback `:94` → TikTok add `:112` | 업로드·예약·비공개 fallback·후속 공개 전환을 각각 관측 가능한 상태로 보존해야 함 |
| 재난 교차 게시 | `tools/run_crosspost.sh:3` → axlock → `crosspost.py:129 run` → `:134 ensure_public` → `:142~159 Instagram/Blogger/Naver/Threads` → 대상별 crosspost.json | 공개 전환과 4개 채널 게시가 한 실행에 포함됨. 대상별 permit 및 원격 결과 ID가 필요 |
| 학과 채용 영상 | `publish_career.py:255 _upload` → TikTok add `:257~258` → IG `:284`, Threads `:286`, X `:288` | 원본 업로드 성공 뒤 실패 대상만 재개하는 구조를 보존. --no-ig/--no-threads, 변환·AI 고지도 보존 |
| 학과 주간 뉴스 영상 | `run_weekly.py:154 upload` → `:191~192 네이버`, 앵커 생성 때 `:196~198 Instagram`, `:206~209 config 기반 TikTok`, `:227 Threads`, `:237~238 X` | 일반 YouTube 업로드 내부 큐 add와 별도 TikTok API 경로까지 구별해야 함. disabled인 경로를 이행 중 켜지 않음 |
| 개인 Tistory→네이버 | `personal/naver-blog-auto/tistory_crosspost.py:578 main` | plan/dry/go 구분은 있으나 dry는 편집기 입력 가능. pure inspect와 동일시 금지 |

## 2. 새 공통 경계와 아직 없는 실행 연결

- W `common/operations/dispatch.py:23 submit_trigger`는 source=launchd/console, phase=prepare/submit/verify와 execution_owner=managed·schedule_owner·enabled를 검사한다(`:27~40`). 기존 wrapper와 server.py가 이 함수를 호출하는 경로는 이번 조사에서 발견되지 않았다.
- W `worker.py:41 run_once`는 기본 policy disabled면 종료한다. `:57` managed owner, `:64` 서버 등록 계정 프로필 잠금, `:76` 읽기 전용 inspect_target, `:93~100` authorize→consume→adapter.submit 순서다. 실제 factory `common/publishers/__init__.py:2 build_adapters`는 빈 dict다.
- W `ax-console/app/web_server.py:582~586`은 RuntimeStore와 기본 disabled 정책·빈 복구 어댑터·미등록 probe를 구성한다. 새 관리 웹의 저장·복구 API가 곧 기존 source의 발행 실행 루프가 된 것은 아니다.
- W `common/operations/crossposts.py:69 preview_crossposts`는 기존 owner면 observe_legacy, 미확인 활성 상태는 unknown으로 표시한다. 반환 `execution_enabled=False`(`:88`)이고 실제 enqueue/게시를 하지 않는다.
- W `common/shared/axlock.py:167`와 R의 같은 역할 `:353`은 잠금 후 명령을 `AX_LOCKED=1`로 실행한다. 이 값은 재진입 잠금 방지 기호이며 publication 허가/불변 승인/사용자 신원을 뜻하지 않는다. 새 발행기가 이 환경변수만 보고 permit을 신뢰하면 안 된다.

## 3. 후속 연결에서 먼저 막아야 할 경로

1. **관리 주인과 legacy 주인의 동시 실행:** 관리로 옮긴 작업의 console/launchd/direct CLI/내부 subprocess/큐 생성 caller를 한 묶음으로 전환한다. 한 경로라도 미연결이면 해당 작업은 legacy로 유지한다. registry의 owner 문자열만 바꾸지 않는다.
2. **검사·dry에 숨은 쓰기:** publishers.py의 네이버 dry, tistory_crosspost.py --dry, 재난 ensure_public은 pure inspect가 아니다. 특히 `dept/disaster-shorts/tools/crosspost.py:106~125 ensure_public`은 videos.list 뒤 조건에 따라 videos.update로 비공개 영상을 공개한다. 읽기 전용 계정 확인 adapter에 재사용하면 permit 이전에 외부 쓰기가 발생한다.
3. **대상 하나를 승인하고 전체 wrapper 실행:** 채용/GeoAI/재난 wrapper에는 여러 계정·채널의 외부 부수효과가 있다. target별 prepare/submit/lookup/verify로 분해하거나 각 외부 쓰기 전에 서버가 검증한 개별 permit을 전달해야 한다. stdout 마지막 줄 성공은 공개 검증이 아니다.
4. **직접 CLI의 기본 실행:** `tiktok_queue.main` 등은 wrapper 없이 직접 부르면 외부 실행이 가능하다. 새 managed 전용 진입점은 미등록 executor·누락/위조 permit을 subprocess 생성 전에 거부해야 한다. 기존 작업의 수동 사용을 임의 삭제하는 방식이 아니라 owner별 명시 경로로 나눈다.
5. **개인 fallback/cwd import:** publishers.py는 cwd를 sys.path 앞에 넣고 dept 외 account를 개인 Blogger로 보낸다. 신규 경계는 enum·connection·실대상·credential/profile owner를 먼저 확인하고 정확한 interpreter/cwd를 고정한다. environment는 비밀값 allowlist와 구독 정책까지 별도 검증한다.
6. **원격 성공 뒤 기록 실패:** legacy task done/큐 posted/crosspost.json은 공통 request_started·unknown과 연계되지 않았다. 자동 재실행으로 원본을 다시 업로드하지 말고 강한 remote ID/대상/내용 증거로 먼저 조회한다.
7. **원격 공개 전환·초안·업로드를 읽기로 취급:** videos.update, posts.insert, 편집기 초안·미디어 container 생성까지 외부 쓰기로 목록화한다. public post 버튼만 permit 대상으로 한정하지 않는다.

## 4. 교차 경로23개 보존 수락표

W `ax-console/config/crossposts.json`의 실제23개 rule ID를 열거했다. 모두 delivery_owner=legacy다. enabled 누락은 True로 보정하지 않고 미확인으로 남긴다. 이 등록부는 이행 기준선이며 현재 운영 활성·성공 증거가 아니다.

| rule ID | 보존할 원본→대상·조건 |
|---|---|
| geoai-short.tiktok | 개인 YouTube→학과 TikTok. 업로드/예약/공개 응답·개인 채널 확인, source=geoai_short, 30분 지연 |
| youtube-generic-personal.tiktok | 개인 일반 업로드→학과 TikTok. video ID·public·설명에 쿠팡 없음 |
| youtube-generic-dept.tiktok | 학과 일반 업로드→학과 TikTok. 위와 같은 일반 업로드 조건 |
| geoai.threads | 개인 Blogger→학과 Threads. 아침/저녁 슬롯, Blogger published 또는 dry 조건 및 no-video/threads 분기 |
| jobs.tistory | 학과 네이버→개인 Tistory. 네이버 성공·초안6시간 이내·네이버 게시 채용1건 이상·유효 채용3건 이상 |
| tistory.safeworking | 개인 Tistory→개인 네이버. 공개 확인·지정6주제·숏츠 전용/학과 회차 제외 |
| naver.blogger | 학과 네이버→학과 Blogger. naver_weekly caller |
| blogger.tistory | 개인 Blogger→개인 Tistory. Tistory 명시 비활성 아니어야 함 |
| geoai.community | 개인 Blogger→개인 YouTube 커뮤니티. 아침/저녁 및 기존 published/dry 조건 |
| news.naver_blog | 학과 YouTube→학과 네이버. weekly_news·YouTube 성공 |
| news.instagram | 학과 YouTube→학과 Instagram. weekly_news·YouTube 성공·앵커 영상 생성 |
| news.threads | 학과 YouTube→학과 Threads. weekly_news·YouTube 성공 |
| news.x | 학과 YouTube→학과 X. weekly_news·YouTube 성공 |
| news.tiktok | 학과 YouTube→학과 TikTok. weekly_news·YouTube 성공·tiktok_enabled. **등록부 enabled=false 보존** |
| career.tiktok | 학과 YouTube→학과 TikTok. publish_career·YouTube 성공 |
| career.instagram | 학과 YouTube→학과 Instagram. publish_career·YouTube 성공·no_ig=false |
| career.threads | 학과 YouTube→학과 Threads. publish_career·YouTube 성공·no_threads=false |
| career.x | 학과 YouTube→학과 X. publish_career·YouTube 성공 |
| disaster.tiktok | 학과 YouTube→학과 TikTok. disaster_publish 업로드/예약 응답 |
| disaster.instagram | 학과 YouTube→학과 Instagram. disaster caller·이전 대상 상태 published/shared_unconfirmed면 건너뜀 |
| disaster.blogger | 학과 YouTube→학과 Blogger. 위와 동일한 대상별 건너뜀 |
| disaster.naver_blog | 학과 YouTube→학과 네이버. 위와 동일한 대상별 건너뜀 |
| disaster.threads | 학과 YouTube→학과 Threads. 위와 동일한 대상별 건너뜀 |

필수 비교 시험:

- 동일 고정 이벤트 묶음으로 legacy 조건과 새 graph의 대상 집합·조건·슬롯·변환·AI 표시·출처·원본 소유·실대상 귀속을 비교한다. `dry`를 실발행 이벤트로 바꾸지 않는다.
- TikTok `tiktok_queue.py:27~32,69~96,145~170`의 30분 add 지연·신규/과거 모두3시간 간격·07:00 포함/23:00 제외·14일·최대5시도·skipped/posted 제외·video 존재·hold_until·new_before_backfill/priority/not_before 정렬·backfill 전후 신규 대기를 동치 fixture로 비교한다. queue_add가 지연 책임자면 관리 경로가 다시30분 더하지 않는다.
- `tiktok_queue.py:198~213`의 인프라 실패 시 시도 증가 제외·동일 화면 오류2회 다음 날 hold를 보존한다. 일괄 retry/reset은 이행 동작으로 제공하지 않는다.
- 개인 원본과 학과 대상은 다른 delivery/승인/계정 잠금을 갖지만 원본 제작은1회다. YouTube 성공+TikTok 실패에서 YouTube submit 누적1, TikTok delivery1·실패 대상만 재개를 입증한다.
- 재난 예약은 공개 전 verified가 아니며, 기존 crosspost.json의 published/shared_unconfirmed는 legacy 관측으로 보존한다. shared_unconfirmed를 내용 검증 완료로 승격하지 않는다.
- 모든23개 전환 전후 회차/부수효과 graph와 enabled/unknown 상태를 비교한다. 이 조건 수락 없이 기존 graph를 줄이거나 꺼진 작업을 켜지 않는다.

## 5. 후속 수정 파일과 적용 순서

아래는 구현이 아니라 파일 단위 후속 작업 지도다. 원본 R에 바로 적용하지 않는다.

1. **서버 소유 단일 진입점:** 신규 `common/operations/entrypoints.py`(등록 executor·owner·회차 해석), `common/operations/worker_service.py`(관리 실행 루프·lease heartbeat·shutdown), `tests/integration/test_entrypoints.py`. 기존 `ax-console/app/server.py`의 run_task/publish_call/run_publish는 owner에 따라 새 enqueue 또는 legacy 실행을 명시 선택하도록 수정한다. 관리되지 않은 작업은 계속 legacy다.
2. **안전한 legacy subprocess 경계:** `ax-console/app/publishers.py`와 신규 `common/publishers/blogs.py`, `social.py`, `legacy_bridge.py`에서 strict account/connection·interpreter/cwd·환경 이름 allowlist·일회성 permit 전달/검증·pure transform·submit 결과·lookup/verify를 분리한다. 실제 파일명은 후속 설계에서 확정하되 지금 동적 모듈 import를 노출하지 않는다.
3. **개인 제작 분리:** `personal/claude-jobs/run_claude_job.sh`, `공통규칙.md`, 작업별 지시문, `jobs.json`의 phase와 명령을 명시 매핑한다. 기존 AX_HOUR·precheck·준비/공개 확인 회차를 보존하고, managed 제작 도구에서 직접 발행 명령을 제거하는 실제 격리를 구현한다. 구독 비용 감사는 별도 필요하다.
4. **다중 부수효과 분리:** `dept/naver-blog-auto/geoai_daily.py`, `run_geoai*.sh`, `run_jobs.sh`, `jobs_work24.py`, `tistory_jobs.py`, `dept/insta-cardnews/jobs_insta.py`, `threads_cli.py`, `post_reel_cli.py`를 target별 호출로 연결한다. 원본/변환/검토 hash를 한 번의 공통 계약으로 전달한다.
5. **영상·큐 단일 책임:** `dept/youtube-shorts-auto/youtube_upload.py`, `geoai_short_post.py`, `run_weekly.py`, `publish_career.py`, `tiktok_queue.py`, `run_tiktok_queue.sh`, `crosspost.py`; `dept/disaster-shorts/tools/publish.py`, `crosspost.py`, `run_crosspost.sh`. 업로드·예약·공개 전환·추가 채널·큐 add를 별도 target mutation으로 나누고 관리 owner 때 숨은 legacy enqueue를 억제한다. 필요 wrapper는 원래 axlock 첫 줄을 유지한다.
6. **개인 교차 경로:** `personal/naver-blog-auto/tistory_crosspost.py`, `dept/naver-blog-auto/naver_crosspost_personal.py`, `blogger_crosspost_personal.py`의 범위·출처·카테고리·AI 고지·이미 게시 연결을 보존한다.
7. **등록/전환:** `ax-console/config/operations.json`, `crossposts.json`, 기존 `automations.json`의 실제 caller mapping과 wrapper/launchd 목록을 확정한다. 신규 `common/operations/cutover.py`, `backup.py`, `tests/integration/test_acceptance.py`, `docs/runbooks/account-operations-cutover.md`에서 모든 진입점·원격 결과·unknown·quota를 포함한 수락/롤백 증거를 요구한다. 운영 plist 재등록은 이 증거 후 작업별 직렬 checkpoint다.

## 6. 실제 적용 전 최소 증거

실제 대상별 읽기 전용 인증/계정 확인, 순수 prepare 무쓰기, permit 이전 외부 쓰기0, 승인된 대상만 submit1, 응답 유실→재시작→조회→검증 후 중복0, 다른 계정 비밀/프로필 접근0, 원본 success 보존·실패 대상만 재개, 모든 caller owner 단일화, 스케줄/disabled/교차23경로 불변, 백업/롤백 후 신규 원격 이력 보존이 필요하다.

현재 이 보고서로 확인한 것은 **소스상 미연결 경계와 후속 수정 위치**다. 실제 인증·발행·공개 검증·운영 전환 완료의 증거로 사용하지 않는다.
