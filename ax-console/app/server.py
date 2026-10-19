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
import sys
sys.path.insert(0, str(ROOT))
from shared import axlock  # noqa: E402  잠금·대기·비상 정지
sys.path.insert(0, str(CONSOLE / 'app'))
import watcher  # noqa: E402  실패 대응 감시기
import auth  # noqa: E402  콘솔 로그인
import account_ops  # noqa: E402  채널 계정 로그아웃·비밀값 저장
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


# ---- 자동 작업 편집: 이름·설명(automations.json), 실행 시각(launchd plist) ----
def _sched_rows(pl):
    """StartCalendarInterval → [{'time':'HH:MM','days':[0..6]|[],'day':N|None}] (요일 비면 매일)."""
    iv = pl.get('StartCalendarInterval')
    if not iv:
        return []
    rows = {}
    for i in (iv if isinstance(iv, list) else [iv]):
        if 'Hour' not in i:
            continue
        k = (f"{i['Hour']:02d}:{i.get('Minute', 0):02d}", i.get('Day'))
        r = rows.setdefault(k, {'time': k[0], 'days': [], 'day': k[1]})
        if 'Weekday' in i:
            r['days'].append(i['Weekday'] % 7)
    return [{**r, 'days': sorted(set(r['days']))} for r in rows.values()]


def job_edit(job, b):
    cat = _json(AUTOMATIONS, {})
    j = next((x for x in cat.get('jobs', []) if x['job'] == job), None)
    if not j:
        raise ValueError('없는 작업입니다')
    changed = []
    for k, lim in (('name', 60), ('what', 400)):
        if k in b and str(b[k]).strip() and str(b[k]).strip() != j.get(k):
            j[k] = str(b[k]).strip()[:lim]
            changed.append(k)
    if changed:
        tmp = AUTOMATIONS.with_suffix('.tmp')
        tmp.write_text(json.dumps(cat, ensure_ascii=False, indent=2) + '\n')
        tmp.replace(AUTOMATIONS)
    if 'schedule' in b or 'interval_min' in b:
        f = _job_plist(job)
        pl = plistlib.loads(f.read_bytes())
        if 'interval_min' in b and pl.get('StartInterval'):
            m = int(b['interval_min'])
            if not 5 <= m <= 1440:
                raise ValueError('간격은 5~1440분 사이로')
            pl['StartInterval'] = m * 60
        elif 'schedule' in b:
            ivs = []
            for r in b['schedule']:
                hm = __import__('re').fullmatch(r'(\d{1,2}):(\d{2})', str(r.get('time', '')).strip())
                if not hm or int(hm.group(1)) > 23 or int(hm.group(2)) > 59:
                    raise ValueError(f"시각 형식이 맞지 않습니다: {r.get('time')}")
                base = {'Hour': int(hm.group(1)), 'Minute': int(hm.group(2))}
                if r.get('day'):
                    ivs.append({**base, 'Day': int(r['day'])})
                elif r.get('days'):
                    ivs += [{**base, 'Weekday': int(d) % 7} for d in sorted(set(r['days']))]
                else:
                    ivs.append(base)
            if not ivs:
                raise ValueError('실행 시각을 하나 이상 넣으세요')
            pl.pop('StartInterval', None)
            pl['StartCalendarInterval'] = ivs if len(ivs) > 1 else ivs[0]
        hist = DATA / 'config-history'
        hist.mkdir(parents=True, exist_ok=True)
        (hist / f"{f.stem}_{now().strftime('%Y%m%d_%H%M%S')}.plist").write_bytes(f.read_bytes())  # 바꾸기 전 사본
        f.write_bytes(plistlib.dumps(pl))
        if subprocess.run(['plutil', '-lint', str(f)], capture_output=True).returncode != 0:
            raise ValueError('plist 검사 실패 — config-history 의 사본으로 되돌리세요')
        dom, label = f'gui/{os.getuid()}', f.stem
        loaded, disabled = _launchd()
        if label in loaded:                 # 켜져 있던 작업만 새 시각으로 다시 올린다
            _lc('bootout', f'{dom}/{label}')
            _lc('bootstrap', dom, str(f))
        changed.append('schedule')
        with open(DATA / 'logs' / 'launchd_control.log', 'a') as lf:
            lf.write(f"{now().isoformat()} edit-schedule {label} → {_when_text(pl)}\n")
    return {'changed': changed, 'job': next(x for x in automations() if x['job'] == job)}


# ---- 콘솔 예약 고치기·취소 ----
def task_reschedule(tid, b):
    with LOCK:
        tasks = load()
        t = next((x for x in tasks if x['id'] == tid), None)
        if not t:
            raise ValueError('작업을 찾지 못했습니다')
        if t['status'] == 'running':
            raise ValueError('실행 중에는 고칠 수 없습니다')
        if 'title' in b and str(b['title']).strip():
            t['title'] = str(b['title']).strip()[:200]
        if 'schedule' in b:
            v = str(b['schedule'] or '').strip()
            if v:
                try:
                    datetime.datetime.fromisoformat(v)
                except ValueError:
                    raise ValueError('시각은 2026-10-20 09:30 처럼 넣으세요')
            t['schedule'] = v
        if b.get('repeat') in ('', 'daily', 'weekly') and 'repeat' in b:
            t['repeat'] = b['repeat']
        if b.get('state') == 'scheduled':
            if not t.get('schedule'):
                raise ValueError('예약하려면 실행 시각을 정하세요')
            t['status'] = 'scheduled'
        elif b.get('state') == 'draft':
            if t.get('content'):
                raise ValueError('콘텐츠 예약은 콘텐츠 탭에서 취소하세요(채널 묶음으로 취소됩니다)')
            t['status'] = 'draft'
        save(tasks)
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


def _is_live(t):
    if t.get('action') == 'publish':
        return True
    a = find_action(t.get('account'), t.get('channel'), t.get('action'))
    return bool(a and a.get('live'))


def scheduler():
    while True:
        due = []
        with LOCK:
            for t in load():
                if t.get('status') == 'scheduled' and t.get('schedule') and \
                        datetime.datetime.fromisoformat(t['schedule']) <= now():
                    if axlock.stopped() and _is_live(t):
                        continue  # 비상 정지 중: 발행 작업은 예약된 채로 둔다(풀리면 바로 돈다)
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


_SECRET_NAMES = {'mtime': None, 'names': None}


