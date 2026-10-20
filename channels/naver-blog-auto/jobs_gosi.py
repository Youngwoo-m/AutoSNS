"""지방자치단체 인터넷원서접수센터(local.gosi.go.kr) 시험공고에서 재난·안전 관련 공무원 채용을 찾는다.

jobs_work24.py 가 부른다. 고용24에 올라오는 공무원 공고는 대부분 임기제(경력직)라, 방재안전직
같은 신입 공채는 여기서 가져온다(2026-09-29).

흐름
  1) 시험공고 게시판(examgosi.do, 서버가 그린 HTML)에서 최근 30일 '계획 공고'만 고른다.
     합격·장소·편의지원 안내와 정정 공고는 뺀다.
  2) 공고 본문은 한두 줄뿐이고 내용은 첨부 PDF 에 있다 — PDF 글자를 뽑는다(pypdf).
     재난·안전·방재가 한 번도 안 나오면 모델에 묻지 않고 넘긴다.
  3) 남은 공고만 Claude 가 PDF 글에서 관련 직렬·인원, 응시자격, 원서접수 기간을 뽑는다.
     접수가 끝난 공고는 뺀다.

robots.txt 는 전체 허용. 게시물은 공공누리 제4유형(출처표시·상업적 이용금지·변경금지)이라
글에 출처와 원문 링크를 붙이고 요약만 싣는다.
"""
import html
import http.cookiejar
import io
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from common import log

BASE = "https://local.gosi.go.kr"
LIST = BASE + "/klid/sihum/examgosi.do"
VIEW = BASE + "/klid/sihum/examgosiView.do?strOperOrgCd={org}&strSeq={seq}&strClass=1&strOperYy={yy}"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0 Safari/537.36"
DAYS = 30
PLAN = re.compile(r"계획|채용\s*공고|임용시험\s*공고")      # '…임용시험 시행계획'(공고 없이)도 있다
SKIP = re.compile(r"합격|장소|편의지원|심사결과|결과\s*안내|정정|추가\s*합격|면접|수렵|청원경찰|공무직")
TOPIC = re.compile(r"방재|재난|안전|비상대비|민방위")


def _opener():
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    op.addheaders = [("User-Agent", UA)]
    return op


def _get(op, url, tries=3):
    for n in range(tries):
        try:
            with op.open(url, timeout=60) as r:
                return r.read()
        except Exception:
            if n == tries - 1:
                raise
            time.sleep(3 * (n + 1))


def _notices(op, days=DAYS, pages=4):
    since = (datetime.now() - timedelta(days=days)).strftime("%Y.%m.%d")
    out = []
    for page in range(1, pages + 1):
        b = _get(op, f"{LIST}?pageNo={page}").decode("utf-8", "replace")
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", b, re.S)
        oldest = "9999"
        for r in rows:
            m = re.search(r"fn_view\('(\d+)','(\d+)','(\d+)'[^)]*\)\"\s*title=\"([^\"]+)\"", r)
            d = re.search(r"(\d{4}\.\d{2}\.\d{2})\.", r)
            org = re.findall(r'<td class="mo-hidden">\s*([^<]+?)\s*</td>', r)
            if not m or not d:
                continue
            oldest = min(oldest, d.group(1))
            out.append({"yy": m.group(1), "org": m.group(2), "seq": m.group(3),
                        "title": html.unescape(m.group(4)).strip(), "date": d.group(1),
                        "agency": org[0] if org else ""})
        if oldest < since:
            break
        time.sleep(1)
    return [n for n in out if n["date"] >= since]


def _pdf_text(op, n):
    b = _get(op, VIEW.format(**n)).decode("utf-8", "replace")
    # 첨부 없이 '공고문 바로가기(시도 누리집)' 링크만 있는 공고도 있다(충북 2026 공채 등)
    files = re.findall(r"fn_newFiledown\('([^']+)','(\d+)','([^']+)'\)", b)
    files.sort(key=lambda f: 0 if f[2].lower().endswith(".pdf") else 1 if f[2].lower().endswith(".hwpx") else 2)
    for fid, org, name in files:
        ext = name.lower().rsplit(".", 1)[-1]
        if ext not in ("pdf", "hwpx"):
            continue                              # .hwp(옛 한글)는 읽지 못한다
        raw = _get(op, BASE + "/klid/com/doFileDown.do?" + urllib.parse.urlencode(
            {"atchFileId": fid, "oper_org_cd": org, "fileName": name}))
        if ext == "pdf" and raw.startswith(b"%PDF"):
            import pypdf
            pages = pypdf.PdfReader(io.BytesIO(raw)).pages
            return "\n".join((p.extract_text() or "") for p in pages[:30])
        if ext == "hwpx" and raw.startswith(b"PK"):
            import zipfile
            z = zipfile.ZipFile(io.BytesIO(raw))
            secs = sorted(n for n in z.namelist() if re.match(r"Contents/section\d+\.xml", n))
            return "\n".join(html.unescape(re.sub(r"<[^>]+>", " ", z.read(n).decode("utf-8", "replace")))
                             for n in secs)
    return ""


