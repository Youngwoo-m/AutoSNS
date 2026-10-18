"""AX 발행 콘솔 서버 (표준 라이브러리만 사용).

실행: python3 ax-console/app/server.py  → http://127.0.0.1:8700
- 계정(학과/개인) → 채널별로 작업을 만들고 고치고 예약한다.
- 예약 시각이 되면 채널에 등록된 실행 작업(기존 run_*.sh)을 돌리고 기록을 남긴다.
- 실행할 수 있는 명령은 아래 ACTIONS 목록뿐이다. 화면에서 임의 명령은 받지 않는다.
"""
import datetime, json, os, subprocess, threading, time, urllib.parse, uuid
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
    if t.get('action') == 'publish':
        return run_publish(t, manual)
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
            # 콘텐츠 예약(메모)은 실제 발행 연결이 없으므로 '발행할 차례'로만 바꾼다
            ts = load()
            for t in ts:
                if t['id'] in due and t.get('content') and t.get('action') == 'memo':
                    t['status'] = 'due'
                    due.remove(t['id'])
            save(ts)
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


def _log_files(pl):
    """plist 로그와 실행 스크립트가 쓰는 logs/*.log 경로."""
    files = [pl.get('StandardOutPath'), pl.get('StandardErrorPath')]
    script = Path(pl.get('ProgramArguments', [''])[-1])
    try:
        if script.suffix == '.sh':
            for m in __import__('re').findall(r'((?:\.\./)?logs/[\w.\-]+\.log)', script.read_text(errors='ignore')):
                files.append(str((script.resolve().parent / m).resolve()))
    except OSError:
        pass
    return list(dict.fromkeys(f for f in files if f and os.path.exists(f)))


def _last_run(pl):
    """plist 로그와 실행 스크립트가 쓰는 logs/*.log 중 가장 최근에 바뀐 시각."""
    times = [os.path.getmtime(f) for f in _log_files(pl)]
    return datetime.datetime.fromtimestamp(max(times)).isoformat(timespec='minutes') if times else ''


def _launchd():
    """불러온 작업 {레이블: (pid, 마지막 종료 코드)} 와 disable 된 레이블 집합."""
    loaded = {}
    for line in subprocess.run(['launchctl', 'list'], capture_output=True, text=True).stdout.splitlines()[1:]:
        f = line.split('\t')
        if len(f) == 3:
            loaded[f[2]] = (f[0], f[1])
    pd = subprocess.run(['launchctl', 'print-disabled', f'gui/{os.getuid()}'], capture_output=True, text=True).stdout
    disabled = set(__import__('re').findall(r'"([^"]+)" => (?:disabled|true)', pd))
    return loaded, disabled


def automations():
    cat, (loaded, disabled) = catalog(), _launchd()
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
        pid, code = loaded.get(f.stem, ('-', ''))
        out.append({**info, 'on': f.stem in loaded, 'disabled': f.stem in disabled, 'running': pid != '-',
                    'exit': code, 'controllable': key in cat and key not in SELF_JOBS,
                    'live': any(c[0] != 'common' for c in info['channels']), 'when': _when_text(pl), 'last': _last_run(pl),
                    'next': [t.isoformat(timespec='minutes') for t in nxt[:3]],
                    'script': pl.get('ProgramArguments', [''])[-1].replace(str(ROOT) + '/', '')})
    return out


# ---- launchd 작업 제어: automations.json 에 등록된 작업만, 콘솔 자신은 제외 ----
SELF_JOBS = {'axconsole'}


def _job_plist(job):
    if job not in catalog() or job in SELF_JOBS:
        raise ValueError('제어할 수 없는 작업입니다')
    f = AGENTS / f'com.smuds.{job}.plist'
    if not f.exists():
        raise ValueError(f'{f.name} 가 없습니다')
    return f


