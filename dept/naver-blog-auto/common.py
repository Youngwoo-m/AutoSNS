"""공통 설정/경로 유틸."""
import json
import os
import time
from datetime import datetime
import sys

# 2026-11-10: Windows 콘솔 기본 인코딩(cp949)에서 제목의 '²' 같은 글자를 찍다 발행기가 죽지 않게 UTF-8 로 고정
for _st in (sys.stdout, sys.stderr):
    try:
        _st.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
# AX_NAVER_PROFILE: 다른 네이버 계정(개인 safeworking 등)용 프로필 폴더를 쓸 때
PROFILE_DIR = os.environ.get("AX_NAVER_PROFILE") or os.path.join(BASE_DIR, "chrome-profile")
POSTS_DIR = os.path.join(BASE_DIR, "posts")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
HISTORY_PATH = os.path.join(BASE_DIR, "title_history.json")

def _ensure_legacy_directories():
    for directory in (POSTS_DIR, LOGS_DIR, PROFILE_DIR):
        os.makedirs(directory, exist_ok=True)


def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise SystemExit(
            "config.json 이 없습니다. config.example.json 을 복사해 값을 채우세요."
        )
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    # 에디션 전환: 환경변수 SMUDS_EDITION 이 있으면 editions[그이름] 을 덮어씌운다.
    # (예: 토요일 AI판. 값이 없으면 기본=재난안전판으로 동작 — 기존과 동일.)
    edition = os.environ.get("SMUDS_EDITION")
    eds = cfg.get("editions", {})
    if edition and edition in eds:
        cfg = _deep_merge(cfg, eds[edition])
    return _apply_secrets(cfg)


# 비밀값은 config.json 에 두지 않고 암호화 저장소(AutoSNS/secrets.env.enc, 열쇠는 키체인)에서
# 채운다(2026-10-17). 칸 목록은 shared/secret_config.py 의 MAP.
def _apply_secrets(cfg):
    import sys
    root = os.path.dirname(os.path.dirname(BASE_DIR))
    if root not in sys.path:
        sys.path.insert(0, root)
    from shared import secret_config
    return secret_config.apply(cfg, warn=log)


def _deep_merge(base, over):
    """over 의 값을 base 위에 재귀 병합(딕셔너리는 깊게, 그 외는 교체)."""
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_history():
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_history(titles):
    _ensure_legacy_directories()
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(titles[-50:], f, ensure_ascii=False, indent=2)


