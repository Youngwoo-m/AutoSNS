"""고용24(work24.go.kr) 재난안전 분야 채용공고를 모아 네이버 블로그 '채용정보'에 주 1회 올린다.

흐름
  1) 여러 검색어로 최근 7일 등록 공고를 모은다(목록 페이지, 로그인 없음).
     robots.txt 는 통합검색(selectUnifySearchPost)만 막고 채용정보 목록은 허용한다.
  2) Claude 가 회사명·공고명만 보고 재난안전학과 진로와 맞는 공고를 12편 안팎 고른다.
     '재난안전' 전체검색에는 직무내용 어딘가에 그 말이 있는 AI개발자·돌봄 공고까지
     걸리고(2026-09-29 확인), '안전관리자'·'소방'은 한 주 50건이 넘어 고르지 않으면 안 된다.
  3) 고른 공고만 상세 페이지를 읽어 Claude 가 담당업무·자격요건을 한 줄씩 요약한다.
     급여·지원기간·경력·학력은 고용24 목록 값을 그대로 쓴다(요약이 숫자를 바꾸지 않게).
  4) 공고마다 [요약 + 원본 공고 링크] 묶음으로 글을 만들어 올린다.
     한 번 올린 공고는 posts/jobs_posted.json 에 남겨 다음 주에 다시 싣지 않는다.

사용:
  python jobs_work24.py --dry    # 모으고 요약해 발행 직전에 멈춤(스크린샷)
  python jobs_work24.py --list   # 모은 공고만 출력(발행 창 안 띄움)
  python jobs_work24.py --go     # 실제 발행 (run_jobs.sh 가 일요일 20:00 호출)
"""
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from common import POSTS_DIR, load_config, log

BASE = "https://www.work24.go.kr"
LIST_URL = BASE + "/wk/a/b/1200/retriveDtlEmpSrchList.do"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/154.0 Safari/537.36"}
STATE = os.path.join(POSTS_DIR, "jobs_posted.json")
CATEGORY = "채용정보"
DAYS = 7
MAX_JOBS = 12
MIN_JOBS = 3               # 이보다 적으면 그 주는 쉰다(빈약한 글은 올리지 않는다)

# (검색어, 제목에서만 찾기). 넓은 말은 제목으로 좁히고, 드문 말은 전체에서 찾는다.
QUERIES = [
    ("재난", True), ("재난안전", False), ("재난관리", False), ("비상계획", False),
    ("방재", True), ("소방안전관리자", True), ("안전관리자", True),
    ("산업안전", True), ("안전보건", True),
]


def _get(url, tries=3):
    for n in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            if n == tries - 1:
                raise
            time.sleep(3 * (n + 1))


def _text(frag):
    frag = re.sub(r"<script.*?</script>|<style.*?</style>", "", frag, flags=re.S)
    return html.unescape(re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"<[^>]+>", " ", frag))).replace("\xa0", " ")


