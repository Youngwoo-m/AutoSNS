"""수집 스크립트가 함께 쓰는 경로·유틸. (표준 라이브러리만 사용)

수집은 소스마다 필요한 라이브러리가 달라 인터프리터를 나눠 쓴다.
  유튜브   → youtube-shorts-auto/.venv  (google-api-python-client)
  인스타   → insta-cardnews/.venv        (selenium)
  블로그·홈페이지 → 시스템 python3       (표준 라이브러리만)
그래서 각 수집기는 서로를 import 하지 않고, 결과를 snapshots/ 에 json 으로만 주고받는다.
"""
import json
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
SNAP_DIR = os.path.join(BASE_DIR, "snapshots")   # 수집 결과(주차별 비교용으로 보관)
OUT_DIR = os.path.join(BASE_DIR, "out")          # 생성된 리포트
LOGS_DIR = os.path.join(BASE_DIR, "logs")

for d in (SNAP_DIR, OUT_DIR, LOGS_DIR):
    os.makedirs(d, exist_ok=True)


def log(msg):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    path = os.path.join(LOGS_DIR, f"{datetime.now():%Y-%m}.log")
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def save_part(name, data, allow_empty=False):
    """수집기 하나의 결과를 snapshots/parts/<name>.json 에 쓴다.

    수집이 빈손으로 끝났는데 직전 결과가 남아 있으면 덮어쓰지 않는다. 세션 만료나
    일시적 오류로 0건이 나올 때 멀쩡한 과거 수집분이 날아가는 걸 막는다.

    allow_empty=True 는 0건 자체가 뜻이 있는 수집기용이다(서치콘솔은 '이번 주 검색
    노출 없음'이 사실이고, 그걸 옛 수치로 가리면 안 된다).
    """
    d = os.path.join(SNAP_DIR, "parts")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{name}.json")
    if not data.get("items") and not allow_empty:
        old = load_part(name)
        if old and old.get("items"):
            log(f"{name}: 수집 0건 — 직전 결과({len(old['items'])}건)를 유지한다")
            return path
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    log(f"{name}: {len(data.get('items', []))}건 저장 → {os.path.relpath(path, ROOT_DIR)}")
    return path


def load_part(name):
    path = os.path.join(SNAP_DIR, "parts", f"{name}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
