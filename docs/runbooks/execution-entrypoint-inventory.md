# 실행 진입점과 실행 주인 검사 등록표

2026-10-31. 작업 사본만 변경. 운영 owner/enabled/plist 변경 0. 실제 wrapper·CLI·legacy import·API·프로필 실행 없이 소스와 fixture로 검증했다.

기계 판독본: [execution-entrypoint-inventory.json](execution-entrypoint-inventory.json). A10은 `jobs[job_id].managed_eligible` 및 `inventory_complete`와 `pending_paths`를 함께 확인한다. unknown 또는 bypass caller 하나라도 남으면 관리 전환 판정은 false다. 이 표의 모든 기존 경로는 현재 `managed_eligible=false`·`inventory_complete=false`다. owner fence가 있는 것과 전체 외부 쓰기의 관리 관문 수락은 다르다.

- entrypoint JSON SHA-256: `f88f93a6701037a94d469b8d7102f1e25bef59b9c4f0e1f08178f2c7f5be7885`
- operations.json 기준선 SHA-256: `bca5e9cd15fd3987d6dbf9f433a049578c0fae7a2af0d3c94da98c5de87a83cf`
- crossposts.json 기준선 SHA-256: `9abca6063ec91aba0044714a18e143fa6fa131ddbda3854d6b32a6c739d0c7c1`

## 경계와 권한

콘솔의 action key는 `(account, channel, action)`이다. `ACTION_ROUTES`가 job/caller/source를 서버에서 확정한다. 기존 memo/test는 명시된 계정·채널에서만 무발행 legacy 경로다. 미등록 새 action은 거부한다. 기존 콘텐츠 직접 발행에 없던 job은 `console.<account>.<channel>`이라는 관측 ID로만 보존한다. 이 네 ID를 실제 등록부에 추가하면 owner를 다시 검사하며, 임의 미등록 job에는 이 예외를 쓰지 않는다.

`route_legacy_action`은 legacy면 무실행 결과를 반환하고, managed면 등록 caller/executor/source·완전한 inventory·단일 부수효과를 확인한 뒤 주입된 서버 submit 또는 A1 submit_registered를 사용한다. 접수 결과는 queued/run_id이며 legacy 완료 기록을 만들지 않는다. 일정이 있는 자동 재호출은 같은 UTC 회차를 사용한다. 서버 내부 configure_legacy_services 외에 HTTP body/환경값으로 서비스를 바꾸는 경로는 없다.

wrapper는 기존 첫 axlock 재진입 줄을 그대로 두고 바로 다음에 작업 사본 상대 경로를 물리적으로 해석한 owner fence를 실행한다. 추가 fence는 원본 R 경로를 실행하지 않는다. managed_eligible=false인 다중 작업은 managed owner가 발견되면 본문 전체를 차단한다. legacy 본문의 AX_HOUR·모델·회차·precheck·인자 검사는 유지한다.

공개 CLI와 관리 leaf는 서로 다른 권한 경계다. CLI는 고정 경로의 `python -I .../legacy_fences.py` 조회를 거쳐 legacy owner에서만 실행한다. 이 격리는 프로젝트 common.py와 관리 common namespace 충돌을 피하며 키/프로필을 import하지 않는다. 관리 leaf는 A6/A7의 등록 executor·일회성 permit 경로로만 실행되어야 한다. CLI가 반환하는 AX_LOCKED나 legacy 결과를 permit으로 인정하지 않는다. 현재 관리 CLI 전송 서비스는 설치하지 않았으며 관리 owner의 미분해 CLI는 차단된다.

## 감사의 모든 진입점 행

