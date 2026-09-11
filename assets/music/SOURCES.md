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
