"""엑스(X) 게시물을 수집한다. 표준 라이브러리만 쓴다.

X API 는 2026-02 부터 쓴 만큼 돈을 낸다. 실적을 세자고 조회 API 를 때리면 크레딧이
새므로 **호출하지 않는다**. 대신 두 가지를 읽는다.

  1) youtube-shorts-auto/x_posts.json — 올리는 순간 x_post 가 남긴 기록(본문·주소)
  2) youtube-shorts-auto/logs/*.log   — 기록을 남기기 전(2026-10-06 이전) 발행분.
     '게시 완료 … /status/<id>' 줄에서 주소와 날짜만 복원한다(본문은 없다).

본문을 모르는 옛 글의 활동명은 비워 둔다. 리포트가 같은 날 유튜브 제목을 빌려 채운다.
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analytics.common import ROOT_DIR, log, save_part  # noqa: E402

YT_DIR = os.path.join(ROOT_DIR, "channels", "youtube-shorts-auto")
POSTS_LOG = os.path.join(YT_DIR, "x_posts.json")
LOG_GLOB = os.path.join(YT_DIR, "logs", "20*.log")
LINE = re.compile(r"^\[(\d{4}-\d{2}-\d{2}) [\d:]+\].*게시 완료.*?(https://x\.com/\S+/status/(\d+))")


def collect(since):
    items = {}

    for path in sorted(glob.glob(LOG_GLOB)):            # 옛 발행분(본문 없음)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = LINE.match(line)
                if m and m.group(1) >= since:
                    items[m.group(3)] = {"title": "", "date": m.group(1), "type": "게시글",
                                         "source": "엑스", "url": m.group(2)}

    if os.path.exists(POSTS_LOG):                       # 기록이 있으면 본문까지 채운다
        with open(POSTS_LOG, "r", encoding="utf-8") as f:
            for tid, rec in json.load(f).items():
                date = (rec.get("at") or "")[:10]
                if date < since:
                    continue
                items[tid] = {"title": (rec.get("text") or "").split("\n")[0][:90],
                              "date": date, "type": "게시글", "source": "엑스",
                              "url": rec.get("url", f"https://x.com/i/status/{tid}")}

    out = sorted(items.values(), key=lambda x: x["date"], reverse=True)
    return {"account": {"username": "smuds_official"}, "items": out}


if __name__ == "__main__":
    since = sys.argv[1] if len(sys.argv) > 1 else "2026-03-01"
    data = collect(since)
    known = sum(1 for x in data["items"] if x["title"])
    log(f"엑스 게시물 {len(data['items'])}건(본문 있는 것 {known}건)")
    save_part("x", data)
