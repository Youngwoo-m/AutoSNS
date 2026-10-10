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
import re
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
               "alt": p.get("alt", "") or query, "text": p.get("alt", ""), "query": query}


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
               "alt": query, "text": h.get("tags", ""), "query": query}


PROVIDERS = {"pexels": _pexels, "pixabay": _pixabay}

# ─── 검색어와 사진이 맞는지 ──────────────────────────────────────────────────
# 공급처는 검색어 단어 하나만 걸려도 사진을 돌려준다. 2026-10-10 대기환경기사 글에
# 'air quality monitoring station' 으로 Pixabay 가 소유즈 우주선(태그 'space station')을
# 줘서 그대로 실렸다. 그래서 사진의 설명(Pexels alt)·태그(Pixabay tags)에 검색어 단어가
# 몇 개 들었는지 세어, 모자라면 버리고 남은 것 중 가장 잘 맞는 사진을 고른다.
STOP = {"the", "and", "with", "for", "from", "into", "onto", "over", "under", "of", "in",
        "on", "at", "to", "by", "a", "an", "photo", "image", "picture", "view"}


def _words(q):
    return [w for w in re.findall(r"[a-z]+", (q or "").lower()) if len(w) >= 3 and w not in STOP]


def _pat(w):
    """복수형·진행형을 같은 낱말로 본다(stations, monitoring 등)."""
    stem = re.sub(r"(ies|es|s|ing)$", "", w) if len(w) > 4 else w
    return r"\b" + re.escape(stem) + r"[a-z]*"


def relevance(photo, query):
    """(맞은 낱말 수, 점수). 점수 = 맞은 낱말 + 붙어 나온 두 낱말(예 'air quality')마다 2."""
    text = (photo.get("text") or "").lower()
    words = _words(query)
    if not text or not words:
        return 0, 0
    hit = [w for w in dict.fromkeys(words) if re.search(_pat(w), text)]
    pairs = sum(1 for a, b in zip(words, words[1:])
                if re.search(_pat(a) + r"[\s,-]+" + _pat(b)[2:], text))
    return len(hit), len(hit) + 2 * pairs


def relevant(photo, query):
    """검색어 낱말이 하나뿐이면 1개, 그 이상이면 2개 이상 맞아야 쓴다."""
    n = len(set(_words(query)))
    return relevance(photo, query)[0] >= min(2, n) if n else True


def find(queries, keys, skip=(), providers=("pexels", "pixabay"), log=print, reject=None):
    """검색어를 앞에서부터 차례로, 공급처도 차례로 찾아 처음 맞는 사진 한 장을 준다.

    skip 에 든 uid(예: 'pexels:123')는 건너뛴다 — 같은 사진이 여러 글에 반복되지 않게.
    reject(photo) 가 참이면 그 사진도 건너뛴다(예: 설명문에 사고 장면이 든 사진).
    태그·설명에 검색어 낱말이 모자란 사진도 버리고(relevant), 남은 것 중 가장 잘 맞는 것을 준다.
    못 찾으면 None."""
    skip = set(skip or ())
    for q in [q for q in queries if q and q.strip()]:
        for name in providers:
            key = (keys or {}).get(name)
            if not key:
                continue
            try:
                ok, off = [], 0
                for photo in PROVIDERS[name](q.strip(), key):
                    if photo["uid"] in skip or (reject and reject(photo)):
                        continue
                    if not relevant(photo, q):
                        off += 1
                        continue
                    ok.append(photo)
                if off:
                    log(f"  {name} '{q}': 검색어와 안 맞는 사진 {off}장 제외(태그·설명 확인)")
                if ok:   # 가장 잘 맞는 것, 같으면 공급처 순위(앞쪽)
                    return max(ok, key=lambda ph: relevance(ph, q)[1])
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
