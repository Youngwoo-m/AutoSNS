"""기존 인증을 재사용하는 localhost 전용 읽기 화면.

import/factory는 파일을 쓰거나 운영 작업을 시작하지 않는다. 인증 세션의
생성·갱신·삭제만 기존 auth.py가 담당하며 운영 서버는 import하지 않는다.
"""
import fcntl
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import threading
from urllib.parse import parse_qs, urlsplit


_APP = Path(__file__).resolve().parent
_AUTH_LOCKS = {}
_AUTH_LOCKS_LOCK = threading.Lock()
_STATIC = {
    'index.html': 'text/html; charset=utf-8',
    'styles.css': 'text/css; charset=utf-8',
    'api.js': 'text/javascript; charset=utf-8',
    'app.js': 'text/javascript; charset=utf-8',
    'view_helpers.js': 'text/javascript; charset=utf-8',
}
_SETUP_NOTICE = '''<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>기존 인증 필요</title><h1>기존 콘솔 인증이 필요합니다</h1>
<p>이 조회 화면은 비밀번호를 만들거나 변경하지 않습니다.
기존 콘솔에서 인증을 설정한 뒤 같은 인증 자료로 조회 서버를 실행하세요.</p></html>'''.encode()


class _SessionLock:
    """새 웹 세션 저장만 스레드·프로세스 사이에서 직렬화한다."""

    def __init__(self, directory):
        self.directory = directory
        self.thread_lock = threading.Lock()
        self.fd = None

    def __enter__(self):
        self.thread_lock.acquire()
        try:
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.fd = os.open(self.directory / 'sessions.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            fcntl.flock(self.fd, fcntl.LOCK_EX)
        except BaseException:
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None
            self.thread_lock.release()
            raise
        return self

    def __exit__(self, *_args):
        try:
            os.close(self.fd)  # 닫을 때 flock도 해제된다. 잠금 파일은 유지한다.
            self.fd = None
        finally:
            self.thread_lock.release()


def _credential_version(path):
    """인증 내용과 파일 교체를 함께 식별한다. 읽기 중 변경되면 거부한다."""
    def identity(stat):
        return stat.st_dev, stat.st_ino, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size

    try:
        with path.open('rb') as stream:
            before = identity(os.fstat(stream.fileno()))
            data = stream.read(65537)
            after = identity(os.fstat(stream.fileno()))
        if len(data) > 65536 or before != after or after != identity(path.stat()):
            return None
    except OSError:
        return None
    return hashlib.sha256(data + b'\0' + repr(after).encode()).hexdigest()


class _VersionedAuth:
    """원본 인증 함수에 비밀번호 버전 검사를 덧붙이는 새 웹 전용 어댑터."""

    def __init__(self, backend):
        self.backend = backend
        self.verified = threading.local()

    def __getattr__(self, name):
        return getattr(self.backend, name)

    def verify(self, password, ip='local'):
        self.verified.__dict__.clear()
        version = _credential_version(self.AUTH)
        valid = self.backend.verify(password, ip)
        if valid and version is not None and version == _credential_version(self.AUTH):
            self.verified.version = version
            return True
        return False

    def new_session(self, ua=''):
        # HTTP 로그인은 같은 요청 스레드의 verify에서 확인한 버전을 사용한다.
        version = getattr(self.verified, 'version', _credential_version(self.AUTH))
        self.verified.__dict__.clear()
        if version is None or version != _credential_version(self.AUTH):
            raise ValueError('인증 정보가 변경되었습니다')
        token = self.backend.new_session(ua)
        try:
            with self.backend._lock:
                if version != _credential_version(self.AUTH):
                    raise ValueError('인증 정보가 변경되었습니다')
                sessions = self.backend._load(self.SESSIONS, {})
                sessions[self.backend._h(token)]['auth_version'] = version
                self.backend._save(self.SESSIONS, sessions)
            if version != _credential_version(self.AUTH):
                raise ValueError('인증 정보가 변경되었습니다')
        except BaseException:
            self.backend.drop(token)
            raise
        return token

    def check(self, token):
        if not token:
            return False
        version = _credential_version(self.AUTH)
        if version is None:
            return False
        with self.backend._lock:
            session = self.backend._load(self.SESSIONS, {}).get(self.backend._h(token))
            if not isinstance(session, dict) or session.get('auth_version') != version:
                return False
        return self.backend.check(token) and version == _credential_version(self.AUTH)


def _load_auth(source_root):
    """기존 비밀번호·내부키를 읽고 새 웹의 세션·쿠키만 별도로 저장한다."""
    spec = importlib.util.spec_from_file_location('_ax_web_auth', _APP / 'auth.py')
    backend = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backend)
    directory = Path(os.environ.get('AX_AUTH_DIR') or
                     source_root / 'ax-console' / 'data' / 'auth').resolve()
    session_directory = directory / 'web-v2'
    backend.DIR = session_directory
    backend.AUTH = directory / 'auth.json'
    backend.SESSIONS = session_directory / 'sessions.json'
    backend.COOKIE = 'ax_web_session'
    backend.KEYFILE = directory / 'internal.key'
    with _AUTH_LOCKS_LOCK:
        backend._lock = _AUTH_LOCKS.setdefault(session_directory, _SessionLock(session_directory))
    return _VersionedAuth(backend)


