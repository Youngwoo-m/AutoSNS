"""각 장면 나레이션을 edge-tts(무료, 한국어)로 mp3 로 합성한다.

- 음성/속도는 config.tts 에서 조정. 기본 ko-KR-SunHiNeural.
- 반환: [{path, duration}] 리스트. duration(초)은 mutagen 으로 측정.
- 인터넷 필요(edge-tts 는 Microsoft Edge 온라인 TTS 를 호출). API 키 불필요.

인터페이스: make_tts(data) -> [{path,duration}], data['audio'] 채움.
"""
import asyncio
import json
import os
import time

import edge_tts
from mutagen.mp3 import MP3

from common import POSTS_DIR, load_config, log


async def _synth(text, voice, rate, out_path):
    kwargs = {"voice": voice}
    if rate:
        kwargs["rate"] = rate
    communicate = edge_tts.Communicate(text, **kwargs)
    await communicate.save(out_path)


def _duration(path):
    try:
        return float(MP3(path).info.length)
    except Exception:
        return 0.0


def make_tts(data):
    cfg = load_config()
    tcfg = cfg.get("tts", {})
    voice = tcfg.get("voice", "ko-KR-SunHiNeural")
    rate = tcfg.get("rate", "+6%")     # 살짝 빠르게(Shorts 템포). "" 면 기본속도
    tail = float(tcfg.get("tail_pad_sec", 0.6))  # 장면 전환 여유(무음)

    scenes = data["scenes"]
    stamp = data.get("stamp") or time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(POSTS_DIR, f"audio_{stamp}")
    os.makedirs(out_dir, exist_ok=True)

    audio = []
    for i, s in enumerate(scenes):
        text = s.get("narration") or " ".join([s.get("heading", "")] + s.get("lines", []))
        text = text.strip() or "재난안전 정보입니다."
        out_path = os.path.join(out_dir, f"{i+1:02d}.mp3")
        asyncio.run(_synth(text, voice, rate, out_path))
        dur = _duration(out_path)
        audio.append({"path": out_path, "duration": round(dur + tail, 3),
                      "speech": round(dur, 3)})
        log(f"TTS {i+1}/{len(scenes)} ({dur:.1f}s): {text[:24]}...")

    data["audio"] = audio
    with open(os.path.join(POSTS_DIR, f"{stamp}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    total = sum(a["duration"] for a in audio)
    log(f"TTS {len(audio)}개 합성 완료(총 {total:.1f}s): {out_dir}")
    return audio


if __name__ == "__main__":
    import glob
    files = sorted(glob.glob(os.path.join(POSTS_DIR, "*.json")))
    if not files:
        raise SystemExit("먼저 generate_script.py 를 실행하세요.")
    with open(files[-1], "r", encoding="utf-8") as f:
        d = json.load(f)
    for a in make_tts(d):
        print(a)
