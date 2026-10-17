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
        'threads': [], 'blogger': [],
    },
    'personal': {
        'blogger': [('geoai_morning', 'GeoAI 아침 글 발행', 'naver-blog-auto/run_geoai.sh'),
                    ('geoai_evening', 'GeoAI 저녁 글 발행', 'naver-blog-auto/run_geoai_evening.sh')],
        'tistory': [('tistory', '티스토리 발행', 'naver-blog-auto/run_tistory.sh')],
        'homepage': [], 'naver_blog': [], 'tiktok': [], 'youtube': [], 'instagram': [], 'kakao': [],
    },
}
CH_LABEL = {'analytics': '성과·색인', 'maintenance': '유지보수', 'youtube': '유튜브', 'instagram': '인스타그램', 'naver_blog': '네이버 블로그', 'tiktok': '틱톡',
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
        accs.append({'id': acc, 'label': a['label'], 'email': a['google']['email'], 'channels': chans,
                     'naver': a.get('naver'), 'kakao': a.get('kakao')})
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
AUTOMATIONS = CONSOLE / 'config' / 'automations.json'
WD_KO = '일월화수목금토'


def catalog():
    return {j['job']: j for j in _json(AUTOMATIONS, {}).get('jobs', [])}


def _when_text(pl):
    if pl.get('StartInterval'):
        return f"{pl['StartInterval'] // 60}분마다"
    iv = pl.get('StartCalendarInterval')
    if not iv:
        return '로그인할 때 켜짐' if pl.get('RunAtLoad') else '시각 없음'
    ivs = iv if isinstance(iv, list) else [iv]
    groups = {}
    for i in ivs:
        t = f"{i.get('Hour', 0):02d}:{i.get('Minute', 0):02d}" if 'Hour' in i else f"매시 {i.get('Minute', 0):02d}분"
        d = f"매월 {i['Day']}일" if 'Day' in i else WD_KO[i['Weekday'] % 7] if 'Weekday' in i else '매일'
        groups.setdefault(d, []).append(t)
    bytimes = {}
    for d, ts in groups.items():
        bytimes.setdefault(', '.join(sorted(ts)), []).append(d)
    order = '매일' + WD_KO
    return ' / '.join(f"{'·'.join(sorted(ds, key=lambda x: order.find(x[0]) if x[0] in order else 99))} {ts}"
                      for ts, ds in bytimes.items())


def _last_run(pl):
    """plist 로그와 실행 스크립트가 쓰는 logs/*.log 중 가장 최근에 바뀐 시각."""
    files = [pl.get('StandardOutPath'), pl.get('StandardErrorPath')]
    script = Path(pl.get('ProgramArguments', [''])[-1])
    try:
        if script.suffix == '.sh':
            for m in __import__('re').findall(r'((?:\.\./)?logs/[\w.\-]+\.log)', script.read_text(errors='ignore')):
                files.append(str((script.resolve().parent / m).resolve()))
    except OSError:
        pass
    times = [os.path.getmtime(f) for f in files if f and os.path.exists(f)]
    return datetime.datetime.fromtimestamp(max(times)).isoformat(timespec='minutes') if times else ''


def automations():
    cat, loaded = catalog(), subprocess.run(['launchctl', 'list'], capture_output=True, text=True).stdout
    out, start = [], now()
    for f in sorted(AGENTS.glob('com.smuds.*.plist')):
        key = f.stem.replace('com.smuds.', '')
        try:
            pl = plistlib.loads(f.read_bytes())
        except Exception:
            continue
        info = cat.get(key, {'job': key, 'account': 'common', 'name': key, 'what': '분석 전 작업',
                             'channels': [['common', 'maintenance']]})
        iv = pl.get('StartCalendarInterval')
        nxt = _next_times(iv, start, 40) if iv else []
        if pl.get('StartInterval'):
            nxt = [start + datetime.timedelta(seconds=pl['StartInterval'])]
        out.append({**info, 'on': f.stem in loaded, 'when': _when_text(pl), 'last': _last_run(pl),
                    'next': [t.isoformat(timespec='minutes') for t in nxt[:3]],
                    'script': pl.get('ProgramArguments', [''])[-1].replace(str(ROOT) + '/', '')})
    return out


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
    for j in automations():
        if j['account'] == 'common' and not j['next']:
            continue
        base = {'account': j['account'], 'channel': j['channels'][0][1], 'channels': j['channels'], 'title': j['name'],
                'what': j['when'], 'source': 'launchd', 'job': j['job'], 'on': j['on']}
        times = []
        if j['next'] and '분마다' not in j['when']:
            iv = plistlib.loads((AGENTS / f"com.smuds.{j['job']}.plist").read_bytes()).get('StartCalendarInterval')
            times = [t.isoformat(timespec='minutes') for t in _next_times(iv, start, days)]
        if not times:
            rows.append({**base, 'at': ''})
        for t in times:
            rows.append({**base, 'at': t})
    rows.sort(key=lambda r: r['at'] or '9')
    return {'from': start.isoformat(), 'days': days, 'labels': CH_LABEL, 'rows': rows}


# ---- 구글 계정 연결: 토큰 상태 확인과 로그인 ----
GPY = str(ROOT / 'youtube-shorts-auto' / '.venv' / 'bin' / 'python')
SERVICE_LABEL = {'youtube': '유튜브', 'blogger': '블로거', 'searchconsole': '서치콘솔'}
# (계정, 서비스) → 기존 인증 스크립트. 이미 토큰이 있으면 묻는 스크립트에는 'y' 를 넣는다.
LOGIN = {
    ('dept', 'youtube'): ('youtube-shorts-auto', ['youtube_login_setup.py']),
    ('personal', 'youtube'): ('youtube-shorts-auto', ['geoai_youtube_auth.py']),
    ('dept', 'blogger'): ('naver-blog-auto', ['blogger_auth_setup.py']),
    ('personal', 'blogger'): ('naver-blog-auto', ['geoai_auth_setup.py']),
    ('dept', 'searchconsole'): ('analytics', ['searchconsole_auth_setup.py', 'dept']),
    ('personal', 'searchconsole'): ('analytics', ['searchconsole_auth_setup.py']),
}
GSTATE = {'checked': None, 'result': {}, 'login': {}}


def google_pairs():
    cfg = _json(ACCOUNTS, {})
    return [[acc, svc, name] for acc, a in cfg.get('accounts', {}).items()
            for svc, name in a.get('google', {}).get('tokens', {}).items()]


def google_check():
    p = subprocess.run([GPY, str(CONSOLE / 'app' / 'google_check.py'), json.dumps(google_pairs())],
                       cwd=str(ROOT), capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise ValueError('토큰 확인 실패: ' + (p.stderr.strip().splitlines() or ['알 수 없는 오류'])[-1][:200])
    GSTATE['result'] = json.loads(p.stdout.strip().splitlines()[-1])
    GSTATE['checked'] = now().isoformat()


def _safe(fn):
    try:
        fn()
    except Exception:
        pass


def google_view():
    cfg = _json(ACCOUNTS, {})
    have = secret_names()
    accs = []
    for acc, a in cfg.get('accounts', {}).items():
        svcs = []
        for svc, name in a.get('google', {}).get('tokens', {}).items():
            r = GSTATE['result'].get(f'{acc}/{svc}', {})
            svcs.append({'id': svc, 'label': SERVICE_LABEL.get(svc, svc), 'secret': name, **r,
                         'login': GSTATE['login'].get(f'{acc}/{svc}')})
        others = []
        for kind, label in (('naver', '네이버'), ('kakao', '카카오')):
            o = a.get(kind)
            if not o:
                continue
            sec = o.get('secrets', [])
            ok = bool(sec) and have is not None and all(n in have for n in sec)
            others.append({'label': label, 'id': o.get('id', ''), 'login': o.get('login', ''), 'note': o.get('note', ''),
                           'secrets': sec, 'ok': ok, 'state': '로그인 정보 저장됨' if ok else '연결 전' if not sec else '비밀값 없음'})
        accs.append({'id': acc, 'label': a['label'], 'email': a['google']['email'], 'services': svcs, 'others': others})
    return {'checked': GSTATE['checked'], 'accounts': accs}


def google_login(acc, svc):
    key = f'{acc}/{svc}'
    if (acc, svc) not in LOGIN:
        raise ValueError('로그인할 수 없는 항목입니다')
    if (GSTATE['login'].get(key) or {}).get('state') == '진행 중':
        raise ValueError('이미 로그인 창이 열려 있습니다')
    folder, args = LOGIN[(acc, svc)]
    GSTATE['login'][key] = {'state': '진행 중', 'at': now().isoformat(),
                            'msg': '브라우저에 구글 로그인 창이 열립니다. 계정을 고르고 허용하세요.'}

    def work():
        py = ROOT / folder / '.venv' / 'bin' / 'python'
        try:
            p = subprocess.run([str(py), *args], cwd=str(ROOT / folder), input='y\n',
                               capture_output=True, text=True, timeout=300)
            ok = p.returncode == 0
            msg = ((p.stdout or '') + (p.stderr or '')).strip().splitlines()
            GSTATE['login'][key] = {'state': '완료' if ok else '실패', 'at': now().isoformat(),
                                    'msg': (msg[-1] if msg else '')[:200]}
            if ok:
                google_check()
        except subprocess.TimeoutExpired:
            GSTATE['login'][key] = {'state': '실패', 'at': now().isoformat(), 'msg': '5분 안에 로그인을 마치지 않아 닫았습니다.'}
        except Exception as e:
            GSTATE['login'][key] = {'state': '실패', 'at': now().isoformat(), 'msg': str(e)[:200]}

    threading.Thread(target=work, daemon=True).start()


# ---- 세명대 AI 게이트웨이 ----
GW_MODULES = ['youtube-shorts-auto', 'naver-blog-auto', 'insta-cardnews', 'insta-manual']
GW_STATE = {'checked': None, 'result': None}


def gateway_view():
    have = secret_names() or set()
    mods = []
    for m in GW_MODULES:
        g = _json(ROOT / m / 'config.json', {}).get('llm_gateway') or {}
        extra = g.get('extra_keys') or []
        mods.append({'module': m, 'enabled': bool(g.get('enabled')), 'base_url': g.get('base_url', ''),
                     'model_map': g.get('model_map', {}), 'main_key': '암호화 저장소' if 'LLM_GATEWAY_API_KEY' in have
                     else ('config.json 평문' if g.get('api_key') else '없음'), 'extra_plain': len(extra),
                     'extra_store': int(g.get('extra_key_count', 0)) if 'LLM_GATEWAY_EXTRA_KEYS' in have else 0})
    since = (now() - datetime.timedelta(days=7)).strftime('%Y-%m-%d')
    use = {'gateway': 0, 'fallback': 0}
    for m in GW_MODULES + ['analytics']:
        for f in (ROOT / m / 'logs').glob('*.log'):
            try:
                if datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d') < since:
                    continue
                for ln in f.read_text(errors='ignore').splitlines():
                    if 'LLM: ' not in ln or ln[1:11] < since:
                        continue
                    use['fallback' if '전환' in ln or 'Anthropic' in ln else 'gateway'] += 1
            except OSError:
                pass
    return {'modules': mods, 'usage7d': use, 'checked': GW_STATE['checked'], 'result': GW_STATE['result']}


def gateway_check():
    p = subprocess.run([GPY, str(CONSOLE / 'app' / 'gateway_check.py')], cwd=str(ROOT / 'youtube-shorts-auto'),
                       capture_output=True, text=True, timeout=300)
    if p.returncode != 0:
        raise ValueError('게이트웨이 확인 실패: ' + (p.stderr.strip().splitlines() or ['알 수 없는 오류'])[-1][:200])
    GW_STATE['result'] = json.loads(p.stdout.strip().splitlines()[-1])
    GW_STATE['checked'] = now().isoformat()


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
        if self.path == '/api/gateway':
            return self.send(200, gateway_view())
        if self.path == '/api/automations':
            return self.send(200, automations())
        if self.path == '/api/google':
            return self.send(200, google_view())
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
            if parts == ['api', 'gateway', 'check']:
                gateway_check()
                return self.send(200, gateway_view())
            if parts == ['api', 'google', 'check']:
                google_check()
                return self.send(200, google_view())
            if parts == ['api', 'google', 'login']:
                google_login(str(b.get('account')), str(b.get('service')))
                return self.send(200, google_view())
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
    threading.Thread(target=lambda: _safe(google_check), daemon=True).start()
    print(f'AX 발행 콘솔: http://{HOST}:{PORT}')
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()
