"""실사 B롤(Pexels → Pixabay) — 공용 구현(shared/stock_video.py)에 이 프로젝트의 키·저장 폴더를 넘긴다.

뉴스 영상에는 쓰지 않는다 — '제천 호우' 영상에 이름 모를 해외 홍수 장면을 깔면
시청자가 실제 현장으로 받아들인다. O·X 퀴즈·진로처럼 특정 사건과 무관한 일반
상식 영상에만 쓴다(그래서 B롤 자동 매칭에는 연결하지 않고, 편마다 검색어를 명시한다).
받은 클립은 글자가 묻히지 않게 어둡게 가공한 사본을 쓴다(shared.pexels.DIM_FX).

키: config.json 의 pexels.api_key / pixabay.api_key (또는 PEXELS_API_KEY / PIXABAY_API_KEY).

사용: python pexels_broll.py "snowy road driving" ["icy road winter" ...]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared import pexels as _px, stock_video as _sv  # noqa: E402

from common import BASE_DIR, load_config, log  # noqa: E402

OUT_DIR = os.path.join(BASE_DIR, "posts", "broll_pexels")
DIM_FX = _px.DIM_FX


def _key():
    k = (load_config().get("pexels", {}) or {}).get("api_key") or os.environ.get("PEXELS_API_KEY")
    if not k:
        raise RuntimeError("Pexels API 키가 없습니다(config.json 의 pexels.api_key).")
    return k


def search(query, per_page=8, min_sec=6):
    return _px.search(query, _key(), per_page=per_page, min_sec=min_sec)


def fetch(query, pick=0, dim=True):
    """세로 클립을 받아 가공본 경로·출처를 돌려준다. Pexels 에 없으면 Pixabay 에서 찾는다
    (키가 있는 곳만). 저장 폴더(broll_pexels)가 경로에 들어가야 render_frames 가 실사용
    글자 강화(realbroll)를 켠다 — Pixabay 클립도 같은 폴더에 둔다."""
    keys = _sv.keys_from(load_config())
    return _sv.fetch(query, keys, OUT_DIR, pick=pick, fx=DIM_FX if dim else None, log=log)


def fetch_pair(query, start=0, tries=4):
    """한 장면에 쓸 클립 두 개(절반에서 컷). 두 번째는 다른 촬영자의 것을 우선한다 —
    같은 촬영자의 연속 영상이면 컷을 바꿔도 같은 화면처럼 보인다(퀴즈 13 눈길 장면).
    두 번째를 못 구하면 (첫째, None)."""
    a = fetch(query, pick=start)
    fallback = None
    for k in range(start + 1, start + 1 + tries):
        try:
            b = fetch(query, pick=k)
        except Exception:
            break
        if b["path"] == a["path"]:
            break                                # 후보가 바닥나 같은 것을 돌려받았다
        if b.get("by") != a.get("by"):
            return a, b
        fallback = fallback or b
    return a, fallback


if __name__ == "__main__":
    for q in sys.argv[1:]:
        print(json.dumps(fetch(q), ensure_ascii=False))
