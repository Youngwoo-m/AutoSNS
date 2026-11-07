"""학과 계정(semyungds) 자동 작업 실행기 — Windows 전용 (2026-11-06, Mac 은퇴 후).

Mac 의 launchd + run_*.sh 를 대신한다. 개인 계정 작업은 personal/run_personal.py 가 맡는다(여기서 건드리지 않음).
예약 시각은 Mac launchd 백업(backups/pre_move_20261021, dept/disaster-shorts/tools/plist_backup_20261022)에서 옮겼다.

    python dept\\run_dept.py <작업>                 실제 실행 (예: naverblog.weekly)
    python dept\\run_dept.py --dry <작업>           시험 실행(AX_DRY=1, 각 도구의 미리 보기 옵션)
    python dept\\run_dept.py list                   작업·예약 시각
    python dept\\run_dept.py register [--apply]     Windows 작업 스케줄러에 AutoSNS\\dept.* 로 등록(처음엔 모두 '사용 안 함')
    python dept\\run_dept.py enable|disable <작업>  등록한 작업 켜기/끄기
    python dept\\run_dept.py status                 등록 상태

모든 작업은 shared/axlock.py 의 잠금·비상 정지·하루 건너뛰기를 거친다(이 파일이 스스로 axlock run 으로 다시 실행된다).
"""
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile

DEPT = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DEPT)
PY = sys.executable
TASK_PREFIX = "AutoSNS\\dept."
YT, NB, IG = (os.path.join(DEPT, d) for d in ("youtube-shorts-auto", "naver-blog-auto", "insta-cardnews"))
DS = os.path.join(DEPT, "disaster-shorts", "tools")
CLAUDE_JOBS = os.path.join(ROOT, "personal", "claude-jobs")   # 지시문·공통규칙·jobs.json 은 여기 있다(dept-crosspost 만 학과)
DAYS = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]       # launchd Weekday 0..6


def S(cwd, *args, dry=None, ok_fail=False, venv=None):
    """한 단계. dry=None 이면 시험 실행 때 건너뛴다. dry=[...] 면 그 인자로 미리 보기."""
    return {"cwd": cwd, "args": list(args), "dry": dry, "ok_fail": ok_fail, "venv": venv or cwd}


