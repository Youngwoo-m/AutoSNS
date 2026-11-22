"""영상용 아이소메트릭 미니어처 디오라마 그림 한 장(9:16)을 학교 AI 게이트웨이 이미지 모델로 만든다.
CLAUDE.md 영상 지침(2026-10-15): 영상마다 디오라마 2~3장, 그림 안에 글자 없음, 고통스러운 장면 대신 대비·대응·작업 장면,
실제 사진처럼 보이지 않게 미니어처·틸트시프트 질감을 분명히.
2026-11-19: --form 으로 장면형(사람·장소·범위)·소품형(장비·도구·원리)을 고르고(기본 auto) 실제 재료·자연광으로 사실감 있게(diorama_forms.py).

    ./.venv/bin/python diorama_image.py --scene "surveyors setting a GNSS antenna on a benchmark on a hill village" --out d1.png

--camera 로 카메라 기법(establishing·insert·rack·frame·dutch·anamorphic·tiltshift)을 덧붙인다.
--scene 에는 장면만 영어로 적는다(스타일·글자 금지 문구는 이 도구가 붙인다).
키는 주 키 → 추가 키 순서로, 월 할당이 (이미지값 + 예비 150) 넘게 남은 키만 쓴다. 구매 크레딧은 쓰지 않는다.
그림에 글자가 보이면(맥 OCR) 글자 금지 문구를 세게 해서 한 번 다시 만들고 글자가 적은 쪽을 남긴다.
결과는 마지막 줄 JSON: {"status": "ok"|"error", "out", "credits", "text_found": [...], "message"}
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

MODEL, COST, RESERVE = "gemini-2.5-flash-image", 39, 150
OCR = "E:/MacMini/devAPP/AutoSNS/channels/disaster-shorts/tools/ocr"
STYLE_T = ("Isometric miniature diorama on a small square base, handcrafted model look with tiny painted figures, "
         "soft studio lighting, strong tilt-shift shallow depth of field, clay and wood textures, "
         "clearly a toy-like scale model and not a real photograph, calm and orderly mood, {ASPECT} composition. "
         "No text, no letters, no numbers, no logos anywhere. Scene: ")
STYLE = STYLE_T.replace("{ASPECT}", "vertical 9:16")
# 2026-11-19: 기본은 --form auto(장면형·소품형 중 고름, 사실감 있게). 예전 점토·장난감 질감은 --form classic 으로만.
import diorama_forms as F  # noqa: E402
# CLAUDE.md 카메라 기법(2026-10-26): --camera 로 골라 프롬프트에 한 줄씩 붙인다. 더치 앵글은 대응·구조 장면에만.
CAMERA = {
    "establishing": "Establishing shot: start from a wide foreground view of the whole scene.",
    "insert": "Insert shot: close-up on a small prop as the subject.",
    "rack": "Rack focus: focus shifts from the foreground subject to the subject behind it.",
    "frame": "Frame within a frame: the scene is seen through an arch, door or window.",
    "dutch": "Dutch angle: tilted camera for tension (use only for response or rescue scenes).",
    "anamorphic": "Anamorphic look: wide frame, horizontal lens flare, oval bokeh.",
    "tiltshift": "Tilt-shift: blur the top and bottom so it looks like a miniature.",
}
NO_TEXT = (" Absolutely no writing anywhere: every sign, screen, label, banner and instrument display is completely blank.")


def out(status, **kw):
    print(json.dumps({"status": status, **kw}, ensure_ascii=False))
    return 0 if status == "ok" else 1


def gen(prompt, aspect="9:16"):
    import veo_clips as V
    from common import load_config
    g = load_config()["llm_gateway"]
    for ki, k in enumerate([g["api_key"]] + list(g.get("extra_keys", []))):
        if V.monthly_remaining(k) < COST + RESERVE:
            continue
        req = urllib.request.Request(
            V.BASE + "/images/generate/", method="POST",
            data=json.dumps({"model": MODEL, "prompt": prompt, "aspect_ratio": aspect, "number_of_images": 1}).encode(),
            headers={"Authorization": f"Bearer {k}", "x-api-key": k, "Content-Type": "application/json",
                     "User-Agent": "smuds-autosns/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=240) as f:
                d = json.loads(f.read())
        except urllib.error.HTTPError as e:
            print(f"키{ki} 실패 {e.code}", file=sys.stderr)
            continue
        u = d["data"][0].get("url") or ""
        img = base64.b64decode(u.split(",", 1)[1]) if u.startswith("data:") else urllib.request.urlopen(u).read()
        return img, d.get("credits_charged", COST)
    raise RuntimeError("모든 키의 월 할당이 부족합니다(구매 크레딧은 쓰지 않음)")


def text_in(path):
    # ocr 은 맥 전용 실행 파일이다. 윈도우에서는 WinError 193 으로 그림 생성 전체가 실패하므로
    # (2026-11-11) 맥이 아니거나 실행이 안 되면 글자 검사만 건너뛰고 그림은 그대로 쓴다.
    if sys.platform != "darwin" or not os.path.exists(OCR):
        return []
    try:
        r = subprocess.run([OCR, path], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return []
    return [p[1] for p in (ln.split("\t") for ln in r.stdout.splitlines())
            if len(p) == 3 and len(re.findall(r"[가-힣A-Za-z0-9]", p[1])) >= 2 and float(p[2]) >= 0.3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", required=True, help="장면 설명(영어)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--aspect", default="9:16", help="9:16(기본)·1:1·16:9 등 — 배너 배경은 1:1/16:9")
    ap.add_argument("--camera", action="append", choices=sorted(CAMERA), default=[],
                    help="카메라 기법(여러 번 가능): " + ", ".join(sorted(CAMERA)))
    ap.add_argument("--form", default="auto", choices=["auto", "scene", "prop", "classic"],
                    help="장면형(scene: 사람·장소·범위)·소품형(prop: 장비·도구·원리) — auto 는 장면 설명으로 고름, classic 은 예전 장난감 질감")
    a = ap.parse_args()
    try:
        asp = a.aspect + " (centered subject, calm empty space around)" if a.aspect != "9:16" else "vertical 9:16"
        scene = a.scene + "".join(" " + CAMERA[c] for c in a.camera)
        if a.form == "classic":
            form, style = "classic", STYLE_T.replace("{ASPECT}", asp)
            prompt = style + scene
        else:   # 장면 설명을 앞에 두면 모형이 장면을 더 따른다
            form = F.pick(a.scene, a.form)
            prompt = "Scene: " + scene + " " + F.style(form, asp)
        print(f"디오라마 형식: {F.LABEL.get(form, form)}", file=sys.stderr)
        # 2026-11-23: 월 할당이 남았으면 게이트웨이, 없으면 로컬 FLUX(12/1 할당이 다시 생기면 저절로 게이트웨이)
        import diorama_backend as B
        ki, why = B.key_for(COST, RESERVE)
        print(f"그림 생성 경로: {why}", file=sys.stderr)
        if ki is None:
            B.local_image(prompt, a.out, a.aspect)
            return out("ok", out=a.out, credits=0, text_found=text_in(a.out), form=form, backend="local-flux",
                       message="로컬 FLUX 로 만든 AI 생성 그림 — 게이트웨이 월 할당 부족")
        img, cr = gen(prompt, a.aspect)
        open(a.out, "wb").write(img)
        found = text_in(a.out)
        if found:
            alt = a.out + ".retry.png"
            img2, cr2 = gen(prompt + NO_TEXT, a.aspect)
            cr += cr2
            open(alt, "wb").write(img2)
            left = text_in(alt)
            if len(left) < len(found):
                os.replace(alt, a.out)
                found = left
            else:
                os.remove(alt)
    except Exception as e:  # noqa: BLE001
        return out("error", message=f"{type(e).__name__}: {str(e)[:200]}")
    return out("ok", out=a.out, credits=cr, text_found=found, form=form,
               message="그림 속 글자가 남았습니다 — 다른 장면 설명으로 다시 만들 것" if found else "")


if __name__ == "__main__":
    sys.exit(main())
