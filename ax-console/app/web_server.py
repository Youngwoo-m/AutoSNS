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
import sqlite3
import sys
import threading
from urllib.parse import parse_qs, urlsplit, unquote, quote


_APP = Path(__file__).resolve().parent
# 단독 실행과 importlib에서 같은 로컬 모듈을 사용한다.
for _module_root in (_APP.parents[1], _APP):
    if str(_module_root) not in sys.path:
        sys.path.insert(0, str(_module_root))
from common.operations.content_store import ContentStore, StoreError, MAX_ASSET_BYTES
from common.operations.integration_store import IntegrationStore
from web_content import (CONTENT_ID, ASSET_ID, MEDIA_TYPES, ERROR_STATUS, ERROR_MESSAGES,
                         content_body, review_body, serialize_content)
from web_integrations import validate_settings_body, settings_response
from workspace_snapshot import compose_workspace_snapshot
_AUTH_LOCKS = {}
_AUTH_LOCKS_LOCK = threading.Lock()
_STATIC = {
    'index.html': 'text/html; charset=utf-8',
    'styles.css': 'text/css; charset=utf-8',
    'api.js': 'text/javascript; charset=utf-8',
    'app.js': 'text/javascript; charset=utf-8',
    'view_helpers.js': 'text/javascript; charset=utf-8',
    'content_editor.js': 'text/javascript; charset=utf-8',
    'integration_settings.js': 'text/javascript; charset=utf-8',
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
    server_version = 'AXWeb'
    sys_version = ''

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *_args):
        # 요청 URL·인증 머리글·원본 예외를 로그로 남기지 않는다.
        pass

    def _send_response(self, status, obj=None, *, body=None, content_type='application/json; charset=utf-8', headers=None):
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

    def _send(self, status, obj=None, **kwargs):
        try:
            self._send_response(status, obj, **kwargs)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True

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
        for name in ('Host', 'Origin', 'Cookie', 'X-AX-Internal', 'Content-Length', 'Content-Type', 'Sec-Fetch-Site',
                     'X-AX-Filename', 'X-AX-Expected-Revision'):
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
        if parsed.path in ('/api/v2/snapshot', '/api/v2/contents', '/api/v2/integrations/settings'):
            if set(query) - {'account'} or any(len(values) != 1 for values in query.values()):
                self._error(400, '올바르지 않은 조회 조건입니다')
                return None
            if query.get('account', ['all'])[0] not in ('all', 'dept', 'personal'):
                self._error(400, '올바르지 않은 계정입니다')
                return None
        elif re.fullmatch(r'/api/v2/contents/' + CONTENT_ID, parsed.path):
            if (set(query) - {'revision'} or any(len(values) != 1 for values in query.values())
                    or ('revision' in query and not re.fullmatch(r'[1-9][0-9]{0,9}', query['revision'][0]))):
                self._error(400, '올바르지 않은 버전입니다')
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
            if method == 'POST' and path in ('/api/auth/login', '/api/auth/logout'):
                return self._post(path)
            managed = path == '/api/v2/integrations/settings' or path == '/api/v2/contents' or path.startswith('/api/v2/contents/')
            if managed:
                if not self._authed():
                    return self._error(401, '로그인이 필요합니다')
                return self._managed(method, path, query)
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
                if self.server.workspace_root is not None:
                    snapshot = compose_workspace_snapshot(snapshot, self.server.workspace_root,
                                                          query.get('account', ['all'])[0])
                    if not getattr(self.server.content_store, '_initialized', False):
                        snapshot['workspace_writable'] = False
                return self._send(200, snapshot)
            if path in ('/', '/web/'):
                return self._static('index.html')
            if path.startswith('/web/') and path[5:] in _STATIC:
                return self._static(path[5:])
            return self._error(404, '지원하지 않는 경로입니다')
        except StoreError as exc:
            self._error(ERROR_STATUS.get(exc.code, 503), ERROR_MESSAGES.get(exc.code, ERROR_MESSAGES['storage_error']))
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True
        except (OSError, sqlite3.Error):
            self._error(503, ERROR_MESSAGES['storage_error'])
        except Exception:
            self._error(500, '조회 요청을 처리하지 못했습니다. 잠시 뒤 다시 시도하세요')

    def _read_body(self, limit, *, json_body=False):
        length_text = self.headers.get('Content-Length', '')
        if not re.fullmatch(r'[0-9]{1,12}', length_text):
            raise StoreError('invalid')
        length = int(length_text)
        if length > limit:
            raise StoreError('too_large')
        if json_body and self.headers.get('Content-Type', '').split(';', 1)[0].strip().lower() != 'application/json':
            raise StoreError('unsupported_media')
        try:
            raw = self.rfile.read(length)
        except (OSError, TimeoutError) as exc:
            self.close_connection = True
            raise StoreError('invalid') from exc
        if len(raw) != length:
            raise StoreError('invalid')
        if not json_body:
            return raw
        try:
            def object_fields(pairs):
                obj = {}
                for key, value in pairs:
                    if key in obj:
                        raise ValueError('duplicate field')
                    obj[key] = value
                return obj

            def invalid_constant(_value):
                raise ValueError('invalid constant')

            return json.loads(raw.decode('utf-8'), object_pairs_hook=object_fields,
                              parse_constant=invalid_constant)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise StoreError('invalid') from exc

    def _managed(self, method, path, query):
        if method not in ('GET', 'POST', 'PUT'):
            return self._error(405, '지원하지 않는 요청입니다')
        if self.server.workspace_root is None:
            if method != 'GET':
                return self._error(405, '조회 전용 화면에서는 지원하지 않는 요청입니다')
            if path in ('/api/v2/contents', '/api/v2/integrations/settings'):
                return self._send(200, {'items': []})
            raise StoreError('not_found')
        store = self.server.content_store
        if method != 'GET' and not getattr(store, '_initialized', False):
            raise StoreError('storage_error')
        if method != 'GET' and query:
            raise StoreError('invalid')
        account = query.get('account', ['all'])[0]
        if path == '/api/v2/integrations/settings':
            if method == 'GET':
                return self._send(200, settings_response(self.server.integration_store.list(account)))
            if method == 'PUT':
                values = validate_settings_body(self._read_body(1024 * 1024, json_body=True))
                return self._send(200, self.server.integration_store.put(*values))
            return self._error(405, '지원하지 않는 요청입니다')
        if path == '/api/v2/contents':
            if method == 'GET':
                return self._send(200, {'items': [serialize_content(item) for item in store.list(account)]})
            if method == 'POST':
                owner, payload = content_body(self._read_body(1024 * 1024, json_body=True), create=True)
                return self._send(201, serialize_content(store.create(owner, payload)))
            return self._error(405, '지원하지 않는 요청입니다')
        match = re.fullmatch(r'/api/v2/contents/(' + CONTENT_ID + r')(.*)', path)
        if not match:
            raise StoreError('not_found')
        content_id, suffix = match.groups()
        if not suffix:
            if method == 'GET':
                revision = int(query['revision'][0]) if 'revision' in query else None
                item = store.get(content_id, revision)
                if item is None:
                    raise StoreError('not_found')
                return self._send(200, serialize_content(item))
            if method == 'PUT':
                revision, payload = content_body(self._read_body(1024 * 1024, json_body=True))
                return self._send(200, serialize_content(store.update(content_id, revision, payload)))
        elif suffix == '/revisions' and method == 'GET':
            if store.get(content_id) is None:
                raise StoreError('not_found')
            return self._send(200, {'items': store.list_revisions(content_id)})
        elif suffix == '/reviews' and method == 'POST':
            values = review_body(self._read_body(1024 * 1024, json_body=True))
            store.record_review(content_id, *values)
            return self._send(200, serialize_content(store.get(content_id, values[0])))
        elif suffix == '/assets' and method == 'POST':
            encoded = self.headers.get('X-AX-Filename', '')
            revision = self.headers.get('X-AX-Expected-Revision', '')
            if (not encoded or len(encoded) > 2400 or re.search(r'%(?![0-9a-fA-F]{2})', encoded)
                    or not re.fullmatch(r'[1-9][0-9]{0,9}', revision)):
                raise StoreError('invalid')
            try:
                encoded.encode('ascii')
                filename = unquote(encoded, encoding='utf-8', errors='strict')
            except UnicodeError as exc:
                raise StoreError('invalid') from exc
            if not filename or len(filename) > 200 or any(c in filename for c in '/\\\x00\r\n'):
                raise StoreError('invalid')
            media_type = self.headers.get('Content-Type', '').strip().lower()
            if media_type not in MEDIA_TYPES:
                raise StoreError('unsupported_media')
            raw = self._read_body(MAX_ASSET_BYTES)
            return self._send(200, serialize_content(store.add_asset(content_id, int(revision), filename, media_type, raw)))
        else:
            asset_match = re.fullmatch(r'/revisions/([1-9][0-9]{0,9})/assets/(' + ASSET_ID + ')', suffix)
            if asset_match and method == 'GET':
                if self.headers.get('Range') is not None:
                    return self._error(416, '부분 자산 요청은 지원하지 않습니다')
                asset, raw = store.read_asset(content_id, int(asset_match[1]), asset_match[2])
                if asset['media_type'] not in MEDIA_TYPES:
                    raise StoreError('storage_error')
                return self._send(200, body=raw, content_type=asset['media_type'],
                                  headers={'Content-Disposition': "attachment; filename*=UTF-8''" + quote(asset['filename'], safe='')})
            raise StoreError('not_found')
        return self._error(405, '지원하지 않는 요청입니다')

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
            body = self._read_body(4096, json_body=True)
            if not isinstance(body, dict) or not isinstance(body.get('password'), str) or len(body['password']) > 512:
                return self._error(400, '올바른 비밀번호를 입력하세요')
        except (ValueError, UnicodeError, OSError):
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
                  web_root: Path, auth_backend=None, snapshot_builder=None,
                  workspace_root: Path | None = None) -> ThreadingHTTPServer:
    """loopback 소켓만 준비한다. serve_forever와 스레드 시작은 호출자 책임이다."""
    try:
        address = ipaddress.ip_address(host if host != 'localhost' else '127.0.0.1')
    except ValueError:
        raise ValueError('조회 서버는 localhost에서만 실행할 수 있습니다') from None
    if not address.is_loopback:
        raise ValueError('조회 서버는 localhost에서만 실행할 수 있습니다')
    source_root, web_root = Path(source_root).resolve(), Path(web_root).resolve()
    workspace_root = Path(workspace_root).resolve() if workspace_root is not None else None
    if workspace_root is not None and (workspace_root.is_relative_to(source_root) or source_root.is_relative_to(workspace_root)):
        raise ValueError('관리 저장소와 운영 루트는 분리해야 합니다')
    backend = auth_backend if auth_backend is not None else _load_auth(source_root)
    server_class = _IPv6WebServer if address.version == 6 else _WebServer
    server = server_class((str(address), port), _Handler)
    server.source_root = source_root
    server.workspace_root = workspace_root
    server.content_store = ContentStore(workspace_root) if workspace_root is not None else None
    server.integration_store = IntegrationStore(workspace_root) if workspace_root is not None else None
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
                           source_root=Path(source), web_root=_APP / 'web',
                           workspace_root=Path(os.environ['AX_WORKSPACE_ROOT']) if os.environ.get('AX_WORKSPACE_ROOT') else None)
    try:
        if server.workspace_root is not None:
            server.content_store.initialize()
            server.integration_store.initialize()
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
