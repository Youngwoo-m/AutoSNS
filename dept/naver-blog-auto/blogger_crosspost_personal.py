"""개인 티스토리 글(na-geoai)을 개인 Blogger(geoaina.blogspot.com)에 교차 발행한다(2026-10-29).

티스토리 본문 HTML 을 그대로 옮기되 광고·스크립트는 걷어낸다. 카카오 CDN 그림은 주소가 만료되고
티스토리 첨부(PDF)는 referer 가 없으면 막히므로, 받아서 공개 이미지 저장소(geoai_assets 저장소)에
줄이지 않고 올린 jsDelivr 주소로 바꾼다(GIF 는 움직임 그대로). 본문 끝 '#태그' 줄은 빼고 라벨로 넣는다.
글 날짜는 티스토리 원래 발행 시각(article:published_time)으로 맞춘다. 끝에 티스토리 원문 링크와 채널 안내.
같은 제목이 이미 있으면 올리지 않는다. 하루 발행 한도를 GeoAI 글과 같이 쓰므로 quota:blogger-personal 잠금.

    ./.venv/bin/python blogger_crosspost_personal.py --tistory-url https://na-geoai.tistory.com/121 --dry|--go
        --dry 는 정리한 본문을 logs/blogger_cross_<번호>/post.html 로 남기고 올리지 않는다(그림도 올리지 않음).

결과 마지막 줄 JSON: {"status": "published"|"dry"|"duplicate"|"error", "url": …, "message": …}
"""
import argparse
import base64
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from naver_crosspost_personal import article_body, get  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0"}


def out(status, url="", message=""):
    print(json.dumps({"status": status, "url": url, "message": message}, ensure_ascii=False))
    return 0 if status in ("published", "dry") else 1


def _download(url, folder, name, referer=""):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    hd = dict(UA, **({"Referer": referer} if referer else {}))
    with urllib.request.urlopen(urllib.request.Request(url, headers=hd), timeout=60) as r, open(path, "wb") as f:
        f.write(r.read())
    return path


def _upload_raw(path, dest):
    """geoai_assets 저장소에 파일을 줄이지 않고 올리고 jsDelivr 주소를 돌려준다."""
    import geoai_assets as ga
    a = ga._acfg()
    repo, branch = ga.ensure_repo(), a.get("branch", "main")
    with open(path, "rb") as f:
        body = {"message": f"티스토리 교차 발행 자료: {dest}", "content": base64.b64encode(f.read()).decode("ascii"),
                "branch": branch}
    try:
        cur = json.loads(ga._gh(["api", f"repos/{repo}/contents/{urllib.parse.quote(dest)}", "-q", "{sha:.sha}"]) or "{}")
        if cur.get("sha"):
            body["sha"] = cur["sha"]
    except RuntimeError:
        pass
    ga._gh(["api", "--method", "PUT", f"repos/{repo}/contents/{urllib.parse.quote(dest)}", "--input", "-"],
           input=json.dumps(body))
    return f"https://cdn.jsdelivr.net/gh/{repo}@{branch}/{urllib.parse.quote(dest)}"


def _safe_name(name):
    base, ext = os.path.splitext(name)
    base = re.sub(r"[^\w가-힣.-]+", "_", base).strip("_") or "file"
    return base[:60] + ext.lower()


