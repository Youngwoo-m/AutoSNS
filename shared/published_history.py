"""채널별로 이미 올린 글·영상 제목을 한 번에 조회한다 — 중복 방지용 공용 도구(클로드 작업·콘솔 에이전트 공통).

공개 피드만 읽는다(로그인·API 할당량 없음). 표준 라이브러리만 쓴다.
  tistory            na-geoai.tistory.com RSS (개인)
  blogger-personal   geoaina.blogspot.com (개인 GeoAI)
  blogger-dept       smuds2026.blogspot.com · smusafe.blogspot.com (학과)
  naver              blog.naver.com/studs23 (학과)
  youtube-personal   @geoai-safety 채널 RSS
  youtube-dept       학과 유튜브 채널 RSS
  local              기록 파일: 제목 기록(title_history.json), 숏츠 예정표, 클로드 작업 기록, 기술사 작성상태

    python3 shared/published_history.py --query 흙막이 계측 [--channel tistory,youtube-personal] [--days 30] [--limit 30] [--refresh]

출력은 JSON 한 줄: {"count": n, "items": [{"title", "date", "channels": [...], "urls": {채널: 주소}, "planned": 예정표 여부}], "errors": {채널: 이유}}
제목에 질의어가 하나라도 들어 있는 것만(질의가 없으면 최신순 전체). 같은 제목은 한 번만(올라간 채널을 channels 에 모음, 미래 날짜는 planned). 채널별 10분 캐시(~/.cache/autosns-llm/history.json).
파이썬에서: from shared.published_history import history
"""
import argparse
import datetime
import email.utils
import html
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path.home() / ".cache" / "autosns-llm" / "history.json"
TTL = 600
UA = {"User-Agent": "Mozilla/5.0 (smuds-autosns/1.0)"}

BLOGGER = {"blogger-personal": ["https://geoaina.blogspot.com"],
           "blogger-dept": ["https://smuds2026.blogspot.com", "https://smusafe.blogspot.com"]}
YOUTUBE = {"youtube-personal": ("UCbHDlxMFIackeJRwW2iTYew", "geoai-safety"), "youtube-dept": ("UCyB8hWjVghfgzZgj8fwmZrQ", "")}
CHANNELS = ["tistory", "blogger-personal", "blogger-dept", "naver", "youtube-personal", "youtube-dept", "local"]


