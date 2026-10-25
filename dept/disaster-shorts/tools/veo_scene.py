"""script.json 의 장면을 세명대 게이트웨이 Veo 로 만든다(AutoSNS veo_clips 재사용).

  python3 veo_scene.py 2026-10-13_산사태 1 [--seconds 6]
길이: 대본의 clip_seconds(없으면 8). 새 편은 8초(2026-10-03 추가 키 3개로 여유 → 6초에서 8초로 되돌림).
키: 주 키의 월 할당이 모자라면 추가 계정 키(llm_gateway.extra_keys)로 넘어간다 — 구매 크레딧은 쓰지 않는다.
요청 번호와 쓴 키 순번을 <클립>.job.json 에 먼저 남겨, 도중에 멈춰도 다시 실행하면 이어 받는다.
"""
import argparse, json, os, sys, time
AUTOSNS = "/Volumes/USB256/devAPP/AutoSNS/channels/youtube-shorts-auto"
sys.path.insert(0, AUTOSNS); os.chdir(AUTOSNS)
import veo_clips as V
V.MODEL = os.environ.get("VIDEO_MODEL", "google/gemini-omni-flash/v1.1")   # 10/15 게이트웨이에서 Veo 가 빠짐 → 대체
from common import load_config

ROOT = "/Volumes/USB256/devAPP/AutoSNS/channels/disaster-shorts"
ap = argparse.ArgumentParser(); ap.add_argument("ep"); ap.add_argument("scene", type=int)
ap.add_argument("--seconds", type=int)
ap.add_argument("--style", help="기본: script.json 의 style")
ap.add_argument("--shot", type=int, help="장면을 여러 컷으로 나눈 경우 컷 번호(0부터) — scene['shots'][k]"); a = ap.parse_args()
sc = json.load(open(f"{ROOT}/{a.ep}/script.json", encoding="utf-8"))
s = next(x for x in sc["scenes"] if x["id"] == a.scene)
style = a.style or sc.get("style", "3d_real")
if a.shot is not None:                      # 한 장면을 짧은 컷 여러 개로(예: 대피 장면 = 위험 → 대피소 도착)
    sh = s["shots"][a.shot]
    secs = a.seconds or sh.get("seconds", 4); body = sh["prompt"]; cut = sh.get("cutaway", False); suffix = f"_shot{a.shot}"
else:
    secs = a.seconds or sc.get("clip_seconds", 8); body = s["video_prompt"][style]; cut = s.get("cutaway"); suffix = ""
DIORAMA_STYLE = (" Style: photorealistic close-up footage of a real handcrafted physical scale-model diorama standing on a wooden "
                 "workbench in a bright workshop, real materials (soil, moss, rocks, water, painted figurines), macro lens with shallow "
                 "depth of field, natural studio light, single continuous shot, no text, no letters, no numbers, no logos, every sign blank.")
cam_src = sh if a.shot is not None else s
cam = (sc.get("camera_text") or {}).get(cam_src.get("camera") or s.get("camera") or "", "")
if sc.get("prompt_order") == "scene_first":   # 장면 설명을 맨 앞에(영상 AI 는 앞쪽 문장을 더 따른다, 10/10 점검)
    prompt = body + cam + (sc.get("cutaway_text", "") if cut else "") + " " + sc["style_prefix"][style]
else:                                          # 예전 대본은 예전 순서 그대로
    prompt = sc["style_prefix"][style] + (sc.get("cutaway_text", "") if cut else "") + " " + body
if a.shot is None and s.get("media") == "diorama":   # 실사 디오라마 장면(10/15 사용자 결정): 축소 모형 스타일로
    prompt = s["diorama_prompt"] + DIORAMA_STYLE; suffix = "_diorama"
g = load_config()["llm_gateway"]
keys = [g["api_key"]] + list(g.get("extra_keys", []))
out_dir = f"{ROOT}/{a.ep}/clips"; os.makedirs(out_dir, exist_ok=True)
out = f"{out_dir}/scene{a.scene}_{style}_{secs}s{suffix}.mp4"
jobs_p = out + ".job.json"   # 장면마다 따로 — 동시에 돌려도 서로 덮어쓰지 않게
jobs = json.load(open(jobs_p)) if os.path.exists(jobs_p) else {}
name = os.path.basename(out)
if name not in jobs:
    errs = []
    for ki, key in enumerate(keys):
        op, err = V._submit(key, prompt, secs)        # 월 할당이 MIN_MONTHLY 아래로 내려가면 거절된다
        if op:
            jobs[name] = {"op": op, "key": ki}; json.dump(jobs, open(jobs_p, "w"), indent=1)
            print(f"요청: {'주 키' if ki == 0 else f'추가 키{ki}'} ({secs}초)")
            break
        errs.append(f"키{ki}: {err}")
    else:
        sys.exit("모든 키의 월 할당 부족 — " + " / ".join(errs))
