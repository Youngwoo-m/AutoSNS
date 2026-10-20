"""나레이션 자막을 영상에 입힌다 — 말하는 순간에 맞춰 화면 아래쪽에 한 줄씩.

화면에는 장면 요약 문구만 있고 나레이션 자막은 유튜브 CC 로만 올려서, 소리를 끄고
보는 사람에게는 나레이션이 전달되지 않았다(MoneyPrinterTurbo 검토, 2026-09-29).

타이밍은 Edge TTS 의 단어 경계(WordBoundary)에서 받는다 — 추가 비용 없음, 한국어도
단어 단위로 온다. 단어를 한 줄(max_chars) 단위로 묶고, 문장이 끝나면 줄을 끊는다.
시스템 ffmpeg 에 자막 파일 필터(libass)가 없어 drawtext 를 조각마다 시간 지정해 그린다.

위치: 학과명(푸터) 바로 위(1920 기준 y≈1400). 장면 요약 문구·후킹(y≈450)·구독 안내
(y≈710)와 겹치지 않는 자리다.
"""
import asyncio
import os
import re
import subprocess

from common import load_config, log

Y_1920 = 1400          # 자막 띠 윗변(1920 높이 기준)
MAX_CHARS = 15         # 한 줄 최대 글자 수(공백 포함)


async def _words_async(text, voice, rate):
    import edge_tts
    kw = {"voice": voice, "boundary": "WordBoundary"}
    if rate:
        kw["rate"] = rate
    out = []
    async for ch in edge_tts.Communicate(text, **kw).stream():
        if ch["type"] == "WordBoundary":
            out.append([round(ch["offset"] / 1e7, 3),
                        round((ch["offset"] + ch["duration"]) / 1e7, 3), ch["text"]])
    return out


def words_for(text):
    """이미 만든 영상에 자막을 덧입힐 때 쓴다 — 같은 문장을 다시 합성해 타이밍만 받는다."""
    tcfg = load_config().get("tts", {})
    return asyncio.run(_words_async(text, tcfg.get("voice", "ko-KR-SunHiNeural"),
                                    tcfg.get("rate", "+6%")))


def _chunks(words, text, max_chars=MAX_CHARS):
    """단어들을 한 줄씩 묶는다. 문장이 끝나는 단어(원문에서 뒤에 . ? ! 가 붙은 것)에서 끊는다."""
    pos, out, cur = 0, [], []
    for w in words:
        i = text.find(w[2], pos)
        end_sentence = False
        if i >= 0:
            pos = i + len(w[2])
            end_sentence = bool(re.match(r"\s*[.?!…]", text[pos:pos + 2]))
        line = " ".join(x[2] for x in cur + [w])
        if cur and len(line) > max_chars:
            out.append(cur)
            cur = []
        cur.append(w)
        if end_sentence:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def cues(data):
    """[(시작초, 끝초, 글)] — 장면 오디오 길이를 이어 붙여 영상 전체 시간으로 바꾼다."""
    scenes, audio = data.get("scenes") or [], data.get("audio") or []
    res, off = [], 0.0
    for sc, au in zip(scenes, audio):
        text = (sc.get("narration") or "").strip()
        words = au.get("words")
        if words is None and text:
            words = words_for(text)
        scene_end = off + float(au["duration"])
        groups = _chunks(words or [], text)
        for k, g in enumerate(groups):
            start = off + g[0][0]
            end = off + (groups[k + 1][0][0] if k + 1 < len(groups) else g[-1][1] + 0.35)
            res.append((round(start, 2), round(min(end, scene_end), 2), " ".join(x[2] for x in g)))
        off = scene_end
    return res


def burn(video, data, work_dir):
    """video 에 자막을 입혀 제자리에서 바꾼다. 돌려주는 값은 입힌 줄 수."""
    from make_video import _ffmpeg
    from overlays import _font
    cs = cues(data)
    if not cs:
        return 0
    os.makedirs(work_dir, exist_ok=True)
    fnt = _font().replace(":", r"\:")
    parts = []
    for n, (a, b, t) in enumerate(cs):
        tf = os.path.join(work_dir, f"cap_{n:03d}.txt")
        with open(tf, "w", encoding="utf-8") as f:
            f.write(t)
        parts.append(
            f"drawtext=fontfile='{fnt}':textfile='{tf}':fontcolor=white:fontsize=54:"
            f"box=1:boxcolor=0x0B1C3A@0.72:boxborderw=18:"
            f"x=(w-text_w)/2:y=h*{Y_1920 / 1920:.4f}:enable='between(t,{a},{b})'")
    tmp = video.replace(".mp4", ".cap.tmp.mp4")
    r = subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", video,
                        "-vf", ",".join(parts), "-c:v", "libx264", "-preset", "veryfast",
                        "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", tmp],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"자막 입히기 실패: {r.stderr[-400:]}")
    os.replace(tmp, video)
    log(f"나레이션 자막 {len(cs)}줄 입힘: {os.path.basename(video)}")
    return len(cs)
