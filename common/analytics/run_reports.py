"""SNS 리포트 실행기 — Windows 전용 (2026-11-07, Mac 은퇴 후).

Mac 의 launchd + run_weekly_report.sh / run_monthly_report.sh / run_promo_report.sh / run_indexing_check.sh 를 대신한다.
예약 시각은 backups/pre_move_20261021 의 plist 에서 옮겼다.

    python common\\analytics\\run_reports.py <작업>          실제 실행(메일 발송 포함)
    python common\\analytics\\run_reports.py --dry <작업>    수집·생성만, 메일은 보내지 않음(SMUDS_REPORT_DRYRUN=1)
    python common\\analytics\\run_reports.py register         작업 스케줄러에 AutoSNS\\common.* 로 등록(켜진 상태)
    python common\\analytics\\run_reports.py status

작업: report.weekly(월 08:00) · report.monthly(매월 1일 08:00) · promoreport.monthly(매일 23:00, 내일이 1일일 때만)
      · indexcheck.daily(매일 07:30)
"""
import datetime as dt
import os
import socket
import subprocess
import sys
import time

AN = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(AN))
DEPT = os.path.join(ROOT, "dept")
PY = sys.executable
try:   # 2026-11-19: 창 없이 돌 때 하위 프로그램(python·tesseract·ffmpeg 등)이 CMD 창을 띄우지 않게
    import importlib.util as _iu
    _s = _iu.spec_from_file_location("nowindow", os.path.join(ROOT, "common", "shared", "nowindow.py"))
    _m = _iu.module_from_spec(_s); _s.loader.exec_module(_m); _m.apply()
except Exception:  # noqa: BLE001
    pass
TASK_PREFIX = "AutoSNS\\common."
SINCE = "2026-03-01"
HWPX_SKILL = os.path.join(os.path.expanduser("~"), ".claude", "skills", "hwpx", "scripts", "md2hwpx.py")


def vpy(folder):
    p = os.path.join(folder, ".venv", "Scripts", "python.exe")
    return p if os.path.exists(p) else PY


A_PY = vpy(AN)                                           # 리포트 생성·메일(googleapiclient·openpyxl)
YT_PY = vpy(os.path.join(DEPT, "youtube-shorts-auto"))
NB_PY = vpy(os.path.join(DEPT, "naver-blog-auto"))
IG_PY = vpy(os.path.join(DEPT, "insta-cardnews"))

JOBS = {
    "report.weekly": {"when": ["/SC", "WEEKLY", "/D", "MON", "/ST", "08:00"], "name": "SNS 주간 리포트 메일"},
    "report.monthly": {"when": ["/SC", "MONTHLY", "/D", "1", "/ST", "08:00"], "name": "월간 콘텐츠 활동 리포트 메일"},
    "promoreport.monthly": {"when": ["/SC", "DAILY", "/ST", "23:00"], "name": "학교 제출용 홍보활동 보고서(말일)"},
    "indexcheck.daily": {"when": ["/SC", "DAILY", "/ST", "07:30"], "name": "검색 색인 점검"},
}

LOG = None


def now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def say(msg):
    line = msg if msg.startswith("[") or msg.startswith("==") else f"[{now()}] {msg}"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def env():
    e = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    return e


def run(py, *args, ok_fail=True, what=None, lock=None):
    """한 단계. lock='profile:naver' 처럼 주면 그 크롬 프로필 잠금을 쥐고 돈다(발행 작업과 겹치지 않게)."""
    # lock 은 기록용이다. 크롬 프로필 잠금은 바깥 axlock 이 작업 전체에 한 번 쥔다(main 참고) —
    # Windows 에선 axlock 을 겹쳐 부르면 바깥 잠금이 상태 파일을 막아 안쪽이 멈췄다(2026-11-07).
    cmd = [py, *args]
    with open(LOG, "a", encoding="utf-8") as f:
        f.flush()
        try:
            p = subprocess.run(cmd, cwd=AN, stdout=f, stderr=subprocess.STDOUT, env=env(), timeout=3600)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            rc = 124
    if rc != 0:
        say(f"!! {what or args[0]} 실패(코드 {rc})" + (" — 직전 결과로 진행" if ok_fail else ""))
        if not ok_fail:
            raise SystemExit(rc)
    return rc


def last_line_of(py, *args):
    p = subprocess.run([py, *args], cwd=AN, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env())
    with open(LOG, "a", encoding="utf-8") as f:
        f.write((p.stdout or "") + (p.stderr or ""))
    out = [ln.strip() for ln in (p.stdout or "").splitlines() if ln.strip()]
    return out[-1] if out else ""


