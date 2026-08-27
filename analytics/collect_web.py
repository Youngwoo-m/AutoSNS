"""네이버 블로그와 학과 홈페이지 게시물을 수집한다. 표준 라이브러리만 쓴다.

둘 다 로그인 없이 공개 목록을 읽는다.
"""
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analytics.common import log, save_part  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
BLOG_ID = "studs23"
SMDS = "https://www.semyung.ac.kr"
BOARDS = [                          # (게시판 ID, 이름, 기본 유형)
    ("BBSMSTR_000000001938", "포토갤러리", None),      # 유형은 첨부로 판정
    ("BBSMSTR_000000001935", "학과공지", "게시글"),
    ("BBSMSTR_000000002198", "채용정보 및 자료", "게시글"),
]


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def _clean(x):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", x))).strip()


def collect_blog(since):
    """PostTitleListAsync 는 제목이 URL 인코딩돼 있고 응답에 잘못된 이스케이프가 섞여
    json.loads 가 실패한다. 정규식으로 직접 뽑는다."""
    items, page = [], 1
    while page <= 30:
        s = _get(f"https://blog.naver.com/PostTitleListAsync.naver?blogId={BLOG_ID}"
                 f"&viewdate=&currentPage={page}&categoryNo=0&parentCategoryNo=&countPerPage=30")
        found = re.findall(r'"logNo":"(\d+)".*?"title":"(.*?)".*?"addDate":"([^"]+)"', s)
        if not found:
            break
        oldest = "9999"
        for log_no, title, add in found:
            m = re.match(r"(\d{4})\.\s*(\d+)\.\s*(\d+)\.", add.strip())
            date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""
            oldest = min(oldest, date or "9999")
            items.append({
                "title": urllib.parse.unquote_plus(title.replace("\\", "")),
                "date": date, "type": "게시글", "source": "네이버 블로그",
                "url": f"https://blog.naver.com/{BLOG_ID}/{log_no}",
            })
        if oldest < since:
            break
        page += 1
        time.sleep(0.3)
    return items


def _gallery_type(title, files, thumbs, body):
    """포토갤러리 글의 유형 판정.
    영상: 동영상 첨부 / 카드뉴스: 제목에 카드뉴스·뉴스 또는 정보 그래픽 2장 이상 /
    나머지는 이미지(현장 사진·단일 포스터)."""
    if "<object" in body or ".mp4" in body.lower() or "동영상" in title:
        return "영상"
    if re.search(r"카드\s*뉴스|뉴스", title):
        return "카드뉴스"
    photos = any("KakaoTalk" in f for f in files)
    numbered = files and all(re.fullmatch(r"\d+(\.\w+)?", f or "") for f in files)
    if thumbs >= 2 and not photos and (numbered or re.search(r"안내|일정|신청|복지|수강", title)):
        return "카드뉴스"
    return "이미지"


def collect_smds(since):
    # 상단 고정(핀) 공지는 모든 페이지에 다시 나온다. nttId 로 중복을 걸러야
    # 페이지 수만큼 부풀지 않는다.
    items, seen = [], set()
    for bbs, name, fixed in BOARDS:
        page = 1
        while page <= 30:
            s = _get(f"{SMDS}/cop/bbs/{bbs}/selectBoardList.do?pageIndex={page}")
            rows, oldest = [], "9999"
            if fixed:                                   # 표 형식 게시판
                for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", s, re.S):
                    nid = re.search(r"nttId=(\d+)", tr)
                    dt = re.search(r"(\d{4}-\d{2}-\d{2})", _clean(tr))
                    ttl = re.search(r"nttId=\d+[^\"]*\"[^>]*>(.*?)</a>", tr, re.S)
                    if nid and dt:
                        rows.append((nid.group(1), _clean(ttl.group(1)) if ttl else "", dt.group(1)))
            else:                                       # 포토갤러리(li 형식)
                block = re.search(r'<ul class="creative_list"[^>]*>(.*?)</ul>', s, re.S)
                for li in re.findall(r"<li>(.*?)</li>", block.group(1), re.S) if block else []:
                    nid = re.search(r"nttId=(\d+)", li)
                    ttl = re.search(r"alt='([^']*)'", li)
                    dt = re.search(r"(\d{4}-\d{2}-\d{2})", li)
                    if nid and dt:
                        rows.append((nid.group(1), _clean(ttl.group(1)) if ttl else "", dt.group(1)))
            if not rows:
                break
            for nid, title, date in rows:
                oldest = min(oldest, date)
                if date < since or nid in seen:
                    continue
                seen.add(nid)
                url = f"{SMDS}/cop/bbs/{bbs}/selectBoardArticle.do?nttId={nid}"
                kind, pages = fixed, 0
                if not fixed:                           # 갤러리는 상세를 열어 유형 판정
                    a = _get(url)
                    gt = re.search(r'<div id="galleryText">(.*?)</div>', a, re.S)
                    files = [html.unescape(x) for x in re.findall(r"value='([^']*)'", gt.group(1))] if gt else []
                    th = re.search(r'<div id="galleryThum">(.*?)<a class="arrLeft"', a, re.S)
                    pages = len(re.findall(r'<li class="item">', th.group(1))) if th else 0
                    bv = re.search(r'<div class="bbs-view-content[^"]*">(.*?)</div>', a, re.S)
                    kind = _gallery_type(title, files, pages, bv.group(1) if bv else "")
                    time.sleep(0.2)
                items.append({"title": title.lstrip("📢 ").strip(), "date": date, "type": kind,
                              "source": name, "pages": pages, "url": url})
            if oldest < since:
                break
            page += 1
            time.sleep(0.25)
    return items


if __name__ == "__main__":
    since = sys.argv[1] if len(sys.argv) > 1 else "2026-03-01"
    blog = collect_blog(since)
    save_part("blog", {"items": [x for x in blog if x["date"] >= since]})
    smds = collect_smds(since)
    save_part("smds", {"items": smds})
    log(f"블로그 {len(blog)}건 수집(기간내 {sum(1 for x in blog if x['date'] >= since)}건), 홈페이지 {len(smds)}건")
