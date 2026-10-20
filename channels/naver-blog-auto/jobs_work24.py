"""고용24(work24.go.kr) 재난안전 분야 채용공고를 모아 네이버 블로그 '채용정보'에 주 1회 올린다.

흐름
  1) 여러 검색어로 최근 7일 등록 공고를 모은다(목록 페이지, 로그인 없음).
     robots.txt 는 통합검색(selectUnifySearchPost)만 막고 채용정보 목록은 허용한다.
  2) Claude 가 회사명·공고명만 보고 재난안전학과 진로와 맞는 공고를 12편 안팎 고른다.
     '재난안전' 전체검색에는 직무내용 어딘가에 그 말이 있는 AI개발자·돌봄 공고까지
     걸리고(2026-09-29 확인), '안전관리자'는 한 주 50건이 넘어 고르지 않으면 안 된다.
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
    ("방재", True), ("안전관리자", True),
    ("산업안전", True), ("안전보건", True),
    ("공무원", True), ("임용시험", True), ("임기제", True),   # 지자체 공무원 채용(관련 없는 것은 선별에서 뺀다)
]
# 공무원·공기업·공공기관(기업형태 04)만 따로 넓게 찾는다. 이런 공고는 제목이 '제4회 ○○군
# 임기제공무원 임용시험'처럼 직무가 안 보여서 전체 필드에서 찾아야 걸린다(2026-09-29).
PUBLIC_QUERIES = ["재난", "안전", "방재", "비상"]
# 소방 관련 공고(소방시설·소방안전관리·소방설비)는 싣지 않는다(2026-09-29 요청).
# 제목·담당업무·자격요건 어디에든 '소방'이 있으면 뺀다 — 방재실 공고도 대개 소방설비 관리다.
NO_FIRE = re.compile(r"소방")
# 신입(N) + 경력무관(Z). 공무원·공공기관 공고는 거의 다 '경력무관'이라 신입만 걸면 모두
# 빠진다. 글에는 '신입' / '경력무관(신입 가능)'으로 구분해 적는다.
CAREER_TYPES = "N,Z"


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
            "public": 'tbl_label navy">공공' in r,
            "deadline": dl.group(1) if dl else "", "reg": reg.group(1) if reg else "",
        })
    return out


def search(keyword, title_only, since, max_pages=4, public=False):
    q = {"srcKeyword": keyword, "keyword": keyword, "resultCnt": "50", "sortField": "DATE",
         "sortOrderBy": "DESC", "siteClcd": "all", "searchMode": "Y", "codeDepth1Info": "11000",
         "codeDepth2Info": "11000", "academicGbnoEdu": "noEdu", "benefitSrchAndOr": "O",
         "careerTypes": CAREER_TYPES}
    if public:
        q["enterPriseGbn"] = "04"
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
    got = [r for r in got if r["reg"] >= since]
    for r in got:
        r["public"] = r.get("public") or public
    return got


def collect(days=DAYS):
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")
    posted = _load_state()
    seen = {}
    for kw, title_only, public in ([(k, t, False) for k, t in QUERIES]
                                   + [(k, False, True) for k in PUBLIC_QUERIES]):
        try:
            rows = search(kw, title_only, since, public=public)
        except Exception as e:
            log(f"고용24 검색 실패({kw}): {type(e).__name__}: {e}")
            continue
        for r in rows:
            if r["id"] in posted:
                continue
            if r["id"] in seen:
                seen[r["id"]]["public"] = seen[r["id"]]["public"] or r["public"]
                continue
            if r["career"] and r["career"] not in ("신입", "경력무관", "관계없음", "신입·경력"):
                continue                      # 목록 표시로도 경력직이면 뺀다
            if NO_FIRE.search(r["title"]):
                continue
            # 목록엔 '경력무관'인데 제목이 '기술직 경력 직원 채용'인 공고가 있었다(서울대병원, 9/29)
            if re.search(r"경력\s*(직|사원|직원)|경력자(?!\s*우대)", r["title"]) and "신입" not in r["title"]:
                continue
            if r["deadline"] and r["deadline"] < today:
                continue
            r["found_by"] = kw
            seen[r["id"]] = r
        time.sleep(1)
    log(f"고용24: 최근 {days}일 신입·경력무관 후보 {len(seen)}건 "
        f"(공공 {sum(1 for r in seen.values() if r['public'])}건, 이미 올린 공고 제외)")
    return list(seen.values())


# ── Claude: 고르기 · 요약 ────────────────────────────────────────────────────
PICK = """아래는 이번 주 고용24에 올라온 채용공고 후보다. 세명대학교 재난안전학과 학생·졸업생에게
소개할 만한 공고를 최대 {n}건 골라라.