def secret_names():
    """암호화 저장소에 있는 비밀값 이름. 복호화에 파이썬을 하나 더 띄워 0.15초 걸리므로
    저장소 파일(secrets.env.enc)이 바뀌었을 때만 다시 읽는다."""
    try:
        mt = (ROOT / 'secrets.env.enc').stat().st_mtime
    except OSError:
        mt = None
    if mt is not None and _SECRET_NAMES['mtime'] == mt and _SECRET_NAMES['names'] is not None:
        return set(_SECRET_NAMES['names'])
    try:
        p = subprocess.run(['python3', '-m', 'shared.secret_env', 'names'], cwd=str(ROOT),
                           capture_output=True, text=True, timeout=20)
        names = set(p.stdout.split()) if p.returncode == 0 else None
    except Exception:
        names = None
    _SECRET_NAMES.update(mtime=mt if names is not None else None, names=names)
    return None if names is None else set(names)


def settings_view():
    cfg = _json(ACCOUNTS, {})
    have = secret_names()
    used = sorted(set(__import__('re').findall(r'"([A-Z][A-Z0-9_]{3,})"', json.dumps(cfg))))
    return {'accounts': cfg.get('accounts', {}), 'channel_labels': CH_LABEL,
            'secrets': [{'name': n, 'ok': None if have is None else n in have, 'used': n in used}
                        for n in sorted(set(used) | (have or set()), key=lambda n: (n not in used, n))],
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
    args = pl.get('ProgramArguments', [''])
    script = Path(next((a for a in args if a.endswith('.sh')), args[-1]))
    if script.name == 'run_claude_job.sh':      # 클로드 작업: logs/<작업>.log 에 claude -p 출력이 쌓인다
        files.append(str(script.parent / 'logs' / f'{args[-1]}.log'))
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
                    'sched': _sched_rows(pl), 'interval_min': (pl.get('StartInterval') or 0) // 60,
                    'script': ' '.join(a for a in pl.get('ProgramArguments', ['']) if a != '/bin/bash').replace(str(ROOT) + '/', '')})
    try:
        out += [{k: v for k, v in j.items() if k != 'times'} for j in codex_jobs()]
    except Exception as e:
        axlock.log(f'Codex 자동화 읽기 실패: {type(e).__name__}: {e}')
    return out


# ---- Codex 자동화(GeoAI_NA 작업)를 개인 계정 자동 작업으로 보여 주기(읽기 전용) ----
CODEX_AUTOS = Path.home() / '.codex' / 'automations'


def _toml_str(txt, key):
    """automation.toml 의 한 줄짜리·여러 줄 문자열 값(파이썬 3.9 라 tomllib 없이 필요한 칸만)."""
    import re
    m = re.search(rf'^{key}\s*=\s*"""(.*?)"""', txt, re.S | re.M) or re.search(rf'^{key}\s*=\s*"((?:[^"\\]|\\.)*)"', txt, re.M)
    if not m:
        return ''
    v = m.group(1)
    try:
        return json.loads(f'"{v}"') if '\n' not in v else v
    except ValueError:
        return v


def _rrule_times(rrule, start, days):
    import re
    hours = [int(h) for h in (re.search(r'BYHOUR=([\d,]+)', rrule) or [None, ''])[1].split(',') if h != '']
    minute = int((re.search(r'BYMINUTE=(\d+)', rrule) or [None, '0'])[1])
    wd = (re.search(r'BYDAY=([A-Z,]+)', rrule) or [None, ''])[1]
    days_ok = {'SU': 0, 'MO': 1, 'TU': 2, 'WE': 3, 'TH': 4, 'FR': 5, 'SA': 6}
    want = {days_ok[x] for x in wd.split(',') if x in days_ok}
    out = []
    for d in range(days):
        day = (start + datetime.timedelta(days=d)).date()
        if want and day.isoweekday() % 7 not in want:
            continue
        for h in hours:
            t = datetime.datetime.combine(day, datetime.time(h, minute))
            if t > start:
                out.append(t)
    return sorted(out), hours, minute


def question_queues():
    """친구 질문 대기열(클로드 자동 작업 claude.*-friend 가 처리). 제목은 외부 사용자가 쓴 글이라 화면에서 이스케이프해 보여 준다."""
    base = ROOT / 'GeoAI_NA' / 'engineer-question-worker'
    out = []
    for f, label in (('state.json', '측량및지형공간정보기술사'), ('civil-state.json', '토목시공기술사')):
        jobs = list(_json(base / f, {}).get('jobs', {}).values())
        cnt = {}
        for j in jobs:
            cnt[j.get('status', '?')] = cnt.get(j.get('status', '?'), 0) + 1
        pending = sorted([j for j in jobs if j.get('status') in ('queued', 'processing', 'published')], key=lambda j: j.get('created_at', ''))
        out.append({'label': label, 'counts': cnt, 'total': len(jobs),
                    'pending': [{'title': j.get('title', '')[:80], 'at': j.get('created_at', '')[:16], 'status': j.get('status')} for j in pending[:5]]})
    return out


def codex_jobs(days=8):
    out, start = [], now()
    moved = {j.get('codex') for j in _json(ROOT / 'GeoAI_NA' / 'claude-jobs' / 'jobs.json', {}).get('jobs', [])}
    for f in sorted(CODEX_AUTOS.glob('*/automation.toml')):
        if f.parent.name in moved:              # 클로드 작업(claude.*)으로 옮긴 것은 그쪽에 보인다
            continue
        txt = f.read_text(errors='ignore')
        name, status, rrule, prompt = (_toml_str(txt, k) for k in ('name', 'status', 'rrule', 'prompt'))
        times, hours, minute = _rrule_times(rrule, start, days)
        low = prompt.lower()
        ch = []
        if 'tistory' in low:
            ch.append(['personal', 'tistory'])
        if '유튜브' in prompt or '숏츠' in prompt or 'youtube' in low:
            ch.append(['personal', 'youtube'])
        if 'blogspot' in low or '블로거' in prompt:
            ch.append(['personal', 'blogger'])
        if '카톡' in prompt or '카카오' in prompt:
            ch.append(['personal', 'kakao'])
        ch = ch or [['personal', 'tistory']]
        when = '매일 ' + ', '.join(f'{h:02d}:{minute:02d}' for h in hours) if hours else rrule
        out.append({'job': f'codex.{f.parent.name}', 'source': 'codex', 'account': 'personal', 'name': name or f.parent.name,
                    'what': prompt.strip().splitlines()[0][:220] if prompt.strip() else '', 'channels': ch,
                    'on': status == 'ACTIVE', 'disabled': status != 'ACTIVE', 'running': False, 'exit': '',
                    'controllable': False, 'live': True, 'when': when, 'last': '',
                    'next': [t.isoformat(timespec='minutes') for t in times[:3]], 'times': [t.isoformat(timespec='minutes') for t in times],
                    'sched': [], 'interval_min': 0, 'script': f'Codex 자동화 {f.parent.name} (~/.codex/automations)',
                    'note': '' if status == 'ACTIVE' else f'Codex 에서 {status}', 'codex': True})
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


