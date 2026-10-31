# 남은 채널 실제 진입점 조사 (6B 준비, 구현 수락 아님)

2026-10-31. 정적 파일 검색·필요 함수 읽기만 수행했다. import/실행/브라우저/네트워크/설정·서버 변경은 하지 않았다. 비밀값·토큰값·로그·개인 콘텐츠 원문은 읽거나 출력하지 않았다. provider 요금 조사는 반복하지 않았다.

## 현재 관리 등록과 판정

`common/publishers/__init__.py:2-16`의 `build_adapters(*, registry=None, bridge=None)`는 BLOG_BINDINGS와 YOUTUBE_BINDINGS만 조립한다. 아래 Instagram/Threads/X/TikTok 함수는 **존재하는 legacy 구현**이며 managed adapter/ExecutorSpec/permit handler로 등록된 구현이라고 볼 수 없다. Facebook은 `dept`, `personal`의 Python 파일 전수 파일명·본문 검색에서 발행 함수가 없었다. `graph.facebook.com`은 Instagram Graph 발행 코드뿐이다(`dept/insta-manual/graph_api.py:25,121`). 따라서 현재 저장소 범위 Facebook 발행은 unsupported이며, 외부 계정 연결·권한 존재 여부는 미확인이다.

|채널·계정 범위|실제 함수·입출력|대상 고정·인증 참조 종류|독립 prepare|숨은 외부/로컬 부수효과·연결 판단|
|---|---|---|---|---|
|Instagram 학과 carousel|`dept/insta-cardnews/post_instagram.py:224` `post_carousel(data, dry_run=None)`; data.images, 캡션용 data → status(dry_run/published/shared_unconfirmed), images; 예외 발생 가능|함수 내 load_config, `common.py:6-9` 고정 PROFILE_DIR, 브라우저 로그인 쿠키. username은 캡션 검증 등에 쓰며 로그인 계정 증명이 아님|`_build_caption(data,cfg)` :623은 분리되어 있으나 managed_prepare 없음|dry도 브라우저·업로드·클립보드·스크린샷. 공유 버튼 :313 이후, 결과 :332-334, finally quit :340. 통째 호출은 submit 이전 준비를 분리하지 못함|
|Instagram 학과 reel|같은 파일 :796 `post_reel(data,dry_run=None)`; data.reel 및 캡션 data → status(dry_run/published/shared_unconfirmed), 원격 ID 없음|동일 프로필·설정. cfg 인자 주입 불가|캡션 helper만 분리|:937 게시 후 캡션 수정, :940-942 선택 첫 댓글까지 추가 mutation. :692 AI 라벨 조작, :762 표지 조작. post_reel 전체를 단일 'publish' 허가로 감싸면 댓글·편집도 허가 범위에 들어가므로 분해 필요|
|Instagram 수동 도구 carousel|`dept/insta-manual/instagram.py:290` `post_carousel(images,caption,*,dry_run=True,headless=False,first_comment_text="",username="",ai_label=False,supervised=True)` → status, images, 선택 first_comment|`core.py:13` 고정 PROFILE_DIR; 브라우저 쿠키. username 인자로 로그인 대상이 전환되지 않음|`build_caption(caption,hashtags,cta="",first_comment=False)` :263은 본문/댓글 tuple; 브라우저 없는 문자열 준비|:400-402 선택 첫 댓글. dry도 업로드·클립보드·스크린샷. :296 감독 모드 보안확인 대기. 계정 범위는 프로필 대상 검증 없이 personal로 재사용 불가|
|Instagram Graph carousel 대안|`dept/insta-manual/graph_api.py:121` `publish_carousel(image_urls,caption,ig_user_id,token,version=DEFAULT_VERSION,dry_run=True)` → dry_run/images/container_id 또는 published/images/media_id|명시 IG user ID + access token 인자. cfg/프로필 의존 없이 대상 바인딩 가능. `verify(ig_user_id,token,version=...)` :83은 계정 GET|`prepare_jpeg(src_path,dst_path,max_edge=1440,quality=88)` :60은 로컬 변환. 공개 HTTPS image URL 공급은 별도 필요|**dry_run도 :139 이후 원격 container POST 생성**. :161 media_publish가 최종 mutation. `post_comment(media_id,text,token,version=...)` :169은 별도 함수라 분리 가능. container 생성/최종 발행 경계를 permit와 일치시키는 추가 구현 필요|
|Threads 학과(개인 콘텐츠 crosspost도 대상은 학과)|`dept/insta-cardnews/post_threads.py:89` `post(text=None,data=None,dry_run=None,image=None)` → status empty/no_box/no_button/dry_run/published, text. image 인자는 본문에서 사용 안 함|내부 load_config, threads.enabled false면 dry로 강등. Instagram build_driver를 import하여 같은 고정 학과 프로필 사용|`_compose(data,cfg=None)` :29와 `dept/youtube-shorts-auto/threads_post.py:22` `compose(title,summary="",url="",tags=(),limit=500,notice="",channels=CHANNELS_LINE)` 분리|:128 버튼 클릭 후 4초 대기만으로 published **추정**; 원격 ID/lookup/verify 없음. dry도 작성창·클립보드 mutation. :136 driver.quit|
|Threads wrapper (leaf 아님)|`dept/youtube-shorts-auto/threads_post.py:48` `crosspost(text)` → 상태 **문자열**. `dept/insta-cardnews/threads_cli.py:14` `main()` stdin {text,data,dry} → stdout JSON|wrapper가 SMUDS_EDITION 환경 제거(:56), 학과 IG venv/CLI 고정; CLI가 post(...dry_run=payload.get('dry',False)) 호출|compose는 순수 문자열|subprocess/captured log 파싱 포함. permit bridge에 subprocess wrapper보다 실제 post 분해 경계가 적합|
|X 학과|`dept/youtube-shorts-auto/x_post.py:217` `post_video(text,video,dry_run=None,cfg=None)` → status dry_run/published/error, text 또는 id/url/error; `crosspost(data,video=None,summary=None)` :246 → disabled 또는 동일 결과|cfg.x OAuth2 사용자 토큰(`TOKEN_PATH` :82, token_store :104) 또는 OAuth1 키 네 개(`_session` :113). cfg.x.username은 URL 구성용이며 원격 principal 검증 아님|`compose(title,summary="",tags=(),cross=CROSS_LINE)` :67, `_fit` :48 분리|:85 token refresh/암호화 저장; :171 `_x_ready` 영상 변환; :137 chunk media upload; :232 tweet POST; :199 `_record` JSON 기록. 전체 post_video는 publish 이전 원격 media 업로드까지 포함. 별도 target inspection/lookup/verify 및 cfg provenance 필요|
|TikTok 학과 web (개인 source도 목적지는 학과)|`dept/youtube-shorts-auto/tiktok_web.py:385` `upload(video,caption,post=False,ai_generated=False,location="충북제천",popular_sound=False)` → dry_run/posted + shot; SystemExit 가능|:32 고정 PROFILE_DIR, :51 Chrome 실행/디버깅 포트 접속; 쿠키 인증. account ID 인자 없음|`build_caption(data,cfg)` :486은 캡션 helper. upload와 독립 managed_prepare 없음|dry도 영상 전송·위치·선택 음원·AI 라벨 쓰기. :419 실패 시 debug Chrome 종료. :451 게시 클릭, :456 확인, :460 `_mark(video)` 로컬 중복기록. :464 finally pass로 **브라우저를 닫지 않음**; managed lifecycle/axlock 요구와 함께 정리 필요|
|TikTok API 별도 경로|`dept/youtube-shorts-auto/tiktok_upload.py:92` `upload(data,dry_run=None,privacy=None)` → dry_run/video 또는 status(외부 상태),publish_id,privacy|내부 load_config cfg.tiktok client 자격 + `TIKTOK_TOKEN_PATH` token_store :38-47. cfg 기반 고정 토큰 주체|`_build_caption(data,cfg)` :79 분리. dry는 :112에서 원격 호출 전에 반환|:50-68 refresh+저장; :120 creator_info; :124-128 요청 공개범위를 자동 대체; :148 init POST, :159 PUT, :168 poll. PUBLISH_COMPLETE/FAILED/PROCESSING을 그대로 반환. web queue와 다른 경로로, 동시 retry owner 금지|

