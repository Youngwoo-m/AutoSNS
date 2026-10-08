"""채용정보 초안(posts/jobs_*.json)을 티스토리(na-geoai.tistory.com) '채용정보' 카테고리에도 올린다.

네이버 블로그와 같은 공고·같은 요약을 HTML 로 싣는다. 공고마다 고용24(또는 원서접수센터)
원본 링크 버튼을 달고, 끝에 네이버 블로그 글 링크를 둔다. 올리는 날 기준으로 마감이 지난
공고는 뺀다(일요일 글을 주중에 올릴 때). 글쓰기 화면 조작은 tistory_crosspost.py 것을 쓴다.

    ./.venv/bin/python tistory_jobs.py posts/jobs_….json --dry   # 발행 직전에 멈춤
    ./.venv/bin/python tistory_jobs.py --latest --go              # 가장 최근 초안으로(run_jobs.sh)
"""
import glob
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

from common import BASE_DIR, log

CATEGORY = "채용정보"
TAGS = ["채용정보", "신입채용", "재난안전", "안전관리자", "산업안전", "건설안전", "공무원채용", "취업정보"]


def _md(d):
    return f"{int(d[5:7])}.{int(d[8:10])}" if d and len(d) == 10 else d


def _naver_url(title):
    """같은 주 네이버 채용정보 글 주소(제목이 같은 글)."""
    try:
        u = ("https://blog.naver.com/PostTitleListAsync.naver?blogId=studs23&viewdate=&currentPage=1"
             "&categoryNo=9&parentCategoryNo=&countPerPage=10")
        s = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}),
                                   timeout=20).read().decode("utf-8", "replace")
        for log_no, t in re.findall(r'"logNo":"(\d+)".*?"title":"(.*?)"', s):
            if urllib.parse.unquote_plus(t).strip() == title.strip():
                return f"https://blog.naver.com/studs23/{log_no}"
    except Exception:
        pass
    return "https://blog.naver.com/PostList.naver?blogId=studs23&categoryNo=9"


def build(draft):
    today = datetime.now().strftime("%Y-%m-%d")
    jobs = [j for j in draft["jobs"] if not j.get("deadline") or j["deadline"] >= today]
    dropped = len(draft["jobs"]) - len(jobs)
    if len(jobs) < 3:
        return None
    # 제목: 네이버 제목의 공고 수만 실제 수로
    title = re.sub(r"채용공고 \d+선", f"채용공고 {len(jobs)}선", draft["title"])
    naver = _naver_url(draft["title"])
    P = [f"<p>{html.escape(draft['body'].splitlines()[0])}</p>",
         "<p>공고마다 핵심만 요약했습니다. 관심 있는 공고는 <b>원본 공고</b>에서 자격·마감일을 꼭 확인해 주세요.</p>"]
    if dropped:
        P.append(f'<p style="color:#7b8794;font-size:14px">※ 올리는 날({_md(today)}) 기준 마감이 지난 공고 {dropped}건은 뺐습니다.</p>')
    circled = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"
    for i, j in enumerate(jobs):
        tag = "[공무원] " if j.get("gov") else "[공공] " if j.get("public") else ""
        car = {"신입": "신입", "경력무관": "경력무관(신입 가능)", "관계없음": "경력무관(신입 가능)"}.get(j.get("career"), j.get("career") or "")
        cond = " · ".join(x for x in (car, j.get("edu")) if x)
        quals = j.get("quals") or "공고 원문 참고"
        if j.get("gov"):
            a = (j.get("apply") or "").split(" ~ ")
            period = f"원서접수 {_md(a[0])} ~ {_md(a[1])}" if len(a) == 2 else "원서접수 기간은 공고문 참고"
        elif j.get("until_hired") or not j.get("deadline"):
            period = f"{_md(j.get('reg'))} ~ 채용 시까지"
        else:
            period = f"{_md(j.get('reg'))} ~ {_md(j['deadline'])} 마감"
        src = "원서접수센터" if j.get("gov") else "고용24"
        rows = [("담당업무" if not j.get("gov") else "모집 직렬", j.get("duty") or "공고 원문 참고"),
                ("급여", j.get("pay") or "공고 원문 참고"),
                ("자격요건", f"{cond} / {quals}" if cond else quals),
                ("지원기간", period)]
        P.append(f"<h3>{circled[i] if i < len(circled) else str(i + 1) + '.'} {html.escape(tag + j['company'])}</h3>")
        P.append(f"<p><b>{html.escape(j['title'])}</b></p>")
        P.append("<ul>" + "".join(f"<li><b>{k}</b>: {html.escape(v)}</li>" for k, v in rows) + "</ul>")
        P.append(f'<p><a href="{html.escape(j["url"])}" target="_blank" rel="noopener">👉 {src} 원본 공고 보기</a></p>')
    P.append("<hr>")
    P.append("<p style=\"font-size:14px;color:#555\">※ 출처: 고용24(work24.go.kr) 채용정보"
             + (", 지방자치단체 인터넷원서접수센터(local.gosi.go.kr) 시험공고(공공누리 제4유형)" if any(j.get("gov") for j in jobs) else "")
             + ". 요약은 편의를 위한 것이며, 급여·자격·마감일 등 세부 조건은 반드시 원본 공고에서 확인하세요.</p>")
    P.append(f'<p style="margin:24px 0 8px;text-align:center"><a href="{html.escape(naver)}" target="_blank" rel="noopener" '
             'style="display:inline-block;background:#0b1c3a;color:#fff;padding:12px 26px;border-radius:999px;'
             'text-decoration:none;font-weight:700">세명대 재난안전학과 블로그에서 보기 →</a></p>')
    P.append('<p style="font-size:13px;color:#7b8794;text-align:center">세명대학교 재난안전학과는 매주 일요일 '
             '재난안전 분야 신입 채용정보를 정리해 올립니다.</p>')
    return {"title": title, "body": "\n".join(P), "count": len(jobs)}