def _lc(*args, ok=()):
    p = subprocess.run(['launchctl', *args], capture_output=True, text=True, timeout=30)
    if p.returncode and p.returncode not in ok:
        raise ValueError(f"launchctl {args[0]} 실패({p.returncode}): {(p.stderr or p.stdout).strip()[:200]}")
    return p


def job_control(job, op):
    f = _job_plist(job)
    dom, label = f'gui/{os.getuid()}', f'com.smuds.{job}'
    loaded = label in _launchd()[0]
    if op == 'off':
        if loaded:
            _lc('bootout', f'{dom}/{label}')
        _lc('disable', f'{dom}/{label}')
    elif op == 'on':
        _lc('enable', f'{dom}/{label}')
        if not loaded:
            _lc('bootstrap', dom, str(f))
    elif op == 'run':
        if not loaded:
            raise ValueError('꺼진 작업입니다. 먼저 켜세요')
        _lc('kickstart', f'{dom}/{label}')
    else:
        raise ValueError('없는 동작입니다')
    with open(DATA / 'logs' / 'launchd_control.log', 'a') as lf:
        lf.write(f'{now().isoformat()} {op} {label}\n')
    return next(j for j in automations() if j['job'] == job)


def job_logs(job, lines=60):
    """작업 로그 파일마다 끝부분을 돌려준다(최근에 바뀐 파일 먼저)."""
    if job not in catalog():
        raise ValueError('없는 작업입니다')
    f = AGENTS / f'com.smuds.{job}.plist'
    pl = plistlib.loads(f.read_bytes()) if f.exists() else {}
    out = []
    for path in sorted(_log_files(pl), key=os.path.getmtime, reverse=True)[:4]:
        with open(path, 'rb') as fh:
            fh.seek(max(0, os.path.getsize(path) - 32768))
            tail = fh.read().decode('utf-8', 'replace').splitlines()[-lines:]
        out.append({'path': path.replace(str(ROOT) + '/', ''), 'size': os.path.getsize(path),
                    'mtime': datetime.datetime.fromtimestamp(os.path.getmtime(path)).isoformat(timespec='minutes'),
                    'tail': '\n'.join(tail)})
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


CLI_LOGINS = {}


def cli_logins():
    """gh·netlify CLI 에 로그인된 계정 이름(토큰은 읽지 않는다)."""
    gh = set()
    for exe in ('/opt/homebrew/bin/gh', '/usr/local/bin/gh'):
        if os.path.exists(exe):
            out = subprocess.run([exe, 'auth', 'status'], capture_output=True, text=True).stdout
            out += subprocess.run([exe, 'auth', 'status'], capture_output=True, text=True).stderr
            gh = set(__import__('re').findall(r'account (\S+)', out))
            act = __import__('re').search(r'account (\S+)[^\n]*\n\s*- Active account: true', out)
            CLI_LOGINS['github_active'] = act.group(1) if act else None
            CLI_LOGINS['gh_bin'] = exe
            break
    nl = {u.get('email') for u in _json(Path.home() / 'Library' / 'Preferences' / 'netlify' / 'config.json', {})
          .get('users', {}).values()}
    CLI_LOGINS.update(github=gh, netlify=nl)


def github_switch(user):
    cli_logins()
    known = {x['id'] for a in _json(ACCOUNTS, {}).get('accounts', {}).values() for x in (a.get('github') or {}).get('accounts', [])}
    if user not in known:
        raise ValueError('설정에 없는 GitHub 계정입니다')
    if user not in CLI_LOGINS.get('github', set()):
        raise ValueError(f'{user} 는 아직 gh 에 로그인돼 있지 않습니다. 터미널에서 gh auth login 으로 먼저 추가하세요')
    p = subprocess.run([CLI_LOGINS['gh_bin'], 'auth', 'switch', '--hostname', 'github.com', '--user', user],
                       capture_output=True, text=True, timeout=30)
    if p.returncode != 0:
        raise ValueError((p.stderr or p.stdout).strip()[:200])


