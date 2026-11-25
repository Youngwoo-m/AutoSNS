"""네이버 교차 발행 dry 실행 중 크롬 창이 닫히는('no such window') 원인 조사용(발행하지 않음). 2026-11-25.
크롬 로그를 켜고, safeworking 프로필 크롬 프로세스의 생사를 0.3초마다 기록한다.
    python tools_probe_winclose.py <티스토리 URL> <로그 폴더>
"""
import os, sys, threading, time, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
url, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
os.environ["CHROME_LOG_FILE"] = os.path.join(outdir, "chrome_debug.log")
sys.path.insert(0, HERE)
os.chdir(HERE)
import psutil
import naver_crosspost_personal as ncp
ncp._legacy_profile_setup()          # common 을 부르기 전에 safeworking 프로필로 맞춘다(안 하면 학과 프로필이 열림)
import common
assert "safeworking" in common.PROFILE_DIR, common.PROFILE_DIR

_orig = common.start_chrome


def start_chrome(options, *a, **k):
    options.add_argument("--enable-logging")
    options.add_argument("--v=0")
    return _orig(options, *a, **k)


common.start_chrome = start_chrome
WATCH = open(os.path.join(outdir, "watch.log"), "a", encoding="utf-8")
stop = False


def watch():
    seen = {}
    while not stop:
        now = {}
        for p in psutil.process_iter(["pid", "name", "cmdline", "ppid"]):
            try:
                cmd = p.info["cmdline"] or []
                if (p.info["name"] or "").lower().startswith("chrome") and any("chrome-profile-safeworking" in c for c in cmd):
                    typ = next((c.split("=", 1)[1] for c in cmd if c.startswith("--type=")), "browser")
                    now[p.info["pid"]] = typ
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        for pid in set(seen) - set(now):
            WATCH.write(f"{ts} GONE {pid} {seen[pid]}\n")
        for pid in set(now) - set(seen):
            WATCH.write(f"{ts} NEW {pid} {now[pid]}\n")
        WATCH.flush()
        seen = now
        time.sleep(0.3)


threading.Thread(target=watch, daemon=True).start()
import naver_crosspost_personal as ncp
sys.argv = ["x", "--tistory-url", url, "--category", "토목시공기술사", "--dry", "--allow-duplicate", "--job", "probe-winclose"]
rc = ncp.main()
time.sleep(1)
stop = True
WATCH.write(f"{datetime.datetime.now():%H:%M:%S} END rc={rc}\n")
WATCH.close()
