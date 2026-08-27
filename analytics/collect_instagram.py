"""인스타그램 게시물 목록을 수집한다. insta-cardnews/.venv 로 실행할 것.

발행에 쓰는 크롬 프로필(로그인 세션)을 그대로 열어 읽기만 한다. 올리거나 지우지 않는다.
공개 web_profile_info 엔드포인트는 메타 쪽 오류로 응답하지 않아, 프로필 페이지에서
user id 를 뽑은 뒤 로그인 상태로 피드 API 를 호출한다.

세션이 풀렸으면 수집을 건너뛰고 빈 결과를 남긴다(로그인은 사람이 직접 해야 한다).
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

JS_FEED = """
const cb = arguments[arguments.length-1], uid = arguments[0], maxid = arguments[1];
let u = '/api/v1/feed/user/'+uid+'/?count=50';
if (maxid) u += '&max_id='+maxid;
fetch(u, {headers:{'X-IG-App-ID':'%s'}})
  .then(r => r.json()).then(j => cb(JSON.stringify(j))).catch(e => cb('ERR '+e));
""" % APP_ID


def _kind(it):
    """1=단일이미지, 2=영상(릴스), 8=캐러셀. 릴스는 60초 이하면 숏츠."""
    mt = it.get("media_type")
    if mt == 2:
        return "숏츠" if (it.get("video_duration") or 0) <= 60 else "영상"
    if mt == 8:
        return "카드뉴스"          # 캐러셀은 대부분 제작 카드. 행사 사진은 사후 보정.
    return "이미지"


def collect(since):
    d = build_driver(headless=False)
    d.set_script_timeout(60)
    try:
        d.get(f"https://www.instagram.com/{USER}/")
        time.sleep(5)
        src = d.page_source
        m = (re.search(r'"profile_id":"(\d+)"', src) or re.search(r'"user_id":"(\d+)"', src)
             or re.search(r'"owner":\{"id":"(\d+)"', src))
        if not m:
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

        items, maxid, page = [], None, 0
        while page < 20:
            raw = d.execute_async_script(JS_FEED, uid, maxid)
            if raw.startswith("ERR"):
                log(f"피드 조회 오류: {raw[:120]}")
                break
            j = json.loads(raw)
            oldest = "9999"
            for it in j.get("items", []):
                date = datetime.fromtimestamp(it["taken_at"], timezone.utc).strftime("%Y-%m-%d")
                oldest = min(oldest, date)
                cap = ((it.get("caption") or {}).get("text") or "").strip()
                items.append({
                    "title": cap.split("\n")[0][:90],
                    "date": date, "type": _kind(it),
                    "caption_empty": not cap,
                    "pages": len(it.get("carousel_media") or []),
                    "seconds": round(it.get("video_duration") or 0),
                    "likes": it.get("like_count") or 0,
                    "comments": it.get("comment_count") or 0,
                    "views": it.get("play_count") or it.get("view_count") or 0,
                    "url": f"https://www.instagram.com/p/{it.get('code')}/",
                })
            if oldest < since or not j.get("more_available"):
                break
            maxid = j.get("next_max_id")
            page += 1
            time.sleep(1.5)
        return {"profile": prof, "items": [x for x in items if x["date"] >= since]}
    finally:
        d.quit()


if __name__ == "__main__":
    since = sys.argv[1] if len(sys.argv) > 1 else "2026-03-01"
    data = collect(since)
    log(f"인스타 팔로워 {data['profile'].get('followers', '?')}명, 게시물 {len(data['items'])}건")
    save_part("instagram", data)