후보는 모두 신입 또는 경력무관 공고다. [공공] 표시는 공무원·공기업·공공기관 공고다.

맞는 분야: 재난관리·재난안전(공공기관·지자체·재난 전문기업), 방재(풍수해·재해 예방),
안전관리자(건설·산업·시설), 산업안전·안전보건, 비상계획·비상대비, 안전 점검·진단.
소방 관련 공고(소방시설·소방설비·소방안전관리자·방재실 소방설비 관리)는 고르지 않는다.
공무원·공공기관은 재난·안전·방재 업무이거나 그럴 가능성이 있는 임용시험·채용공고(예: 지자체
임기제공무원 임용시험, 공공기관 안전직)를 넣는다 — 제목에 직무가 안 보여도 기관이 지자체·
공공기관이면 후보로 본다.
빼는 것: 재난안전 직무가 아닌 공고(개발자, 돌봄, 조리, 간호, 영업, 단순 사무·경비·미화 등).
고를 때: [공공] 공고를 먼저 두되 관련 없는 것은 빼고, 같은 종류(예: 건설현장 안전관리자)가
몰리지 않게 섞고, 같은 회사는 한 건만 고른다.

출력은 고른 번호의 JSON 배열 하나만(중요한 순서대로). 예: [3, 17, 5]

[후보]
{rows}"""

SUMMARIZE = """아래 채용공고 원문에서 항목마다 짧게 뽑아라. 원문에 없는 내용은 쓰지 않는다.
- duty: 담당업무 한 줄(45자 이내, 명사형으로 끝낸다. 예: '건설현장 안전점검 및 안전교육').
  원문에 적힌 업무만 쓴다. '등'을 붙여 원문에 없는 분야를 짐작해 넣지 않는다.
- quals: 자격요건 한 줄(60자 이내). 필수 자격증·면허를 먼저, 우대는 '우대:'로.
  경력 연수·학력은 따로 표시하므로 쓰지 않는다(자격증·면허·특수 조건만).
  원문에 자격 조건이 없으면 '공고 원문 참고'.
- newbie: 대학 졸업 예정·신규 졸업자가 지원할 수 있으면 true. 원문이 '○년 이상 경력 필수',
  '경력자만', '특급·1급 선임자로 실무경력 필요'처럼 경력을 요구하면 false.
  (자격증만 요구하는 것은 true — 자격증은 학생도 딸 수 있다.)
- related: 원문에 적힌 실제 업무가 재난·안전·방재·산업안전·보건관리이면 true.
  원문에서 그런 업무가 확인되지 않으면 false(예: 임업·조리·돌봄·일반행정)
  (공무원 임용시험은 뽑는 분야 중에 재난·안전 관련 직렬이 있으면 true, 그 분야를 duty 에 적는다).

출력은 JSON 배열 하나만: [{{"id": "...", "duty": "...", "quals": "...", "newbie": true, "related": true}}]

