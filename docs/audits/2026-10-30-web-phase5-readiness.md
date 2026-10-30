# 운영 웹 5단계 사전 조사

2026-10-30. 기존 성과 코드와 계정별 경로를 두 에이전트가 읽기 전용 조사했다. 수집기 실행·원격 조회·자격증명 읽기/복호화·프로필 열기·원본 이행은 수행하지 않았다. 아래는 후속 실행 계획의 근거이며 5단계 구현 완료를 뜻하지 않는다.

추가 현장 확인: 원본 운영 경로의 `common/analytics/snapshots/parts`에는9개 JSON이 존재한다. 단순 JSON/파일 읽기로 blog132·blogger71·instagram137·threads59·x33·youtube108·smds380·searchconsole2개 items와 별도 indexing 자료를 확인했다. 이는 파일 행 수이며 오늘 실적·공개 검증 수가 아니다.9개 모두 최상위 observed_at/status가 없어 관측 시각·조회 실패·실제0을 확정할 공통 근거가 없다. 아래 에이전트의 ‘worktree에 snapshots 없음’은 원본 자료까지 없다는 뜻이 아니다. 수집기·token refresh는 실행하지 않았다.

# 5단계 준비 조사: 성과·다음 기획

2026-10-30. 구현 승인 전 읽기 전용 코드 조사다. 수집기 실행·모듈 import·원격 API·비밀 복호화·브라우저/프로필 접근·운영 데이터 변경은 하지 않았다. 이 보고서만 작성했다.

## 결론

현재 웹의 성과는 의도적으로 `unavailable`이다. 기존 analytics에는 학과 중심의 지표 수집 코드가 있지만, 원본/배포/게시 ID와 관측 시각을 보존하는 공통 성과 계약은 없다. 그대로 웹 요청에서 실행하거나 기존 집계를 실제 기간 성과로 해석하면 안 된다. 이 worktree에는 `common/analytics/snapshots/`가 없으므로 실제 최신 수집 건수·최근 성공·인증 유효성은 확인하지 못했다. 아래 coverage는 코드상 범위다.

근거 요구: 전체 계획 `docs/superpowers/plans/2026-10-30-account-channel-automation.md` T14는 `collect_delivery_metrics(ctx,remote_id,collector)`, `record_metrics(store,delivery_id,result)`, `build_planning_context(account_id,registry,store)`와 결과 `status(ok/unsupported/error),values,observed_at,remote_id,target_id`를 요구한다. 화면 설계 `docs/superpowers/specs/2026-10-30-account-web-screens-design.md`의 성과 절은 실제 0/조회 오류/미지원/미수집 구분, 제작비→원본 계정·채널 실적/발행량→대상 계정, 다음 기획 연결과 승인 범위 유지가 기준이다.

## 1. 원천 파일·스키마와 채널 범위

공통 저장 경로는 `common/analytics/common.py`의 `SNAP_DIR/parts/<name>.json`이며 루트 호환 링크는 `analytics -> common/analytics`다. `save_part`는 보통 빈 items로 기존 비어 있지 않은 파일을 덮지 않는다. 관측 실패가 과거 성공값 뒤에 숨을 수 있다. 모든 part에 통일된 schema_version/account_id/connection_id/target_id/observed_at/status가 있는 구조가 아니다.