TISTORY_DIR = ROOT / 'GeoAI_NA' / 'naver-blog-auto'


def tistory_status():
    """티스토리 교차 게시의 최근 결과와 카카오 장기 로그인 쿠키 만료일(값은 읽지 않는다)."""
    out = {'last_ok': '', 'last_fail': '', 'fail_reason': '', 'kakao_until': '', 'profile_busy': False}
    try:
        for ln in (TISTORY_DIR / 'tistory-logs' / 'tistory.log').read_text(errors='ignore').splitlines()[-400:]:
            if '발행 완료' in ln:
                out['last_ok'] = ln[1:20]
            elif '실패' in ln or '비밀번호를 묻' in ln or '건너뜀' in ln:
                out['last_fail'], out['fail_reason'] = ln[1:20], ln[22:].split('http')[0].strip(' :')[:120]
    except OSError:
        pass
    import shutil, sqlite3, tempfile
    db = TISTORY_DIR / 'chrome-profile-tistory' / 'Default' / 'Cookies'
    if db.exists():
        with tempfile.TemporaryDirectory() as td:
            cp = Path(td) / 'c.db'
            shutil.copy(db, cp)
            try:
                row = sqlite3.connect(cp).execute(
                    "select max(expires_utc) from cookies where host_key like '%kakao.com' and name='_kawlt'").fetchone()
                if row and row[0]:
                    out['kakao_until'] = datetime.datetime.fromtimestamp(row[0] / 1e6 - 11644473600).isoformat(timespec='minutes')
            except sqlite3.Error:
                pass
    out['profile_busy'] = subprocess.run(['pgrep', '-f', 'chrome-profile-tistory'], capture_output=True).returncode == 0
    return out


def _safe(fn):
    try:
        fn()
    except Exception:
        pass


def google_view():
    cfg = _json(ACCOUNTS, {})
    have = secret_names()
    cli_logins()
    accs = []
    for acc, a in cfg.get('accounts', {}).items():
        svcs = []
        for svc, name in a.get('google', {}).get('tokens', {}).items():
            r = GSTATE['result'].get(f'{acc}/{svc}', {})
            svcs.append({'id': svc, 'label': SERVICE_LABEL.get(svc, svc), 'secret': name, **r,
                         'login': GSTATE['login'].get(f'{acc}/{svc}')})
        others = []
        for kind, label in (('naver', '네이버'), ('kakao', '카카오'), ('tistory', '티스토리'), ('netlify', 'Netlify')):
            o = a.get(kind)
            if not o:
                continue
            sec = o.get('secrets', [])
            ok = bool(sec) and have is not None and all(n in have for n in sec)
            if kind == 'tistory':
                ts = tistory_status()
                fail_newer = ts['last_fail'] > ts['last_ok']
                ok = bool(ts['last_ok']) and not fail_newer
                sec = ['TISTORY']
                o = {**o, 'note': (f"최근 성공 {ts['last_ok'][5:16]}" if ts['last_ok'] else '성공 기록 없음')
                     + (f" · 최근 실패 {ts['last_fail'][5:16]}: {ts['fail_reason']}" if fail_newer else '')
                     + (f" · 카카오 로그인 유지 {ts['kakao_until'][:10]}까지" if ts['kakao_until'] else ' · 카카오 로그인 쿠키 없음')
                     + (' · 지금 다른 작업이 티스토리 크롬 사용 중' if ts['profile_busy'] else '')}
            if kind in ('github', 'netlify'):
                ok = o.get('id', '') in CLI_LOGINS.get(kind, set())
                sec = ['CLI']
            state = ('정상' if ok else '로그인 확인 필요') if sec == ['TISTORY'] else \
                ('CLI 로그인됨' if ok else 'CLI 로그인 안 됨') if sec == ['CLI'] else \
                ('로그인 정보 저장됨' if ok else '연결 전' if not sec else '비밀값 없음')
            others.append({'label': label, 'id': o.get('id', ''), 'login': o.get('login', ''), 'note': o.get('note', ''),
                           'secrets': sec, 'ok': ok, 'state': state})
        gh = None
        if a.get('github'):
            gh = {'note': a['github'].get('note', ''), 'accounts': [
                {**x, 'logged_in': x['id'] in CLI_LOGINS.get('github', set()), 'active': x['id'] == CLI_LOGINS.get('github_active')}
                for x in a['github'].get('accounts', [])]}
        accs.append({'id': acc, 'label': a['label'], 'email': a['google']['email'], 'services': svcs, 'others': others,
                     'github': gh})
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


