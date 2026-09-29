"""Pexels 무료 영상에서 세로 배경 클립을 찾아 받고, 글자가 묻히지 않게 가공한다.

유튜브 퀴즈·진로(youtube-shorts-auto/pexels_broll.py)와 인스타 카드뉴스 릴
(insta-cardnews/reel_broll.py)이 같이 쓴다. 키와 저장 폴더는 부르는 쪽이 넘긴다.

라이선스: Pexels License — 무료·상업 이용 가능, 출처 표기 의무 없음. 그래도 설명에
넣을 수 있게 촬영자·원본 주소를 함께 돌려준다.
"""
import json
import os
import subprocess
import urllib.parse
import urllib.request

API = "https://api.pexels.com/videos/search"

# 실사 클립은 일러스트보다 밝고 복잡해 글자가 묻힌다. 네 단계를 비교해 풍경은 살리고
# 글자는 읽히는 '중간'을 골랐다(2026-09-29, 퀴즈 13 눈길 장면).
DIM_FX = "eq=brightness=-0.20:contrast=0.9:saturation=0.7,gblur=sigma=2"


def search(query, api_key, per_page=8, min_sec=6):
    """세로 영상 후보를 (video, 고른 파일) 목록으로 돌려준다."""
    q = urllib.parse.urlencode({"query": query, "orientation": "portrait",
                                "size": "medium", "per_page": per_page})
    req = urllib.request.Request(f"{API}?{q}", headers={"Authorization": api_key,
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


def dim(src, fx=DIM_FX, suffix="_dim", max_sec=20, ffmpeg="ffmpeg"):
    """1080×1920 로 맞추고 가공한 사본을 만든다(소리 제거, 최대 max_sec 초). 이미 있으면 재사용."""
    out = src.replace(".mp4", f"{suffix}.mp4")
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return out
    # 임시 파일로 만든 뒤 성공했을 때만 옮긴다 — 실패로 남은 0바이트 파일을 다음 번에
    # '이미 있음'으로 재사용하던 문제가 있었다.
    tmp = out.replace(".mp4", ".part.mp4")
    # 색공간 정보가 비어 있는(reserved) 원본은 엄격한 ffmpeg 빌드가 'Invalid color space'
    # 로 거부한다(Pexels 35601601). 가공 전에 bt709 로 지정해 둔다.
    vf = ("setparams=colorspace=bt709:color_trc=bt709:color_primaries=bt709,"
          "scale=1080:1920:force_original_aspect_ratio=increase,"
          f"crop=1080:1920,fps=30,{fx}")
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-t", str(max_sec), "-i", src,
                    "-vf", vf, "-an", "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", tmp],
                   check=True)
    os.replace(tmp, out)
    return out


def fetch(query, api_key, out_dir, pick=0, fx=DIM_FX, suffix="_dim", ffmpeg="ffmpeg", log=print):
    """검색해 pick 번째 후보를 받아 가공본 경로와 출처 정보를 돌려준다.

    fx=None 이면 가공하지 않은 원본을 준다. 받은 원본은 out_dir 에 남겨 재사용한다."""
    cands = search(query, api_key)
    if not cands:
        raise RuntimeError(f"Pexels 에 맞는 세로 영상이 없습니다: {query}")
    v, f = cands[min(pick, len(cands) - 1)]
    os.makedirs(out_dir, exist_ok=True)
    raw = os.path.join(out_dir, f"pexels_{v['id']}.mp4")
    if not os.path.exists(raw):
        req = urllib.request.Request(f["link"], headers={"User-Agent": "smuds/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r, open(raw, "wb") as w:
            w.write(r.read())
    path = dim(raw, fx=fx, suffix=suffix, ffmpeg=ffmpeg) if fx else raw
    info = {"source": "pexels", "query": query, "id": v["id"], "path": path, "raw": raw,
            "width": f.get("width"),
            "height": f.get("height"), "duration": v.get("duration"),
            "size_mb": round(os.path.getsize(path) / 1e6, 1),
            "by": (v.get("user") or {}).get("name", ""), "url": v.get("url", "")}
    log(f"Pexels B롤: {query} → {info['width']}x{info['height']} {info['duration']}s "
        f"{info['size_mb']}MB (by {info['by']})")
    return info
