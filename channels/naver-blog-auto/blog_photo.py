"""Blogger 글 본문에 실사 사진(자료사진) 한 장을 넣는다 — 두 블로그 공용.

그동안 학과 블로그 글은 이미지가 하나도 없었고(브리핑·진로·자격증), GeoAI 글도 그려
만든 배너·도식뿐이었다. 글 주제에 맞는 무료 실사 사진을 Pexels(없으면 Pixabay)에서
찾아 우리 저장소(CDN)에 다시 올리고, 본문 도입부 뒤에 넣는다. 공급처는 글마다 번갈아
먼저 찾는다(직전 사진이 Pexels 면 이번엔 Pixabay 부터) — 한 곳만 쓰면 사진 풀이 좁고
분위기가 비슷한 사진이 반복된다. 먼저 찾은 곳에 맞는 사진이 없으면 다른 곳으로 넘어간다.

주의 — 자료사진임을 반드시 밝힌다. 브리핑은 실제 사고를 다루는데, 그 옆의 사진이
현장 사진처럼 읽히면 독자를 속이는 셈이다. 그래서 캡션 첫머리는 늘 '자료사진'이고,
검색어도 특정 사건·장소·인물이 아니라 일반적인 장면으로 만든다.

실패하면 조용히 빈 문자열을 준다 — 사진이 없어도 글은 나간다.
설정: config.stock_photo.enabled(기본 True). 키는 config.pexels / config.pixabay.
"""
import html
import json
import os
import re
import sys
from datetime import datetime

from common import BASE_DIR, POSTS_DIR, load_config, log

sys.path.insert(0, os.path.dirname(os.path.dirname(BASE_DIR)))
from shared import stock_photo  # noqa: E402
from shared.stock_video import keys_from  # noqa: E402

HISTORY = os.path.join(BASE_DIR, "stock_photo_history.json")
KEEP = 400                       # 최근 몇 장까지 다시 쓰지 않을지

SYSTEM = """You write stock-photo search queries (Pexels, Pixabay) for a Korean disaster-safety blog post.

<goal>
Return 3 English queries whose words will literally appear in the tags or caption of a matching photo.
A photo is accepted only if its tags contain at least 2 words of the query, so every word must be a
concrete, photographable noun or adjective.
</goal>

<rules>
- Output exactly 3 lines, one query per line, 2 to 4 words each. No numbering, quotes or other text.
- Line 1: the most specific photographable scene for the topic. Line 2: a close alternative.
  Line 3: broader but still on topic.
- Use plain visual words a photographer would tag: objects, workers, equipment, places, weather.
  Prefer nouns that only fit this topic.
- NEVER use words with an unrelated common meaning on stock sites: station, monitor, screen, control,
  system, network, model, plant, cell, data, digital, concept, technology.
  Write the specific thing instead: "air quality sensor" not "air quality monitoring station";
  "weather radar dome" not "radar monitor screen".
- NEVER name a specific event, date, place name, organisation, brand or real person.
  The photo is labelled as an illustrative stock photo.
- NEVER depict the accident or disaster moment, injury, victims, gore, or a person in danger
  (falling, crash, collapse, explosion, drowning, flames, fire or smoke from a fire, flood water rushing). The post may be about a real
  accident where people died; such a photo hurts readers and can be mistaken for the scene.
  Show prevention and preparedness: safety gear, inspection, barriers, warning signs, training,
  calm general views.
- For exam, career or study posts, show the work itself: "safety inspector hard hat", "surveyor tripod field".
</rules>

<examples>
Title: 대기환경기사 | 화학사고와 대기질
industrial smokestack emissions
air pollution chimney smoke
city smog skyline

Title: 공장 창고 화재로 2천만원 피해
fire extinguisher inspection warehouse
firefighter equipment truck
fire safety sign industrial

Title: 축제장 인파 사고 이후 안전관리 강화
festival crowd safety barrier
event security staff crowd
outdoor concert crowd
</examples>"""

# 위 지시를 어기고 나온 검색어는 버린다 — 사고 순간을 묘사하는 말이 든 것.
# (2026-10-04 줄타기 공연자 추락 사망 브리핑에 'tightrope performer falling' 사진이 붙었다)
BANNED = re.compile(
    r"\b(fall|falls|falling|fallen|crash\w*|collision|collid\w*|collaps\w*|explo\w*|"
    r"drown\w*|accident|injur\w*|victim\w*|dead|death|dying|wreck\w*|burning\s+(house|car|building)|"
    r"blood\w*|corpse|rubble\s+person|trapped)\b", re.I)
# 검색어가 멀쩡해도 사진이 엉뚱할 수 있다 — 'festival crowd safety barrier' 에 Pexels 가
# 불 쇼·오토바이 스턴트 사진을 줬다. 사진 설명(alt)에 이런 말이 있으면 버린다.
RISKY_ALT = re.compile(r"stunt|daredevil|acrobat|tightrope|slackline|fire (performance|show|breath)|"
                       r"jump\w*|flip|extreme", re.I)


