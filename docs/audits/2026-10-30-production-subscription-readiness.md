# 제작·독립 검토·구독 비용 경계 사전 조사

2026-10-30. T12 후속 계획을 위한 정적 코드·지시문 조사다. 제작기·모델·Claude CLI·검토자·브라우저·서비스 API를 실행하지 않았다. config·비밀값·토큰·환경변수의 실제 값은 읽지 않았다. 코드는 변경하지 않았다.

## 결론과 근거 범위

새 phase4 runtime에는 subscription_only 정책 검사와 산출물/독립 검토 hash 결합이 있다. 그러나 **실제 제작·검토 프로세스를 그 정책 아래 실행시키는 producer는 없다**. 기존 CLI나 generate 함수를 그대로 호출하면 발행 부수효과 또는 유료/학교 호출을 포함할 수 있다. 구독만으로 복구하라는 개인 작업의 범위는 legacy 공용 fallback보다 엄격하므로, 구독 probe 성공만으로 그 작업 전체를 안전하게 재개할 수 없다.

아래 경로는 별도 표시가 없으면 작업 사본 기준이다. 원본 `/Volumes/USB256/devAPP/AutoSNS`와 AGENTS.md·CLAUDE.md·common/shared/llm.py·personal/claude-jobs/run_claude_job.sh·공통규칙.md·dept/youtube-shorts-auto/diorama_image.py·geoai_video.py의 **파일 bytes가 동일함**을 해시 비교했다. 나머지 참조 파일은 작업 사본의 코드상 후보이며 운영 배포 동일성까지 주장하지 않는다. 실행 중인 공급자·로그인·잔액·키 설정은 확인하지 않았다.

## 1. 제작 진입점 → 공급자 → 외부 변경

| 경로 | 정적 호출과 부수효과 | 관리 producer에 필요한 분리 |
|---|---|---|
| 개인 기술사·훈련 `personal/claude-jobs/run_claude_job.sh:17` | 작업/AX_HOUR별 model과 runs를 고름. :35 공통규칙과 개별 jobs 지시문을 합침. :55 `claude -p --permission-mode bypassPermissions`와 넓은 디렉터리 권한으로 실행 | 원래 prepare/확인 회차 보존, 서브프로세스 권한/출력 allowlist 분리. 이 CLI는 제작 전용이 아님 |
| 개인 지시문 `공통규칙.md:57` | shorts-maker 생성·음성·렌더 → :63 부모가 geoai_short_post로 업로드·예약·댓글. :86 개인 Tistory 공개 뒤 개인 Naver 교차 게시 | 기존 원문 지시문을 관리 producer에 그대로 주면 안 됨. 제작 산출물 반환과 발행 실행을 별도 계약으로 분리 |
| 개인 GeoAI `dept/naver-blog-auto/geoai_daily.py:281` | generate_content.generate → :337 geoai_blogger import → :360 캡처 upload_for → :386 publish → :393 community 후속 | generate/compose와 자산 공개 업로드·Blogger publish·community를 분리. dry 플래그만으로 무부작용을 추정하지 않음 |
| 개인 GeoAI 연재 `dept/naver-blog-auto/geoai_series.py:646` | `_llm_client(cfg)` 생성 요청, :812 publish | 계정명이 dept 경로에 있다고 학과 제작으로 분류하지 않음. 순수 생성/본문 합성만 producer 후보 |
| 학과 블로그/숏츠 `generate_content.py:271`, `generate_script.py:318` | 둘 다 `_llm_client`를 거쳐 shared.llm.client. 같은 파일 안 provider 보호 없이 재사용 가능 | source별 허용 정책과 계정 주입. 공용 cfg를 그대로 전달하지 않음 |
| 개인 영상 `dept/youtube-shorts-auto/geoai_video.py:40` | card 경로 :69 make_frames → :70 make_tts → :71 make_video → :74 upload, :85 post_top_comment. anchor 경로 :61 make_news_anchor | 영상 파일 생성 함수와 upload/comment/caption 등 원격 변경을 끊어야 함. 실행 함수 자체를 producer로 등록 금지 |
| 웹 초안 `ax-console/app/draft_ai.py:59` | shared.llm.client(load_config()).messages.create | 기존 콘솔 초안 생성은 별도 fallback 경로. phase4 비활성 정책의 자동 보호를 받는다고 볼 수 없음 |
| 웹 에이전트 `ax-console/app/agent_core.py:96` | cfg의 gateway/CLI/Anthropic 클라이언트 목록 생성 후 :119 순차 호출 | tool 실행까지 가능한 기존 agent를 제작 권한으로 축소해야 함. 목록에 유료 클라이언트 자체가 들어오지 않는 정책 검사 필요 |

