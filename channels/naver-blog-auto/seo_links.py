"""smuds2026 입시 연재의 내부 링크를 맞춘다: 목차 페이지 + 각 글 끝 이전/다음 링크.

구글이 블로거 글을 '발견됨 - 색인 안 됨' 으로 두는 것을 줄이려는 것이 목적이다.
(라벨 페이지 /search/label/... 은 robots.txt 로 막히므로 글끼리 직접 링크가 크롤 경로가 된다)

- 목차는 글이 아닌 '페이지'(/p/…)로 만든다 → 하루 2편 발행 상한·RSS·티스토리 요약에 안 걸린다.
- 글 끝 링크는 <!--series-nav--> 표식 사이만 바꾼다. 여러 번 돌려도 같은 결과다(멱등).
- 연재가 새로 올라온 날 다시 돌리면 목차와 이전/다음이 갱신된다.

사용 (youtube-shorts-auto/.venv 로):  python seo_links.py            # 미리보기
                                         python seo_links.py --apply    # 실제 반영
"""
import html
import re
import sys

import post_blogger as pb                       # noqa: E402
from common import log                          # noqa: E402

LABEL = "입시"
TOC_TITLE = "세명대 재난안전학과 입시 연재 목차 | 14편 한눈에"
SERIES_TOTAL = 14
HOME = "https://smusafe.blogspot.com/2026/10/blog-post.html"      # 학과 소개글
TISTORY = "https://na-geoai.tistory.com/"
GEOAI = "https://geoaina.blogspot.com/"
NAV_RE = re.compile(r"\s*<!--series-nav-->.*?<!--/series-nav-->", re.S)


def _svc():
    from googleapiclient.discovery import build
    return build("blogger", "v3", credentials=pb._creds(), cache_discovery=False)


def _series(svc, bid):
    items, tok = [], None
    while True:
        r = svc.posts().list(blogId=bid, labels=LABEL, maxResults=50, orderBy="PUBLISHED",
                             pageToken=tok, fields="nextPageToken,items(id,title,url,published)").execute()
        items += r.get("items", [])
        tok = r.get("nextPageToken")
        if not tok:
            break
    return sorted(items, key=lambda p: p["published"])


def _short(title):
    """'세명대 재난안전학과는 무엇을 배우나 | 4년 과정 한눈에 [1/14]' → 보여줄 짧은 제목."""
    return re.sub(r"\s*\[\d+/\d+\]\s*$", "", title).strip()


def toc_html(posts, toc_url=None):
    lis = "".join(
        f'<li>[{i}/{SERIES_TOTAL}] <a href="{html.escape(p["url"])}">{html.escape(_short(p["title"]))}</a></li>'
        for i, p in enumerate(posts, 1))
    soon = f"<p>{len(posts) + 1}편부터 {SERIES_TOTAL}편까지는 매일 한 편씩 올라옵니다.</p>" \
        if len(posts) < SERIES_TOTAL else ""
    return (
        "<p>세명대학교 재난안전학과 입시를 14편으로 나눠 정리하는 연재의 목차입니다. "
        "학과가 무엇을 배우는지부터 수시·정시, 지역인재 전형, 고등학교 준비까지 순서대로 이어집니다.</p>"
        f"<h3>연재 목록</h3><ol style='list-style:none;padding-left:0'>{lis}</ol>{soon}"
        "<h3>함께 보면 좋은 곳</h3><ul>"
        f'<li><a href="{HOME}">세명대 재난안전학과 소개 | 무엇을 배우고 졸업 후 어디로 가나</a></li>'
        f'<li><a href="{TISTORY}">GeoAI 티스토리</a></li>'
        f'<li><a href="{GEOAI}">GeoAI 블로그</a></li></ul>')


def nav_html(posts, i, toc_url):
    prev_ = f'<a href="{html.escape(posts[i-1]["url"])}">← 이전 글</a>' if i > 0 else "← 첫 글입니다"
    next_ = f'<a href="{html.escape(posts[i+1]["url"])}">다음 글 →</a>' if i + 1 < len(posts) else "다음 글은 곧 올라옵니다"
    return ('<!--series-nav--><hr><p style="text-align:center">'
            f'{prev_} · <a href="{html.escape(toc_url)}">입시 연재 목차</a> · {next_}</p>'
            '<!--/series-nav-->')


def main(argv):
    apply = "--apply" in argv
    cfg = pb.load_config()
    bid = cfg["blogger"]["blog_id"]
    svc = _svc()
    posts = _series(svc, bid)
    log(f"입시 연재 {len(posts)}편 확인")

    page = next((p for p in svc.pages().list(blogId=bid, fields="items(id,title,url)").execute().get("items", [])
                 if p["title"] == TOC_TITLE), None)
    body = toc_html(posts)
    if apply:
        if page:
            svc.pages().patch(blogId=bid, pageId=page["id"], body={"content": body}).execute()
        else:
            page = svc.pages().insert(blogId=bid, body={"title": TOC_TITLE, "content": body}).execute()
        log(f"목차 페이지: {page['url']}")
        toc_url = page["url"]
    else:
        toc_url = page["url"] if page else "(목차 페이지 새로 만듦)"
        log(f"[미리보기] 목차 페이지: {toc_url}")

    for i, p in enumerate(posts):
        cur = svc.posts().get(blogId=bid, postId=p["id"], fields="content").execute()["content"]
        new = NAV_RE.sub("", cur) + nav_html(posts, i, toc_url)
        changed = new != cur
        log(f"  {'수정' if changed else '그대로'} [{i+1}] {_short(p['title'])[:30]}")
        if apply and changed:
            svc.posts().patch(blogId=bid, postId=p["id"], body={"content": new}).execute()
    if not apply:
        print("\n미리보기였다. 반영하려면 --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
