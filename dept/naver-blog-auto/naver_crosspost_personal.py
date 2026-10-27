"""개인 티스토리 글을 개인 네이버 블로그(safeworking)에 교차 발행한다.

티스토리 공개 글(HTML)을 소제목·문단·표(줄 글)·그림으로 바꿔 네이버 스마트에디터에 입력한다.
학과 계정(chrome-profile)은 건드리지 않고 chrome-profile-safeworking 프로필만 쓴다(login_setup_safeworking.py 로 로그인).
학과 CTA·학과 해시태그는 넣지 않는다. 표의 열은 ' | ' 로 이은 줄이 되고, 따라쓰기 PDF 같은 첨부는 티스토리 원문 링크로 안내한다.

    python3 shared/axlock.py 를 스스로 거친다(profile:safeworking).
    ./.venv/bin/python naver_crosspost_personal.py --tistory-url https://na-geoai.tistory.com/119 \
        --assets-dir ../../GeoAI_NA/civil-engineer-writing/04일차_온도균열 --category "카테고리" --dry|--go

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
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["AX_NAVER_PROFILE"] = os.path.join(HERE, "chrome-profile-safeworking")
os.environ["AX_NAVER_ID"] = "safeworking"
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

BLOG_ID = "safeworking"
UA = {"User-Agent": "Mozilla/5.0"}


def out(status, url="", message=""):
    print(json.dumps({"status": status, "url": url, "message": message}, ensure_ascii=False))
    return 0 if status in ("published", "dry") else 1


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode("utf-8", "replace")


def article_body(page):
    m = re.search(r'<div class="(?:tt_article_useless_p_margin|contents_style)[^>]*>(.*?)<div class="(?:container_postbtn|another_category)', page, re.S)
    if not m:
        raise RuntimeError("티스토리 본문을 찾지 못함")
    return m.group(1)


def fix(t):
    """네이버 에디터가 줄머리 '1. ' 을 자동 번호 목록으로 바꿔 글자를 지우므로 '1) ' 로 쓴다.
    주소로 끝나는 줄은 뒤에 공백을 둬야 자동 링크가 확정돼 다음 줄 ENTER 가 먹히지 않는 일이 없다."""
    t = re.sub(r"^(\d+)\.\s+", r"\1) ", t)
    return t + " " if re.search(r"https?://\S+\)?$", t) else t


def join_lines(lines):
    """문단 사이는 빈 줄 하나, 같은 종류의 목록·표 줄은 바로 아래줄에 이어 쓴다."""
    out, prev = "", None
    for kind, t in lines:
        if prev is not None:
            out += "\n" if kind == prev and kind in ("li", "row") else "\n\n"
        out += t
        prev = kind
    return out


class Conv(HTMLParser):
    """본문 HTML → (intro, blocks[{heading, lines[], image}], tags). 문단은 줄 단위로 모은다."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.intro, self.blocks, self.tags = [], [], []
        self.cur = None            # 현재 소제목 블록
        self.buf, self.row, self.hrefs = [], [], []
        self.mode = None           # p / li / h / cell / bq
        self.in_row = False
        self.images = []
        self.skip = False          # 파일 첨부 카드(fileblock) 안의 글자는 버린다

    def _target(self):
        return self.cur["lines"] if self.cur else self.intro

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("h2", "h3"):
            self.buf, self.mode = [], "h"
        elif tag in ("p", "li", "blockquote"):
            self.buf, self.hrefs, self.mode = [], [], {"p": "p", "li": "li", "blockquote": "bq"}[tag]
        elif tag == "tr":
            self.row, self.in_row = [], True
        elif tag in ("td", "th"):
            self.buf, self.mode = [], "cell"
        elif tag == "a" and a.get("href", "").startswith("http"):
            self.hrefs.append(a["href"])
        elif tag == "figure" and "fileblock" in (a.get("class") or ""):
            self.skip = True
        elif tag == "figure" and "imageblock" in (a.get("class") or ""):
            fn = a.get("data-filename")
            if fn and self.cur is not None:
                self.cur.setdefault("images", []).append(fn)
            elif fn:
                self.images.append(fn)

    def handle_data(self, data):
        if self.mode and not self.skip:
            self.buf.append(data)

    def handle_endtag(self, tag):
        if tag == "figure":
            self.skip = False
        txt = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        if tag in ("h2", "h3") and self.mode == "h":
            self.cur = {"heading": txt, "lines": []}
            self.blocks.append(self.cur)
            self.mode = None
        elif tag in ("td", "th") and self.mode == "cell":
            self.row.append(txt)
            self.mode = None
        elif tag == "tr":
            if self.row:
                self._target().append(("row", fix(" | ".join(self.row))))
            self.in_row = False
        elif tag in ("p", "li", "blockquote") and self.mode in ("p", "li", "bq"):
            if txt.startswith("#") and re.fullmatch(r"(#\S+\s*)+", txt):
                self.tags = [t.lstrip("#") for t in txt.split()]
            elif txt:
                urls = [u for u in self.hrefs if "tistory.com" not in u and u not in txt]
                if self.mode == "li":
                    txt = "• " + txt
                elif self.mode == "bq":
                    txt = "「" + txt + "」"
                if urls and self.mode == "li":
                    txt += " (" + urls[0] + ")"
                self._target().append(("li" if self.mode == "li" else "p", fix(txt)))
            self.mode = None


