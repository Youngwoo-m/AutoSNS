"""실패 대응 ① 감시기 — 모델 없이 규칙으로 실패·멈춤을 찾아 '사건'으로 묶는다.

콘솔 서버가 10분마다 부른다(check()). 보는 신호:
  log       작업 로그의 실패 문구(새로 쓰인 부분만). 글은 나갔고 일부만 빠진 것은 '경고'
  missed    예정 시각 + 40분이 지났는데 로그가 그 뒤로 안 바뀜(작업이 아예 안 돎)
  unloaded  launchd 에서 사라짐(사용자가 끈 이유 note 가 없을 때만)
  shot      실패 스크린샷(*fail*, no_*_box …)이 새로 생김
  console   콘솔 예약·자동 발행 작업 실패
  lock      오케스트레이터가 기다리다 건너뜀
  env       USB 미장착, 디스크 여유 부족
같은 작업·같은 문구(숫자·시각을 지운 것)는 하나의 사건으로 묶고 횟수·마지막 시각만 늘린다.
사건: data/incidents/<YYYY-MM>/<id>.json, 상태: data/incidents/state.json
"""
import datetime
import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
from pathlib import Path

CONSOLE = Path(__file__).resolve().parents[1]
ROOT = CONSOLE.parent
DIR = CONSOLE / 'data' / 'incidents'
STATE = DIR / 'state.json'
AGENTS = Path.home() / 'Library' / 'LaunchAgents'
CATALOG = CONSOLE / 'config' / 'automations.json'

FAIL = re.compile(r'실패|오류|Traceback|Error|예외|SystemExit|No space|찾지 못했|로그인 세션이 만료|비밀번호를 묻|이번 회차를 건너뜀|기다려도 .*비지 않')
# 글은 나갔고 일부만 빠진 경우·의도된 건너뜀 → 경고(또는 무시)
WARN = re.compile(r'글은 정상|없이 진행|유튜브는 정상|네이버는 정상|실패 무시|건너뜀\(|다음 실행에서 다시|^\s*(\[[\d: -]+\]\s*)?\[[^\]]*오류\]\s*https?')
IGNORE = re.compile(r'^\s*(File "|\^+|Traceback \(most recent call last\):|raise |return |self\.|During handling)|'
                    r'쓰레드 건너뜀: 아침 회차|오늘 이미 .*건너뜁|DRY|dry_run|미리 보기|실패 0[편건개]?(\D|$)')
TS = re.compile(r'^\[(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})\]')
SHOT = re.compile(r'(fail|no_caption_box|no_file_input|not_logged_in|unconfirmed|error)', re.I)
GRACE_MIN = 40


def now():
    return datetime.datetime.now().replace(microsecond=0)


def _load(p, default):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return default


def _save(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2))
    tmp.replace(p)


def signature(text):
    t = TS.sub('', text)
    t = re.sub(r'https?://\S+', 'URL', t)
    t = re.sub(r'[\w./-]+\.(mp4|png|jpg|json|log|py)\b', 'FILE', t)
    t = re.sub(r'\d+', 'N', t)
    return re.sub(r'\s+', ' ', t).strip(' =-:')[:90]


# ---- 사건 저장 ----
def _iid(job, kind, sig):
    return hashlib.sha1(f'{job}|{kind}|{sig}'.encode()).hexdigest()[:10]


def incident_path(iid):
    hits = list(DIR.glob(f'*/{iid}.json'))
    return hits[0] if hits else DIR / now().strftime('%Y-%m') / f'{iid}.json'


