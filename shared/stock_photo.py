"""무료 실사 사진(가로) — 블로그 본문용. Pexels 를 먼저, 없으면 Pixabay 에서 찾는다.

shared/stock_video.py 가 쇼츠 배경용 '세로 영상'이라면 이쪽은 글에 넣을 '가로 사진'이다.
라이선스는 둘 다 무료·상업 이용 가능, 출처 표기 의무 없음. 그래도 글에는 촬영자와
원본 주소를 밝힌다(credit). Pixabay 는 핫링크 금지라 두 곳 모두 받아서 쓴다 — 부르는
쪽이 우리 저장소(CDN)에 다시 올린다.

    keys = {"pexels": "...", "pixabay": "..."}     # stock_video.keys_from(cfg) 로 얻는다
    photo = find(["flood rescue", "heavy rain street"], keys, skip={"pexels:123"})
    path  = download(photo, out_dir)
"""
import json
import os
import urllib.parse
import urllib.request

UA = {"User-Agent": "smuds/1.0"}


def _get(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _pexels(query, key, per_page=15):
    q = urllib.parse.urlencode({"query": query, "orientation": "landscape",
                                "size": "large", "per_page": per_page})
    data = _get(f"https://api.pexels.com/v1/search?{q}", {"Authorization": key})
    for p in data.get("photos", []):
        src = p.get("src") or {}
        url = src.get("large2x") or src.get("large") or src.get("original")
        if not url or p.get("width", 0) < 1200:
            continue
        yield {"uid": f"pexels:{p['id']}", "provider": "Pexels", "image": url,
               "page": p.get("url", ""), "author": p.get("photographer", ""),
               "alt": p.get("alt", "") or query, "query": query}


def _pixabay(query, key, per_page=20):
    q = urllib.parse.urlencode({"key": key, "q": query, "image_type": "photo",
                                "orientation": "horizontal", "safesearch": "true",
                                "per_page": per_page})
    data = _get(f"https://pixabay.com/api/?{q}")
    for h in data.get("hits", []):
        url = h.get("largeImageURL") or h.get("webformatURL")
        if not url or h.get("imageWidth", 0) < 1200:
            continue
        yield {"uid": f"pixabay:{h['id']}", "provider": "Pixabay", "image": url,
               "page": h.get("pageURL", ""), "author": h.get("user", ""),
               "alt": query, "query": query}


PROVIDERS = {"pexels": _pexels, "pixabay": _pixabay}


def find(queries, keys, skip=(), providers=("pexels", "pixabay"), log=print, reject=None):
    """검색어를 앞에서부터 차례로, 공급처도 차례로 찾아 처음 맞는 사진 한 장을 준다.

    skip 에 든 uid(예: 'pexels:123')는 건너뛴다 — 같은 사진이 여러 글에 반복되지 않게.
    reject(photo) 가 참이면 그 사진도 건너뛴다(예: 설명문에 사고 장면이 든 사진).
    못 찾으면 None."""
    skip = set(skip or ())
    for q in [q for q in queries if q and q.strip()]:
        for name in providers:
            key = (keys or {}).get(name)
            if not key:
                continue
            try:
                for photo in PROVIDERS[name](q.strip(), key):
                    if photo["uid"] in skip or (reject and reject(photo)):
                        continue
                    return photo
            except Exception as e:
                log(f"  {name} 사진 검색 실패('{q}'): {type(e).__name__}: {str(e)[:80]}")
    return None


def download(photo, out_dir):
    """사진을 받아 로컬 경로를 준다."""
    os.makedirs(out_dir, exist_ok=True)
    ext = os.path.splitext(urllib.parse.urlparse(photo["image"]).path)[1].lower() or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        ext = ".jpg"
    path = os.path.join(out_dir, f"stock_{photo['uid'].replace(':', '_')}{ext}")
    req = urllib.request.Request(photo["image"], headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r, open(path, "wb") as f:
        f.write(r.read())
    return path