JOBS = {
    "ytshorts.weekly": {"name": "재난 뉴스 숏츠(유튜브·릴·스레드·X·틱톡)", "times": [(3, "20:00"), (6, "20:00")],
                        "log": (YT, "run.out.log"), "disk": "유튜브뉴스",
                        "steps": [S(YT, "run_weekly.py", dry=["run_weekly.py", "--check"])]},
    "ytcareer.weekly": {"name": "진로·퀴즈 시리즈", "times": [(2, "19:00")], "log": (YT, "career_publish.out.log"),
                        "disk": "유튜브진로퀴즈", "steps": [S(YT, "publish_career.py", dry=["publish_career.py", "--dry"])]},
    "ytshorts.trigger": {"name": "큰 재난 즉시 숏츠 판단", "times": [(None, t) for t in ("08:00", "11:00", "14:00", "17:00", "20:00")],
                         "log": (YT, "trigger.out.log"), "disk": "유튜브트리거",
                         "steps": [S(YT, "check_trigger.py", dry=["check_trigger.py", "--dry"])]},
    "captionbackfill.daily": {"name": "유튜브 자막 보충", "times": [(None, "17:10")], "log": (YT, "caption_backfill.log"),
                              "steps": [S(YT, "backfill_captions.py", "--go", "--limit", "10", dry=["backfill_captions.py"])]},
    "tiktok.queue": {"name": "학과 틱톡 대기열", "every_min": 60, "log": (YT, "tiktok_queue.out.log"),
                     "fence": ["dept", "tiktok", "tiktok.queue"], "disk": "틱톡대기열",
                     "pre": (YT, ["-c", "import tiktok_queue as T,sys; e,_=T.pick(T._load()); sys.exit(0 if e else 3)"]),
                     "steps": [S(YT, "tiktok_queue.py", dry=["tiktok_queue.py", "--plan"])]},
    "xpromo.daily": {"name": "X 학과 소개", "times": [(None, "12:30")], "log": (YT, "x_promo.out.log"), "disk": "X학과소개",
                     "note": "2026-11-06 X 계정 정지(페이스북 해킹 연동) — config x.enabled=false. 정지가 풀린 뒤에 켤 것",
                     "steps": [S(YT, "x_promo.py", dry=["x_promo.py", "--plan"])]},
    "instacards.weekly": {"name": "인스타 카드뉴스", "times": [(3, "08:30"), (6, "08:30")], "log": (IG, "run.out.log"),
                          "disk": "인스타카드뉴스", "steps": [S(IG, "run_weekly.py")]},   # 시험 실행 옵션이 없다(항상 실제 게시) — 2026-11-06 시험 실행에서 실제로 게시된 사고 뒤 시험 때는 건너뜀
    "captionautofix.daily": {"name": "인스타 빈 캡션 복원", "times": [(None, "07:00")], "log": (IG, "caption_autofix.log"),
                             "steps": [S(IG, "build_caption_fixlist.py", "14", "captions_auto.json",
                                         dry=["build_caption_fixlist.py", "14", "captions_auto.json"]),
                                       S(IG, "ig_caption_restore.py", "captions_auto.json", "--go",
                                         dry=["ig_caption_restore.py", "captions_auto.json"])],
                             "skip_if_empty": os.path.join(IG, "captions_auto.json")},
    "captionrecheck.weekly": {"name": "인스타 캡션 재점검", "times": [(0, "21:00")], "log": (IG, "caption_recheck.log"),
                              "steps": [S(IG, "ig_caption_boost.py", "--go", "150", "--recheck",
                                          dry=["ig_caption_boost.py", "--recheck"])]},
    "naverblog.weekly": {"name": "네이버 학과 블로그 브리핑", "times": [(None, "19:00")], "log": (NB, "run.out.log"),
                         "disk": "네이버블로그", "steps": [S(NB, "run_weekly.py")]},   # 뉴스 경로는 시험 옵션을 무시한다 → 시험 때는 건너뜀(2026-11-06)
    "blogcareer.daily": {"name": "학과 Blogger 진로 시리즈", "times": [(None, "08:30")], "log": (NB, "career_series.log"),
                         "disk": "블로거진로", "steps": [S(NB, "career_series.py", dry=["career_series.py", "--dry"])]},
    "naverjobs.weekly": {"name": "채용정보(네이버·인스타·티스토리)", "times": [(0, "20:00")], "log": (NB, "jobs.log"),
                         "fence": ["dept", "naver_blog", "naverjobs.weekly"],
                         "note": "2026-10-18 사용자가 일부러 끔 — 켜기 전에 사용자에게 확인",
                         "steps": [S(NB, "jobs_work24.py", "--go", dry=["jobs_work24.py", "--dry"]),
                                   S(IG, "jobs_insta.py", "--latest", "--go", ok_fail=True),
                                   S(NB, "tistory_jobs.py", "--latest", "--go")]},
    "naverbuddy.weekly": {"name": "네이버 서로이웃 신청·집계", "times": [(5, "21:00")], "log": (NB, "buddy.out.log"),
                          "steps": [S(NB, "naver_buddy_request.py", "--go", dry=["naver_buddy_request.py"]),
                                    S(NB, "buddy_report.py", dry=["buddy_report.py", "--no-kakao"])]},
    "disastershorts.weekly": {"name": "재난 유형 숏츠(주 4편)", "times": [(d, "20:00") for d in (0, 1, 3, 4)],
                              "log": (os.path.join(DEPT, "disaster-shorts"), os.path.join("logs", "weekly.log")),
                              "steps": [S(DS, "weekly.py", dry=["weekly.py", "--check"], venv=YT)]},
    "disastershorts.crosspost": {"name": "재난 숏츠 교차 게시", "times": [(d, t) for d in (2, 5) for t in ("19:30", "21:00")],
                                 "log": (os.path.join(DEPT, "disaster-shorts"), os.path.join("logs", "crosspost.log")),
                                 "fence": ["dept", "youtube", "disastershorts.crosspost"],
                                 "steps": [S(DS, "crosspost.py", venv=YT)]},
    "claude.dept-crosspost": {"name": "학과 교차 발행(클로드, 개인 글 요약·숏츠)", "times": [(None, "21:00")], "claude": "dept-crosspost",
                              "fence": ["dept", "claude", "dept-crosspost"]},
}


def now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def venv_python(folder):
    p = os.path.join(folder, ".venv", "Scripts", "python.exe")
    return p if os.path.exists(p) else PY