def build(url, workdir, upload):
    """티스토리 글 → (제목, 정리한 본문, 라벨, 고정 라벨, 발행 시각, 자료 수)."""
    page = get(url)
    no = url.rstrip("/").split("/")[-1]
    m = re.search(r'<meta property="og:title" content="([^"]+)"', page)
    title = html.unescape(m.group(1)).strip() if m else ""
    m = re.search(r'<meta property="article:published_time" content="([^"]+)"', page)
    published = m.group(1) if m else None
    # 글의 카테고리: 본문 위 경로 링크(사이드바 메뉴는 class="link_…" 가 붙는다) 중 마지막
    cats = [html.unescape(c).strip() for c in re.findall(r'href="/category/[^"]+">([^<]+)<', page)]
    body = article_body(page)
    # 광고·스크립트·티스토리 앱 자리 걷어내기
    body = re.sub(r"<script\b.*?</script>", "", body, flags=re.S)
    body = re.sub(r"<ins\b.*?</ins>", "", body, flags=re.S)
    body = re.sub(r'<div data-tistory-react-app="[^"]*"></div>', "", body)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    # 태그: 본문 끝 '#태그' 줄 → 없으면 티스토리 태그 목록. 그 줄은 본문에서 뺀다
    tags = []
    hm = re.findall(r"<p[^>]*>\s*((?:#[^\s<#]+\s*)+)</p>", body)
    if hm:
        tags = [t.lstrip("#") for t in hm[-1].split()]
    else:
        tm = re.search(r'<div class="box-tag">(.*?)</div>', page, re.S)
        tags = [html.unescape(t).strip() for t in re.findall(r'rel="tag">([^<]+)<', tm.group(1))] if tm else []
    body = re.sub(r"<p[^>]*>\s*(?:#[^\s<#]+\s*)+</p>", "", body)

    counts = {"image": 0, "file": 0}

    def put(src, name, referer=""):
        if not upload:
            return src
        p = _download(src, workdir, name, referer)
        return _upload_raw(p, f"tistory/{no}/{name}")

    def fileblock(m):
        a = re.search(r'href="([^"]+)"', m.group(0))
        n = re.search(r'class="name">([^<]+)<', m.group(0))
        if not a:
            return ""
        href = html.unescape(a.group(1))
        name = html.unescape(n.group(1)).strip() if n else os.path.basename(urllib.parse.urlparse(href).path)
        counts["file"] += 1
        link = put(href, _safe_name(name), referer=url)
        return (f'<p>📎 첨부 파일: <a href="{html.escape(link)}" target="_blank" rel="noopener">'
                f'{html.escape(name)}</a></p>')

    def figure(m):
        fig = m.group(0)
        srcs = re.findall(r'<img[^>]+src="([^"]+)"', fig)
        if not srcs:
            return fig
        alts = re.findall(r'<img[^>]+alt="([^"]*)"', fig)
        parts = []
        for i, src in enumerate(srcs):
            src = html.unescape(src)
            if "kakaocdn.net" in src or "daumcdn.net" in src or "tistory.com" in src:
                fn = re.search(r'data-filename="([^"]+)"', fig)
                ext = os.path.splitext(fn.group(1) if fn else urllib.parse.urlparse(src).path)[1].lower() or ".png"
                counts["image"] += 1
                src = put(src, f"img{counts['image']:02d}{ext}")
            alt = html.unescape(alts[i]) if i < len(alts) else title
            parts.append(f'<p style="text-align:center"><img src="{html.escape(src)}" alt="{html.escape(alt)}" '
                         f'style="max-width:100%;height:auto"></p>')
        cap = re.search(r"<figcaption[^>]*>(.*?)</figcaption>", fig, re.S)
        if cap and cap.group(1).strip():
            parts.append(f'<p style="text-align:center;color:#666;font-size:0.9em">{cap.group(1)}</p>')
        return "".join(parts)

    body = re.sub(r'(?:<p[^>]*>\s*)?<figure class="fileblock".*?</figure>(?:\s*</p>)?', fileblock, body, flags=re.S)
    body = re.sub(r"<figure\b.*?</figure>", figure, body, flags=re.S)
    # 남은 티스토리 그림(본문에 바로 든 <img>)
    for src in set(re.findall(r'<img[^>]+src="(https?://[^"]*(?:kakaocdn|daumcdn)\.net[^"]*)"', body)):
        counts["image"] += 1
        ext = os.path.splitext(urllib.parse.urlparse(html.unescape(src)).path)[1].lower() or ".png"
        body = body.replace(src, html.escape(put(html.unescape(src), f"img{counts['image']:02d}{ext}")))
    body = re.sub(r'\s(?:onerror|srcset|data-[\w-]+)="[^"]*"', "", body)
    body = body.strip() + (f'<hr><p>이 글은 티스토리에 먼저 올린 글입니다. 원문: '
                           f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{html.escape(url)}</a></p>')
    return {"title": title, "body": body, "tags": tags, "category": cats[1] if len(cats) > 1 else (cats[0] if cats else ""),
            "published": published, "counts": counts}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tistory-url", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry", action="store_true")
    g.add_argument("--go", action="store_true")
    ap.add_argument("--job", default="claude")
    a = ap.parse_args()
    if os.environ.get("AX_DRY") == "1":
        a.go = False
    no = a.tistory_url.rstrip("/").split("/")[-1]
    workdir = os.path.join(HERE, "logs", f"blogger_cross_{no}")
    import geoai_blogger as gb
    try:
        if a.go:
            if gb.gcfg().get("enabled") is False:
                return out("error", message="config.json 의 geoai.enabled 가 꺼져 있습니다")
            # 그림을 올리기 전에 중복부터 본다
            t = build(a.tistory_url, workdir, upload=False)["title"]
            if t.strip() in gb.posted_titles(gb.service(), gb.blog_id(), pages=8):
                return out("duplicate", message="같은 제목 글이 이미 있습니다")
        d = build(a.tistory_url, workdir, upload=a.go)
    except Exception as e:
        return out("error", message=f"{type(e).__name__}: {str(e)[:300]}")
    if re.search(r'(src|href)="(?!https?://)[^"#]', d["body"]):
        return out("error", message="본문에 http(s) 가 아닌 그림·링크 주소가 남았습니다")
    html_body = gb.compose(d["body"], title=d["title"])
    pinned = [d["category"]] if d["category"] else []
    print(f"{no}: {d['title'][:50]} | {d['published']} | 분류 {d['category']} | 태그 {d['tags']} | 자료 {d['counts']}",
          file=sys.stderr)
    if not a.go:
        os.makedirs(workdir, exist_ok=True)
        with open(os.path.join(workdir, "post.html"), "w", encoding="utf-8") as f:
            f.write(html_body)
        r = gb.publish(d["title"], html_body, d["tags"], dry_run=True, pinned=pinned, published=d["published"])
        return out("dry", message=f"라벨: {', '.join(r.get('labels', []))} | {os.path.join(workdir, 'post.html')}")
    from shared.axlock import Timeout, hold, stopped
    if stopped():
        return out("error", message="비상 정지 중이라 발행하지 않았습니다")
    try:
        with hold(["quota:blogger-personal"], job=f"{a.job}:blogger_cross", wait=2400):
            r = gb.publish(d["title"], html_body, d["tags"], pinned=pinned, published=d["published"])
    except Timeout:
        return out("error", message="40분 기다려도 개인 Blogger 한도 잠금이 비지 않았습니다")
    if r.get("status") == "published":
        return out("published", r.get("url", ""))
    if r.get("status") == "duplicate":
        return out("duplicate", message="같은 제목 글이 이미 있습니다")
    return out("error", message=r.get("error") or json.dumps(r, ensure_ascii=False)[:300])


if __name__ == "__main__":
    sys.exit(main())