def _rows(page_html):
    """목록 한 쪽의 공고들. 체크박스 값이 '공고번호|유형|회사명|공고명' 이라 이름은 거기서."""
    out = []
    for r in re.findall(r'<tr id="list\d+">(.*?)</tr>', page_html, re.S):
        v = re.search(r'id="chkboxWantedAuthNo\d+" value="([^"]+)"', r)
        link = re.search(r'href="(/wk/a/b/1500/empDetailAuthView\.do\?[^"]+)"', r)
        if not v or not link:
            continue
        parts = html.unescape(v.group(1)).split("|")
        if len(parts) < 4:
            continue
        lines = [ln.strip() for ln in _text(r).split("\n") if ln.strip()]
        flat = " ".join(lines)
        # 급여는 '월급 / 300 / 만원 ~ / 450 / 만원' 처럼 여러 줄로 쪼개져 있어 이은 글에서 찾는다
        pm = re.search(r"(월급|연봉|시급|일급|주급)\s*([\d,]+)\s*(만원|원)"
                       r"(?:\s*~\s*([\d,]+)\s*(?:만원|원))?(\s*이상)?", flat)
        if pm:
            a, unit, b = pm.group(2), pm.group(3).replace("만원", "만 원"), pm.group(4)
            pay = (f"{pm.group(1)} {a}~{b}{unit}" if b and b != a else f"{pm.group(1)} {a}{unit}") \
                + (" 이상" if pm.group(5) else "")
        else:
            pay = next((ln for ln in lines if "회사내규" in ln or "면접 후" in ln), "")
        career = next((ln for ln in lines if re.fullmatch(r"(경력무관|신입|경력(\d+년)?|신입·경력|관계없음)", ln)), "")
        edu = next((ln for ln in lines if re.fullmatch(
            r"(학력무관|고졸|초대졸|대졸|대졸\(4년\)|석사|박사|중졸 이하|고졸 이상|대졸 이상)", ln)), "")
        dl = re.search(r"마감일\s*:\s*([\d-]+)", flat)
        reg = re.search(r"등록일\s*:\s*([\d-]+)", flat)
        out.append({
            "id": parts[0], "company": parts[2].strip(), "title": parts[3].strip(),
            "url": BASE + html.unescape(link.group(1)),
            "pay": re.sub(r"\s+", " ", pay), "career": career, "edu": edu,
            "until_hired": "채용시까지" in flat,
            "deadline": dl.group(1) if dl else "", "reg": reg.group(1) if reg else "",
        })
    return out


def search(keyword, title_only, since, max_pages=4):
    q = {"srcKeyword": keyword, "keyword": keyword, "resultCnt": "50", "sortField": "DATE",
         "sortOrderBy": "DESC", "siteClcd": "all", "searchMode": "Y", "codeDepth1Info": "11000",
         "codeDepth2Info": "11000", "academicGbnoEdu": "noEdu", "benefitSrchAndOr": "O"}
    if title_only:
        q.update({"keywordWantedTitle": "Y", "keywordBusiNm": "N", "keywordJobCont": "N",
                  "keywordStaAreaNm": "N"})
    got = []
    for page in range(1, max_pages + 1):
        q.update({"pageIndex": str(page), "currentPageNo": str(page)})
        rows = _rows(_get(LIST_URL + "?" + urllib.parse.urlencode(q)))
        got += rows
        if not rows or min((r["reg"] for r in rows if r["reg"]), default="0") < since:
            break
        time.sleep(1)
    return [r for r in got if r["reg"] >= since]


def collect(days=DAYS):
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")
    posted = _load_state()
    seen = {}
    for kw, title_only in QUERIES:
        try:
            rows = search(kw, title_only, since)
        except Exception as e:
            log(f"고용24 검색 실패({kw}): {type(e).__name__}: {e}")
            continue
        for r in rows:
            if r["id"] in posted or r["id"] in seen:
                continue
            if r["deadline"] and r["deadline"] < today:
                continue
            r["found_by"] = kw
            seen[r["id"]] = r
        time.sleep(1)
    log(f"고용24: 최근 {days}일 후보 {len(seen)}건 (이미 올린 공고 제외)")
    return list(seen.values())


# ── Claude: 고르기 · 요약 ────────────────────────────────────────────────────
PICK = """아래는 이번 주 고용24에 올라온 채용공고 후보다. 세명대학교 재난안전학과 학생·졸업생에게
소개할 만한 공고를 최대 {n}건 골라라.

맞는 분야: 재난관리·재난안전(공공기관·지자체·재난 전문기업), 방재·방재실, 소방시설·소방안전관리,
안전관리자(건설·산업·시설), 산업안전·안전보건, 비상계획·비상대비, 안전 점검·진단.
빼는 것: 제목·회사로 봐서 재난안전 직무가 아닌 공고(개발자, 돌봄, 영업, 단순 사무·경비·미화 등).
고를 때: 공공기관·지자체·연구기관·재난 전문기업을 앞에 두고, 같은 종류(예: 건설현장 안전관리자)가
몰리지 않게 섞고, 같은 회사는 한 건만 고르고, 신입이 지원할 수 있는 공고를 우대한다.

출력은 고른 번호의 JSON 배열 하나만(중요한 순서대로). 예: [3, 17, 5]

[후보]
{rows}"""