## 2. 구독 실패 시 유료/학교 우회가 가능한 정확한 경계

1. `common/shared/llm.py:54~85`: `_Messages.create`는 후보 실패/지원 불가 시 다음 후보로 이동하고 마지막에 `_direct.messages.create`를 호출한다. `client:322~334`는 text_enabled이면 학교 후보, CLI 가능하면 구독 후보, anthropic_api_key가 있으면 direct를 만든다. 따라서 구독의 주간/월간 한도·로그인·timeout 후 API fallback이 코드상 가능하다. 설정 값은 열지 않았으므로 현재 어느 후보가 활성인지 단정하지 않는다.
2. `llm.py:257`의 CLI 환경은 ANTHROPIC_API_KEY만 제거한다. 이는 해당 CLI 한 번의 호출 설정이고 전체 프로세스 트리·후속 Python의 cfg·다른 인증 관련 환경을 제거하거나 유료 fallback을 금지하는 전역 정책이 아니다.
3. `personal/claude-jobs/run_claude_job.sh:55`는 실제 CLI 환경을 별도로 정제하지 않는다. 현재 환경에 키가 존재한다고 주장하는 것이 아니라 **구독-only를 이 wrapper가 기계적으로 입증하지 못한다**는 의미다.
4. `agent_core.py:106~113`은 text_enabled일 때 gateway를, anthropic_api_key가 있으면 Anthropic을 후보 목록에 추가한다. :119의 순차 실행은 별도 우회 경로다. draft_ai도 공용 llm fallback을 사용한다.
5. `dept/youtube-shorts-auto/diorama_image.py:51~72`는 cfg gateway 키 목록과 월 할당을 확인하고 `/images/generate/` POST를 직접 호출한다. `diorama_clip.py:76~95`와 `veo_clips.py:114`는 영상 generation과 상태 조회 경로다. 글 LLM을 구독 전용으로 바꿔도 이 이미지/영상 호출은 별도로 남는다.
6. `shorts-maker.md:26~34`는 그림 2~3장 및 선택 클립을 지시한다. `공통규칙.md:70`은 시험에서도 실제 그림을 그릴 수 있다고 명시한다. 따라서 AX_DRY는 생성 비용0 또는 네트워크0의 근거가 아니다.
7. `geoai_video.py:61` anchor 경로는 HeyGen 제작으로 갈 수 있고 `heygen_anchor.py:30~46`에 별도 API 키·요청 구현이 있다. 이번 조사로 현재 실제 요금·활성 설정은 확인하지 않았다. subscription_only producer에서 기본 차단해야 할 별도 공급자다.

### 개인 구독-only와 기존 학과 정책의 구별

- 이번 개인 실패 복구의 사용자는 유료 Anthropic·학교 우회를 금지했다. 새 정책의 유효 범위는 내부 생성기·검토기까지 포함되어야 한다. 이미지/영상이 필요하나 허용된 기존 산출물 재사용 또는 구독 경로가 없으면 단계 중단이 맞다. 자동으로 매체 생략·다른 스타일/도구로 요구사항을 축소하지 않는다.
- 기존 프로젝트 CLAUDE.md:42~47은 학교 크레딧을 영상 제작에 한정하고 글은 CLI 후 Anthropic fallback이라고 설명한다. 개인/학과 공통 legacy 설명이므로 새 개인 제약보다 우선하지 않는다. 동시에 사용자의 이번 제한을 근거 없이 모든 학과 작업에 영구 확대하지 않는다.
- `publication_gate.py:45~51`은 새 runtime에서 provider_policy와 job_policy의 subscription_only=True를 요구한다. 현재는 실제 제작기 연결 전 공통 정책 계약이다. 이름만 True인 boolean은 실제 내부 도구 비용이 차단됐다는 증거가 아니다. 학과 media의 기존 별도 허용 정책을 이어갈 경우, 계정/작업/매체별 예산과 공급자 허용 규칙을 명시 설계·검토한 뒤 적용해야 한다.

