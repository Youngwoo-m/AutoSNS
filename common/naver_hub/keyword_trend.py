"""글 키워드 후보의 네이버 검색량을 견줘 본다(데이터랩 검색어트렌드).

    python3 common/naver_hub/keyword_trend.py "건설안전기술사" "건축시공기술사" "거푸집 동바리"
후보마다 한 그룹(최대 5개)으로 최근 12개월 월별 추이를 조회해, 후보 중 가장 큰 값을 100 으로 둔 상대값을 낸다.
(데이터랩 값은 한 번 조회 안에서만 비교된다. 후보를 바꾸면 기준이 달라진다.)
키는 secret_env 에서 읽고 출력하지 않는다.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "common"))

from naver_hub import naver_hub as hub  # noqa: E402
from shared import secret_env  # noqa: E402

KEYS = (hub.ID_KEY, hub.SECRET_KEY, hub.PROVIDER_KEY)


def _dotenv():
    f = ROOT / ".env"
    out = {}
    if f.exists():
        for line in f.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() in KEYS:
                out[k.strip()] = v.strip().strip("\"'")
    return out


def compare(terms, months=12):
    env = {**_dotenv(), **{k: secret_env.get(k) for k in KEYS if secret_env.get(k)}}
    env.update({k: v for k, v in _dotenv().items() if k == hub.PROVIDER_KEY})  # 제공처는 .env 우선
    end = date.today().replace(day=1) - timedelta(days=1)   # 지난달 말
    start = (end.replace(day=1) - timedelta(days=30 * (months - 1))).replace(day=1)
    groups = [{"groupName": t, "keywords": [t]} for t in terms]
    return hub.search_trend(env, groups, start.isoformat(), end.isoformat(), "month")


def main(argv):
    if not 1 <= len(argv) <= 5:
        raise SystemExit("후보를 1~5개 주세요")
    try:
        series = compare(argv)
    except hub.HubError as e:
        raise SystemExit(f"조회 실패: {e}")
    for s in series:
        data = s.get("data") or []
        vals = [d.get("ratio", 0) for d in data]
        avg = sum(vals) / len(vals) if vals else 0
        last = vals[-3:] if vals else []
        print(f"{s.get('title')}: 평균 {avg:.1f} · 최근3개월 {last}")


if __name__ == "__main__":
    main(sys.argv[1:])
