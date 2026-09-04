"""인스타그램 게시물 목록을 수집한다. insta-cardnews/.venv 로 실행할 것.

발행에 쓰는 크롬 프로필(로그인 세션)을 그대로 열어 읽기만 한다. 올리거나 지우지 않는다.

수집 경로는 둘이다.
  1) 피드 API `/api/v1/feed/user/<uid>/` — 한 번에 50건씩. 빠르지만 인스타가 막을 때가 있다
     (2026-09 확인: 로그인 상태여도 HTML 을 돌려준다).
  2) 프로필 그리드에서 게시물 코드를 긁고 `/api/v1/media/<pk>/info/` 로 하나씩 조회.
     느리지만 1) 이 막혀도 동작한다. 코드→pk 는 base64(64진법) 변환이다.

세션이 풀렸으면 수집을 건너뛰고 빈 결과를 남긴다(로그인은 사람이 직접 해야 한다).
빈 결과는 직전 수집분을 덮어쓰지 않는다(common.save_part).
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "insta-cardnews"))
from analytics.common import log, save_part      # noqa: E402
from post_instagram import build_driver          # noqa: E402

USER = "smu_ds_official"
APP_ID = "936619743392459"
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"

JS_FEED = """
const cb = arguments[arguments.length-1], uid = arguments[0], maxid = arguments[1];
let u = '/api/v1/feed/user/'+uid+'/?count=50';
if (maxid) u += '&max_id='+maxid;
fetch(u, {headers:{'X-IG-App-ID':'%s'}})
  .then(r => r.text()).then(t => cb(t)).catch(e => cb('ERR '+e));
""" % APP_ID

JS_MEDIA = """
const cb = arguments[arguments.length-1];
fetch('/api/v1/media/'+arguments[0]+'/info/', {headers:{'X-IG-App-ID':'%s'}})
  .then(r => r.json()).then(j => cb(JSON.stringify((j.items||[])[0]||{})))
  .catch(e => cb('ERR '+e));
""" % APP_ID


def shortcode_to_pk(code):
    n = 0
    for ch in code:
        n = n * 64 + ALPHABET.index(ch)
    return n


def _row(it):
    """미디어 하나를 리포트가 쓰는 형태로 정리한다.
    media_type 1=단일이미지 2=영상(릴스) 8=캐러셀. 릴스는 60초 이하면 숏츠."""
    mt = it.get("media_type")
    dur = it.get("video_duration") or 0
    if mt == 2:
        kind = "숏츠" if dur <= 60 else "영상"
    elif mt == 8:
        kind = "카드뉴스"
    else:
        kind = "이미지"
    cap = ((it.get("caption") or {}).get("text") or "").strip()
    return {
        "title": cap.split("\n")[0][:90],
        "date": datetime.fromtimestamp(it["taken_at"], timezone.utc).strftime("%Y-%m-%d"),
        "type": kind,
        "caption_empty": not cap,
        "pages": len(it.get("carousel_media") or []),
        "seconds": round(dur),
        "likes": it.get("like_count") or 0,
        "comments": it.get("comment_count") or 0,
        "views": it.get("play_count") or it.get("view_count") or 0,
        "url": f"https://www.instagram.com/p/{it.get('code')}/",
    }


def _via_feed(d, uid, since):
    """피드 API 경로. 막혀 있으면 None 을 돌려 그리드 경로로 넘긴다."""
    items, maxid, page = [], None, 0
    while page < 20:
        raw = d.execute_async_script(JS_FEED, uid, maxid)
        if raw.startswith("ERR") or raw.lstrip().startswith("<"):
            return None                     # HTML 이 오면 막힌 것
        j = json.loads(raw)
        got = j.get("items")
        if got is None:
            return None
        for it in got:
            items.append(_row(it))
        if not items or min(x["date"] for x in items) < since or not j.get("more_available"):
            break
        maxid = j.get("next_max_id")
        page += 1
        time.sleep(1.5)
    return items


def _via_grid(d, since):
    """프로필 그리드를 훑어 코드를 모으고 하나씩 조회한다."""
    items, seen, stale, rounds = [], set(), 0, 0
    while rounds < 40 and stale < 5:
        codes = [c for c in re.findall(r'(?:instagram\.com)?/(?:p|reel)/([A-Za-z0-9_-]{5,})/',
                                       d.page_source) if c not in seen]
        for c in codes:
            seen.add(c)
            raw = d.execute_async_script(JS_MEDIA, str(shortcode_to_pk(c)))
            if raw.startswith("ERR"):
                continue
            it = json.loads(raw)
            if not it.get("taken_at"):
                continue
            row = _row(it)
            items.append(row)
            if row["date"] < since:
                stale += 1                  # 고정 게시물 때문에 한 건으로 끊지 않는다
            time.sleep(0.25)
        if stale >= 5:
            break
        d.execute_script("window.scrollBy(0, document.body.scrollHeight);")
        time.sleep(2.5)
        rounds += 1
        if not codes and rounds > 2:
            break                            # 더 이상 새 코드가 없으면 끝
    return items


def collect(since):
    d = build_driver(headless=False)
    d.set_script_timeout(60)
    try:
        d.get(f"https://www.instagram.com/{USER}/")
        time.sleep(8)
        src = d.page_source
        m = (re.search(r'"profile_id":"(\d+)"', src) or re.search(r'"user_id":"(\d+)"', src)
             or re.search(r'"owner":\{"id":"(\d+)"', src))
        cookies = {c["name"] for c in d.get_cookies()}
        if not m or "sessionid" not in cookies:
            log("인스타 세션이 풀린 것으로 보임 — 수집 건너뜀 (직접 로그인 필요)")
            return {"profile": {}, "items": [], "skipped": "no_session"}
        uid = m.group(1)

        prof = {"username": USER, "uid": uid}
        og = re.search(r'<meta property="og:description" content="([^"]{0,200})"', src)
        if og:
            f = re.search(r"팔로워 ([\d,]+)명", og.group(1))
            p = re.search(r"게시물 ([\d,]+)개", og.group(1))
            if f:
                prof["followers"] = int(f.group(1).replace(",", ""))
            if p:
                prof["posts"] = int(p.group(1).replace(",", ""))

        items = _via_feed(d, uid, since)
        if items is None:
            log("피드 API 가 막혀 그리드 경로로 수집한다(느림)")
            items = _via_grid(d, since)
        items = [x for x in items if x["date"] >= since]
        items.sort(key=lambda x: x["date"], reverse=True)
        return {"profile": prof, "items": items}
    finally:
        d.quit()


if __name__ == "__main__":
    since = sys.argv[1] if len(sys.argv) > 1 else "2026-03-01"
    data = collect(since)
    log(f"인스타 팔로워 {data['profile'].get('followers', '?')}명, 게시물 {len(data['items'])}건")
    save_part("instagram", data)
