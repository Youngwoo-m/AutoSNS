"""AED·대피소 좌표 보정 — 원본 좌표가 '주소 대표점'(정문 등)이라 건물이 틀리게 찍히는 문제.

AED 원본은 한 기관의 여러 대(예: 세명대 8대)가 모두 같은 주소 좌표로 들어 있다.
'기관명 + 설치 건물명'(예: 세명대학교 학생회관)을 카카오 키워드 검색으로 찾아,
원래 좌표 2km 안에서 이름에 건물명이 들어간 장소가 나오면 그 좌표로 바꾼다.
결과는 geo_cache.json 에 캐시해 다시 실행할 때 검색을 반복하지 않는다.
"""
import json
import math
import os
import re
import urllib.parse
import urllib.request

AUTO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "geo_cache.json")


def _key():
    # 키는 암호화 저장소에 있다(2026-10-17 .env 에서 옮김). 어느 파이썬에서든 꺼낼 수 있다.
    import sys
    sys.path.insert(0, AUTO)
    from shared.secret_get import get
    k = get("KAKAO_REST_KEY")
    if not k:
        raise SystemExit("암호화 저장소에 KAKAO_REST_KEY 가 없습니다")
    return k


KEY = _key()
cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}


def dist(a, b):
    r = math.pi / 180
    return 2 * 6371000 * math.asin(math.sqrt(math.sin((b[0] - a[0]) * r / 2) ** 2 + math.cos(a[0] * r)
                                             * math.cos(b[0] * r) * math.sin((b[1] - a[1]) * r / 2) ** 2))


def search(q, lat, lon):
    k = f"{q}|{lat:.3f},{lon:.3f}"
    if k not in cache:
        u = "https://dapi.kakao.com/v2/local/search/keyword.json?" + urllib.parse.urlencode(
            {"query": q, "x": lon, "y": lat, "radius": 2000, "sort": "accuracy", "size": 5})
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"Authorization": "KakaoAK " + KEY}), timeout=20))
            cache[k] = [[d["place_name"], float(d["y"]), float(d["x"])] for d in r["documents"]]
        except Exception as e:
            print("  검색 실패:", q, e)
            return []
    return cache[k]


# 설치 위치 문구에서 건물명만: '학생회관 1층 로비' → '학생회관', '본관 지하1층' → '본관'
FLOOR = re.compile(r"(지하)?\s*\d+\s*층.*|지하.*|로비.*|복도.*|입구.*|현관.*|\(.*|내부.*|1F.*|B\d.*", re.I)
BUILDING = re.compile(r"([가-힣A-Za-z0-9]+(관|동|센터|회관|도서관|체육관|병원|기숙사|학사|생활관|청사|별관|본관))")


# 원본 건물명과 지도 장소명이 다른 경우
ALIAS = {"민송도서관": "학술정보원"}


def building(text):
    m = BUILDING.search(FLOOR.sub("", text or "").strip())
    return ALIAS.get(m.group(1), m.group(1)) if m else ""


def core(name):
    return re.sub(r"\s+", "", name)


def refine(items, org_of, place_of):
    """같은 좌표를 공유하는 기관의 항목만 건물명으로 다시 찾는다. 바뀐 건수를 돌려준다."""
    groups = {}
    for x in items:
        groups.setdefault((x["lat"], x["lon"], org_of(x)), []).append(x)
    moved = 0
    for (lat, lon, org), xs in groups.items():
        if len(xs) < 2 and not building(place_of(xs[0])):
            continue
        for x in xs:
            b = building(place_of(x))
            if not b or b in org:
                continue
            org_base = re.sub(r"\(.*?\)|지하.*|\d+층.*", "", org).strip()
            # 건물명과 기관명 앞 두 글자가 모두 들어간 장소만('충청북도청 본관' → '주짓수팜 청주본관' 같은 오답 배제)
            hits = [h for h in search(f"{org_base} {b}", lat, lon)
                    if core(b) in core(h[0]) and core(org_base)[:2] in core(h[0])
                    and dist((lat, lon), (h[1], h[2])) < 2000]
            if hits and dist((lat, lon), hits[0][1:]) > 30:
                x["lat"], x["lon"], x["fix"] = round(hits[0][1], 6), round(hits[0][2], 6), 1
                moved += 1
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    return moved