# ---- 콘텐츠 파이프라인: ① 기획 → ② 초안 → ③ 검토 → ④ 제작 → ⑤ 예약 → ⑥ 발행 → ⑦ 성과 ----
CONTENT = DATA / 'content'
STAGES = ['idea', 'drafting', 'review', 'scheduled', 'published', 'failed']  # 예약 안의 'due' 는 작업 단위
CHECKS = {'sources': '출처를 확인했다', 'facts': '수치·날짜·기관명을 확인했다',
          'tone': '자극적인 표현이 없다', 'ai_notice': 'AI 도움을 받은 글임을 밝혔거나 밝힐 필요가 없다'}
CLOCK = threading.Lock()


def _cdir(cid):
    hits = list(CONTENT.glob(f'*/*/{cid}'))
    if not hits:
        raise ValueError('콘텐츠를 찾지 못했습니다')
    return hits[0]


def cload(cid):
    return _sync_status(json.loads((_cdir(cid) / 'meta.json').read_text()))


def csave(c):
    d = CONTENT / c['created'][:4] / c['created'][5:7] / c['id']
    d.mkdir(parents=True, exist_ok=True)
    c['updated'] = now().isoformat()
    tmp = d / 'meta.tmp'
    tmp.write_text(json.dumps(c, ensure_ascii=False, indent=2))
    tmp.replace(d / 'meta.json')
    # 사람이 읽기 쉬운 사본(원문·변환본)도 남긴다
    (d / '원문.md').write_text(f"# {c.get('title') or c['topic']}\n\n{c.get('original', '')}\n")
    for ch, txt in (c.get('variants') or {}).items():
        (d / f'변환본_{ch}.md').write_text(txt + '\n')


def _sync_status(c):
    """⑥ 발행: 연결된 예약 작업의 결과로 콘텐츠 상태를 맞춘다."""
    if c['status'] != 'scheduled' or not c.get('tasks'):
        return c
    ts = {t['id']: t for t in load()}
    st = [ts.get(tid, {}).get('status') for tid in c['tasks'].values()]
    new = 'published' if st and all(x == 'done' for x in st) else 'failed' if any(x == 'failed' for x in st) else None
    if new:  # 바뀐 상태는 파일에도 남긴다(지우기·목록이 같은 상태를 보게)
        c['status'] = new
        c.setdefault('history', []).append({'at': now().isoformat(), 'what': '모든 채널 발행 완료' if new == 'published' else '발행 실패 채널 있음'})
        csave(c)
    return c


def contents():
    out = []
    for f in sorted(CONTENT.glob('*/*/*/meta.json')):
        try:
            c = _sync_status(json.loads(f.read_text()))
        except ValueError:
            continue
        out.append(c)
    return sorted(out, key=lambda c: c.get('updated', ''), reverse=True)


def content_create(b):
    acc = b.get('account')
    chans = [c for c in b.get('channels', []) if any(ch['id'] == c for a in meta()['accounts'] if a['id'] == acc
                                                    for ch in a['channels'])]
    topic = str(b.get('topic', '')).strip()[:200]
    if acc not in ('dept', 'personal') or not topic or not chans:
        raise ValueError('계정·주제·채널을 고르세요')
    c = {'id': uuid.uuid4().hex[:8], 'created': now().isoformat(), 'account': acc, 'topic': topic,
         'notes': str(b.get('notes', ''))[:5000], 'channels': chans, 'status': 'idea', 'variants': {},
         'checks': {}, 'history': [{'at': now().isoformat(), 'what': '기획 등록'}]}
    csave(c)
    return c


