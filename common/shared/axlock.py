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
import hashlib
import tempfile
import threading
import uuid
import fcntl
import json
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DIR = ROOT / 'ax-console' / 'data' / 'locks'
STOP = ROOT / 'ax-console' / 'data' / 'STOP.json'
SKIP = ROOT / 'ax-console' / 'data' / 'skip_once.json'   # {작업: {'date': 'YYYY-MM-DD', 'reason': …}} — 그날 한 번만 건너뛴다
LOG = ROOT / 'ax-console' / 'data' / 'logs' / 'orchestrator.log'
CATALOG = ROOT / 'ax-console' / 'config' / 'automations.json'


def _now():
    return datetime.datetime.now().isoformat(timespec='seconds')


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


# ---- 잠금 ----
class Timeout(Exception):
    pass


# 크롬 프로필 이름 → 폴더(잠금 밖 프로세스 감지용)
# 2026-10-28 사용자 지정: 서비스별 프로필 8개를 계정별 로그인 브라우저 2개로 합쳤다.
# 옛 chrome-profile* 폴더는 이 두 폴더를 가리키는 심볼릭 링크다(원본은 *.bak-20261028 로 보관).
LOGIN_DIRS = {
    'personal': str(Path.home() / '.autosns-login' / 'personal'),   # 개인: 개인 네이버·티스토리·개인 유튜브(블로거)
    'dept': str(Path.home() / '.autosns-login' / 'dept'),           # 학과: 학과 네이버·유튜브·틱톡·인스타
}
ACCOUNT_OF = {
    'naver': 'dept', 'insta': 'dept', 'tiktok': 'dept', 'youtube-dept': 'dept', 'insta-manual': 'dept',
    'safeworking': 'personal', 'tistory': 'personal', 'youtube-personal': 'personal',
}
# 링크 경로로 띄운 크롬도 같은 폴더로 보고 잡는다
_LINKS = {
    'naver': 'dept/naver-blog-auto/chrome-profile', 'safeworking': 'dept/naver-blog-auto/chrome-profile-safeworking',
    'tistory': 'personal/naver-blog-auto/chrome-profile-tistory', 'insta': 'dept/insta-cardnews/chrome-profile-insta',
    'tiktok': 'dept/youtube-shorts-auto/chrome-profile-tiktok', 'youtube-personal': 'dept/youtube-shorts-auto/chrome-profile-youtube',
    'youtube-dept': 'dept/youtube-shorts-auto/chrome-profile-youtube-dept', 'insta-manual': 'dept/insta-manual/chrome-profile',
}
PROFILES = {k: LOGIN_DIRS[a] for k, a in ACCOUNT_OF.items()}
PROFILES['scratch'] = str(ROOT / 'ax-console' / 'data' / 'browser-scratch')   # 콘솔 내부 브라우저용 빈 프로필


def _canon(res):
    """같은 로그인 폴더를 쓰는 profile:* 자원은 계정 하나의 잠금으로 묶는다(한 폴더를 크롬 둘이 열지 않게)."""
    if res.startswith('profile:') and res[len('profile:'):] in ACCOUNT_OF:
        return 'profile:acct-' + ACCOUNT_OF[res[len('profile:'):]]
    return res


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
        fds = _default().acquire(res, job, wait, check_stop=check_stop and is_publish(job))
    except (Timeout, ControlBlocked) as e:
        log(f'{job}: 건너뜀 — {e}')
        print(f'[{_now()}] {job}: 건너뜀 — {e}')
        return 75
    log(f'{job}: 시작 {res}')
    t0 = time.monotonic()
    try:
        code = subprocess.call(cmd, env={**os.environ, 'AX_LOCKED': '1', 'AX_JOB': job})
    finally:
        _release(fds)
    log(f'{job}: 끝 (코드 {code}, {int(time.monotonic() - t0)}초)')
    if code != 0 and os.environ.get('AX_DRY') != '1' and job_info(job).get('notify_fail'):
        kakao(f"[AX] 작업 실패: {job} (코드 {code}, {int(time.monotonic() - t0)}초). 콘솔 '자동 작업' 탭에서 기록을 확인하세요.")
    return code


@dataclass(frozen=True)
class LockPaths:
    root: Path
    lock_dir: Path
    stop: Path
    skip: Path
    log: Path
    catalog: Path

    @classmethod
    def from_root(cls, source_root):
        root = Path(source_root).resolve()
        data = root / 'ax-console' / 'data'
        return cls(root, data / 'locks', data / 'STOP.json', data / 'skip_once.json',
                   data / 'logs' / 'orchestrator.log', root / 'ax-console' / 'config' / 'automations.json')


