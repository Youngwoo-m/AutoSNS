"""매주 한 편을 자동으로 만들어 편 날짜 19:00(config.publish.time_kst) 예약 공개로 올린다(launchd: 일·월 20:00).

  .venv/bin/python weekly.py            # 다가오는 화요일 편을 만든다(이미 올렸으면 아무것도 안 함)
  .venv/bin/python weekly.py --check    # 무엇을 만들지 보여 주기만
단계마다 결과 파일이 있으면 건너뛰므로, 도중에 실패해도 월요일 재시도 때 이어서 한다.
끝나면(또는 실패하면) 카톡으로 알린다.
"""
import shutil, datetime as dt, json, os, subprocess, sys, time, traceback, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
ROOT = CFG["root"]
AUTOSNS = "/Volumes/USB256/devAPP/AutoSNS/channels/youtube-shorts-auto"
PY = os.path.join(AUTOSNS, ".venv", "bin", "python")
KST = dt.timezone(dt.timedelta(hours=9))
sys.path.insert(0, AUTOSNS)


def log(m):
    print(f"[{dt.datetime.now(KST):%m-%d %H:%M}] {m}", flush=True)


def kakao(text, link=None):
    try:
        os.chdir(AUTOSNS)
        from kakao_notify import notify
        notify(text, link)
    except Exception as e:
        log(f"카톡 알림 실패: {e}")


def target():
    """앞으로 1~3일 안(일·월 저녁 → 화요일, 수·목 저녁 → 금요일)의 계획 편 중 아직 안 올린 편."""
    today = dt.datetime.now(KST).date()
    for e in json.load(open(os.path.join(ROOT, "schedule.json"), encoding="utf-8"))["episodes"]:
        d = dt.date.fromisoformat(e["date"])
        if today < d <= today + dt.timedelta(days=3):
            ep = f"{e['date']}_{e['type'].replace(' ', '').replace('/', '·')}"
            if not os.path.exists(os.path.join(ROOT, ep, "upload.json")):
                return e, ep
    return None, None


VBSH = "/Volumes/USB256/devAPP/AutoSNS/shared/voicebox.sh"


def ensure_voicebox():
    for i in range(60):
        try:
            urllib.request.urlopen(CFG["voicebox"]["url"] + "/models/cache-dir", timeout=3)
            return
        except Exception:
            if i == 0:   # 필요할 때만 켬 — 끄기는 run_weekly.sh 가 끝에 한다(AutoSNS/shared/voicebox.sh)
                log("Voicebox 실행")
                subprocess.run(["/bin/bash", VBSH, "up", "disastershorts.weekly"])
            time.sleep(5)
    raise RuntimeError("Voicebox 서버가 뜨지 않습니다")


def step(name, cmd):
    log(f"▶ {name}")
    r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
    sys.stdout.write(r.stdout[-3000:])
    if r.returncode != 0:
        raise RuntimeError(f"{name} 실패:\n{(r.stderr or r.stdout)[-800:]}")


