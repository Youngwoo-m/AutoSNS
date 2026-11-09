"""재난 소식 띠(geoai-na /fn/alerts)가 모은 재난뉴스를 숏츠 뉴스 후보에 참고로 더한다(2026-11-09 사용자 지정).

저녁 룰렛·셔틀 앱 띠에 흐르는 것과 같은 목록이다(띠 자체를 영상에 넣는 것이 아님). 함수 쪽에서 이미 걸렀다:
  - 제천·충북 재난·사고 기사(최근 3일, 행사·블로그 글 제외) 최대 4건 + 전국 큰 재난 기사(최근 1일) 최대 2건
  - (warnings=True 일 때만) 기상청 특보 현황 중 충청북도가 든 특보·예비특보 줄
fetch_news() 가 config.news.alerts=true 일 때 부른다. 실패하면 빈 목록(수집은 그대로 간다).
반환 형식은 fetch_news 와 같다: [{title, link, source, published(dt), published_str, via}]
"""
import json
import urllib.request
from datetime import datetime, timedelta, timezone

URL = "https://geoai-na.web.app/fn/alerts"
KMA = "https://www.weather.go.kr/w/special-report/overall.do"


def fetch_alerts(url=URL, within_days=3, warnings=False, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "AutoSNS-dept"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=within_days)
    out = []
    for x in data.get("items") or []:
        kind, text = x.get("kind"), (x.get("text") or "").strip()
        if not text:
            continue
        if kind == "뉴스":
            try:
                pub = datetime.fromisoformat(x["date"].replace("Z", "+00:00"))
            except (KeyError, ValueError, AttributeError):
                pub = now
            if pub < cutoff:
                continue
            out.append({"title": text, "link": x.get("url") or "", "source": x.get("source") or "",
                        "published": pub, "published_str": pub.astimezone().strftime("%Y-%m-%d"), "via": "alerts"})
        elif kind in ("특보", "예비특보") and warnings:
            label = "충북 기상특보" if kind == "특보" else "충북 예비특보"
            out.append({"title": f"[{label}] {text}", "link": x.get("url") or KMA, "source": "기상청",
                        "published": now, "published_str": now.astimezone().strftime("%Y-%m-%d"), "via": "alerts"})
    return out


if __name__ == "__main__":
    for it in fetch_alerts():
        print(f"[{it['published_str']}] {it['title']}  ({it['source']})")