## 3. 음성·렌더링·자산 공개의 구별

- `shorts_voice.py:35` 기본 Voicebox, :138 관리 스크립트 기동, :142 로컬 generation, :160 종료. edge 백엔드 :59는 온라인 TTS다. 무료/키 불필요라는 설명과 네트워크 없음은 다르다. 검사 결과 backend/voice_label·실측 seconds·받아쓰기 결과를 산출물에 보존한다.
- `tts.py:22~34`는 edge_tts.Communicate의 온라인 stream이고 :43 이후 출력 디렉터리/JSON 쓰기가 있다. 로컬 렌더와 한꺼번에 무네트워크로 분류하지 않는다.
- `dept/disaster-shorts/tools/voice.py:149~151`에는 Voicebox 프로세스 종료/재기동 구현이 존재한다. 사람 앱 보존 규칙 때문에 범용 producer의 자동 복구 루틴으로 그대로 가져오지 않는다.
- `geoai_assets.py:46~57,98`은 gh auth와 외부 자산 upload가 가능한 코드다. 이미지 파일 생성과 공개 저장소 업로드는 다른 권한이다. 공개 자산을 먼저 올린 뒤 블로그만 permit으로 막는 구조는 제작-only가 아니다.
- 기존 Remotion/ffmpeg·폰트/디오라마 스타일·합성 고지·20초 제한 등 매체 요구는 보존한다. 실제 CLI/렌더를 실행하지 않았으므로 환경 적합성/최종 미디어 검증을 완료한 것은 아니다.

## 4. 독립 검토를 실제 산출물에 결합하는 데 필요한 것

기존 규칙 `공통규칙.md:74~81`은 계산이 있으면 calc-verifier→수정/재검산, :104~112는 source-reviewer→수정/재검토를 요구한다. 그러나 마지막 상태의 calc/review 요약 문자열은 제출 대상의 최신 bytes 검토를 증명하지 않는다. legacy source-reviewer의 fix 후 재검토 선택(:110)은 새 runtime이 pass만 허용하는 조건과 자동 호환되지 않는다.

phase4 `publication_gate.py:17~42`의 실제 계약은 다음과 같다.

- 생산자 principal_id/execution_id가 보존된 production_provenance와 일치해야 한다.
- source 필수, job policy require_calc_review이면 calc도 필수다. reviewer principal/execution은 생산자 및 서로와 달라야 하며 review_authorities의 역할 등록이 필요하다.
- 보고서 필드는 role,reviewer_id,execution_id,content_id,content_revision,manifest_hash,verdict,checked_at,report_hash이며 pass만 허용한다.
- 해시는 report_hash 자신을 제외한 정규화 JSON으로 계산한다. 보고서 전체와 manifest/revision이 영속 independent_review 근거와 일치해야 한다.
- `runtime_store.py:573` 부근의 content_evidence 저장은 현재 콘텐츠 manifest와 대조한다. 기록 인터페이스가 있다는 사실과 실제 검토자가 실행됐다는 사실은 별개다.

후속 producer는 파일 검토를 마친 시점의 콘텐츠/자산 snapshot을 저장하고 그 content_id/revision/manifest_hash를 리뷰 실행에 전달해야 한다. 리뷰 이후 숫자·출처·스크립트·음성·영상·설명 중 어떤 제출 bytes라도 바뀌면 새 revision/manifest로 다시 필요한 검토를 받아야 한다. producer가 리뷰어 ID만 바꿔 가짜 pass를 만드는 경로는 금지한다. 불명확 계산 가정은 명시 수정 뒤 검토하고 원고 수정 전 unclear/fix를 pass로 변환하지 않는다.

