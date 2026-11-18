# AutoSNS 작업 지침

세명대학교 재난안전학과 SNS 자동 발행 시스템. 사용자에게 보이는 모든 글은 한국어로 쓴다.

## 영상 제작 지침 (2026-10-15 사용자 지정)

새로 만드는 영상(숏츠·릴·홍보 영상 등)은 다음을 따른다.

1. **편집은 Remotion 으로 한다.** 장면 구성·자막·전환·끝 화면 같은 편집은 Remotion 스킬
   (`remotion-best-practices` 를 먼저 읽고 `remotion-create` / `remotion-captions` /
   `remotion-render` 등)로 만든다. ffmpeg 는 소스 준비(자르기·인코딩·음성 합치기)에만 쓴다.
2. **영상마다 디오라마 이미지를 2~3장 넣는다.** 주제 장면을 아이소메트릭 미니어처 디오라마로
   만든 그림(예: 산불이 번지는 산 마을, 침수된 골목, 대피소 운영 모습)을 장면 사이·배경에 쓴다.
   - 만들기: 학교 AI 게이트웨이 이미지 모델(Gemini 이미지) 또는 Google Flow(Nano Banana).
   - 그림 안에 글자를 넣지 않는다(AI가 그린 한글은 깨진다). 글자는 편집 단계에서 얹는다.
   - 사고 순간·부상자·불길 한가운데처럼 고통스러운 장면은 피하고, 대비·대응·구조 장면으로.
   - 실제 사진처럼 보이지 않게 디오라마 질감(미니어처·틸트시프트)을 분명히 한다.
   - 카메라 기법(2026-10-26 추가, 이미지·영상 프롬프트에 한 줄씩 지시): 에스태블리싱 샷 "전경으로 시작"
     / 인서트 샷 "소품을 인서트 샷으로" / 랙 포커스 "앞 피사체에서 뒤 피사체로 초점 이동" /
     프레임 인 프레임 "아치·문·창으로 프레임 인 프레임" / 더치 앵글 "기울인 앵글로 긴장감" /
     아나모픽 "와이드 화면비·가로 플레어·타원 보케" / 틸트 시프트 "위아래를 흐려 미니어처처럼".
     더치 앵글은 불안감을 주므로 재난 영상에서는 대응·구조 장면에만 쓴다.
   - 시네마틱 영상(2026-10-28 추가): 디오라마 영상 클립은 `dept/youtube-shorts-auto/diorama_clip.py`(--move 카메라 움직임 한 가지
     + --camera 룩, 8초 약 240~400 크레딧). 한 클립 = 한 컷·움직임 하나, 룩은 아나모픽·얕은 심도·따뜻한 빛/차가운 그림자·약한 그레인.
     Remotion `survey-short` 는 `kind: "dioclip"` 장면으로 넣는다(디오라마 장면 수에 셈). 재난숏츠(`dept/disaster-shorts`)는
     `assemble.py` 가 장면 영상에 시네마틱 보정(색·비네트·그레인)을 건다(`cinematic: false` 로 끔).
3. 글꼴: 제목·보조 모두 **Pretendard Bold**, 인스타 카드 본문만 KoPub 돋움 Bold
   (assets/FONTS/). 굵기 대신 글자 크기와 색으로 위계를 준다 — Black·검은고딕은 "너무 두꺼워
   읽기 어렵다"고 반려됐다(2026-10-14). 글꼴을 바꿀 때는 `shared/fonts.py` 의 DISPLAY
   한 줄만 고치면 썸네일·영상 프레임·카드·배너가 모두 따라온다.
   AI가 만든 사람·목소리가 나오면 화면과 설명에 AI 합성 고지를 넣는다.

기존 자동 발행 파이프라인(make_video.py 등 ffmpeg 기반)은 아직 이 지침으로 바꾸지 않았다.
바꿀 때는 사용자와 범위를 정한 뒤 옮긴다.
(2026-10-18 옮김: 클로드 자동 작업 survey-daily 숏츠 — `remotion-shorts/src/survey-short` + `dept/youtube-shorts-auto/diorama_image.py`.)