def content_draft(cid):
    with CLOCK:
        c = cload(cid)
        if c['status'] not in ('idea', 'review'):
            raise ValueError('기획·검토 단계에서만 초안을 만들 수 있습니다')
        c['status'] = 'drafting'
        csave(c)

    def work():
        try:
            req = json.dumps({k: c[k] for k in ('account', 'topic', 'notes', 'channels')}, ensure_ascii=False)
            # ② 초안 에이전트(조사 → 원문 → 자체 검토). 실패하면 한 번 호출 방식(draft_ai)으로 대신한다
            p = subprocess.run([GPY, str(CONSOLE / 'app' / 'agents' / 'drafter.py')], cwd=str(ROOT / 'youtube-shorts-auto'),
                               input=req, capture_output=True, text=True, timeout=1500)
            try:
                d = json.loads(p.stdout.strip().splitlines()[-1])
            except (IndexError, ValueError):
                d = {'error': '초안 에이전트 출력 없음: ' + ((p.stderr or '').strip().splitlines() or [''])[-1][:200]}
            fallback = ''
            if d.get('error'):
                fallback = d['error']
                p = subprocess.run([GPY, str(CONSOLE / 'app' / 'draft_ai.py')], cwd=str(ROOT / 'youtube-shorts-auto'),
                                   input=req, capture_output=True, text=True, timeout=600)
                d = json.loads(p.stdout.strip().splitlines()[-1])
            with CLOCK:
                x = cload(cid)
                x.update(title=d.get('title', ''), summary=d.get('summary', ''), original=d.get('original', ''),
                         sources=d.get('sources', []), variants=d.get('variants', {}), status='review', checks={},
                         model=d.get('model', ''), error='', outline=d.get('outline', ''),
                         research=d.get('research', {}), review=d.get('review', {}),
                         agent_logs=[v for v in (d.get('agent_log'), d.get('review_log')) if v], usage=d.get('usage', {}))
                x['history'].append({'at': now().isoformat(), 'what': f"AI 초안 ({d.get('model', '')})"
                                     + (f" — 에이전트 실패로 한 번 호출 방식 사용: {fallback[:120]}" if fallback else '')})
                csave(x)
        except Exception as e:
            with CLOCK:
                x = cload(cid)
                x.update(status='idea', error=f'초안 실패: {str(e)[:200]}')
                csave(x)

    threading.Thread(target=work, daemon=True).start()


def content_update(cid, b):
    with CLOCK:
        c = cload(cid)
        if c['status'] not in ('idea', 'review'):
            raise ValueError('예약된 뒤에는 고칠 수 없습니다. 예약을 취소하세요')
        for k in ('title', 'original', 'topic', 'notes'):
            if k in b:
                c[k] = str(b[k])[:20000]
        if 'variants' in b:
            c['variants'] = {ch: str(b['variants'].get(ch, ''))[:20000] for ch in c['channels']}
        if 'checks' in b:
            c['checks'] = {k: bool(b['checks'].get(k)) for k in CHECKS}
        csave(c)
        return c


