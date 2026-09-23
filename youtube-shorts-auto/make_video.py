"""프레임 PNG + 나레이션 mp3 → 세로(9:16) Shorts mp4 를 만든다.

시스템 ffmpeg 이 없어도 되도록 imageio-ffmpeg 가 번들한 ffmpeg 바이너리를 쓴다.
장면마다 (이미지 1장 + 나레이션 1개)를 그 나레이션 길이만큼의 세그먼트 mp4 로 만들고,
전부 이어붙여 최종 mp4 를 만든다. (선택) 배경음악을 낮은 볼륨으로 깔 수 있다.

인터페이스: make_video(data) -> mp4경로, data['video'] 채움.
"""
import json
import os
import subprocess
import time

import imageio_ffmpeg

from common import POSTS_DIR, load_config, log

W, H = 1080, 1920
FPS = 30


def _ffmpeg():
    return imageio_ffmpeg.get_ffmpeg_exe()


def _run(args):
    """ffmpeg 실행. 실패하면 마지막 로그와 함께 예외."""
    proc = subprocess.run(
        [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 실패:\n{proc.stderr.strip()[-1500:]}")


def _vf_motion(dur, zoom_max):
    """켄번스(느린 중앙 줌인) 필터. 정적 카드에 움직임을 줘 완주율을 높인다.

    - 입력을 2배로 키운 뒤 zoompan 으로 서서히 확대 → 다시 1080x1920 로 출력(선명도 유지).
    - 줌은 은은하게(기본 1.06배)라 상·하단 세이프존/자막이 잘리지 않는다.
    """
    nf = max(int(round(dur * FPS)), 1)
    step = (zoom_max - 1.0) / nf
    return (
        f"scale={W*2}:{H*2}:force_original_aspect_ratio=decrease,"
        f"pad={W*2}:{H*2}:(ow-iw)/2:(oh-ih)/2:color=white,"
        f"zoompan=z='min(zoom+{step:.6f},{zoom_max})':d={nf}"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},"
        f"setsar=1"
    )


def _vf_static():
    return (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=white,setsar=1")


def _segment_broll(frame, audio, dur, out_path, broll):
    """B롤 영상 위에 투명 프레임(자막·소제목)을 얹어 한 장면을 만든다.

    클립이 장면보다 짧으면 -stream_loop 로 반복하고, 길면 -t 로 자른다.
    9:16 로 맞출 때는 늘리지 않고 꽉 채운 뒤 잘라낸다(increase+crop) — pad 로
    레터박스를 두면 위아래 검은 띠가 생겨 자막 영역과 겹친다.
    켄번스 줌은 걸지 않는다. 클립이 이미 움직이는데 덧대면 흔들려 보인다.
    """
    fc = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
          f"crop={W}:{H},fps={FPS},setsar=1[bg];"
          f"[bg][1:v]overlay=0:0:format=auto,trim=duration={dur:.3f},"
          f"setpts=PTS-STARTPTS[v]")
    _run(["-stream_loop", "-1", "-i", broll, "-i", frame, "-i", audio,
          "-filter_complex", fc,
          "-map", "[v]", "-map", "2:a",
          "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
          "-r", str(FPS),
          "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-af", "apad",
          "-t", f"{dur:.3f}", out_path])


def _segment(frame, audio, dur, out_path, motion=True, zoom_max=1.06, broll=""):
    if broll:
        return _segment_broll(frame, audio, dur, out_path, broll)
    vf = _vf_motion(dur, zoom_max) if motion else _vf_static()
    args = ["-loop", "1", "-i", frame, "-i", audio,
            "-c:v", "libx264", "-preset", "veryfast"]
    if not motion:
        args += ["-tune", "stillimage"]   # 정지영상 최적화(움직임 있으면 부적합)
    args += [
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-vf", vf,
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-af", "apad",
        "-t", f"{dur:.3f}",
        out_path,
    ]
    _run(args)


def _concat(seg_paths, list_path, out_path):
    with open(list_path, "w", encoding="utf-8") as f:
        for p in seg_paths:
            f.write("file '" + p.replace("\\", "/").replace("'", "'\\''") + "'\n")
    _run([
        "-f", "concat", "-safe", "0", "-i", list_path,
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-movflags", "+faststart",
        out_path,
    ])


def _mix_bgm(video_in, bgm_path, volume, out_path):
    """배경음악을 루프해 낮은 볼륨으로 깐다. 나레이션은 그대로 유지."""
    _run([
        "-i", video_in,
        "-stream_loop", "-1", "-i", bgm_path,
        "-filter_complex",
        f"[1:a]volume={volume}[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        out_path,
    ])


def make_video(data):
    cfg = load_config()
    vcfg = cfg.get("video", {})
    # 길이 상한: data 로 넘기면 우선(개별 영상용), 없으면 config/기본값
    max_sec = float(data.get("max_seconds") or vcfg.get("max_seconds", 58))

    motion = vcfg.get("motion", True)             # 켄번스 줌(완주율↑). 끄려면 false
    zoom_max = float(vcfg.get("zoom_max", 1.06))  # 줌 세기(과하면 자막 잘림 주의)

    frames = data.get("frames") or []
    audio = data.get("audio") or []
    if not frames or not audio:
        raise RuntimeError("프레임/오디오가 없습니다. render_frames → tts 를 먼저 실행하세요.")
    n = min(len(frames), len(audio))
    frames, audio = frames[:n], audio[:n]

    stamp = data.get("stamp") or time.strftime("%Y%m%d_%H%M%S")
    work = os.path.join(POSTS_DIR, f"video_{stamp}")
    os.makedirs(work, exist_ok=True)

    brolls = data.get("broll_used") or {}
    seg_paths, total = [], 0.0
    for i, (fr, au) in enumerate(zip(frames, audio)):
        dur = float(au["duration"])
        if total + dur > max_sec and seg_paths:
            log(f"길이 상한({max_sec}s) 도달 → 장면 {i+1}부터 제외")
            break
        seg = os.path.join(work, f"seg_{i+1:02d}.mp4")
        _segment(fr, au["path"], dur, seg, motion=motion, zoom_max=zoom_max,
                 broll=brolls.get(str(i + 1), ""))
        seg_paths.append(seg)
        total += dur
        log(f"세그먼트 {i+1}/{n} 생성({dur:.1f}s, 누적 {total:.1f}s)")

    out_path = os.path.join(POSTS_DIR, f"short_{stamp}.mp4")
    _concat(seg_paths, os.path.join(work, "_list.txt"), out_path)
    log(f"영상 합치기 완료(총 {total:.1f}s): {out_path}")

    bgm = vcfg.get("bgm_path", "")
    if bgm and os.path.exists(bgm):
        mixed = os.path.join(POSTS_DIR, f"short_{stamp}_bgm.mp4")
        _mix_bgm(out_path, bgm, float(vcfg.get("bgm_volume", 0.12)), mixed)
        out_path = mixed
        log(f"배경음악 믹스 완료: {out_path}")

    try:                                       # 후킹(초반)·CTA(후반) 오버레이(완주율·구독 전환↑)
        from overlays import apply as apply_overlays
        apply_overlays(out_path, dur=total)    # out_path 제자리 교체
    except Exception as e:
        log(f"오버레이 건너뜀(영상은 정상): {type(e).__name__}: {e}")

    data["video"] = out_path
    data["video_seconds"] = round(total, 1)
    with open(os.path.join(POSTS_DIR, f"{stamp}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return out_path


if __name__ == "__main__":
    import glob
    files = sorted(glob.glob(os.path.join(POSTS_DIR, "*.json")))
    if not files:
        raise SystemExit("먼저 generate_script.py → render_frames.py → tts.py 를 실행하세요.")
    with open(files[-1], "r", encoding="utf-8") as f:
        d = json.load(f)
    print(make_video(d))
