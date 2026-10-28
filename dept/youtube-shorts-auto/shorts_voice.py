"""숏츠 나레이션을 만든다 — 숏츠 제작 공용 도구(shorts-maker 에이전트·클로드 작업).

음성 엔진 두 가지(2026-10-22 edge 로 바꿨다가 2026-10-28 사용자 지시로 기본을 Voicebox 로 되돌렸다):
  edge       edge-tts 'ko-KR-InJoonNeural'. 인터넷만 있으면 몇 초, 맥 부하 없음. 시드·받아 적기 검사 없음.
  voicebox   Voicebox 내 목소리 1샘플(기본, 2026-10-28 복귀). 과부하 시 DEFAULT_BACKEND 를 "edge" 로 바꾸거나
             `--backend edge` / 환경변수 SHORTS_VOICE_BACKEND=edge 로 쓴다. 평소 꺼 두므로 이 도구가
             `shared/voicebox.sh up/down <작업>` 으로 켜고(응답할 때까지 기다림) 끝나면 끈다(--keep 이면 안 끔).

    python shorts_voice.py --text-file 대본.txt --out voice.wav [--backend edge|voicebox] [--seed 14005] [--check] [--job survey-daily]

  --check   (voicebox 만) 만든 음성을 Voicebox 의 음성 인식(/transcribe)으로 다시 받아 적어 대본과 비교한다
            (고유명사·'곱하기'·'제곱' 같은 낱말이 잘못 읽혔는지 보는 용도. 인식기 오류일 수도 있으니 참고만).
결과는 마지막 줄 JSON: {"status": "ok"|"error", "out", "seconds", "backend", "voice", "voice_label", "seed", "generation_id", "check": {...}, "message"}
`voice_label` 은 화면 고지·설명에 그대로 넣는 음성 고지 문구다(edge: 'AI 합성 음성(TTS)', voicebox: 'AI 합성 음성(본인 목소리 복제)').
voicebox 에서는 같은 대본이라도 --seed 를 바꾸면 억양이 달라진다. 길이가 20초를 넘으면 대본을 줄여야 한다(빠르게 읽히게 하지 않는다).
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
VB = "http://127.0.0.1:17493/"
PROFILE = "9ae4198e-a2c5-4604-9165-7d39adf0143c"       # 내 목소리(1샘플)
SH = os.path.join(ROOT, "shared", "voicebox.sh")

# 기본 음성 엔진. 2026-10-28 사용자 지시로 Voicebox 로 되돌렸다. 맥이 과부하되면 이 한 줄을 "edge" 로 바꾼다.
DEFAULT_BACKEND = "voicebox"
EDGE_VOICE = "ko-KR-InJoonNeural"
EDGE_RATE = "+10%"   # +0% 는 Voicebox 보다 느려 같은 대본이 25초(공백 제외 108자)였다 — +10% 는 약 23초
VOICE_LABEL = {"edge": "AI 합성 음성(TTS)", "voicebox": "AI 합성 음성(본인 목소리 복제)"}


def out(status, **kw):
    print(json.dumps({"status": status, **kw}, ensure_ascii=False))
    return 0 if status == "ok" else 1


def _json(req, timeout=120):
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def seconds_of(path):
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    try:
        return round(float(p.stdout.strip()), 3)
    except ValueError:
        return None


def edge_generate(text, out_wav, voice=EDGE_VOICE, rate=EDGE_RATE):
    """edge-tts 로 mp3 를 받아 wav 로 바꿔 저장한다(Voicebox 결과와 같은 wav 형식)."""
    import edge_tts

    async def _run(path):
        kw = {"voice": voice}
        if rate and rate != "+0%":
            kw["rate"] = rate
        await edge_tts.Communicate(text, **kw).save(path)

    with tempfile.TemporaryDirectory() as d:
        mp3 = os.path.join(d, "v.mp3")
        asyncio.run(_run(mp3))
        if not os.path.isfile(mp3) or os.path.getsize(mp3) < 1000:
            raise RuntimeError("edge-tts 가 음성을 만들지 못했습니다(인터넷 연결 확인)")
        os.makedirs(os.path.dirname(os.path.abspath(out_wav)), exist_ok=True)
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", mp3, "-ar", "44100", "-ac", "1", out_wav],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("wav 변환 실패: " + r.stderr.strip()[-200:])


def generate(text, seed):
    body = dict(profile_id=PROFILE, text=text, language="ko", engine="qwen", model_size="0.6B",
                seed=seed, normalize=True, max_chunk_chars=250)
    g = _json(urllib.request.Request(VB + "generate", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"}))
    t0 = time.time()
    while g.get("status") != "completed":
        if g.get("status") in ("failed", "cancelled"):
            raise RuntimeError("음성 합성 실패: " + json.dumps(g, ensure_ascii=False)[:300])
        if time.time() - t0 > 600:
            raise RuntimeError("음성 합성 10분 초과")
        time.sleep(3)
        g = _json(urllib.request.Request(VB + "history/" + g["id"]), 40)
    return g


def transcribe(path):
    """Voicebox /transcribe(multipart)로 받아 적는다."""
    boundary = "----ax" + uuid.uuid4().hex
    data = open(path, "rb").read()
    parts = [f"--{boundary}\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\nko\r\n".encode(),
             f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{os.path.basename(path)}\"\r\n"
             "Content-Type: audio/wav\r\n\r\n".encode(), data, f"\r\n--{boundary}--\r\n".encode()]
    req = urllib.request.Request(VB + "transcribe", data=b"".join(parts),
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    return _json(req, 300)


def main():
    ap = argparse.ArgumentParser(description="숏츠 나레이션(edge-tts 기본 / Voicebox 내 목소리)")
    ap.add_argument("--backend", choices=["edge", "voicebox"],
                    default=os.environ.get("SHORTS_VOICE_BACKEND", DEFAULT_BACKEND))
    ap.add_argument("--text-file", required=True)
    ap.add_argument("--out", required=True, help="저장할 wav 경로")
    ap.add_argument("--seed", type=int, default=14005, help="(voicebox 만)")
    ap.add_argument("--voice", default=EDGE_VOICE, help="(edge 만) edge-tts 음성 이름")
    ap.add_argument("--rate", default=EDGE_RATE, help="(edge 만) 속도, 예 +0%% / +6%%")
    ap.add_argument("--check", action="store_true", help="(voicebox 만) 받아 적기 검사")
    ap.add_argument("--job", default="shorts-voice", help="Voicebox 사용 표시 이름")
    ap.add_argument("--keep", action="store_true", help="끝나도 Voicebox 를 끄지 않는다")
    a = ap.parse_args()
    text = " ".join(open(a.text_file, encoding="utf-8").read().split())
    if not text:
        return out("error", message="대본이 비어 있습니다")
    if a.backend == "edge":
        try:
            edge_generate(text, a.out, a.voice, a.rate)
            sec = seconds_of(a.out)
            res = {"out": os.path.abspath(a.out), "seconds": sec, "backend": "edge", "voice": a.voice,
                   "voice_label": VOICE_LABEL["edge"]}
            if a.check:
                res["check"] = {"note": "edge-tts 는 받아 적기 검사를 하지 않는다(숫자·고유명사는 화면 자막과 대본 표기를 직접 확인)."}
            if sec and sec > 20.0:
                return out("error", message=f"음성이 {sec}초로 20초를 넘습니다 — 대본을 줄이세요", **res)
            return out("ok", **res)
        except Exception as e:
            return out("error", message=f"{type(e).__name__}: {str(e)[:300]}")
    started = subprocess.run(["bash", SH, "up", a.job], capture_output=True, text=True, timeout=240)
    if started.returncode != 0:
        return out("error", message="Voicebox 를 켜지 못했습니다: " + (started.stderr or started.stdout).strip()[-200:])
    try:
        g = generate(text, a.seed)
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "wb") as f:
            f.write(urllib.request.urlopen(VB + "audio/" + g["id"], timeout=120).read())
        sec = seconds_of(a.out)
        res = {"out": os.path.abspath(a.out), "seconds": sec, "backend": "voicebox", "voice_label": VOICE_LABEL["voicebox"],
               "seed": a.seed, "generation_id": g["id"]}
        if a.check:
            t = transcribe(a.out)
            res["check"] = {"heard": (t.get("text") or "").strip(), "script": text,
                            "note": "인식기가 잘못 받아 적었을 수도 있다 — 다른 낱말로 읽혔다면 대본의 표기(한글 풀어쓰기)를 바꿔 seed 를 달리해 다시"}
        if sec and sec > 20.0:
            return out("error", message=f"음성이 {sec}초로 20초를 넘습니다 — 대본을 줄이세요", **res)
        return out("ok", **res)
    except Exception as e:
        return out("error", message=f"{type(e).__name__}: {str(e)[:300]}")
    finally:
        if not a.keep:
            subprocess.run(["bash", SH, "down", a.job], capture_output=True, text=True, timeout=120)


if __name__ == "__main__":
    sys.exit(main())