def content_approve(cid, b):
    """③ 검토 통과 → ⑤ 예약: 채널마다 예약 작업을 만든다."""
    with CLOCK:
        c = cload(cid)
        if c['status'] != 'review':
            raise ValueError('검토 대기 상태에서만 승인할 수 있습니다')
        if not all(c.get('checks', {}).get(k) for k in CHECKS):
            raise ValueError('점검표를 모두 확인해야 승인할 수 있습니다')
        texts = [c.get('original', '')] + list(c.get('variants', {}).values())
        if any('[확인 필요]' in t for t in texts):
            raise ValueError('[확인 필요] 표시가 남아 있습니다. 확인해 고친 뒤 승인하세요')
        when = b.get('schedule') or {}
        for ch in c['channels']:
            try:
                datetime.datetime.fromisoformat(when.get(ch) or '')
            except ValueError:
                raise ValueError(f"{CH_LABEL.get(ch, ch)} 발행 시각을 정하세요")
        tids = {}
        with LOCK:
            tasks = load()
            for ch in c['channels']:
                auto = (b.get('modes') or {}).get(ch) == 'auto' and (c['account'], ch) in AUTO_PUBLISH
                t = {'id': uuid.uuid4().hex[:8], 'created': now().isoformat(), 'runs': [], 'account': c['account'],
                     'channel': ch, 'title': f"[콘텐츠] {c.get('title') or c['topic']}", 'action': 'publish' if auto else 'memo',
                     'body': c['variants'].get(ch, ''), 'schedule': when[ch], 'repeat': '', 'status': 'scheduled',
                     'content': cid}
                tasks.append(t)
                tids[ch] = t['id']
            save(tasks)
        c.update(status='scheduled', tasks=tids, approved=now().isoformat())
        c['history'].append({'at': now().isoformat(), 'what': '승인·예약 (' + ', '.join(f'{k} {v[5:16]}' for k, v in when.items() if k in tids) + ')'})
        csave(c)
        return c


# ---- ⑥ 자동 발행: 승인된 콘텐츠를 채널별 기존 발행 코드로 ----
AUTO_PUBLISH = {  # (계정, 채널) → 실행할 모듈 폴더
    ('dept', 'blogger'): 'naver-blog-auto', ('personal', 'blogger'): 'naver-blog-auto',
    ('dept', 'naver_blog'): 'naver-blog-auto', ('dept', 'x'): 'youtube-shorts-auto',
}


def publish_call(cid, account, channel, dry):
    folder = AUTO_PUBLISH[(account, channel)]
    args = [str(ROOT / folder / '.venv' / 'bin' / 'python'), str(CONSOLE / 'app' / 'publishers.py'),
            str(_cdir(cid)), account, channel] + (['--dry'] if dry else [])
    p = subprocess.run(args, cwd=str(ROOT / folder), capture_output=True, text=True, timeout=1800)
    lines = (p.stdout or '').strip().splitlines()
    try:
        return json.loads(lines[-1]), (p.stdout or '') + (p.stderr or '')
    except (IndexError, ValueError):
        return {'status': 'error', 'detail': ((p.stderr or '').strip().splitlines() or ['출력 없음'])[-1][:300]}, \
            (p.stdout or '') + (p.stderr or '')


def run_publish(t, manual):
    start = now()
    day = RUNS / start.strftime('%Y-%m-%d')
    day.mkdir(parents=True, exist_ok=True)
    log = day / f"{start.strftime('%H%M%S')}_{t['id']}.log"
    try:
        r, out = publish_call(t['content'], t['account'], t['channel'], dry=False)
    except Exception as e:
        r, out = {'status': 'error', 'detail': str(e)[:300]}, ''
    log.write_text(f"자동 발행: {t['title']} → {t['account']}/{t['channel']}\n시작: {start}\n결과: {json.dumps(r, ensure_ascii=False)}\n\n{out}")
    ok = r.get('status') == 'published'
    with LOCK:
        tasks = load()
        x = next((y for y in tasks if y['id'] == t['id']), None)
        if x:
            x['status'] = 'done' if ok else 'failed'
            x['url'] = r.get('url', '')
            x['result'] = r
            x.setdefault('runs', []).insert(0, {'at': start.isoformat(), 'end': now().isoformat(),
                                                'code': 0 if ok else 1, 'manual': manual,
                                                'log': str(log.relative_to(CONSOLE)),
                                                'tail': r.get('url') or r.get('detail', '')})
            save(tasks)


