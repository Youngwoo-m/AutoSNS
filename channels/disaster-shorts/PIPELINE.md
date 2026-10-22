# 재난 유형별 피해 양상과 대응 방안 — 숏츠 파이프라인

> 위치: `channels/disaster-shorts/` (2026-10-22 `/Volumes/USB256/shorts-disaster` 에서 이 저장소로 옮김, git 추적. 옛 경로는 바로가기만 남김).
> 2026-10-22 사용자 지정 변경: ① 나레이션·인트로·아웃트로 목소리는 edge-tts **인준**(`ko-KR-InJoonNeural`, `config.json` 의 `voice_backend`/`edge`; 사양이 좋아지면 `"voicebox"` 로 되돌림)
> ② 영상 맨 앞 2.6초에 큰 글자 **훅**(`hook_text`, `hook_seconds`) ③ 화면 자막은 **대본(나레이션) 문장 그대로**(`captions_from_script`) ④ 인트로·아웃트로는 인준 목소리 새 HeyGen 아바타 영상을 다시 붙임(`intro_outro: true`)
> ⑤ 대본은 더 짧게(한글 75~85자, 50초판 190~225자). 실행 설정 `tools/config.json` 은 비밀값이 있어 git 에 올리지 않는다 — `tools/config.example.json` 참고.
> Remotion 글꼴은 git 에 없다: `assets/FONTS/` 의 `KoPubBold.otf`·`Pretendard-Bold.otf` 를 `remotion/public/fonts/` 에 복사한다.

## 영상 구성 (30초 이내)
| 구간 | 길이 | 소스 | 비고 |
|---|---|---|---|
| 인트로 | ≈4.5초 | HeyGen 토킹포토 `b7a0513bc3644e2f9858982961cefcd9` ("Youngwoo in the light blue shirt") | "안녕하세요. 세명대학교 재난안전학과 나영우 교수입니다." — 1회 제작, 전 편 재사용 |
| 본문 | ≈20초 | Veo 3.1 Lite 8초 클립 3개 (세명대 게이트웨이) + Voicebox 내 목소리 나레이션 + 자막 | 편마다 새로 제작 |
| 아웃트로 | ≈4.5초 | HeyGen 같은 아바타 | "이상 재난유형별 피해 양상과 대응방안을 말씀 드렸습니다." + 화면 하단 "다음 편: ○○" 자막(편마다 바뀜) |

## 단계
0. 공통 자산(1회): Voicebox로 인트로·아웃트로 음성 생성 → HeyGen에 오디오 업로드 → 토킹포토 립싱크 영상 2개 → `common/intro.mp4`, `common/outro.mp4`
1. 대본(Claude): `NN_type/script.json` — 장면 3개(나레이션·자막·영문 영상 프롬프트), 행안부 국민행동요령으로 사실 확인
2. 나레이션(Voicebox, 내 목소리 프로필, Qwen TTS 0.6B, ko): 장면별 wav → 무음 정리·-14 LUFS
3. 영상(게이트웨이 Veo): 장면별 8초 9:16 클립, 요청 번호를 `_jobs.json`에 기록해 재실행 시 이어받기
4. 조립(ffmpeg): 장면 클립을 나레이션 길이에 맞춰 자르기 → 자막(Whisper 타이밍) → 인트로 + 본문 + 아웃트로 → 1080x1920 30fps, -14 LUFS
5. 업로드(youtube_upload.py 재사용): 합성 콘텐츠 표시, 설명란에 출처·AI 아바타 고지

## 일정 (매주 화요일 08:00, 학과 채널 @smds2023)
- 주제·순서: `schedule.json` (계절별 52주 계획)
- 일요일 20:00 자동 제작 → 유튜브에 '비공개 + 화요일 08:00 예약 공개'로 업로드 → 카톡으로 미리보기 링크
- 월요일 20:00 재시도(일요일에 맥이 꺼져 있었거나 실패한 경우)
- 월 4~5편 × 1,200 = 4,800~6,000 크레딧

## 비용 (편당)
- Veo: 3클립 × 400 = 1,200 크레딧 (월 12,000 → 최대 약 9편, 대본 몫 제외)
- HeyGen: 인트로·아웃트로 1회만 (API 잔여 781)
- Voicebox: 무료(로컬 CPU, 느림)

## 재사용 코드 (AutoSNS/youtube-shorts-auto)
- `heygen_anchor.py` — upload_audio(), generate(audio_asset_id=…), await_video()  ※ HeyGen v2 API는 2026-10-31 종료 예정 → 인트로·아웃트로는 그 전에 생성하거나 v3로 이전
- `veo_clips.py` — 게이트웨이 Veo 요청·이어받기, MIN_MONTHLY 보호
- `youtube_upload.py` — 업로드·합성 콘텐츠 표시
