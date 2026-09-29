"""무료 실사 영상 공용 진입점 — Pexels 와 Pixabay 를 차례로 찾는다.

키가 있는 곳만 쓴다. 한 곳에 맞는 세로 영상이 없거나 받기에 실패하면 다음 곳으로
넘어간다. 순서는 providers 인자(기본: pexels → pixabay).

keys = {"pexels": "...", "pixabay": "..."}
"""
from shared import pexels, pixabay

PROVIDERS = {"pexels": pexels, "pixabay": pixabay}
DIM_FX = pexels.DIM_FX


def keys_from(cfg, env=None):
    import os
    env = env if env is not None else os.environ
    return {"pexels": (cfg.get("pexels", {}) or {}).get("api_key") or env.get("PEXELS_API_KEY"),
            "pixabay": (cfg.get("pixabay", {}) or {}).get("api_key") or env.get("PIXABAY_API_KEY")}


def fetch(query, keys, out_dir, providers=("pexels", "pixabay"), log=print, **kw):
    errors = []
    for name in providers:
        key = keys.get(name)
        if not key:
            continue
        try:
            info = PROVIDERS[name].fetch(query, key, out_dir, log=log, **kw)
            info.setdefault("source", name)
            return info
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__}: {str(e)[:60]}")
    if not errors:
        raise RuntimeError("실사 영상 API 키가 하나도 없습니다(pexels / pixabay).")
    raise RuntimeError("실사 영상을 찾지 못함 — " + " | ".join(errors))