def _set_note(job, note):
    """automations.json 의 작업 note 를 쓰거나(note) 지운다(None). 지운 note 는 last_note 로 남긴다.
    note 가 있는 작업은 장애 감시(내려감·놓침·로그)가 '일부러 끈 작업'으로 본다."""
    data = _json(AUTOMATIONS, {})
    for j in data.get('jobs', []):
        if j['job'] == job:
            if note:
                j['note'] = note
            elif j.get('note'):
                j['last_note'] = j.pop('note')
    tmp = AUTOMATIONS.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(AUTOMATIONS)


def job_control(job, op, reason=''):
    f = _job_plist(job)
    dom, label = f'gui/{os.getuid()}', f'com.smuds.{job}'
    loaded = label in _launchd()[0]
    if op == 'off':
        if loaded:
            _lc('bootout', f'{dom}/{label}')
        _lc('disable', f'{dom}/{label}')
        # 콘솔에서 끈 작업은 '일부러 끈 작업' — 이유를 note 로 남겨 장애 감시가 '내려감'으로 잡지 않게(2026-10-19)
        _set_note(job, f"{now():%Y-%m-%d %H:%M} 콘솔에서 끔 — {reason.strip()[:200] or '사유 미기록'}")
    elif op == 'on':
        _lc('enable', f'{dom}/{label}')
        if not loaded:
            _lc('bootstrap', dom, str(f))
        _set_note(job, None)            # 다시 켰으니 끈 이유는 지운다(감시가 다시 이 작업을 본다)
    elif op == 'run':
        if not loaded:
            raise ValueError('꺼진 작업입니다. 먼저 켜세요')
        _lc('kickstart', f'{dom}/{label}')
    else:
        raise ValueError('없는 동작입니다')
    with open(DATA / 'logs' / 'launchd_control.log', 'a') as lf:
        lf.write(f'{now().isoformat()} {op} {label}' + (f' — {reason.strip()[:200]}' if reason.strip() else '') + '\n')
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
    codex = {j['job']: j['times'] for j in codex_jobs(days)} if CODEX_AUTOS.exists() else {}
    for j in automations():
        if j['account'] == 'common' and not j['next']:
            continue
        base = {'account': j['account'], 'channel': j['channels'][0][1], 'channels': j['channels'], 'title': j['name'],
                'what': j['when'], 'source': 'codex' if j.get('codex') else 'launchd', 'job': j['job'], 'on': j['on']}
        times = []
        if j.get('codex'):
            times = codex.get(j['job'], [])
        elif j['next'] and '분마다' not in j['when']:
            iv = plistlib.loads((AGENTS / f"com.smuds.{j['job']}.plist").read_bytes()).get('StartCalendarInterval')
            times = [t.isoformat(timespec='minutes') for t in _next_times(iv, start, days)]
        if not times and not j.get('codex'):
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
    cli_logins(force=True)
    _safe(site_info)


CLI_LOGINS = {}


def cli_logins(force=False):
    """gh·netlify CLI 에 로그인된 계정 이름(토큰은 읽지 않는다).
    gh auth status 는 네트워크로 토큰을 확인해 한 번에 0.7초쯤 걸린다 — 계정 연결 화면을 열 때마다 돌면
    화면이 무거워서 5분 동안 결과를 쓰고, 계정을 바꿀 때(force)만 바로 다시 읽는다(2026-10-19)."""
    if not force and CLI_LOGINS.get('_at') and time.time() - CLI_LOGINS['_at'] < 300:
        return
    gh = set()
    for exe in ('/opt/homebrew/bin/gh', '/usr/local/bin/gh'):
        if os.path.exists(exe):
            p = subprocess.run([exe, 'auth', 'status'], capture_output=True, text=True, timeout=30)
            out = p.stdout + p.stderr
            gh = set(__import__('re').findall(r'account (\S+)', out))
            act = __import__('re').search(r'account (\S+)[^\n]*\n\s*- Active account: true', out)
            CLI_LOGINS['github_active'] = act.group(1) if act else None
            CLI_LOGINS['gh_bin'] = exe
            break
    nl = {u.get('email') for u in _json(Path.home() / 'Library' / 'Preferences' / 'netlify' / 'config.json', {})
          .get('users', {}).values()}
    CLI_LOGINS.update(github=gh, netlify=nl, _at=time.time())


def github_switch(user):
    cli_logins(force=True)
    known = {x['id'] for a in _json(ACCOUNTS, {}).get('accounts', {}).values() for x in (a.get('github') or {}).get('accounts', [])}
    if user not in known:
        raise ValueError('설정에 없는 GitHub 계정입니다')
    if user not in CLI_LOGINS.get('github', set()):
        raise ValueError(f'{user} 는 아직 gh 에 로그인돼 있지 않습니다. 터미널에서 gh auth login 으로 먼저 추가하세요')
    p = subprocess.run([CLI_LOGINS['gh_bin'], 'auth', 'switch', '--hostname', 'github.com', '--user', user],
                       capture_output=True, text=True, timeout=30)
    if p.returncode != 0:
        raise ValueError((p.stderr or p.stdout).strip()[:200])
    cli_logins(force=True)


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


def _rss(url):
    import html as H
    import urllib.request
    x = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=15).read().decode('utf-8', 'ignore')
    t = __import__('re').search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', x, __import__('re').S)
    last = __import__('re').search(r'<pubDate>(.*?)</pubDate>', x[x.find('<item>'):]) if '<item>' in x else None
    first = __import__('re').search(r'<item>.*?<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', x, __import__('re').S)
    return {'name': H.unescape(t.group(1)).strip() if t else '', 'recent': x.count('<item>'),
            'last': last.group(1) if last else '', 'last_title': H.unescape(first.group(1)).strip()[:80] if first else ''}


