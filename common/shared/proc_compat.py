"""프로세스 목록·종료의 OS 공통 창구(2026-11-06 Windows 이전: pgrep/pkill/ps 가 없다).

    processes()                   [(pid, ppid, 명령줄)]  — psutil 이 있으면 그것, 없으면 Windows 는 PowerShell CIM, 그 밖은 ps
    user_data_dirs()              {realpath 정규화 경로: [pid…]} — 크롬 --user-data-dir 값
    profile_in_use(path)          그 프로필 폴더를 쓰는 크롬이 떠 있는지(정션·링크는 realpath 로 맞춘다)
    kill_matching(text)           명령줄에 text 가 든 프로세스를 끝낸다(pkill -f 대체). 끝낸 pid 목록
"""
import json
import os
import re
import subprocess
import sys

_UDD = re.compile(r'--user-data-dir=(?:"([^"]+)"|(.+?))(?=\s+--|\s*"?$)')


def processes():
    try:
        import psutil
        out = []
        for p in psutil.process_iter(["pid", "ppid", "cmdline"]):
            cl = p.info.get("cmdline") or []
            out.append((p.info["pid"], p.info.get("ppid") or 0, " ".join(cl)))
        return out
    except ImportError:
        pass
    if sys.platform == "win32":
        ps = ("Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,CommandLine | "
              "ConvertTo-Json -Compress")
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        rows = json.loads(r.stdout or "[]")
        if isinstance(rows, dict):
            rows = [rows]
        return [(x.get("ProcessId") or 0, x.get("ParentProcessId") or 0, x.get("CommandLine") or "") for x in rows]
    r = subprocess.run(["ps", "-axo", "pid=,ppid=,command="], capture_output=True, text=True)
    out = []
    for line in r.stdout.splitlines():
        parts = line.split(None, 2)
        if len(parts) >= 2:
            out.append((int(parts[0]), int(parts[1]), parts[2] if len(parts) > 2 else ""))
    return out


def _norm(path):
    p = os.path.realpath(os.path.expanduser(path.strip().strip('"')))
    return os.path.normcase(p.rstrip("\\/"))


def user_data_dirs(procs=None):
    found = {}
    for pid, _ppid, cl in (procs if procs is not None else processes()):
        for m in _UDD.finditer(cl or ""):
            found.setdefault(_norm(m.group(1) or m.group(2)), []).append(pid)
    return found


def profile_in_use(path, procs=None):
    return _norm(path) in user_data_dirs(procs)


def kill_matching(text):
    """명령줄에 text 가 든 프로세스를 끝낸다. 자기 자신과 조상(부른 셸 등)은 건드리지 않는다."""
    procs = processes()
    parent = {pid: ppid for pid, ppid, _ in procs}
    keep, cur = set(), os.getpid()
    while cur and cur not in keep:
        keep.add(cur)
        cur = parent.get(cur)
    killed = []
    for pid, _ppid, cl in procs:
        if pid not in keep and text in (cl or ""):
            try:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    os.kill(pid, 15)
                killed.append(pid)
            except OSError:
                pass
    return killed
