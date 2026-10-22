"""AX 오케스트레이터의 잠금·대기·비상 정지 — 모든 자동 작업이 거치는 한 곳.

자원(크롬 프로필, 하루 한도를 함께 쓰는 블로그 등)마다 운영체제 파일 잠금(flock)을 잡는다.
잡은 프로세스가 죽으면 잠금이 저절로 풀린다. 자원은 이름 순서로 잡아 서로 물고 늘어지지 않는다.

실행 스크립트(run_*.sh) 맨 앞의 한 줄이 스크립트 자신을 이 래퍼 아래에서 다시 실행한다.
    [ -z "$AX_LOCKED" ] && exec /usr/bin/python3 /Volumes/USB256/devAPP/AutoSNS/shared/axlock.py run --job naverblog.weekly -- "$0" "$@"

명령줄
    python3 shared/axlock.py run --job <작업> [--res profile:naver ...] [--wait 2400] [--no-stop] -- 명령 …
    python3 shared/axlock.py status          # 잡고 있는 작업·기다리는 작업·비상 정지(JSON)
    python3 shared/axlock.py stop "사유"      # 비상 정지 켜기
    python3 shared/axlock.py resume          # 비상 정지 끄기
    python3 shared/axlock.py skip <작업> <YYYY-MM-DD> [사유]   # 그날 그 작업을 한 번만 건너뛰기

파이썬에서
    from shared.axlock import hold, stopped
    with hold(['profile:naver'], job='console:abcd'):   # 기다렸다가 잡고, 끝나면 푼다
        ...

비상 정지 중에는 발행 작업(계정이 학과·개인인 작업)이 시작하지 않고 건너뛴다. 이미 돌고 있는
작업은 끊지 않는다. 유지보수·보고서(공통 계정) 작업은 계속 돈다.
"""
import datetime
import fcntl
import json
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / 'ax-console' / 'data' / 'locks'
STOP = ROOT / 'ax-console' / 'data' / 'STOP.json'
SKIP = ROOT / 'ax-console' / 'data' / 'skip_once.json'   # {작업: {'date': 'YYYY-MM-DD', 'reason': …}} — 그날 한 번만 건너뛴다
LOG = ROOT / 'ax-console' / 'data' / 'logs' / 'orchestrator.log'
CATALOG = ROOT / 'ax-console' / 'config' / 'automations.json'


def _now():
    return datetime.datetime.now().isoformat(timespec='seconds')


