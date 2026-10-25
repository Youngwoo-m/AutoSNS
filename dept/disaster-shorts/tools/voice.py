"""나레이션 음성. config.json 의 voice_backend 로 고른다(2026-10-22: 내 목소리 Voicebox 가 맥을 과부하시켜 기본 edge).

  edge       edge-tts 'ko-KR-InJoonNeural'(config.edge). 몇 초, 맥 부하 없음. 받아쓰기 검사 없음.
  voicebox   Voicebox(내 목소리)로 읽게 하고 받아쓰기로 발음을 검사한다. 컴퓨터 사양이 좋아지면 이 값으로 되돌린다.

Voicebox 방식 설명:
Voicebox(내 목소리)로 문장을 읽게 하고, 받아쓰기로 발음을 검사해 가장 정확한 것을 고른다.

  python3 voice.py "문장" out.wav            # 한 문장
  python3 voice.py --episode 2026-10-06_산불  # 대본의 장면 나레이션 전부 → voice/sceneN.wav

시드를 바꿔 가며 만들고, Whisper 받아쓰기와 원문의 글자 오차율(CER)이 max_cer 이하인
첫 결과를 쓴다. 모두 넘으면 오차율이 가장 낮은 것을 쓰고 경고를 남긴다.
"""
import argparse, difflib, json, os, re, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
VB = CFG["voicebox"]
BACKEND = CFG.get("voice_backend", "voicebox")


def speak_edge(text, out):
    """edge-tts 로 mp3 를 받아 wav 로 바꿔 저장한다(Voicebox 결과와 같은 wav)."""
    import asyncio, tempfile
    import edge_tts
    ec = CFG.get("edge", {})
    kw = {"voice": ec.get("voice", "ko-KR-InJoonNeural")}
    if ec.get("rate"):
        kw["rate"] = ec["rate"]
    with tempfile.TemporaryDirectory() as d:
        mp3 = os.path.join(d, "v.mp3")
        asyncio.run(edge_tts.Communicate(text, **kw).save(mp3))
        if not os.path.isfile(mp3) or os.path.getsize(mp3) < 1000:
            raise RuntimeError(f"edge-tts 가 음성을 만들지 못했습니다: {text[:30]}")
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", mp3, "-ar", "44100", "-ac", "1", out],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("wav 변환 실패: " + r.stderr.strip()[-200:])
    return {"file": out, "backend": "edge", "voice": kw["voice"]}


def _api(method, path, body=None):
    r = urllib.request.Request(VB["url"] + path, method=method,
                               data=json.dumps(body).encode() if body else None,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=120) as f:
        return f.read()


def stt(path):
    out = subprocess.run(["curl", "-s", "-X", "POST", VB["url"] + "/transcribe", "-F", f"file=@{path}",
                          "-F", "language=ko", "-F", "model=small"], capture_output=True, text=True).stdout
    try:
        return json.loads(out)["text"]
    except Exception:
        return ""


def _norm(t):
    t = t.replace("3명", "세명")          # Whisper 가 '세명'을 숫자로 적는 버릇
    return re.sub(r"[^가-힣0-9a-zA-Z]", "", t)


_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_JONG = ["", *"ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"]


def _jamo(t):
    """자모로 풀고 소리 없는 초성 ㅇ 을 뺀다 — '산은'과 '사는'(연음)이 같게 비교되도록."""
    out = []
    for ch in t:
        c = ord(ch) - 0xAC00
        if 0 <= c < 11172:
            cho, jung, jong = c // 588, (c % 588) // 28, c % 28
            if _CHO[cho] != "ㅇ":
                out.append(_CHO[cho])
            out.append(_JUNG[jung])
            if jong:
                out.append(_JONG[jong])
        else:
            out.append(ch)
    return "".join(out)


def cer(ref, hyp):
    a, b = _jamo(_norm(ref)), _jamo(_norm(hyp))
    return 1 - difflib.SequenceMatcher(None, a, b).ratio() if a else 1.0