class ControlBlocked(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def read_control_state(paths, process_probe=None):
    """순수 관측. STOP 읽기 실패는 clear로 취급하지 않는다."""
    probe = process_probe or _alive
    state, version, stop = 'clear', 'clear', None
    try:
        raw = paths.stop.read_bytes()
    except FileNotFoundError:
        pass
    except OSError:
        state, version = 'unknown', None
    else:
        version = hashlib.sha256(raw).hexdigest()
        try:
            stop = json.loads(raw)
            if not isinstance(stop, dict) or not isinstance(stop.get('reason'), str) or not isinstance(stop.get('at'), str):
                raise ValueError('invalid STOP')
            state = 'stopped'
        except (ValueError, UnicodeError):
            state, stop = 'unknown', None
    result = {'state': state, 'version': version, 'stop': stop, 'holding': [], 'waiting': []}
    for folder, key in ((paths.lock_dir, 'holding'), (paths.lock_dir / 'waiting', 'waiting')):
        for file in sorted(folder.glob('*.json')):
            try:
                item = json.loads(file.read_bytes())
                if isinstance(item, dict) and probe(item.get('pid')):
                    result[key].append(item)
            except (OSError, ValueError, UnicodeError, TypeError):
                continue
    return result


class AxLock:
    def __init__(self, paths, process_probe=None):
        self.paths = paths
        self.process_probe = process_probe
        self._owned_locks = {}

    def _check_control(self, resources):
        if resources == ['control:publish-gate']:
            return
        state = read_control_state(self.paths)['state']
        if state != 'clear':
            raise ControlBlocked('control_' + state)

    def status(self):
        observed = read_control_state(self.paths)
        stop = observed['stop']
        if observed['state'] == 'unknown':
            stop = {'reason': 'control_unknown', 'state': 'unknown'}
        return {'stop': stop, 'holding': observed['holding'],
                'waiting': observed['waiting'], 'control': observed}

    def stopped(self):
        observed = read_control_state(self.paths)
        if observed['state'] == 'unknown':
            return {'reason': 'control_unknown', 'state': 'unknown'}
        return observed['stop']

    def set_stop(self, reason, by='사람'):
        with self.hold(['control:publish-gate'], job='control:stop'):
            self.paths.stop.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix='.STOP-', dir=self.paths.stop.parent)
            try:
                with os.fdopen(fd, 'w') as stream:
                    json.dump({'at': _now(), 'reason': reason or '사유 없음', 'by': by, 'event_id': uuid.uuid4().hex}, stream, ensure_ascii=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, self.paths.stop)
                directory_fd = os.open(self.paths.stop.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            finally:
                Path(name).unlink(missing_ok=True)
            return read_control_state(self.paths)

    def clear_stop(self, expected_version, by='사람'):
        with self.hold(['control:publish-gate'], job='control:resume'):
            current = read_control_state(self.paths)
            if current['state'] == 'unknown':
                raise ControlBlocked('control_unknown')
            if expected_version != current['version']:
                raise ControlBlocked('control_version_conflict')
            self.paths.stop.unlink(missing_ok=True)
            return read_control_state(self.paths)

    def log(self, msg):
        self.paths.log.parent.mkdir(parents=True, exist_ok=True)
        with self.paths.log.open('a') as f:
            f.write(f'[{_now()}] {msg}\n')

    def job_info(self, job):
        try:
            for j in json.loads(self.paths.catalog.read_text()).get('jobs', []):
                if j['job'] == job:
                    return j
        except (OSError, ValueError):
            pass
        return {}

    def resources_for(self, job, extra=()):
        info = self.job_info(job)
        res = set(info.get('locks', [])) | set(extra)
        res.add(f'job:{job}')            # 같은 작업이 겹쳐 두 번 돌지 않게
        return sorted(res)

    def is_publish(self, job):
        return self.job_info(job).get('account', 'dept') != 'common'

    def _try(self, res, holder):
        self.paths.lock_dir.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.paths.lock_dir / f'{_safe(res)}.lock', os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return None
        try:
            (self.paths.lock_dir / f'{_safe(res)}.json').write_text(json.dumps({'resource': res, **holder}, ensure_ascii=False))
        except BaseException:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
            raise
        self._owned_locks[res] = (fd, os.getpid(), threading.get_ident())
        return fd

    def _release(self, fds):
        for res, fd in fds:
            owned = self._owned_locks.get(res)
            if owned and owned[0] == fd:
                self._owned_locks.pop(res, None)
            try:
                (self.paths.lock_dir / f'{_safe(res)}.json').unlink()
            except OSError:
                pass
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def verify_descriptor(self, res, fd):
        """등록 파일과 같은 열린 description이 실제 배타 flock을 보유하는지 확인한다.

        별도 FD의 busy 관측만으로 소유자를 추정하지 않는다. 상속 FD의 같은
        description 재확인까지 성공해야 한다. 새 잠금을 얻는 API가 아니다.
        """
        if type(fd) is not int or fd < 3:
            raise ValueError('invalid_lock_descriptor')
        res = _canon(res)
        path = self.paths.lock_dir / f'{_safe(res)}.lock'
        if path.is_symlink():
            raise ValueError('invalid_lock_descriptor')
        info, target = os.fstat(fd), path.stat()
        if (info.st_dev, info.st_ino) != (target.st_dev, target.st_ino):
            raise ValueError('invalid_lock_descriptor')
        probe = os.open(path, os.O_RDWR)
        try:
            try:
                fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                pass
            else:
                fcntl.flock(probe, fcntl.LOCK_UN)
                raise ValueError('lock_not_held')
            # 다른 owner만 보유했으면 supplied FD에서는 실패한다. 상속된 동일
            # description의 재확인은 기존 잠금과 충돌하지 않는다.
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(probe)
        return True

    def owned_descriptor(self, res):
        """이 객체가 현재 프로세스에서 획득하고 아직 해제하지 않은 실제 FD."""
        res = _canon(res)
        owned = self._owned_locks.get(res)
        if not owned or owned[1] != os.getpid():
            raise ValueError('lock_not_owned')
        self.verify_descriptor(res, owned[0])
        return owned[0]

    @contextmanager
    def publication_guard(self, *, job, wait=10):
        """이미 같은 thread가 보유한 gate에는 중첩 flock을 요청하지 않는다."""
        owned = self._owned_locks.get('control:publish-gate')
        if owned and owned[1:] == (os.getpid(), threading.get_ident()):
            self.verify_descriptor('control:publish-gate', owned[0])
            yield
            return
        with self.hold(['control:publish-gate'], job=job, wait=wait):
            yield

    def holder_of(self, res):
        try:
            h = json.loads((self.paths.lock_dir / f'{_safe(res)}.json').read_text())
            return h if _alive(h.get('pid')) else None
        except (OSError, ValueError):
            return None

    def _profile_busy_outside(self, res):
        """잠금을 거치지 않은 바깥 도구(Codex 자동화·사용자가 열어 둔 로그인 브라우저 등)가 같은 크롬 프로필을 쓰고 있는지."""
        if self.process_probe is not None:
            return self.process_probe(res)
        if not res.startswith('profile:'):
            return False
        name = res[len('profile:'):]
        if name.startswith('acct-'):
            acct = name[len('acct-'):]
            cands = {LOGIN_DIRS[acct]} | {str(self.paths.root / _LINKS[k]) for k, a in ACCOUNT_OF.items() if a == acct}
        else:
            path = str(self.paths.root / 'ax-console' / 'data' / 'browser-scratch') if name == 'scratch' else PROFILES.get(name)
            cands = {path} if path else set()
        for cand in cands:
            r = subprocess.run(['pgrep', '-f', f'user-data-dir={re.escape(cand)}( |$)'], capture_output=True)
            if r.returncode == 0:
                return True
        return False

    def acquire(self, resources, job, wait=2400, poll=5, check_stop=True):
        """자원을 모두 잡을 때까지 기다린다. 못 잡으면 Timeout. 잡은 [(자원, fd)] 를 돌려준다."""
        resources = sorted({_canon(r) for r in resources})
        holder = {'job': job, 'pid': os.getpid(), 'since': _now()}
        wfile = self.paths.lock_dir / 'waiting' / f'{os.getpid()}-{threading.get_ident()}.json'
        wfile.parent.mkdir(parents=True, exist_ok=True)
        t0, said = time.monotonic(), False
        try:
            while True:
                if check_stop:
                    self._check_control(resources)
                got, busy = [], None
                try:
                    for res in sorted(resources):
                        if self._profile_busy_outside(res) and not self.holder_of(res):
                            busy = f'{res}(잠금 밖 프로세스)'
                            break
                        fd = self._try(res, holder)
                        if fd is None:
                            h = self.holder_of(res)
                            busy = f"{res}({h['job'] if h else '?'})"
                            break
                        got.append((res, fd))
                except BaseException:
                    self._release(got)
                    raise
                if busy is None:
                    try:
                        if check_stop:
                            self._check_control(resources)
                        if said:
                            self.log(f'{job}: 기다린 끝에 잡음 {resources} ({int(time.monotonic() - t0)}초)')
                    except BaseException:
                        self._release(got)
                        raise
                    return got
                self._release(got)
                if not said:
                    self.log(f'{job}: 기다림 — {busy} 사용 중')
                    said = True
                wfile.write_text(json.dumps({'job': job, 'pid': os.getpid(), 'since': holder['since'],
                                             'resources': resources, 'blocked_by': busy}, ensure_ascii=False))
                if check_stop:
                    self._check_control(resources)
                if time.monotonic() - t0 >= wait:
                    raise Timeout(f"{f'{wait // 60}분' if wait >= 60 else f'{wait}초'} 기다려도 {busy} 가 비지 않음")
                time.sleep(max(0, min(poll, wait - (time.monotonic() - t0))))
        finally:
            try:
                wfile.unlink()
            except OSError:
                pass

    @contextmanager
    def hold(self, resources, job, wait=2400, check_stop=True):
        fds = self.acquire(resources, job, wait, poll=.05 if resources == ['control:publish-gate'] else 5, check_stop=check_stop)
        try:
            yield
        finally:
            self._release(fds)

    def set_skip(self, job, date, reason='', by='명령줄'):
        """그 날짜에 그 작업의 실행을 한 번 건너뛴다(그날 첫 실행이 건너뛰고 기록은 지워진다)."""
        d = json.loads(self.paths.skip.read_text()) if self.paths.skip.exists() else {}
        d[job] = {'date': date, 'reason': reason, 'by': by, 'at': _now()}
        self.paths.skip.write_text(json.dumps(d, ensure_ascii=False, indent=2))
        self.log(f'{job}: {date} 한 번 건너뛰기 등록 ({by}) — {reason}')

    def take_skip(self, job):
        """오늘 건너뛸 차례면 그 기록(지움)을, 아니면 None. 지난 날짜 기록은 지운다."""
        try:
            d = json.loads(self.paths.skip.read_text())
        except (OSError, ValueError):
            return None
        e = d.get(job)
        if not e:
            return None
        today = datetime.date.today().isoformat()
        if e.get('date') > today:
            return None
        d.pop(job)
        self.paths.skip.write_text(json.dumps(d, ensure_ascii=False, indent=2))
        return e if e.get('date') == today else None


def _default():
    # 기존 테스트/도구의 모듈 경로 주입도 유지한다.
    return AxLock(LockPaths(ROOT, DIR, STOP, SKIP, LOG, CATALOG))


def _profile_busy_outside(*args, **kwargs):
    return _default()._profile_busy_outside(*args, **kwargs)


def _release(*args, **kwargs):
    return _default()._release(*args, **kwargs)


def _try(*args, **kwargs):
    return _default()._try(*args, **kwargs)


def acquire(*args, **kwargs):
    return _default().acquire(*args, **kwargs)


def hold(*args, **kwargs):
    return _default().hold(*args, **kwargs)


def holder_of(*args, **kwargs):
    return _default().holder_of(*args, **kwargs)


def is_publish(*args, **kwargs):
    return _default().is_publish(*args, **kwargs)


def job_info(*args, **kwargs):
    return _default().job_info(*args, **kwargs)


def log(*args, **kwargs):
    return _default().log(*args, **kwargs)


def resources_for(*args, **kwargs):
    return _default().resources_for(*args, **kwargs)


def set_skip(*args, **kwargs):
    return _default().set_skip(*args, **kwargs)


def set_stop(*args, **kwargs):
    return _default().set_stop(*args, **kwargs)


def status(*args, **kwargs):
    return _default().status(*args, **kwargs)


def stopped(*args, **kwargs):
    return _default().stopped(*args, **kwargs)


def take_skip(*args, **kwargs):
    return _default().take_skip(*args, **kwargs)


def clear_stop(by='사람', expected_version=None):
    lock = _default()
    if expected_version is None:
        expected_version = read_control_state(lock.paths)['version']
    return lock.clear_stop(expected_version, by=by)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
