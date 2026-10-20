"""뉴스 원본 기사에서 대표 이미지(og:image)를 가져와 로컬에 저장한다.

Google News RSS 링크는 실제 기사로의 JS 리다이렉트라 그대로는 이미지를 못 얻는다.
그래서 news.google.com 의 batchexecute(Fbv4je) 로 '실제 기사 URL'을 디코딩한 뒤,
그 페이지의 og:image 를 받아 posts/images_<stamp>/ 에 내려받는다.

전부 best-effort: 디코딩/추출/다운로드가 실패하면 그 항목만 건너뛴다(자동화는 계속).
인터페이스: fetch_images(data) -> [로컬 이미지 경로]. data['news_images'] 채움.
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request

from common import POSTS_DIR, load_config, log

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
BATCH_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"


def _get(url, timeout=15, data=None, headers=None):
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _resolve_google_news(link):
    """news.google.com/rss/articles/{id} → 실제 기사 URL (실패 시 None)."""
    if "news.google.com" not in link or "/articles/" not in link:
        return link  # 이미 실제 URL 이면 그대로
    art_id = link.split("/articles/")[1].split("?")[0]
    html = _get("https://news.google.com/rss/articles/" + art_id).decode("utf-8", "ignore")
    sg = re.search(r'data-n-a-sg="([^"]+)"', html)
    ts = re.search(r'data-n-a-ts="([^"]+)"', html)
    if not (sg and ts):
        return None
    inner = ('["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,'
             'null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],"'
             + art_id + '",' + ts.group(1) + ',"' + sg.group(1) + '"]')
    payload = [[["Fbv4je", inner, None, "generic"]]]
    body = ("f.req=" + urllib.parse.quote(json.dumps(payload))).encode()
    resp = _get(BATCH_URL, data=body,
                headers={"Content-Type":
                         "application/x-www-form-urlencoded;charset=UTF-8"}
                ).decode("utf-8", "ignore")
    part = json.loads(resp.split("\n\n")[1])[:-2]
    return json.loads(part[0][2])[1]


def _og_image(url):
    html = _get(url).decode("utf-8", "ignore")
    m = (re.search(r'<meta[^>]+property=["\']og:image["\'][^>]*content=["\']([^"\']+)', html)
         or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*property=["\']og:image', html))
    if not m:
        return None
    return urllib.parse.urljoin(url, m.group(1))


def _download(img_url, out_path):
    raw = _get(img_url, timeout=20)
    if len(raw) < 2000:  # 너무 작으면 아이콘/깨진 이미지로 간주
        return False
    with open(out_path, "wb") as f:
        f.write(raw)
    return True


def _needed_indices(data, limit):
    """장면이 참조한 출처 번호(1-based)를 순서대로, 중복 없이. 없으면 앞에서부터 채운다."""
    idxs = []
    for s in data.get("scenes", []):
        si = s.get("src_idx")
        if isinstance(si, int) and si not in idxs:
            idxs.append(si)
    if not idxs:  # 대본에 출처 표기가 없으면 앞쪽 기사부터
        idxs = list(range(1, len(data.get("sources") or []) + 1))
    return idxs[:limit]


def fetch_images(data):
    cfg = load_config()
    if not cfg.get("news_images", {}).get("enabled", True):
        data["source_images"] = {}
        return {}

    limit = int(cfg.get("news_images", {}).get("max", 4))
    sources = data.get("sources") or []
    stamp = data.get("stamp") or time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(POSTS_DIR, f"images_{stamp}")
    os.makedirs(out_dir, exist_ok=True)

    # 설명란에 노출되는 출처(최대 6개)의 실제 기사 URL을 미리 디코딩 →
    # 지저분한 Google News 리다이렉트 대신 깔끔한 '바로 열리는' 링크로.
    show_n = int(cfg.get("news_images", {}).get("resolve_links", 6))
    for s in sources[:show_n]:
        try:
            real = _resolve_google_news(s.get("link", ""))
            if real:
                s["real_link"] = real
        except Exception as e:
            log(f"출처 링크 디코딩 건너뜀: {repr(e)[:60]}")

    # 장면이 근거한 기사 사진만 골라 받는다(장면-사진 내용 일치 보장).
    source_images = {}
    for idx in _needed_indices(data, limit):
        if not (1 <= idx <= len(sources)):
            continue
        s = sources[idx - 1]
        try:
            real = s.get("real_link") or _resolve_google_news(s.get("link", ""))
            if not real:
                continue
            s["real_link"] = real  # 설명란 출처 링크로 재사용(깔끔한 실제 URL)
            img = _og_image(real)
            if not img:
                continue
            ext = os.path.splitext(urllib.parse.urlparse(img).path)[1].lower()
            if ext not in (".jpg", ".jpeg", ".png", ".webp"):
                ext = ".jpg"
            out = os.path.join(out_dir, f"src{idx:02d}{ext}")
            if _download(img, out):
                source_images[str(idx)] = out
                log(f"출처{idx} 이미지 저장: {os.path.basename(out)}")
        except Exception as e:
            log(f"이미지 수집 건너뜀(출처{idx}): {repr(e)[:80]}")

    data["source_images"] = source_images
    with open(os.path.join(POSTS_DIR, f"{stamp}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log(f"뉴스 이미지 {len(source_images)}장 확보(요청 {len(sources)}건 중, 장면 매칭).")
    return source_images


if __name__ == "__main__":
    import glob
    files = sorted(glob.glob(os.path.join(POSTS_DIR, "*.json")))
    if not files:
        raise SystemExit("먼저 generate_script.py 를 실행하세요.")
    with open(files[-1], "r", encoding="utf-8") as f:
        d = json.load(f)
    for k, p in fetch_images(d).items():
        print(f"출처{k}: {p}")
