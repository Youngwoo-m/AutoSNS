"""이미 올라간 GeoAI 블로그 글에 카드뉴스·영상을 나중에 붙인다.

하루 1편 원칙 때문에, 글이 이미 나간 날에 미디어만 더하고 싶을 때 쓴다.
(자동 발행은 geoai_daily.py 가 글·카드·영상을 한 번에 만든다)

    python geoai_backfill_media.py            # 최신 글에 무엇을 붙일지만 출력
    python geoai_backfill_media.py --cards --go        # 카드뉴스만 붙이기
    python geoai_backfill_media.py --cards --video --go  # 카드뉴스 + 영상까지

--post <URL> 로 특정 글을 지정할 수 있다(생략하면 최신 글).
"""
import html as _html
import json
import re
import sys

from common import load_config, log
from geoai_blogger import blog_id, img_html, service, video_html


def _text(s):
    """태그를 걷어낸 본문 텍스트."""
    return _html.unescape(re.sub(r"<[^>]+>", " ", s or "")).replace("\xa0", " ").strip()


def fetch_post(svc, bid, url=None):
    r = svc.posts().list(blogId=bid, maxResults=20,
                         fields="items(id,title,url,content,labels)").execute()
    items = r.get("items", [])
    if not items:
        raise SystemExit("글이 없습니다.")
    if url:
        for i in items:
            if i.get("url", "").rstrip("/") == url.rstrip("/"):
                return i
        raise SystemExit(f"그 주소의 글을 찾지 못했습니다: {url}")
    return items[0]


def data_from_post(post):
    """발행된 HTML 에서 대본·카드에 쓸 재료를 뽑는다(제목·3줄요약·소제목/본문)."""
    content = post.get("content", "")
    summary = [_text(li) for li in re.findall(r"<li>(.*?)</li>", content, re.S)][:3]
    sections = []
    for m in re.finditer(r"<h3>(.*?)</h3>(.*?)(?=<h3>|$)", content, re.S):
        head, body = _text(m.group(1)), _text(m.group(2))
        if head.startswith(("📌", "🖼️", "🎬")) or not body:
            continue
        sections.append((head, body[:600]))
    return {"title": post.get("title", ""), "summary": summary,
            "sections": sections, "tags": post.get("labels", [])}


def insert_media(content, images, video_id, title=""):
    """기존 본문은 그대로 두고 앞뒤에 미디어만 끼운다(채널 안내는 이미 글 안에 있다).

    이미 붙어 있는 미디어는 지우고 새로 넣는다(두 번 돌려도 중복되지 않게)."""
    body = re.sub(r"^(?:<p style=\"text-align:center\"><img.*?</p>\s*|<h3>🎬[^<]*</h3>\s*|"
                  r"<p style=\"text-align:center\"><iframe.*?</iframe></p>\s*)+", "",
                  content, flags=re.S)
    body = re.sub(r"<h3>🖼️[^<]*</h3>(?:\s*<p style=\"text-align:center\"><img.*?</p>)+",
                  "", body, flags=re.S)
    head = []
    if images:
        head.append(img_html(images[0], title))
    if video_id:
        head.append("<h3>🎬 1분 브리핑 영상</h3>")
        head.append(video_html(video_id, title))
    tail = []
    if len(images) > 1:
        tail.append("<h3>🖼️ 카드뉴스로 한눈에</h3>")
        tail += [img_html(u, title) for u in images[1:]]
    if tail:            # 카드뉴스 묶음은 채널 안내(<hr>) 앞에 넣는다
        parts = body.rsplit("<hr>", 1)
        body = (parts[0] + "\n".join(tail) + "\n<hr>" + parts[1]) if len(parts) == 2 \
            else body + "\n".join(tail)
    return "\n".join(head + [body])


def main():
    go = "--go" in sys.argv
    want_cards = "--cards" in sys.argv
    want_video = "--video" in sys.argv
    url = None
    if "--post" in sys.argv:
        url = sys.argv[sys.argv.index("--post") + 1]

    cfg = load_config()
    svc = service()
    bid = blog_id(cfg)
    post = fetch_post(svc, bid, url)
    data = data_from_post(post)
    log(f"대상 글: {post['title'][:60]}")
    log(f"  요약 {len(data['summary'])}줄 / 소제목 {len(data['sections'])}개 / 라벨 {len(data['tags'])}개")
    if not go:
        print("\n미리보기(발행/업로드 안 함) — 실제로 붙이려면 --go 를 붙이세요.")
        print(f"  카드뉴스: {'붙임' if want_cards else '안 함'} / 영상: {'만들어 업로드' if want_video else '안 함'}")
        return

    images, video = [], {}
    if want_cards:
        from geoai_daily import make_cards
        images = make_cards(data, cfg, dry_run=False)
    if want_video:
        from geoai_daily import make_video
        video = make_video(data, cfg, dry_run=False)
    if not images and not video.get("video_id"):
        log("붙일 미디어가 없습니다(생성 실패). 글은 그대로 둡니다.")
        return
    new_html = insert_media(post["content"], images, video.get("video_id", ""), post["title"])
    svc.posts().patch(blogId=bid, postId=post["id"], body={"content": new_html}).execute()
    log(f"글 갱신 완료: {post['url']}  (카드 {len(images)}장, 영상 "
        f"{video.get('url') or '없음'})")
    print(json.dumps({"post": post["url"], "images": images, "video": video},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