def site_info():
    """구글 밖 채널의 공개 정보(블로그 이름·최근 글, GitHub 저장소 수). 계정 연결 화면에 쓴다."""
    out, cfg = {}, _json(ACCOUNTS, {}).get('accounts', {})
    for acc, a in cfg.items():
        nb = (a.get('naver') or {}).get('blog')
        if nb:
            try:
                r = _rss(f'https://rss.blog.naver.com/{nb}.xml')
                out[f'{acc}/naver'] = {'name': r['name'], 'url': f'https://blog.naver.com/{nb}',
                                       'stats': {'최근 글': r['recent']}, 'note': f"마지막 글 {r['last'][:16]} · {r['last_title']}"}
            except Exception as e:
                out[f'{acc}/naver'] = {'error': str(e)[:120]}
        ts = (a.get('tistory') or {}).get('id')
        if ts:
            try:
                r = _rss(f'https://{ts}/rss')
                out[f'{acc}/tistory'] = {'name': r['name'], 'url': f'https://{ts}', 'stats': {'최근 글': r['recent']},
                                         'note': f"마지막 글 {r['last'][:16]} · {r['last_title']}"}
            except Exception as e:
                out[f'{acc}/tistory'] = {'error': str(e)[:120]}
        for g in (a.get('github') or {}).get('accounts', []):
            gh = CLI_LOGINS.get('gh_bin') or '/usr/local/bin/gh'
            try:
                r = subprocess.run([gh, 'api', f"users/{g['id']}"], capture_output=True, text=True, timeout=20)
                u = json.loads(r.stdout)
                out[f"github/{g['id']}"] = {'name': u.get('login'), 'url': u.get('html_url'),
                                           'stats': {'공개 저장소': u.get('public_repos', 0), '팔로워': u.get('followers', 0)}}
            except Exception as e:
                out[f"github/{g['id']}"] = {'error': str(e)[:120]}
    GSTATE['site_info'] = out
    GSTATE['site_checked'] = now().isoformat()
    return out


def _safe(fn):
    try:
        fn()
    except Exception:
        pass


def google_check_bg():
    """콘솔이 켜질 때 한 번 도는 토큰 확인. 도는 동안만 checking=True — 화면은 그동안만 다시 묻는다.
    전에는 '확인 안 됨'(실패 포함)이면 계정 연결 화면이 3초마다 /api/google(1.6초짜리)을 끝없이 불렀다."""
    GSTATE['checking'], GSTATE['check_error'] = True, ''
    try:
        google_check()
    except Exception as e:
        GSTATE['check_error'] = f'{type(e).__name__}: {str(e)[:200]}'
    finally:
        GSTATE['checking'] = False


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
            others.append({'info': GSTATE.get('site_info', {}).get(f'{acc}/{kind}'), 'label': label, 'kind': kind, 'id': o.get('id', ''), 'login': o.get('login', ''), 'note': o.get('note', ''),
                           'secrets': sec, 'ok': ok, 'state': state,
                           'site': {'naver': 'naver' if acc == 'dept' else '', 'tistory': 'tistory'}.get(kind, ''),
                           'site_login': GSTATE['login'].get('site:' + {'naver': 'naver', 'tistory': 'tistory'}.get(kind, '-'))})
        gh = None
        if a.get('github'):
            gh = {'note': a['github'].get('note', ''), 'accounts': [
                {**x, 'logged_in': x['id'] in CLI_LOGINS.get('github', set()), 'active': x['id'] == CLI_LOGINS.get('github_active'),
                 'info': GSTATE.get('site_info', {}).get(f"github/{x['id']}")}
                for x in a['github'].get('accounts', [])]}
        accs.append({'id': acc, 'label': a['label'], 'email': a['google']['email'], 'services': svcs, 'others': others,
                     'github': gh})
    return {'checked': GSTATE['checked'], 'checking': GSTATE.get('checking', False), 'check_error': GSTATE.get('check_error', ''), 'accounts': accs}


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