| 채널/계정 | 재사용 후보 파일·함수 | 저장 part·필드 / 한계 |
|---|---|---|
| YouTube 학과 | `collect_youtube.py:collect` | `youtube.json`: channel(title,handle,subscribers,total_views), items(id,title,date,type,seconds,privacy,views,likes,url). 고정 학과 토큰 경로와 `mine=True`; 개별 검증 게시 ID 계약은 없음 |
| YouTube 개인·학과 심화 | `retention_report.py:_videos,_half_life,main` | `--geoai`/학과 토큰 분기. 기간별 views,averageViewDuration,averageViewPercentage와 audienceWatchRatio 코드 존재. 결과는 콘솔 출력이며 part/원장 저장 없음 |
| Instagram 학과 | `collect_instagram.py:_row,_via_feed,_via_grid,collect` | `instagram.json`: profile(username,uid,followers,posts), items(title,date,type,caption_empty,pages,seconds,likes,comments,views,url). 사용자 고정, 미디어 ID를 결과에 직접 보존하지 않고 URL code만 보존. 저장·공유·도달 수집 없음. 숫자 누락은 `or 0`으로 소실 |
| Threads 학과 | `collect_threads.py:collect,_fill_views,_views` | `threads.json`: profile(username,url), items(title,date,type,source,url,선택적 views). 고정 학과 사용자. 게시 URL 마지막 pid는 수집 중 사용하나 결과 ID 필드 없음. 60일 이전 또는 실패 시 지난 views 재사용; 항목별 새 관측 시각 없음 |
| X 학과 | `collect_x.py:collect` | `x.json`: account(username), items(title,date,type,source,url). `channels/youtube-shorts-auto/x_posts.json`과 logs의 완료 URL에서 목록 복원. API 조회 없이 게시량만 집계; 조회·반응 지표 없음 |
| 네이버 학과 | `collect_web.py:collect_blog`, `collect_naver_stats.py:_dashboard,main` | `blog.json`: items(title,date,type,source,url)에 통계 views/likes/comments 추가, part에 views_at(날짜). studs23 고정. URL 글번호를 통계 contentId로 사용. 부분 실패별 상태·관측 시각 없음 |
| 네이버 개인 safeworking | 위 코드에는 해당 없음 | 학과 BLOG_ID/기존 학과 프로필 코드라 단순 재사용 불가. 계정별 대상/프로필 주입과 검증 필요 |
| Blogger 학과 | `collect_blogger.py:collect` | `blogger.json`: blog(title,url), items(title,date,type,source,url). smuds2026 공개 feed 목록만; 개인 geoaina는 의도적으로 제외. 조회·반응 지표 없음 |
| 홈페이지 학과 | `collect_web.py:collect_smds` | `smds.json`: items(title,date,type,source,pages,url). 고정 3개 게시판의 nttId 중복 제거/콘텐츠 유형 분류. pages는 첨부 이미지 장수이며 조회수가 아님 |
| Search Console 개인·학과 혼합 | `collect_searchconsole.py:collect,_query,_total,_sites` | `searchconsole.json`: sites,period(start,end),items(site,query,clicks,impressions,ctr[%],position),pages(site,page,clicks,impressions),per_site,totals. top query 20/page 10으로 절단. 게시물 전체 지표가 아니라 검색 유입 근거 |
| Tistory | `common/shared/published_history.py:_tistory` | 개인 na-geoai RSS 제목/날짜/URL 이력만. analytics 성과 수집기는 없음. `personal/naver-blog-auto/tistory*.py`는 발행/로그인/수정 작업이며 지표 수집 근거가 아님 |
| Facebook | 해당 성과 수집기 없음 | 웹 플랫폼 목록·외부 연동 후보의 존재와 실제 수집 지원은 별개 |
| TikTok·Kakao | 해당 analytics 성과 수집기 없음 | 대기열/게시 보고를 성과로 바꾸지 않음 |

`collect_youtube.py:collect_via_rss`는 기존 item 지표를 유지하고 새 항목의 seconds/views/likes를 0으로 채우며 `degraded='quota'`로 표시한다. 이 0은 확인된 실제 0이 아니다. `build_report.py:merge/fill_missing_titles`는 날짜 근접 YouTube 제목으로 IG/X 빈 제목을 추정(`title_inferred`)한다. 제목·날짜 일치는 원본/배포 연결 증거로 사용할 수 없다.

`build_report.py:build`의 `snapshots/YYYY-MM-DD.json`은 date,subject,week_count,cum_count,subscribers,followers,total_views,by_media 등 집계 요약이다. 게시 ID별 시계열 저장소가 아니다. `build_monthly.py:analyze`의 yt_views는 해당 월에 게시된 영상의 현재 누적 조회수 합이며 그 달 발생 조회수와 다르다. `window_report.py`도 게시일 cohort의 현재 views 비교다.

## 2. 연결 키와 현재 웹 경계