{items}"""


def _client(cfg):
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    from shared.llm import client
    return client(cfg)


def _llm_text(cfg, prompt, max_tokens):
    """게이트웨이 Sonnet 5 는 먼저 생각(thinking)에 토큰을 쓰고, 그 양이 실행마다 다르다
    (선별에서 800·4000 토큰을 생각만 하다 답 없이 끝남, 9/29). 비면 한도를 두 배로 한 번 더."""
    for mt in (max_tokens, max_tokens * 2):
        msg = _client(cfg).messages.create(model=cfg.get("model", "claude-sonnet-4-6"),
                                           max_tokens=mt,
                                           messages=[{"role": "user", "content": prompt}])
        text = "".join(getattr(b, "text", "") for b in msg.content)
        if text.strip():
            return text
        log(f"답이 비었음(stop_reason={msg.stop_reason}, max_tokens={mt}) — 한도를 늘려 다시")
    raise RuntimeError("답이 비었습니다 — 두 번 모두 생각만 하다 끝남")


def _ask(cfg, prompt, max_tokens=3000):
    text = _llm_text(cfg, prompt, max_tokens)
    i = text.find("[")
    return json.JSONDecoder().raw_decode(text[i:])[0] if i >= 0 else []


def _ask_obj(cfg, prompt, max_tokens=4000):
    """JSON 객체 하나를 돌려받는다(원서접수센터 공고 한 건 요약용)."""
    text = _llm_text(cfg, prompt, max_tokens)
    i = text.find("{")
    if i < 0:
        raise ValueError("JSON 없음")
    return json.JSONDecoder().raw_decode(text[i:])[0]


def pick(cfg, cands, n=MAX_JOBS):
    rows = "\n".join(f"{i}. {'[공공] ' if c.get('public') else ''}{c['company']} | {c['title']}"
                     for i, c in enumerate(cands))
    ids = _ask(cfg, PICK.format(n=n, rows=rows), 12000)
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
    # 여섯 건씩 나눠 묻는다 — 18건을 한 번에 물으니 생각(thinking)까지 합쳐 한도를 넘겨
    # JSON 이 중간에 잘렸다(2026-09-29). 한 묶음이 실패하면 한 번 더 묻는다.
    res = {}
    for k in range(0, len(items), 6):
        for attempt in (1, 2):
            try:
                got = _ask(cfg, SUMMARIZE.format(items="\n\n".join(items[k:k + 6])), 8000)
                res.update({r.get("id"): r for r in got if isinstance(r, dict)})
                break
            except (ValueError, RuntimeError) as e:
                log(f"요약 {k // 6 + 1}묶음 실패({attempt}/2): {type(e).__name__}: {str(e)[:80]}")
    keep = []
    for j in jobs:
        r = res.get(j["id"], {})
        j["duty"] = (r.get("duty") or "").strip() or "공고 원문 참고"
        j["quals"] = (r.get("quals") or "").strip() or "공고 원문 참고"
        # 특급 소방안전관리자는 실무경력이 있어야 딸 수 있는 자격이다. 모델 판정이 실행마다
        # 달라서(9/29 같은 공고가 한 번은 빠지고 한 번은 남음) 규칙으로 뺀다.
        if NO_FIRE.search(j["title"] + j["duty"] + j["quals"]):
            log(f"제외(소방 관련): {j['company']} | {j['title'][:40]}")
            continue
        if re.search(r"특급|기술사|지도사", j["title"] + j["quals"]):
            # 기술사·산업안전지도사도 응시에 실무경력이 필요한 자격이다(한국안전 공고가 실행마다 판정이 갈림)
            log(f"제외(경력이 필요한 자격): {j['company']} | {j['title'][:40]}")
            continue
        if r.get("newbie") is False:
            log(f"제외(원문상 경력 필요): {j['company']} | {j['title'][:40]}")
            continue
        if r.get("related") is False:
            log(f"제외(재난안전 무관): {j['company']} | {j['title'][:40]}")
            continue
        keep.append(j)
    return keep


# ── 글 만들기 ────────────────────────────────────────────────────────────────
def _pay(p):
    return p or "공고 원문 참고"


def _md(d):
    return f"{int(d[5:7])}.{int(d[8:10])}" if len(d) == 10 else d


def build(jobs):
    now = datetime.now()
    week = (now.day - 1) // 7 + 1
    npub = sum(1 for j in jobs if j.get("public"))
    ngov = sum(1 for j in jobs if j.get("gov"))
    extra = " (공무원·공공기관 포함)" if ngov else " (공공기관 포함)" if npub else ""
    title = (f"[채용정보] 신입 지원 가능한 재난안전·안전관리 채용공고 {len(jobs)}선"
             f"{extra} | {now.month}월 {week}주차")
    intro = (f"이번 주({_md((now - timedelta(days=DAYS)).strftime('%Y-%m-%d'))}~{_md(now.strftime('%Y-%m-%d'))}) "
             "고용24와 지방자치단체 인터넷원서접수센터에 올라온 재난안전 분야 채용공고 중 신입이 지원할 수 있는 공고"
             "(신입 모집·경력무관)만 모았습니다."
             + (f" 공무원·공공기관 공고 {npub}건을 앞에 두었습니다." if npub else "")
             + ("" if ngov else " 이번 주 원서접수센터에는 재난·안전 직렬 신입 공채 공고가 없었습니다.") + "\n"
             "공고마다 핵심만 요약했으니, 관심 있는 공고는 아래 링크로 원문을 꼭 확인해 주세요.")
    blocks = []
    circled = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"
    for i, j in enumerate(jobs):
        car = {"신입": "신입", "경력무관": "경력무관(신입 가능)", "관계없음": "경력무관(신입 가능)"
               }.get(j["career"], j["career"])
        if j.get("gov"):
            car = {"공개경쟁": "공개경쟁(신입 가능)", "경력경쟁": "경력경쟁(자격증 요건)"}.get(j.get("exam_type"), "")
        cond = " · ".join(x for x in (car, j["edu"]) if x)
        if j.get("gov"):
            a = j.get("apply", "").split(" ~ ")
            period = (f"원서접수 {_md(a[0])} ~ {_md(a[1])}" if len(a) == 2
                      else "원서접수 기간은 공고문 참고")
        else:
            period = (f"{_md(j['reg'])} ~ 채용 시까지" if j["until_hired"] or not j["deadline"]
                      else f"{_md(j['reg'])} ~ {_md(j['deadline'])} 마감")
        quals = j["quals"] if not cond else f"{cond} / {j['quals']}"
        duty_label = "모집 직렬" if j.get("gov") else "담당업무"
        text = "\n".join([
            f"{circled[i] if i < len(circled) else str(i + 1) + '.'} "
            f"{'[공무원] ' if j.get('gov') else '[공공] ' if j.get('public') else ''}{j['company']}",
            f"{j['title']}",
            f"· {duty_label}: {j['duty']}",
            f"· 급여: {_pay(j['pay'])}",
            f"· 자격요건: {quals}",
            f"· 지원기간: {period}",
        ])
        blocks.append({"text": text, "url": j["url"],
                       "link_text": "👉 원서접수센터 원본 공고 보기" if j.get("gov") else "👉 고용24 원본 공고 보기"})
    outro = ("─────────────\n"
             "※ 출처: 고용24(work24.go.kr) 채용정보"
             + (", 지방자치단체 인터넷원서접수센터(local.gosi.go.kr) 시험공고(공공누리 제4유형)"
                if any(j.get("gov") for j in jobs) else "") +
             ". 요약은 편의를 위한 것이며, 급여·자격·마감일 등 "
             "세부 조건은 반드시 원본 공고에서 확인하세요. 마감 전에 채용이 끝날 수도 있습니다.\n"
             "세명대학교 재난안전학과는 매주 일요일 재난안전 분야 채용정보를 정리해 올립니다. "
             "이웃추가하고 다음 주 공고도 받아보세요!")
    return {
        "title": title, "body": intro, "link_blocks": blocks, "outro": outro,
        "category": CATEGORY, "no_banner": False,
        "tags": ["채용정보", "신입채용", "재난안전채용", "공무원채용", "방재", "안전관리자",
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
    if "--rewrite" in sys.argv:
        # --rewrite <logNo> <초안.json> [--go]: 이미 올린 글을 초안 내용으로 고쳐 쓴다
        i = sys.argv.index("--rewrite")
        log_no, path = sys.argv[i + 1], sys.argv[i + 2]
        saved = json.load(open(path, encoding="utf-8"))
        jobs = saved.pop("jobs")
        r = rewrite(log_no, saved, go="--go" in sys.argv)
        if r.get("status") == "published":
            _save_state(jobs)
            log(f"✅ 채용정보 고쳐쓰기 발행: {saved['title']}")
        return 0
    if "--publish" in sys.argv:
        # --list 로 만든 초안(posts/jobs_*.json)을 그대로 올린다 — 다시 고르면 모델이 다른
        # 공고를 고를 수 있어, 사람이 본 글과 올라가는 글이 달라진다.
        path = sys.argv[sys.argv.index("--publish") + 1]
        saved = json.load(open(path, encoding="utf-8"))
        jobs = saved.pop("jobs")
        return _publish(saved, jobs, go=True)
    mode = next((a for a in sys.argv[1:] if a in ("--dry", "--go", "--list")), None)
    if not mode:
        raise SystemExit("사용: jobs_work24.py --list | --dry | --go | --publish posts/jobs_….json")
    cfg = load_config()
    # 지자체 공무원 공채(원서접수센터) — 고용24 공무원 공고는 대부분 임기제 경력직이다
    try:
        from jobs_gosi import collect as collect_gosi
        gov = collect_gosi(lambda prompt: _ask_obj(cfg, prompt), posted=_load_state())
    except Exception as e:
        log(f"원서접수센터 수집 건너뜀: {type(e).__name__}: {e}")
        gov = []
    cands = collect()
    jobs = pick(cfg, cands, MAX_JOBS + 6) if len(cands) >= 1 else []
    log(f"채용정보: {len(jobs)}건 선택 — " + ", ".join(j["company"] for j in jobs))
    jobs = summarize(cfg, jobs) if jobs else []
    pub = [j for j in jobs if j.get("public")]
    jobs = (gov + pub + [j for j in jobs if not j.get("public")])[:MAX_JOBS]   # 공무원·공공을 앞에
    if len(jobs) < MIN_JOBS:
        log("채용정보: 원문 확인 뒤 남은 공고가 너무 적어 이번 주는 올리지 않음")
        return 0
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
    return _publish(data, jobs, go=(mode == "--go"))


def rewrite(log_no, data, go=False):
    """이미 올린 채용정보 글의 제목과 본문(인사말부터 끝까지)을 새 목록으로 바꾼다.

    상단 배너는 그대로 두고, '이번 주(' 로 시작하는 인사말 문단부터 글 끝까지 선택해
    지운 뒤 발행 때와 같은 방식(요약 + 원본 링크)으로 다시 입력한다. 소방 공고를 빼고
    다른 공고로 채울 때 썼다(2026-09-29). go=False 면 입력만 하고 발행 전에 멈춘다."""
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    from publish_naver import (MOD_KEY, _type_text, build_driver, click_if_present,
                               insert_link_blocks, shot, type_contenteditable)
    driver = build_driver(load_config().get("publish", {}).get("headless", False))
    try:
        driver.get(f"https://blog.naver.com/PostUpdateForm.naver?blogId=studs23&logNo={log_no}")
        time.sleep(5)
        try:
            driver.switch_to.alert.accept()
        except Exception:
            pass
        try:
            WebDriverWait(driver, 15).until(EC.frame_to_be_available_and_switch_to_it((By.ID, "mainFrame")))
        except Exception:
            pass
        time.sleep(3)
        click_if_present(driver, By.CSS_SELECTOR, ".se-popup-button-cancel", timeout=3)
        click_if_present(driver, By.CSS_SELECTOR, ".se-help-panel-close-button", timeout=2)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, ".se-component.se-text .se-text-paragraph")))
        time.sleep(1)
        def select_span(a, b):
            """a 요소의 왼쪽 위 첫 글자부터 b 요소의 오른쪽 아래 끝까지 마우스로 선택한다.
            Cmd+A·Cmd+Shift+↓·줄 단위 이동은 에디터에서 문단 전체를 잡지 못했다(9/29)."""
            ra, rb = a.rect, b.rect
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", a)
            time.sleep(0.3)
            ActionChains(driver).move_to_element_with_offset(
                a, -ra["width"] / 2 + 1, -ra["height"] / 2 + 4).click().perform()
            time.sleep(0.2)
            # 클릭이 첫 글자 뒤에 떨어져 한 글자가 남았다('[[채용정보', '이이번 주') — 줄 맨 앞으로
            ActionChains(driver).key_down(MOD_KEY).send_keys(Keys.ARROW_LEFT).key_up(MOD_KEY).perform()
            time.sleep(0.2)
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", b)
            time.sleep(0.3)
            ActionChains(driver).key_down(Keys.SHIFT).move_to_element_with_offset(
                b, rb["width"] / 2 - 1, rb["height"] / 2 - 4).click().key_up(Keys.SHIFT).perform()
            time.sleep(0.2)
            # 마지막 줄 끝까지 확실히
            ActionChains(driver).key_down(Keys.SHIFT).key_down(MOD_KEY).send_keys(Keys.ARROW_RIGHT) \
                .key_up(MOD_KEY).key_up(Keys.SHIFT).perform()
            time.sleep(0.3)

        # 제목: 제목 문단 전체를 선택해 지우고 새 제목으로
        t = driver.find_element(By.CSS_SELECTOR, ".se-section-documentTitle .se-text-paragraph")
        select_span(t, t)
        ActionChains(driver).send_keys(Keys.BACKSPACE).perform()
        time.sleep(0.3)
        ActionChains(driver).send_keys(data["title"]).perform()
        time.sleep(0.5)
        # 본문: 인사말 문단 맨 앞 → 글 끝까지 선택 → 지우기
        intro = next((p for p in driver.find_elements(
            By.CSS_SELECTOR, ".se-component.se-text .se-text-paragraph")
            if (p.text or "").strip().startswith("이번 주(")), None)
        if intro is None:
            shot(driver, f"jobs_rewrite_nointro_{log_no}")
            raise RuntimeError("인사말 문단('이번 주(')을 찾지 못해 고치지 않습니다.")
        last = driver.find_elements(By.CSS_SELECTOR, ".se-component.se-text .se-text-paragraph")[-1]
        select_span(intro, last)
        ActionChains(driver).send_keys(Keys.BACKSPACE).perform()
        time.sleep(1)
        left = " ".join(p.text for p in driver.find_elements(
            By.CSS_SELECTOR, ".se-component.se-text .se-text-paragraph"))
        if "원본 공고 보기" in left or "① " in left:
            shot(driver, f"jobs_rewrite_notcleared_{log_no}")
            raise RuntimeError("기존 목록이 다 지워지지 않아 멈춥니다(스크린샷 확인).")
        _type_text(driver, data["body"])
        insert_link_blocks(driver, data["link_blocks"], data.get("outro", ""))
        time.sleep(1)
        shot(driver, f"jobs_rewrite_typed_{log_no}")
        # 입력 결과 점검 — 제목, 배너, 링크 수, 공고 수, 소방 흔적
        doc = driver.execute_script(
            "return document.querySelector('.se-section-documentTitle').innerText + '\\n=====\\n' +"
            " [...document.querySelectorAll('.se-component')].map(c => c.classList.contains('se-image') ?"
            " '[이미지]' : c.innerText).join('\\n')")
        links = driver.execute_script(
            "return [...document.querySelectorAll('.se-component.se-text *')]"
            ".filter(e => /원본 공고 보기/.test(e.innerText||'') && (e.tagName==='A' || /link/.test(e.className))).length")
        items = len(re.findall(r"^[①-⑮] ", doc, re.M))
        log(f"고쳐쓰기 점검: 링크 {links}개, 공고 {items}건, 이미지 {doc.count('[이미지]')}장, "
            f"'소방' {'있음' if '소방' in doc else '없음'}")
        with open(os.path.join(POSTS_DIR, f"_rewrite_{log_no}.txt"), "w", encoding="utf-8") as f:
            f.write(doc)
        title_now = doc.split("\n=====")[0].strip()
        if title_now != data["title"]:
            log(f"고쳐쓰기 점검: 제목 불일치 → {title_now!r}")
        if (items != len(data["link_blocks"]) or links < len(data["link_blocks"]) or "소방" in doc
                or title_now != data["title"] or doc.count("이번 주(") != 1):
            raise RuntimeError("고쳐쓴 본문 점검 실패 — 발행하지 않습니다(_rewrite_*.txt 확인)")
        if not go:
            log("채용정보 고쳐쓰기: [DRY] 입력까지 하고 발행 전에 멈춤")
            return {"status": "dry"}
        if not click_if_present(driver, By.XPATH,
                "//button[contains(@class,'publish') and contains(.,'발행')]", 6):
            click_if_present(driver, By.XPATH, "//*[contains(@class,'publish_btn')]", 6)
        time.sleep(2)
        shot(driver, f"jobs_rewrite_layer_{log_no}")
        if not click_if_present(driver, By.XPATH,
                "//div[contains(@class,'layer') or contains(@class,'option')]"
                "//button[contains(@class,'confirm') and contains(.,'발행')]", 6):
            click_if_present(driver, By.XPATH, "//button[contains(@class,'confirm_btn')]", 6)
        time.sleep(6)
        shot(driver, f"jobs_rewrite_done_{log_no}")
        return {"status": "published"}
    finally:
        driver.quit()


def _publish(data, jobs, go):
    from make_banner import make_banner
    try:
        data["banner"] = make_banner("재난안전 분야 채용공고", f"{datetime.now():%Y년 %m월 %d일}",
                                     badge="JOB INFO")
    except Exception as e:
        log(f"배너 생성 실패, 배너 없이 진행: {e}")
    from publish_naver import publish
    r = publish(data, dry_run=not go)
    if go and r.get("status") == "published":
        _save_state(jobs)
        log(f"✅ 채용정보 발행: {data['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
