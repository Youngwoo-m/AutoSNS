"""AX 발행 콘솔 서버 (표준 라이브러리만 사용).

실행: python3 ax-console/app/server.py  → http://127.0.0.1:8700
- 계정(학과/개인) → 채널별로 작업을 만들고 고치고 예약한다.
- 예약 시각이 되면 채널에 등록된 실행 작업(기존 run_*.sh)을 돌리고 기록을 남긴다.
- 실행할 수 있는 명령은 아래 ACTIONS 목록뿐이다. 화면에서 임의 명령은 받지 않는다.
"""
import datetime, json, os, subprocess, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CONSOLE = Path(__file__).resolve().parents[1]
ROOT = CONSOLE.parent
DATA = CONSOLE / 'data'
TASKS = DATA / 'tasks.json'
RUNS = DATA / 'runs'
HOST, PORT = '127.0.0.1', int(os.environ.get('AX_PORT', 8700))
LOCK = threading.Lock()

S = lambda p: str(ROOT / p)
# 채널별 실행 작업. memo 는 실행 없이 기록만, test 는 실제 발행 없이 실행 경로만 점검한다.
COMMON = [{'key': 'memo', 'label': '메모 (실행 없음)', 'cmd': None, 'live': False},
          {'key': 'test', 'label': '실행 점검 (발행 안 함)', 'cmd': ['/bin/echo', 'AX 콘솔 실행 점검 OK'], 'live': False}]
ACTIONS = {
    'dept': {
        'youtube': [('shorts_weekly', '숏츠 주간 발행', 'youtube-shorts-auto/run.sh'),
                    ('career_publish', '진로 숏츠 발행', 'youtube-shorts-auto/run_career_publish.sh'),
                    ('caption_backfill', '자막 보충', 'youtube-shorts-auto/run_caption_backfill.sh')],
        'instagram': [('cards_weekly', '카드뉴스 발행', 'insta-cardnews/run.sh'),
                      ('caption_autofix', '캡션 자동 수정', 'insta-cardnews/run_caption_autofix.sh')],
        'naver_blog': [('naver_weekly', '블로그 글 발행', 'naver-blog-auto/run.sh'),
                       ('career_series', '진로 시리즈 발행', 'naver-blog-auto/run_career_series.sh'),
                       ('naver_jobs', '채용 소식 발행', 'naver-blog-auto/run_jobs.sh')],
        'tiktok': [('tiktok_queue', '틱톡 대기열 발행', 'youtube-shorts-auto/run_tiktok_queue.sh')],
        'x': [('x_promo', 'X 홍보글 발행', 'youtube-shorts-auto/run_x_promo.sh')],
        'threads': [], 'blogger': [], 'kakao': [],
    },
    'personal': {
        'blogger': [('geoai_morning', 'GeoAI 아침 글 발행', 'naver-blog-auto/run_geoai.sh'),
                    ('geoai_evening', 'GeoAI 저녁 글 발행', 'naver-blog-auto/run_geoai_evening.sh')],
        'tistory': [('tistory', '티스토리 발행', 'naver-blog-auto/run_tistory.sh')],
        'homepage': [], 'naver_blog': [], 'tiktok': [], 'youtube': [], 'instagram': [],
    },
}
CH_LABEL = {'youtube': '유튜브', 'instagram': '인스타그램', 'naver_blog': '네이버 블로그', 'tiktok': '틱톡',
            'x': 'X', 'threads': '스레드', 'blogger': '블로거', 'kakao': '카카오', 'tistory': '티스토리',
            'homepage': '개인 홈페이지'}


def actions_for(acc, ch):
    out = list(COMMON)
    for key, label, path in ACTIONS.get(acc, {}).get(ch, []):
        out.append({'key': key, 'label': label, 'cmd': ['/bin/bash', S(path)], 'live': True, 'script': path})
    return out


def find_action(acc, ch, key):
    return next((a for a in actions_for(acc, ch) if a['key'] == key), None)


def meta():
    cfg = json.loads((CONSOLE / 'config' / 'accounts.json').read_text())
    accs = []
    for acc, a in cfg['accounts'].items():
        chans = []
        for ch, info in a['channels'].items():
            chans.append({'id': ch, 'label': CH_LABEL.get(ch, ch), 'status': info.get('status', '연결됨'),
                          'detail': info.get('note') or info.get('blog') or info.get('site') or '',
                          'actions': [{k: v for k, v in x.items() if k != 'cmd'} for x in actions_for(acc, ch)]})
        accs.append({'id': acc, 'label': a['label'], 'email': a['google']['email'], 'channels': chans})
    return {'accounts': accs}


