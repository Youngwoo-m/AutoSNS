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
3. 글꼴: 제목·보조 모두 **Pretendard Bold**, 인스타 카드 본문만 KoPub 돋움 Bold
   (assets/FONTS/). 굵기 대신 글자 크기와 색으로 위계를 준다 — Black·검은고딕은 "너무 두꺼워
   읽기 어렵다"고 반려됐다(2026-10-14). 글꼴을 바꿀 때는 `shared/fonts.py` 의 DISPLAY
   한 줄만 고치면 썸네일·영상 프레임·카드·배너가 모두 따라온다.
   AI가 만든 사람·목소리가 나오면 화면과 설명에 AI 합성 고지를 넣는다.

기존 자동 발행 파이프라인(make_video.py 등 ffmpeg 기반)은 아직 이 지침으로 바꾸지 않았다.
바꿀 때는 사용자와 범위를 정한 뒤 옮긴다.
(2026-10-18 옮김: 클로드 자동 작업 survey-daily 숏츠 — `remotion-shorts/src/survey-short` + `channels/youtube-shorts-auto/diorama_image.py`.)

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
`channels/naver-blog-auto/MATH_GIF_PROMPT.md`, `channels/naver-blog-auto/math_gif/` 를 따른다.
GIF 는 mp4 로 그린 뒤 ffmpeg 팔레트 변환(2MB 이하), Blogger 는 줄이지 않고 올린다(`math_gif/post_draft.py`).
시험 글은 공개하지 말고 Blogger 초안으로 먼저 확인한다. 숫자 계산은 calc-verifier, 출처는 source-reviewer 로 검토한다.

## 발행

글·영상 발행 절차는 `.claude/skills/sns-publish-post` 를 따른다.

## 브랜치

브랜치 이름·병합 순서·커밋 메시지 규칙은 `docs/브랜치규칙.md` 를 따른다.

## 폴더 구조 (2026-10-25 개편 진행 중)

앱 계정(학과·개인·공통)에 맞춰 `common/`(shared·analytics·maintenance·tools·assets·remotion-shorts),
`dept/`, `personal/` 로 나눈다. 1단계로 `common/` 을 옮겼고, 옛 경로(`shared/`, `tools/` 등)는
`common/…` 를 가리키는 심볼릭 링크로 남겼다(launchd·자동화는 옛 경로 그대로 동작). 새 코드는 `common/…` 를 쓴다.
스크립트의 ROOT 계산은 `realpath` 기준 3단계 위다. 되돌릴 기준점: 태그 `backup/pre-restructure-20261025`.