def main(check=False):
    e, ep = target()
    if not e:
        log("만들 편 없음(이미 올렸거나 계획 없음)"); return
    ep_dir = os.path.join(ROOT, ep)
    log(f"대상: {e['date']} {e['type']} — {e['angle']}")
    if check:
        return
    if not os.path.exists("/Volumes/USB256"):
        raise RuntimeError("USB256 이 연결되어 있지 않습니다")
    step("대본", [PY, "write_script.py", e["date"]])
    sc = json.load(open(os.path.join(ep_dir, "script.json"), encoding="utf-8"))
    procs = []
    for s in sc["scenes"]:
        if s.get("media") == "card":            # 정리 카드는 조립 때 이 맥에서 그린다(무료)
            continue
        if s.get("media") == "diorama":         # 계기판(anatomy)은 미리 anatomy/models/<날짜>_gauge.mp4 에 둔다
            src = os.path.join(ROOT, "anatomy", "models", f"{e['date']}_gauge.mp4")
            dst = os.path.join(ep_dir, "clips", f"scene{s['id']}_gauge.mp4")
            if (s.get("gauge") or "").strip() and os.path.exists(src) and not os.path.exists(dst):   # 계기판은 필요할 때만
                shutil.copy(src, dst)
            if (s.get("gauge") or "").strip() and not os.path.exists(dst):   # 미리 만든 것이 없으면 여기서 그린다
                try:
                    import make_gauge
                    make_gauge.episode(ep, s["id"])
                except Exception as ge:
                    log(f"계기판 만들기 실패(계기판 없이 계속): {str(ge)[:200]}")
            fname = f"scene{s['id']}_3d_real_{sc.get('clip_seconds', 8)}s_diorama.mp4"
            if not os.path.exists(os.path.join(ep_dir, "clips", fname)):
                procs.append(subprocess.Popen([PY, "veo_scene.py", ep, str(s["id"])], cwd=HERE)); time.sleep(3)
            continue
        if s.get("media") == "model":           # anatomy 모형 영상은 미리 만들어 anatomy/models/<날짜>.mp4 에 둔다
            src = os.path.join(ROOT, "anatomy", "models", f"{e['date']}.mp4")
            dst = os.path.join(ep_dir, "clips", f"scene{s['id']}_model.mp4")
            if os.path.exists(src) and not os.path.exists(dst):
                shutil.copy(src, dst)
            if os.path.exists(dst):
                continue
            kakao(f"[재난 대응 숏츠] {e['date']} 모형 영상이 없어 장면 {s['id']}을 AI 영상으로 대신 만듭니다.")
        jobs = ([(f"scene{s['id']}_3d_real_{sh.get('seconds', 4)}s_shot{k}.mp4", ["--shot", str(k)])
                 for k, sh in enumerate(s["shots"])] if s.get("shots")
                else [(f"scene{s['id']}_3d_real_{sc.get('clip_seconds', 8)}s.mp4", [])])
        for fname, extra in jobs:
            if not os.path.exists(os.path.join(ep_dir, "clips", fname)):
                tool = "image_scene.py" if (sc.get("visual_mode") == "image" or s.get("media") == "image") else "veo_scene.py"
                procs.append(subprocess.Popen([PY, tool, ep, str(s["id"])] + extra, cwd=HERE))
                time.sleep(3)
    if CFG.get("voice_backend", "voicebox") != "edge":     # edge-tts 는 Voicebox 를 켜지 않는다(맥 부하)
        ensure_voicebox()
    step("나레이션(" + ("edge-tts" if CFG.get("voice_backend") == "edge" else "내 목소리") + ")",
         [sys.executable, "voice.py", "--episode", ep])
    for p in procs:
        if p.wait() != 0:
            raise RuntimeError("Veo 영상 생성 실패(크레딧 부족 또는 게이트웨이 오류)")
    step("조립", [PY, "assemble.py", ep])
    step("예약 업로드", [PY, "publish.py", ep])
    up = json.load(open(os.path.join(ep_dir, "upload.json")))
    kakao(f"[재난 대응 숏츠] {e['date']} {CFG['publish']['time_kst']} 공개 예약 완료\n「{sc['title']}」\n"
          f"지금은 비공개예요. 문제가 있으면 공개 전에 YouTube 스튜디오에서 수정·삭제해 주세요.", up["url"])
    log(f"완료: {up['url']}")


if __name__ == "__main__":
    try:
        main("--check" in sys.argv)
    except Exception as ex:
        log("실패: " + "".join(traceback.format_exception_only(type(ex), ex)))
        if "--check" not in sys.argv:
            kakao(f"[재난 대응 숏츠] 자동 제작 실패 — 월요일 20시에 다시 시도합니다.\n{str(ex)[:300]}")
        sys.exit(1)
