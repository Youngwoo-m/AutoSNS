"""Veo 대신 3D 사실 이미지 1장 + 천천히 확대·이동(켄 번스)으로 장면 영상을 만든다(크레딧 절약판).

  .venv/bin/python image_scene.py 2026-10-23_산행안전사고 1 [--shot 0]
결과 파일 이름은 veo_scene.py 와 같아서(scene{n}_3d_real_{초}s[_shot{k}].mp4) assemble.py 를 그대로 쓴다.
이미지: 게이트웨이 gemini-2.5-flash-image(9:16, 1장 39크레딧). 글자가 보이면(맥 OCR) 한 번 다시 만든다.
키: 주 키 → 추가 키 순서로, 남은 월 할당이 (이미지값 + 예비 150) 이상인 키를 쓴다. 구매 크레딧은 쓰지 않는다.
"""
import argparse, base64, json, os, re, subprocess, sys, tempfile, urllib.error, urllib.request

AUTOSNS = "/Volumes/USB256/devAPP/AutoSNS/channels/youtube-shorts-auto"
sys.path.insert(0, AUTOSNS); os.chdir(AUTOSNS)
import veo_clips as V
from common import load_config

ROOT = "/Volumes/USB256/devAPP/AutoSNS/channels/disaster-shorts"
MODEL, COST, RESERVE = "gemini-2.5-flash-image", 39, 150
NO_TEXT = (" Absolutely no writing anywhere: every sign, signboard, banner, screen, label and license plate is "
           "completely blank; avoid storefronts and building facades with names.")

ap = argparse.ArgumentParser(); ap.add_argument("ep"); ap.add_argument("scene", type=int)
ap.add_argument("--shot", type=int); a = ap.parse_args()
sc = json.load(open(f"{ROOT}/{a.ep}/script.json", encoding="utf-8"))
s = next(x for x in sc["scenes"] if x["id"] == a.scene)
style = sc.get("style", "3d_real")
if a.shot is not None:
    sh = s["shots"][a.shot]; secs = sh.get("seconds", 4); body = sh["prompt"]; cut = sh.get("cutaway", False); suffix = f"_shot{a.shot}"
else:
    secs = sc.get("clip_seconds", 8); body = s["video_prompt"][style]; cut = s.get("cutaway"); suffix = ""
prefix = (sc["style_prefix"][style].replace("cinematic aerial footage", "cinematic aerial photograph")
          .replace("single continuous shot, ", "").replace(" single continuous shot,", ""))
if a.scene != 1 or a.shot is not None:      # 정지 이미지는 카메라가 안 움직여 사람이 작으면 행동이 안 보인다 → 사람 장면은 눈높이 근접
    prefix = (prefix.replace("cinematic aerial photograph", "cinematic eye-level photograph")
              .replace("shot on a high-end drone camera", "shot on a high-end camera at eye level, the person fills a large part of the frame"))
if sc.get("prompt_order") == "scene_first":   # 새 대본: 장면 설명 → 카메라 → 단면 → 스타일
    style_txt = sc["style_prefix"][style].replace("documentary footage", "documentary photograph").replace("single continuous shot, ", "").replace("filmed on location", "taken on location").replace(" moving at real-time speed", "")
    cam_key = ((s["shots"][a.shot] if a.shot is not None else s).get("camera") or s.get("camera")
               or ("aerial" if a.scene == 1 and a.shot is None else "eye"))
    cam = (sc.get("camera_text_image") or sc.get("camera_text") or {}).get(cam_key, "")
    prompt = body + cam + (sc.get("cutaway_text", "") if cut else "") + " " + style_txt
else:
    prompt = prefix + (sc.get("cutaway_text", "") if cut else "") + " " + body
out_dir = f"{ROOT}/{a.ep}/clips"; os.makedirs(out_dir, exist_ok=True)
out = f"{out_dir}/scene{a.scene}_{style}_{secs}s{suffix}.mp4"
png = out.replace(".mp4", ".png")

g = load_config()["llm_gateway"]
keys = [g["api_key"]] + list(g.get("extra_keys", []))


def _gen(p):
    for ki, k in enumerate(keys):
        if V.monthly_remaining(k) < COST + RESERVE:
            continue
        r = urllib.request.Request(V.BASE + "/images/generate/", method="POST",
                                   data=json.dumps({"model": MODEL, "prompt": p, "aspect_ratio": "9:16",
                                                    "number_of_images": 1}).encode(),
                                   headers={"Authorization": f"Bearer {k}", "x-api-key": k,
                                            "Content-Type": "application/json", "User-Agent": "smuds-autosns/1.0"})
        try:
            with urllib.request.urlopen(r, timeout=240) as f:
                d = json.loads(f.read())
        except urllib.error.HTTPError as e:
            print(f"키{ki} 실패 {e.code}: {e.read()[:150]}"); continue
        u = d["data"][0].get("url") or ""
        img = base64.b64decode(u.split(",", 1)[1]) if u.startswith("data:") else urllib.request.urlopen(u).read()
        print(f"이미지: {'주 키' if ki == 0 else f'추가 키{ki}'} ({d.get('credits_charged')}크레딧)")
        return img
    sys.exit("모든 키의 월 할당 부족(이미지)")


def _text(path):
    r = subprocess.run([f"{ROOT}/tools/ocr", path], capture_output=True, text=True)
    return [p[1] for p in (l.split("\t") for l in r.stdout.splitlines())
            if len(p) == 3 and len(re.findall(r"[가-힣A-Za-z]", p[1])) >= 2 and float(p[2]) >= 0.3]


if not os.path.exists(png):
    open(png, "wb").write(_gen(prompt))
    found = _text(png)
    if found:
        print("이미지 속 글자 발견 → 한 번 다시 만듭니다:", found[:5])
        alt = png.replace(".png", ".retry.png"); open(alt, "wb").write(_gen(prompt + NO_TEXT))
        left = _text(alt); print("다시 만든 이미지 글자:", left[:5] or "없음")
        if len(left) < len(found):
            os.replace(alt, png)

# 켄 번스: 크게 키운 뒤 천천히 확대(1.00→1.12)하며 가운데로 살짝 이동 → 720x1280 24fps(Veo 클립과 같은 규격)
frames = int(secs * 24)
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-loop", "1", "-i", png,
                "-vf", (f"scale=1440:2560:flags=lanczos,zoompan=z='1+0.12*on/{frames}':"
                        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)+ih*0.02*on/{frames}':d={frames}:s=720x1280:fps=24,"
                        "format=yuv420p"),
                "-frames:v", str(frames), "-c:v", "libx264", "-crf", "18", out], check=True)
print("완료", out)