SUMMARIZE = """아래 채용공고 원문에서 항목마다 두 가지만 짧게 뽑아라. 원문에 없는 내용은 쓰지 않는다.
- duty: 담당업무 한 줄(45자 이내, 명사형으로 끝낸다. 예: '소방시설 점검 및 방재실 운영')
- quals: 자격요건 한 줄(60자 이내). 필수 자격증·면허를 먼저, 우대는 '우대:'로.
  경력 연수·학력은 따로 표시하므로 쓰지 않는다(자격증·면허·특수 조건만).
  원문에 자격 조건이 없으면 '공고 원문 참고'.

출력은 JSON 배열 하나만: [{{"id": "...", "duty": "...", "quals": "..."}}]

{items}"""


def _client(cfg):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    from shared.llm import client
    return client(cfg)


def _ask(cfg, prompt, max_tokens=3000):
    msg = _client(cfg).messages.create(model=cfg.get("model", "claude-sonnet-4-6"),
                                       max_tokens=max_tokens,
                                       messages=[{"role": "user", "content": prompt}])
    # 게이트웨이 Sonnet 5 는 먼저 생각(thinking)에 토큰을 쓴다. 한도가 작으면 생각만 하다
    # 답 없이 끝나므로(후보 194건 선별에서 800 토큰으로 발생) 한도를 넉넉히 준다.
    text = "".join(getattr(b, "text", "") for b in msg.content)
    if not text.strip():
        raise RuntimeError(f"답이 비었습니다(stop_reason={msg.stop_reason}) — max_tokens 를 늘릴 것")
    i = text.find("[")
    return json.JSONDecoder().raw_decode(text[i:])[0] if i >= 0 else []


def pick(cfg, cands, n=MAX_JOBS):
    rows = "\n".join(f"{i}. {c['company']} | {c['title']}" for i, c in enumerate(cands))
    ids = _ask(cfg, PICK.format(n=n, rows=rows), 4000)
    out = []
    for k in ids:
        if isinstance(k, int) and 0 <= k < len(cands) and cands[k] not in out:
            out.append(cands[k])
    return out[:n]


def _detail_text(url):
    t = _text(_get(url))
    t = re.sub(r"\n\s*\n+", "\n", t)
    i = t.find("모집요강")
    j = t.find("직무내용", i if i >= 0 else 0)
    start = j if j >= 0 else max(i, 0)
    return re.sub(r"\s+", " ", t[start:start + 2500]).strip()


def summarize(cfg, jobs):
    items = []
    for j in jobs:
        try:
            j["detail"] = _detail_text(j["url"])
        except Exception as e:
            j["detail"] = ""
            log(f"상세 읽기 실패 {j['id']}: {type(e).__name__}")
        items.append(f"[id: {j['id']}] {j['company']} | {j['title']}\n{j['detail'] or '(원문 없음)'}")
        time.sleep(1)
    res = {r.get("id"): r for r in _ask(cfg, SUMMARIZE.format(items="\n\n".join(items)), 6000)
           if isinstance(r, dict)}
    for j in jobs:
        r = res.get(j["id"], {})
        j["duty"] = (r.get("duty") or "").strip() or "공고 원문 참고"
        j["quals"] = (r.get("quals") or "").strip() or "공고 원문 참고"
    return jobs


# ── 글 만들기 ────────────────────────────────────────────────────────────────
def _pay(p):
    return p or "공고 원문 참고"


def _md(d):
    return f"{int(d[5:7])}.{int(d[8:10])}" if len(d) == 10 else d