- 원본: `contents.id + revisions.revision + manifest_hash`, 소유자는 `contents.owner_account_id` (`common/operations/database.py` DDL). 원본 제작비는 이 키에 귀속해야 한다.
- 배포 계획: `deliveries.id`; UNIQUE `(content_id,revision,connection_id,publication_purpose,schedule_slot)`. `ledger.py:_context`/계획 생성에서 owner와 destination을 나눈다.
- 실행 게시: `runtime_deliveries.id`는 deliveries FK이며 `context`에 content_id/content_revision/manifest_hash/owner_account_id/destination_account_id/connection_id/target_id/platform을 보존하고 remote_id/url/state를 별도 저장한다. `RuntimeStore.get_delivery/list_operations`, `finish_attempt`가 연결 근거다.
- 공개 검증: `common/operations/verification.py:verify_delivery,strong_identity`가 remote_id/target_id/destination_account_id와 콘텐츠 증거를 대조한다. 이 검증을 통과한 배포 중심으로 수집 대상을 제한하는 것이 T14 기준이다. 상태/게시 ID가 없는 옛 목록은 자동으로 검증 완료로 승격할 근거가 없다.
- 기존 analytics는 대부분 URL로만 join할 수 있다. YouTube는 id 직접 보존; Naver는 URL 글번호; Threads/Instagram/X/Blogger/Tistory/홈페이지는 플랫폼별 URL 정규화와 target_id 결합이 필요하다. URL 문자열 또는 제목만으로 계정 간 묶기 금지. 기존 수집 JSON의 id와 등록부 연결·대상 일치는 별도 검증해야 한다.
- `ax-console/app/read_model.py:build_snapshot`은 `metrics={'status':'unavailable','items':[]}`를 고정한다. `_delivery`의 legacy id는 경로/작업 해시이며 remote_id가 없다. 각 레거시 완료 기록도 공개·내용 미검증이라고 명시한다.
- `ax-console/app/workspace_snapshot.py:compose_workspace_snapshot`은 관리 콘텐츠/배포 계획만 합치고 metrics를 채우지 않는다. `web/app.js:renderAnalytics`는 조회/저장·공유/원문 유입/제작비 모두 미수집으로 표시한다.
- 현재 `common/operations/database.py` v3 DDL에 metrics 테이블이 없고 `common/operations/metrics.py`, `planning_context.py`도 없다. `common/publishers/protocols.py:PublicationAdapter`는 inspect_target/prepare/submit/lookup/verify 계약만 가지며 metrics 메서드는 없다. `common/publishers/`에는 이 protocol과 `__init__.py`만 존재한다.

## 3. import·조회·실행 부작용

| 경로 | 정적 조사에서 확인한 부작용/조회 경계 |
|---|---|
| `read_model.py` | 표준 라이브러리만 import. `build_snapshot`은 허용 로컬 파일을 제한된 크기/개수로 읽고 링크는 거부; 쓰기·원격 호출 없음. 임의 홈 경로 탐색도 없음 |
| `workspace_snapshot.py` / `database.py:connect_database` | 명시 DB의 `mode=ro` 연결. initialize_database는 별도 생성·스키마 변경 경로이므로 읽기 화면에서 호출하면 안 됨 |
| `analytics/common.py` | import 자체가 snapshots/out/logs 디렉터리를 생성. load_part 본문은 JSON 읽기지만 import까지 순수 조회가 아님. log는 로그 쓰기, save_part는 디렉터리/파일 쓰기 |
| Instagram·Threads 수집기 | import가 post_instagram→채널 common을 경유해 posts/logs/profile 디렉터리 생성 가능. collect는 ChromeDriver와 저장 프로필을 열고 네트워크 요청·쿠키 사용, finally quit. 내부 잠금은 없으므로 별도 잠금 wrapper 필요 |
| Naver 통계 | main은 publish_naver/build_driver import 및 저장 프로필 Chrome 실행, 내부 API 요청과 blog.json 덮어쓰기. 채널 common도 import 시 디렉터리 생성 |
| YouTube/Search Console/retention | 함수 실행은 token_store/자격증명 읽기 및 필요 시 refresh와 원격 API. YouTube collect는 갱신본 미저장, retention은 load_google(save=False). Search Console `_creds`는 load_google 기본 경로이므로 읽기 화면에서 토큰 처리 실행을 허용할 근거가 없음 |
| `collect_x.py:collect` | 원격 호출은 없지만 기존 로그 전체와 x_posts.json을 읽음. import 시 analytics/common 디렉터리 생성; CLI는 save_part/log 쓰기 |
| `build_report.py`, `build_monthly.py` | import/common과 CLI의 HTML/MD/XLSX/스냅샷 쓰기. 현재 reports를 조회용 순수 모델로 직접 사용 불가 |
| `published_history.py:history` | 캐시 miss/TTL 만료 시 `_fetch` 원격 요청, `~/.cache/autosns-llm/history.json` 생성·변경. 함수 이름이 조회여도 파일 읽기만 하는 함수가 아님 |
| `run_weekly_report.sh` | 기존 axlock 진입과 브라우저별 LOCKRUN 존재. DRYRUN도 수집·토큰·프로필 접근·파일 생성 실행하며 메일만 건너뜀. 월간 wrapper 등도 단순 읽기 점검용으로 실행하면 안 됨 |

