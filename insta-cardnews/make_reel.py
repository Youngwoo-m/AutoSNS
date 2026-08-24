"""카드 PNG 들 + 배경음악(mp3)을 세로 릴 영상(mp4)으로 합성한다.

- 1080x1920(9:16) 세로. 1:1 카드를 가운데 두고 위아래를 브랜드 배경색으로 채운다.
- 카드당 표시 시간(초)만큼 슬라이드쇼로 이어붙이고, 음악을 입혀(짧으면 반복) 페이드아웃.
- ffmpeg 은 imageio-ffmpeg 내장 바이너리를 쓴다(시스템 설치 불필요).
- 음악은 영상에 직접 인코딩되므로, 인스타 업로드 시 별도 음악 선택이 필요 없다.

배경음악 파일: config.reel.audio_file (기본 assets/bgm.mp3). 저작권 자유(royalty-free)
음원을 넣어야 한다. 파일이 없으면 명확히 안내하고 중단한다.
"""
import os
import subprocess
import time

import imageio_ffmpeg

from common import BASE_DIR, POSTS_DIR, load_config, log

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def _abs(p):
    return p if os.path.isabs(p) else os.path.join(BASE_DIR, p)


def make_reel(data, audio_path=None):
    cfg = load_config()
    rcfg = cfg.get("reel", {})
    images = [p for p in (data.get("images") or []) if os.path.exists(p)]
    if not images:
        raise RuntimeError("릴로 만들 카드 PNG 가 없습니다. 먼저 카드를 렌더하세요.")

    audio = _abs(audio_path or rcfg.get("audio_file", "assets/bgm.mp3"))
    if not os.path.exists(audio):
        raise SystemExit(
            f"배경음악 파일이 없습니다: {audio}\n"
            f"저작권 자유(royalty-free) mp3 를 그 경로에 넣어주세요.")

    secs = float(rcfg.get("seconds_per_card", 3.5))
    bg = rcfg.get("bg_color", "0x0f2038")
    dur = round(secs * len(images), 2)

    stamp = data.get("stamp") or time.strftime("%Y%m%d_%H%M%S")
    work = os.path.join(POSTS_DIR, f"reel_{stamp}")
    os.makedirs(work, exist_ok=True)

    # concat demuxer 용 리스트(각 이미지 duration 지정, 마지막 프레임 1회 반복)
    list_path = os.path.join(work, "list.txt")
    with open(list_path, "w", encoding="utf-8") as f:
        for p in images:
            f.write(f"file '{os.path.abspath(p).replace(chr(92),'/')}'\n")
            f.write(f"duration {secs}\n")
        f.write(f"file '{os.path.abspath(images[-1]).replace(chr(92),'/')}'\n")

    out = os.path.join(POSTS_DIR, f"{stamp}_reel.mp4")
    # 카드를 940px 로 살짝 줄여 세로 가운데 배치 → 인스타 릴 썸네일의 1:1 중앙 크롭에도
    # 카드 상·하단(제목/출처)이 잘리지 않게 여백을 준다(기존 1080 은 크롭 경계에 딱 붙어 잘림).
    card = int(rcfg.get("card_px", 940))
    vf = (f"scale={card}:{card}:force_original_aspect_ratio=decrease,"
          f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color={bg},"
          f"setsar=1,fps=30,format=yuv420p")
    afade = max(dur - 1.5, 0)
    cmd = [
        FFMPEG, "-y",
        "-f", "concat", "-safe", "0", "-i", list_path,
        "-stream_loop", "-1", "-i", audio,
        "-t", str(dur),
        "-vf", vf,
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
        "-af", f"afade=t=in:st=0:d=0.6,afade=t=out:st={afade}:d=1.5",
        "-movflags", "+faststart",
        out,
    ]
    log(f"릴 영상 합성 중... (카드 {len(images)}장 × {secs}s = {dur}s, 음악 {os.path.basename(audio)})")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out):
        raise RuntimeError(f"ffmpeg 실패:\n{r.stderr[-1500:]}")

    size = os.path.getsize(out)
    log(f"릴 영상 생성: {out} ({size//1024}KB, {dur}s)")
    data["reel"] = out
    return out


if __name__ == "__main__":
    import glob
    import json
    files = sorted(glob.glob(os.path.join(POSTS_DIR, "*.json")))
    if not files:
        raise SystemExit("먼저 generate_cards.py 와 카드 렌더를 실행하세요.")
    with open(files[-1], "r", encoding="utf-8") as f:
        d = json.load(f)
    print(make_reel(d))
