"""캡션이 빈 채로 올라간 릴을 찾아 원본 캡션을 되살린 captions.json 을 만든다.

빈 캡션은 발행 직후 보완(post_instagram._fix_caption_after_publish)이 실패했을 때 남는다.
ig_caption_restore.py 가 채워 넣지만 코드→캡션 매핑 파일을 사람이 만들어야 했다.
그 매핑을 발행 기록에서 되살려 자동으로 만든다.

캡션 원문은 지어내지 않는다. 발행 순간 post_instagram 이 남긴 caption_log.json
(게시물코드 → 그때 넣은 캡션)에서 그대로 가져온다. 날짜로 발행 기록을 추측하는
방식은 같은 날 영상이 둘이면 엉뚱한 캡션을 넣게 돼 쓰지 않는다. 기록이 없는
옛 게시물은 건너뛰고 목록만 남긴다(사람이 판단할 몫).

사용: python build_caption_fixlist.py [최근 N일=14] [출력=captions_auto.json]
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

from common import BASE_DIR, load_config, log
from post_instagram import CAPTION_LOG, build_driver

APP_ID = "936619743392459"
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"

JS_MEDIA = """
const cb = arguments[arguments.length-1];
fetch('/api/v1/media/'+arguments[0]+'/info/', {headers:{'X-IG-App-ID':'%s'}})
  .then(r => r.json()).then(j => {const m=(j.items||[])[0]||{};
    cb(JSON.stringify({code:m.code, taken_at:m.taken_at, mt:m.media_type,
                       cap:((m.caption||{}).text||'')}));})
  .catch(e => cb('ERR '+e));
""" % APP_ID


def shortcode_to_pk(code):
    n = 0
    for ch in code:
        n = n * 64 + ALPHABET.index(ch)
    return n


def caption_for(code, recorded):
    """발행 때 남긴 기록에서 캡션을 꺼낸다. 없으면 (None, 사유)."""
    hit = recorded.get(code)
    if not hit:
        return None, "발행 기록 없음(캡션 기록 이전 게시물)"
    cap = (hit.get("caption") or "").strip()
    if not cap:
        return None, "기록된 캡션이 비어 있음"
    return cap, f"기록 {hit.get('at', '')}"


def main(argv):
    days = int(argv[0]) if argv and argv[0].isdigit() else 14
    out = next((a for a in argv if a.endswith(".json")), "captions_auto.json")
    cfg = load_config()
    user = cfg.get("instagram", {}).get("username", "smu_ds_official")
    recorded = {}
    if os.path.exists(CAPTION_LOG):
        with open(CAPTION_LOG, "r", encoding="utf-8") as f:
            recorded = json.load(f)
    log(f"캡션 기록 {len(recorded)}건 보유")
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    d = build_driver(headless=False)
    d.set_script_timeout(60)
    found, skipped = {}, []
    try:
        d.get(f"https://www.instagram.com/{user}/")
        time.sleep(8)
        codes = []
        for _ in range(4):
            for c in re.findall(r"(?:instagram\.com)?/(?:p|reel)/([A-Za-z0-9_-]{5,})/", d.page_source):
                if c not in codes:
                    codes.append(c)
            d.execute_script("window.scrollBy(0, document.body.scrollHeight);")
            time.sleep(2.5)
        log(f"프로필에서 게시물 {len(codes)}건 확인")

        for c in codes:
            raw = d.execute_async_script(JS_MEDIA, str(shortcode_to_pk(c)))
            if raw.startswith("ERR"):
                continue
            m = json.loads(raw)
            if not m.get("taken_at"):
                continue
            date = datetime.fromtimestamp(m["taken_at"], timezone.utc).strftime("%Y-%m-%d")
            if date < since:
                break
            if m.get("cap", "").strip():
                continue
            cap, why = caption_for(c, recorded)
            if cap:
                found[c] = cap
                log(f"  빈 캡션 {c}({date}) ← {why}")
            else:
                skipped.append((c, date, why))
                log(f"  빈 캡션 {c}({date}) — 복원 못 함: {why}")
            time.sleep(0.25)
    finally:
        d.quit()

    with open(os.path.join(BASE_DIR, out), "w", encoding="utf-8") as f:
        json.dump(found, f, ensure_ascii=False, indent=1)
    log(f"복원 대상 {len(found)}건 → {out} (판단 보류 {len(skipped)}건)")
    return 0 if found or not skipped else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
