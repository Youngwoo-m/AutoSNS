"""공통 설정/경로 유틸."""
import json
import os
import time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
PROFILE_DIR = os.path.join(BASE_DIR, "chrome-profile")
POSTS_DIR = os.path.join(BASE_DIR, "posts")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
HISTORY_PATH = os.path.join(BASE_DIR, "title_history.json")

for d in (POSTS_DIR, LOGS_DIR, PROFILE_DIR):
    os.makedirs(d, exist_ok=True)


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
# 채운다(2026-10-17). config.json 쪽 값은 비워 둔다 — 저장소에 없을 때만 config 값이 쓰인다.
# 이름은 `python -m shared.secret_env names` 로 본다.
SECRET_MAP = {
    ("anthropic_api_key",): "ANTHROPIC_API_KEY",
    ("gamma_api_key",): "GAMMA_API_KEY",
    ("llm_gateway", "api_key"): "LLM_GATEWAY_API_KEY",
    ("pexels", "api_key"): "PEXELS_API_KEY",
    ("pixabay", "api_key"): "PIXABAY_API_KEY",
    ("news", "naver_search", "client_id"): "NAVER_SEARCH_CLIENT_ID",
    ("news", "naver_search", "client_secret"): "NAVER_SEARCH_CLIENT_SECRET",
}
_SECRETS = {"mtime": None, "vals": {}}


def secrets():
    """암호화 저장소 값(dict). 파일이 바뀔 때만 다시 푼다(load_config 가 자주 불린다).
    열지 못하면 {} — 그때는 config.json 값으로 돌아간다."""
    root = os.path.dirname(BASE_DIR)
    path = os.path.join(root, "secrets.env.enc")
    try:
        m = os.path.getmtime(path)
    except OSError:
        return {}
    if _SECRETS["mtime"] != m:
        try:
            import sys
            if root not in sys.path:
                sys.path.insert(0, root)
            from shared import secret_env
            _SECRETS["vals"], _SECRETS["mtime"] = secret_env.read(), m
        except BaseException as e:          # 키체인 거부는 SystemExit 로 온다
            log(f"⚠ 암호화 환경설정을 열지 못함({type(e).__name__}) — config.json 값으로 진행")
            _SECRETS["vals"], _SECRETS["mtime"] = {}, m
    return _SECRETS["vals"]


def _apply_secrets(cfg):
    vals = secrets()
    for keys, name in SECRET_MAP.items():
        v = vals.get(name)
        if not v:
            continue
        d = cfg
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = v
    return cfg


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
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(titles[-50:], f, ensure_ascii=False, indent=2)


def log(msg):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    logfile = os.path.join(LOGS_DIR, f"{datetime.now():%Y-%m}.log")
    with open(logfile, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def start_chrome(options, tries=3, wait=90):
    """크롬을 띄운다. 드라이버 짝이 안 맞으면 기다렸다 다시 시도한다.

    크롬이 자동 업데이트되면 selenium 이 받아 둔 chromedriver 와 버전이 어긋나
    SessionNotCreatedException 이 난다. selenium manager 가 새 드라이버를 받는 데
    1~2분이면 되는데, 그 사이에 걸리면 그날 글이 통째로 버려졌다
    (2026-09-19, 09-26 실제 발생 — 본문까지 다 만들어 놓고 발행에서 끊겼다).
    """
    from selenium import webdriver
    from selenium.common.exceptions import SessionNotCreatedException, WebDriverException
    # 크롬이 실행마다 앱 전체(~1.4GB)를 임시 폴더에 복제하고 남기는 것을 막는다(2026-10-09)
    options.add_argument("--disable-features=MacAppCodeSignClone")
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