| 감사 행 | 파일/내부 호출 | job | 현재 상태·전환 blocker |
|---|---|---|---|
| 기존 콘솔 일반 작업 | `ax-console/app/server.py:run_task` | `ytshorts.weekly`, `ytcareer.weekly`, `captionbackfill.daily`, `instacards.weekly`, `captionautofix.daily`, `naverblog.weekly`, `blogcareer.daily`, `naverjobs.weekly`, `tiktok.queue`, `xpromo.daily`, `geoai.daily`, `geoai.evening`, `tistory` | `owner_fenced_legacy`; eligible=false |
| 기존 콘솔 예약 생성 | `ax-console/app/server.py:content_approve` | `console.dept.blogger`, `console.dept.naver_blog`, `console.dept.x`, `console.personal.blogger` | `owner_fenced_legacy`; eligible=false |
| 기존 콘솔 자동 발행 | `ax-console/app/server.py:run_publish`<br>`ax-console/app/server.py:publish_call` | `console.dept.blogger`, `console.dept.naver_blog`, `console.dept.x`, `console.personal.blogger` | `owner_fenced_legacy`; eligible=false |
| 콘솔 Blogger | `ax-console/app/publishers.py:blogger`<br>`dept/naver-blog-auto/post_blogger.py`<br>`personal/naver-blog-auto/geoai_blogger.py` | `console.dept.blogger`, `console.personal.blogger` | `bypass_pending_leaf_A6`; eligible=false |
| 콘솔 네이버·X | `ax-console/app/publishers.py:naver`<br>`ax-console/app/publishers.py:x`<br>`dept/naver-blog-auto/publish_naver.py`<br>`dept/youtube-shorts-auto/x_post.py` | `console.dept.naver_blog`, `console.dept.x` | `bypass_pending_leaf_A6`; eligible=false |
| 개인 Claude 작업 | `personal/claude-jobs/run_claude_job.sh` | `claude.survey-daily`, `claude.survey-shorts`, `claude.civil-daily`, `claude.survey-friend`, `claude.civil-friend`, `claude.building-daily`, `claude.building-friend`, `claude.safety-daily`, `claude.safety-friend`, `claude.safekorea`, `claude.nordic` | `owner_fenced_autonomous_body_pending`; eligible=false |
| GeoAI 아침/저녁 | `dept/naver-blog-auto/run_geoai.sh`<br>`dept/naver-blog-auto/run_geoai_evening.sh`<br>`dept/naver-blog-auto/geoai_daily.py` | `geoai.daily`, `geoai.evening` | `multi_effect_pending`; eligible=false |
| 학과 채용 블로그 | `dept/naver-blog-auto/run_jobs.sh`<br>`dept/naver-blog-auto/jobs_work24.py`<br>`dept/insta-cardnews/jobs_insta.py`<br>`dept/naver-blog-auto/tistory_jobs.py` | `naverjobs.weekly` | `multi_account_effect_pending`; eligible=false |
| TikTok 큐 실행 | `dept/youtube-shorts-auto/run_tiktok_queue.sh`<br>`dept/youtube-shorts-auto/tiktok_queue.py:main` | `tiktok.queue` | `direct_queue_bypass_pending`; eligible=false |
| 개인 숏츠 | `dept/youtube-shorts-auto/geoai_short_post.py:main`<br>`dept/youtube-shorts-auto/geoai_short_post.py:cmd_upload`<br>`dept/youtube-shorts-auto/geoai_short_post.py:cmd_comment`<br>`dept/youtube-shorts-auto/geoai_short_post.py:cmd_delete` | `claude.survey-shorts`, `claude.survey-daily`, `geoai.daily`, `geoai.evening` | `internal_function_bypass_pending_A7`; eligible=false |
| 일반 YouTube 업로드 | `dept/youtube-shorts-auto/youtube_upload.py:upload`<br>`dept/youtube-shorts-auto/youtube_upload.py:post_top_comment`<br>`dept/youtube-shorts-auto/youtube_upload.py:add_to_playlist` | `ytshorts.weekly`, `ytshorts.trigger`, `geoai.daily`, `geoai.evening` | `internal_function_bypass_pending_A7`; eligible=false |
| 재난 숏츠 업로드 | `dept/disaster-shorts/tools/publish.py:upload` | `disastershorts.weekly` | `upload_schedule_private_fallback_queue_pending_A7`; eligible=false |
| 재난 교차 게시 | `dept/disaster-shorts/tools/run_crosspost.sh`<br>`dept/disaster-shorts/tools/crosspost.py:run`<br>`dept/disaster-shorts/tools/crosspost.py:ensure_public` | `disastershorts.crosspost` | `visibility_four_targets_pending_A7`; eligible=false |
| 학과 채용 영상 | `dept/youtube-shorts-auto/publish_career.py:_upload`<br>`dept/youtube-shorts-auto/publish_career.py:main` | `ytcareer.weekly` | `internal_multitarget_bypass_pending_A7`; eligible=false |
| 학과 주간 뉴스 영상 | `dept/youtube-shorts-auto/run_weekly.py` | `ytshorts.weekly` | `internal_multitarget_bypass_pending_A7`; eligible=false |
| 개인 Tistory→네이버 | `personal/naver-blog-auto/tistory_crosspost.py:main` | `tistory` | `direct_crosspost_bypass_pending_A6`; eligible=false |

