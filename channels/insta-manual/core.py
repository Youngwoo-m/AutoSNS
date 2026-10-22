"""설정·경로·로그.

설정은 웹 화면에서 입력해 config.json 에 저장한다(개인 정보라 git 에 올라가지 않는다).
파일이 없어도 기본값으로 동작하며, 화면이 설정을 채우라고 안내한다.
"""
import json
import os
import threading
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
PROFILE_DIR = os.path.join(BASE_DIR, "chrome-profile")   # 인스타 로그인 세션이 사는 곳
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

for _d in (UPLOADS_DIR, LOGS_DIR, PROFILE_DIR):
    os.makedirs(_d, exist_ok=True)

DEFAULTS = {
    "anthropic_api_key": "",          # 비우면 AI 초안 기능만 꺼진다(게시는 정상 동작)
    "caption_model": "claude-sonnet-5",
    "instagram": {
        "username": "",               # @ 없이. 첫 댓글을 달 때 프로필을 찾는 데 쓴다
        "headless": False,            # True 면 창 없이 — 로그인 문제 추적이 어려워 권장 안 함
        "follow_cta": "",             # 캡션 끝에 자동으로 붙일 문구(선택)
        "ai_label": False,            # 게시 시 'AI 레이블' 토글 시도
    },
    "hashtags": [],                   # 기본 해시태그
    "always_tags": [],                # 항상 포함할 태그(브랜딩용). 개수 제한보다 우선한다
    "max_hashtags": 30,               # 인스타 상한이 30개
}


def _merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def config_exists():
    return os.path.exists(CONFIG_PATH)


def load_config():
    """저장된 설정을 기본값 위에 얹어 돌려준다. 파일이 없어도 예외를 던지지 않는다."""
    saved = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            log(f"config.json 을 읽지 못했습니다({e}). 기본값으로 진행합니다.")
    cfg = _merge(DEFAULTS, saved)
    # 예전 이름 호환: local_tags → always_tags
    if not cfg.get("always_tags") and saved.get("local_tags"):
        cfg["always_tags"] = saved["local_tags"]
    sc = _secret_config()
    return sc.apply(cfg, warn=log) if sc else cfg


def _secret_config():
    """AutoSNS 안에서 돌 때만 쓰는 암호화 저장소(shared/secret_config.py).
    이 앱만 따로 떼어 쓰면 없으니, 그때는 예전처럼 config.json 에 키를 둔다."""
    import sys
    root = os.path.dirname(os.path.dirname(BASE_DIR))
    if not os.path.exists(os.path.join(root, "shared", "secret_config.py")):
        return None
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from shared import secret_config
        return secret_config
    except Exception:
        return None


def save_config(patch):
    """화면에서 넘어온 설정을 기존 값 위에 병합해 저장한다."""
    current = load_config()
    cfg = _merge(current, patch or {})
    on_disk = cfg
    sc = _secret_config()
    if sc:
        # 비밀값은 파일 대신 저장소에 둔다. 화면에서 새 키를 넣으면 저장소 값을 바꾼다 —
        # 이 키는 AutoSNS 자동 발행과 같이 쓰는 공용 키다. '지우기'는 저장소의 공용 키를
        # 지우지 않는다(다른 발행이 멈추므로). 저장소를 못 쓰면 예전처럼 파일에 둔다.
        try:
            from shared import secret_env
            new = {name: v for keys, name in sc.MAP.items()
                   if (v := sc._get(patch or {}, keys))}
            if new:
                secret_env.update(new)
                log(f"비밀값 {len(new)}개를 암호화 저장소에 저장했습니다.")
            on_disk = sc.strip(cfg)
        except BaseException as e:
            log(f"⚠ 암호화 저장소에 쓰지 못함({type(e).__name__}) — config.json 에 저장합니다")
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(on_disk, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_PATH)      # 쓰다 만 파일이 남지 않도록 원자적 교체
    try:
        os.chmod(CONFIG_PATH, 0o600)  # API 키가 들어가므로 본인만 읽게
    except OSError:
        pass
    log("설정을 저장했습니다.")
    return cfg


def is_ready():
    """게시에 필요한 최소 설정이 채워졌는지."""
    return bool(load_config().get("instagram", {}).get("username"))


def merge_tags(tags, cfg=None):
    """always_tags 를 반드시 포함시키면서 max_hashtags 개로 자른다."""
    cfg = cfg or load_config()
    always = [t.lstrip("#") for t in cfg.get("always_tags", []) if t]
    maxn = int(cfg.get("max_hashtags", 30))
    rest = [t.lstrip("#") for t in (tags or []) if t and t.lstrip("#") not in always]
    return list(dict.fromkeys(rest[:max(0, maxn - len(always))] + always))[:maxn]


CAPTION_MAX = 2200     # 인스타 캡션 글자 상한
COMMENT_MAX = 2200     # 댓글 글자 상한
IMAGES_MAX = 10        # 캐러셀 최대 장수


def check_post(caption, comment, tags_in, tags_out, n_images=None, max_tags=30):
    """발행 직전 점검. (errors, warnings) 를 돌려준다. errors 가 있으면 인스타가 거부한다."""
    errors, warnings = [], []
    if len(caption) > CAPTION_MAX:
        errors.append(f"캡션이 {len(caption)}자입니다. 인스타 상한은 {CAPTION_MAX}자 — "
                      f"{len(caption) - CAPTION_MAX}자를 줄여 주세요.")
    elif len(caption) > CAPTION_MAX - 150:
        warnings.append(f"캡션이 {len(caption)}자로 상한({CAPTION_MAX}자)에 가깝습니다.")
    if len(comment) > COMMENT_MAX:
        errors.append(f"첫 댓글이 {len(comment)}자입니다. 상한은 {COMMENT_MAX}자입니다.")
    dropped = len(dict.fromkeys(t.lstrip("#") for t in tags_in if t)) - len(tags_out)
    if dropped > 0:
        warnings.append(f"해시태그가 상한({max_tags}개)을 넘어 {dropped}개는 빠집니다. "
                        f"올라가는 태그는 {len(tags_out)}개입니다.")
    if n_images is not None and n_images > IMAGES_MAX:
        warnings.append(f"카드가 {n_images}장입니다. 앞의 {IMAGES_MAX}장만 올라갑니다.")
    return errors, warnings


def shot_path(name):
    return os.path.join(LOGS_DIR, f"{datetime.now():%Y%m%d_%H%M%S}_{name}.png")


# ---------------------------------------------------------------- 로그
# 게시는 백그라운드 스레드에서 돌고 브라우저가 실시간으로 로그를 받아본다.
# _sink 가 걸려 있으면 그쪽에도 쌓아 화면으로 흘려보낸다.
_sink = None
_sink_lock = threading.Lock()


def set_sink(lines):
    global _sink
    with _sink_lock:
        _sink = lines


def log(msg):
    line = f"[{datetime.now():%H:%M:%S}] {msg}"
    print(line, flush=True)
    try:
        with open(os.path.join(LOGS_DIR, f"{datetime.now():%Y-%m}.log"), "a",
                  encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except OSError:
        pass
    with _sink_lock:
        if _sink is not None:
            _sink.append(line)
