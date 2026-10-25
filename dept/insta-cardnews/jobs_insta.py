"""네이버 블로그에 올린 '채용정보' 글을 인스타그램 카드뉴스(캐러셀)로도 올린다.

naver-blog-auto/jobs_work24.py 가 만든 초안(posts/jobs_*.json)을 읽는다. 공고를 다시 고르지
않는다 — 블로그와 인스타가 같은 공고를 싣게.

카드: 표지 → 공고 카드(한 장에 2건) → '지원 전 체크'. 인스타 캡션의 링크는 눌리지 않아
원본 공고 링크는 블로그 글(프로필 링크)로 안내하고, 블로그 주소를 캡션에 적는다.
소방 관련 공고는 싣지 않는다(2026-09-29 요청).

사용:
  python jobs_insta.py posts/…/jobs_….json --dry   # 카드 만들고 '공유하기' 직전에 멈춤
  python jobs_insta.py --latest --go                 # 가장 최근 초안으로 실제 게시(run_jobs.sh)
"""
import glob
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

from common import POSTS_DIR, log

NAVER_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "channels", "naver-blog-auto")
STATE = os.path.join(POSTS_DIR, "jobs_insta_posted.json")
BLOG_ID, CATEGORY_NO = "studs23", 9            # 네이버 '채용정보' 카테고리
NO_FIRE = re.compile(r"소방")
PER_CARD = 2
TAGS = ["채용정보", "신입채용", "재난안전", "안전관리자", "산업안전", "건설안전", "공무원채용",
        "취업정보", "재난안전학과", "세명대학교", "세명대", "세명대재난안전학과"]


def _md(d):
    return f"{int(d[5:7])}.{int(d[8:10])}" if d and len(d) == 10 else d


def _deadline(j):
    if j.get("gov"):
        a = (j.get("apply") or "").split(" ~ ")
        return f"원서접수 ~{_md(a[1])}" if len(a) == 2 else "공고문 확인"
    if j.get("until_hired") or not j.get("deadline"):
        return "채용 시까지"
    return f"~{_md(j['deadline'])} 마감"


def _short(s, n):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[:n - 1] + "…"


def _career(j):
    return {"신입": "신입", "경력무관": "경력무관(신입 가능)", "관계없음": "경력무관(신입 가능)"
            }.get(j.get("career"), "") or ("공개경쟁" if j.get("exam_type") == "공개경쟁" else "")


def _latest_blog_url():
    """방금 올린 '채용정보' 글 주소(캡션에 적는다). 못 찾으면 카테고리 주소."""
    try:
        u = (f"https://blog.naver.com/PostTitleListAsync.naver?blogId={BLOG_ID}&viewdate=&currentPage=1"
             f"&categoryNo={CATEGORY_NO}&parentCategoryNo=&countPerPage=5")
        s = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}),
                                   timeout=20).read().decode("utf-8", "replace")
        m = re.search(r'"logNo":"(\d+)".*?"title":"(.*?)"', s)
        if m and "채용정보" in urllib.parse.unquote_plus(m.group(2)):
            return f"https://blog.naver.com/{BLOG_ID}/{m.group(1)}"
    except Exception:
        pass
    return f"https://blog.naver.com/PostList.naver?blogId={BLOG_ID}&categoryNo={CATEGORY_NO}"