def _get(url, timeout=20):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def _day(s):
    """여러 날짜 모양을 'YYYY-MM-DD' 로. 못 읽으면 ''."""
    s = (s or "").strip()
    m = re.match(r"(\d{4})-(\d\d)-(\d\d)", s) or re.match(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    try:
        return email.utils.parsedate_to_datetime(s).astimezone().strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return datetime.date.today().isoformat() if "전" in s else ""     # '방금 전'·'5분 전'


def _tistory():
    x = ET.fromstring(_get("https://na-geoai.tistory.com/rss"))
    return [{"title": html.unescape(i.findtext("title") or "").strip(), "url": i.findtext("link") or "",
             "date": _day(i.findtext("pubDate"))} for i in x.iter("item")]


def _blogger(base):
    d = json.loads(_get(f"{base}/feeds/posts/default?alt=json&max-results=50"))
    out = []
    for e in d.get("feed", {}).get("entry", []):
        url = next((l["href"] for l in e.get("link", []) if l.get("rel") == "alternate"), "")
        out.append({"title": (e.get("title", {}).get("$t") or "").strip(), "url": url,
                    "date": _day(e.get("published", {}).get("$t"))})
    return out


def _naver():
    import urllib.parse
    s = _get("https://blog.naver.com/PostTitleListAsync.naver?blogId=studs23&viewdate=&currentPage=1"
             "&categoryNo=0&parentCategoryNo=&countPerPage=30").decode("utf-8", "replace")
    return [{"title": urllib.parse.unquote_plus(t).strip(), "url": f"https://blog.naver.com/studs23/{n}", "date": _day(d)}
            for n, t, d in re.findall(r'"logNo":"(\d+)".*?"title":"(.*?)".*?"addDate":"(.*?)"', s)]


def _youtube(cid, handle=""):
    ns = {"a": "http://www.w3.org/2005/Atom"}
    try:
        x = ET.fromstring(_get(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"))
        return [{"title": (e.findtext("a:title", "", ns) or "").strip(),
                 "url": (e.find("a:link", ns).get("href") if e.find("a:link", ns) is not None else ""),
                 "date": _day(e.findtext("a:published", "", ns))} for e in x.findall("a:entry", ns)]
    except Exception:
        if not handle:
            raise
    # RSS 가 오래 500 을 주는 채널(@geoai-safety): 채널 화면(숏츠·동영상)의 videoId 를 모아 oEmbed 로 제목을 읽는다.
    # 날짜는 알 수 없다(빈 값). 비공개·예약 영상은 공개 화면에 없어 안 보인다.
    import concurrent.futures
    import urllib.parse
    ids = []
    for tab in ("shorts", "videos"):
        page = _get(f"https://www.youtube.com/@{handle}/{tab}").decode("utf-8", "ignore")
        ids += re.findall(r'"videoId":"([\w-]{11})"', page)
    ids = list(dict.fromkeys(ids))[:40]

    def one(v):
        try:
            u = f"https://www.youtube.com/watch?v={v}"
            d = json.loads(_get("https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(u, safe=""), 15))
            return {"title": (d.get("title") or "").strip(), "url": f"https://www.youtube.com/shorts/{v}", "date": ""}
        except Exception:
            return None
    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        return [r for r in ex.map(one, ids) if r and r["title"]]


def _local():
    out = []

    def add(title, date="", url=""):
        if isinstance(title, str) and title.strip():
            out.append({"title": title.strip(), "url": url, "date": _day(date)})

    for f in ("naver-blog-auto/title_history.json", "youtube-shorts-auto/title_history.json"):
        try:
            for t in json.loads((ROOT / f).read_text()):
                add(t if isinstance(t, str) else (t or {}).get("title"))
        except (OSError, ValueError):
            pass
    try:
        for x in json.loads((ROOT / "youtube-shorts-auto/publish_schedule.json").read_text()):
            add(x.get("title"), x.get("date") or x.get("publish_at") or "")
    except (OSError, ValueError, AttributeError):
        pass
    for f in sorted((ROOT / "GeoAI_NA/claude-jobs/state").glob("*.jsonl")):
        for line in f.read_text(errors="ignore").splitlines()[-200:]:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("status") == "published":
                add(r.get("title"), r.get("at", ""), next(iter((r.get("urls") or {}).values()), ""))
    for f in (ROOT / "GeoAI_NA").glob("*engineer-writing*/**/작성상태.json"):
        try:
            r = json.loads(f.read_text())
            add(r.get("제목"), r.get("작성일", ""))
        except (OSError, ValueError, AttributeError):
            pass
    return out


def _fetch(channel):
    if channel == "tistory":
        return _tistory()
    if channel in BLOGGER:
        out = []
        for base in BLOGGER[channel]:
            try:
                out += _blogger(base)
            except Exception:
                if base == BLOGGER[channel][0]:
                    raise
        return out
    if channel == "naver":
        return _naver()
    if channel in YOUTUBE:
        return _youtube(*YOUTUBE[channel])
    if channel == "local":
        return _local()
    raise ValueError(f"없는 채널: {channel}")


def _cache():
    try:
        return json.loads(CACHE.read_text())
    except (OSError, ValueError):
        return {}


def history(query="", channels=None, days=0, limit=30, refresh=False):
    """{count, items, errors}. channels 가 없으면 전부. query 는 공백으로 나눈 낱말 중 하나라도 든 제목."""
    chans = [c for c in (channels or CHANNELS) if c in CHANNELS]
    cache, errors, items = ({} if refresh else _cache()), {}, []
    dirty = False
    for c in chans:
        hit = cache.get(c)
        if hit and time.time() - hit["at"] < TTL:
            rows = hit["rows"]
        else:
            try:
                rows = _fetch(c)
                cache[c] = {"at": time.time(), "rows": rows}
                dirty = True
            except Exception as e:
                errors[c] = f"{type(e).__name__}: {str(e)[:100]}"
                rows = (hit or {}).get("rows", [])       # 못 읽으면 지난 결과라도
        items += [{**r, "channel": c} for r in rows]
    if dirty:
        try:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(cache, ensure_ascii=False))
        except OSError:
            pass
    words = [w for w in re.split(r"\s+", query or "") if len(w) > 1]
    if words:
        items = [r for r in items if any(w in r["title"] for w in words)]
    if days:
        since = (datetime.date.today() - datetime.timedelta(days=int(days))).isoformat()
        items = [r for r in items if not r["date"] or r["date"] >= since]
    today = datetime.date.today().isoformat()
    merged = {}
    for r in sorted(items, key=lambda r: r["date"] or "", reverse=True):
        key = re.sub(r"\s+", " ", r["title"])
        if not r["title"]:
            continue
        m = merged.setdefault(key, {"title": r["title"], "date": r["date"], "channels": [], "urls": {}})
        if r["channel"] not in m["channels"]:
            m["channels"].append(r["channel"])
        if r["url"] and r["channel"] not in m["urls"]:
            m["urls"][r["channel"]] = r["url"]
        if r["date"] and not m["date"]:
            m["date"] = r["date"]
    out = list(merged.values())
    for m in out:
        m["planned"] = bool(m["date"] and m["date"] > today)        # 예정표(아직 안 올라간 것)
    out.sort(key=lambda m: (m["planned"], -int((m["date"] or "0000-00-00").replace("-", ""))))
    return {"count": len(out), "items": out[:int(limit)], "errors": errors}


def main():
    ap = argparse.ArgumentParser(description="채널별 지난 글·영상 제목 조회(중복 방지)")
    ap.add_argument("--query", nargs="*", default=[], help="낱말들(하나라도 든 제목)")
    ap.add_argument("--channel", default="", help=f"쉼표로 구분: {', '.join(CHANNELS)}")
    ap.add_argument("--days", type=int, default=0)
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--refresh", action="store_true", help="캐시를 무시하고 다시 읽기")
    a = ap.parse_args()
    r = history(" ".join(a.query), [c for c in a.channel.split(",") if c] or None, a.days, a.limit, a.refresh)
    print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