## 자동 작업 잠금·비상 정지 (2026-10-18)

크롬 프로필을 열거나 글을 올리는 작업은 `shared/axlock.py run --job … --res profile:… -- 명령` 으로 실행한다.
자세한 규칙은 `AGENTS.md`. launchd `run_*.sh` 맨 앞의 AX_LOCKED 한 줄은 지우지 않는다.

## 세명대 AI 게이트웨이 크레딧 (2026-10-19 사용자 지정)

게이트웨이 크레딧은 **영상 제작에만** 쓴다(영상 클립 생성, 숏츠 디오라마 그림). 글 작성은 `shared/llm.py` 가
Max 구독(`claude -p`)으로 보내고, 안 되면 Anthropic 키로 간다. 그림이 든 요청과 콘솔 에이전트(도구 호출)도
claude CLI 로 먼저 보낸다(그림은 파일로 넘겨 Read, 도구는 `<tool_call>` 흉내).
게이트웨이로 글을 쓰려면 `llm_gateway.text_enabled` 를 일부러 켜야 한다.

## 글에 수식이 나올 때 (2026-10-23 사용자 지정)

블로거·티스토리·네이버 글에 수식이 있으면 ① 수식은 LaTeX(Manim MathTex)로 써서 이미지로, ② 핵심 식은 Manim 도식 GIF
(글당 1~2개)로 넣는다. 수식이 없는 글에는 만들지 않는다. 지시문·렌더 스크립트·샘플은
`dept/naver-blog-auto/MATH_GIF_PROMPT.md`, `dept/naver-blog-auto/math_gif/` 를 따른다.
GIF 는 mp4 로 그린 뒤 ffmpeg 팔레트 변환(2MB 이하), Blogger 는 줄이지 않고 올린다(`math_gif/post_draft.py`).
시험 글은 공개하지 말고 Blogger 초안으로 먼저 확인한다. 숫자 계산은 calc-verifier, 출처는 source-reviewer 로 검토한다.

## 글 윤문 (2026-11-08 사용자 지정)

자동으로 쓰는 글은 사람이 쓴 것처럼 윤문해서 내보낸다. 글을 쓸 때는 `shared/humanize_rules.py`(HUMANIZE_KR)를
프롬프트에 붙이고, 다 쓴 글은 `shared/humanize.py` 의 `polish_segments()` 로 한 번 더 다듬는다(korean-humanize 스킬 규칙 요약).
숫자·날짜·URL·인용이 달라지거나 많이 바뀐 조각은 원문으로 되돌리고, 실패해도 발행은 그대로 간다.
현재 연결: 네이버 브리핑(`generate_content.py`), 진로·자격증·입시 시리즈(`cert_writer.py` — 블로거·네이버),
GeoAI 개념 시리즈(`personal/naver-blog-auto/geoai_series.py` — 따라하기·프롬프트 예시는 제외),
학과 Blogger 교차 게시(`dept_blogger_post.py --go` — `polish_html()` 로 <p>·<li> 안쪽 글만, 코드·표·제목 제외).
영상 제작 대본(2026-11-09 사용자 지정 — 규칙을 붙이고 제작 전 `polish_script()` 로 내레이션만 2차 윤문, 길이 85~110%·tts_text 숫자 읽기 재적용,
대본 검사를 다시 못 넘으면 원래 대본): 학과 뉴스 숏츠(`generate_script.py`, 설명도), 재난 유형 숏츠(`disaster-shorts/tools/write_script.py`).
직접 대본을 써서 영상을 만들 때도 같은 단계를 거친다.
영상 대본도 제작 전에 한 번 더 윤문한다(2026-11-09 사용자 지정): GeoAI 숏츠 대본(`geoai_script.py` `_polish_script()` — 글자 상한·첫 문장 질문형이 깨지면 원문),
틱톡 1분 해설(`personal/geoai-youtube/tiktok_long.py` `polish_script()` — 장면 70자·목표 글자 수 밖이면 원문). 새 영상 대본 경로에도 같은 단계를 넣는다.
클로드 자동 작업은 `personal/claude-jobs/공통규칙.md` 의 korean-humanize 규칙을 따른다.
새 글쓰기 경로를 만들면 같은 단계를 넣는다. 끄려면 config.json 에 `"humanize": {"enabled": false}`.
윤문·틱톡 캡션은 크레딧 절약 규칙(`~/.agents/memory/model-routing-credit-saving.md`)대로 로컬 Ollama(`qwen3.5:9b-32k`, 윤문만)
→ OpenRouter 무료(`inclusionai/ling-3.2-flash:free`, 키는 환경변수 OPENROUTER_API_KEY) → claude CLI → 키 순으로 보낸다
(`client(cfg, task="polish"|"caption")`, 2026-11-15). 무료 모형은 공개될 글만 받는다. 끄기: `"local_llm"`/`"free_llm": {"enabled": false}`.
크레딧 절약 배분(2026-11-15): `client(cfg, task=…)` 로 부른다 — `polish`(윤문)·`keywords`(자료사진 검색어, `blog_photo.py`)·`classify`(채용공고 선별, `jobs_work24.py` `pick()` — 절반 못 고르면 주 모형으로 다시)·`summary`(채용공고·공고문 요약 — 형식·길이·원문에 없는 숫자 검사에 걸린 건만 주 모형으로 다시)는
Ollama 먼저, `caption`(틱톡 캡션)은 OpenRouter 무료 먼저. 공개 글 본문·대본·사실 확인은 task 없이 주 모형(claude CLI)이 쓴다.

