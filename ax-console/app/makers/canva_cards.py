"""④ 제작 — 인스타 변환본(카드 문구)을 Canva 브랜드 템플릿에 채워 카드 PNG 로 만든다.

표준 라이브러리만 쓴다(콘솔 서버 파이썬). Canva 는 CLI(`canva api …`)로 부른다 — 로그인은
CLI 가 가지고 있고, 이 코드는 토큰을 읽지 않는다. 설정: config/canva.json

    from makers import canva_cards as cc
    plan = cc.plan(content, 'dept')          # 문구 나누기 + 글자 수 검사(네트워크 없음)
    r = cc.make(content, 'dept', out_dir)    # 채우기 → PNG 내려받기 → {'files': […], 'design_id', 'edit_url'}
    cc.check_template('dept')                # 템플릿에 필요한 필드가 다 있는지

필드 이름(템플릿 규격, docs/제작_Canva_카드뉴스.md): C1_TITLE·C1_BODY … C6_TITLE·C6_BODY, COVER_IMAGE, HANDLE
"""
import json
import re
import subprocess
import time
import urllib.request
from pathlib import Path

CONSOLE = Path(__file__).resolve().parents[2]
CFG = CONSOLE / 'config' / 'canva.json'
KEYCAP = '️⃣'


class CanvaError(Exception):
    pass


def cfg():
    return json.loads(CFG.read_text())


# ---- 1. 문구 나누기 ----
_START = re.compile(r'^\s*(?:\*\*)?\s*(?:\[?\s*카드\s*(\d+)\s*\]?|(\d+)\s*(?:' + KEYCAP + r'|⃣|[.)\]:]|장))\s*(?:\*\*)?\s*[:.\-–]?\s*(.*)$')
_CAPTION = re.compile(r'^\s*(?:\*\*)?\s*(캡션|본문 캡션|게시글|caption)\s*(?:\*\*)?\s*[:：]\s*(.*)$', re.I)


def _clean(t):
    t = re.sub(r'\*\*(.+?)\*\*', r'\1', t)
    t = re.sub(r'^\s*(제목|본문)\s*[:：]\s*', '', t)
    return t.strip(' \t-–·"“”')


def parse(text):
    """인스타 변환본 → {'cards': [{'title','body'}], 'caption', 'hashtags'}.
    카드 머리: '1️⃣', '1.', '1)', '[카드 1]', '카드 1:' 등. 한 줄 '제목 / 본문' 또는 여러 줄(첫 줄 제목)."""
    cards, cur, cap_lines, in_cap = [], None, [], False
    for raw in (text or '').splitlines():
        ln = raw.rstrip()
        if not ln.strip():
            continue
        m = _CAPTION.match(ln)
        if m:
            in_cap, cur = True, None
            if m.group(2).strip():
                cap_lines.append(m.group(2).strip())
            continue
        m = None if in_cap else _START.match(ln)
        if m:
            cur = {'n': int(m.group(1) or m.group(2)), 'lines': [m.group(3)] if m.group(3).strip() else []}
            cards.append(cur)
            continue
        if in_cap or cur is None or (ln.lstrip().startswith('#') and len(cards) >= 3):
            in_cap = in_cap or ln.lstrip().startswith('#')
            cap_lines.append(ln.strip())
        else:
            cur['lines'].append(ln.strip())
    out = []
    for c in cards:
        joined = [_clean(x) for x in c['lines'] if _clean(x)]
        if not joined:
            continue
        if ' / ' in joined[0]:
            title, body = joined[0].split(' / ', 1)
            body = ' '.join([body] + joined[1:])
        elif len(joined) == 1:   # 한 줄에 제목·본문이 붙은 경우: 첫 문장(?!. — :)에서 나눈다
            m = re.match(r'^(.{2,40}?[?!.](?=\s)|.{2,40}?(?=\s?[—–:]\s))\s*[—–:]?\s*(.+)$', joined[0])
            title, body = (m.group(1), m.group(2)) if m else (joined[0], '')
        else:
            title, body = joined[0], ' '.join(joined[1:])
        out.append({'title': _clean(title).rstrip('.'), 'body': _clean(body)})
    caption = '\n'.join(x for x in cap_lines if not re.fullmatch(r'(#\S+\s*)+', x)).strip()
    tags = re.findall(r'#[^\s#]+', '\n'.join(cap_lines))
    return {'cards': out, 'caption': caption, 'hashtags': list(dict.fromkeys(tags))}


def plan(content, account):
    """카드 6장 배치와 글자 수 검사. 네트워크를 쓰지 않는다."""
    c = cfg()
    text = (content.get('variants') or {}).get('instagram') or ''
    p = parse(text)
    cards, pages = p['cards'], int(c.get('pages', 6))
    problems = []
    if len(cards) < pages - 1:
        problems.append(f'카드 문구가 {len(cards)}장뿐입니다(필요 {pages - 1}~{pages}장). 인스타 변환본의 카드 머리(1️⃣, 1. 등)를 확인하세요')
    if len(cards) > pages:
        problems.append(f'카드 문구가 {len(cards)}장으로 템플릿({pages}쪽)보다 많습니다')
    if len(cards) == pages - 1:  # 마무리 카드는 설정의 고정 문구
        cards = cards + [dict(c['end_card'])]
    lim = c.get('limits', {})
    for i, k in enumerate(cards[:pages], 1):
        for f in ('title', 'body'):
            n = len(k.get(f, ''))
            if f in lim and n > int(lim[f]):
                problems.append(f'{i}번 카드 {"제목" if f == "title" else "본문"} {n}자 (한도 {lim[f]}자): {k[f][:30]}…')
        if not k.get('title'):
            problems.append(f'{i}번 카드 제목이 비었습니다')
    fields = {'HANDLE': c.get('handle', {}).get(account, '')}
    for i, k in enumerate(cards[:pages], 1):
        fields[f'C{i}_TITLE'] = k.get('title', '')
        fields[f'C{i}_BODY'] = k.get('body', '')
    return {'cards': cards[:pages], 'fields': fields, 'caption': p['caption'], 'hashtags': p['hashtags'],
            'problems': problems, 'ok': not problems}


