"""script.json 의 장면을 로컬 ComfyUI + Wan 2.2 TI2V 5B 로 만든다(무료, 게이트웨이 크레딧이 없을 때).

  python wan_scene.py 2026-11-24_화재 1 [--shot 0] [--seconds 8] [--smoke]
결과 파일 이름은 veo_scene.py 와 같아서(scene{n}_3d_real_{초}s[_shot{k}|_diorama].mp4) assemble.py 를 그대로 쓴다.
프롬프트는 veo_scene.py 와 같은 규칙(장면형·소품형, 카메라 문구, 디오라마 장면)으로 만든다.
설정은 2026-11-09 검증값(448x800, 24fps, fp8 로드, shift 8, uni_pc/simple, CFG 5, 20단계, 타일 VAE)을 쓴다.
생성 해상도 448x800 은 조립(assemble.py)에서 1080x1920 으로 늘린다. AI 생성 영상이며 실제 촬영이 아니다.
끝나면 ComfyUI 메모리를 비워 Voicebox 등 다른 작업이 그래픽카드를 쓸 수 있게 한다.
"""
import argparse, json, os, random, subprocess, sys, time, urllib.error, urllib.parse, urllib.request

_AXROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))).replace("\\", "/")
ROOT = _AXROOT + "/channels/disaster-shorts"
sys.path.insert(0, _AXROOT + "/channels/youtube-shorts-auto")
import diorama_forms as F

COMFY = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")
STARTER = r"E:\Persnal_App\Seller\geopanda-data\tools\start_comfyui_local.py"
STARTER_PY = r"C:\AI\comfyui-env\Scripts\python.exe"
W, H, FPS = 448, 800, 24
NEGATIVE = ("text, letters, words, numbers, subtitles, captions, watermark, logo, signage text, cartoon, toy, clay, "
            "plastic doll, video game CG, deformed hands, extra fingers, extra limbs, distorted face, melting objects, "
            "flicker, strobe, abrupt cut, rapid camera shake, blurry, low quality, oversaturated, gore, injured people")
DIORAMA_STYLE = (" Style: photorealistic close-up footage of a real handcrafted physical scale-model diorama standing on a wooden "
                 "workbench in a bright workshop, real materials (soil, moss, rocks, water, painted figurines), macro lens with shallow "
                 "depth of field, natural studio light, single continuous shot, no text, no letters, no numbers, no logos, every sign blank.")


def build_prompt(sc, s, shot, seconds, style):
    """veo_scene.py 와 같은 규칙으로 (프롬프트, 초, 결과 파일 이름 꼬리)를 만든다."""
    sc = json.loads(json.dumps(sc))           # 원본 dict 를 바꾸지 않게
    form = "prop" if shot is None and s.get("form") == "prop" else "scene"
    if form == "prop":
        sc["style_prefix"][style] = sc.get("style_prefix_prop") or F.DISASTER_PROP
    elif sc["style_prefix"].get(style, "").startswith(F.OLD_DISASTER_PREFIX):
        sc["style_prefix"][style] = F.DISASTER_SCENE
    if shot is not None:
        sh = s["shots"][shot]
        secs = seconds or sh.get("seconds", 4); body = sh["prompt"]; cut = sh.get("cutaway", False); suffix = f"_shot{shot}"
    else:
        secs = seconds or sc.get("clip_seconds", 8); body = s["video_prompt"][style]; cut = s.get("cutaway"); suffix = ""
    cam_src = s["shots"][shot] if shot is not None else s
    cam = "" if form == "prop" else (sc.get("camera_text") or {}).get(cam_src.get("camera") or s.get("camera") or "", "")
    if sc.get("prompt_order") == "scene_first":
        prompt = body + cam + (sc.get("cutaway_text", "") if cut else "") + " " + sc["style_prefix"][style]
    else:
        prompt = sc["style_prefix"][style] + (sc.get("cutaway_text", "") if cut else "") + " " + body
    if shot is None and s.get("media") == "diorama":
        prompt = s["diorama_prompt"] + DIORAMA_STYLE; suffix = "_diorama"
    return prompt + " Single continuous shot, calm steady camera, no text anywhere.", secs, suffix


def _get(path, timeout=10):
    with urllib.request.urlopen(COMFY + path, timeout=timeout) as r:
        return json.load(r)


