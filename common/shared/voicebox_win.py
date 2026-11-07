"""Voicebox(내 목소리 TTS, http://127.0.0.1:17493) 를 Windows 에서 켜고 끈다 — Mac 의 shared/voicebox.sh 대신 (2026-11-06).

    python common\\shared\\voicebox_win.py up [이름]      켜고 API 가 응답할 때까지 기다림(최대 3분). 이미 켜져 있으면 바로 끝
    python common\\shared\\voicebox_win.py down [이름]    이 도구가 켠 서버이고 다른 사용자가 없으면 끔
    python common\\shared\\voicebox_win.py status
    python common\\shared\\voicebox_win.py run -- 명령 …  켜고 → 명령 실행 → 끔

Voicebox 앱(GUI)이 서버를 띄우지 못했을 때도 서버 실행 파일(voicebox-server.exe)을 직접 띄운다.
데이터(목소리 프로필·생성 기록)는 앱과 같은 폴더(%APPDATA%\\sh.voicebox.app)를 쓰고, 모델은 E:\\MacMini\\VoiceboxModels.
사람이 직접 연 서버는 끄지 않는다.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

PORT = 17493
URL = f"http://127.0.0.1:{PORT}"
DATA_DIR = os.path.join(os.environ.get("APPDATA", ""), "sh.voicebox.app")
# GPU(CUDA) 서버가 있으면 그것을, 없으면 CPU 서버를 띄운다(앱이 띄우는 것과 같은 실행 파일)
_CUDA = os.path.join(DATA_DIR, "backends", "cuda", "voicebox-server-cuda.exe")
_CPU = os.path.join(os.environ.get("LOCALAPPDATA", ""), "packages", "Claude_pzs8sxrjxfjjc", "LocalCache", "Local",
                    "Voicebox", "voicebox-server.exe")
SERVER = os.environ.get("VOICEBOX_SERVER") or (_CUDA if os.path.exists(_CUDA) else _CPU)
STATE = os.path.join(os.environ.get("LOCALAPPDATA", ""), "AutoSNS", "voicebox")
OURS = os.path.join(STATE, "started_by_ax.json")
USERS = os.path.join(STATE, "users")
LOG = os.path.join(STATE, "server.log")


def alive():
    try:
        with urllib.request.urlopen(URL + "/profiles", timeout=3) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def _users():
    os.makedirs(USERS, exist_ok=True)
    now = time.time()
    out = []
    for n in os.listdir(USERS):
        p = os.path.join(USERS, n)
        if now - os.path.getmtime(p) > 4 * 3600:      # 4시간 지난 표시는 버린다
            os.remove(p)
        else:
            out.append(n)
    return out


def up(name="manual"):
    os.makedirs(USERS, exist_ok=True)
    open(os.path.join(USERS, name), "w").close()
    if alive():
        print("Voicebox 이미 켜져 있음")
        return 0
    if not os.path.exists(SERVER):
        print(f"voicebox-server.exe 가 없습니다: {SERVER}")
        return 1
    os.makedirs(STATE, exist_ok=True)
    flags = 0x00000008 | 0x00000200 | 0x08000000      # DETACHED | NEW_PROCESS_GROUP | NO_WINDOW
    with open(LOG, "a", encoding="utf-8") as log:
        p = subprocess.Popen([SERVER, "--host", "127.0.0.1", "--port", str(PORT), "--data-dir", DATA_DIR],
                             stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=flags)
    with open(OURS, "w", encoding="utf-8") as f:
        json.dump({"pid": p.pid, "at": time.strftime("%Y-%m-%d %H:%M:%S")}, f)
    for _ in range(180):
        if alive():
            print(f"Voicebox 켜짐 (pid {p.pid})")
            return 0
        if p.poll() is not None:
            print(f"Voicebox 서버가 바로 끝났습니다(코드 {p.returncode}) — {LOG} 확인")
            return 1
        time.sleep(1)
    print("3분 안에 Voicebox API 가 응답하지 않았습니다")
    return 1


def down(name="manual"):
    try:
        os.remove(os.path.join(USERS, name))
    except FileNotFoundError:
        pass
    if not os.path.exists(OURS):
        print("이 도구가 켠 서버가 아니라 그대로 둡니다")
        return 0
    if _users():
        print("다른 작업이 아직 쓰고 있어 켜 둡니다:", ", ".join(_users()))
        return 0
    with open(OURS, encoding="utf-8") as f:
        pid = json.load(f)["pid"]
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    os.remove(OURS)
    print("Voicebox 끔")
    return 0


def main(argv):
    cmd = argv[0] if argv else "status"
    name = argv[1] if len(argv) > 1 and not argv[1].startswith("-") else "manual"
    if cmd == "up":
        return up(name)
    if cmd == "down":
        return down(name)
    if cmd == "run" and "--" in argv:
        rc = up("run-%d" % os.getpid())
        if rc:
            return rc
        try:
            return subprocess.call(argv[argv.index("--") + 1:])
        finally:
            down("run-%d" % os.getpid())
    print(json.dumps({"alive": alive(), "started_by_ax": os.path.exists(OURS), "users": _users() if os.path.isdir(USERS) else []},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