## 등록 action → job/caller 전체

별칭 `channels/*`는 해당 `dept/*` 경로로 연결된다. 아래 각 행은 현재 legacy로 보존되며 관리 전환 허용을 뜻하지 않는다.

| account/channel/action | caller ID | job ID | 파일·이유 |
|---|---|---|---|
| `dept/youtube/shorts_weekly` | `legacy.console.dept.youtube.shorts_weekly` | `ytshorts.weekly` | `ax-console/app/server.py → dept/youtube-shorts-auto/run.sh`<br>leaf/caller별 관문 연결 수락 전 |
| `dept/youtube/career_publish` | `legacy.console.dept.youtube.career_publish` | `ytcareer.weekly` | `ax-console/app/server.py → dept/youtube-shorts-auto/run_career_publish.sh`<br>leaf/caller별 관문 연결 수락 전 |
| `dept/youtube/caption_backfill` | `legacy.console.dept.youtube.caption_backfill` | `captionbackfill.daily` | `ax-console/app/server.py → dept/youtube-shorts-auto/run_caption_backfill.sh`<br>leaf/caller별 관문 연결 수락 전 |
| `dept/instagram/cards_weekly` | `legacy.console.dept.instagram.cards_weekly` | `instacards.weekly` | `ax-console/app/server.py → dept/insta-cardnews/run.sh`<br>leaf/caller별 관문 연결 수락 전 |
| `dept/instagram/caption_autofix` | `legacy.console.dept.instagram.caption_autofix` | `captionautofix.daily` | `ax-console/app/server.py → dept/insta-cardnews/run_caption_autofix.sh`<br>leaf/caller별 관문 연결 수락 전 |
| `dept/naver_blog/naver_weekly` | `legacy.console.dept.naver_blog.naver_weekly` | `naverblog.weekly` | `ax-console/app/server.py → dept/naver-blog-auto/run.sh`<br>leaf/caller별 관문 연결 수락 전 |
| `dept/naver_blog/career_series` | `legacy.console.dept.naver_blog.career_series` | `blogcareer.daily` | `ax-console/app/server.py → dept/naver-blog-auto/run_career_series.sh`<br>leaf/caller별 관문 연결 수락 전 |
| `dept/naver_blog/naver_jobs` | `legacy.console.dept.naver_blog.naver_jobs` | `naverjobs.weekly` | `ax-console/app/server.py → dept/naver-blog-auto/run_jobs.sh`<br>leaf/caller별 관문 연결 수락 전 |
| `dept/tiktok/tiktok_queue` | `legacy.console.dept.tiktok.tiktok_queue` | `tiktok.queue` | `ax-console/app/server.py → dept/youtube-shorts-auto/run_tiktok_queue.sh`<br>leaf/caller별 관문 연결 수락 전 |
| `dept/x/x_promo` | `legacy.console.dept.x.x_promo` | `xpromo.daily` | `ax-console/app/server.py → dept/youtube-shorts-auto/run_x_promo.sh`<br>leaf/caller별 관문 연결 수락 전 |
| `personal/blogger/geoai_morning` | `legacy.console.personal.blogger.geoai_morning` | `geoai.daily` | `ax-console/app/server.py → dept/naver-blog-auto/run_geoai.sh`<br>leaf/caller별 관문 연결 수락 전 |
| `personal/blogger/geoai_evening` | `legacy.console.personal.blogger.geoai_evening` | `geoai.evening` | `ax-console/app/server.py → dept/naver-blog-auto/run_geoai_evening.sh`<br>leaf/caller별 관문 연결 수락 전 |
| `personal/tistory/tistory` | `legacy.console.personal.tistory.tistory` | `tistory` | `ax-console/app/server.py → personal/naver-blog-auto/run_tistory.sh`<br>leaf/caller별 관문 연결 수락 전 |
| `dept/blogger/publish` | `legacy.console.dept.blogger.publish` | `console.dept.blogger` | `ax-console/app/server.py:publish_call/run_publish`<br>leaf/caller별 관문 연결 수락 전 |
| `dept/blogger/publish-cli` | `legacy.console.dept.blogger.publish-cli` | `console.dept.blogger` | `ax-console/app/publishers.py:main`<br>leaf/caller별 관문 연결 수락 전 |
| `dept/naver_blog/publish` | `legacy.console.dept.naver_blog.publish` | `console.dept.naver_blog` | `ax-console/app/server.py:publish_call/run_publish`<br>leaf/caller별 관문 연결 수락 전 |
| `dept/naver_blog/publish-cli` | `legacy.console.dept.naver_blog.publish-cli` | `console.dept.naver_blog` | `ax-console/app/publishers.py:main`<br>leaf/caller별 관문 연결 수락 전 |
| `dept/x/publish` | `legacy.console.dept.x.publish` | `console.dept.x` | `ax-console/app/server.py:publish_call/run_publish`<br>leaf/caller별 관문 연결 수락 전 |
| `dept/x/publish-cli` | `legacy.console.dept.x.publish-cli` | `console.dept.x` | `ax-console/app/publishers.py:main`<br>leaf/caller별 관문 연결 수락 전 |
| `personal/blogger/publish` | `legacy.console.personal.blogger.publish` | `console.personal.blogger` | `ax-console/app/server.py:publish_call/run_publish`<br>leaf/caller별 관문 연결 수락 전 |
| `personal/blogger/publish-cli` | `legacy.console.personal.blogger.publish-cli` | `console.personal.blogger` | `ax-console/app/publishers.py:main`<br>leaf/caller별 관문 연결 수락 전 |
| `personal/claude/survey-daily` | `legacy.launchd.personal.claude.survey-daily` | `claude.survey-daily` | `personal/claude-jobs/run_claude_job.sh survey-daily`<br>AX_HOUR별 모델/회차와 자율 발행 도구 미분해 |
| `personal/claude/survey-shorts` | `legacy.launchd.personal.claude.survey-shorts` | `claude.survey-shorts` | `personal/claude-jobs/run_claude_job.sh survey-shorts`<br>AX_HOUR별 모델/회차와 자율 발행 도구 미분해 |
| `personal/claude/civil-daily` | `legacy.launchd.personal.claude.civil-daily` | `claude.civil-daily` | `personal/claude-jobs/run_claude_job.sh civil-daily`<br>AX_HOUR별 모델/회차와 자율 발행 도구 미분해 |
| `personal/claude/survey-friend` | `legacy.launchd.personal.claude.survey-friend` | `claude.survey-friend` | `personal/claude-jobs/run_claude_job.sh survey-friend`<br>AX_HOUR별 모델/회차와 자율 발행 도구 미분해 |
| `personal/claude/civil-friend` | `legacy.launchd.personal.claude.civil-friend` | `claude.civil-friend` | `personal/claude-jobs/run_claude_job.sh civil-friend`<br>AX_HOUR별 모델/회차와 자율 발행 도구 미분해 |
| `personal/claude/building-daily` | `legacy.launchd.personal.claude.building-daily` | `claude.building-daily` | `personal/claude-jobs/run_claude_job.sh building-daily`<br>AX_HOUR별 모델/회차와 자율 발행 도구 미분해 |
| `personal/claude/building-friend` | `legacy.launchd.personal.claude.building-friend` | `claude.building-friend` | `personal/claude-jobs/run_claude_job.sh building-friend`<br>AX_HOUR별 모델/회차와 자율 발행 도구 미분해 |
| `personal/claude/safety-daily` | `legacy.launchd.personal.claude.safety-daily` | `claude.safety-daily` | `personal/claude-jobs/run_claude_job.sh safety-daily`<br>AX_HOUR별 모델/회차와 자율 발행 도구 미분해 |
| `personal/claude/safety-friend` | `legacy.launchd.personal.claude.safety-friend` | `claude.safety-friend` | `personal/claude-jobs/run_claude_job.sh safety-friend`<br>AX_HOUR별 모델/회차와 자율 발행 도구 미분해 |
| `personal/claude/safekorea` | `legacy.launchd.personal.claude.safekorea` | `claude.safekorea` | `personal/claude-jobs/run_claude_job.sh safekorea`<br>AX_HOUR별 모델/회차와 자율 발행 도구 미분해 |
| `personal/claude/nordic` | `legacy.launchd.personal.claude.nordic` | `claude.nordic` | `personal/claude-jobs/run_claude_job.sh nordic`<br>AX_HOUR별 모델/회차와 자율 발행 도구 미분해 |
| `personal/blogger/geoai.daily` | `legacy.launchd.personal.blogger.geoai.daily` | `geoai.daily` | `dept/naver-blog-auto/run_geoai.sh`<br>다중 대상/큐 부수효과 미분해 |
| `personal/blogger/geoai.evening` | `legacy.launchd.personal.blogger.geoai.evening` | `geoai.evening` | `dept/naver-blog-auto/run_geoai_evening.sh`<br>다중 대상/큐 부수효과 미분해 |
| `dept/naver_blog/naverjobs.weekly` | `legacy.launchd.dept.naver_blog.naverjobs.weekly` | `naverjobs.weekly` | `dept/naver-blog-auto/run_jobs.sh`<br>다중 대상/큐 부수효과 미분해 |
| `dept/tiktok/tiktok.queue` | `legacy.launchd.dept.tiktok.tiktok.queue` | `tiktok.queue` | `dept/youtube-shorts-auto/run_tiktok_queue.sh`<br>다중 대상/큐 부수효과 미분해 |
| `dept/youtube/disastershorts.crosspost` | `legacy.launchd.dept.youtube.disastershorts.crosspost` | `disastershorts.crosspost` | `dept/disaster-shorts/tools/run_crosspost.sh`<br>다중 대상/큐 부수효과 미분해 |
| `dept/youtube/youtube-upload-cli` | `legacy.console.dept.youtube.youtube-upload-cli` | `ytshorts.weekly`, `ytshorts.trigger`, `ytcareer.weekly`, `disastershorts.weekly` | `dept/youtube-shorts-auto/youtube_upload.py (__main__)`<br>일반 업로드의 숨은 TikTok add와 내부 caller 분해 필요 |
| `personal/youtube/youtube-upload-cli` | `legacy.console.personal.youtube.youtube-upload-cli` | `geoai.daily`, `geoai.evening`, `claude.survey-daily`, `claude.survey-shorts`, `claude.civil-daily`, `claude.survey-friend`, `claude.civil-friend`, `claude.building-daily`, `claude.building-friend`, `claude.safety-daily`, `claude.safety-friend`, `claude.safekorea`, `claude.nordic` | `dept/youtube-shorts-auto/youtube_upload.py (__main__)`<br>일반 CLI edition으로 개인 업로드 가능; 개인 내부 caller 미분해 |
| `personal/youtube/geoai-short-upload` | `legacy.console.personal.youtube.geoai-short-upload` | `geoai.daily`, `geoai.evening`, `claude.survey-daily`, `claude.survey-shorts`, `claude.civil-daily`, `claude.survey-friend`, `claude.civil-friend`, `claude.building-daily`, `claude.building-friend`, `claude.safety-daily`, `claude.safety-friend`, `claude.safekorea`, `claude.nordic` | `dept/youtube-shorts-auto/geoai_short_post.py:main upload`<br>개인 업로드/댓글/삭제와 학과 큐 분해 필요 |
| `personal/youtube/geoai-short-comment` | `legacy.console.personal.youtube.geoai-short-comment` | `geoai.daily`, `geoai.evening`, `claude.survey-daily`, `claude.survey-shorts`, `claude.civil-daily`, `claude.survey-friend`, `claude.civil-friend`, `claude.building-daily`, `claude.building-friend`, `claude.safety-daily`, `claude.safety-friend`, `claude.safekorea`, `claude.nordic` | `dept/youtube-shorts-auto/geoai_short_post.py:main comment`<br>개인 업로드/댓글/삭제와 학과 큐 분해 필요 |
| `personal/youtube/geoai-short-delete` | `legacy.console.personal.youtube.geoai-short-delete` | `geoai.daily`, `geoai.evening`, `claude.survey-daily`, `claude.survey-shorts`, `claude.civil-daily`, `claude.survey-friend`, `claude.civil-friend`, `claude.building-daily`, `claude.building-friend`, `claude.safety-daily`, `claude.safety-friend`, `claude.safekorea`, `claude.nordic` | `dept/youtube-shorts-auto/geoai_short_post.py:main delete`<br>개인 업로드/댓글/삭제와 학과 큐 분해 필요 |
| `personal/youtube/geoai-short-check` | `legacy.console.personal.youtube.geoai-short-check` | `geoai.daily`, `geoai.evening`, `claude.survey-daily`, `claude.survey-shorts`, `claude.civil-daily`, `claude.survey-friend`, `claude.civil-friend`, `claude.building-daily`, `claude.building-friend`, `claude.safety-daily`, `claude.safety-friend`, `claude.safekorea`, `claude.nordic` | `dept/youtube-shorts-auto/geoai_short_post.py:main check`<br>개인 업로드/댓글/삭제와 학과 큐 분해 필요 |
| `personal/tistory/tistory-post-cli` | `legacy.console.personal.tistory.tistory-post-cli` | `tistory`, `claude.survey-daily`, `claude.survey-shorts`, `claude.civil-daily`, `claude.survey-friend`, `claude.civil-friend`, `claude.building-daily`, `claude.building-friend`, `claude.safety-daily`, `claude.safety-friend`, `claude.safekorea`, `claude.nordic` | `personal/naver-blog-auto/tistory_post.py (__main__/main)`<br>Tistory dry도 브라우저 쓰기 가능; 모든 Claude 내부 caller fence 필요 |

