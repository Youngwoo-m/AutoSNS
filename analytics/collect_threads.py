"""스레드(Threads) 게시물을 수집한다. insta-cardnews/.venv 로 실행할 것.

스레드는 인스타 로그인 세션을 함께 쓴다. 발행에 쓰는 크롬 프로필을 그대로 열어
프로필 화면을 훑어 읽기만 한다(공식 API 토큰은 없다 — 발행도 브라우저로 한다).

게시물마다 붙는 <time datetime> 에서 날짜를 얻는다. 화면에 보이는 '5일 전' 같은
표기는 쓰지 않는다.

스레드는 목록을 가상화해 화면 밖 게시물을 DOM 에서 치운다. 한 번에 4~6개만
존재하므로 조금씩 내리면서 매번 주워 담아야 빠뜨리지 않는다.
"""
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "insta-cardnews"))
from analytics.common import log, save_part      # noqa: E402
from post_instagram import build_driver          # noqa: E402

USER = "smu_ds_official"
PROFILE = f"https://www.threads.com/@{USER}"

# 게시물 컨테이너를 직접 훑는다. 링크와 시간이 같은 묶음 안에 있어야 짝이 맞는다.
JS_POSTS = """
const out = [];
document.querySelectorAll('time[datetime]').forEach(t => {
  let node = t, link = null;
  for (let i = 0; i < 8 && node; i++) {
    node = node.parentElement;
    if (!node) break;
    const a = node.querySelector('a[href*="/post/"]');
    if (a) { link = a.getAttribute('href'); break; }
  }
  if (!link) return;
  let box = t;
  for (let i = 0; i < 10 && box.parentElement; i++) box = box.parentElement;
  out.push({dt: t.getAttribute('datetime'), href: link,
            text: (box.innerText || '').slice(0, 400)});
});
return JSON.stringify(out);
"""


def _title(text, user):
    """본문 첫 줄을 활동명으로 쓴다. 화면 텍스트에는 계정명·시간·버튼이 섞여 들어온다."""
    skip = (user, "팔로우", "Follow", "더 보기", "More", "번역 보기", "답글", "좋아요")
    for line in (text or "").split("\n"):
        s = line.strip()
        if not s or s.startswith("@") or s in skip:
            continue
        if s.replace("일", "").replace("시간", "").replace("분", "").strip().isdigit():
            continue
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):      # 날짜 줄은 제목이 아니다
            continue
        if any(k in s and len(s) <= 6 for k in skip):
            continue
        return s[:90]
    return ""


def collect(since):
    d = build_driver(headless=False)
    d.set_script_timeout(60)
    try:
        d.get(PROFILE)
        time.sleep(8)
        seen, items, idle = set(), [], 0
        for _ in range(60):
            before = len(seen)
            for p in json.loads(d.execute_script(JS_POSTS)):
                href = p["href"]
                pid = href.rstrip("/").split("/")[-1]
                if pid in seen:
                    continue
                seen.add(pid)
                date = (p["dt"] or "")[:10]
                if not date:
                    continue
                items.append({
                    "title": _title(p.get("text"), USER) or "(본문 없음)",
                    "date": date, "type": "게시글", "source": "스레드",
                    "url": f"https://www.threads.com/@{USER}/post/{pid}",
                })
            if items and min(x["date"] for x in items) < since:
                break
            idle = 0 if len(seen) > before else idle + 1
            if idle >= 6:                       # 여섯 번 내려도 새 글이 없으면 끝
                break
            d.execute_script("window.scrollBy(0, Math.round(window.innerHeight * 0.6));")
            time.sleep(1.2)
        items = [x for x in items if x["date"] >= since]
        items.sort(key=lambda x: x["date"], reverse=True)
        return {"profile": {"username": USER, "url": PROFILE}, "items": items}
    finally:
        d.quit()


if __name__ == "__main__":
    since = sys.argv[1] if len(sys.argv) > 1 else "2026-03-01"
    data = collect(since)
    log(f"스레드 게시물 {len(data['items'])}건")
    save_part("threads", data)
