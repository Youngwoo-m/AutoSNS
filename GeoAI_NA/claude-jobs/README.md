# 클로드 자동 작업 (개인 계정 · 재난안전과 GeoAI)

Codex 앱 자동화(`~/.codex/automations`)로 돌던 개인 티스토리·개인 블로거 글 작업을 2026-10-18 클로드 실행으로 옮겼다.
launchd → `run_claude_job.sh <작업>` → axlock(비상 정지·중복 실행 방지) → `claude -p` 순서로 돈다. Codex 앱을 켜 둘 필요가 없다.

| 작업 (launchd `com.smuds.claude.…`) | 시각 | 원래 Codex | 채널 |
|---|---|---|---|
| survey-daily — 측량 하루 한 문제 | 06:00 · 08:00 | automation | 티스토리 · 유튜브 숏츠 · 카톡 |
| civil-daily — 토목시공 하루 한 문제 | 08:00 | 8 | 티스토리 · 개인 블로거 |
| survey-friend — 측량 친구 요청 | 23:00 | automation-2 | 티스토리 · 카톡 |
| civil-friend — 토목시공 친구 요청 | 23:10 | 11 | 티스토리 · 개인 블로거 |
| safekorea — 안전한국훈련 | 09:00 · 12:00 · 18:00 | geoai | 티스토리 |
| nordic — 노르딕워킹 | 07:00 | automation-3 | 티스토리 |

Codex '7'(측량 기출 숏츠, 유튜브만)은 티스토리·블로거 작업이 아니라 옮기지 않았다(Codex 에서 일시정지 상태).

## 파일

- `jobs.json` — 작업 표(시각·모델·채널). 고친 뒤 `python3 install.py --load` 로 launchd 를 다시 만든다.
- `jobs/<작업>.md` — 사용자 지시 원문(Codex 에서 그대로 옮김). 내용 요구를 바꿀 때는 여기를 고친다.
- `공통규칙.md` — 모든 작업에 앞에 붙는 실행 규칙(발행 도구, 기록 파일, 시험 실행, 안전).
- `run_claude_job.sh` — 실행기. 3시간 넘으면 끊는다. 출력은 `logs/<작업>.log`.
- `state/<작업>.jsonl` — 회차별 결과 기록(대화 기록 대신, git 제외).

## 발행 도구 (`naver-blog-auto/`)

- `tistory_post.py` — 티스토리 공용 발행기. profile:tistory 잠금을 잡고, 같은 제목 글이 있으면 건너뛴다.
  본문의 `<p data-ax-attach="파일"></p>` 자리에 그림·PDF 를 네이티브 첨부로 올린다(편집기에 끌어다 놓기 방식 —
  파일 입력칸에 경로를 넣는 방식은 업로드가 시작되지 않았다).
- `blogger_post.py` — 개인 Blogger(geoaina) 발행기. quota:blogger-personal 잠금, 같은 제목 건너뛰기, https 주소만 허용.
- `kakao_notify.py "메시지" "링크"` — 카카오톡 나에게 보내기.
- `youtube-shorts-auto/geoai_short_post.py` — 개인 유튜브(@geoai-safety) 숏츠 업로드·운영자 댓글·상태 확인(upload/comment/check).
  profile:youtube-personal 잠금, 20.0초 초과·과거 예약 거부, 같은 제목 영상·기존 운영자 댓글이면 duplicate. AX_DRY=1 이면 점검만.
- `youtube-shorts-auto/diorama_image.py` · `remotion-shorts/render_survey_short.py` — 측량 숏츠 디오라마 그림(게이트웨이)과 Remotion 렌더(src/survey-short). CLAUDE.md 영상 지침(2026-10-18 survey-daily 에 적용).
- 따라쓰기 PDF 파이썬: `GeoAI_NA/claude-jobs/.venv` (requirements.txt — reportlab·pypdf·pypdfium2·pdfplumber·pillow, git 제외). Codex 런타임은 쓰지 않는다.
- `youtube-shorts-auto/yt_transcript.py URL --out 자막.txt` — 유튜브 영상 정보(임베드 가능 여부 포함)와 한국어 자막 평문(yt-dlp, 영상은 안 받음). safekorea 12시 글의 내용 확인용.

## 시험 실행

```bash
AX_DRY=1 GeoAI_NA/claude-jobs/run_claude_job.sh nordic
```

발행기는 발행 직전에 멈추고, 대기열·카톡·작성상태는 건드리지 않는다. 산출물은 `dry/<작업>/<날짜>/`.
