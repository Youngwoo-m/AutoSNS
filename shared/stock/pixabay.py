"""Pixabay 무료 영상 — shared/pexels.py 와 같은 모양(search / fetch)으로 쓴다.

라이선스: Pixabay Content License — 무료·상업 이용 가능, 출처 표기 의무 없음.
단 핫링크 금지(영상 주소를 직접 걸지 말 것) — 여기서는 항상 받아서 쓴다.
API 는 영상 방향(세로) 필터가 없어 후보를 받은 뒤 세로만 고른다. 한도는 분당 100회.
"""
import os
import urllib.parse

from shared.stock.pexels import DIM_FX, dim
from shared.web import download, get_json

API = "https://pixabay.com/api/videos/"


def search(query, api_key, per_page=30, min_sec=6):
    """세로 영상 후보를 (hit, 고른 파일) 목록으로 돌려준다(1080×1920 에 가까운 순)."""
    q = urllib.parse.urlencode({"key": api_key, "q": query, "per_page": per_page,
                                "video_type": "film", "safesearch": "true"})
    data = get_json(f"{API}?{q}")
    out = []
    for h in data.get("hits", []):
        if (h.get("duration") or 0) < min_sec:
            continue
        files = [f for f in (h.get("videos") or {}).values()
                 if f.get("url") and (f.get("height") or 0) > (f.get("width") or 0)]
        files.sort(key=lambda f: (abs((f.get("height") or 0) - 1920), -(f.get("height") or 0)))
        if files:
            out.append((h, files[0]))
    if out:
        return out
    # Pixabay 는 세로 영상이 드물다(대부분 가로). 세로가 하나도 없으면 1920 폭 이상 가로
    # 영상을 받아 가운데를 세로로 자른다 — dim() 이 1080×1920 으로 채워 자르고 흐리게
    # 가공하므로 배경으로는 확대 흔적이 거의 보이지 않는다.
    for h in data.get("hits", []):
        if (h.get("duration") or 0) < min_sec:
            continue
        wide = [f for f in (h.get("videos") or {}).values()
                if f.get("url") and (f.get("width") or 0) >= 1920]
        wide.sort(key=lambda f: f.get("width") or 0)
        if wide:
            out.append((h, {**wide[0], "cropped": True}))
    return out


def fetch(query, api_key, out_dir, pick=0, fx=DIM_FX, suffix="_dim", ffmpeg="ffmpeg", log=print):
    cands = search(query, api_key)
    if not cands:
        raise RuntimeError(f"Pixabay 에 맞는 세로 영상이 없습니다: {query}")
    h, f = cands[min(pick, len(cands) - 1)]
    os.makedirs(out_dir, exist_ok=True)
    raw = os.path.join(out_dir, f"pixabay_{h['id']}.mp4")
    if not os.path.exists(raw) or os.path.getsize(raw) == 0:
        download(f["url"], raw)
    path = dim(raw, fx=fx, suffix=suffix, ffmpeg=ffmpeg) if fx else raw
    info = {"source": "pixabay", "query": query, "id": h["id"], "path": path, "raw": raw,
            "width": f.get("width"), "height": f.get("height"), "duration": h.get("duration"),
            "cropped": bool(f.get("cropped")),
            "size_mb": round(os.path.getsize(path) / 1e6, 1),
            "by": h.get("user", ""), "url": h.get("pageURL", "")}
    log(f"Pixabay B롤: {query} → {info['width']}x{info['height']} {info['duration']}s "
        f"{info['size_mb']}MB (by {info['by']})")
    return info
