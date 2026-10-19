"""숏츠 나레이션을 Voicebox(내 목소리 1샘플)로 만든다 — 숏츠 제작 공용 도구(shorts-maker 에이전트·클로드 작업).

작업마다 음성 합성 스크립트를 새로 쓰던 것을 한곳으로 모았다. Voicebox 는 평소 꺼 두므로 이 도구가
`shared/voicebox.sh up/down <작업>` 으로 켜고(응답할 때까지 기다림) 끝나면 끈다(--keep 이면 안 끔).

    python shorts_voice.py --text-file 대본.txt --out voice.wav [--seed 14005] [--check] [--job survey-daily]

  --check   만든 음성을 Voicebox 의 음성 인식(/transcribe)으로 다시 받아 적어 대본과 비교한다
            (고유명사·'곱하기'·'제곱' 같은 낱말이 잘못 읽혔는지 보는 용도. 인식기 오류일 수도 있으니 참고만).
결과는 마지막 줄 JSON: {"status": "ok"|"error", "out", "seconds", "seed", "generation_id", "check": {...}, "message"}
같은 대본이라도 --seed 를 바꾸면 억양이 달라진다. 길이가 20초를 넘으면 대본을 줄여야 한다(빠르게 읽히게 하지 않는다).
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VB = "http://127.0.0.1:17493/"
PROFILE = "9ae4198e-a2c5-4604-9165-7d39adf0143c"       # 내 목소리(1샘플)
SH = os.path.join(ROOT, "shared", "voicebox.sh")


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
    ap = argparse.ArgumentParser(description="숏츠 나레이션(Voicebox 내 목소리)")
    ap.add_argument("--text-file", required=True)
    ap.add_argument("--out", required=True, help="저장할 wav 경로")
    ap.add_argument("--seed", type=int, default=14005)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--job", default="shorts-voice", help="Voicebox 사용 표시 이름")
    ap.add_argument("--keep", action="store_true", help="끝나도 Voicebox 를 끄지 않는다")
    a = ap.parse_args()
    text = " ".join(open(a.text_file, encoding="utf-8").read().split())
    if not text:
        return out("error", message="대본이 비어 있습니다")
    started = subprocess.run(["bash", SH, "up", a.job], capture_output=True, text=True, timeout=240)
    if started.returncode != 0:
        return out("error", message="Voicebox 를 켜지 못했습니다: " + (started.stderr or started.stdout).strip()[-200:])
    try:
        g = generate(text, a.seed)
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "wb") as f:
            f.write(urllib.request.urlopen(VB + "audio/" + g["id"], timeout=120).read())
        sec = seconds_of(a.out)
        res = {"out": os.path.abspath(a.out), "seconds": sec, "seed": a.seed, "generation_id": g["id"]}
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
