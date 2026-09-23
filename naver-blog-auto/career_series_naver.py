"""진로·자격증 시리즈를 네이버 블로그에도 올린다.

왜 만들었나: 네이버 블로그에는 '지난 소식' 브리핑만 올라가고 있었다. 그런데
데이터랩으로 확인해 보니 검색량은 자격증(산업안전기사·소방안전관리자)이
재난 브리핑·대피요령의 40~100배다(2026-09-22 조사). 이미 써 둔 진로 8편과
자격증 16편은 블로거로만 나가고 있어서, 검색 수요가 큰 글이 방문자 없는 쪽에만
쌓이고 있었다. 그래서 같은 원고를 네이버에도 올린다.

블로거 발행(career_series.py)은 건드리지 않는다. 상태 파일도 따로 둔다 —
어느 한쪽이 밀려도 다른 쪽이 영향을 받지 않게.

사용:
  ./.venv/bin/python career_series_naver.py --dry-run   # 에디터에 채우고 발행 직전 정지
  ./.venv/bin/python career_series_naver.py             # 1편 발행
"""
import html
import json
import os
import re
import sys
import time

import career_series
import cert_writer
from common import BASE_DIR, load_config, log
from publish_naver import publish

STATE = os.path.join(BASE_DIR, "career_naver_state.json")
CATEGORY = "학과진로"          # 네이버 블로그 카테고리
GAP_SECONDS = 180


def _state():
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    return {"posted": {}}


def _save(state):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _episodes():
    """(시리즈키, 라벨, 순번, 총편수, 에피소드) 를 발행 순서대로 돌려준다.

    진로 8편을 먼저 다 올리고 자격증 16편으로 넘어간다 — 진로는 원고가 이미
    확정돼 있어 실패할 일이 없고, 자격증은 매번 생성해야 해서 느리다.
    """
    for s in career_series.SERIES:
        eps = s["eps"]
        for i, ep in enumerate(eps, 1):
            yield s["key"], s["label"], i, len(eps), ep


def _plain(t):
    """블로거용 원고에 든 HTML 태그를 지운다.

    진로 시리즈 본문에는 <b>…</b> 가 들어 있다(블로거는 HTML 로 올리니까).
    네이버 에디터에는 글자 그대로 찍히므로 반드시 벗겨야 한다.
    """
    return html.unescape(re.sub(r"<[^>]+>", "", t)).strip()


def _body_for(key, ep, n, total, cfg):
    """시리즈별 원고를 네이버 발행용 data 로 맞춘다."""
    if key == "career":
        _vid, title, summary, paras, faq, tags = ep
    else:
        _slug, title, angle, tags = ep
        w = cert_writer.write(n, total, title, angle, cfg)
        summary, paras, faq = w["summary"], w["paras"], w["faq"]

    # 본문은 블록으로 넘긴다 — 구조형 경로라야 글 끝 CTA(이웃추가·채널 링크)가 붙는다.
    blocks = [{"heading": "", "paragraph": _plain(p)} for p in paras[1:]]
    return {
        "title": f"{title} [{n}/{total}]",
        "summary": "\n".join(f"· {_plain(s)}" for s in summary),
        "intro": _plain(paras[0]),
        "news_blocks": blocks,
        "faq": "\n".join(f"Q. {_plain(q)}\nA. {_plain(a)}" for q, a in faq),
        "tags": tags,
        "category": CATEGORY,
        "no_banner": False,
        "no_images": True,          # 기사가 없는 글이라 삽화를 만들지 않는다
        "banner_badge": "CAREER & LICENSE",
    }


def main():
    dry = "--dry-run" in sys.argv
    per_run = 1 if not dry else 1
    cfg = load_config()
    state = _state()
    done = 0

    for key, label, n, total, ep in _episodes():
        uid = f"{key}-{n}"
        if uid in state["posted"]:
            continue
        title = ep[1]
        log(f"[{label} {n}/{total}] {title}")
        data = _body_for(key, ep, n, total, cfg)
        r = publish(data, dry_run=dry)
        if dry:
            log("DRY-RUN: 에디터에 채우고 발행 직전에 멈췄습니다.")
            return 0
        state["posted"][uid] = {"title": title,
                                "at": time.strftime("%Y-%m-%d %H:%M:%S")}
        _save(state)
        log(f"✅ 네이버 발행: {title}")
        done += 1
        if done >= per_run:
            break
        time.sleep(GAP_SECONDS)

    if done == 0 and not dry:
        log("올릴 편이 남아 있지 않습니다(진로 8편 + 자격증 16편 모두 발행됨).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