def _build_snapshot(source_root, account='all', **kwargs):
    # 파일 조회 모델만 지연 import한다. 기존 server.py는 사용하지 않는다.
    spec = importlib.util.spec_from_file_location('_ax_web_read_model', _APP / 'read_model.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_snapshot(source_root, account, **kwargs)


class _WebServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class _IPv6WebServer(_WebServer):
    address_family = socket.AF_INET6


class _Handler(BaseHTTPRequestHandler):
    server_version = 'AXReadOnly'
    sys_version = ''

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *_args):
        # 요청 URL·인증 머리글·원본 예외를 로그로 남기지 않는다.
        pass

    def _send(self, status, obj=None, *, body=None, content_type='application/json; charset=utf-8', headers=None):
        data = body if body is not None else json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)

    def send_error(self, code, message=None, explain=None):
        self._send(code, {'error': '요청을 처리할 수 없습니다'})

    def _error(self, status, message):
        self._send(status, {'error': message})

    def _validated_target(self):
        # BaseHTTPRequestHandler가 //를 정규화하기 전 요청 대상도 확인한다.
        target = self.requestline.split(' ')[1]
        if (len(target) > 2048 or not target.startswith('/') or target.startswith('//')
                or re.search(r'[\\\x00-\x20\x7f]', target)):
            self._error(400, '올바르지 않은 경로입니다')
            return None
        try:
            parsed = urlsplit(target)
        except ValueError:
            self._error(400, '올바르지 않은 경로입니다')
            return None
        if parsed.scheme or parsed.netloc or parsed.fragment or '%' in parsed.path or '..' in parsed.path.split('/'):
            self._error(400, '올바르지 않은 경로입니다')
            return None
        for name in ('Host', 'Origin', 'Cookie', 'X-AX-Internal', 'Content-Length', 'Content-Type', 'Sec-Fetch-Site'):
            if len(self.headers.get_all(name, [])) > 1:
                self._error(400, '중복된 요청 머리글입니다')
                return None
        host = self.headers.get('Host', '')
        if host not in self.server.allowed_hosts:
            self._error(403, '허용되지 않은 호스트입니다')
            return None
        origin = self.headers.get('Origin')
        if ((origin is not None and origin != 'http://' + host)
                or self.headers.get('Sec-Fetch-Site') == 'cross-site'):
            self._error(403, '같은 출처에서만 접근할 수 있습니다')
            return None
        if self.headers.get('Transfer-Encoding'):
            self._error(400, '지원하지 않는 요청 형식입니다')
            return None
        if re.search(r'%(?![0-9a-fA-F]{2})', parsed.query):
            self._error(400, '올바르지 않은 조회 조건입니다')
            return None
        try:
            query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True,
                             max_num_fields=4, encoding='utf-8', errors='strict') if parsed.query else {}
        except (ValueError, UnicodeError):
            self._error(400, '올바르지 않은 조회 조건입니다')
            return None
        if parsed.path == '/api/v2/snapshot':
            if set(query) - {'account'} or any(len(values) != 1 for values in query.values()):
                self._error(400, '올바르지 않은 조회 조건입니다')
                return None
            if query.get('account', ['all'])[0] not in ('all', 'dept', 'personal'):
                self._error(400, '올바르지 않은 계정입니다')
                return None
        elif query:
            self._error(400, '지원하지 않는 조회 조건입니다')
            return None
        return parsed.path, query

    def _token(self):
        return self.server.auth_backend.cookie_of(self.headers.get('Cookie'))

    def _authed(self):
        key = self.headers.get('X-AX-Internal', '')
        keyfile = getattr(self.server.auth_backend, 'KEYFILE', None)
        if key and keyfile is not None:
            try:
                with Path(keyfile).open('r', encoding='utf-8') as stream:
                    existing = stream.read(4097).strip()
                if existing and len(existing) <= 4096 and hmac.compare_digest(key.encode(), existing.encode()):
                    return True
            except (OSError, UnicodeError):
                pass
        return self.server.auth_backend.check(self._token())

    def _static(self, name):
        candidate = self.server.web_root / name
        try:
            resolved = candidate.resolve(strict=True)
            if resolved.parent != self.server.web_root:
                return self._error(404, '화면 파일을 찾을 수 없습니다')
            data = resolved.read_bytes()
        except OSError:
            return self._error(404, '화면 파일을 찾을 수 없습니다')
        self._send(200, body=data, content_type=_STATIC[name])

    def do_GET(self):
        self._dispatch('GET')

    def do_POST(self):
        self._dispatch('POST')

    def _dispatch(self, method):
        try:
            validated = self._validated_target()
            if validated is None:
                return
            path, query = validated
            if method == 'POST':
                return self._post(path)
            if method != 'GET':
                return self._error(405, '조회 전용 화면에서는 지원하지 않는 요청입니다')
            auth = self.server.auth_backend
            if path == '/api/auth/status':
                return self._send(200, {'setup': auth.is_setup(), 'logged_in': self._authed(),
                                        'setup_supported': False, 'read_only': True})
            if path == '/login':
                data = (_APP / 'login.html').read_bytes() if auth.is_setup() else _SETUP_NOTICE
                # 원본 로그인 파일은 유지하고 이 응답에서만 시스템 글꼴을 쓴다.
                data = re.sub(rb'@font-face\s*\{[^}]*\}', b'', data)
                return self._send(200, body=data, content_type='text/html; charset=utf-8')
            if not self._authed():
                if path in ('/', '/web/', '/web/index.html'):
                    return self._send(302, body=b'', headers={'Location': '/login'})
                return self._send(401, {'error': '로그인이 필요합니다', 'login': True})
            if path == '/api/v2/snapshot':
                kwargs = ({'launchagents_dir': self.server.launchagents_dir}
                          if self.server.launchagents_dir is not None else {})
                snapshot = self.server.snapshot_builder(self.server.source_root, query.get('account', ['all'])[0], **kwargs)
                return self._send(200, snapshot)
            if path in ('/', '/web/'):
                return self._static('index.html')
            if path.startswith('/web/') and path[5:] in _STATIC:
                return self._static(path[5:])
            return self._error(404, '지원하지 않는 경로입니다')
        except Exception:
            self._error(500, '조회 요청을 처리하지 못했습니다. 잠시 뒤 다시 시도하세요')

    def _post(self, path):
        if path not in ('/api/auth/login', '/api/auth/logout'):
            return self._error(405, '조회 전용 화면에서는 지원하지 않는 요청입니다')
        auth = self.server.auth_backend
        if path == '/api/auth/logout':
            if not self._authed():
                return self._error(401, '로그인이 필요합니다')
            auth.drop(self._token())
            return self._send(200, {'ok': True}, headers={'Set-Cookie': auth.clear_cookie()})
        if not auth.is_setup():
            return self._error(503, '기존 콘솔에서 인증을 먼저 설정하세요')
        try:
            length_text = self.headers.get('Content-Length', '')
            if not length_text.isdecimal():
                return self._error(400, '올바르지 않은 요청 길이입니다')
            length = int(length_text)
            if length > 4096:
                return self._error(413, '로그인 요청이 너무 큽니다')
            if self.headers.get('Content-Type', '').split(';', 1)[0].strip().lower() != 'application/json':
                return self._error(415, 'JSON 요청만 지원합니다')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict) or not isinstance(body.get('password'), str) or len(body['password']) > 512:
                return self._error(400, '올바른 비밀번호를 입력하세요')
        except (ValueError, UnicodeError):
            return self._error(400, '올바르지 않은 로그인 요청입니다')
        try:
            verified = auth.verify(body['password'], self.client_address[0])
        except ValueError:
            return self._error(429, '로그인 요청이 너무 많습니다. 잠시 뒤 다시 시도하세요')
        if not verified:
            return self._error(401, '비밀번호가 맞지 않습니다')
        try:
            token = auth.new_session(self.headers.get('User-Agent', ''))
        except ValueError:
            return self._error(401, '인증 정보가 변경되었습니다. 다시 로그인하세요')
        return self._send(200, {'ok': True}, headers={'Set-Cookie': auth.set_cookie(token)})

    def _unsupported(self):
        self._dispatch(self.command)

    do_HEAD = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_TRACE = _unsupported