개인 폴더에는 위 채널 독립 발행 leaf를 찾지 못했다. 개인 source → 학과 TikTok/Threads 규칙을 개인 대상 adapter가 있다는 뜻으로 해석하면 안 된다. 개인 Instagram/Threads/X/TikTok의 실제 계정 인증·발행 구현 재사용 가능성은 미확인이다.

## 23 crossposts·owner 보존과 연결 위치

원본은 `ax-console/config/crossposts.json`이며 23개 rule ID의 trigger/conditions/allowed_slots/enabled(특히 null)/delivery_owner/delay_owner/계정 범위를 유지해야 한다. 목적지 다섯 채널 관련 근거:

- 개인 source→학과 TikTok: `geoai-short.tiktok` :5, `youtube-generic-personal.tiktok` :119. 학과 generic TikTok :220. 개인→학과 Threads `geoai.threads` :321. source owner와 destination account는 다르다. geoai.threads 조건 :350은 (Blogger published 또는 dry_run) AND (no_video 또는 threads override).
- 뉴스 Instagram :715 조건 :737은 weekly_news + youtube_success + made_anchor, Threads :759/:781과 X :804/:826은 weekly_news + youtube_success. `news.tiktok` :843은 API 경로로 queue 지연을 무조건 붙일 수 없다.
- 진로 TikTok :892, Instagram :981, Threads :1030, X :1079. Instagram은 no_ig=false(:1008), Threads는 no_threads=false(:1057), 다른 조건과 caller/published phase도 함께 보존한다.
- 재난 TikTok :1123, Instagram :1227, Threads :1392. Instagram :1260은 caller disaster + 이전상태가 published/shared_unconfirmed가 아닌 경우. `dept/disaster-shorts/tools/crosspost.py:106` ensure_public 및 :129 run은 다른 블로그 발행과 YouTube 공개전환까지 포함하므로 submit leaf로 재사용하면 안 된다.