## 추가로 확인한 직접 CLI·내부 caller

| 호출자 | 귀속 job | 미분리 이유 |
|---|---|---|
| `dept/youtube-shorts-auto/check_trigger.py:upload` | `ytshorts.trigger` | upload内 TikTok add; eligible=false |
| `dept/youtube-shorts-auto/geoai_video.py:upload/post_top_comment` | `geoai.daily`, `geoai.evening` | 개인 업로드·댓글; eligible=false |
| `personal/naver-blog-auto/tistory_patch.py:tp.main` | `tistory` | main fence 있음; import와 편집 leaf는 A6 미분리; eligible=false |
| `personal/civil-engineer-writing/01일차_흙의다짐/숏츠/upload_short.py` | `claude.civil-daily` | 별도 직접 Google upload; 미이행 우회; eligible=false |
| `dept/youtube-shorts-auto/backfill_playlist_links.py` | `captionbackfill.daily` | playlist metadata mutation; eligible=false |
| `dept/youtube-shorts-auto/backfill_comments.py` | `captionbackfill.daily` | 댓글 mutation; eligible=false |
| `dept/youtube-shorts-auto/backfill_captions.py` | `captionbackfill.daily` | caption mutation; eligible=false |
| `dept/youtube-shorts-auto/make_captions.py` | `ytshorts.weekly`, `ytcareer.weekly` | caption insert; eligible=false |
| `dept/naver-blog-auto/naver_crosspost_personal.py` | `naverblog.weekly` | naver→blogger; eligible=false |
| `dept/naver-blog-auto/blogger_crosspost_personal.py` | `geoai.daily`, `geoai.evening` | blogger→tistory; eligible=false |
| `dept/youtube-shorts-auto/tiktok_queue.py:add/upload/main` | `tiktok.queue`, `ytshorts.weekly`, `ytshorts.trigger`, `ytcareer.weekly`, `geoai.daily`, `disastershorts.weekly` | queue add와 submit 직접 호출; eligible=false |
| `personal/naver-blog-auto/tistory_post.py:publish/edit_body` | `tistory`, `claude.survey-daily`, `claude.survey-shorts`, `claude.civil-daily`, `claude.survey-friend`, `claude.civil-friend`, `claude.building-daily`, `claude.building-friend`, `claude.safety-daily`, `claude.safety-friend`, `claude.safekorea`, `claude.nordic` | public main은 fence; 직접 내부 함수와 자율 도구 미분리; eligible=false |

