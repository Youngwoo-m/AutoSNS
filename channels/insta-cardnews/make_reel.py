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
    # 카드 사이사이에 배경 영상을 전체 화면으로 보여 준다(2026-10-01): 카드가 사라졌다가
    # 다음 카드가 나타난다. 실사 배경이 있을 때만 — 단색 배경이면 빈 화면이 될 뿐이다.
    gap = float(rcfg.get("video_gap", 1.2))
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
    afade = max(dur - 1.5, 0)
    # 카드 위아래 띠에 주제 맞춤 실사(Pexels)를 깐다(config.reel.stock_bg). 카드는 가리지
    # 않고, 카드 아래 띠에 '배경: 자료 화면'을 표기한다. 받기에 실패하면 예전처럼 단색 배경.
    stock = None
    if rcfg.get("stock_bg", True):
        from reel_broll import bg_sequence, fetch_bg, label_png
        stock = fetch_bg(data)
        if stock and len(stock.get("clips") or []) > 1:
            try:
                stock["path"] = bg_sequence(stock["clips"], dur, work, FFMPEG)
                log(f"릴 배경: 클립 {len(stock['clips'])}개를 7초마다 컷")
            except Exception as e:
                log(f"배경 컷 이어붙이기 실패 → 클립 하나로: {type(e).__name__}: {str(e)[:80]}")
    if stock:
        top = (1920 - card) // 2
        labeled = stock.get("label", True)          # 일러스트 B롤이면 표기하지 않는다
        dur = round(secs * len(images) + gap * (len(images) - 1), 2)
        afade = max(dur - 1.5, 0)
        if stock.get("clips") and len(stock["clips"]) > 1:   # 길어진 길이에 맞춰 다시 컷
            try:
                stock["path"] = bg_sequence(stock["clips"], dur, work, FFMPEG)
            except Exception:
                pass
        inputs = ["-stream_loop", "-1", "-i", audio,                 # 0: 음악
                  "-stream_loop", "-1", "-i", stock["path"]]         # 1: 배경 영상
        graph = (f"[1:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                 f"setsar=1,fps=30[v0];")
        fd = 0.35                                   # 카드가 나타나고 사라지는 시간
        last = "v0"
        for k, img in enumerate(images):
            idx = 2 + k
            inputs += ["-loop", "1", "-t", f"{secs:.2f}", "-i", img]
            start = k * (secs + gap)
            fx = [f"scale={card}:{card}:force_original_aspect_ratio=decrease", "setsar=1",
                  "fps=30", "format=rgba"]
            if k > 0:                                # 첫 카드는 곧바로(썸네일·첫 화면)
                fx.append(f"fade=t=in:st=0:d={fd}:alpha=1")
            if k < len(images) - 1:                  # 마지막 카드는 끝까지 남긴다
                fx.append(f"fade=t=out:st={secs - fd:.2f}:d={fd}:alpha=1")
            fx.append(f"setpts=PTS-STARTPTS+{start:.2f}/TB")
            graph += f"[{idx}:v]{','.join(fx)}[c{k}];"
            graph += f"[{last}][c{k}]overlay=(W-w)/2:(H-h)/2:eof_action=pass[v{k + 1}];"
            last = f"v{k + 1}"
        if labeled:
            li = 2 + len(images)
            inputs += ["-loop", "1", "-i", label_png(work)]
            graph += (f"[{last}][{li}:v]overlay={(1080 - card) // 2}:{top + card + 16}:shortest=1,"
                      f"format=yuv420p[v]")
        else:
            graph += f"[{last}]format=yuv420p[v]"
        vargs = ["-filter_complex", graph, "-map", "[v]", "-map", "0:a"]
        log(f"릴 배경: {'실사' if labeled else '일러스트'} '{stock['query']}' "
            f"({stock.get('source', '')} {stock['id']}, by {stock['by']})"
            + (" + '배경: 자료 화면' 표기" if labeled else ""))
        data["reel_stock"] = {k: stock.get(k) for k in ("source", "query", "id", "by", "url")}
    else:
        inputs = ["-f", "concat", "-safe", "0", "-i", list_path, "-stream_loop", "-1", "-i", audio]
        vargs = ["-vf", (f"scale={card}:{card}:force_original_aspect_ratio=decrease,"
                         f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color={bg},"
                         f"setsar=1,fps=30,format=yuv420p")]
    cmd = [
        FFMPEG, "-y",
        *inputs,
        "-t", str(dur),
        *vargs,
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", "30",
        # 실사 배경을 어둡게 가공하지 않으니 비트레이트가 7Mbps 까지 올랐다 — 웹 업로드가
        # 느려지지 않게 상한을 둔다(인스타가 어차피 다시 압축한다).
        "-crf", "23", "-maxrate", "4M", "-bufsize", "8M",
        "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
        "-af", f"afade=t=in:st=0:d=0.6,afade=t=out:st={afade}:d=1.5",
        "-movflags", "+faststart",
        out,
    ]
    log(f"릴 영상 합성 중... (카드 {len(images)}장 × {secs}s"
        + (f" + 사이 영상 {gap}s × {len(images) - 1}" if stock else "")
        + f" = {dur}s, 음악 {os.path.basename(audio)})")
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
