"""개인 티스토리 글을 개인 네이버 블로그(safeworking)에 교차 발행한다.

티스토리 공개 글 본문(HTML)을 네이버 스마트에디터에 붙여넣어 소제목·표·인용·구분선·링크·번호를 그대로 옮기고,
그림(GIF 포함)과 첨부(PDF)는 원문에서 받아 제자리에 올린다(naver_paste.py, 2026-10-28). macOS 클립보드를 쓴다.
학과 계정(chrome-profile)은 건드리지 않고 chrome-profile-safeworking 프로필만 쓴다(login_setup_safeworking.py 로 로그인).
학과 CTA·학과 해시태그는 넣지 않는다. 끝에 티스토리 원문 링크 한 줄을 붙인다. 붙인 뒤 표·인용·구분선·그림·첨부 수와
소제목이 원문과 다르면 발행하지 않고 error 로 끝난다.

    python3 shared/axlock.py 를 스스로 거친다(profile:safeworking).
    ./.venv/bin/python naver_crosspost_personal.py --tistory-url https://na-geoai.tistory.com/119 \
        --category "카테고리" --dry|--go

결과 마지막 줄 JSON: {"status": "published"|"dry"|"duplicate"|"error", "url": …, "message": …}
"""
import argparse
import html
import json
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
# 로그인 프로필은 본 체크아웃에만 있다(워크트리에서 돌려도 본 체크아웃 프로필을 쓴다)
_MAIN = os.path.realpath(os.path.join(HERE, "..", ".."))
if "/.claude/worktrees/" in _MAIN:
    _MAIN = _MAIN.split("/.claude/worktrees/")[0]
os.environ["AX_NAVER_PROFILE"] = os.path.join(_MAIN, "dept", "naver-blog-auto", "chrome-profile-safeworking")
os.environ["AX_NAVER_ID"] = "safeworking"
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

BLOG_ID = "safeworking"
UA = {"User-Agent": "Mozilla/5.0"}


def out(status, url="", message=""):
    print(json.dumps({"status": status, "url": url, "message": message}, ensure_ascii=False))
    return 0 if status in ("published", "dry") else 1


def get(url):
    # 티스토리가 가끔 500 을 낸다(2026-10-28) → 5초 뒤 한 번 더
    for i in range(2):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if i or e.code < 500:
                raise
            time.sleep(5)


def article_body(page):
    m = re.search(r'<div class="(?:tt_article_useless_p_margin|contents_style)[^>]*>(.*?)<div class="(?:container_postbtn|another_category)', page, re.S)
    if not m:
        raise RuntimeError("티스토리 본문을 찾지 못함")
    return m.group(1)


# 작업 이름 접두 → safeworking 카테고리 (2026-10-26 분리)
JOB_CATEGORY = (("survey", "측량기술사"), ("civil", "토목시공기술사"), ("building", "건축시공기술사"), ("safety", "건설안전기술사"), ("nordic", "노르딕워킹·건강"), ("safekorea", "안전한국훈련·재난"))


def category_for(job):
    j = (job or "").split(":")[-1].replace("claude.", "")
    for prefix, name in JOB_CATEGORY:
        if j.startswith(prefix):
            return name
    return "게시판"


def build_data(url, workdir, category, tags_arg):
    page = get(url)
    m = re.search(r'<meta property="og:title" content="([^"]+)"', page)
    title = html.unescape(m.group(1)) if m else ""
    body = article_body(page)
    tags = [t.strip() for t in tags_arg.split(",") if t.strip()] if tags_arg else []
    if not tags:
        # 본문 끝 '#태그' 줄 → 없으면 티스토리 글의 태그 목록(184·189 는 태그 줄이 없어 태그 없이 발행됐다, 2026-10-28)
        hm = re.findall(r"<p[^>]*>\s*((?:#[^\s<#]+\s*)+)</p>", body)
        if hm:
            tags = [t.lstrip("#") for t in hm[-1].split()]
        else:
            m = re.search(r'<div class="box-tag">(.*?)</div>', page, re.S)
            tags = [html.unescape(t).strip() for t in re.findall(r'rel="tag">([^<]+)<', m.group(1))] if m else []
    import naver_paste
    pk = naver_paste.prep(body, workdir)
    pk["html"] += f'<p>티스토리 원문: <a href="{html.escape(url)}">{html.escape(url)}</a></p>'
    return {
        "title": title,
        "category": category,
        "paste": pk,
        "tags": tags[:10],
        "no_images": True,
        "no_banner": True,
        "no_cta": True,
    }


def rss_has(title):
    try:
        x = get(f"https://rss.blog.naver.com/{BLOG_ID}.xml")
    except Exception:
        return ""
    for it in re.findall(r"<item>(.*?)</item>", x, re.S):
        t = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
        if t and html.unescape(t.group(1)).strip() == title.strip():
            l = re.search(r"<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>", it, re.S)
            return l.group(1).strip() if l else "found"
    return ""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tistory-url", required=True)
    ap.add_argument("--assets-dir", default="", help="(쓰지 않음) 그림·첨부는 티스토리 원문에서 받는다. 옛 호출과 맞추려고 남김")
    ap.add_argument("--category", default="")
    ap.add_argument("--tags", default="", help="쉼표로 구분(없으면 본문 끝의 #해시태그)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry", action="store_true")
    g.add_argument("--go", action="store_true")
    ap.add_argument("--allow-duplicate", action="store_true")
    ap.add_argument("--job", default="claude")
    args = ap.parse_args()
    if os.environ.get("AX_DRY") == "1" and args.go:
        args.go, args.dry = False, True
    try:
        workdir = os.path.join(HERE, "logs", f"crosspost_{time.strftime('%Y%m%d_%H%M%S')}")
        data = build_data(args.tistory_url, workdir, args.category or category_for(args.job), args.tags)
    except Exception as e:
        return out("error", message=f"{type(e).__name__}: {e}")
    print(f"제목: {data['title']} | 원문 구성 {data['paste']['expect']} | 태그 {data['tags']}", file=sys.stderr)
    if not args.allow_duplicate:
        u = rss_has(data["title"])
        if u:
            return out("duplicate", u, "같은 제목 글이 이미 있어 올리지 않았습니다")
    from shared.axlock import Timeout, hold, stopped
    if args.go and stopped():
        return out("error", message="비상 정지 중이라 발행하지 않았습니다")
    try:
        with hold(["profile:safeworking"], job=f"{args.job}:naver_personal", wait=2400):
            os.environ["AX_LOCKED"] = "1"
            import publish_naver
            publish_naver.publish(data, dry_run=not args.go)
    except Timeout:
        return out("error", message="40분 기다려도 safeworking 크롬 프로필이 비지 않았습니다")
    except Exception as e:
        return out("error", message=f"{type(e).__name__}: {str(e)[:300]}")
    if not args.go:
        return out("dry", message="발행 직전까지 채우고 멈췄습니다(logs/ 에 스크린샷)")
    for _ in range(6):
        time.sleep(5)
        u = rss_has(data["title"])
        if u:
            return out("published", u)
    return out("error", message="발행 버튼은 눌렀으나 RSS 에서 글을 찾지 못했습니다 — 블로그에서 확인 필요")


if __name__ == "__main__":
    sys.exit(main())