def content_check(cid):
    """승인 전 점검: 자동 발행할 채널을 '게시 직전'까지만 돌려 본다."""
    c = cload(cid)
    out = {}
    for ch in c['channels']:
        if (c['account'], ch) not in AUTO_PUBLISH:
            out[ch] = {'status': 'manual', 'detail': '자동 발행 연결 없음 — 직접 올린 뒤 완료 표시'}
        elif ch == 'naver_blog':
            out[ch] = {'status': 'not_checked', 'detail': '네이버 점검은 크롬 창을 열어 글을 입력하므로 버튼으로 따로 실행합니다'}
        else:
            out[ch] = publish_call(cid, c['account'], ch, dry=True)[0]
    return out


def content_cancel(cid):
    with CLOCK:
        c = cload(cid)
        if c['status'] != 'scheduled':
            raise ValueError('예약된 콘텐츠만 취소할 수 있습니다')
        with LOCK:
            tasks = [t for t in load() if t['id'] not in (c.get('tasks') or {}).values() or t['status'] != 'scheduled']
            save(tasks)
        c.update(status='review', tasks={})
        c['history'].append({'at': now().isoformat(), 'what': '예약 취소 → 검토로'})
        csave(c)
        return c


def task_done(tid, url):
    """사람이 직접 올린 콘텐츠 작업을 완료로 표시(결과 주소를 남긴다)."""
    with LOCK:
        tasks = load()
        t = next((x for x in tasks if x['id'] == tid), None)
        if not t:
            raise ValueError('작업을 찾지 못했습니다')
        url = str(url or '').strip()[:500]
        if url and not url.startswith(('http://', 'https://')):
            raise ValueError('주소는 http 로 시작해야 합니다')
        t['status'] = 'done'
        t['url'] = url
        t.setdefault('runs', []).insert(0, {'at': now().isoformat(), 'end': now().isoformat(), 'code': 0,
                                            'manual': True, 'log': '', 'tail': '직접 발행 완료 ' + url})
        save(tasks)


def content_delete(cid):
    with CLOCK:
        c = cload(cid)
        if c['status'] in ('scheduled', 'drafting'):
            raise ValueError('예약·초안 작성 중에는 지울 수 없습니다')
        import shutil
        shutil.rmtree(_cdir(cid))


# ---- 에이전트 설정 ----
AGENTS_CFG = CONSOLE / 'config' / 'agents.json'


def agents_view():
    cfg = _json(AGENTS_CFG, {})
    u = _json(DATA / 'agent' / 'usage.json', {}).get(now().strftime('%Y-%m'), {})
    total = sum(v.get('input', 0) + v.get('output', 0) for v in u.values())
    return {'config': cfg, 'usage': u, 'month_total': total}


