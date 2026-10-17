"""config.json 의 비밀값 칸을 암호화 저장소(secrets.env.enc)에서 채운다 — 프로젝트 공용.

비밀값은 config.json 에 두지 않는다(값은 빈 문자열). 각 프로젝트의 load_config 가 마지막에
apply(cfg) 를 부르면 아래 MAP 의 칸이 저장소 값으로 채워진다. 저장소에 없는 이름은 config
값을 그대로 둔다. 저장소를 열지 못하면(열쇠 없음 등) 경고만 남기고 config 값으로 진행한다.

이름 보기/바꾸기:  python -m shared.secret_env names | set 이름
(2026-10-17 블로거 → 유튜브·인스타 순서로 옮김)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILE = os.path.join(ROOT, "secrets.env.enc")

MAP = {
    ("anthropic_api_key",): "ANTHROPIC_API_KEY",
    ("gamma_api_key",): "GAMMA_API_KEY",
    ("llm_gateway", "api_key"): "LLM_GATEWAY_API_KEY",
    ("pexels", "api_key"): "PEXELS_API_KEY",
    ("pixabay", "api_key"): "PIXABAY_API_KEY",
    ("news", "naver_search", "client_id"): "NAVER_SEARCH_CLIENT_ID",
    ("news", "naver_search", "client_secret"): "NAVER_SEARCH_CLIENT_SECRET",
    ("tiktok", "client_key"): "TIKTOK_CLIENT_KEY",
    ("tiktok", "client_secret"): "TIKTOK_CLIENT_SECRET",
    ("heygen", "api_key"): "HEYGEN_API_KEY",
    ("x", "oauth2_client_id"): "X_OAUTH2_CLIENT_ID",
    ("x", "oauth2_client_secret"): "X_OAUTH2_CLIENT_SECRET",
}

_CACHE = {"mtime": None, "vals": {}}


def secrets(warn=print):
    """저장소 값(dict). 파일이 바뀔 때만 다시 푼다(load_config 는 한 실행에 여러 번 불린다)."""
    try:
        m = os.path.getmtime(FILE)
    except OSError:
        return {}
    if _CACHE["mtime"] != m:
        try:
            if ROOT not in sys.path:
                sys.path.insert(0, ROOT)
            from shared import secret_env
            _CACHE["vals"], _CACHE["mtime"] = secret_env.read(), m
        except BaseException as e:          # 키체인 거부는 SystemExit 로 온다
            warn(f"⚠ 암호화 환경설정을 열지 못함({type(e).__name__}) — config.json 값으로 진행")
            _CACHE["vals"], _CACHE["mtime"] = {}, m
    return _CACHE["vals"]


def _get(cfg, keys):
    d = cfg
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def apply(cfg, warn=print):
    """cfg 의 비밀값 칸을 저장소 값으로 채워 돌려준다(제자리 수정)."""
    vals = secrets(warn)
    for keys, name in MAP.items():
        v = vals.get(name)
        if not v:
            continue
        d = cfg
        for k in keys[:-1]:
            if not isinstance(d.get(k), dict):
                d[k] = {}
            d = d[k]
        d[keys[-1]] = v
    return cfg


def strip(cfg):
    """파일에 쓰기 전에 비밀값 칸을 비운 사본(설정 화면이 config.json 을 다시 쓰는 앱용)."""
    import copy
    out = copy.deepcopy(cfg)
    for keys in MAP:
        d = out
        for k in keys[:-1]:
            d = d.get(k) if isinstance(d, dict) else None
        if isinstance(d, dict) and d.get(keys[-1]):
            d[keys[-1]] = ""
    return out
