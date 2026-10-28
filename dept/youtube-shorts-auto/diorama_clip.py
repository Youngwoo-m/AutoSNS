"""시네마틱 디오라마 영상 클립 한 개(9:16, 무음 mp4)를 학교 AI 게이트웨이 영상 모델로 만든다.
CLAUDE.md 영상 지침: 아이소메트릭 미니어처 디오라마, 그림 안에 글자 없음, 고통스러운 장면 대신 대비·대응·작업 장면.
정지 그림(diorama_image.py)과 같은 미니어처 질감에 시네마틱 카메라 움직임(--move)과 룩(--camera)을 더한다.

    ./.venv/bin/python diorama_clip.py --scene "surveyors setting a GNSS antenna on a hill village" \
        --move dolly_in --camera anamorphic --camera tiltshift --seconds 8 --out c1.mp4

키는 주 키 → 추가 키 순서로 월 할당이 남은 것만 쓴다(구매 크레딧은 쓰지 않음, veo_clips._submit 이 막는다).
요청 번호를 <out>.job.json 에 먼저 남겨, 도중에 멈춰도 같은 명령을 다시 실행하면 이어 받는다.
영상 속 글자는 맥 OCR 로 본다. 결과는 마지막 줄 JSON: {"status","out","seconds","text_found","message"}
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import veo_clips as V  # noqa: E402
from common import load_config  # noqa: E402
from diorama_image import CAMERA, NO_TEXT, OCR, text_in  # noqa: E402

V.MODEL = os.environ.get("VIDEO_MODEL", "google/gemini-omni-flash/v1.1")   # 10/15 게이트웨이에서 Veo 가 빠짐

STYLE = ("Cinematic isometric miniature diorama on a small base, handcrafted scale model with tiny painted figures, "
         "clay and wood textures, strong tilt-shift shallow depth of field, soft warm key light with cool shadows, "
         "subtle film grain, clearly a toy-like model and not a real place, calm and orderly mood, vertical 9:16. "
         "Single continuous shot, no cuts. No text, no letters, no numbers, no logos, every sign and screen blank. Scene: ")
# 한 클립에 움직임은 하나만 (시네마틱 지침)
MOVE = {
    "dolly_in": "Camera movement: slow smooth dolly-in toward the subject.",
    "dolly_out": "Camera movement: slow smooth dolly-out revealing the whole scene.",
    "crane_up": "Camera movement: slow crane-up rising to reveal the whole miniature landscape.",
    "orbit": "Camera movement: slow orbit around the diorama, about 30 degrees.",
    "pan": "Camera movement: slow steady horizontal pan across the scene.",
    "static": "Camera movement: locked-off static camera, only the tiny figures and props move.",
}


def out(status, **kw):
    print(json.dumps({"status": status, **kw}, ensure_ascii=False))
    return 0 if status == "ok" else 1


def frames_text(clip, seconds):
    """영상 중간 몇 장면에서 글자를 찾는다."""
    found = []
    with tempfile.TemporaryDirectory() as td:
        files = []
        for t in (1, seconds / 2, max(seconds - 1, 1)):
            f = os.path.join(td, f"f{len(files)}.png")
            subprocess.run([V._ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.1f}", "-i", clip,
                            "-frames:v", "1", f], check=False)
            if os.path.isfile(f):
                files.append(f)
                found += text_in(f)
    return sorted(set(found))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", required=True, help="장면 설명(영어)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seconds", type=int, default=8, help="4·6·8 (기본 8)")
    ap.add_argument("--move", choices=sorted(MOVE), default="dolly_in", help="카메라 움직임 한 가지")
    ap.add_argument("--camera", action="append", choices=sorted(CAMERA), default=[], help="룩·구도(diorama_image 와 같음)")
    ap.add_argument("--dry-run", action="store_true", help="프롬프트와 예상 크레딧만 보여 준다")
    a = ap.parse_args()
    prompt = STYLE + a.scene + " " + MOVE[a.move] + "".join(" " + CAMERA[c] for c in a.camera)
    need = a.seconds / 4 * 200
    if a.dry_run:
        return out("ok", prompt=prompt, credits=need, message="요청하지 않음")
    g = load_config()["llm_gateway"]
    keys = [g["api_key"]] + list(g.get("extra_keys", []))
    jobs_p = a.out + ".job.json"
    job = json.load(open(jobs_p)) if os.path.exists(jobs_p) else None
    try:
        if not job:
            errs = []
            for ki, key in enumerate(keys):
                op, err = V._submit(key, prompt, a.seconds)
                if op:
                    job = {"op": op, "key": ki}
                    json.dump(job, open(jobs_p, "w"))
                    break
                errs.append(f"키{ki}: {err}")
            if not job:
                return out("error", message="모든 키의 월 할당 부족 — " + " / ".join(errs))
        key = keys[job["key"]]
        t0 = time.time()
        while True:
            st, b = V._req(key, "GET", f"{V.BASE}/video/generation/{job['op']}/?model={V.MODEL}")
            d = json.loads(b) if st < 300 else {}
            if d.get("status") in ("completed", "failed"):
                break
            if time.time() - t0 > 900:
                return out("error", message=f"15분 넘게 처리 중 — 같은 명령을 다시 실행하면 이어 받음 ({jobs_p})")
            time.sleep(10)
        if d["status"] != "completed":
            os.remove(jobs_p)
            return out("error", message=f"생성 실패(크레딧 환불): {str(d.get('error'))[:200]}")
        V._finish(key, t0, job["op"], a.out)
        os.remove(jobs_p)
        found = frames_text(a.out, a.seconds)
    except Exception as e:  # noqa: BLE001
        return out("error", message=f"{type(e).__name__}: {str(e)[:200]}")
    return out("ok", out=a.out, seconds=a.seconds, credits=need, text_found=found,
               message="영상 속 글자가 보입니다 — 장면 설명을 바꿔 다시 만들 것" if found else "")


if __name__ == "__main__":
    sys.exit(main())
