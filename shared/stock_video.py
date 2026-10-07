"""무료 실사 영상 공용 진입점 — Pexels 와 Pixabay 를 차례로 찾는다.

키가 있는 곳만 쓴다. 한 곳에 맞는 세로 영상이 없거나 받기에 실패하면 다음 곳으로
넘어간다. 순서는 providers 인자(기본: pexels → pixabay).

keys = {"pexels": "...", "pixabay": "..."}
"""
from shared import pexels, pixabay

PROVIDERS = {"pexels": pexels, "pixabay": pixabay}

# 뉴스(카드뉴스 릴·유튜브 뉴스)용 주제 → 검색어. 사고·피해 장면이 나오지 않을 상황
# 장면으로만 검색한다. 뉴스에 깔 때는 '배경: 자료 화면'을 표기한다(2026-09-29 결정).
TOPIC_QUERIES = [
    # 우주·위성 소식(누리호 5차, 2026-10-07). 이 항목이 없을 때 카드 본문의 "산불" 예시가
    # 잡혀 누리호 릴 배경에 산불 영상이 깔렸다. 글 앞머리에 오는 말이 이기므로 제목의
    # "누리호"가 먼저 잡힌다.
    (("누리호", "나로호", "나로우주센터", "발사체", "로켓", "인공위성", "위성", "우주"), "satellite earth orbit"),
    (("산불",), "forest fire smoke"),
    (("호우", "폭우", "집중호우", "침수", "홍수", "장마", "물폭탄"), "heavy rain street"),
    (("태풍", "강풍", "돌풍"), "storm wind trees"),
    (("폭설", "대설", "빙판", "한파", "동파"), "snow winter street"),
    (("폭염", "열사병", "온열", "무더위"), "hot summer sun city"),
    (("산사태", "토사", "토석류"), "mountain forest rain"),
    (("지진",), "city buildings aerial"),
    (("화재", "불길", "연기"), "fire smoke dark"),
    (("드론",), "drone flying sky"),
    (("AI", "인공지능", "CCTV", "스마트", "디지털"), "city lights night timelapse"),
    (("훈련", "소방", "구조대"), "fire truck city"),
    (("교통", "도로", "고속도로"), "highway traffic night"),
    (("추석", "명절", "전통시장", "축제"), "busy market street"),
]
DEFAULT_QUERY = "clouds sky timelapse"

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


def pick_query(texts, default=DEFAULT_QUERY):
    """texts 를 앞에서부터 보며, 각 글에서 가장 먼저 나오는 재난어로 검색어를 고른다.

    목록 순으로 고르면 '충북 드론 선제 출동 — AI가 산불·재난 골든타임'이 '산불'로 잡혀
    산불 현장처럼 보였다. 글 앞머리가 기사의 주어라 가장 먼저 나오는 말을 따른다."""
    for text in texts:
        text = text or ""
        hits = [(text.find(w), q) for words, q in TOPIC_QUERIES for w in words if w in text]
        if hits:
            return min(hits)[1]
    return default