def _resubmit():
    for ki, key in enumerate(keys):
        op, err = V._submit(key, prompt, secs)
        if op:
            jobs[name] = {"op": op, "key": ki}; json.dump(jobs, open(jobs_p, "w"), indent=1)
            print(f"다시 요청: {'주 키' if ki == 0 else f'추가 키{ki}'} ({secs}초)")
            return
    sys.exit("다시 요청 실패 — 모든 키의 월 할당 부족")


for attempt in range(3):                    # Veo 서버 오류(code 13 등)로 실패하면 새로 요청(실패분은 환불)
    j = jobs[name]
    op, key = (j, keys[0]) if isinstance(j, str) else (j["op"], keys[j["key"]])
    t0 = time.time()
    while True:
        st, b = V._req(key, "GET", f"{V.BASE}/video/generation/{op}/?model={V.MODEL}")
        d = json.loads(b) if st < 300 else {}
        if d.get("status") in ("completed", "failed"): break
        time.sleep(15)
    if d.get("status") == "completed":
        break
    print(f"실패(크레딧 환불) — {str(d.get('error'))[:120]}")
    if attempt == 2:
        sys.exit("Veo 가 세 번 실패했습니다")
    time.sleep(30); _resubmit()
V._finish(key, t0, op, out)
print("완료", out, f"{time.time()-t0:.0f}s", "이 키 월 할당 남음:", round(V.monthly_remaining(key)))


def text_in(clip):
    """영상 속에 AI 가 그린 글자(깨진 한글 간판 등)가 있는지 맥 내장 OCR 로 본다 → 찾은 글자 목록."""
    import re, subprocess, tempfile
    here = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else ROOT + "/tools"
    ocr = os.path.join(ROOT, "tools", "ocr")
    found = []
    with tempfile.TemporaryDirectory() as td:
        for t in (1, 3, 5, 7):
            f = os.path.join(td, f"f{t}.png")
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(t), "-i", clip,
                            "-frames:v", "1", f], check=False)
        r = subprocess.run([ocr] + [os.path.join(td, f"f{t}.png") for t in (1, 3, 5, 7)],
                           capture_output=True, text=True)
        for line in r.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) == 3 and len(re.findall(r"[가-힣A-Za-z]", parts[1])) >= 2 and float(parts[2]) >= 0.3:
                found.append(parts[1])
    return found


NO_TEXT = (" Absolutely no writing anywhere: every sign, signboard, banner, screen, label and license plate is "
           "completely blank; avoid storefronts and building facades with names.")
found = text_in(out)
if found and not jobs.get("retried"):
    print("영상 속 글자 발견 → 한 번 다시 만듭니다:", found[:5])
    os.replace(out, out.replace(".mp4", ".had_text.mp4"))
    op2 = None; errs2 = []
    for ki, key2 in enumerate(keys):
        op2, err = V._submit(key2, prompt + NO_TEXT, secs)
        if not op2:
            errs2.append(f"키{ki}: {err}")
        if op2:
            jobs[name] = {"op": op2, "key": ki}; jobs["retried"] = True
            json.dump(jobs, open(jobs_p, "w"), indent=1); break
    if not op2:
        print("다시 만들기 요청 실패:", " / ".join(errs2)[:600])
        os.replace(out.replace(".mp4", ".had_text.mp4"), out)
    if op2:
        t0 = time.time()
        while True:
            st, b = V._req(key2, "GET", f"{V.BASE}/video/generation/{op2}/?model={V.MODEL}")
            d = json.loads(b) if st < 300 else {}
            if d.get("status") in ("completed", "failed"): break
            time.sleep(15)
        if d.get("status") == "completed":
            V._finish(key2, t0, op2, out)
            left = text_in(out)
            print("다시 만든 영상 글자:", left[:5] or "없음")
            if left and len(left) >= len(found):              # 더 나아지지 않았으면 처음 것을 쓴다
                os.replace(out.replace(".mp4", ".had_text.mp4"), out)
        else:
            os.replace(out.replace(".mp4", ".had_text.mp4"), out); print("다시 만들기 실패 — 처음 영상을 씁니다", d)
elif found:
    print("⚠ 다시 만든 뒤에도 글자 발견:", found[:5])