def wait_network(limit=300):
    end = time.time() + limit
    while time.time() < end:
        try:
            socket.create_connection(("www.googleapis.com", 443), timeout=5).close()
            return True
        except OSError:
            time.sleep(10)
    return False


def _insta_paused():
    try:
        import json
        cfg = json.load(open(os.path.join(ROOT, "dept", "insta-cardnews", "config.json"), encoding="utf-8"))
        return bool(cfg.get("instagram", {}).get("paused"))
    except Exception:  # noqa: BLE001
        return False


def collect(weekly=False):
    say("== 수집 시작 ==")
    run(YT_PY, "collect_youtube.py", what="유튜브 수집")
    run(A_PY, "collect_web.py", SINCE, what="블로그·홈페이지 수집")
    run(A_PY, "collect_blogger.py", SINCE, what="블로거 수집")
    run(A_PY, "collect_x.py", SINCE, what="엑스 수집")
    run(NB_PY, "collect_naver_stats.py", what="네이버 블로그 조회수 수집", lock="profile:naver")
    if _insta_paused():   # 2026-11-19 사용자 지시: 학과 인스타 보안 확인 중 — 로그인 시도를 하지 않는다
        say("인스타·스레드 수집 건너뜀(insta-cardnews config instagram.paused)")
    else:
        run(IG_PY, "collect_threads.py", SINCE, what="스레드 수집", lock="profile:insta")
        run(IG_PY, "collect_instagram.py", SINCE, what="인스타 수집", lock="profile:insta")
    if weekly:
        run(NB_PY, "collect_searchconsole.py", what="서치콘솔 수집")


def send(html, subject, *attach, dry):
    if dry:
        say("== 드라이런: 메일 발송 건너뜀 ==")
        return 0
    if not os.path.exists(os.path.join(AN, "mail_config.json")):
        say("메일 설정(mail_config.json) 없음 — 리포트 파일만 생성했습니다.")
        return 0
    say("== 메일 발송 ==")
    files = [a for a in attach if a and os.path.exists(os.path.join(AN, a) if not os.path.isabs(a) else a)]
    return run(A_PY, "send_mail.py", html, subject, *files, what="메일 발송")


def subject_of(path, default):
    try:
        return open(path, encoding="utf-8").read().strip() or default
    except OSError:
        return default


def weekly(dry, today=None):
    today = today or dt.date.today().isoformat()
    collect(weekly=True)
    say("== 리포트 생성 ==")
    html = last_line_of(A_PY, "build_report.py", today)
    say(html)
    if not os.path.exists(html):
        say("!! 리포트 생성 실패")
        return 1
    return send(html, subject_of(html[:-5] + ".subject.txt", "[재난안전학과] SNS 주간 리포트"), dry=dry)


def build_promo(ym, out):
    return run(A_PY, "build_promo_report.py", ym, out, ok_fail=True, what="홍보활동 보고서 작성")


def monthly(dry, today=None, ym=None):
    today = today or dt.date.today().isoformat()
    collect()
    say("== 월간 리포트 생성 ==")
    html = last_line_of(A_PY, "build_monthly.py", today, *([ym] if ym else []))
    if not os.path.exists(html):
        say(f"!! 리포트 생성 실패 ({html})")
        return 1
    ym = os.path.basename(html)[:-5].replace("monthly_", "")
    say(html)
    hwpx = f"out/재난안전학과_{ym}_콘텐츠활동_분석.hwpx"
    if os.path.exists(HWPX_SKILL):
        if run(A_PY, HWPX_SKILL, f"out/monthly_{ym}.md", "-o", hwpx, "-t", "report",
               "--title", f"세명대학교 재난안전학과 {ym} 콘텐츠 활동 분석", "--creator", "재난안전학과",
               what="한글 보고서 생성") != 0:
            hwpx = ""
    else:
        say(f"!! hwpx 스킬을 찾을 수 없음({HWPX_SKILL}) — 한글 첨부 제외")
        hwpx = ""
    xlsx = f"out/재난안전학과_{ym}_활동목록.xlsx"
    try:
        import shutil
        shutil.copyfile(os.path.join(AN, f"out/monthly_{ym}.xlsx"), os.path.join(AN, xlsx))
    except OSError:
        xlsx = ""
    promo = f"out/[재난안전학과] 온라인 홍보활동 보고서 {ym}.xlsx"
    if os.path.exists(os.path.join(AN, promo)):
        say("홍보활동 보고서: 말일에 작성된 파일을 첨부한다")
    else:
        say("홍보활동 보고서: 말일 작성분이 없어 지금 만든다")
        if build_promo(ym, promo) != 0:
            promo = ""
    subj = subject_of(os.path.join(AN, f"out/monthly_{ym}.subject.txt"), "[재난안전학과] 월간 콘텐츠 활동 리포트")
    return send(html, subj, hwpx, xlsx, promo, dry=dry)