def load():
    try:
        return json.loads(TASKS.read_text())
    except (OSError, ValueError):
        return []


def save(tasks):
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = TASKS.with_suffix('.tmp')
    tmp.write_text(json.dumps(tasks, ensure_ascii=False, indent=2))
    tmp.replace(TASKS)


def now():
    return datetime.datetime.now().replace(microsecond=0)


def clean(body, old=None):
    t = dict(old or {})
    for k in ('account', 'channel', 'title', 'body', 'action', 'schedule', 'repeat'):
        if k in body:
            t[k] = str(body[k] or '').strip()[:5000]
    if not find_action(t.get('account'), t.get('channel'), t.get('action')):
        raise ValueError('이 채널에 없는 실행 작업입니다')
    if not t.get('title'):
        raise ValueError('제목을 입력하세요')
    if t.get('schedule'):
        datetime.datetime.fromisoformat(t['schedule'])
    if t.get('repeat') not in ('', 'daily', 'weekly'):
        t['repeat'] = ''
    if body.get('state') in ('draft', 'scheduled'):
        t['status'] = body['state']
    t['status'] = t.get('status') or 'draft'
    if t['status'] == 'scheduled' and not t.get('schedule'):
        raise ValueError('예약하려면 실행 시각을 정하세요')
    return t


def run_task(tid, manual=False):
    with LOCK:
        tasks = load()
        t = next((x for x in tasks if x['id'] == tid), None)
        if not t or t['status'] == 'running':
            return
        t['status'] = 'running'
        save(tasks)
    act = find_action(t['account'], t['channel'], t['action'])
    start = now()
    day = RUNS / start.strftime('%Y-%m-%d')
    day.mkdir(parents=True, exist_ok=True)
    log = day / f"{start.strftime('%H%M%S')}_{tid}.log"
    if act['cmd'] is None:
        code, out = 0, '메모 작업: 실행할 명령 없이 완료로 기록했습니다.\n'
    else:
        try:
            p = subprocess.run(act['cmd'], cwd=str(Path(act['cmd'][-1]).parent) if act.get('script') else str(ROOT),
                               capture_output=True, text=True, timeout=3600)
            code, out = p.returncode, (p.stdout or '') + (p.stderr or '')
        except Exception as e:  # 시간 초과·실행 실패도 기록으로 남긴다
            code, out = -1, f'실행 실패: {e}\n'
    log.write_text(f"작업: {t['title']}\n명령: {act['label']}\n시작: {start}\n\n{out}")
    run = {'at': start.isoformat(), 'end': now().isoformat(), 'code': code, 'manual': manual,
           'log': str(log.relative_to(CONSOLE)), 'tail': out.strip()[-400:]}
    with LOCK:
        tasks = load()
        t = next((x for x in tasks if x['id'] == tid), None)
        if not t:
            return
        t.setdefault('runs', []).insert(0, run)
        t['runs'] = t['runs'][:20]
        step = {'daily': 1, 'weekly': 7}.get(t.get('repeat'))
        if step and not manual and t.get('schedule'):
            nxt = datetime.datetime.fromisoformat(t['schedule'])
            while nxt <= now():
                nxt += datetime.timedelta(days=step)
            t['schedule'] = nxt.isoformat(timespec='minutes')
            t['status'] = 'scheduled'
        elif manual and t.get('_was') == 'scheduled':
            t['status'] = 'scheduled'
        else:
            t['status'] = 'done' if code == 0 else 'failed'
        t.pop('_was', None)
        with (RUNS / 'history.jsonl').open('a') as f:
            f.write(json.dumps({'task': tid, 'account': t['account'], 'channel': t['channel'],
                                'title': t['title'], **run}, ensure_ascii=False) + '\n')
        save(tasks)


def scheduler():
    while True:
        due = []
        with LOCK:
            for t in load():
                if t.get('status') == 'scheduled' and t.get('schedule') and \
                        datetime.datetime.fromisoformat(t['schedule']) <= now():
                    due.append(t['id'])
        for tid in due:
            threading.Thread(target=run_task, args=(tid,), daemon=True).start()
        time.sleep(15)


