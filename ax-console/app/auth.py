"""콘솔 로그인 — 비밀번호 하나, 쿠키 세션, 내부 호출 키.

- 비밀번호는 사용자가 처음 열 때 직접 만든다. PBKDF2-SHA256 해시만 저장한다(data/auth/auth.json).
- 로그인하면 임의 토큰을 쿠키(ax_session, HttpOnly, SameSite=Strict)로 준다. 서버에는 토큰의 해시만 둔다.
  30일이 지나거나 3일 동안 쓰지 않으면 끝난다. 로그아웃하면 바로 지운다.
- 이 Mac 안의 에이전트가 콘솔 API 를 부를 때는 내부 키(data/auth/internal.key, 0600)를
  X-AX-Internal 머리글로 보낸다.
- 비밀번호를 잊으면 이 Mac 에서 data/auth/auth.json 을 지우고 다시 만든다(세션도 함께 사라진다).
- 실패가 1분에 5번을 넘으면 1분 동안 막는다.
"""
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path

DIR = Path(os.environ.get('AX_AUTH_DIR') or Path(__file__).resolve().parents[1] / 'data' / 'auth')
AUTH = DIR / 'auth.json'
SESSIONS = DIR / 'sessions.json'
KEYFILE = DIR / 'internal.key'
COOKIE = 'ax_session'
MAX_AGE, IDLE = 30 * 86400, 3 * 86400
ITER = 310_000
_lock = threading.Lock()
_fails = {}


def _load(p, default):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return default


def _save(p, obj):
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(obj, f)
    tmp.replace(p)


def _h(token):
    return hashlib.sha256(token.encode()).hexdigest()


def internal_key():
    DIR.mkdir(parents=True, exist_ok=True)
    if not KEYFILE.exists():
        fd = os.open(KEYFILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(secrets.token_urlsafe(32))
    return KEYFILE.read_text().strip()


def is_setup():
    return bool(_load(AUTH, {}).get('hash'))


def _check_pw(pw):
    if len(pw or '') < 8:
        raise ValueError('비밀번호는 8자 이상으로 정하세요')


def _hash(pw, salt):
    return hashlib.pbkdf2_hmac('sha256', pw.encode(), bytes.fromhex(salt), ITER).hex()


def set_password(pw):
    _check_pw(pw)
    salt = secrets.token_hex(16)
    _save(AUTH, {'salt': salt, 'hash': _hash(pw, salt), 'iter': ITER, 'set_at': int(time.time())})


def setup(pw):
    """처음 한 번만. 이미 비밀번호가 있으면 거부(다른 사람이 덮어쓰지 못하게)."""
    with _lock:
        if is_setup():
            raise ValueError('이미 비밀번호가 있습니다')
        set_password(pw)


def _limited(ip):
    now = time.time()
    _fails[ip] = [t for t in _fails.get(ip, []) if now - t < 60]
    return len(_fails[ip]) >= 5


def verify(pw, ip='local'):
    if _limited(ip):
        raise ValueError('여러 번 틀려서 1분 동안 막았습니다. 잠시 뒤 다시 하세요')
    a = _load(AUTH, {})
    ok = bool(a.get('hash')) and hmac.compare_digest(_hash(pw or '', a['salt']), a['hash'])
    if not ok:
        _fails.setdefault(ip, []).append(time.time())
    return ok


def change_password(old, new):
    if not verify(old):
        raise ValueError('지금 비밀번호가 맞지 않습니다')
    set_password(new)
    with _lock:   # 비밀번호를 바꾸면 다른 세션은 모두 끝낸다
        _save(SESSIONS, {})


def new_session(ua=''):
    tok = secrets.token_urlsafe(32)
    now = int(time.time())
    with _lock:
        s = {k: v for k, v in _load(SESSIONS, {}).items() if _alive(v, now)}
        s[_h(tok)] = {'created': now, 'last': now, 'ua': ua[:120]}
        _save(SESSIONS, s)
    return tok


def _alive(v, now):
    return now - v['created'] < MAX_AGE and now - v['last'] < IDLE


def check(token):
    if not token:
        return False
    now = int(time.time())
    with _lock:
        s = _load(SESSIONS, {})
        v = s.get(_h(token))
        if not v or not _alive(v, now):
            return False
        if now - v['last'] > 300:   # 5분에 한 번만 '마지막 사용' 갱신
            v['last'] = now
            _save(SESSIONS, s)
    return True


def drop(token):
    with _lock:
        s = _load(SESSIONS, {})
        s.pop(_h(token or ''), None)
        _save(SESSIONS, s)


def cookie_of(header):
    for part in (header or '').split(';'):
        k, _, v = part.strip().partition('=')
        if k == COOKIE:
            return v
    return ''


def set_cookie(token):
    return f'{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={MAX_AGE}'


def clear_cookie():
    return f'{COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0'