def main():
    import tistory_crosspost as T
    go = "--go" in sys.argv
    if "--latest" in sys.argv:
        files = sorted(glob.glob(os.path.join(BASE_DIR, "posts", "jobs_2*.json")), key=os.path.getmtime)
        path = files[-1] if files else None
        if not path or time.time() - os.path.getmtime(path) > 6 * 3600:
            log("티스토리 채용정보: 최근 초안 없음 — 건너뜀")
            return 0
    else:
        path = next((a for a in sys.argv[1:] if a.endswith(".json")), None)
        if not path:
            raise SystemExit(__doc__)
    key = "jobs:" + os.path.basename(path)
    s = T.state()
    if key in s["posted"]:
        log(f"티스토리 채용정보: 이미 올린 초안({os.path.basename(path)}) — 건너뜀")
        return 0
    draft = json.load(open(path, encoding="utf-8"))
    if go and "--latest" in sys.argv:
        try:
            naver = json.load(open(os.path.join(BASE_DIR, "posts", "jobs_posted.json"), encoding="utf-8"))
        except Exception:
            naver = {}
        if not any(j["id"] in naver for j in draft.get("jobs", [])):
            log("티스토리 채용정보: 블로그에 발행되지 않은 초안 — 건너뜀")
            return 0
    post = build(draft)
    if not post:
        log("티스토리 채용정보: 마감 안 된 공고가 3건 미만 — 건너뜀")
        return 0
    log(f"티스토리 채용정보 {'발행' if go else '[DRY]'}: {post['title']} ({post['count']}건)")
    d = T.build_driver(headless=False)
    try:
        url = T.write_post(d, {"title": post["title"]}, post["body"], CATEGORY, TAGS, go)
    except Exception as e:
        T._shot(d, "jobs_fail")
        log(f"티스토리 채용정보 실패: {type(e).__name__}: {str(e)[:160]}")
        return 1
    finally:
        d.quit()
    if go:
        s["posted"][key] = {"tistory": url, "title": post["title"], "at": f"{datetime.now():%Y-%m-%d %H:%M}"}
        T.save_state(s)
        log(f"티스토리 채용정보 발행 완료: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