def record(job, kind, severity, sig, evidence, at=None):
    """사건을 만들거나(같은 것이 열려 있으면) 횟수·근거를 덧붙인다. 새로 만들었으면 True."""
    iid = _iid(job, kind, sig)
    p = incident_path(iid)
    at = at or now().isoformat()
    inc = _load(p, None)
    if inc is None and iid in _load(STATE, {}).get('ignored_ids', []):
        return False     # 초기화 전에 '무시'한 문구
    new = inc is None or inc.get('status') in ('resolved',) and inc.get('resolved_at', '') < at
    if inc and inc.get('status') == 'ignored':
        return False
    if new:
        info = catalog().get(job, {})
        inc = {'id': iid, 'job': job, 'name': info.get('name', job), 'account': info.get('account', ''),
               'channels': info.get('channels', []), 'kind': kind, 'severity': severity, 'signature': sig,
               'first': at, 'last': at, 'count': 0, 'status': 'open', 'evidence': [], 'analysis': None,
               'history': [{'at': now().isoformat(), 'what': '감시기가 찾음'}]}
    if inc['status'] == 'resolved':
        inc['status'] = 'open'
        inc['history'].append({'at': now().isoformat(), 'what': '해결 뒤 다시 발생'})
    inc['count'] += 1
    inc['last'] = max(inc['last'], at)
    if severity == 'error':
        inc['severity'] = 'error'
    ev = evidence if isinstance(evidence, dict) else {'text': str(evidence)}
    inc['evidence'] = (inc['evidence'] + [{'at': at, **ev}])[-15:]
    _save(p, inc)
    return new


def incidents(status=None):
    out = [_load(f, None) for f in DIR.glob('*/*.json')]
    out = [x for x in out if x and (not status or x['status'] == status)]
    return sorted(out, key=lambda x: (x['status'] != 'open', x['last']), reverse=False)


# ---- 작업 정보 ----
def catalog():
    return {j['job']: j for j in _load(CATALOG, {}).get('jobs', [])}


def plist(job):
    try:
        return plistlib.loads((AGENTS / f'com.smuds.{job}.plist').read_bytes())
    except Exception:
        return {}


def job_logs(pl, job=None):
    files = [pl.get('StandardOutPath'), pl.get('StandardErrorPath')]
    files += [str(ROOT / x) for x in catalog().get(job, {}).get('logs', [])]
    script = Path(pl.get('ProgramArguments', [''])[-1])
    try:
        if script.suffix == '.sh':
            for m in re.findall(r'((?:\.\./)?logs/[\w.\-]+\.log)', script.read_text(errors='ignore')):
                files.append(str((script.resolve().parent / m).resolve()))
    except OSError:
        pass
    return sorted({f for f in files if f and os.path.exists(f)})


def _next_times(iv, start, end):
    ivs = iv if isinstance(iv, list) else [iv]
    out, d = [], start.date()
    while d <= end.date():
        for i in ivs:
            if 'Weekday' in i and d.isoweekday() % 7 != i['Weekday'] % 7:
                continue
            if 'Day' in i and d.day != i['Day']:
                continue
            for h in ([i['Hour']] if 'Hour' in i else range(24)):
                t = datetime.datetime.combine(d, datetime.time(h, i.get('Minute', 0)))
                if start < t <= end:
                    out.append(t)
        d += datetime.timedelta(days=1)
    return sorted(out)