def append(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(text if text.endswith("\n") else text + "\n")


def fence(args):
    r = subprocess.run([PY, "-I", os.path.join(ROOT, "common", "operations", "legacy_fences.py"), *args],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise SystemExit(f"legacy_fences 거부({r.returncode}): {r.stdout.strip()} {r.stderr.strip()[:200]}")


def kakao(text):
    try:
        import importlib.util as u
        s = u.spec_from_file_location("ax_kakao", os.path.join(ROOT, "common", "shared", "kakao_notify.py"))
        m = u.module_from_spec(s)
        sys.path.insert(0, ROOT)
        s.loader.exec_module(m)
        return m.notify(text[:190])
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


def _env(dry):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    if dry:
        env["AX_DRY"] = "1"
    return env


def run_steps(key, dry):
    j = JOBS[key]
    logdir, logname = j["log"]
    log = os.path.join(logdir, "logs", logname) if not logname.startswith("logs") else os.path.join(logdir, logname)
    if j.get("fence"):
        fence(j["fence"])
    env = _env(dry)
    append(log, f"===== [{now()}] {key} 시작{' (시험 실행)' if dry else ''} (Windows run_dept.py) =====")
    if j.get("disk") and not dry:
        subprocess.run([PY, os.path.join(ROOT, "common", "shared", "diskguard.py"), j["disk"]],
                       cwd=ROOT, env=env, capture_output=True)
    if j.get("pre") and not dry:
        cwd, args = j["pre"]
        if subprocess.run([venv_python(cwd), *args], cwd=cwd, env=env, capture_output=True).returncode == 3:
            append(log, f"[{now()}] 할 일 없음 — 건너뜀")
            return 0
    rc = 0
    with open(log, "a", encoding="utf-8") as fout:
        for i, st in enumerate(j["steps"]):
            args = st["dry"] if dry else st["args"]
            if args is None:
                fout.write(f"[{now()}] 시험 실행: {st['args'][0]} 단계는 미리 보기 옵션이 없어 건너뜀\n")
                continue
            if i > 0 and j.get("skip_if_empty") and not dry:
                try:
                    if not json.load(open(j["skip_if_empty"], encoding="utf-8")):
                        fout.write(f"[{now()}] 처리할 항목 없음 — 이후 단계 건너뜀\n")
                        break
                except (OSError, ValueError):
                    pass
            fout.flush()
            p = subprocess.Popen([venv_python(st["venv"]), *args], cwd=st["cwd"], stdout=fout, stderr=subprocess.STDOUT, env=env)
            try:
                code = p.wait(timeout=3 * 3600)
            except subprocess.TimeoutExpired:
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
                code = 124
            if code != 0:
                fout.write(f"[{now()}] {args[0]} 코드 {code}\n")
                if not st["ok_fail"]:
                    rc = code
                    break
    append(log, f"===== [{now()}] {key} 끝 (코드 {rc}) =====")
    if rc != 0 and not dry and key != "tiktok.queue":
        kakao(f"[AX] 학과 작업 실패: {key} (코드 {rc})")
    return rc


def run_claude(key, dry):
    """학과 교차 발행 클로드 작업. 지시문은 personal/claude-jobs/jobs/<key>.md(jobs.json 에 account: dept)."""
    j = JOBS[key]
    fence(j["fence"])
    name = j["claude"]
    meta = next(x for x in json.load(open(os.path.join(CLAUDE_JOBS, "jobs.json"), encoding="utf-8"))["jobs"] if x["key"] == name)
    log = os.path.join(CLAUDE_JOBS, "logs", f"{name}.log")
    rules = open(os.path.join(CLAUDE_JOBS, "공통규칙.md"), encoding="utf-8").read()
    body = open(os.path.join(CLAUDE_JOBS, "jobs", f"{name}.md"), encoding="utf-8").read()
    lines = [rules, "", "# 이번 실행",
             f"- 작업: {name} (학과 계정, Windows 작업 스케줄러 {TASK_PREFIX}{key}, 작업 기록 personal/claude-jobs/state/{name}.jsonl)",
             f"- 시각: {dt.datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z (%a)')}",
             "- **시험 실행(AX_DRY=1)** — 공통 규칙의 '시험 실행'대로 한다." if dry else "- 실제 실행",
             "", "# 이 PC(Windows)",
             "- 셸은 Windows 다. 가상환경 파이썬은 `.venv\\Scripts\\python.exe`. `/usr/bin`·`osascript`·`pbcopy` 는 없다.",
             "- 학과 발행기: dept/naver-blog-auto/dept_blogger_post.py, dept/youtube-shorts-auto/dept_short_post.py. 학과 크롬(chrome-dept.exe)은 발행기가 알아서 연다.",
             "", "# 작업 지시문", "", body]
    fd, prompt = tempfile.mkstemp(prefix="deptjob_", suffix=".md")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    claude = shutil.which("claude") or shutil.which("claude.cmd")
    if not claude:
        raise SystemExit("claude CLI 를 찾지 못했습니다")
    cmd = [claude, "-p", "--model", meta.get("model", "sonnet"), "--permission-mode", "bypassPermissions", "--no-chrome"]
    env = {**_env(dry), "CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS": "7200000"}
    append(log, f"===== [{now()}] {name} 시작 (모델 {meta.get('model')}{', 시험 실행' if dry else ''}, Windows run_dept.py) =====")
    with open(prompt, encoding="utf-8") as fin, open(log, "a", encoding="utf-8") as fout:
        p = subprocess.Popen(cmd, stdin=fin, stdout=fout, stderr=subprocess.STDOUT, cwd=ROOT, env=env)
        try:
            rc = p.wait(timeout=3 * 3600)
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
            rc = 124
    os.remove(prompt)
    append(log, f"===== [{now()}] {name} 끝 (코드 {rc}) =====")
    if rc != 0 and not dry:
        kakao(f"[AX] 학과 클로드 작업 실패: {name} (코드 {rc})")
    return rc


def _tasks():
    """[(작업 이름, schtasks 시점 인자, 작업 키)]"""
    out = []
    for key, j in JOBS.items():
        if j.get("every_min"):
            out.append((f"{TASK_PREFIX}{key}", ["/SC", "MINUTE", "/MO", str(j["every_min"])], key))
            continue
        by_time = {}
        for d, t in j["times"]:
            by_time.setdefault(t, []).append(d)
        for t, days in by_time.items():
            suffix = "" if len(by_time) == 1 else "." + t.replace(":", "")
            when = (["/SC", "DAILY", "/ST", t] if None in days
                    else ["/SC", "WEEKLY", "/D", ",".join(DAYS[d] for d in days), "/ST", t])
            out.append((f"{TASK_PREFIX}{key}{suffix}", when, key))
    return out


def register(apply):
    me = os.path.abspath(__file__)
    pyw = PY.replace("python.exe", "pythonw.exe")
    pyw = pyw if os.path.exists(pyw) else PY
    for name, when, key in _tasks():
        tr = f'"{pyw}" "{me}" {key}'
        print(f"{name:44s} {' '.join(when):34s} (사용 안 함으로 만듦)")
        if apply:
            r = subprocess.run(["schtasks", "/Create", "/F", "/TN", name, *when, "/TR", tr], capture_output=True, text=True, encoding="mbcs", errors="replace")
            ok = r.returncode == 0
            if ok:
                subprocess.run(["schtasks", "/Change", "/TN", name, "/DISABLE"], capture_output=True, text=True, encoding="mbcs", errors="replace")
            print("   ->", "등록(사용 안 함)" if ok else (r.stderr or r.stdout).strip()[:150])
    if not apply:
        print("\n(--apply 를 붙이면 위 작업을 '사용 안 함' 상태로 등록합니다. 켜려면 enable <작업>.)")
    return 0


def toggle(key, on):
    names = [n for n, _, k in _tasks() if k == key]
    if not names:
        raise SystemExit(f"학과 작업이 아닙니다: {key}")
    if on and JOBS[key].get("note"):
        print(f"주의: {JOBS[key]['note']}")
    for n in names:
        r = subprocess.run(["schtasks", "/Change", "/TN", n, "/ENABLE" if on else "/DISABLE"], capture_output=True, text=True, encoding="mbcs", errors="replace")
        print(n, "켬" if on and r.returncode == 0 else "끔" if r.returncode == 0 else (r.stderr or r.stdout).strip()[:150])
    return 0


def status():
    r = subprocess.run(["schtasks", "/Query", "/FO", "CSV", "/NH"], capture_output=True, text=True, encoding="mbcs", errors="replace")
    rows = [l for l in r.stdout.splitlines() if "\\AutoSNS\\dept." in l]
    for l in rows:
        print(l)
    if not rows:
        print("등록된 AutoSNS\\dept.* 작업이 없습니다")
    return 0


def main(argv):
    dry = "--dry" in argv or os.environ.get("AX_DRY") == "1"
    argv = [a for a in argv if a != "--dry"]
    if not argv:
        print(__doc__)
        return 2
    cmd = argv[0]
    if cmd == "list":
        for key, j in JOBS.items():
            when = f"{j['every_min']}분마다" if j.get("every_min") else ", ".join(
                (DAYS[d] + " " if d is not None else "매일 ") + t for d, t in j["times"])
            print(f"{key:26s} {when:40s} {j['name']}{'  ※ ' + j['note'] if j.get('note') else ''}")
        return 0
    if cmd == "register":
        return register("--apply" in argv)
    if cmd in ("enable", "disable") and len(argv) == 2:
        return toggle(argv[1], cmd == "enable")
    if cmd == "status":
        return status()
    if cmd not in JOBS:
        print(__doc__)
        return 2
    if not os.environ.get("AX_LOCKED"):     # 잠금·비상 정지를 거쳐 자기 자신을 다시 실행한다
        ax = [PY, os.path.join(ROOT, "common", "shared", "axlock.py"), "run", "--job", cmd]
        return subprocess.call(ax + ["--", PY, os.path.abspath(__file__), *(["--dry"] if dry else []), cmd],
                               env=_env(dry), cwd=ROOT)
    return run_claude(cmd, dry) if JOBS[cmd].get("claude") else run_steps(cmd, dry)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