인증 보조 `geoai_youtube_auth.py`/`youtube_login_setup.py`는 SCOPES만 import하는 caller다. credential 생성은 이 작업에서 실행·이행하지 않았다. `backfill_*`, `make_captions.py`, 별도 수동 upload_short.py처럼 실제 mutation이 남은 caller를 pure read로 분류하지 않는다.

## 교차23경로와 원본 job 연결

각 rule의 전체 조건·변환·태그·원본/대상·AI 고지·상태는 기존 crossposts.json의 canonical rule_sha256와 전체 파일 기준선으로 비교한다. enabled 누락은 unknown(null)으로 보존한다. news.tiktok=false를 포함해 true 보정은 없다.

| rule ID | 실행 caller 귀속 job | delivery owner | enabled |
|---|---|---|---|
| `geoai-short.tiktok` | `claude.survey-shorts`, `claude.survey-daily` | legacy | true |
| `youtube-generic-personal.tiktok` | `geoai.daily`, `geoai.evening` | legacy | true |
| `youtube-generic-dept.tiktok` | `ytshorts.weekly`, `ytshorts.trigger` | legacy | true |
| `geoai.threads` | `geoai.daily`, `geoai.evening` | legacy | none |
| `jobs.tistory` | `naverjobs.weekly` | legacy | none |
| `tistory.safeworking` | `tistory` | legacy | none |
| `naver.blogger` | `naverblog.weekly` | legacy | none |
| `blogger.tistory` | `geoai.daily`, `geoai.evening` | legacy | none |
| `geoai.community` | `geoai.daily`, `geoai.evening` | legacy | none |
| `news.naver_blog` | `ytshorts.weekly` | legacy | none |
| `news.instagram` | `ytshorts.weekly` | legacy | none |
| `news.threads` | `ytshorts.weekly` | legacy | none |
| `news.x` | `ytshorts.weekly` | legacy | none |
| `news.tiktok` | `ytshorts.weekly` | legacy | false |
| `career.tiktok` | `ytcareer.weekly` | legacy | true |
| `career.instagram` | `ytcareer.weekly` | legacy | none |
| `career.threads` | `ytcareer.weekly` | legacy | none |
| `career.x` | `ytcareer.weekly` | legacy | none |
| `disaster.tiktok` | `disastershorts.weekly` | legacy | true |
| `disaster.instagram` | `disastershorts.crosspost` | legacy | none |
| `disaster.blogger` | `disastershorts.crosspost` | legacy | none |
| `disaster.naver_blog` | `disastershorts.crosspost` | legacy | none |
| `disaster.threads` | `disastershorts.crosspost` | legacy | none |

원본 제작 소유와 목적지 계정은 rule에 각각 남아 있으며, 개인 원본→학과 TikTok/Threads를 개인 발행 하나로 합치지 않는다. queue add 지연/간격/시간대/시도/hold와 재난 예약·비공개 fallback·공개 전환·후속 대상은 아직 legacy 의미를 보존한다. 대상별 분해·재시작/조회 fixture 수락이 끝나기 전 위 job은 모두 관리 전환 불가다.

## 남은 한계

실제 불변 대상·인증·공개·제작비 증거는 없다. fixture 성공은 운영 전환 허가가 아니다. 반복 콘솔 작업의 queued 이후 장기 상태 동기화와 다음 회차 관리, CLI→관리 서비스 통신은 A8/A9와 운영 전환 수락에서 별도 확인해야 한다. 현재 모든 실경로가 legacy이므로 이 미완성이 기존 운영 상태를 바꾸지 않는다.