## 영어 블로그 (2026-11-18 사용자 지정)

해외 이용자용 영어 블로그 GeoAI for Disaster Safety(`https://geoai-safety.blogspot.com/`, blog ID 3154612862980198700,
개인 GeoAI 블로거와 같은 구글 계정·토큰)에 `personal/naver-blog-auto/english_series.py` 가 하루 1편(12:30, `run_personal.py english-daily`)을 올린다.
주제 목록(TOPICS)은 순서대로 나가며, 본문은 공개 글이라 주 모형(claude CLI)이 쓴다. 발행 전 검사: <h2> 4개 이상, 800~1800단어,
허용 도메인 밖 링크 제거, 통계·출처 불명 연구처럼 보이는 문장이 있으면 다시 쓰기(3회 실패 시 발행 안 함). 하루에 이미 글이 있으면 건너뛴다.
같은 블로그에는 다른 작업이 올린 번역 글 44편(2026-11-15)과 매일 "Whitebox QGIS Practice"가 있어, 주제는 이들과 겹치지 않는 것만 두고
하루 1편 검사도 이 시리즈 글(english_state.json)만 센다. 주제를 더할 때는 블로그 제목과 먼저 대조한다.
시험: `--dry`(english/drafts/ 에 저장), 목록: `--plan`. 한국어 윤문 단계는 영어 글에 적용하지 않는다. 홈페이지 영어판은 `personal/geoai-site/en/`.

## 발행

글·영상 발행 절차는 `.claude/skills/sns-publish-post` 를 따른다.

## 브랜치

브랜치 이름·병합 순서·커밋 메시지 규칙은 `docs/브랜치규칙.md` 를 따른다.

## 폴더 구조 (2026-10-25 개편 진행 중)

앱 계정(학과·개인·공통)에 맞춰 `common/`(shared·analytics·maintenance·tools·assets·remotion-shorts),
`dept/`, `personal/` 로 나눈다. 1단계로 `common/` 을 옮겼고, 옛 경로(`shared/`, `tools/` 등)는
`common/…` 를 가리키는 심볼릭 링크로 남겼다(launchd·자동화는 옛 경로 그대로 동작). 새 코드는 `common/…` 를 쓴다.
스크립트의 ROOT 계산은 `realpath` 기준 3단계 위다. 되돌릴 기준점: 태그 `backup/pre-restructure-20261025`.