def agents_save(b):
    cfg = _json(AGENTS_CFG, {})

    def num(v, lo, hi, name):
        try:
            v = int(v)
        except (TypeError, ValueError):
            raise ValueError(f'{name}: 숫자를 넣으세요')
        if not lo <= v <= hi:
            raise ValueError(f'{name}: {lo}~{hi} 사이로 넣으세요')
        return v
    if 'monthly_token_limit' in b:
        cfg['monthly_token_limit'] = num(b['monthly_token_limit'], 10000, 100000000, '월 토큰 한도')
    for acc, a in (b.get('planner_accounts') or {}).items():
        if acc not in ('dept', 'personal'):
            continue
        t = cfg.setdefault('planner', {}).setdefault('accounts', {}).setdefault(acc, {})
        t['enabled'] = bool(a.get('enabled'))
        t['count'] = num(a.get('count'), 1, 20, '제안 개수')
        t['weekday'] = num(a.get('weekday'), 0, 6, '요일')
        t['hour'] = num(a.get('hour'), 0, 23, '시각')
    for ag in ('planner', 'incident'):
        bb = (b.get('budgets') or {}).get(ag)
        if bb:
            t = cfg.setdefault(ag, {}).setdefault('budget', {})
            t['max_tokens'] = num(bb.get('max_tokens'), 2000, 500000, '실행당 토큰')
            t['max_tool_calls'] = num(bb.get('max_tool_calls'), 1, 200, '도구 호출')
            t['max_turns'] = num(bb.get('max_turns'), 1, 100, '턴')
    tmp = AGENTS_CFG.with_suffix('.tmp')
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(AGENTS_CFG)
    return agents_view()


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
        if self.path == '/api/agents':
            return self.send(200, agents_view())
        if self.path == '/api/contents':
            return self.send(200, {'items': contents(), 'checks': CHECKS,
                                   'auto': [f'{a}/{c}' for a, c in AUTO_PUBLISH]})
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
        if self.path.startswith('/api/automations/log?job='):
            try:
                return self.send(200, job_logs(urllib.parse.unquote(self.path.split('=', 1)[1])))
            except ValueError as e:
                return self.send(400, {'error': str(e)})
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
            if parts[:2] == ['api', 'tasks'] and parts[3:] == ['done']:
                task_done(parts[2], b.get('url'))
                return self.send(200, {'ok': True})
            if parts == ['api', 'agents']:
                return self.send(200, agents_save(b))
            if parts == ['api', 'contents']:
                return self.send(200, content_create(b))
            if parts[:2] == ['api', 'contents'] and len(parts) == 4:
                cid, op = parts[2], parts[3]
                if op == 'draft':
                    content_draft(cid)
                    return self.send(200, {'ok': True})
                if op == 'update':
                    return self.send(200, content_update(cid, b))
                if op == 'check':
                    return self.send(200, content_check(cid))
                if op == 'check_naver':
                    # 연달아 점검하면 네이버 편집기 자동저장이 다음 글에 섞인다(2026-10-18 확인) → 5분 간격
                    last = GW_STATE.get('naver_check')
                    if last and (now() - last).total_seconds() < 300:
                        raise ValueError('네이버 점검은 5분에 한 번만 할 수 있습니다(편집기 자동저장이 섞이지 않게)')
                    GW_STATE['naver_check'] = now()
                    c = cload(cid)
                    return self.send(200, {'naver_blog': publish_call(cid, c['account'], 'naver_blog', dry=True)[0]})
                if op == 'approve':
                    return self.send(200, content_approve(cid, b))
                if op == 'cancel':
                    return self.send(200, content_cancel(cid))
                if op == 'delete':
                    content_delete(cid)
                    return self.send(200, {'ok': True})
            if parts == ['api', 'gateway', 'check']:
                gateway_check()
                return self.send(200, gateway_view())
            if parts == ['api', 'google', 'check']:
                google_check()
                return self.send(200, google_view())
            if parts == ['api', 'github', 'switch']:
                github_switch(str(b.get('user', '')))
                return self.send(200, google_view())
            if parts == ['api', 'google', 'login']:
                google_login(str(b.get('account')), str(b.get('service')))
                return self.send(200, google_view())
            if parts[:2] == ['api', 'automations'] and len(parts) == 4 and parts[3] in ('on', 'off', 'run'):
                return self.send(200, job_control(parts[2], parts[3]))
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
    for f in CONTENT.glob('*/*/*/meta.json'):
        c = json.loads(f.read_text())
        if c.get('status') == 'drafting':
            c.update(status='idea', error='서버가 다시 켜져 초안 작성이 중단됐습니다')
            f.write_text(json.dumps(c, ensure_ascii=False, indent=2))
    threading.Thread(target=scheduler, daemon=True).start()
    threading.Thread(target=lambda: _safe(google_check), daemon=True).start()
    print(f'AX 발행 콘솔: http://{HOST}:{PORT}')
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()