# ---- 설정 탭: 계정 정보, 스킬, 커넥터, 플러그인 ----
CLAUDE = Path.home() / '.claude'
ACCOUNTS = CONSOLE / 'config' / 'accounts.json'


def _json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def _front(md):
    """SKILL.md 머리말에서 name·description 만 읽는다."""
    out, lines = {}, md.read_text(errors='ignore').splitlines()
    if lines and lines[0].strip() == '---':
        for ln in lines[1:40]:
            if ln.strip() == '---':
                break
            if ':' in ln and not ln.startswith(' '):
                k, v = ln.split(':', 1)
                out[k.strip()] = v.strip().strip('"\'')
    return out


def skills():
    rows = []
    for src, base in (('사용자', CLAUDE / 'skills'), ('이 프로젝트', ROOT / '.claude' / 'skills')):
        for md in sorted(base.glob('*/SKILL.md')):
            f = _front(md)
            rows.append({'name': f.get('name', md.parent.name), 'desc': f.get('description', '')[:200], 'source': src})
    for pid, info in plugin_rows(raw=True):
        for md in sorted(Path(info['path']).glob('skills/*/SKILL.md')):
            f = _front(md)
            rows.append({'name': f"{pid.split('@')[0]}:{f.get('name', md.parent.name)}",
                         'desc': f.get('description', '')[:200], 'source': '플러그인'})
    return rows


def plugin_rows(raw=False):
    inst = _json(CLAUDE / 'plugins' / 'installed_plugins.json', {}).get('plugins', {})
    enabled = _json(CLAUDE / 'settings.json', {}).get('enabledPlugins', {})
    rows = []
    for pid, lst in inst.items():
        info = lst[0] if isinstance(lst, list) and lst else {}
        rows.append((pid, {'path': info.get('installPath', ''), 'version': info.get('version', '')[:16],
                           'enabled': bool(enabled.get(pid, False))}))
    if raw:
        return [r for r in rows if r[1]['enabled']]
    return [{'id': pid, 'name': pid.split('@')[0], 'market': pid.split('@')[-1], **{k: v for k, v in i.items() if k != 'path'}}
            for pid, i in rows]


def connectors():
    rows, needs = [], _json(CLAUDE / 'mcp-needs-auth-cache.json', {})
    for pid, info in plugin_rows(raw=True):
        for name, cfg in _json(Path(info['path']) / '.mcp.json', {}).get('mcpServers', {}).items():
            rows.append({'name': name, 'source': f"플러그인 {pid.split('@')[0]}", 'type': cfg.get('type', 'stdio'),
                         'state': '인증 필요' if any(name in k for k in needs) else '사용 가능'})
    for scope, servers in (('사용자', _json(Path.home() / '.claude.json', {}).get('mcpServers', {})),
                           ('이 프로젝트', _json(ROOT / '.mcp.json', {}).get('mcpServers', {}))):
        for name, cfg in servers.items():
            rows.append({'name': name, 'source': scope, 'type': cfg.get('type', 'stdio'), 'state': '설정됨'})
    for k in needs:
        if not any(k.endswith(':' + r['name']) for r in rows):
            rows.append({'name': k.split(':')[-1], 'source': k.rsplit(':', 1)[0], 'type': 'http', 'state': '인증 필요'})
    return rows


def secret_names():
    try:
        p = subprocess.run(['python3', '-m', 'shared.secret_env', 'names'], cwd=str(ROOT),
                           capture_output=True, text=True, timeout=20)
        return set(p.stdout.split()) if p.returncode == 0 else None
    except Exception:
        return None


def settings_view():
    cfg = _json(ACCOUNTS, {})
    have = secret_names()
    used = sorted(set(__import__('re').findall(r'"([A-Z][A-Z0-9_]{3,})"', json.dumps(cfg))))
    return {'accounts': cfg.get('accounts', {}), 'channel_labels': CH_LABEL,
            'secrets': [{'name': n, 'ok': None if have is None else n in have} for n in used],
            'skills': skills(), 'plugins': plugin_rows(), 'connectors': connectors()}


EDITABLE = ('blog', 'site', 'status', 'note')