def log(msg):
    _ensure_legacy_directories()
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    logfile = os.path.join(LOGS_DIR, f"{datetime.now():%Y-%m}.log")
    with open(logfile, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def kill_stale_headless(profile_dir):
    """이 프로필을 붙잡고 남은 '창 없는(headless)' 크롬만 끈다. 끈 개수를 돌려준다.

    2026-11-15 19:07 이웃새글 수집용 headless 크롬이 멈춘 채 driver.quit() 마저 시간 초과로 남아
    프로필을 잠그는 바람에 19:36 발행용 크롬이 3번 모두 'Chrome failed to start: crashed' 로 실패했다.
    사람이 보는 창(headless 아님)은 건드리지 않는다. 윈도우 전용."""
    if os.name != "nt" or not profile_dir:
        return 0
    import subprocess
    want = os.path.normcase(os.path.realpath(profile_dir)).rstrip("\\")
    ps = ("Get-CimInstance Win32_Process -Filter \"Name like 'chrome%.exe'\" | "
          "Where-Object { $_.CommandLine -and $_.CommandLine -notmatch '--type=' -and $_.CommandLine -match '--headless' } | "
          "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=60,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except Exception as e:
        log(f"남은 headless 크롬 확인 실패: {type(e).__name__}")
        return 0
    n = 0
    for line in out.splitlines():
        pid, _, cmd = line.partition("\t")
        m = cmd.split("--user-data-dir=", 1)
        if len(m) < 2 or not pid.strip().isdigit():
            continue
        prof = m[1].strip()
        if m[0].endswith('"'):  # "--user-data-dir=C:\a b" 처럼 인수 전체가 따옴표
            prof = prof.split('"', 1)[0]
        elif prof.startswith('"'):  # --user-data-dir="C:\a b"
            prof = prof[1:].split('"', 1)[0]
        else:
            prof = prof.split()[0]
        if os.path.normcase(os.path.realpath(prof)).rstrip("\\") != want:
            continue
        subprocess.run(["taskkill", "/PID", pid.strip(), "/T", "/F"], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        log(f"프로필을 잡고 남은 headless 크롬(PID {pid.strip()})을 정리했습니다.")
        n += 1
    if n:
        time.sleep(3)
    return n


def start_chrome(options, tries=3, wait=90):
    """크롬을 띄운다. 드라이버 짝이 안 맞으면 기다렸다 다시 시도한다.

    크롬이 자동 업데이트되면 selenium 이 받아 둔 chromedriver 와 버전이 어긋나
    SessionNotCreatedException 이 난다. selenium manager 가 새 드라이버를 받는 데
    1~2분이면 되는데, 그 사이에 걸리면 그날 글이 통째로 버려졌다
    (2026-09-19, 09-26 실제 발생 — 본문까지 다 만들어 놓고 발행에서 끊겼다).
    """
    _ensure_legacy_directories()
    from selenium import webdriver
    from selenium.common.exceptions import SessionNotCreatedException, WebDriverException
    # 계정별 크롬 실행 파일(개인 chrome-na.exe · 학과 chrome-dept.exe) — 프로필 폴더로 판단(2026-11-06)
    try:
        import importlib.util as _u
        _r = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
        _s = _u.spec_from_file_location("autosns_chrome_bin", os.path.join(_r, "common", "shared", "chrome_bin.py"))
        _m = _u.module_from_spec(_s)
        _s.loader.exec_module(_m)
        _m.apply(options)
    except Exception as e:
        log(f"계정별 크롬 지정 실패 — 기본 크롬으로 띄웁니다: {type(e).__name__}: {str(e)[:120]}")
    # 크롬이 실행마다 앱 전체(~1.4GB)를 임시 폴더에 복제하고 남기는 것을 막는다(2026-10-09)
    options.add_argument("--disable-features=MacAppCodeSignClone")
    # chromedriver 는 맥에서 --use-mock-keychain 을 붙여 가짜 키로 쿠키를 암호화한다. 그러면 로그인 앱(일반 크롬)으로
    # 로그인한 쿠키를 못 풀고 지워 '로그인 만료'가 난다(2026-10-28 개인 교차 발행 3건). 진짜 키체인을 쓰게 뺀다.
    ex = options.experimental_options.get("excludeSwitches") or []
    if "use-mock-keychain" not in ex:
        options.add_experimental_option("excludeSwitches", list(ex) + ["use-mock-keychain"])
    # 콘솔 브라우저 서비스가 켜진 프로필이면 창 없는 크롬을 빌려 쓴다(D3, ax-console/config/browser_service.json)
    try:
        import sys
        _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from shared.ax_browser import attach
        d = attach(options, log)
        if d is not None:
            return d
    except Exception as e:
        log(f"콘솔 브라우저 연결 실패 — 예전 방식으로 띄웁니다: {type(e).__name__}: {str(e)[:150]}")
    # 같은 프로필을 잡고 남은 headless 크롬이 있으면 먼저 정리한다(2026-11-15 발행 실패 원인)
    _ud = None
    try:
        _ud = next((a.split("=", 1)[1].strip('"') for a in options.arguments if a.startswith("--user-data-dir=")), None)
        kill_stale_headless(_ud)
    except Exception as e:
        log(f"남은 headless 크롬 정리 건너뜀: {type(e).__name__}")
    # 크롬 창이 도중에 사라지는 일('no such window', 2026-11-15~25 티스토리·네이버, 원인 미확인)의 단서를 남긴다.
    # 프로필마다 logs/chrome_<프로필>.log — 크롬이 뜰 때마다 새로 쓴다(마지막 실행분만 남음).
    try:
        if _ud and "--enable-logging" not in options.arguments:
            os.makedirs(LOGS_DIR, exist_ok=True)
            os.environ["CHROME_LOG_FILE"] = os.path.join(LOGS_DIR, f"chrome_{os.path.basename(os.path.normpath(_ud))}.log")
            options.add_argument("--enable-logging")
    except Exception as e:  # noqa: BLE001
        log(f"크롬 로그 설정 건너뜀: {type(e).__name__}")
    last = None
    for n in range(1, tries + 1):
        try:
            return webdriver.Chrome(options=options)
        except (SessionNotCreatedException, WebDriverException) as e:
            msg = str(e)
            if "session not created" not in msg.lower():
                raise
            last = e
            if n < tries:
                log(f"크롬 실행 실패({n}/{tries}) — {wait}초 뒤 다시 시도합니다. "
                    "(크롬이 업데이트되면 드라이버를 새로 받는 동안 이 오류가 난다)")
                time.sleep(wait)
    raise last