`run_weekly_report.sh`는 Naver `profile:naver`, Threads/Instagram `profile:insta`로 잠근다. 두 리소스는 사용자 AGENTS.md의 학과 통합 프로필에 해당한다. 신규 수집 실행 승인 뒤에도 수집 함수 직접 호출로 wrapper 잠금을 우회할 수 없다.

## 4. 다음 기획의 기존 재사용 한계

`ax-console/app/agents/planner.py:search_queries`는 ACCOUNT와 무관하게 `secret_env.read()['SEARCHCONSOLE_TOKEN']` 개인 토큰을 쓰고 SITES[ACCOUNT]만 바꾼다. T14의 학과 요청→개인 토큰 조회 0 조건을 충족하지 않는다. `collect_searchconsole.py:_token_paths/collect`도 저장된 모든 토큰을 탐색하고 첫 접근 계정으로 같은 site를 중복 제거하므로 계정/연결별 승인 사이트 경계가 없다. 일부 인증·site 실패를 건너뛴 뒤 빈 합계 0을 낼 수 있어 정상 0과 오류가 섞인다.

`planner.py`의 SITES에는 개인 safeworking이 없고 CHANNELS는 학과에 Facebook/TikTok, 개인에 safeworking이 없다. `drafter.py:past_titles`는 `history(query,limit=30)`를 채널/계정 제한 없이 호출한다. `published_history.py`는 개인/학과 공개 RSS를 함께 모으고 제목으로 중복을 합치며 safeworking 채널이 없다. 이력 중복 방지에는 쓸 수 있으나 원본 소유권이나 성과 식별 근거로 사용하면 안 된다.

재사용할 것은 플랫폼 응답 파서, 날짜·ID 변환, API 필드 처리와 기존 공개 이력 수집 로직이다. 계정별 등록부 자격증명/허용 사이트/검증 게시 ID를 주입하는 경계와 결과 상태/관측 시각/출처 보존은 새 계약으로 설계해야 한다. Instagram·Threads는 학과 전용 브라우저 로직, X·Blogger·홈페이지는 목록 수집, Tistory·Facebook은 실제 성과 어댑터 없음으로 명시한다. 미구현 채널을 임의 개인 Instagram 연결 등으로 만들어서는 안 된다.

## 5. 계획에 반영할 최소 수락 조건

1. 웹 GET은 저장된 관측값과 지원 상태만 읽으며 수집·네트워크·토큰 복호화·브라우저·캐시 쓰기를 유발하지 않는다. 수집 실행은 별도 권한/작업 경계다.
2. 배포 단위 결과에 T14 필드와 connection/플랫폼/owner/destination/content revision을 연결하고 누적 지표와 기간 지표·기간/관측 시각·과거값 재사용을 구분한다. unknown 값을 0으로 보정하지 않는다.
3. 미수집/unsupported/error/실제 0 fixture, 공개 미검증 배포 제외, personal 원본→dept 대상 성과 귀속, 계정 필터·비용 중복 합산 방지, 학과 요청의 개인 토큰 접근 0을 검증한다.
4. 기존 JSON은 읽기 전용 legacy 원천으로 취급하고 파일 부재·손상·오래됨·부분 실패를 나타낸다. 현재 파일이 없다는 이유로 수집 성공이나 지표 0을 생성하지 않는다.
5. Instagram·Threads·X·Tistory·Facebook도 플랫폼별 지원표와 실패 상태에 포함한다. 실제 수집 가능/연결됨/인증 유효함은 각각 검증하기 전에는 주장하지 않는다. 성과 기반 제안은 저장 가능한 근거이며 자동 채택·발행 승인을 확대하지 않는다.


---

# 5단계 폴더·데이터 분리 준비 조사