PUBLISH_LOCKS = {  # 자동 발행이 함께 잡는 자원 — launchd 작업과 같은 이름(automations.json locks)
    ('dept', 'naver_blog'): ['profile:naver'], ('dept', 'blogger'): ['quota:blogger-dept'],
    ('personal', 'blogger'): ['quota:blogger-personal'],
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
        if axlock.stopped():
            raise RuntimeError('비상 정지 중이라 발행하지 않았습니다')
        with axlock.hold(PUBLISH_LOCKS.get((t['account'], t['channel']), []) + [f"job:console-{t['account']}-{t['channel']}"],
                         job=f"console:{t['id']}"):
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
    if 'incident_enabled' in b:
        cfg.setdefault('incident', {})['enabled'] = bool(b['incident_enabled'])
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


# ---- 실패 대응: 감시기·장애 ----
WSTATE = {'running': False}


def watch_loop():
    while True:
        run_watch()
        time.sleep(600)


def run_watch():
    if WSTATE['running']:
        return
    WSTATE['running'] = True
    try:
        watcher.check()
        _safe(planner_due)
        cfg = _json(CONSOLE / 'config' / 'agents.json', {}).get('incident', {})
        if cfg.get('enabled'):   # 자동 원인 분석(설정에서 켬): 아직 분석 안 된 '오류' 사건만
            for x in watcher.incidents('open'):
                if x['severity'] == 'error' and not x.get('analysis') and not x.get('analyzing'):
                    analyze(x['id'])
                    break        # 한 번에 하나씩
    except Exception as e:
        axlock.log(f'감시기 오류: {type(e).__name__}: {e}')
    finally:
        WSTATE['running'] = False


def incidents_view():
    items = watcher.incidents()
    st = watcher._load(watcher.STATE, {})
    cat, bs = catalog(), _json(BS_CFG, {}).get('profiles', {})
    for x in items:   # 조치하기 메뉴에 쓸 정보: 다시 실행할 수 있나, 어느 크롬 프로필을 쓰나
        j = cat.get(x['job'], {})
        x['ctl'] = x['job'] in cat and x['job'] not in SELF_JOBS and (AGENTS / f"com.smuds.{x['job']}.plist").exists()
        x['profiles'] = [{'name': l.split(':', 1)[1], 'mode': bs.get(l.split(':', 1)[1], '')}
                         for l in j.get('locks', []) if l.startswith('profile:')]
    return {'items': items, 'checked': st.get('checked'), 'counts': st.get('last_counts'),
            'open_errors': sum(1 for x in items if x['status'] == 'open' and x['severity'] == 'error'),
            'auto': bool(_json(CONSOLE / 'config' / 'agents.json', {}).get('incident', {}).get('enabled'))}


ACT_LABEL = {'rerun': '작업 다시 실행', 'jobon': '작업 다시 켬', 'bs_off': '콘솔 브라우저 끔(예전 방식)',
             'bs_hidden': '콘솔 브라우저를 숨김 창 방식으로'}


def incident_act(iid, b):
    """조치하기 — 사건 기록에 무엇을 했는지 남긴다. 사람이 콘솔 다른 화면에서 하는 조치(다시 로그인 등)는 note 로 기록만."""
    inc = watcher._load(watcher.incident_path(iid), None)
    if not inc:
        raise ValueError('사건을 찾지 못했습니다')
    act, prof = str(b.get('action', '')), str(b.get('profile', ''))
    if act == 'rerun':
        job_control(inc['job'], 'run')
    elif act == 'jobon':
        job_control(inc['job'], 'on')
    elif act in ('bs_off', 'bs_hidden'):
        bs_save({'profile': prof, 'mode': '' if act == 'bs_off' else 'hidden'})
    elif act != 'note':
        raise ValueError('없는 조치입니다')
    what = '조치: ' + (str(b.get('note', ''))[:200] if act == 'note' else ACT_LABEL[act] + (f' ({prof})' if prof else ''))
    watcher.add_history(iid, what)
    axlock.log(f"장애 {iid} {what}")


def analyze(iid):
    """② 원인 분석 에이전트를 백그라운드로 돌린다."""
    p = watcher.incident_path(iid)
    inc = watcher._load(p, None)
    if not inc:
        raise ValueError('사건을 찾지 못했습니다')
    if inc.get('analyzing'):
        raise ValueError('이미 분석 중입니다')
    inc['analyzing'] = now().isoformat()
    watcher._save(p, inc)

    def work():
        try:
            r = subprocess.run([GPY, str(CONSOLE / 'app' / 'agents' / 'incident.py'), iid], cwd=str(ROOT / 'youtube-shorts-auto'),
                               capture_output=True, text=True, timeout=1200)
            try:
                res = json.loads(r.stdout.strip().splitlines()[-1])
            except (IndexError, ValueError):
                res = {'error': ((r.stderr or '').strip().splitlines() or ['출력 없음'])[-1][:300]}
        except Exception as e:
            res = {'error': str(e)[:300]}
        x = watcher._load(p, inc)
        x.pop('analyzing', None)
        x['analysis'] = {**res, 'at': now().isoformat()}
        x['history'].append({'at': now().isoformat(), 'what': '원인 분석 ' + ('실패: ' + res['error'] if res.get('error') else '완료')})
        if res.get('human_needed') is False and res.get('confidence') == '확실':
            x['history'].append({'at': now().isoformat(), 'what': '사람 조치가 필요 없다고 판단'})
        watcher._save(p, x)

    threading.Thread(target=work, daemon=True).start()


# ---- D3 내부 브라우저: browser_worker.py(127.0.0.1:8711) 를 띄우고 중계한다 ----
BW = 'http://127.0.0.1:8711'
BW_PROC = {'p': None}
BW_PROFILES = {  # 프로필 → (이름, 로그인 주소, 로그인 확인 쿠키 도메인·이름, 쿠키 파일로 받아 둘 곳)
    'naver': ('네이버 (학과 smuds)', 'https://nid.naver.com/nidlogin.login', ('naver.com', 'NID_AUT'), None),
    'tistory': ('티스토리 (개인 na-geoai, 카카오 로그인)', 'https://www.tistory.com/auth/login', ('tistory.com', 'TSSESSION'),
                (['tistory', 'kakao'], 'GeoAI_NA/naver-blog-auto/tistory_cookies.json')),
    'insta': ('인스타그램·스레드 (학과)', 'https://www.instagram.com/accounts/login/', ('instagram.com', 'sessionid'), None),
    'tiktok': ('틱톡 (학과)', 'https://www.tiktok.com/login', ('tiktok.com', 'sessionid'), None),
    'youtube-personal': ('유튜브 (개인 GeoAI)', 'https://studio.youtube.com', ('youtube.com', 'SID'), None),
    'youtube-dept': ('유튜브 (학과)', 'https://studio.youtube.com', ('youtube.com', 'SID'), None),
    'scratch': ('빈 브라우저 (아무 계정 없음)', 'https://www.naver.com', None, None),
}


def bw_call(path, body=None, raw=False, timeout=60):
    import urllib.request
    key = auth.internal_key()
    for attempt in (1, 2):
        try:
            req = urllib.request.Request(BW + path, data=None if body is None else json.dumps(body).encode(),
                                         headers={'Content-Type': 'application/json', 'X-AX-Internal': key})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            return data if raw else json.loads(data)
        except urllib.error.HTTPError as e:
            raise ValueError(json.loads(e.read() or b'{}').get('error', f'브라우저 서비스 오류 {e.code}'))
        except (urllib.error.URLError, ConnectionError):
            if attempt == 2:
                raise ValueError('브라우저 서비스를 켜지 못했습니다')
            bw_start()


def bw_start():
    if BW_PROC['p'] and BW_PROC['p'].poll() is None:
        return
    BW_PROC['p'] = subprocess.Popen([GPY, str(CONSOLE / 'app' / 'browser_worker.py')], cwd=str(CONSOLE / 'app'),
                                    stdout=subprocess.DEVNULL, stderr=open(DATA / 'logs' / 'browser_worker.log', 'a'))
    for _ in range(30):
        time.sleep(0.3)
        try:
            import urllib.request
            urllib.request.urlopen(urllib.request.Request(BW + '/list', headers={'X-AX-Internal': auth.internal_key()}), timeout=1)
            return
        except Exception:
            pass


BS_CFG = CONSOLE / 'config' / 'browser_service.json'


def bs_save(b):
    cfg = _json(BS_CFG, {'profiles': {}})
    prof, mode = str(b.get('profile', '')), str(b.get('mode', ''))
    if prof not in BW_PROFILES or prof == 'scratch':
        raise ValueError('없는 프로필입니다')
    if mode not in ('', 'headless', 'hidden'):
        raise ValueError('없는 방식입니다')
    if mode:
        cfg.setdefault('profiles', {})[prof] = mode
    else:
        cfg.setdefault('profiles', {}).pop(prof, None)
    tmp = BS_CFG.with_suffix('.tmp')
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(BS_CFG)
    axlock.log(f"브라우저 서비스 설정: {prof} → {mode or '예전 방식(바깥 창)'}")
    return cfg


def bw_login_done(profile):
    """사람이 내부 브라우저에서 로그인한 뒤: 로그인 쿠키 확인 → (필요하면) 쿠키 파일 저장 → 크롬을 정상 종료해 저장."""
    name, _, check, save = BW_PROFILES[profile]
    ok = True
    if check:
        ck = bw_call(f'/cookies?profile={profile}&domain={check[0]}')
        ok = check[1] in ck['names']
        if not ok:
            raise ValueError(f'아직 로그인되지 않았습니다({check[0]} 의 {check[1]} 쿠키 없음). 로그인을 마친 뒤 다시 누르세요')
        # 쿠키를 파일로 받아 두지 않는 프로필은 로그인 쿠키가 디스크에 남아야 한다 — 세션 쿠키면 창을 닫는 순간 풀린다
        # (2026-10-18 23:00 네이버 로그인이 다음 날 아침 통계 수집에서 401: NID_AUT 가 세션 쿠키로만 있었다)
        if not save and check[1] in ck.get('session', []):
            raise ValueError(f"로그인은 됐지만 '로그인 상태 유지'가 꺼져 있어 창을 닫으면 풀립니다({check[1]} 가 세션 쿠키). "
                             "로그아웃한 뒤 '로그인 상태 유지'를 켜고 다시 로그인하세요")
    saved = bw_call('/save_cookies', {'profile': profile, 'domains': save[0], 'path': save[1]})['saved'] if save else None
    bw_call('/stop', {'profile': profile})
    axlock.log(f'내부 브라우저 로그인 완료: {profile}' + (f' (쿠키 {saved}개 파일 저장)' if saved is not None else ''))
    GSTATE['login'][f'site:{profile}'] = {'state': '완료', 'at': now().isoformat(), 'msg': '내부 브라우저에서 로그인'}
    _safe(site_info)
    return {'ok': ok, 'saved': saved}


# ---- ⓪ 주간 기획 제안 ----
PROP = DATA / 'proposals'
PSTATE = {'running': set()}


def _week():
    y, w, _ = now().isocalendar()
    return f'{y}-W{w:02d}'


def prop_files():
    return sorted(PROP.glob('*-W*_*.json'))


def proposals_view():
    out = []
    for f in prop_files()[-8:]:
        d = _json(f, {})
        for it in d.get('items', []):
            out.append({**it, 'week': d.get('week'), 'account': d.get('account'), 'file': f.name})
    return {'items': out[::-1], 'running': sorted(PSTATE['running'])}


def run_planner(acc, why='수동'):
    if acc in PSTATE['running']:
        raise ValueError('이미 제안을 만드는 중입니다')
    cfg = _json(CONSOLE / 'config' / 'agents.json', {}).get('planner', {}).get('accounts', {}).get(acc, {})
    count = int(cfg.get('count', 5))
    PSTATE['running'].add(acc)

    def work():
        try:
            p = subprocess.run([GPY, str(CONSOLE / 'app' / 'agents' / 'planner.py'), acc, str(count)],
                               cwd=str(ROOT / 'youtube-shorts-auto'), capture_output=True, text=True, timeout=1800)
            d = json.loads((p.stdout or '').strip().splitlines()[-1])
            if d.get('error'):
                raise RuntimeError(d['error'])
            PROP.mkdir(parents=True, exist_ok=True)
            f = PROP / f'{_week()}_{acc}.json'
            old = _json(f, {}).get('items', [])
            items = old + [{**x, 'id': uuid.uuid4().hex[:8], 'status': 'new', 'created': now().isoformat()} for x in d['proposals']]
            f.write_text(json.dumps({'week': _week(), 'account': acc, 'items': items, 'log': d.get('log'), 'usage': d.get('usage')},
                                    ensure_ascii=False, indent=2))
            axlock.log(f"기획 제안 {acc}: {len(d['proposals'])}개 ({why})")
        except Exception as e:
            axlock.log(f'기획 제안 {acc} 실패: {type(e).__name__}: {str(e)[:200]}')
        finally:
            PSTATE['running'].discard(acc)

    threading.Thread(target=work, daemon=True).start()


def planner_due():
    """설정한 요일·시각이 지났고 이번 주 제안이 아직 없으면 돌린다(감시기 주기에 함께 점검)."""
    cfg = _json(CONSOLE / 'config' / 'agents.json', {}).get('planner', {}).get('accounts', {})
    t = now()
    for acc, c in cfg.items():
        if not c.get('enabled'):
            continue
        if (t.isoweekday() % 7) == int(c.get('weekday', 0)) and t.hour >= int(c.get('hour', 20)) \
                and not (PROP / f'{_week()}_{acc}.json').exists() and acc not in PSTATE['running']:
            run_planner(acc, '예약')


def prop_decide(pid, decision, reason=''):
    for f in prop_files():
        d = _json(f, {})
        for it in d.get('items', []):
            if it['id'] != pid:
                continue
            if it['status'] != 'new':
                raise ValueError('이미 처리한 제안입니다')
            it['status'], it['reason'], it['decided'] = decision, reason[:300], now().isoformat()
            res = {}
            if decision == 'accepted':
                notes = f"{it.get('summary', '')}\n왜 지금: {it.get('why_now', '')}\n근거: " + ' / '.join(it.get('evidence', []))
                c = content_create({'account': d['account'], 'topic': it['topic'], 'notes': notes, 'channels': it.get('channels', [])})
                it['content'] = c['id']
                res = {'content': c['id']}
            f.write_text(json.dumps(d, ensure_ascii=False, indent=2))
            with (PROP / 'feedback.jsonl').open('a') as fb:   # 다음 제안에 반영(planner.rejections)
                fb.write(json.dumps({'at': now().isoformat(), 'account': d['account'], 'decision': '채택' if decision == 'accepted' else '반려',
                                     'topic': it['topic'], 'reason': reason[:300]}, ensure_ascii=False) + '\n')
            return res
    raise ValueError('제안을 찾지 못했습니다')


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, obj=None, body=None, ctype='application/json; charset=utf-8', headers=None):
        data = body if body is not None else json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Cache-Control', 'no-store')
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        n = int(self.headers.get('Content-Length') or 0)
        return json.loads(self.rfile.read(n) or b'{}')

    def same_origin(self):
        # 다른 사이트가 브라우저를 통해 실행 요청을 보내지 못하게 막는다
        o = self.headers.get('Origin')
        return o in (None, f'http://{HOST}:{PORT}', f'http://localhost:{PORT}')

    # ---- 로그인 ----
    def token(self):
        return auth.cookie_of(self.headers.get('Cookie'))

    def authed(self):
        k = self.headers.get('X-AX-Internal')
        if k and auth.hmac.compare_digest(k, auth.internal_key()):
            return True
        return auth.check(self.token())

    def do_GET(self):
        if self.path == '/login' or self.path.startswith('/login?'):
            return self.send(200, body=(CONSOLE / 'app' / 'login.html').read_bytes(), ctype='text/html; charset=utf-8')
        if self.path == '/api/auth/status':
            return self.send(200, {'setup': auth.is_setup(), 'logged_in': self.authed()})
        if not self.path.startswith('/fonts/') and not self.authed():
            if self.path in ('/', '/index.html'):
                return self.send(302, body=b'', headers={'Location': '/login'})
            return self.send(401, {'error': '로그인이 필요합니다', 'login': True})
        if self.path in ('/', '/index.html'):
            return self.send(200, body=(CONSOLE / 'app' / 'index.html').read_bytes(), ctype='text/html; charset=utf-8')
        if self.path.startswith('/fonts/'):
            f = ROOT / 'FONTS' / 'Pretendard-Bold.otf'
            return self.send(200, body=f.read_bytes(), ctype='font/otf')
        if self.path == '/api/meta':
            return self.send(200, meta())
        if self.path == '/api/browser/config':
            return self.send(200, {**_json(BS_CFG, {'profiles': {}}), 'names': {k: v[0] for k, v in BW_PROFILES.items() if k != 'scratch'}})
        if self.path == '/api/browser/list':
            try:
                sess = bw_call('/list', timeout=5) if BW_PROC['p'] and BW_PROC['p'].poll() is None else []
            except ValueError:
                sess = []
            return self.send(200, {'sessions': sess, 'profiles': {k: {'name': v[0], 'login_url': v[1], 'has_check': bool(v[2])}
                                                                     for k, v in BW_PROFILES.items()}})
        if self.path.startswith('/api/browser/shot?profile='):
            # 프로필이 닫혔거나(작업이 끝나 창을 닫음) 서비스가 꺼진 경우 — 화면은 404 를 받고 새로 그린다(예외를 흘리지 않음)
            try:
                return self.send(200, body=bw_call('/shot?profile=' + self.path.split('=', 1)[1], raw=True, timeout=20), ctype='image/jpeg')
            except ValueError as e:
                return self.send(404, {'error': str(e), 'closed': True})
        if self.path == '/api/incidents':
            return self.send(200, incidents_view())
        if self.path.startswith('/api/shot?'):
            from urllib.parse import unquote
            f = Path(unquote(self.path.split('=', 1)[1])).resolve()
            if f.suffix != '.png' or not str(f).startswith(str(ROOT)) or not f.exists():
                return self.send(404, {'error': '없음'})
            return self.send(200, body=f.read_bytes(), ctype='image/png')
        if self.path == '/api/orchestrator':
            st = axlock.status()
            try:
                with open(axlock.LOG, 'rb') as f:     # 10초마다 불리므로 끝 16KB 만 읽는다(로그는 계속 자란다)
                    f.seek(max(0, os.path.getsize(axlock.LOG) - 16384))
                    st['log'] = f.read().decode('utf-8', 'ignore').splitlines()[-30:]
            except OSError:
                st['log'] = []
            return self.send(200, st)
        if self.path == '/api/proposals':
            return self.send(200, proposals_view())
        if self.path == '/api/agents':
            return self.send(200, agents_view())
        if self.path == '/api/contents':
            return self.send(200, {'items': contents(), 'checks': CHECKS,
                                   'auto': [f'{a}/{c}' for a, c in AUTO_PUBLISH]})
        if self.path == '/api/gateway':
            return self.send(200, gateway_view())
        if self.path == '/api/questions':
            return self.send(200, question_queues())
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

    def account_op(self, op, b):
        cfg = _json(ACCOUNTS, {}).get('accounts', {})
        acc = str(b.get('account', ''))
        if op in ('google-disconnect', 'google-logout'):
            toks = (cfg.get(acc, {}).get('google') or {}).get('tokens', {})
            if not toks:
                raise ValueError('없는 계정입니다')
            if op == 'google-disconnect':
                svc = str(b.get('service', ''))
                if svc not in toks:
                    raise ValueError('없는 서비스입니다')
                account_ops.google_disconnect(acc, svc, toks[svc])
                GSTATE['result'].pop(f'{acc}/{svc}', None)
                return self.send(200, {'ok': True})
            r = account_ops.google_logout(acc, list(toks.values()))
            for svc in toks:
                GSTATE['result'].pop(f'{acc}/{svc}', None)
            return self.send(200, {'ok': True, **r})
        if op in ('browser-logout', 'browser-login'):
            site = str(b.get('site', ''))
            if site not in account_ops.BROWSER:
                raise ValueError('없는 사이트입니다')
            if op == 'browser-logout':
                try:
                    return self.send(200, account_ops.browser_logout(site))
                except axlock.Timeout:
                    raise ValueError('그 사이트 크롬 프로필을 다른 작업이 쓰고 있습니다. 끝난 뒤 다시 하세요')
            key = f'site:{site}'
            if (GSTATE['login'].get(key) or {}).get('state') == '진행 중':
                raise ValueError('이미 로그인 창이 열려 있습니다')
            GSTATE['login'][key] = {'state': '진행 중', 'at': now().isoformat(), 'msg': '로그인 창이 열립니다. 직접 로그인하면 알아서 닫힙니다(최대 10분).'}

            def work():
                try:
                    r = account_ops.browser_login(site)
                    GSTATE['login'][key] = {'state': '완료' if r['ok'] else '실패', 'at': now().isoformat(), 'msg': r['msg']}
                    _safe(site_info)   # 연결되면 채널 정보를 다시 가져온다
                except Exception as e:
                    GSTATE['login'][key] = {'state': '실패', 'at': now().isoformat(), 'msg': str(e)[:200]}
            threading.Thread(target=work, daemon=True).start()
            return self.send(200, {'ok': True})
        if op == 'gh-logout':
            account_ops.gh_logout(str(b.get('user', '')))
            return self.send(200, {'ok': True})
        if op == 'kakao-logout':
            account_ops.kakao_logout()
            return self.send(200, {'ok': True})
        return self.send(404, {'error': '없는 주소'})

    def auth_post(self, op, b):
        ip = self.client_address[0]
        log = (lambda m: axlock.log(f'[시험 서버 {PORT}] {m}')) if os.environ.get('AX_NO_BG') else axlock.log
        if op == 'setup':
            auth.setup(str(b.get('password', '')))
            tok = auth.new_session(self.headers.get('User-Agent', ''))
            log('콘솔 비밀번호를 처음 만들고 로그인')
            return self.send(200, {'ok': True}, headers={'Set-Cookie': auth.set_cookie(tok)})
        if op == 'login':
            if not auth.verify(str(b.get('password', '')), ip):
                log('콘솔 로그인 실패')
                return self.send(401, {'error': '비밀번호가 맞지 않습니다'})
            tok = auth.new_session(self.headers.get('User-Agent', ''))
            log('콘솔 로그인')
            return self.send(200, {'ok': True}, headers={'Set-Cookie': auth.set_cookie(tok)})
        if not self.authed():
            return self.send(401, {'error': '로그인이 필요합니다', 'login': True})
        if op == 'logout':
            auth.drop(self.token())
            log('콘솔 로그아웃')
            return self.send(200, {'ok': True}, headers={'Set-Cookie': auth.clear_cookie()})
        if op == 'password':
            auth.change_password(str(b.get('old', '')), str(b.get('new', '')))
            tok = auth.new_session(self.headers.get('User-Agent', ''))
            log('콘솔 비밀번호 변경(다른 세션 모두 종료)')
            return self.send(200, {'ok': True}, headers={'Set-Cookie': auth.set_cookie(tok)})
        return self.send(404, {'error': '없는 주소'})

    def do_POST(self):
        if not self.same_origin():
            return self.send(403, {'error': '허용되지 않은 요청'})
        try:
            b = self.body()
            parts = self.path.strip('/').split('/')
            if parts[:2] == ['api', 'auth']:
                return self.auth_post(parts[2] if len(parts) > 2 else '', b)
            if not self.authed():
                return self.send(401, {'error': '로그인이 필요합니다', 'login': True})
            if parts[:2] == ['api', 'tasks'] and parts[3:] == ['done']:
                task_done(parts[2], b.get('url'))
                return self.send(200, {'ok': True})
            if parts == ['api', 'incidents', 'check']:
                run_watch()
                return self.send(200, incidents_view())
            if parts == ['api', 'incidents', 'reset']:
                r = watcher.reset()
                axlock.log(f"장애 목록 초기화: {r['moved']}건 보관함으로")
                return self.send(200, {**incidents_view(), 'reset': r})
            if parts[:2] == ['api', 'incidents'] and len(parts) == 4:
                if parts[3] == 'act':
                    incident_act(parts[2], b)
                elif parts[3] == 'analyze':
                    analyze(parts[2])
                else:
                    watcher.set_status(parts[2], {'resolve': 'resolved', 'ignore': 'ignored', 'reopen': 'open'}[parts[3]],
                                       str(b.get('note', ''))[:300])
                return self.send(200, incidents_view())
            if parts == ['api', 'stop']:
                if b.get('on'):
                    axlock.set_stop(str(b.get('reason') or '콘솔에서 정지')[:200], by='콘솔')
                else:
                    axlock.clear_stop(by='콘솔')
                return self.send(200, axlock.status())
            if parts == ['api', 'proposals', 'run']:
                acc = str(b.get('account', ''))
                if acc not in ('dept', 'personal'):
                    raise ValueError('계정을 고르세요')
                run_planner(acc)
                return self.send(200, proposals_view())
            if parts[:2] == ['api', 'proposals'] and len(parts) == 4 and parts[3] in ('accept', 'reject'):
                return self.send(200, prop_decide(parts[2], 'accepted' if parts[3] == 'accept' else 'rejected', str(b.get('reason', ''))))
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
                    try:
                        with axlock.hold(['profile:naver'], job=f'console:naver-check-{cid}', wait=5):
                            r = publish_call(cid, c['account'], 'naver_blog', dry=True)[0]
                    except axlock.Timeout as e:
                        raise ValueError(f'네이버 프로필을 다른 작업이 쓰고 있습니다: {e}')
                    return self.send(200, {'naver_blog': r})
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
            if parts == ['api', 'browser', 'config']:
                return self.send(200, bs_save(b))
            if parts[:2] == ['api', 'browser'] and len(parts) == 3:
                op, prof = parts[2], str(b.get('profile', ''))
                if prof not in BW_PROFILES:
                    raise ValueError('없는 프로필입니다')
                if op == 'start':
                    body = {'profile': prof, 'mode': b.get('mode') or 'headless'}
                    if b.get('owner_pid'):    # 발행 작업이 빌려 쓰기(잠금은 그 작업이 쥐고 있다)
                        body.update(owner_pid=int(b['owner_pid']), extra=b.get('extra') or [])
                    else:
                        body['url'] = b.get('url') or BW_PROFILES[prof][1]
                    return self.send(200, bw_call('/start', body))
                if op == 'stop':
                    return self.send(200, bw_call('/stop', {'profile': prof}))
                if op == 'input':
                    return self.send(200, bw_call('/input', {**b, 'profile': prof}))
                if op == 'login_done':
                    return self.send(200, bw_login_done(prof))
                return self.send(404, {'error': '없는 주소'})
            if parts == ['api', 'secrets']:
                account_ops.save_secret(str(b.get('name', '')).strip(), str(b.get('value', '')))
                return self.send(200, {'ok': True})
            if parts[:2] == ['api', 'account'] and len(parts) == 3:
                return self.account_op(parts[2], b)
            if parts == ['api', 'github', 'switch']:
                github_switch(str(b.get('user', '')))
                return self.send(200, google_view())
            if parts == ['api', 'google', 'login']:
                google_login(str(b.get('account')), str(b.get('service')))
                return self.send(200, google_view())
            if parts[:2] == ['api', 'automations'] and len(parts) == 4 and parts[3] == 'edit':
                return self.send(200, job_edit(parts[2], b))
            if parts[:2] == ['api', 'tasks'] and len(parts) == 4 and parts[3] == 'reschedule':
                return self.send(200, task_reschedule(parts[2], b))
            if parts[:2] == ['api', 'automations'] and len(parts) == 4 and parts[3] in ('on', 'off', 'run'):
                return self.send(200, job_control(parts[2], parts[3], str(b.get('reason', ''))))
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
                    if axlock.stopped() and _is_live(t):
                        raise ValueError('비상 정지 중이라 발행 작업을 실행하지 않습니다')
                    t['_was'] = t['status']
                    save(tasks)
            if parts[3:] == ['run']:
                threading.Thread(target=run_task, args=(t['id'], True), daemon=True).start()
                return self.send(200, {'ok': True})
            self.send(404, {'error': '없는 주소'})
        except (ValueError, KeyError) as e:
            self.send(400, {'error': str(e)})


if __name__ == '__main__':
    auth.internal_key()   # 내부 호출 키를 미리 만든다
    TEST = bool(os.environ.get('AX_NO_BG'))   # 시험용 서버: 실제 데이터를 고치는 일을 하지 않는다
    with LOCK:  # 서버가 꺼진 사이 '실행 중'으로 남은 작업은 실패로 돌린다
        ts = load()
        for t in ts:
            if t.get('status') == 'running' and not TEST:
                t['status'] = 'failed'
        if not TEST:
            save(ts)
    for f in ([] if TEST else CONTENT.glob('*/*/*/meta.json')):
        c = json.loads(f.read_text())
        if c.get('status') == 'drafting':
            c.update(status='idea', error='서버가 다시 켜져 초안 작성이 중단됐습니다')
            f.write_text(json.dumps(c, ensure_ascii=False, indent=2))
    if not TEST:   # 시험용 서버(AX_NO_BG=1)는 예약 실행기·감시기·토큰 확인을 돌리지 않는다
        threading.Thread(target=scheduler, daemon=True).start()
        threading.Thread(target=watch_loop, daemon=True).start()
        threading.Thread(target=google_check_bg, daemon=True).start()
    print(f'AX 발행 콘솔: http://{HOST}:{PORT}')
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()