ASK = """아래는 지방공무원 임용시험 공고문(PDF에서 뽑은 글)이다. 원문에 있는 내용만 쓴다.
- related: 선발 직렬 중에 재난·안전·방재·비상대비와 관련된 직렬(예: 방재안전직, 안전 분야)이
  있으면 true. 소방 관련 직렬만 있으면 false(소방은 싣지 않는다).
- positions: 그 관련 직렬과 직급·인원만 한 줄(60자 이내). 예: '9급 방재안전직 3명'. 관련 직렬이
  없으면 빈 문자열.
- newbie: 공개경쟁 임용시험이면 true. 경력경쟁이면 그 관련 직렬의 응시요건이 자격증·학위만이면
  true, 근무·실무 경력을 요구하면 false.
- quals: 그 관련 직렬의 응시요건 한 줄(60자 이내. 자격증·학위·거주지 등). 연령 조건은 빼도 된다.
- apply: 원서접수 기간 'YYYY-MM-DD ~ YYYY-MM-DD'. 원문에 없으면 빈 문자열.

출력은 JSON 하나만: {{"related": true, "positions": "...", "newbie": true, "quals": "...", "apply": "..."}}

[공고문]
{text}"""


def _for_llm(text):
    """앞부분(선발 직렬·인원, 응시자격) + '원서접수' 부분. 접수 기간은 공고문 뒤쪽에 있어
    앞 7천 자만 보내니 빈칸으로 왔다(2025 경북 공채)."""
    head = text[:6000]
    m = re.search(r"원서\s*접수\s*(기간|일정|및)|접수\s*기간", text[6000:])
    if not m:
        return head
    i = 6000 + m.start()
    return head + "\n…\n" + text[max(6000, i - 200):i + 1500]


def _item(n, duty, quals, apply):
    return {
        "id": f"gosi:{n['org']}:{n['seq']}", "source": "gosi", "public": True, "gov": True,
        "company": n["agency"] or "지방자치단체", "title": n["title"],
        "url": VIEW.format(**n), "duty": duty, "quals": quals,
        "pay": "공무원 보수규정에 따름", "career": "", "edu": "",
        "reg": n["date"].replace(".", "-"), "apply": apply,
        "deadline": apply.split(" ~ ")[-1] if apply else "", "until_hired": False,
        "exam_type": "공개경쟁" if "공개경쟁" in n["title"] else ("경력경쟁" if "경력경쟁" in n["title"] else ""),
    }


def collect(ask_json, posted=(), days=DAYS):
    """관련 공고를 jobs_work24 의 공고 형식으로 돌려준다. ask_json(prompt) -> dict."""
    op = _opener()
    try:
        notices = _notices(op, days)
    except Exception as e:
        log(f"원서접수센터 목록 실패: {type(e).__name__}: {e}")
        return []
    cands = [n for n in notices if PLAN.search(n["title"]) and not SKIP.search(n["title"])]
    log(f"원서접수센터: 최근 {days}일 공고 {len(notices)}건 중 채용계획 {len(cands)}건")
    today = datetime.now().strftime("%Y-%m-%d")
    out = []
    for n in cands:
        nid = f"gosi:{n['org']}:{n['seq']}"
        if nid in posted:
            continue
        try:
            text = _pdf_text(op, n)
        except Exception as e:
            log(f"원서접수센터 PDF 실패({n['title'][:30]}): {type(e).__name__}")
            continue
        time.sleep(1)
        if not text:
            # 공고문을 못 읽었다. 신입 공채(공개경쟁)만 '직렬은 공고문 확인'으로 싣는다 —
            # 학생에게 가장 중요한 공고라 빼지 않되, 방재안전직이 있다고 쓰지는 않는다.
            if "공개경쟁" in n["title"]:
                out.append(_item(n, "직렬·선발인원은 공고문에서 확인(방재안전직 등 선발 여부 확인)",
                                 "공고문 참고", ""))
            continue
        if not TOPIC.search(text[:6000]):
            continue                              # 재난·안전 직렬이 없는 공고 — 모델에 묻지 않는다
        try:
            r = ask_json(ASK.format(text=_for_llm(text)))
        except Exception as e:
            log(f"원서접수센터 요약 실패({n['title'][:30]}): {type(e).__name__}: {str(e)[:60]}")
            continue
        if not isinstance(r, dict) or not r.get("related") or not r.get("positions"):
            continue
        if r.get("newbie") is False:
            log(f"제외(경력 요구): {n['title'][:40]}")
            continue
        m = re.findall(r"\d{4}-\d{2}-\d{2}", r.get("apply") or "")
        if m and m[-1] < today:
            log(f"제외(접수 마감): {n['title'][:40]}")
            continue
        out.append(_item(n, r["positions"], r.get("quals") or "공고문 참고", " ~ ".join(m[:2]) if len(m) >= 2 else ""))
    log(f"원서접수센터: 재난·안전 관련 신입 지원 가능 {len(out)}건")
    return out