2026-10-30, 현재 작업 사본의 코드·링크를 읽기 전용 조사했다. 실행 규칙 통일 후 폴더를 분리하는 접근 A를 전제로 한다. 운영 프로세스·환경변수·토큰·키·프로필·실제 운영 파일은 열거나 실행하지 않았다. 아래 실제 경로는 **작업 사본에서 관찰한 위치와 코드가 계산하는 위치**이며, 운영 원본의 존재·실행 환경까지 검증했다는 뜻은 아니다.

## 1. 현재 원본·자산·실행·설정 경로

`R`은 명시적 운영 자료 루트, `W`는 별도 관리 저장 루트다. 작업 사본 자체는 `/Users/youngwoo/.codex/worktrees/account-automation-design/AutoSNS`다. 사용법의 운영 루트 예시는 `/Volumes/USB256/devAPP/AutoSNS`이며, 현재 가동 프로세스의 환경은 이번 범위에서 확인하지 않았다.

| 구분 | 현재 경로·결정 방식 | 코드 근거 |
|---|---|---|
| 관리 원본·자산 | `W/{personal|dept}/content/{content_id}/revisions/{revision}/{request_uuid}/manifest.json`, 같은 폴더의 `asset_*`; 준비 파일은 `W/.staging/{request_uuid}` | `common/operations/content_store.py:218` `ContentStore._save`; 자산은 확장자 이름이 아닌 asset ID로 저장하며 manifest가 원래 이름·해시를 보존 |
| 관리 원장·설정·실행 상태 | `W/operations.sqlite3` 하나. 콘텐츠/revisions/reviews, integration_settings, jobs/runs/deliveries, runtime_runs/runtime_deliveries/attempts, 승인·복구·할당량 근거가 함께 저장됨 | `common/operations/database.py:6`, `DDL/OPERATIONS_DDL/RUNTIME_DDL`; `RuntimeStore.__init__/_db` |
| 웹 루트 선택 | `AX_SOURCE_ROOT` 필수, `AX_WORKSPACE_ROOT` 선택; W 미지정이면 관리 저장소 미생성. R과 W의 포함 관계를 금지 | `ax-console/app/web_server.py:559` `create_server`, `:598` `main` |
| 관리 등록부 | 별도 지정 `AX_OPERATIONS_REGISTRY`, 미지정 Ledger 기본은 코드 쪽 `ax-console/config/operations.json`; registry 옆 `crossposts.json`도 읽음 | `web_server.py:581,606`; `common/operations/registry.py:25` `load_registry` |
| legacy 콘솔 원본·배포 관측 | `R/ax-console/data/content/*/*/*/meta.json`, 콘솔 tasks 등; 개인 기록 `R/personal/claude-jobs/state/*.jsonl`; 학과 영상 `R/dept/disaster-shorts/*/upload.json`; TikTok 큐 `R/dept/youtube-shorts-auto/posts/tiktok_queue.json` | `ax-console/app/read_model.py:302` `build_snapshot`, `:394,448,468,482` |
| legacy 학과 프로젝트 | `dept/naver-blog-auto`, `dept/youtube-shorts-auto`, `dept/insta-cardnews` 각각 `config.json`, `posts`, `logs`, `title_history.json`; 개인 프로젝트도 `personal/naver-blog-auto/common.py`에서 독립 BASE_DIR 계산 | 각 `common.py:7` 부근. 일부 common은 import 때 mkdir하므로 조사 도구에서 import 금지 |
| 아직 학과에 있는 개인 코드 | `dept/naver-blog-auto/geoai_*.py`, `dept/youtube-shorts-auto/geoai_short_post.py`, `geoai_video.py`, `geoai_youtube_auth.py`, `geoai_community*.py` | T13 이동 대상과 일치. `geoai_short_post.py:28,32`는 자기 폴더의 개인 전용 토큰 경로 사용; 이름만 기록하고 내용은 읽지 않음 |
| 공용 코드·자산 | `common/shared`, `common/analytics`, `common/assets`, `common/remotion-shorts`, `common/tools`; 개인 전용 자산 `personal/assets`도 존재 | 디렉터리/링크 목록 관찰 |
| 실행 환경 | 기존 `server.publish_call`은 `R/channels/{프로젝트}/.venv/bin/python`, cwd도 그 프로젝트; `run_geoai.sh`는 자기 폴더로 cd 후 `./.venv/bin/python` 실행 | `ax-console/app/server.py:1334`; `dept/naver-blog-auto/run_geoai.sh:3,16` |
| 공용 잠금·STOP | `R/ax-console/data/locks`, `STOP.json`, `skip_once.json`, `logs/orchestrator.log`; 카탈로그 `R/ax-console/config/automations.json` | `common/shared/axlock.py:40` 및 `LockPaths` |
| 로그인·비밀값 경로 | 계정 로그인 `~/.autosns-login/{dept|personal}`; 암호화 파일 루트 `secrets.env.enc`는 공용 참조 | `axlock.py:90` 계정 매핑; `common/shared/secret_config.py:15`; 경로만 조사, 열람·복호화 없음 |