# 작업 이름 접두 → safeworking 카테고리 (2026-10-26 분리)
JOB_CATEGORY = (("survey", "측량·GIS 기술사"), ("civil", "토목시공기술사"), ("building", "건축시공기술사"), ("nordic", "노르딕워킹·건강"), ("safekorea", "안전한국훈련·재난"))


def category_for(job):
    j = (job or "").split(":")[-1].replace("claude.", "")
    for prefix, name in JOB_CATEGORY:
        if j.startswith(prefix):
            return name
    return "게시판"


def build_data(url, assets_dir, category, tags_arg):
    page = get(url)
    m = re.search(r'<meta property="og:title" content="([^"]+)"', page)
    title = html.unescape(m.group(1)) if m else ""
    c = Conv()
    c.feed(article_body(page))
    blocks = []
    for b in c.blocks:
        blk = {"heading": fix(b["heading"]), "paragraph": join_lines(b["lines"])}
        imgs = b.get("images") or []
        if imgs:
            path = os.path.join(assets_dir, imgs[0])
            if not os.path.exists(path):
                raise RuntimeError(f"그림 파일이 없음: {path}")
            blk["image"] = path
            if len(imgs) > 1:
                print(f"  그림 {len(imgs)}장 중 첫 장만 넣음: {b['heading']}", file=sys.stderr)
        blocks.append(blk)
    tags = [t.strip() for t in tags_arg.split(",") if t.strip()] if tags_arg else c.tags
    return {
        "title": title,
        "category": category,
        "intro": join_lines(c.intro),
        "news_blocks": blocks,
        "outro": f"표와 따라쓰기 PDF가 들어 있는 전체 글은 티스토리 원문에서 볼 수 있습니다.\n{url}",
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
    ap.add_argument("--assets-dir", default=HERE, help="본문 그림 원본이 있는 폴더(figure 의 data-filename 과 같은 이름). 그림 없는 글은 생략")
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
        data = build_data(args.tistory_url, os.path.abspath(args.assets_dir), args.category or category_for(args.job), args.tags)
    except Exception as e:
        return out("error", message=f"{type(e).__name__}: {e}")
    print(f"제목: {data['title']} | 소제목 {len(data['news_blocks'])}개 | 그림 {sum(1 for b in data['news_blocks'] if b.get('image'))}장 | 태그 {data['tags']}", file=sys.stderr)
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
