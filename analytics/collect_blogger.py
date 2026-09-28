"""블로거(blogspot) 게시글을 수집한다. 표준 라이브러리만 쓴다.

구글 블로거는 로그인 없이 공개 피드로 전체 목록을 준다(할당량 없음).
한 번에 최대 500건씩 받고, 그보다 많으면 start-index 로 이어 받는다.

학과 블로그(smuds2026)만 본다. GeoAI 글이 올라가는 geoaina.blogspot.com 은
학과 공식 채널이 아니어서 홍보활동 실적에 넣지 않기로 했다(2026-09-28 결정).
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analytics.common import log, save_part  # noqa: E402

BLOG = "https://smuds2026.blogspot.com"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
PAGE = 200


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def collect(since):
    items, start = [], 1
    title = ""
    while start < 2000:
        feed = _get(f"{BLOG}/feeds/posts/default?alt=json"
                    f"&max-results={PAGE}&start-index={start}")["feed"]
        title = title or feed.get("title", {}).get("$t", "")
        entries = feed.get("entry", [])
        if not entries:
            break
        for e in entries:
            link = next((l["href"] for l in e.get("link", []) if l.get("rel") == "alternate"), "")
            items.append({
                "title": e.get("title", {}).get("$t", "").strip(),
                "date": e.get("published", {}).get("$t", "")[:10],
                "type": "게시글",
                "source": "블로거",
                "url": link,
            })
        if len(entries) < PAGE:
            break
        start += PAGE
    items = [x for x in items if x["date"] >= since]
    items.sort(key=lambda x: x["date"], reverse=True)
    return {"blog": {"title": title, "url": BLOG}, "items": items}


if __name__ == "__main__":
    since = sys.argv[1] if len(sys.argv) > 1 else "2026-03-01"
    data = collect(since)
    log(f"블로거 '{data['blog']['title']}' 게시글 {len(data['items'])}건")
    save_part("blogger", data)
