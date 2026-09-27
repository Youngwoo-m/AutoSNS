"""이미 발행된 글에 화면 캡처를 뒤늦게 끼워 넣는다.

따라하기 단계 글은 글을 만들 때 정해지므로, 보통은 글이 나간 뒤에야 무엇을 찍어야
할지 알게 된다. 그래서 캡처를 shots/<slug>/ 에 넣고 이걸 돌리면 이미 올라간 글의
따라하기 칸만 고쳐 준다. 본문 글·제목·라벨·주소는 건드리지 않는다.

  ./.venv/bin/python geoai_shots_apply.py <slug>          # 무엇이 바뀔지만 보여 준다
  ./.venv/bin/python geoai_shots_apply.py <slug> --go     # 실제로 반영

우리가 만든 마크업(_howto_html)만 다룬다 — Blogger 화면에서 손으로 고친 글이라면
형태가 달라져 못 찾을 수 있고, 그때는 아무것도 바꾸지 않고 멈춘다.
"""
import html as _html
import os
import re
import sys

from common import load_config, log

HOWTO_HEAD = "<h3>🖥️ 화면에서 따라하기</h3>"


def _find_post(svc, bid, slug):
    """slug 에 해당하는 발행된 글을 찾는다."""
    from geoai_series import TOPICS, post_title
    topic = next((t for t in TOPICS if t[0] == slug), None)
    if topic is None:
        raise SystemExit(f"그런 slug 가 없습니다: {slug}")
    want = post_title(topic).strip()
    for p in svc.posts().list(blogId=bid, maxResults=100).execute().get("items", []):
        if p["title"].strip() == want:
            return p
    raise SystemExit(f"블로그에서 글을 못 찾았습니다: {want}")



def _steps_from_html(html):
    """이미 발행된 글의 따라하기 목록에서 (단계이름, 설명)을 되읽는다.

    낱말로 단계를 찾으려면 그 글의 실제 단계 글이 필요하다 — 파일 번호만 믿으면
    글을 다시 생성해 순서가 바뀐 경우 엉뚱한 자리에 붙는다.

    태그를 걷어낸 뒤 엔티티까지 푼다. 본문은 &gt; 처럼 저장돼 있어, 풀지 않으면
    낱말 대조가 'File'·'Open' 사이의 &gt; 를 낱말로 세고, 그대로 다시 그리면
    도식에 'File &gt; Open Product' 로 찍힌다(2026-09-27 SAR 편에서 확인)."""
    i = html.find(HOWTO_HEAD)
    if i < 0:
        return []
    m = re.search(r"<ol[^>]*>(.*?)</ol>", html[i:], flags=re.S)
    if not m:
        return []
    out = []
    for li in re.findall(r"<li>(.*?)</li>", m.group(1), flags=re.S):
        nm = re.search(r"<strong>(.*?)</strong>", li, flags=re.S)
        name = re.sub(r"<[^>]+>", "", nm.group(1)).strip() if nm else ""
        rest = li[nm.end():] if nm else li
        rest = re.sub(r'<div style="margin:8px 0 4px">.*?</div>', "", rest, flags=re.S)
        desc = re.sub(r"<[^>]+>", " ", rest).strip()
        out.append((_html.unescape(name), _html.unescape(desc)))
    return out


def _replace_head_image(html, url):
    """따라하기 제목 바로 뒤의 그림을 캡처로 바꾼다(없으면 새로 넣는다)."""
    i = html.find(HOWTO_HEAD)
    if i < 0:
        return html, "따라하기 칸 없음"
    after = i + len(HOWTO_HEAD)
    m = re.match(r'\s*<p style="text-align:center"><img [^>]*></p>', html[after:])
    new = ('\n<p style="text-align:center"><img src="%s" alt="따라하기 단계" '
           'style="max-width:100%%;height:auto;border-radius:8px"></p>' % url)
    if m:
        return html[:after] + new + html[after + m.end():], "표지 그림 교체"
    return html[:after] + new + html[after:], "표지 그림 추가"


def _insert_step_shots(html, steps):
    """<ol> 안 N번째 <li> 끝에 캡처를 넣는다. 이미 있으면 갈아 끼운다."""
    i = html.find(HOWTO_HEAD)
    if i < 0:
        return html, 0
    m = re.search(r"<ol[^>]*>(.*?)</ol>", html[i:], flags=re.S)
    if not m:
        return html, 0
    block, done = m.group(1), 0
    items = re.findall(r"<li>.*?</li>", block, flags=re.S)
    out = []
    for n, li in enumerate(items, start=1):
        if n in steps:
            from geoai_series import _shot_html
            cap, url = steps[n]
            li = re.sub(r'<div style="margin:8px 0 4px">.*?</div>', "", li, flags=re.S)
            li = li[:-len("</li>")] + _shot_html(url, cap) + "</li>"
            done += 1
        out.append(li)
    new_block = "\n".join(out)
    start = i + m.start(1)
    return html[:start] + new_block + html[i + m.end(1):], done


def apply_to_published(slug, go=False, cfg=None):
    cfg = cfg or load_config()
    from geoai_blogger import service, blog_id
    from geoai_shots import find, upload_for
    staged = find(slug)
    if not staged["cover"] and not staged["steps"]:
        raise SystemExit(f"shots/{slug}/ 에 캡처가 없습니다. 파일을 먼저 넣으세요.")
    svc = service()
    bid = blog_id(cfg)
    post = _find_post(svc, bid, slug)
    html = post.get("content", "")
    if HOWTO_HEAD not in html:
        raise SystemExit("이 글에는 '화면에서 따라하기' 칸이 없습니다 — 바꾸지 않았습니다.")
    steps = _steps_from_html(html)
    if not go:
        from geoai_shots import match_steps
        m = match_steps(slug, steps)
        print(f"글: {post['title']}\n  {post['url']}")
        print(f"  표지 캡처: {'있음' if staged['cover'] else '없음'}")
        print(f"  이 글의 따라하기 {len(steps)}단계 — 캡처가 붙을 자리:")
        for j, (name, _) in enumerate(steps, start=1):
            cap, path = m.get(j, ("", ""))
            mark = os.path.basename(path) if path else "(없음)"
            print(f"    {j}. {name[:18]:20} ← {mark}")
        print("\n실제로 반영하려면 --go 를 붙이세요.")
        return
    shots = upload_for(slug, cfg, steps=steps)
    note = ""
    if shots.get("cover"):
        html, note = _replace_head_image(html, shots["cover"])
    html, n = _insert_step_shots(html, shots.get("steps", {}))
    if shots.get("cover"):                      # 도식이 아니게 됐으니 안내 문구를 고친다
        html = html.replace(" 위 그림은 순서를 정리한 도식입니다.", "")
    svc.posts().patch(blogId=bid, postId=post["id"], body={"content": html}).execute()
    log(f"화면 캡처 반영: {post['title'][:40]} ({note}, 단계 {n}장)")
    print(f"반영했습니다: {post['url']}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    apply_to_published(sys.argv[1], go="--go" in sys.argv)