# ---- 신호별 점검 ----
def check_logs(state, first_run):
    found = 0
    offs = state.setdefault('offsets', {})
    cutoff = (now() - datetime.timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
    for job in catalog():
        if catalog()[job].get('note'):
            continue  # 사용자가 일부러 끈 작업
        for f in job_logs(plist(job), job):
            size = os.path.getsize(f)
            start = offs.get(f, 0)
            if start > size:          # 로그가 새로 시작됨(잘림·교체)
                start = 0
            if first_run and f not in offs:
                start = max(0, size - 400_000)   # 처음엔 끝부분만 보고 24시간 안 것만
            with open(f, 'rb') as fh:
                fh.seek(start)
                chunk = fh.read().decode('utf-8', 'ignore')
            offs[f] = size
            ts = None
            for ln in chunk.splitlines():
                m = TS.match(ln)
                if m:
                    ts = m.group(1).replace('T', ' ')
                if first_run and (not ts or ts < cutoff):
                    continue
                if not FAIL.search(ln) or IGNORE.search(ln):
                    continue
                sev = 'warn' if WARN.search(ln) else 'error'
                at = (ts or now().isoformat()).replace(' ', 'T')
                found += record(job, 'log', sev, signature(ln),
                                {'text': ln.strip()[:400], 'file': str(Path(f).relative_to(ROOT)) if str(f).startswith(str(ROOT)) else f}, at)
    return found


def check_missed(state):
    found = 0
    last = state.get('missed_checked')
    end = now() - datetime.timedelta(minutes=GRACE_MIN)
    start = datetime.datetime.fromisoformat(last) if last else end - datetime.timedelta(hours=24)
    loaded = subprocess.run(['launchctl', 'list'], capture_output=True, text=True).stdout
    for job, info in catalog().items():
        pl = plist(job)
        iv = pl.get('StartCalendarInterval')
        if not iv or info.get('note') or info.get('quiet') or f'com.smuds.{job}' not in loaded:
            continue
        logs = job_logs(pl, job)
        mt = max((os.path.getmtime(f) for f in logs), default=0)
        for t in _next_times(iv, start, end):
            if mt < t.timestamp():
                found += record(job, 'missed', 'error', f'{t:%H:%M} 예정 실행 흔적 없음',
                                {'text': f'{t:%m-%d %H:%M} 예정이었는데 {GRACE_MIN}분이 지나도 로그가 바뀌지 않음'
                                         + (f' (마지막 기록 {datetime.datetime.fromtimestamp(mt):%m-%d %H:%M})' if mt else '')},
                                t.isoformat())
    state['missed_checked'] = end.isoformat()
    return found


def check_unloaded():
    found = 0
    loaded = subprocess.run(['launchctl', 'list'], capture_output=True, text=True).stdout
    for job, info in catalog().items():
        if (AGENTS / f'com.smuds.{job}.plist').exists() and f'com.smuds.{job}' not in loaded and not info.get('note'):
            found += record(job, 'unloaded', 'error', 'launchd 에서 내려감',
                            {'text': '작업이 launchd 에 올라가 있지 않고, 끈 이유(note)도 없음'})
    return found


SHOT_JOB = {'tiktok': 'tiktok.queue', 'tistory': 'tistory', 'insta': 'instacards.weekly', 'reel': 'ytshorts.weekly',
            'threads': 'geoai.evening', 'buddy': 'naverbuddy.weekly', 'jobs': 'naverjobs.weekly'}


def check_shots(state):
    found = 0
    seen = state.setdefault('shot_mtime', 0)
    newest = seen
    cat = catalog()
    dirs = {Path(f).parent.resolve(): j for j in cat for f in job_logs(plist(j), j)}
    done = set()
    for d, owner in dirs.items():
        for f in d.glob('*.png'):
            rf = f.resolve()
            mt = rf.stat().st_mtime
            if rf in done or mt <= seen or not SHOT.search(f.name):
                continue
            done.add(rf)
            newest = max(newest, mt)
            if now().timestamp() - mt > 86400:
                continue
            job = next((j for k, j in SHOT_JOB.items() if k in f.name.lower()), owner)
            if cat.get(job, {}).get('note'):
                continue
            kind = re.sub(r'^\d+_\d+_', '', f.stem)
            found += record(job, 'shot', 'error', f'실패 화면: {kind}',
                            {'text': f'실패 스크린샷 {f.name}', 'screenshot': str(rf)},
                            datetime.datetime.fromtimestamp(mt).isoformat(timespec='seconds'))
    state['shot_mtime'] = newest
    return found


def check_console(state):
    found = 0
    done = set(state.setdefault('console_seen', []))
    for t in _load(CONSOLE / 'data' / 'tasks.json', []):
        key = f"{t['id']}:{len(t.get('runs', []))}"
        if t.get('status') == 'failed' and key not in done:
            r = t.get('result') or {}
            found += record(f"console:{t['account']}/{t['channel']}", 'console', 'error',
                            signature(r.get('detail') or (t.get('runs') or [{}])[0].get('tail', '실패')),
                            {'text': f"{t['title']}: {r.get('detail') or (t.get('runs') or [{}])[0].get('tail', '')}"[:400]})
            done.add(key)
    state['console_seen'] = sorted(done)[-500:]
    return found


def check_lock(state):
    found = 0
    log = CONSOLE / 'data' / 'logs' / 'orchestrator.log'
    if not log.exists():
        return 0
    size, start = log.stat().st_size, state.get('lock_off', 0)
    with open(log, 'rb') as fh:
        fh.seek(start if start <= size else 0)
        chunk = fh.read().decode('utf-8', 'ignore')
    state['lock_off'] = size
    for ln in chunk.splitlines():
        m = re.match(r'^\[(\S+)\] (\S+): 건너뜀 — (.*)', ln)
        if m and not m.group(2).startswith(('t', '시험', 'console:naver-check')):
            found += record(m.group(2), 'lock', 'error', signature('기다리다 건너뜀 ' + re.sub(r'\(.*?\)', '', m.group(3))),
                            {'text': ln[:300]}, m.group(1))
    return found


def check_env():
    found = 0
    if not Path('/Volumes/USB256').exists():
        found += record('env', 'env', 'error', 'USB256 미장착', {'text': '/Volumes/USB256 이 없음 — 모든 작업이 실패한다'})
    for path, need, name in (('/', 5, '내장 디스크'), ('/Volumes/USB256', 10, 'USB256')):
        try:
            free = shutil.disk_usage(path).free / 1e9
        except OSError:
            continue
        if free < need:
            found += record('env', 'env', 'error', f'{name} 여유 부족',
                            {'text': f'{name} 여유 {free:.1f}GB (기준 {need}GB)'})
    return found


def check():
    DIR.mkdir(parents=True, exist_ok=True)
    state = _load(STATE, {})
    first = not state.get('checked')
    counts = {}
    for name, fn in (('log', lambda: check_logs(state, first)), ('missed', lambda: check_missed(state)),
                     ('unloaded', check_unloaded), ('shot', lambda: check_shots(state)),
                     ('console', lambda: check_console(state)), ('lock', lambda: check_lock(state)), ('env', check_env)):
        try:
            counts[name] = fn()
        except Exception as e:  # 한 신호가 깨져도 나머지는 본다
            counts[name] = f'점검 오류: {type(e).__name__}: {str(e)[:120]}'
    state['checked'] = now().isoformat()
    state['last_counts'] = counts
    _save(STATE, state)
    return counts


def set_status(iid, status, note=''):
    p = incident_path(iid)
    inc = _load(p, None)
    if not inc:
        raise ValueError('사건을 찾지 못했습니다')
    inc['status'] = status
    if status == 'resolved':
        inc['resolved_at'] = now().isoformat()
    inc['history'].append({'at': now().isoformat(), 'what': {'resolved': '해결로 표시', 'ignored': '무시(같은 문구는 다시 안 띄움)',
                                                          'open': '다시 열기'}.get(status, status) + (f' — {note}' if note else '')})
    _save(p, inc)
    return inc


def add_history(iid, what):
    p = incident_path(iid)
    inc = _load(p, None)
    if not inc:
        raise ValueError('사건을 찾지 못했습니다')
    inc['history'].append({'at': now().isoformat(), 'what': what})
    _save(p, inc)
    return inc


def reset():
    """장애 목록 초기화 — 지우지 않고 archive/<시각>/ 으로 옮긴다. 로그 읽은 위치(state)는 그대로 두어
    지난 로그 줄이 다시 사건이 되지 않게 하고, '무시'한 문구는 계속 무시한다."""
    files = [f for f in DIR.glob('*/*.json') if f.parent.name != 'archive']
    if not files:
        return {'moved': 0}
    dest = DIR / 'archive' / now().strftime('%Y%m%d-%H%M%S')
    dest.mkdir(parents=True, exist_ok=True)
    st = _load(STATE, {})
    ign = set(st.get('ignored_ids', []))
    for f in files:
        x = _load(f, None)
        if x and x.get('status') == 'ignored':
            ign.add(x['id'])
        f.replace(dest / f.name)
    st['ignored_ids'] = sorted(ign)
    _save(STATE, st)
    return {'moved': len(files), 'archive': str(dest.relative_to(CONSOLE))}


if __name__ == '__main__':
    print(json.dumps(check(), ensure_ascii=False))
    for x in incidents('open')[:40]:
        print(x['severity'], x['kind'], x['job'], x['count'], x['last'][5:16], '|', x['signature'][:70])