def log(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open('a') as f:
        f.write(f'[{_now()}] {msg}\n')


def _safe(res):
    """자원 이름 → 파일 이름. 한글처럼 바꿔야 하는 글자가 있으면 해시를 붙여 서로 겹치지 않게 한다."""
    out = re.sub(r'[^A-Za-z0-9_.-]', '_', res)
    if out != res:
        import hashlib
        out += '-' + hashlib.sha1(res.encode()).hexdigest()[:8]
    return out


def _alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


# ---- 비상 정지 ----
def stopped():
    try:
        return json.loads(STOP.read_text())
    except (OSError, ValueError):
        return None


def set_stop(reason, by='사람'):
    STOP.parent.mkdir(parents=True, exist_ok=True)
    STOP.write_text(json.dumps({'at': _now(), 'reason': reason or '사유 없음', 'by': by}, ensure_ascii=False))
    log(f'비상 정지 켬 ({by}): {reason}')


def clear_stop(by='사람'):
    if STOP.exists():
        STOP.unlink()
        log(f'비상 정지 끔 ({by})')


# ---- 카카오톡 '나에게' 알림 ----
def kakao(text):
    """실패 알림. 스스로 알리지 않는 작업만 automations.json 의 notify_fail 로 켠다. 실패해도 작업 결과는 바꾸지 않는다."""
    try:
        nb = ROOT / 'channels' / 'naver-blog-auto'
        r = subprocess.run([str(nb / '.venv' / 'bin' / 'python'), str(nb / 'kakao_notify.py'), text[:190]],
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            log(f'카카오 알림 실패: {(r.stderr or r.stdout).strip()[-120:]}')
    except Exception as e:  # noqa: BLE001
        log(f'카카오 알림 실패: {type(e).__name__}: {e}')


# ---- 작업 정보 ----
def job_info(job):
    try:
        for j in json.loads(CATALOG.read_text()).get('jobs', []):
            if j['job'] == job:
                return j
    except (OSError, ValueError):
        pass
    return {}


def resources_for(job, extra=()):
    info = job_info(job)
    res = set(info.get('locks', [])) | set(extra)
    res.add(f'job:{job}')            # 같은 작업이 겹쳐 두 번 돌지 않게
    return sorted(res)


def is_publish(job):
    return job_info(job).get('account', 'dept') != 'common'


# ---- 잠금 ----
class Timeout(Exception):
    pass


def _try(res, holder):
    DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(DIR / f'{_safe(res)}.lock', os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    (DIR / f'{_safe(res)}.json').write_text(json.dumps({'resource': res, **holder}, ensure_ascii=False))
    return fd


def _release(fds):
    for res, fd in fds:
        try:
            (DIR / f'{_safe(res)}.json').unlink()
        except OSError:
            pass
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def holder_of(res):
    try:
        h = json.loads((DIR / f'{_safe(res)}.json').read_text())
        return h if _alive(h.get('pid')) else None
    except (OSError, ValueError):
        return None


def _profile_busy_outside(res):
    """잠금을 거치지 않은 바깥 도구(Codex 자동화 등)가 같은 크롬 프로필을 쓰고 있는지."""
    if not res.startswith('profile:'):
        return False
    path = PROFILES.get(res[len('profile:'):])
    if not path:
        return False
    for cand in {path, path.replace('/GeoAI_NA/naver-blog-auto/', '/naver-blog-auto/')}:  # 링크 경로로 띄운 경우도
        r = subprocess.run(['pgrep', '-f', f'user-data-dir={re.escape(cand)}( |$)'], capture_output=True)
        if r.returncode == 0:
            return True
    return False


def acquire(resources, job, wait=2400, poll=5):
    """자원을 모두 잡을 때까지 기다린다. 못 잡으면 Timeout. 잡은 [(자원, fd)] 를 돌려준다."""
    holder = {'job': job, 'pid': os.getpid(), 'since': _now()}
    wfile = DIR / 'waiting' / f'{os.getpid()}.json'
    wfile.parent.mkdir(parents=True, exist_ok=True)
    t0, said = time.time(), False
    try:
        while True:
            got, busy = [], None
            for res in sorted(resources):
                if _profile_busy_outside(res) and not holder_of(res):
                    busy = f'{res}(잠금 밖 프로세스)'
                    break
                fd = _try(res, holder)
                if fd is None:
                    h = holder_of(res)
                    busy = f"{res}({h['job'] if h else '?'})"
                    break
                got.append((res, fd))
            if busy is None:
                if said:
                    log(f'{job}: 기다린 끝에 잡음 {resources} ({int(time.time() - t0)}초)')
                return got
            _release(got)
            if not said:
                log(f'{job}: 기다림 — {busy} 사용 중')
                said = True
            wfile.write_text(json.dumps({'job': job, 'pid': os.getpid(), 'since': holder['since'],
                                         'resources': resources, 'blocked_by': busy}, ensure_ascii=False))
            if time.time() - t0 >= wait:
                raise Timeout(f"{f'{wait // 60}분' if wait >= 60 else f'{wait}초'} 기다려도 {busy} 가 비지 않음")
            time.sleep(max(0.5, min(poll, wait - (time.time() - t0))))
    finally:
        try:
            wfile.unlink()
        except OSError:
            pass


@contextmanager
def hold(resources, job, wait=2400):
    fds = acquire(resources, job, wait)
    try:
        yield
    finally:
        _release(fds)


def status():
    out = {'stop': stopped(), 'holding': [], 'waiting': []}
    for f in sorted(DIR.glob('*.json')):
        try:
            h = json.loads(f.read_text())
        except ValueError:
            continue
        if _alive(h.get('pid')):
            out['holding'].append(h)
    for f in sorted((DIR / 'waiting').glob('*.json')):
        try:
            w = json.loads(f.read_text())
        except ValueError:
            continue
        if _alive(w.get('pid')):
            out['waiting'].append(w)
        else:
            f.unlink(missing_ok=True)
    return out


# 크롬 프로필 이름 → 폴더(잠금 밖 프로세스 감지용)
PROFILES = {
    'naver': str(ROOT / 'channels' / 'naver-blog-auto' / 'chrome-profile'),
    'safeworking': str(ROOT / 'channels' / 'naver-blog-auto' / 'chrome-profile-safeworking'),   # 개인 네이버 블로그
    'tistory': str(ROOT / 'GeoAI_NA' / 'naver-blog-auto' / 'chrome-profile-tistory'),
    'insta': str(ROOT / 'channels' / 'insta-cardnews' / 'chrome-profile-insta'),
    'tiktok': str(ROOT / 'channels' / 'youtube-shorts-auto' / 'chrome-profile-tiktok'),
    'youtube-personal': str(ROOT / 'channels' / 'youtube-shorts-auto' / 'chrome-profile-youtube'),
    'youtube-dept': str(ROOT / 'channels' / 'youtube-shorts-auto' / 'chrome-profile-youtube-dept'),
    'insta-manual': str(ROOT / 'channels' / 'insta-manual' / 'chrome-profile'),
    'scratch': str(ROOT / 'ax-console' / 'data' / 'browser-scratch'),   # 콘솔 내부 브라우저용 빈 프로필
}


def set_skip(job, date, reason='', by='명령줄'):
    """그 날짜에 그 작업의 실행을 한 번 건너뛴다(그날 첫 실행이 건너뛰고 기록은 지워진다)."""
    d = json.loads(SKIP.read_text()) if SKIP.exists() else {}
    d[job] = {'date': date, 'reason': reason, 'by': by, 'at': _now()}
    SKIP.write_text(json.dumps(d, ensure_ascii=False, indent=2))
    log(f'{job}: {date} 한 번 건너뛰기 등록 ({by}) — {reason}')


def take_skip(job):
    """오늘 건너뛸 차례면 그 기록(지움)을, 아니면 None. 지난 날짜 기록은 지운다."""
    try:
        d = json.loads(SKIP.read_text())
    except (OSError, ValueError):
        return None
    e = d.get(job)
    if not e:
        return None
    today = datetime.date.today().isoformat()
    if e.get('date') > today:
        return None
    d.pop(job)
    SKIP.write_text(json.dumps(d, ensure_ascii=False, indent=2))
    return e if e.get('date') == today else None


def main(argv):
    if not argv or argv[0] == 'status':
        print(json.dumps(status(), ensure_ascii=False, indent=2))
        return 0
    if argv[0] == 'stop':
        set_stop(' '.join(argv[1:]), by='명령줄')
        return 0
    if argv[0] == 'resume':
        clear_stop(by='명령줄')
        return 0
    if argv[0] == 'skip' and len(argv) >= 3:      # axlock.py skip <작업> <YYYY-MM-DD> [사유]
        set_skip(argv[1], argv[2], ' '.join(argv[3:]))
        return 0
    if argv[0] != 'run' or '--' not in argv:
        print(__doc__)
        return 2
    opts, cmd = argv[1:argv.index('--')], argv[argv.index('--') + 1:]
    job, extra, wait, check_stop = 'manual', [], 2400, True
    i = 0
    while i < len(opts):
        if opts[i] == '--job':
            job, i = opts[i + 1], i + 2
        elif opts[i] == '--res':
            extra.append(opts[i + 1])
            i += 2
        elif opts[i] == '--wait':
            wait, i = int(opts[i + 1]), i + 2
        elif opts[i] == '--no-stop':
            check_stop, i = False, i + 1
        else:
            i += 1
    st = stopped()
    if check_stop and st and is_publish(job):
        log(f"{job}: 비상 정지 중이라 건너뜀 ({st.get('reason')})")
        print(f"[{_now()}] 비상 정지 중이라 건너뜁니다: {st.get('reason')}")
        return 0
    sk = take_skip(job)
    if sk:
        log(f"{job}: 오늘 한 번 건너뛰기로 등록돼 건너뜀 ({sk.get('reason', '')})")
        print(f"[{_now()}] 오늘 한 번 건너뛰기로 등록돼 건너뜁니다: {sk.get('reason', '')}")
        return 0
    res = resources_for(job, extra)
    try:
        fds = acquire(res, job, wait)
    except Timeout as e:
        log(f'{job}: 건너뜀 — {e}')
        print(f'[{_now()}] {job}: 건너뜀 — {e}')
        return 75
    log(f'{job}: 시작 {res}')
    t0 = time.time()
    try:
        code = subprocess.call(cmd, env={**os.environ, 'AX_LOCKED': '1', 'AX_JOB': job})
    finally:
        _release(fds)
    log(f'{job}: 끝 (코드 {code}, {int(time.time() - t0)}초)')
    if code != 0 and os.environ.get('AX_DRY') != '1' and job_info(job).get('notify_fail'):
        kakao(f"[AX] 작업 실패: {job} (코드 {code}, {int(time.time() - t0)}초). 콘솔 '자동 작업' 탭에서 기록을 확인하세요.")
    return code


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