def _risky(photo):
    # Pixabay 는 설명문이 없고 태그만 있다 — 태그(text)도 함께 본다.
    alt = f'{photo.get("alt") or ""} {photo.get("text") or ""}'
    return bool(BANNED.search(alt) or RISKY_ALT.search(alt))


def _enabled(cfg):
    return bool(((cfg or {}).get("stock_photo") or {}).get("enabled", True))


def queries_for(title, summary="", cfg=None):
    """글 제목·요약 → 영어 검색어 3개(구체적인 것부터). 실패하면 []."""
    cfg = cfg or load_config()
    try:
        from anthropic import Anthropic
        client = _llm_client(cfg)
        msg = client.messages.create(
            model=cfg.get("model", "claude-sonnet-4-6"), max_tokens=120, system=SYSTEM,
            messages=[{"role": "user", "content": f"Title: {title}\nSummary: {summary[:400]}"}])
        lines = msg.content[0].text.strip().splitlines()
    except Exception as e:
        log(f"자료사진 검색어 만들기 실패: {type(e).__name__}: {str(e)[:80]}")
        return []
    out = []
    for ln in lines:
        q = re.sub(r"^[\s\-\*\d\.\)]+", "", ln).strip().strip('"').strip()
        if q and re.fullmatch(r"[A-Za-z][A-Za-z \-']{2,40}", q):
            if BANNED.search(q):
                log(f"자료사진 검색어 버림(사고 장면 묘사): '{q}'")
                continue
            out.append(q)
    return out[:3]


def _history():
    try:
        with open(HISTORY, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _remember(uid):
    h = [u for u in _history() if u != uid] + [uid]
    try:
        with open(HISTORY, "w", encoding="utf-8") as f:
            json.dump(h[-KEEP:], f)
    except Exception as e:
        log(f"자료사진 기록 실패(글은 정상): {type(e).__name__}")


def _order(hist):
    """직전에 쓴 사진의 공급처가 아닌 곳을 먼저 — 글마다 번갈아 쓰게."""
    last = hist[-1].split(":", 1)[0] if hist else ""
    return ("pixabay", "pexels") if last == "pexels" else ("pexels", "pixabay")


def figure_html(url, photo):
    """사진 + '자료사진 · 사진: 촬영자 / 공급처' 캡션."""
    e = html.escape
    author = e(photo.get("author") or "")
    prov = e(photo.get("provider") or "")
    src = (f'<a href="{e(photo["page"])}" target="_blank" rel="noopener">{prov}</a>'
           if photo.get("page") else prov)
    who = f"사진: {author} / {src}" if author else f"사진: {src}"
    return ('<figure style="margin:1.4em 0;text-align:center">'
            f'<img src="{e(url)}" alt="{e(photo.get("alt") or "")}" '
            'style="max-width:100%;height:auto;border-radius:10px">'
            '<figcaption style="margin-top:6px;font-size:13px;color:#7b8794">'
            f'자료사진 · {who}</figcaption></figure>')


def photo_html(title, summary="", cfg=None, dry_run=False):
    """글 주제에 맞는 자료사진을 찾아 올리고 본문에 넣을 HTML 을 준다. 없으면 ""."""
    cfg = cfg or load_config()
    if not _enabled(cfg):
        return ""
    keys = keys_from(cfg)
    if not any(keys.values()):
        log("자료사진 건너뜀: pexels/pixabay 키가 없습니다")
        return ""
    queries = queries_for(title, summary, cfg)
    if not queries:
        return ""
    hist = _history()
    photo = stock_photo.find(queries, keys, skip=hist, providers=_order(hist), log=log,
                             reject=_risky)
    if not photo:
        log(f"자료사진 없음(검색어 {queries}) — 사진 없이 발행")
        return ""
    if dry_run:
        log(f"[DRY] 자료사진: {photo['provider']} {photo['uid']} '{photo['query']}' "
            f"— {photo['author']} (올리지 않음)")
        return ""
    try:
        path = stock_photo.download(photo, os.path.join(POSTS_DIR, "stock"))
        from geoai_assets import upload
        urls = upload([path], f"{datetime.now():%Y/%m}/photo_{datetime.now():%Y%m%d_%H%M%S}", cfg)
    except Exception as e:
        log(f"자료사진 올리기 실패(글은 사진 없이): {type(e).__name__}: {str(e)[:100]}")
        return ""
    if not urls:
        return ""
    _remember(photo["uid"])
    log(f"자료사진: {photo['provider']} {photo['uid']} '{photo['query']}' — {photo['author']}")
    return figure_html(urls[0], photo)


def _llm_client(cfg):
    """학교 AI 게이트웨이 → (실패 시) Anthropic 키. shared/llm.py 참고."""
    import os
    import sys
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    from shared.llm import client
    return client(cfg)