def create_server(host: str = '127.0.0.1', port: int = 0, *, source_root: Path,
                  web_root: Path, auth_backend=None, snapshot_builder=None) -> ThreadingHTTPServer:
    """loopback 소켓만 준비한다. serve_forever와 스레드 시작은 호출자 책임이다."""
    try:
        address = ipaddress.ip_address(host if host != 'localhost' else '127.0.0.1')
    except ValueError:
        raise ValueError('조회 서버는 localhost에서만 실행할 수 있습니다') from None
    if not address.is_loopback:
        raise ValueError('조회 서버는 localhost에서만 실행할 수 있습니다')
    source_root, web_root = Path(source_root).resolve(), Path(web_root).resolve()
    backend = auth_backend if auth_backend is not None else _load_auth(source_root)
    server_class = _IPv6WebServer if address.version == 6 else _WebServer
    server = server_class((str(address), port), _Handler)
    server.source_root = source_root
    server.web_root = web_root
    server.auth_backend = backend
    server.snapshot_builder = snapshot_builder if snapshot_builder is not None else _build_snapshot
    explicit_agents = os.environ.get('AX_LAUNCHAGENTS_DIR')
    server.launchagents_dir = Path(explicit_agents).resolve() if explicit_agents else None
    bound_host = f'[{address}]' if address.version == 6 else str(address)
    server.allowed_hosts = {f'{bound_host}:{server.server_port}', f'localhost:{server.server_port}'}
    return server


def main():
    source = os.environ.get('AX_SOURCE_ROOT')
    if not source:
        raise SystemExit('AX_SOURCE_ROOT로 조회할 운영 루트를 지정하세요')
    server = create_server(os.environ.get('AX_HOST', '127.0.0.1'),
                           int(os.environ.get('AX_PORT', '8767')),
                           source_root=Path(source), web_root=_APP / 'web')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
