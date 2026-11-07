"""룰렛 앱(geoai-site/dinner)용 주변 안전시설 데이터 만들기 — 충북 AED·민방위 대피소.

공공데이터포털 API 는 브라우저에서 직접 부를 수 없어(CORS 없음) 미리 받아 정적 JSON 으로 둔다.
키는 암호화 저장소의 DATA_GO_KR_KEY. 결과: geoai-site/dinner/data/{aed,shelter}.json
배포 전에 한 번씩 다시 실행하면 최신으로 갱신된다.

  python3 geoai-data/fetch_safety.py
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request

AUTO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(AUTO, "geoai-site", "dinner", "data")
REGION = "충청북도"


def key():
    # 키는 암호화 저장소에 있다(2026-10-17 .env 에서 옮김). 어느 파이썬에서든 꺼낼 수 있다.
    import sys
    sys.path.insert(0, AUTO)
    from shared.secret_get import get
    k = get("DATA_GO_KR_KEY")
    if not k:
        raise SystemExit("암호화 저장소에 DATA_GO_KR_KEY 가 없습니다")
    return k


KEY = key()


def get(url, params, tries=3):
    q = urllib.parse.urlencode({"serviceKey": KEY, **params})
    for i in range(tries):
        try:
            return urllib.request.urlopen(url + "?" + q, timeout=90).read().decode("utf-8", "replace")
        except Exception as e:
            if i == tries - 1:
                raise
            print("  재시도:", e); time.sleep(3)


def tag(item, name):
    m = re.search(f"<{name}>(.*?)</{name}>", item, re.S)
    return m.group(1).strip() if m else ""


def fetch_aed():
    url = "https://apis.data.go.kr/B552657/AEDInfoInqireService/getEgytAedManageInfoInqire"
    rows, page = [], 1
    while True:
        b = get(url, {"Q0": REGION, "pageNo": page, "numOfRows": 500})
        items = re.findall(r"<item>(.*?)</item>", b, re.S)
        for it in items:
            try:
                lat, lon = float(tag(it, "wgs84Lat")), float(tag(it, "wgs84Lon"))
            except ValueError:
                continue
            days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
            always = all(tag(it, d + "SttTme") in ("0000", "") and tag(it, d + "EndTme") in ("2400", "")
                         for d in days)
            rows.append({"n": tag(it, "org"), "p": tag(it, "buildPlace"), "a": tag(it, "buildAddress"),
                         "lat": round(lat, 6), "lon": round(lon, 6), "h24": always,
                         "mon": f"{tag(it, 'monSttTme')}-{tag(it, 'monEndTme')}"})
        total = int((re.findall(r"<totalCount>(\d+)", b) or ["0"])[0])
        print(f"AED {page}쪽 누적 {len(rows)}/{total}")
        if page * 500 >= total or not items:
            break
        page += 1
    return rows


def fetch_shelter():
    url = "https://apis.data.go.kr/1741000/civil_defense_shelter_info/info"
    rows, page = [], 1
    while True:
        # numOfRows 를 크게 줘도 100건씩만 온다
        body = json.loads(get(url, {"pageNo": page, "numOfRows": 100, "returnType": "json"}))["response"]["body"]
        items = (body.get("items") or {}).get("item") or []
        for it in items:
            addr = it.get("ROAD_NM_WHOL_ADDR") or it.get("LCTN_WHOL_ADDR") or ""
            if not addr.startswith(REGION) or it.get("OPER_STTS") != "사용중":
                continue
            try:  # 좌표 항목명 오타(LOT_EPST4326)는 원본 그대로
                lat, lon = float(it["LAT_EPSG4326"]), float(it["LOT_EPST4326"])
            except (KeyError, TypeError, ValueError):
                continue
            rows.append({"n": it.get("FCLT_NM", ""), "a": addr, "lat": round(lat, 6), "lon": round(lon, 6),
                         "ug": it.get("FCLTLOC_GRND_UDGD", ""), "cap": it.get("MAX_ACTC_PERNE", "")})
        total = int(body.get("totalCount", 0))
        if page % 20 == 0:
            print(f"대피소 {page}쪽 (전국 {total}) 충북 누적 {len(rows)}")
        if page * 100 >= total or not items:
            break
        page += 1
    return rows


def save(name, rows):
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, name)
    meta = {"region": REGION, "updated": time.strftime("%Y-%m-%d"), "count": len(rows)}
    with open(p, "w", encoding="utf-8") as f:
        json.dump({**meta, "items": rows}, f, ensure_ascii=False, separators=(",", ":"))
    print(p, len(rows), f"{os.path.getsize(p) // 1024}KB")


def shelter_org(x):
    # 주소 괄호 속 건물명이 있으면 그것(예: '세명대학교'), 없으면 이름 첫 단어
    m = re.search(r",\s*([^,()]+)$|\(([^()]*?)\)$", x["a"])
    tail = (m.group(1) or m.group(2)).split(",")[-1].strip() if m else ""
    return tail if tail and not re.search(r"[동리]$", tail) else x["n"].split()[0]


if __name__ == "__main__":
    from refine_coords import refine
    aed = fetch_aed()
    print("AED 건물 좌표 보정", refine(aed, lambda x: x["n"], lambda x: x["p"]))
    save("aed.json", aed)
    sh = fetch_shelter()
    print("대피소 건물 좌표 보정", refine(sh, shelter_org, lambda x: x["n"]))
    save("shelter.json", sh)