순수 판정 위치는 `common/operations/crossposts.py:16` earliest_post_time, :49 _matches, :69 preview_crossposts, :92 crosspost_intents다. 기존 legacy 소유는 observe_legacy이며 planned는 enabled=True AND delivery_owner=managed일 때만 가능(:82-85). 시각/조건 preview는 실발행이 아니며 execution_enabled=False 반환이다.

실행 owner는 `common/operations/entrypoints.py:8` resolve_entrypoint 및 :74 route_legacy_action이 검증한다. :117-119 모든 caller inventory 완료 전 관리 전환을 막는다. `common/operations/legacy_fences.py:23` _row 기본 managed_eligible=False/inventory_complete=False, :38-45 Instagram/TikTok/X 콘솔 action, :67-70 TikTok/re난 launchd wrapper도 미분해 상태다. owner만 managed로 바꾸는 것은 leaf/caller 분해 수락이 아니다.

permit bridge 재사용 경계는 `common/publishers/bridge_host.py:41` execute의 등록 executor/action → :64 prepared/context binding → :92 redeem_bridge → handler 호출이다. 새 adapter에는 별도 immutable prepare, 원격 계정 inspection, submit mutation, lookup/verify가 필요하다. 현 leaf의 게시 추정 반환을 verify 성공으로 매핑할 근거는 없다. `common/operations/admission_context.py:46-62`의 managed job·계정·connection·교차허용 검증도 유지해야 한다.

## TikTok retry 통합 지점

`dept/youtube-shorts-auto/tiktok_queue.py:69` add의 정확한 signature는 `add(video,title,description="",hashtags=(),ai_generated=False,not_before=None,source="",backfill=False,notice="",ai_voice=False)`이며 bool 반환이다. :87-88에서 **입력 not_before에 30분을 더한다**. managed 시각계산 결과를 그대로 add에 넣으면 이중 지연된다. 규칙의 delay_owner=legacy_queue_add와 managed/source 구분이 필수다.

`pick(q,now=None)` :145는 07–23시, 3시간 간격, 14일 나이 제한, tries<5, skipped/posted 제외, not_before/hold_until, 파일 존재, new-before-backfill/priority 순서를 검사한다. :174 main은 캡션 생성·캐시·발행·retry bookkeeping까지 묶는다. :111 make_caption은 LLM 외부호출을 포함하므로 순수 prepare가 아니다. :191-196 캡션을 큐에 캐시하고 :199 upload(...post=True)를 부른다. :202-223은 인프라 오류 tries 제외, 다른 오류 tries 증가, 동일화면 오류 2회시 다음 자정 hold; :227-230 posted 기록이다. 이 경계의 데이터·의미를 관리 attempt/recovery와 연결해야 하며 main 전체를 permit handler로 감싸거나 독립 API/web retry를 동시에 돌릴 수 없다.

현 web leaf는 게시 후 목록 확인 실패를 SystemExit로 내보낸다(:458). 실제 게시 여부가 불명확한 실패를 신규 재시도로 직결하지 말고 managed unknown/lookup 경계로 분리할 필요가 있다. 이는 이번 조사에서 구현/시험한 사항이 아니다.

## 제한

함수 존재·정적 코드 경계만 확인했다. 실제 토큰 권한·연결 주체·세션 상태·외부 API/DOM 유효성·발행 성공은 확인하지 않았다. managed adapter를 추가하지 않았고 6B 설계/구현 완료를 주장하지 않는다. 다른 agent 파일·메뉴·Task8 통합 소유 파일은 변경하지 않았다.