def save_accounts(body):
    cfg = _json(ACCOUNTS, {})
    for acc, a in body.get('accounts', {}).items():
        if acc not in cfg['accounts']:
            continue
        tgt = cfg['accounts'][acc]
        if 'email' in a:
            tgt['google']['email'] = str(a['email']).strip()[:120]
        if 'label' in a:
            tgt['label'] = str(a['label']).strip()[:60] or tgt['label']
        for ch, info in a.get('channels', {}).items():
            if ch not in tgt['channels']:
                continue
            for k in EDITABLE:
                if k in info:
                    v = str(info[k]).strip()[:200]
                    if v:
                        tgt['channels'][ch][k] = v
                    else:
                        tgt['channels'][ch].pop(k, None)
    tmp = ACCOUNTS.with_suffix('.tmp')
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(ACCOUNTS)


def toggle_plugin(pid, on):
    path = CLAUDE / 'settings.json'
    cfg = _json(path, None)
    if cfg is None or pid not in _json(CLAUDE / 'plugins' / 'installed_plugins.json', {}).get('plugins', {}):
        raise ValueError('설치되지 않은 플러그인입니다')
    bak = path.with_name('settings.json.ax-backup')
    if not bak.exists():
        bak.write_text(path.read_text())
    cfg.setdefault('enabledPlugins', {})[pid] = bool(on)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)


# ---- 예약 목록: 콘솔 예약 + launchd 자동 작업 ----
import plistlib
AGENTS = Path.home() / 'Library' / 'LaunchAgents'
# launchd 작업 → (계정, 채널, 이름)
LAUNCHD = {
    'ytshorts.weekly': ('dept', 'youtube', '숏츠 주간 발행'), 'ytcareer.weekly': ('dept', 'youtube', '진로 숏츠 발행'),
    'ytshorts.trigger': ('dept', 'youtube', '숏츠 발행 트리거 점검'), 'captionbackfill.daily': ('dept', 'youtube', '자막 보충'),
    'instacards.weekly': ('dept', 'instagram', '카드뉴스 발행'), 'captionautofix.daily': ('dept', 'instagram', '캡션 자동 수정'),
    'captionrecheck.weekly': ('dept', 'instagram', '캡션 재점검'),
    'naverblog.weekly': ('dept', 'naver_blog', '블로그 글 발행'), 'blogcareer.daily': ('dept', 'naver_blog', '진로 시리즈 발행'),
    'naverjobs.weekly': ('dept', 'naver_blog', '채용 소식 발행'), 'naverbuddy.weekly': ('dept', 'naver_blog', '이웃 관리'),
    'tiktok.queue': ('dept', 'tiktok', '틱톡 대기열 발행'), 'xpromo.daily': ('dept', 'x', 'X 홍보글 발행'),
    'disastershorts.weekly': ('dept', 'youtube', '재난 숏츠 발행'), 'disastershorts.crosspost': ('dept', 'instagram', '재난 숏츠 교차 게시'),
    'geoai.daily': ('personal', 'blogger', 'GeoAI 아침 글 발행'), 'geoai.evening': ('personal', 'blogger', 'GeoAI 저녁 글 발행'),
    'tistory': ('personal', 'tistory', '티스토리 발행'),
}


def _next_times(intervals, start, days=8):
    out = []
    if isinstance(intervals, dict):
        intervals = [intervals]
    for d in range(days):
        day = (start + datetime.timedelta(days=d)).date()
        for iv in intervals:
            wd = iv.get('Weekday')
            if wd is not None and (day.isoweekday() % 7) != wd % 7:
                continue
            if 'Day' in iv and day.day != iv['Day']:
                continue
            for h in ([iv['Hour']] if 'Hour' in iv else range(24)):
                t = datetime.datetime.combine(day, datetime.time(h, iv.get('Minute', 0)))
                if t > start:
                    out.append(t)
    return sorted(out)