## 5. 후속 구현 파일과 수락 증거

아래는 아직 구현하지 않은 구체적 작업 제안이다.

| 파일/책임 | 필요한 계약/검증 |
|---|---|
| 신규 `common/operations/production.py` | 계정·작업·회차·입력 snapshot·production_unit_id·공급자 정책을 받아 원고/자산/제작 provenance만 반환. 발행·대기열·알림·발행용 credential/token·브라우저 권한 없음 |
| 신규 `common/operations/production_providers.py` | 명시 provider allowlist와 정제된 자식 환경. subscription_only에서 유료/학교 클라이언트 생성·키 조회·호출0. 한도/login/timeout이면 산출물 보존과 차단 결과 |
| 신규 `common/operations/review_runner.py` | 생산자와 다른 실제 실행 신원으로 calc/source를 순서대로 실행. 서버 등록 principal/role·검토 payload와 최신 manifest 결합, 결과 진실성/실행 증거 보존 |
| 기존 shared/llm·agent_core·draft_ai 진입점 | legacy 기본 동작을 임의 변경하지 않고 managed 경로에서는 명시 정책 클라이언트만 전달. unmanaged fallback의 재유입 시험 |
| 기존 shorts-maker/개인 job 지시문·geoai_daily/geoai_video | 생성-only 요청 계약과 결과 parser 분리. 기존 원문 발행 명령/댓글/교차 게시/알림을 생성 subprocess에서 허용하지 않음 |
| 신규 `tests/operations/test_production.py`, `test_production_providers.py`, `test_review_runner.py` | 실제 서비스 없이 자식프로세스·가짜 provider/adapter로 검증 |

필수 수락 항목:

1. 구독 실패(일/주/월 한도·인증·timeout) 각각에서 Anthropic·gateway·HeyGen·이미지/영상 호출0, 키/토큰 조회0. 최상위와 내부 생성·검토 호출을 모두 계측한다. 이 조건의 키/토큰 조회0은 금지한 공급자와 발행용 인증에 관한 것이다. Claude CLI 자체는 기존 구독 세션으로 인증하되 애플리케이션이 그 인증 내용을 추출하거나 다른 공급자에 전달하지 않는다.
2. 생성 중 adapter.submit·Blogger/YouTube/Tistory/Naver·community/comment·교차 큐·공개 자산 업로드·카카오 알림0. 임의 legacy CLI를 producer로 등록하면 거부한다.
3. 제작비는 원본/버전/manifest/production_unit_id로 한 번 예약하고 배포 수만큼 재과금하지 않는다. 실패·응답 불명 비용은 실제 공급자 관측 전 확정0으로 해제하지 않는다.
4. calc/source 실행 누락·동일 주체·중복 execution·과거 report·hash 변조·미등록 reviewer·fix/unclear·원고/매체 수정 뒤 옛 리뷰는 승인 불가다. 두 번 수정 후에도 block이면 게시하지 않는다.
5. 누락/불완전한 PDF·음성·영상·필수 매체·고지/자막/출처, 영상20초 초과이면 제작 완료로 집계하지 않는다. 최종 PDF 전페이지·영상 장면별 검증 증거를 남긴다.
6. prepare/submit/verify 회차를 보존하고 기존 공개/예약 산출물은 재제작하지 않는다. premade 재사용도 해시·검토·관련 URL 갱신 후 실제 snapshot으로 검증한다.
7. 계정별 권한 fixture에서 개인 제작이 학과 credential/profile에 접근0, 반대방향도0. 허용된 개인 원본→학과 배포는 제작기 아닌 대상별 publication 관문에서 수행한다.

본 조사는 정적 경계와 후속 시험 요구를 확정한 것이다. 실제 구독 복구·제작기 격리·독립 검토 실행·실계정 게시를 완료한 증거가 아니다.
