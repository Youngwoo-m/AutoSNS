"""Pexels 무료 영상에서 세로 B롤 클립을 찾아 받는다(시험용).

뉴스 영상에는 쓰지 않는다 — '제천 호우' 영상에 이름 모를 해외 홍수 장면을 깔면
시청자가 실제 현장으로 받아들인다. O·X 퀴즈·진로처럼 특정 사건과 무관한 일반
상식 영상에만 쓴다(그래서 B롤 자동 매칭에는 연결하지 않고, 편마다 명시해서 쓴다).

키: config.json 의 pexels.api_key 또는 환경변수 PEXELS_API_KEY.
라이선스: Pexels License — 무료·상업 이용 가능, 출처 표기 의무 없음. 그래도 영상
설명에 넣을 수 있게 촬영자·원본 주소를 함께 돌려준다.

사용: python pexels_broll.py "snowy road driving" ["icy road winter" ...]
"""
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

from common import BASE_DIR, load_config, log

OUT_DIR = os.path.join(BASE_DIR, "posts", "broll_pexels")
API = "https://api.pexels.com/videos/search"


def _key():
    k = (load_config().get("pexels", {}) or {}).get("api_key") or os.environ.get("PEXELS_API_KEY")
    if not k:
        raise RuntimeError("Pexels API 키가 없습니다(config.json 의 pexels.api_key).")
    return k


def search(query, per_page=8, min_sec=6):
    """세로 영상 후보를 (video, 고른 파일) 목록으로 돌려준다. 해상도 높은 순."""
    q = urllib.parse.urlencode({"query": query, "orientation": "portrait",
                                "size": "medium", "per_page": per_page})
    req = urllib.request.Request(f"{API}?{q}", headers={"Authorization": _key(),
                                                         "User-Agent": "smuds/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    out = []
    for v in data.get("videos", []):
        if (v.get("duration") or 0) < min_sec:
            continue
        files = [f for f in v.get("video_files", [])
                 if f.get("file_type") == "video/mp4" and f.get("height", 0) > f.get("width", 0)]
        # 1080×1920 에 가장 가까운 것(너무 큰 4K 는 받기만 무겁다)
        files.sort(key=lambda f: (abs((f.get("height") or 0) - 1920), -(f.get("height") or 0)))
        if files:
            out.append((v, files[0]))
    return out


# 실사 클립은 일러스트보다 밝고 복잡해 글자가 묻힌다. 네 단계를 비교해 풍경은 살리고
# 글자는 읽히는 '중간'을 골랐다(2026-09-29, 퀴즈 13 눈길 장면).
DIM_FX = "eq=brightness=-0.20:contrast=0.9:saturation=0.7,gblur=sigma=2"


def _dim(src, max_sec=20):
    """1080×1920 로 맞추고 어둡게·차분하게 가공한 사본을 만든다(소리 제거, 최대 20초)."""
    out = src.replace(".mp4", "_dim.mp4")
    if not os.path.exists(out):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-t", str(max_sec), "-i", src,
                        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,"
                               f"crop=1080:1920,fps=30,{DIM_FX}",
                        "-an", "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", out],
                       check=True)
    return out


def fetch(query, pick=0, dim=True):
    """검색해 pick 번째 후보를 받아 로컬 경로와 출처 정보를 돌려준다(이미 받았으면 재사용)."""
    cands = search(query)
    if not cands:
        raise RuntimeError(f"Pexels 에 맞는 세로 영상이 없습니다: {query}")
    v, f = cands[min(pick, len(cands) - 1)]
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"pexels_{v['id']}.mp4")
    if not os.path.exists(path):
        req = urllib.request.Request(f["link"], headers={"User-Agent": "smuds/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as w:
            w.write(r.read())
    raw = path
    if dim:
        path = _dim(raw)
    info = {"query": query, "id": v["id"], "path": path, "raw": raw, "width": f.get("width"),
            "height": f.get("height"), "duration": v.get("duration"),
            "size_mb": round(os.path.getsize(path) / 1e6, 1),
            "by": (v.get("user") or {}).get("name", ""), "url": v.get("url", "")}
    log(f"Pexels B롤: {query} → {info['width']}x{info['height']} {info['duration']}s "
        f"{info['size_mb']}MB (by {info['by']})")
    return info


if __name__ == "__main__":
    for q in sys.argv[1:]:
        print(json.dumps(fetch(q), ensure_ascii=False))