주의: 문서의 `AX_WORKSPACE_ROOT="$PWD/ax-console/data/managed-workspace"`는 cwd가 운영 R이면 `create_server`의 R/W 분리 검사에 걸린다. 현재 작업 사본처럼 운영 R과 다른 checkout에서 지정하거나 R 밖 명시 절대경로를 써야 한다. 경로 registry도 이 분리 불변식을 유지해야 한다.

## 2. 이미 분리된 것과 공용으로 유지할 것

- 관리 파일은 이미 owner별 분리다. 대상 계정 변환본과 교차 발행은 소유자의 한 원본을 참조한다. 대상마다 원본을 복제하면 revision/hash/검토 귀속과 배포 연결이 깨진다(`ContentStore.create/update/_save`, `Ledger`의 snapshot 참조).
- 학과 프로젝트와 개인 네이버·기술사 제작·claude-jobs는 물리 분리되어 있지만, **개인 YouTube/GeoAI 코드 및 일부 개인 상태·토큰 경로는 dept 폴더 안**이다. 디렉터리 이름으로만 계정 소유권을 판정하면 틀린다.
- 공용 operations.sqlite3는 계정 폴더로 쪼개는 대상으로 잡지 않는다. 교차 배포의 owner/destination 관계, FK, CAS, 승인·시도·복구·quota 트랜잭션을 공유한다. 논리 계정 분리와 물리 DB 분리는 다른 변경이다.
- 공용 기능·폰트·Remotion 구성·잠금/STOP·등록부·운영 이력 조회 코드는 common에 유지한다. 공용 코드가 계정 토큰·출력 경로를 암묵 선택하지 않도록 인자로 분리한다. 비밀값 저장소·기존 .venv·로그인 폴더는 T13의 이동 제외 대상이다.
- 관찰한 호환 링크: 루트 `GeoAI_NA→personal`, `shared→common/shared`, `analytics→common/analytics`, `assets→common/assets`, `remotion-shorts→common/remotion-shorts`, `tools→common/tools`; `channels/*→../dept/*`.
- 특히 `personal/youtube-shorts-auto→../channels/youtube-shorts-auto→dept/youtube-shorts-auto`다. `personal/shared`, `personal/remotion-shorts`도 공용 링크다. `engineer-video-output→GeoAI_NA/engineer-video-output`는 링크 문자열만 관찰했으며 목적지 존재 보장은 하지 않는다. alias manifest는 이름·link target·canonical path·존재 여부를 별도 필드로 저장해야 한다.

## 3. 구체적인 fallback·상대경로 위험 consumer