def _post(path, body, timeout=60):
    req = urllib.request.Request(COMFY + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return json.loads(raw) if raw.strip() else {}


def ensure_comfy():
    try:
        _get("/system_stats", 3); return
    except OSError:
        pass
    print("ComfyUI 실행")
    subprocess.run([STARTER_PY, STARTER], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(90):
        try:
            _get("/system_stats", 3); return
        except OSError:
            time.sleep(4)
    raise SystemExit("ComfyUI 서버가 뜨지 않습니다")


def free_vram():
    try:
        _post("/free", {"unload_models": True, "free_memory": True}, 30)
    except Exception as e:  # noqa: BLE001
        print("메모리 비우기 실패(무시):", type(e).__name__)


def graph(prompt, frames, seed, steps, prefix, start=None):
    def n(cls, **inputs): return {"class_type": cls, "inputs": inputs}
    return {
        "37": n("UNETLoader", unet_name="wan2.2_ti2v_5B_fp16.safetensors", weight_dtype="fp8_e4m3fn"),
        "38": n("CLIPLoader", clip_name="umt5_xxl_fp8_e4m3fn_scaled.safetensors", type="wan", device="default"),
        "39": n("VAELoader", vae_name="wan2.2_vae.safetensors"),
        "48": n("ModelSamplingSD3", model=["37", 0], shift=8.0),
        "6": n("CLIPTextEncode", clip=["38", 0], text=prompt),
        "7": n("CLIPTextEncode", clip=["38", 0], text=NEGATIVE),
        "55": n("Wan22ImageToVideoLatent", vae=["39", 0], width=W, height=H, length=frames, batch_size=1,
                **({"start_image": ["60", 0]} if start else {})),
        **({"56": n("LoadImage", image=start),
            "60": n("ImageScale", image=["56", 0], upscale_method="lanczos", width=W, height=H, crop="center")} if start else {}),
        "3": n("KSampler", model=["48", 0], positive=["6", 0], negative=["7", 0], latent_image=["55", 0], seed=seed,
               steps=steps, cfg=5.0, sampler_name="uni_pc", scheduler="simple", denoise=1.0),
        "8": n("VAEDecodeTiled", samples=["3", 0], vae=["39", 0], tile_size=512, overlap=64, temporal_size=32, temporal_overlap=8),
        "57": n("CreateVideo", images=["8", 0], fps=float(FPS)),
        "58": n("SaveVideo", video=["57", 0], filename_prefix=prefix, format="mp4", codec="h264"),
    }


def _wait_file(pid, ext, dst, what, timeout=3600):
    """ComfyUI 작업이 끝나면 ext 로 끝나는 결과 파일을 dst 로 내려받는다."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(5)
        h = _get(f"/history/{pid}")
        if pid not in h:
            continue
        st = h[pid].get("status", {})
        if st.get("status_str") == "error":
            raise SystemExit(f"{what} 실패: " + json.dumps(st.get("messages", []), ensure_ascii=False)[-400:])
        for node in h[pid].get("outputs", {}).values():
            for v in node.get("images", []) + node.get("videos", []) + node.get("gifs", []):
                if v.get("filename", "").endswith(ext):
                    q = urllib.parse.urlencode({"filename": v["filename"], "subfolder": v.get("subfolder", ""), "type": v.get("type", "output")})
                    with urllib.request.urlopen(f"{COMFY}/view?{q}", timeout=120) as r, open(dst + ".part", "wb") as f:
                        f.write(r.read())
                    os.replace(dst + ".part", dst)
                    return time.time() - t0
        if st.get("completed"):
            raise SystemExit(f"{what} 결과 파일을 찾지 못했습니다")
    raise SystemExit(f"{what} 시간 초과")


def _upload(path):
    """그림을 ComfyUI input 폴더에 올리고 이름을 돌려준다(LoadImage 용)."""
    bd = "----axwan" + str(random.randint(10**8, 10**9))
    name = os.path.basename(path)
    body = (f"--{bd}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n"
            f"--{bd}\r\nContent-Disposition: form-data; name=\"subfolder\"\r\n\r\ndisaster_shorts\r\n"
            f"--{bd}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\nContent-Type: image/png\r\n\r\n").encode()
    body += open(path, "rb").read() + f"\r\n--{bd}--\r\n".encode()
    req = urllib.request.Request(COMFY + "/upload/image", data=body, headers={"Content-Type": f"multipart/form-data; boundary={bd}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.load(r)
    return (d.get("subfolder") + "/" if d.get("subfolder") else "") + d["name"]


SW, SH = 576, 1024     # 그림 크기(9:16). Wan 에는 448x800 으로 줄여 넣는다


def still(prompt, dst, seed, free=True):
    """FLUX.1 schnell(로컬, 무료)로 글자 없는 디오라마 그림 한 장 — 질감·구도를 그림으로 먼저 고정한다."""
    def n(cls, **inputs): return {"class_type": cls, "inputs": inputs}
    g = {
        "1": n("CheckpointLoaderSimple", ckpt_name="flux1-schnell-fp8.safetensors"),
        "2": n("CLIPTextEncode", clip=["1", 1], text=prompt + " No text, no letters, no numbers, no logos, all signs blank."),
        "3": n("ConditioningZeroOut", conditioning=["2", 0]),
        "4": n("EmptySD3LatentImage", width=SW, height=SH, batch_size=1),
        "5": n("KSampler", model=["1", 0], positive=["2", 0], negative=["3", 0], latent_image=["4", 0], seed=seed,
               steps=4, cfg=1.0, sampler_name="euler", scheduler="simple", denoise=1.0),
        "6": n("VAEDecode", samples=["5", 0], vae=["1", 2]),
        "7": n("SaveImage", images=["6", 0], filename_prefix="disaster_shorts/" + os.path.splitext(os.path.basename(dst))[0]),
    }
    pid = _post("/prompt", {"prompt": g, "client_id": "disaster-shorts"})["prompt_id"]
    took = _wait_file(pid, ".png", dst, "그림(FLUX)", timeout=1800)
    print(f"그림: FLUX.1 schnell {SW}x{SH} {took:.0f}s → {os.path.basename(dst)}")
    if free:
        free_vram()      # FLUX(17GB)를 내려야 Wan 이 12GB 에 들어간다
    return dst


def run(prompt, secs, out, steps=20, timeout=3600, still_first=True):
    frames = int(secs * FPS) // 4 * 4 + 1        # Wan 은 4n+1 프레임
    seed = random.randint(1, 2**31 - 1)
    prefix = "disaster_shorts/" + os.path.splitext(os.path.basename(out))[0]
    ensure_comfy()
    start = None
    if still_first:
        png = out.replace(".mp4", ".still.png")
        if not os.path.exists(png):
            still(prompt, png, seed)
        start = _upload(png)
    motion = prompt + (" Animate this exact scene: keep the same composition, materials, figures and lighting; "
                       "gentle natural motion of people and objects as described, slow steady camera." if start else "")
    pid = _post("/prompt", {"prompt": graph(motion, frames, seed, steps, prefix, start), "client_id": "disaster-shorts"})["prompt_id"]
    json.dump({"prompt_id": pid, "seed": seed, "frames": frames, "size": [W, H], "still": start, "prompt": motion},
              open(out + ".wan.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"요청: Wan 2.2 5B {W}x{H} {frames}프레임 seed {seed}" + (" (그림에서 시작)" if start else ""))
    took = _wait_file(pid, ".mp4", out, "Wan 영상", timeout)
    print("완료", out, f"{took:.0f}s")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("ep"); ap.add_argument("scene", type=int)
    ap.add_argument("--seconds", type=int); ap.add_argument("--style"); ap.add_argument("--shot", type=int)
    ap.add_argument("--smoke", action="store_true", help="짧은 시험(2초·12단계)")
    ap.add_argument("--out", help="결과 파일(기본: 편 clips 폴더의 veo_scene.py 와 같은 이름)")
    ap.add_argument("--keep-vram", action="store_true", help="끝나도 모델을 내리지 않음(장면을 이어서 만들 때)")
    ap.add_argument("--still-only", action="store_true", help="그림만 만든다(여러 장면 그림을 FLUX 한 번 불러 몰아서 그릴 때)")
    ap.add_argument("--text-only", action="store_true", help="그림 없이 글만으로 만든다(예전 방식)")
    a = ap.parse_args()
    sc = json.load(open(f"{ROOT}/{a.ep}/script.json", encoding="utf-8"))
    s = next(x for x in sc["scenes"] if x["id"] == a.scene)
    style = a.style or sc.get("style", "3d_real")
    prompt, secs, suffix = build_prompt(sc, s, a.shot, 2 if a.smoke else a.seconds, style)
    out_dir = f"{ROOT}/{a.ep}/clips"; os.makedirs(out_dir, exist_ok=True)
    out = a.out or f"{out_dir}/scene{a.scene}_{style}_{a.seconds or (sc.get('clip_seconds', 8) if a.shot is None else s['shots'][a.shot].get('seconds', 4))}s{suffix}.mp4"
    if a.smoke and not a.out:
        out = out.replace(".mp4", "_smoke.mp4")
    if a.still_only:
        png = out.replace(".mp4", ".still.png")
        if not os.path.exists(png):
            ensure_comfy(); still(prompt, png, random.randint(1, 2**31 - 1), free=not a.keep_vram)
        sys.exit(0)
    ok = False
    try:
        run(prompt, secs, out, steps=12 if a.smoke else 20, still_first=not a.text_only); ok = True
    finally:
        if not (a.keep_vram and ok):       # 실패하면 다음 작업을 위해 항상 비운다
            free_vram()