# ---- 2. Canva CLI ----
def cli(*args, body=None, dry=False):
    cmd = [cfg()['cli'], 'api', *args]
    if body is not None:
        cmd += ['--body', json.dumps(body, ensure_ascii=False)]
    if dry:
        cmd.append('--dry-run')
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    out = p.stdout or p.stderr
    try:
        d = json.loads(out[out.index('{'):])
    except ValueError:
        raise CanvaError(f'Canva CLI 응답을 읽지 못함: {out.strip()[:200]}')
    if not d.get('ok'):
        e = d.get('error') or {}
        raise CanvaError(f"{e.get('code', '?')}: {e.get('message', '')} (status {d.get('meta', {}).get('status')})")
    return d.get('data') if not dry else d


def _wait(get_args, pick, what, limit=240):
    """비동기 작업을 지수 간격으로 기다린다(1,2,4,8,15초…)."""
    t0, delay = time.time(), 1
    while True:
        d = cli(*get_args)
        job = d.get('job') or d
        st = job.get('status')
        if st == 'success':
            return pick(job)
        if st == 'failed':
            raise CanvaError(f"{what} 실패: {json.dumps(job.get('error'), ensure_ascii=False)[:300]}")
        if time.time() - t0 > limit:
            raise CanvaError(f"{what}: {limit}초가 지나도 끝나지 않음 (작업 {get_args[-1]})")
        time.sleep(delay)
        delay = min(delay * 2, 15)


def template_id(account):
    tid = (cfg().get('templates') or {}).get(account, '').strip()
    if not tid:
        raise CanvaError(f'{account} 계정의 카드뉴스 브랜드 템플릿 ID 가 config/canva.json 에 없습니다')
    return tid


def check_template(account):
    """템플릿의 데이터 필드를 읽어 규격과 비교한다."""
    d = cli('brand-templates', 'dataset', '--brand-template-id', template_id(account))
    have = {k: v.get('type') for k, v in (d.get('dataset') or {}).items()}
    pages = int(cfg().get('pages', 6))
    need = {**{f'C{i}_{f}': 'text' for i in range(1, pages + 1) for f in ('TITLE', 'BODY')}, 'HANDLE': 'text'}
    missing = [k for k in need if k not in have]
    wrong = [k for k, t in need.items() if k in have and have[k] != t]
    return {'fields': have, 'missing': missing, 'wrong_type': wrong, 'has_cover_image': have.get('COVER_IMAGE') == 'image',
            'ok': not missing and not wrong}


def upload_image(path):
    d = cli('assets', 'create-upload', '--name', Path(path).stem[:50], '--file', str(path))
    jid = (d.get('job') or {}).get('id')
    return _wait(['assets', 'get-upload', '--job-id', jid], lambda j: j['asset']['id'], '이미지 업로드')


def make(content, account, out_dir, image=None, dry=False):
    """카드 디자인을 만들고 PNG 를 내려받는다. dry=True 면 Canva 에 보내지 않고 요청만 검증한다."""
    p = plan(content, account)
    if not p['ok']:
        raise CanvaError('카드 문구 문제: ' + ' / '.join(p['problems']))
    tid = template_id(account) if not dry else ((cfg().get('templates') or {}).get(account) or 'DRY_RUN_TEMPLATE')
    data = {k: {'type': 'text', 'text': v} for k, v in p['fields'].items()}
    if image and not dry:
        data['COVER_IMAGE'] = {'type': 'image', 'asset_id': upload_image(image)}
    title = f"[AX] {content.get('title') or content.get('topic', '')}"[:255]
    body = {'brand_template_id': tid, 'title': title, 'data': data}
    if dry:
        cli('autofill', 'create', body=body, dry=True)
        return {'dry_run': True, 'fields': list(data), 'cards': p['cards']}
    d = cli('autofill', 'create', body=body)
    design = _wait(['autofill', 'get', '--job-id', d['job']['id']], lambda j: j['result']['design'], '템플릿 채우기')
    ex = cfg().get('export', {})
    e = cli('exports', 'create', body={'design_id': design['id'],
                                       'format': {'type': 'png', 'width': ex.get('width', 1080), 'height': ex.get('height', 1350),
                                                  'lossless': False}})
    urls = _wait(['exports', 'get', '--export-id', e['job']['id']], lambda j: j['urls'], 'PNG 내보내기')
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for i, u in enumerate(urls, 1):
        f = out / f'card_{i:02d}.png'
        with urllib.request.urlopen(u, timeout=120) as r:
            f.write_bytes(r.read())
        files.append(str(f))
    return {'design_id': design['id'], 'edit_url': (design.get('urls') or {}).get('edit_url', ''),
            'files': files, 'caption': p['caption'], 'hashtags': p['hashtags'], 'cards': p['cards']}


if __name__ == '__main__':
    import sys
    if sys.argv[1:2] == ['check']:
        print(json.dumps(check_template(sys.argv[2]), ensure_ascii=False, indent=2))
