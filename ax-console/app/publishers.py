"""승인된 콘텐츠를 채널별 기존 발행 코드로 올린다(⑥ 자동 발행).

콘솔 서버가 채널에 맞는 모듈의 .venv 파이썬으로, 그 모듈 폴더에서 부른다.
  블로거·네이버 → naver-blog-auto/.venv,  X → youtube-shorts-auto/.venv

    python publishers.py <콘텐츠 폴더> <계정> <채널> [--dry]

--dry 는 각 채널의 '게시 직전'까지만 한다(블로거: 글 HTML·한도 확인, 네이버: 편집기에
입력하고 발행 버튼 전에 멈춤, X: 글자 수 확인). 결과는 JSON 한 줄:
{"status": "published"|"dry_run"|"skipped"|"error", "url": "...", "detail": "..."}
"""
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.getcwd())

AI_NOTE = '이 글은 AI 도움을 받아 초안을 만들고 사람이 검토해 올렸습니다.'


def md_to_html(md):
    """초안에 쓰는 정도의 마크다운(제목·목록·굵게·문단)만 HTML 로 바꾼다."""
    out, lst = [], None

    def inline(t):
        t = html.escape(t)
        return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t)

    for line in md.splitlines():
        s = line.strip()
        m = re.match(r'^(#{1,6})\s+(.*)', s)
        item = re.match(r'^(?:[-*•]|\d+[.)])\s+(.*)', s)
        if lst and not item:
            out.append(f'</{lst}>')
            lst = None
        if not s:
            continue
        if m:
            lvl = min(len(m.group(1)) + 1, 4)  # 글 제목이 h1 이라 본문은 h2 부터
            out.append(f'<h{lvl}>{inline(m.group(2))}</h{lvl}>')
        elif item:
            tag = 'ol' if s[0].isdigit() else 'ul'
            if lst != tag:
                if lst:
                    out.append(f'</{lst}>')
                out.append(f'<{tag}>')
                lst = tag
            out.append(f'<li>{inline(item.group(1))}</li>')
        else:
            out.append(f'<p>{inline(s)}</p>')
    if lst:
        out.append(f'</{lst}>')
    return '\n'.join(out)


def md_to_text(md):
    t = re.sub(r'^#{1,6}\s+', '', md, flags=re.M)
    # 네이버 편집기는 '- ' 로 시작하는 줄을 자동 목록으로 바꿔 다음 줄까지 망가뜨린다 → '• ' 로
    t = re.sub(r'^\s*[-*]\s+', '• ', t, flags=re.M)
    return re.sub(r'\*\*(.+?)\*\*', r'\1', t).strip()


def blogger(c, account, text, dry):
    if account == 'dept':
        import post_blogger as pb
        from common import load_config
        from googleapiclient.discovery import build
        cfg = load_config()
        b = cfg.get('blogger') or {}
        bid = str(b.get('blog_id', '')).strip()
        svc = build('blogger', 'v3', credentials=pb._creds(cfg), cache_discovery=False)
        limit = int(b.get('daily_limit', 1))
        if pb._posted_today() >= limit:
            return {'status': 'skipped', 'detail': f'학과 블로거 오늘 한도({limit}편)를 이미 썼습니다. 자동 작업과 같은 한도를 씁니다'}
        if pb._already_posted(svc, bid, c['title']):
            return {'status': 'skipped', 'detail': '같은 제목의 글이 이미 있습니다'}
        count = pb._count_post
    else:
        import geoai_blogger as gb
        svc, bid = gb.service(), gb.blog_id()
        n = len(gb.posts_today(svc, bid))
        if n >= 3:
            return {'status': 'skipped', 'detail': f'개인 블로거에 오늘 이미 {n}편이 올라가 있습니다(남용 제한 방지)'}
        if c['title'].strip() in [t.strip() for t in gb.posted_titles(svc, bid, pages=1)]:
            return {'status': 'skipped', 'detail': '같은 제목의 글이 이미 있습니다'}
        count = None
    body = {'kind': 'blogger#post', 'title': c['title'],
            'content': md_to_html(text) + f'<p><em>{AI_NOTE}</em></p>'}
    if dry:
        return {'status': 'dry_run', 'detail': f'블로그 {bid} · 본문 {len(body["content"])}자 · 게시 직전에 멈춤'}
    r = svc.posts().insert(blogId=bid, body=body, isDraft=False).execute()
    if count:
        count()
    return {'status': 'published', 'url': r.get('url', '')}


def naver(c, account, text, dry):
    if account != 'dept':
        return {'status': 'skipped', 'detail': '개인 네이버 계정은 아직 연결 전입니다'}
    from publish_naver import publish
    data = {'title': c['title'], 'body': md_to_text(text) + '\n\n' + AI_NOTE,
            'tags': [], 'summary': c.get('summary', ''),
            'no_banner': True}  # 기본 배너는 '재난안전 브리핑' 서식이라 콘솔 글과 맞지 않는다
    r = publish(data, dry_run=dry)
    st = r.get('status')
    return {'status': 'dry_run' if st == 'dry_run' else 'published' if st == 'published' else 'error',
            'url': r.get('url', ''), 'detail': json.dumps(r, ensure_ascii=False)[:300]}


def x(c, account, text, dry):
    if account != 'dept':
        return {'status': 'skipped', 'detail': 'X 는 학과 계정만 있습니다'}
    import x_post
    from common import load_config
    cfg = load_config()
    t = x_post._fit(md_to_text(text))
    if dry or not (cfg.get('x') or {}).get('enabled'):
        why = '' if dry else ' (config x.enabled 가 꺼져 있어 점검만 함)'
        return {'status': 'dry_run', 'detail': f'{x_post._weight(t)}/{x_post.MAX_WEIGHT}자{why}: {t[:60]}'}
    s = x_post._session(cfg)
    j = x_post._check(s.post(f'{x_post.API}/tweets', json={'text': t}), '게시')
    tid = (j.get('data') or {}).get('id', '')
    url = f"https://x.com/{(cfg.get('x') or {}).get('username', 'i')}/status/{tid}" if tid else ''
    x_post._record(tid, url, t)
    return {'status': 'published', 'url': url}


ADAPTERS = {'blogger': blogger, 'naver_blog': naver, 'x': x}


def main():
    folder, account, channel = sys.argv[1:4]
    dry = '--dry' in sys.argv
    c = json.load(open(os.path.join(folder, 'meta.json')))
    text = (c.get('variants') or {}).get(channel) or c.get('original', '')
    try:
        if channel not in ADAPTERS:
            r = {'status': 'skipped', 'detail': '자동 발행 연결이 없는 채널입니다'}
        else:
            r = ADAPTERS[channel](c, account, text, dry)
    except Exception as e:
        r = {'status': 'error', 'detail': f'{type(e).__name__}: {str(e)[:300]}'}
    print(json.dumps(r, ensure_ascii=False))


if __name__ == '__main__':
    main()
