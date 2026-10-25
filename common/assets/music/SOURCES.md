# 배경음악 출처 (CC BY 4.0)

손으로 만든 홍보 영상에 상업 음원을 쓰면 유튜브 Content ID 주장이 걸린다
(2026-09 태무산 홍보 영상이 ATEEZ 'BAD' 로 러시아 차단됨). 아래 음원으로 교체한다.

모두 Kevin MacLeod (incompetech.com) / CC BY 4.0 — **영상 설명에 출처 표기 필수**:

    🎵 배경음악: <곡명> — Kevin MacLeod (incompetech.com) / CC BY 4.0

| 곡 | 분위기 | 내려받기 |
|---|---|---|
| Cut and Run | 드럼·베이스 중심 업비트(가장 강함) | `curl -O https://incompetech.com/music/royalty-free/mp3-royaltyfree/Cut%20and%20Run.mp3` |
| Blip Stream | 밝은 신스 비트 | `.../Blip%20Stream.mp3` |
| Electrodoodle | 일렉트로닉 댄스 | `.../Electrodoodle.mp3` |

교체 방법(영상 재인코딩 없이 오디오만 교체):

    ffmpeg -y -i 원본.mp4 -ss 10 -i assets/music/Cut_and_Run.mp3 \
      -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 192k \
      -af "afade=t=in:st=0:d=1,afade=t=out:st=26.4:d=2,loudnorm=I=-14:TP=-1.5" \
      -shortest -movflags +faststart 결과.mp4

## AI 생성 음악 (Google Lyria 3 Clip, 2026-09-29~ 기본)

세명대 AI 게이트웨이(`/v1/gateway/audio/music/`, lyria-3-clip-preview, 곡당 40 크레딧)로 만든
연주곡. 한 번 받은 30초 곡을 3초 크로스페이드로 두 번 이어 약 57초로 늘렸다(숏폼 한 편보다
길게 — 루프 이음새가 들리지 않게). 음량은 loudnorm 으로 맞춰 두었다.

| 파일 | 용도 | 음량 | 믹스 volume |
|---|---|---|---|
| lyria_news_1 / lyria_news_2 | 뉴스(차분) | -20 LUFS | 0.2 → -34 LUFS |
| lyria_bright_1 / lyria_bright_2 | 퀴즈·진로(밝음) | -20 LUFS | 0.2 |
| lyria_reel_1 | 카드뉴스 릴스(나레이션 없음) | -29 LUFS | 그대로 |

설명 표기: `🎵 배경음악: AI 생성 음악(Google Lyria, 세명대 AI 게이트웨이)` (출처 표기 의무는 없지만
AI 생성임을 밝혀 둔다). 이미 렌더해 둔 예약 영상은 원래 곡(Kevin MacLeod)과 그 표기를 유지한다.