def promo(dry, ym=None, force=False):
    if not ym:
        if not force and (dt.date.today() + dt.timedelta(days=1)).day != 1:
            return 0                      # 말일이 아니면 조용히 끝낸다(매일 깨어나므로)
        ym = dt.date.today().strftime("%Y-%m")
    collect()
    say("== 홍보활동 보고서 작성 ==")
    out = f"out/[재난안전학과] 온라인 홍보활동 보고서 {ym}.xlsx"
    rc = build_promo(ym, out)
    say(out)
    return rc


def indexcheck(dry):
    say("== 색인 점검 ==")
    return run(NB_PY, "check_indexing.py", what="색인 점검")


def kakao(text):
    try:
        sys.path.insert(0, ROOT)
        sys.path.insert(0, os.path.join(ROOT, "common"))
        from shared.kakao_notify import notify
        return notify(text[:190])
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


def do(key, dry, extra):
    global LOG
    os.makedirs(os.path.join(AN, "logs"), exist_ok=True)
    LOG = os.path.join(AN, "logs", f"{key}.log")
    if key == "promoreport.monthly" and not extra and (dt.date.today() + dt.timedelta(days=1)).day != 1 \
            and os.environ.get("FORCE") != "1":
        return 0                          # 말일 아님 — 기록도 남기지 않는다
    say(f"===== [{now()}] {key} 시작{' (드라이런: 메일 안 보냄)' if dry else ''} (Windows run_reports.py) =====")
    if not wait_network():
        say("!! 네트워크가 없어 이번 회차는 건너뛴다")
        rc = 1
    else:
        try:
            if key == "report.weekly":
                rc = weekly(dry, *extra[:1])
            elif key == "report.monthly":
                rc = monthly(dry, *extra[:2])
            elif key == "promoreport.monthly":
                rc = promo(dry, *(extra[:1] or [None]), force=os.environ.get("FORCE") == "1")
            else:
                rc = indexcheck(dry)
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else 1
    say(f"===== [{now()}] {key} 끝 (코드 {rc}) =====")
    if rc and not dry:
        kakao(f"[AX] 리포트 작업 실패: {key} (코드 {rc})")
    return rc


def register():
    me = os.path.abspath(__file__)
    pyw = PY.replace("python.exe", "pythonw.exe")
    pyw = pyw if os.path.exists(pyw) else PY
    for key, j in JOBS.items():
        name = TASK_PREFIX + key
        r = subprocess.run(["schtasks", "/Create", "/F", "/TN", name, *j["when"], "/TR", f'"{pyw}" "{me}" {key}'],
                           capture_output=True, text=True, encoding="mbcs", errors="replace")
        print(f"{name:40s} {' '.join(j['when']):32s}", "등록(켜짐)" if r.returncode == 0 else (r.stderr or r.stdout).strip()[:150])
    return 0


def status():
    r = subprocess.run(["schtasks", "/Query", "/FO", "CSV", "/NH"], capture_output=True, text=True, encoding="mbcs", errors="replace")
    for ln in r.stdout.splitlines():
        if "\\AutoSNS\\common." in ln:
            print(ln)
    return 0


def main(argv):
    dry = "--dry" in argv or os.environ.get("SMUDS_REPORT_DRYRUN") == "1"
    argv = [a for a in argv if a != "--dry"]
    if not argv:
        print(__doc__)
        return 2
    cmd, extra = argv[0], argv[1:]
    if cmd == "register":
        return register()
    if cmd == "status":
        return status()
    if cmd not in JOBS:
        print(__doc__)
        return 2
    if not os.environ.get("AX_LOCKED"):     # 잠금·비상 정지를 거쳐 자기 자신을 다시 실행한다
        ax = [PY, os.path.join(ROOT, "common", "shared", "axlock.py"), "run", "--job", cmd,
              *(["--res", "profile:naver", "--res", "profile:insta"] if cmd != "indexcheck.daily" else []), "--"]
        return subprocess.call(ax + [PY, os.path.abspath(__file__), *(["--dry"] if dry else []), cmd, *extra],
                               env={**env(), **({"SMUDS_REPORT_DRYRUN": "1"} if dry else {})}, cwd=ROOT)
    return do(cmd, dry, extra)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