1. **개인 fallback:** `ax-console/app/publishers.py:67` `blogger`는 `account=='dept'` 외 모두 개인 `geoai_blogger`로 진입한다. `main:135`도 계정 enum을 먼저 검사하지 않는다. 정상 콘솔 `AUTO_PUBLISH` 조회는 잘못된 키를 막지만 이 스크립트를 직접 부르거나 새 adapter에서 재사용하면 잘못된 계정이 개인 경로로 갈 수 있다. 신규 resolver/adapter는 계정 누락·unknown·빈 문자열을 거부해야 한다.
2. **개인 채널 추정:** `server.py:616`의 Codex 작업 관측은 채널 검출 실패 시 개인 Tistory를 넣고 계정도 개인으로 표시한다. `server.py:1222`는 학과 외 계정에 개인 history 채널 묶음을 선택한다. 이는 legacy 관측/기획 경로이며 관리 승인·계정 귀속의 근거로 승격하면 안 된다. 반면 `read_model._account`는 unknown을 None으로 남기고 관리 `ContentStore.create`는 unknown을 거부하므로 신규 계층에 동일 fallback이 있다고 일반화하지 않는다.
3. **cwd 기반 모듈 선택:** `publishers.py:20`의 `sys.path.insert(0, os.getcwd())`와 `from common import load_config`, `import geoai_blogger/post_blogger`는 호출자의 cwd에 묶여 있다. `server.publish_call`이 cwd를 설정해 현재 동작을 성립시킨다. 코드만 개인 폴더로 옮기면 같은 모듈명 common, config, 개인/학과 설정·토큰 선택이 달라진다.
4. **sibling 경로:** `dept/naver-blog-auto/geoai_daily.py:39`는 BASE_DIR의 sibling `youtube-shorts-auto`, `:243`은 sibling `insta-cardnews`를 계산한다. 개인 블로그만 이동하면 이 경로는 personal 아래를 가리켜 실제 공용/학과 모듈을 잃는다. `geoai_assets.py:18`의 `POSTS_DIR`도 현재 학과 common에 묶여 있다.
5. **alias/abspath 차이:** 세 프로젝트 `common.py`의 `abspath(__file__)`는 `resolve`와 달리 alias를 보존할 수 있다. 이동·import 경로별 BASE_DIR이 달라질 수 있다. `common/shared/paths.py`는 `resolve().parent.parent.parent`로 현 루트에 도달하지만 폴더 깊이를 변경하면 함께 갱신해야 한다. analytics는 `common.py:14`에서 부모 한 단계만 ROOT_DIR로 삼아 `common`에 도달할 수 있고, `collect_youtube.py:26`은 그 아래 `channels/.../token.json`을 붙인다. 실행 방식/alias에 따른 차이를 fixture로 확인해야 하며 이번 조사에서 실제 토큰 해석은 실행하지 않았다.
6. **wrapper·환경 경로:** `run_geoai.sh:3` 잠금 진입점은 `/Volumes/USB256/devAPP/AutoSNS/shared/axlock.py` 절대경로다. 이후 `../../shared/diskguard.py`와 `.venv`는 상대경로다. 폴더 이동 전 wrapper/launchd/지시문/console/자동화 caller 전부를 manifest에 넣어야 한다. 잠금 줄 제거로 해결하지 않는다.
7. **링크로 이행을 숨길 수 없음:** `read_model._Reader.allowed:128`은 심볼릭 링크를 읽지 않는다. `ContentStore._path:81`과 database `_path:16`도 저장 경로의 링크를 제한한다. 새 관리 저장소를 legacy 경로에 링크하는 방식은 지원되지 않는다. 또한 `read_model._Reader.key:187`의 상대경로가 `_id` 입력이므로 경로 변경 후 조회 ID가 달라질 수 있다. import 키에 기존 원본 ID/원래 경로를 보존해야 한다.

## 4. 원본 변경 전 가능한 구현과 검증

현재 T13의 `layout.py`, `legacy_import.py`, `environment_manifest.py`, `audit_account_paths.py`는 없다. 다음은 **구현 제안이며 이번 조사에서 생성·연결하지 않았다.**

### 4.1 순수 path registry / layout

`common/operations/layout.py`에 T13 계약 `resolve_layout(account_id,root)`와 `build_path_migration(baseline)`, `can_remove_alias(alias,callers)`를 구현할 수 있다. `root`는 명시된 절대경로, account는 dept/personal만 허용하고 기본값을 두지 않는다. 반환은 config_root/content_root/media_root/history_root와 schema/version을 갖는다. 현재 위치와 제안 목적지를 별개로 보존하고 경로 계산만 하며 mkdir·import·실행·자동 fallback을 하지 않는다.

처음에는 기존 consumer를 바꾸지 않고 fixture에서만 소비한다. R(source)/W(managed)/code_root/environment_root를 구별하고 겹침·탈출·링크 정책을 명시한다. 관리 ContentStore의 현재 불변 구조를 변경하지 않는다. 개인 `blog-auto`·`shorts-auto`는 승인 계획의 목적지이고 **현재 존재하는 실제 저장소라고 표시하지 않는다.**

### 4.2 import manifest와 순수 계획

T13 `build_import_plan(snapshot,registry)`를 먼저 만든다. 행별 source namespace, original/source-relative/canonical path, legacy ID, owner, destination, channel, remote ID/URL, 해시, alias, caller, 환경 참조, 원래 상태, 관측 시각, 불확실성, 제안 목적지를 기록한다. 게시 이력은 immutable observation으로 유지한다. 계정 없는 자료는 quarantine/unassigned로 두며 계정 추측으로 개인에 편입하지 않는다.