def schedule_view(days=8):
    start, rows = now(), []
    for t in load():
        if t.get('status') == 'scheduled' and t.get('schedule'):
            a = find_action(t['account'], t['channel'], t['action']) or {}
            rows.append({'at': t['schedule'], 'account': t['account'], 'channel': t['channel'], 'title': t['title'],
                         'what': a.get('label', t['action']), 'repeat': t.get('repeat', ''), 'source': 'console', 'id': t['id']})
    loaded = subprocess.run(['launchctl', 'list'], capture_output=True, text=True).stdout
    for f in sorted(AGENTS.glob('com.smuds.*.plist')):
        key = f.stem.replace('com.smuds.', '')
        if key not in LAUNCHD:
            continue
        acc, ch, name = LAUNCHD[key]
        try:
            pl = plistlib.loads(f.read_bytes())
        except Exception:
            continue
        on = f.stem in loaded
        iv = pl.get('StartCalendarInterval')
        times = _next_times(iv, start, days) if iv else []
        if not times:
            rows.append({'at': '', 'account': acc, 'channel': ch, 'title': name, 'what': '감시형(시각 없음)',
                         'source': 'launchd', 'job': key, 'on': on})
        for t in times:
            rows.append({'at': t.isoformat(timespec='minutes'), 'account': acc, 'channel': ch, 'title': name,
                         'what': Path(pl.get('ProgramArguments', [''])[-1]).name, 'source': 'launchd', 'job': key, 'on': on})
    rows.sort(key=lambda r: r['at'] or '9')
    return {'from': start.isoformat(), 'days': days, 'labels': CH_LABEL, 'rows': rows}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, obj=None, body=None, ctype='application/json; charset=utf-8'):
        data = body if body is not None else json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        n = int(self.headers.get('Content-Length') or 0)
        return json.loads(self.rfile.read(n) or b'{}')

    def same_origin(self):
        # 다른 사이트가 브라우저를 통해 실행 요청을 보내지 못하게 막는다
        o = self.headers.get('Origin')
        return o in (None, f'http://{HOST}:{PORT}', f'http://localhost:{PORT}')

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            return self.send(200, body=(CONSOLE / 'app' / 'index.html').read_bytes(), ctype='text/html; charset=utf-8')
        if self.path.startswith('/fonts/'):
            f = ROOT / 'FONTS' / 'Pretendard-Bold.otf'
            return self.send(200, body=f.read_bytes(), ctype='font/otf')
        if self.path == '/api/meta':
            return self.send(200, meta())
        if self.path == '/api/schedule':
            return self.send(200, schedule_view())
        if self.path == '/api/settings':
            return self.send(200, settings_view())
        if self.path == '/api/tasks':
            return self.send(200, sorted(load(), key=lambda t: (t.get('schedule') or '9', t['created'])))
        if self.path.startswith('/api/log?'):
            rel = self.path.split('=', 1)[1]
            p = (CONSOLE / rel).resolve()
            if RUNS.resolve() not in p.parents or not p.exists():
                return self.send(404, {'error': '기록 없음'})
            return self.send(200, body=p.read_bytes(), ctype='text/plain; charset=utf-8')
        self.send(404, {'error': '없는 주소'})

    def do_POST(self):
        if not self.same_origin():
            return self.send(403, {'error': '허용되지 않은 요청'})
        try:
            b = self.body()
            parts = self.path.strip('/').split('/')
            if parts == ['api', 'settings', 'accounts']:
                save_accounts(b)
                return self.send(200, {'ok': True})
            if parts == ['api', 'settings', 'plugin']:
                toggle_plugin(str(b.get('id', '')), b.get('enabled'))
                return self.send(200, {'ok': True})
            with LOCK:
                tasks = load()
                if parts == ['api', 'tasks']:
                    t = clean(b)
                    t.update(id=uuid.uuid4().hex[:8], created=now().isoformat(), runs=[])
                    tasks.append(t)
                    save(tasks)
                    return self.send(200, t)
                t = next((x for x in tasks if len(parts) > 2 and x['id'] == parts[2]), None)
                if not t:
                    return self.send(404, {'error': '작업을 찾지 못했습니다'})
                if parts[3:] == ['update']:
                    if t['status'] == 'running':
                        raise ValueError('실행 중에는 고칠 수 없습니다')
                    tasks[tasks.index(t)] = t = clean(b, t)
                    save(tasks)
                    return self.send(200, t)
                if parts[3:] == ['delete']:
                    tasks.remove(t)
                    save(tasks)
                    return self.send(200, {'ok': True})
                if parts[3:] == ['run']:
                    t['_was'] = t['status']
                    save(tasks)
            if parts[3:] == ['run']:
                threading.Thread(target=run_task, args=(t['id'], True), daemon=True).start()
                return self.send(200, {'ok': True})
            self.send(404, {'error': '없는 주소'})
        except (ValueError, KeyError) as e:
            self.send(400, {'error': str(e)})


if __name__ == '__main__':
    with LOCK:  # 서버가 꺼진 사이 '실행 중'으로 남은 작업은 실패로 돌린다
        ts = load()
        for t in ts:
            if t.get('status') == 'running':
                t['status'] = 'failed'
        save(ts)
    threading.Thread(target=scheduler, daemon=True).start()
    print(f'AX 발행 콘솔: http://{HOST}:{PORT}')
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()
