"""최근 N주(기본 4주) 구간에 올라간 항목만 채널별로 집계한다. (표준 라이브러리만)

누적 조회수만 보면 최근 변화를 알 수 없어, 항목의 게시일 기준으로 구간을 자른다.
사용: python3 window_report.py [주수]   (기본 4)
"""
import statistics
import sys
from datetime import date, timedelta

from common import load_part

PARTS = ["youtube", "instagram", "blog", "threads"]


def main(weeks=4):
    today = date.today()
    cur0 = (today - timedelta(weeks=weeks)).isoformat()
    prev0 = (today - timedelta(weeks=2 * weeks)).isoformat()
    print(f"구간: 최근 {weeks}주({cur0}~) vs 직전 {weeks}주({prev0}~{cur0})  ※ 게시일 기준, 조회는 현재 누적")
    for name in PARTS:
        part = load_part(name)
        if not part:
            print(f"- {name}: 데이터 없음")
            continue
        items = [i for i in part["items"] if i.get("date") and i.get("views") is not None]
        cur = [i for i in items if i["date"] >= cur0]
        prev = [i for i in items if prev0 <= i["date"] < cur0]

        def stat(xs):
            v = [i["views"] for i in xs]
            return f"{len(v)}건 합{sum(v)} 중앙{statistics.median(v) if v else 0:g}"

        print(f"- {name}: 최근 {stat(cur)} | 직전 {stat(prev)}")
        for i in sorted(cur, key=lambda i: -i["views"])[:3]:
            print(f"    {i['views']:>5} {i['date']} {i['title'][:40]}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 4)
