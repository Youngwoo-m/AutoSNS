"""원본 뉴스 기사에서 대표 이미지(og:image)를 최선노력(best-effort)으로 가져온다.

Google News RSS 링크는 실제 언론사 URL 이 아니라 리다이렉트라서, batchexecute 로
실제 URL 을 복원한 뒤 그 페이지의 og:image 를 추출·다운로드한다.

★ 주의:
- Google 이 방식을 바꾸면 복원이 깨질 수 있다. 그래서 모든 단계는 실패해도 예외를
  던지지 않고 None 을 반환한다(이미지는 '있으면 좋은' 요소, 없어도 게시는 진행).
- 언론사 사진은 대개 저작권이 있다. 재사용 시 출처를 함께 표기하며, 법적 판단은 사용자 몫.
"""
import json
import os
import re
import urllib.parse
import urllib.request

from common import POSTS_DIR, log

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def _resolve_google_news(link):
    """Google News 기사 링크 -> 실제 언론사 URL (실패 시 None)."""
    m = re.search(r"/articles/([^?/]+)", link)
    if not m:
        return link if "news.google.com" not in link else None
    gid = m.group(1)
    try:
        html = _get(f"https://news.google.com/rss/articles/{gid}")
        sig = re.search(r'data-n-a-sg="([^"]+)"', html)
        ts = re.search(r'data-n-a-ts="([^"]+)"', html)
        if not (sig and ts):
            return None
        inner = ('["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,'
                 'null,null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,'
                 'null,0],"%s",%s,"%s"]' % (gid, ts.group(1), sig.group(1)))
        freq = json.dumps([[["Fbv4je", inner, None, "generic"]]])
        body = urllib.parse.urlencode({"f.req": freq}).encode()
        req = urllib.request.Request(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute",
            data=body,
            headers={"User-Agent": UA,
                     "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"})
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode("utf-8", "ignore")
        # 응답에서 Fbv4je 결과(JSON 문자열) 추출 후 파싱
        m2 = re.search(r'\[\\?"garturlres\\?",\\?"(https?:[^\\"]+)', raw)
        if m2:
            return m2.group(1).replace("\\/", "/")
        # 대안: 응답 내 첫 비-google https URL
        for u in re.findall(r'https?://[^\\"\s]+', raw):
            if "google" not in u and "gstatic" not in u:
                return u.replace("\\/", "/")
        return None
    except Exception as e:
        log(f"뉴스 URL 복원 실패(건너뜀): {str(e)[:60]}")
        return None


def _og_image(page_url):
    try:
        html = _get(page_url)
        pats = (
            r'<meta[^>]+property=["\']og:image(?::url)?["\'][^>]+content=["\']([^"\']+)',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
            r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)',
            r'<meta[^>]+itemprop=["\']image["\'][^>]+content=["\']([^"\']+)',
            r'<link[^>]+rel=["\']image_src["\'][^>]+href=["\']([^"\']+)',
        )
        for pat in pats:
            m = re.search(pat, html, re.I)
            if m and m.group(1).strip():
                return _absolutize(m.group(1).strip(), page_url)
        # 폴백: 본문 내 첫 번째 '충분히 커 보이는' 이미지
        for im in re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.I):
            low = im.lower()
            if any(k in low for k in ("logo", "icon", "banner", "btn", "blank",
                                      "1x1", "spacer", ".svg")):
                continue
            if re.search(r'\.(jpg|jpeg|png|webp)', low):
                return _absolutize(im, page_url)
        return None
    except Exception:
        return None


def _absolutize(url, base):
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http"):
        return url
    return urllib.parse.urljoin(base, url)


def _download_image(url, dest):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25) as r:
            data = r.read()
        if len(data) < 3000:  # 너무 작으면 아이콘/깨진 이미지로 간주
            return None
        with open(dest, "wb") as f:
            f.write(data)
        return dest
    except Exception:
        return None


def attach_news_images(news, out_dir=None, max_images=4):
    """news 리스트 각 항목에 대해 원본 기사 이미지를 받아 파일 경로를 붙인다.

    반환: [{title, source, published_str, image(경로 or None)}] 중 image 있는 것만 다운로드.
    실패는 조용히 건너뜀. 최대 max_images 장까지.
    """
    out_dir = out_dir or os.path.join(POSTS_DIR, "news_imgs")
    os.makedirs(out_dir, exist_ok=True)
    got = []
    for i, n in enumerate(news):
        if len(got) >= max_images:
            break
        real = _resolve_google_news(n.get("link", ""))
        if not real:
            continue
        img_url = _og_image(real)
        if not img_url:
            continue
        dest = os.path.join(out_dir, f"news_{i+1:02d}.jpg")
        p = _download_image(img_url, dest)
        if p:
            got.append({"title": n.get("title", ""), "source": n.get("source", ""),
                        "published_str": n.get("published_str", ""), "image": p,
                        "article_url": real})
    log(f"원본 뉴스 이미지 {len(got)}장 확보(최대 {max_images}).")
    return got


if __name__ == "__main__":
    from fetch_news import fetch_news
    res = attach_news_images(fetch_news(), max_images=6)
    for r in res:
        print(f"- {r['title'][:30]}  ({r['source']})\n    {r['image']}\n    {r['article_url'][:70]}")