def speak_once(text, seed):
    j = json.loads(_api("POST", "/generate", {"profile_id": VB["profile_id"], "text": text, "language": "ko",
                                              "engine": "qwen", "model_size": VB["model_size"], "seed": seed}))
    gid = j["id"]; t0 = time.time()
    while True:
        st = json.loads(_api("GET", f"/history/{gid}"))["status"]
        if st not in ("generating", "loading_model", "queued", "pending"):
            break
        if time.time() - t0 > VB.get("timeout_sec", 360):   # 끝없이 이어지는 생성(멈춤)을 끊는다
            _api("POST", f"/generate/{gid}/cancel")
            raise TimeoutError(f"{VB.get('timeout_sec', 360)}초 초과 — 취소")
        time.sleep(5)
    if st != "completed":
        raise RuntimeError(f"Voicebox 생성 실패: {st}")
    return _api("GET", f"/audio/{gid}")


def speak(text, out, check_text=None):
    """check_text: 받아쓰기와 비교할 문장(숫자를 한글로 풀어 읽게 한 경우 원래 표기)."""
    best = None
    for seed in VB["seeds"]:
        try:
            wav = speak_once(text, seed)
        except TimeoutError as e:
            print(f"  seed {seed}: {e}", flush=True)
            continue
        tmp = f"{out}.s{seed}.wav"
        open(tmp, "wb").write(wav)
        heard = stt(tmp)
        e = min(cer(text, heard), cer(check_text, heard) if check_text else 1.0)
        print(f"  seed {seed}: 오차 {e:.2f}  「{heard}」", flush=True)
        if best is None or e < best[0]:
            best = (e, tmp, seed, heard)
        if e <= VB["max_cer"]:
            break
    if best is None:
        raise RuntimeError(f"모든 시드가 시간 초과: {text[:30]}")
    os.replace(best[1], out)
    for f in os.listdir(os.path.dirname(out) or "."):
        if f.startswith(os.path.basename(out) + ".s"):
            os.remove(os.path.join(os.path.dirname(out) or ".", f))
    if best[0] > VB["max_cer"]:
        print(f"  ⚠️ 발음 검사 미통과(오차 {best[0]:.2f}) — 가장 나은 것 사용", flush=True)
    return {"file": out, "seed": best[2], "cer": round(best[0], 3), "heard": best[3]}


def ensure_server():
    """서버가 안 떠 있으면(앱만 켜져 있고 서버가 죽은 경우 포함) Voicebox 를 다시 켠다(10/6 실패 사례)."""
    def up():
        try:
            urllib.request.urlopen(VB["url"] + "/models/cache-dir", timeout=3); return True
        except Exception:
            return False
    if up():
        return
    print("Voicebox 서버가 꺼져 있어 다시 켭니다", flush=True)
    subprocess.run(["osascript", "-e", 'quit app "Voicebox"']); time.sleep(3)
    subprocess.run(["pkill", "-f", "voicebox-server"]); subprocess.run(["pkill", "-f", "Voicebox.app"]); time.sleep(3)
    subprocess.run(["open", "-a", "/Applications/Voicebox.app"])
    for _ in range(60):
        time.sleep(5)
        if up():
            return
    raise RuntimeError("Voicebox 서버가 뜨지 않습니다")


def episode(ep):
    if BACKEND != "edge":
        ensure_server()
    d = os.path.join(CFG["root"], ep)
    sc = json.load(open(os.path.join(d, "script.json"), encoding="utf-8"))
    os.makedirs(os.path.join(d, "voice"), exist_ok=True)
    res = []
    for s in sc["scenes"]:
        out = os.path.join(d, "voice", f"scene{s['id']}.wav")
        if os.path.exists(out):
            continue
        print(f"장면 {s['id']}: {s['narration']}", flush=True)
        if BACKEND == "edge":
            res.append(speak_edge(s.get("tts_text", s["narration"]), out))
        else:
            res.append(speak(s.get("tts_text", s["narration"]), out, check_text=s["narration"]))
    json.dump(res, open(os.path.join(d, "voice", "report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?"); ap.add_argument("out", nargs="?"); ap.add_argument("--episode")
    a = ap.parse_args()
    if a.episode:
        episode(a.episode)
    else:
        print(speak_edge(a.text, a.out) if BACKEND == "edge" else speak(a.text, a.out))
