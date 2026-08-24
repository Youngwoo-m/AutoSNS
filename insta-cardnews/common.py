"""공통 설정/경로 유틸. (네이버 자동포스팅과 독립된 별도 프로젝트)"""
import json
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
PROFILE_DIR = os.path.join(BASE_DIR, "chrome-profile-insta")  # 인스타 로그인 전용 프로필
POSTS_DIR = os.path.join(BASE_DIR, "posts")                   # 생성 결과(json/txt/png)
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