def build(jobs):
    now = datetime.now()
    week = (now.day - 1) // 7 + 1
    title = f"[채용정보] 재난안전·방재·소방 분야 채용공고 {len(jobs)}선 | {now.month}월 {week}주차"
    intro = (f"이번 주({_md((now - timedelta(days=DAYS)).strftime('%Y-%m-%d'))}~{_md(now.strftime('%Y-%m-%d'))}) "
             "고용24에 새로 올라온 재난안전 분야 채용공고를 모았습니다.\n"
             "공고마다 핵심만 요약했으니, 관심 있는 공고는 아래 링크로 원문을 꼭 확인해 주세요.")
    blocks = []
    circled = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"
    for i, j in enumerate(jobs):
        cond = " · ".join(x for x in (j["career"], j["edu"]) if x)
        period = (f"{_md(j['reg'])} ~ 채용 시까지" if j["until_hired"] or not j["deadline"]
                  else f"{_md(j['reg'])} ~ {_md(j['deadline'])} 마감")
        quals = j["quals"] if not cond else f"{cond} / {j['quals']}"
        text = "\n".join([
            f"{circled[i] if i < len(circled) else str(i + 1) + '.'} {j['company']}",
            f"{j['title']}",
            f"· 담당업무: {j['duty']}",
            f"· 급여: {_pay(j['pay'])}",
            f"· 자격요건: {quals}",
            f"· 지원기간: {period}",
        ])
        blocks.append({"text": text, "link_text": "👉 고용24 원본 공고 보기", "url": j["url"]})
    outro = ("─────────────\n"
             "※ 출처: 고용24(work24.go.kr) 채용정보. 요약은 편의를 위한 것이며, 급여·자격·마감일 등 "
             "세부 조건은 반드시 원본 공고에서 확인하세요. 마감 전에 채용이 끝날 수도 있습니다.\n"
             "세명대학교 재난안전학과는 매주 일요일 재난안전 분야 채용정보를 정리해 올립니다. "
             "이웃추가하고 다음 주 공고도 받아보세요!")
    return {
        "title": title, "body": intro, "link_blocks": blocks, "outro": outro,
        "category": CATEGORY, "no_banner": False,
        "tags": ["채용정보", "재난안전채용", "방재", "소방안전관리자", "안전관리자",
                 "산업안전", "고용24", "재난안전학과", "세명대학교", "세명대"],
    }


def _load_state():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {}


def _save_state(jobs):
    st = _load_state()
    today = datetime.now().strftime("%Y-%m-%d")
    for j in jobs:
        st[j["id"]] = today
    cut = (datetime.now() - timedelta(days=120)).strftime("%Y-%m-%d")
    st = {k: v for k, v in st.items() if v >= cut}          # 넉 달 지난 기록은 버린다
    with open(STATE + ".part", "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(STATE + ".part", STATE)


def main():
    mode = next((a for a in sys.argv[1:] if a in ("--dry", "--go", "--list")), None)
    if not mode:
        raise SystemExit("사용: jobs_work24.py --list | --dry | --go")
    cfg = load_config()
    cands = collect()
    if len(cands) < MIN_JOBS:
        log(f"채용정보: 후보 {len(cands)}건 — 이번 주는 올리지 않음")
        return 0
    jobs = pick(cfg, cands)
    log(f"채용정보: {len(jobs)}건 선택 — " + ", ".join(j["company"] for j in jobs))
    if len(jobs) < MIN_JOBS:
        log("채용정보: 고른 공고가 너무 적어 이번 주는 올리지 않음")
        return 0
    jobs = summarize(cfg, jobs)
    data = build(jobs)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(os.path.join(POSTS_DIR, f"jobs_{stamp}.json"), "w", encoding="utf-8") as f:
        json.dump({**data, "jobs": jobs}, f, ensure_ascii=False, indent=1)
    if mode == "--list":
        print(data["title"] + "\n\n" + data["body"])
        for b in data["link_blocks"]:
            print("\n" + b["text"] + "\n" + b["link_text"] + " → " + b["url"])
        print("\n" + data["outro"])
        return 0
    from make_banner import make_banner
    try:
        data["banner"] = make_banner("재난안전 분야 채용공고", f"{datetime.now():%Y년 %m월 %d일}",
                                     badge="JOB INFO")
    except Exception as e:
        log(f"배너 생성 실패, 배너 없이 진행: {e}")
    from publish_naver import publish
    r = publish(data, dry_run=(mode != "--go"))
    if mode == "--go" and r.get("status") == "published":
        _save_state(jobs)
        log(f"✅ 채용정보 발행: {data['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