def build(draft, extra=False):
    """extra=True: 이미 올린 주의 '추가 공고'(블로그 글을 고쳐 채운 공고). 인스타는 올린
    캐러셀에 사진을 더할 수 없어 새 게시물로 올린다(9/29)."""
    jobs = [j for j in draft["jobs"] if not NO_FIRE.search(j["title"] + j.get("duty", "") + j.get("quals", ""))]
    if len(jobs) < 2:
        return None
    jobs = jobs[:PER_CARD * 8]                  # 캐러셀 10장 = 표지 + 공고 8장 + 마무리
    now = datetime.now()
    week = (now.day - 1) // 7 + 1
    ngov = sum(1 for j in jobs if j.get("gov"))
    cards = ["\n".join([
        f"신입 채용공고, 이번 주 추가 {len(jobs)}선" if extra else f"신입 채용공고, 이번 주 {len(jobs)}선",
        "",
        "재난안전·안전관리 분야",
        "신입·경력무관 공고만 골랐어요" + (" (공무원 포함)" if ngov else ""),
        f"{now.month}월 {week}주차 · 고용24·지자체 원서접수센터",
    ])]
    for k in range(0, len(jobs), PER_CARD):
        chunk = jobs[k:k + PER_CARD]
        paras = []
        for i, j in enumerate(chunk, k + 1):
            tag = "[공무원] " if j.get("gov") else "[공공] " if j.get("public") else ""
            lines = [
                _short(f"{i}. {tag}{j['company']}", 16),
                _short(j["title"], 38),
                f"업무: {_short(j.get('duty'), 32)}",
                f"급여: {_short(j.get('pay') or '공고 참고', 26)}",
                f"자격: {_short(' · '.join(x for x in (_career(j), j.get('quals', '')) if x and x != '공고 원문 참고'), 40) or '공고 참고'}",
                f"기간: {_deadline(j)}",
            ]
            if len(chunk) == 1:
                # 한 장에 1건이면 렌더러가 문단 하나를 두 줄씩 상자로 쪼갠다(9/29 시험) —
                # 회사·공고명 / 세부 조건 두 문단으로 나눠 상자 두 개로 보이게 한다
                paras += ["\n".join(lines[:2]), "\n".join(lines[2:])]
            else:
                paras.append("\n".join(lines))
        rng = f"{k + 1}" if len(chunk) == 1 else f"{k + 1}~{k + len(chunk)}"
        cards.append(f"💼 채용공고 {rng}\n\n" + "\n\n".join(paras))
    cards.append("\n".join([
        "✅ 지원 전 체크",
        "",
        "자격·마감일은 공고 원문에서 다시 확인",
        "마감 전에 채용이 끝날 수 있어요",
        "원본 공고 링크는 프로필 링크의 네이버 블로그 '채용정보'에서 확인하세요",
    ]))
    blog = _latest_blog_url()
    head = f"추가 {len(jobs)}선" if extra else f"{len(jobs)}선"
    lines = [f"💼 [채용정보] 신입 지원 가능한 재난안전·안전관리 채용공고 {head} | {now.month}월 {week}주차",
             "", "고용24·지방자치단체 인터넷원서접수센터에서 이번 주 공고 중 신입이 지원할 수 있는 공고만 골랐어요.", ""]
    for i, j in enumerate(jobs, 1):
        lines.append(f"{i}. {j['company']} — {_short(j['title'], 34)} ({_deadline(j)})")
    lines += ["", "🔗 공고별 원본 링크는 프로필 링크 → 네이버 블로그 '채용정보'에 있어요.", blog, "",
              "※ 출처: 고용24(work24.go.kr)" + (", 지방자치단체 인터넷원서접수센터(공공누리 제4유형)" if ngov else "")
              + ". 세부 조건은 반드시 원본 공고에서 확인하세요.", "",
              " ".join("#" + t for t in TAGS)]
    return {
        "title": f"신입 채용공고 {'추가 ' if extra else ''}{len(jobs)}선", "cards": cards, "caption": "\n".join(lines),
        "hashtags": [], "sources": [], "cover_query": "construction safety helmet",
        "stamp": "JOBS_" + now.strftime("%Y%m%d_%H%M%S"), "jobs": [j["id"] for j in jobs],
    }


def _load_state():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {}


def main():
    go = "--go" in sys.argv
    if "--latest" in sys.argv:
        files = sorted(glob.glob(os.path.join(NAVER_DIR, "posts", "jobs_2*.json")), key=os.path.getmtime)
        if not files:
            raise SystemExit("채용정보 초안이 없습니다.")
        path = files[-1]
        if time.time() - os.path.getmtime(path) > 6 * 3600:
            log(f"인스타 채용정보: 최근 초안이 오래됨({os.path.basename(path)}) — 이번 주 블로그 발행이 없었던 것으로 보고 건너뜀")
            return 0
    else:
        path = next((a for a in sys.argv[1:] if a.endswith(".json")), None)
        if not path:
            raise SystemExit(__doc__)
    key = os.path.basename(path)
    st = _load_state()
    if go and key in st:
        log(f"인스타 채용정보: 이미 올린 초안({key}) — 건너뜀")
        return 0
    draft = json.load(open(path, encoding="utf-8"))
    if go and "--latest" in sys.argv:
        # 블로그에 실제로 올라간 초안만 인스타에도 올린다(블로그 발행이 실패한 주는 건너뜀)
        try:
            naver = json.load(open(os.path.join(NAVER_DIR, "posts", "jobs_posted.json"), encoding="utf-8"))
        except Exception:
            naver = {}
        if not any(j["id"] in naver for j in draft.get("jobs", [])):
            log("인스타 채용정보: 이 초안은 블로그에 발행되지 않았음 — 건너뜀")
            return 0
    data = build(draft, extra="--extra" in sys.argv)
    if not data:
        log("인스타 채용정보: 소방 제외 뒤 공고가 2건 미만 — 건너뜀")
        return 0
    import render_cards_local
    render_cards_local.CHIP = "재난안전 채용정보"      # 뉴스판 표지('제천·충북 재난안전') 대신
    render_cards_local.make_cards(data)
    log(f"인스타 채용정보: 카드 {len(data['images'])}장 — {data['title']}")
    from post_instagram import post_carousel
    r = post_carousel(data, dry_run=not go)
    log(f"인스타 채용정보: {r.get('status')}")
    if go and r.get("status") in ("published", "shared_unconfirmed"):
        st[key] = datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(STATE, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