현재 웹 snapshot은 파일/행 수 제한·로그 tail·정제·손상 제외가 있다(`read_model._Reader.files/rows/jsonl`). 화면용 snapshot만 완전한 이행 원본이라고 간주하면 안 된다. 원본 경로별 인벤토리와 누락/중복/손상/미지원 카운트를 별도 보존한다. 파일을 지우거나 이동해 경로가 바뀌어도 legacy 식별자를 재발급하지 않는 정책이 필요하다.

실제 `import_snapshot(store,plan)`은 이후 임시 fixture 저장소에서만 검증한다. `ContentStore.create`는 UUID를 새로 만들기 때문에 그대로 두 번 호출하는 구현은 멱등하지 않다. legacy source key↔managed ID/row 해시 매핑과 unique 제약/트랜잭션 설계가 필요하다. done은 legacy_recorded, running은 복구 대기로 취급하고 verified나 승인·재시도 권한을 합성하지 않는다. 기존 조회의 reported_published 상태와 import용 legacy_recorded는 구분한다.

### 4.3 읽기 전용 inventory / environment manifest

`common/tools/audit_account_paths.py`는 명시 root 아래 allowlist만 lstat/readlink 및 허용 코드 정적 검색한다. symlink를 따라 재귀 탐색하거나 common.py·collector·publisher를 import하지 않는다(import mkdir/네트워크 가능). 비밀값·토큰·쿠키·프로필의 내용은 읽지 않고 필요하면 경로 유형만 기록한다. source에는 쓰지 않고 stdout 또는 별도 지정 출력에만 쓴다. 전체 운영 루트 조사는 이번 작업 권한과 별개인 후속 체크포인트다.

`environment_manifest.py`는 기존 interpreter 경로, requirements/lock 경로, 코드 진입점, cwd, 환경변수 **이름**, profile/credential **기호 참조**, caller 목록을 기록한다. .venv 재생성·패키지 설치·키 검사·프로필 기동은 하지 않는다. 운영 환경 변수의 값/자격증명을 manifest에 복제하지 않는다.

### 4.4 이행 전 통과시킬 검증

- 필수 T13 테스트 네 개: import 2회 ID/건수 불변, done이 verified가 아님, 개인 경로에 dept 기본값 없음, caller 하나라도 남으면 alias 제거 거부. cwd 두 곳에서 동일한 절대경로 계산을 확인한다.
- 누락/빈/unknown 계정과 cwd 교체에 대해 개인 fallback·학과 config import·프로필·비밀 조회·subprocess가 모두 0임을 fixture로 검증한다.
- 관리 revision/file_path/asset hash·owner/destination·FK 연결·CAS·승인 귀속이 보존되는지 확인한다. 원본 파일과 manifest 검토 시점 사이 변경은 해시 불일치로 계획을 무효화한다.
- alias 중첩·dangling·외부탈출·순환, traversal/절대경로 주입, root 겹침을 거부하거나 명시 관측 상태로 보고한다. 링크 제거는 caller 0과 실제 관찰 증거 둘 다 갖춘 후다.
- inventory 전후 source의 파일 집합/mtime/해시와 mkdir·쓰기·네트워크·프로필 호출 0을 작은 fixture로 확인한다. 실제 운영 데이터의 전체 해시 검사는 별도 읽기 허용·민감 파일 제외 정책 하에서 한다.
- 코드 이동 시 interpreter/cwd/wrapper/launchd/지시문/자동화 등록/상태 파일 caller를 한 묶음으로 검증한다. 토큰·로그인 폴더·기존 .venv 이동 수 0을 고정한다. 복구는 manifest 역매핑과 기존 스케줄 실행 주인 유지로 준비한다.

T13은 전체 계획상 T10~T12 이후다. 현재 가능한 것은 위의 순수 경로/계획/fixture 검증 준비이며, 이것으로 T13 전체 완료나 legacy 실제 전환 완료를 표시하면 안 된다. 실행 규칙 단일화와 adapter/제작 계약이 정해진 다음 상태 귀속→공용 추출→코드 이동→신규 산출물 경로→과거 데이터 순서를 따른다(`docs/superpowers/plans/2026-10-30-account-channel-automation.md:230`).
