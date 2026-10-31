"""임시 원본·인증과 loopback HTTP만 사용하는 조회 서버 회귀 시험."""
import fcntl
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import select
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch


APP = Path(__file__).resolve().parents[1] / 'ax-console' / 'app'
SPEC = importlib.util.spec_from_file_location('web_server_test_target', APP / 'web_server.py')


class FakeAuth:
    KEYFILE = None

    def __init__(self):
        self.tokens = set()
        self.configured = True

    def is_setup(self): return self.configured
    def verify(self, password, ip): return password == 'fixture-password'
    def new_session(self, ua):
        self.tokens.add('fixture-token')
        return 'fixture-token'
    def check(self, token): return token in self.tokens
    def drop(self, token): self.tokens.discard(token)
    def cookie_of(self, header): return (header or '').removeprefix('ax_session=')
    def set_cookie(self, token): return f'ax_session={token}; HttpOnly; SameSite=Strict; Path=/'
    def clear_cookie(self): return 'ax_session=; Max-Age=0; Path=/'


class WebServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = importlib.util.module_from_spec(SPEC)
        SPEC.loader.exec_module(cls.module)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / 'source'
        self.source.mkdir()
        self.web = Path(self.tmp.name) / 'web'
        self.web.mkdir()
        for name in ('index.html', 'styles.css', 'api.js', 'app.js', 'view_helpers.js'):
            (self.web / name).write_text('fixture ' + name)
        self.auth = FakeAuth()
        self.calls = []
        self.server = self.module.create_server(
            source_root=self.source, web_root=self.web, auth_backend=self.auth,
            snapshot_builder=self.snapshot)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def snapshot(self, source_root, account='all', **kwargs):
        self.calls.append((source_root, account))
        return {'schema_version': 1, 'read_only': True, 'scope': account}

    def request(self, path, method='GET', data=None, headers=None, server=None):
        server = server or self.server
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
        body = json.dumps(data) if data is not None else None
        merged = {'Content-Type': 'application/json'}
        merged.update(headers or {})
        conn.request(method, path, body=body, headers=merged)
        response = conn.getresponse()
        result = (response.status, dict(response.getheaders()), response.read())
        conn.close()
        return result

    def login(self):
        status, headers, _ = self.request('/api/auth/login', 'POST', {'password': 'fixture-password'})
        self.assertEqual(status, 200)
        self.assertIn('HttpOnly', headers['Set-Cookie'])
        return {'Cookie': 'ax_session=fixture-token'}

    def test_auth_required_and_root_redirect(self):
        self.assertEqual(self.request('/api/v2/snapshot')[0], 401)
        status, headers, _ = self.request('/')
        self.assertEqual((status, headers['Location']), (302, '/login'))
        self.assertEqual(self.request('/web/app.js')[0], 401)
        self.assertFalse(self.calls)

    def test_login_snapshot_scope_and_logout(self):
        cookie = self.login()
        for account in ('all', 'dept', 'personal'):
            status, headers, body = self.request('/api/v2/snapshot?account=' + account, headers=cookie)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)['scope'], account)
            self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(self.calls[-1], (self.source.resolve(), 'personal'))
        self.assertEqual(self.request('/api/auth/logout', 'POST', {}, cookie)[0], 200)
        self.assertEqual(self.request('/api/v2/snapshot', headers=cookie)[0], 401)

    def test_reject_invalid_queries_before_builder(self):
        cookie = self.login()
        for query in ('account=bad', 'account=', 'account=dept&account=personal', 'root=/private',
                      'account=%zz', 'account=all&root=x'):
            with self.subTest(query=query):
                self.assertEqual(self.request('/api/v2/snapshot?' + query, headers=cookie)[0], 400)
        self.assertFalse(self.calls)

    def test_static_allowlist_and_traversal(self):
        cookie = self.login()
        for name in ('index.html', 'styles.css', 'api.js', 'app.js', 'view_helpers.js'):
            self.assertEqual(self.request('/web/' + name, headers=cookie)[0], 200)
        self.assertEqual(self.request('/web/', headers=cookie)[0], 200)
        self.assertEqual(self.request('/web/unknown.js', headers=cookie)[0], 404)
        for path in ('/web/../auth.py', '/web/%2e%2e/auth.py', '/web/%252e%252e/auth.py',
                     '/web/%2fetc/passwd', '/web/..%5cauth.py', '//evil.example/web/',
                     'http://evil.example/api/v2/snapshot'):
            with self.subTest(path=path):
                self.assertIn(self.request(path, headers=cookie)[0], (400, 404))
        (self.web / 'api.js').unlink()
        (self.web / 'api.js').symlink_to(APP / 'auth.py')
        self.assertEqual(self.request('/web/api.js', headers=cookie)[0], 404)

    def test_engineer_panel_static_module_requires_auth_and_javascript_type(self):
        (self.web / 'engineer_panel.js').write_text('export const fixture = true;')
        self.assertEqual(self.request('/web/engineer_panel.js')[0], 401)
        status, headers, body = self.request('/web/engineer_panel.js', headers=self.login())
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'text/javascript; charset=utf-8')
        self.assertEqual(body, b'export const fixture = true;')

    def test_write_routes_and_methods_rejected(self):
        cookie = self.login()
        for method in ('POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'TRACE'):
            for path in ('/api/v2/snapshot', '/api/stop', '/api/contents', '/api/auth/change', '/api/auth/setup'):
                with self.subTest(method=method, path=path):
                    self.assertIn(self.request(path, method, {}, cookie)[0], (404, 405))
        self.assertFalse(self.calls)

    def test_bad_host_origin_and_fetch_site(self):
        cookie = self.login()
        for extra in ({'Host': 'evil.example'}, {'Host': '127.0.0.1:1'},
                      {'Origin': 'https://evil.example'}, {'Origin': 'null'},
                      {'Sec-Fetch-Site': 'cross-site'}):
            with self.subTest(extra=extra):
                self.assertEqual(self.request('/api/v2/snapshot', headers={**cookie, **extra})[0], 403)
        origin = f'http://127.0.0.1:{self.server.server_port}'
        self.assertEqual(self.request('/api/v2/snapshot', headers={**cookie, 'Origin': origin})[0], 200)
        self.assertEqual(self.request('/api/auth/login', 'POST', {'password': 'fixture-password'},
                                      {'Origin': 'http://evil.example'})[0], 403)

    def test_invalid_body_and_wrong_password(self):
        self.assertEqual(self.request('/api/auth/login', 'POST', {'password': 'bad'})[0], 401)
        for data in ([], {'password': 3}, {'password': 'x' * 5000}):
            self.assertIn(self.request('/api/auth/login', 'POST', data)[0], (400, 413))

    def test_duplicate_headers_and_transfer_encoding_rejected(self):
        for name, value in (('Host', 'evil.example'), ('Origin', 'null'), ('Content-Length', '1')):
            conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
            conn.putrequest('GET', '/api/auth/status')
            if name != 'Host':
                conn.putheader(name, value)
            conn.putheader(name, value)
            conn.endheaders()
            response = conn.getresponse()
            self.assertEqual(response.status, 400)
            response.read()
            conn.close()
        self.assertEqual(self.request('/api/auth/login', 'POST', {},
                                      {'Transfer-Encoding': 'chunked'})[0], 400)

    def test_import_does_not_start_services_or_mutate_source(self):
        (self.source / 'record.json').write_text('{"status":"waiting"}')
        before = self.file_state(self.source)
        with patch('socket.socket', side_effect=AssertionError('socket during import')), \
                patch('threading.Thread.start', side_effect=AssertionError('background during import')), \
                patch('subprocess.Popen', side_effect=AssertionError('process during import')):
            module = importlib.util.module_from_spec(SPEC)
            SPEC.loader.exec_module(module)
        self.assertEqual(self.file_state(self.source), before)

    @staticmethod
    def file_state(root):
        return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in root.rglob('*') if p.is_file()}

    @staticmethod
    def seed_auth(directory):
        """새 웹 생성 전, 임시 기존 콘솔의 인증 파일만 준비한다."""
        spec = importlib.util.spec_from_file_location('fixture_legacy_auth', APP / 'auth.py')
        backend = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(backend)
        backend.DIR = directory
        backend.AUTH = directory / 'auth.json'
        backend.SESSIONS = directory / 'sessions.json'
        backend.KEYFILE = directory / 'internal.key'
        backend.setup('fixture-password')
        return backend

    def real_auth_fixture(self):
        directory = Path(self.tmp.name) / 'versioned-auth'
        legacy = self.seed_auth(directory)
        with patch.dict(os.environ, {'AX_AUTH_DIR': str(directory)}):
            server = self.module.create_server(source_root=self.source, web_root=self.web,
                                               snapshot_builder=self.snapshot)
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), thread.join()))
        return legacy, server

    def real_login(self, server, password='fixture-password'):
        status, headers, _ = self.request('/api/auth/login', 'POST', {'password': password}, server=server)
        self.assertEqual(status, 200)
        return {'Cookie': headers['Set-Cookie'].split(';')[0]}

    def test_errors_do_not_expose_paths_or_traceback(self):
        def failed(*args, **kwargs):
            raise RuntimeError(str(self.source) + '/secret password=hidden')
        self.server.snapshot_builder = failed
        status, _, body = self.request('/api/v2/snapshot', headers=self.login())
        self.assertEqual(status, 500)
        self.assertNotIn(str(self.source).encode(), body)
        self.assertNotIn(b'hidden', body)
        self.assertNotIn(b'Traceback', body)

    def test_missing_setup_is_honest_and_does_not_create_auth(self):
        self.auth.configured = False
        status, _, body = self.request('/api/auth/status')
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body)['setup_supported'])
        self.assertEqual(self.request('/api/auth/login', 'POST', {'password': 'fixture-password'})[0], 503)
        status, _, body = self.request('/login')
        self.assertEqual(status, 200)
        self.assertIn('기존 콘솔'.encode(), body)
        self.assertNotIn(b'/api/auth/setup', body)
        self.assertFalse((self.source / 'ax-console' / 'data' / 'auth').exists())

    def test_real_auth_instances_isolated_factory_has_no_file_writes(self):
        other_source = Path(self.tmp.name) / 'other-source'
        self.seed_auth(self.source / 'ax-console' / 'data' / 'auth')
        before = self.file_state(self.source)
        servers = []
        with patch.dict(os.environ, {}, clear=True), patch('threading.Thread.start', side_effect=AssertionError('background')):
            for root in (self.source, other_source):
                server = self.module.create_server(source_root=root, web_root=self.web,
                                                   snapshot_builder=self.snapshot)
                servers.append(server)
                self.addCleanup(server.server_close)
                self.assertFalse((root / 'ax-console' / 'data' / 'auth' / 'web-v2').exists())
        first, second = (s.auth_backend for s in servers)
        self.assertTrue(first.is_setup())
        self.assertFalse(second.is_setup())
        self.assertNotEqual(first.AUTH, second.AUTH)
        self.assertFalse(first.KEYFILE.exists())
        self.assertFalse(second.KEYFILE.exists())
        self.assertEqual(self.file_state(self.source), before)

    def test_real_auth_over_http_and_explicit_auth_directory(self):
        auth_dir = Path(self.tmp.name) / 'explicit-auth'
        legacy = self.seed_auth(auth_dir)
        legacy_token = legacy.new_session('original-console')
        legacy_before = self.file_state(auth_dir)
        with patch.dict(os.environ, {'AX_AUTH_DIR': str(auth_dir)}):
            server = self.module.create_server(source_root=self.source, web_root=self.web,
                                               snapshot_builder=self.snapshot)
        self.addCleanup(server.server_close)
        self.assertEqual(self.file_state(auth_dir), legacy_before)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), thread.join()))
        status, headers, _ = self.request('/api/auth/login', 'POST', {'password': 'fixture-password'}, server=server)
        self.assertEqual(status, 200)
        self.assertTrue(headers['Set-Cookie'].startswith('ax_web_session='))
        self.assertEqual(server.auth_backend.SESSIONS, auth_dir.resolve() / 'web-v2' / 'sessions.json')
        cookie = {'Cookie': headers['Set-Cookie'].split(';')[0]}
        old_cookie = {'Cookie': 'ax_session=' + legacy_token}
        self.assertEqual(self.request('/api/v2/snapshot', headers=old_cookie, server=server)[0], 401)
        self.assertEqual(self.request('/api/v2/snapshot', headers=cookie, server=server)[0], 200)
        self.assertEqual(self.request('/api/auth/logout', 'POST', {}, cookie, server=server)[0], 200)
        self.assertEqual(self.request('/api/v2/snapshot', headers=cookie, server=server)[0], 401)
        self.assertFalse((auth_dir / 'internal.key').exists())
        self.assertFalse((self.source / 'ax-console' / 'data' / 'auth').exists())
        self.assertEqual({name: self.file_state(auth_dir)[name] for name in legacy_before}, legacy_before)
        self.assertTrue(legacy.check(legacy_token))
        self.assertEqual(legacy.COOKIE, 'ax_session')

    def test_web_session_lock_serializes_other_processes(self):
        auth_dir = Path(self.tmp.name) / 'lock-auth'
        self.seed_auth(auth_dir)
        session_dir = auth_dir / 'web-v2'
        session_dir.mkdir()
        lock_file = session_dir / 'sessions.lock'
        script = '''import importlib.util, os, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location('child_web_server', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
backend = module._load_auth(Path(sys.argv[2]))
print('ready', flush=True)
sys.stdin.readline()
token = backend.new_session('second-process')
print(token, flush=True)
'''
        with lock_file.open('w') as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            child = subprocess.Popen([sys.executable, '-u', '-c', script, str(APP / 'web_server.py'), str(self.source)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     env={**os.environ, 'AX_AUTH_DIR': str(auth_dir)})
            def close_child():
                if child.poll() is None:
                    child.kill()
                child.communicate()
            self.addCleanup(close_child)
            self.assertEqual(child.stdout.readline(), b'ready\n')
            child.stdin.write(b'go\n')
            child.stdin.flush()
            try:
                readable, _, _ = select.select([child.stdout], [], [], 0.2)
                self.assertEqual(readable, [], '다른 프로세스가 보유한 세션 잠금을 기다려야 합니다')
            finally:
                fcntl.flock(held, fcntl.LOCK_UN)
            output, error = child.communicate(timeout=5)
            self.assertEqual(child.returncode, 0, error.decode())
            self.assertTrue(output.strip())
        stored = json.loads((session_dir / 'sessions.json').read_text())
        self.assertEqual(len(stored), 1)

    def test_password_change_revokes_existing_web_session(self):
        legacy, server = self.real_auth_fixture()
        cookie = self.real_login(server)
        self.assertEqual(self.request('/api/v2/snapshot', headers=cookie, server=server)[0], 200)
        legacy.change_password('fixture-password', 'changed-password')
        before = self.file_state(legacy.DIR)
        self.assertEqual(self.request('/api/v2/snapshot', headers=cookie, server=server)[0], 401)
        self.assertFalse(json.loads(self.request('/api/auth/status', headers=cookie, server=server)[2])['logged_in'])
        self.assertEqual(self.file_state(legacy.DIR), before)
        fresh_cookie = self.real_login(server, 'changed-password')
        self.assertEqual(self.request('/api/v2/snapshot', headers=fresh_cookie, server=server)[0], 200)
        self.assertEqual(self.request('/api/v2/snapshot', headers=cookie, server=server)[0], 401)

    def test_deleted_and_recreated_auth_file_does_not_revive_session(self):
        legacy, server = self.real_auth_fixture()
        cookie = self.real_login(server)
        original = legacy.AUTH.read_bytes()
        legacy.AUTH.unlink()
        self.assertEqual(self.request('/api/v2/snapshot', headers=cookie, server=server)[0], 401)
        # 같은 바이트를 복원해도 이전 파일의 세션을 되살리지 않는다.
        legacy.AUTH.write_bytes(original)
        self.assertEqual(self.request('/api/v2/snapshot', headers=cookie, server=server)[0], 401)
        self.real_login(server)

    def test_unversioned_existing_web_session_is_rejected(self):
        _, server = self.real_auth_fixture()
        token = 'existing-session-without-password-version'
        now = int(time.time())
        session_file = server.auth_backend.SESSIONS
        session_file.parent.mkdir(parents=True, exist_ok=True)
        session_file.write_text(json.dumps({hashlib.sha256(token.encode()).hexdigest(): {
            'created': now, 'last': now, 'ua': 'old-web-version'}}))
        cookie = {'Cookie': 'ax_web_session=' + token}
        self.assertEqual(self.request('/api/v2/snapshot', headers=cookie, server=server)[0], 401)
        self.real_login(server)
        self.assertEqual(self.request('/api/v2/snapshot', headers=cookie, server=server)[0], 401)

    def test_password_change_between_verify_and_issue_rejects_login(self):
        legacy, server = self.real_auth_fixture()
        real_verify = server.auth_backend.verify

        def verify_then_change(password, ip):
            verified = real_verify(password, ip)
            legacy.change_password('fixture-password', 'changed-password')
            return verified

        with patch.object(server.auth_backend, 'verify', side_effect=verify_then_change):
            status, headers, _ = self.request('/api/auth/login', 'POST', {'password': 'fixture-password'}, server=server)
        self.assertEqual(status, 401)
        self.assertNotIn('Set-Cookie', headers)
        self.real_login(server, 'changed-password')

    def test_login_uses_system_font_without_missing_font_request(self):
        original = (APP / 'login.html').read_bytes()
        status, _, body = self.request('/login')
        self.assertEqual(status, 200)
        self.assertNotIn(b'url(/fonts/', body)
        self.assertIn(b'-apple-system,sans-serif', body)
        self.assertEqual((APP / 'login.html').read_bytes(), original)

    def test_default_builder_reads_only_explicit_launchagents_directory(self):
        agents = Path(self.tmp.name) / 'explicit-launchagents'
        agents.mkdir()
        (agents / 'com.smuds.fixture.plist').write_bytes(plistlib.dumps({
            'Label': 'com.smuds.fixture', 'StartCalendarInterval': {'Hour': 19, 'Minute': 0}}))
        before_source, before_agents = self.file_state(self.source), self.file_state(agents)
        with patch.dict(os.environ, {'AX_LAUNCHAGENTS_DIR': str(agents)}):
            server = self.module.create_server(source_root=self.source, web_root=self.web, auth_backend=self.auth)
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), thread.join()))
        cookie = self.login()
        status, _, body = self.request('/api/v2/snapshot', headers=cookie, server=server)
        self.assertEqual(status, 200)
        snapshot = json.loads(body)
        self.assertEqual(len(snapshot['schedule']), 1)
        self.assertEqual(snapshot['schedule'][0]['kind'], 'local_request')
        self.assertIsNotNone(snapshot['schedule'][0]['scheduled_at'])
        self.assertEqual(self.file_state(self.source), before_source)
        self.assertEqual(self.file_state(agents), before_agents)

    def test_internal_key_only_if_existing_and_not_exposed(self):
        keyfile = self.source / 'internal.key'
        self.auth.KEYFILE = keyfile
        self.assertEqual(self.request('/api/v2/snapshot', headers={'X-AX-Internal': 'fixture-key'})[0], 401)
        self.assertFalse(keyfile.exists())
        keyfile.write_text('fixture-key')
        self.assertEqual(self.request('/api/v2/snapshot', headers={'X-AX-Internal': 'fixture-key'})[0], 200)
        self.assertEqual(self.request('/api/v2/snapshot', headers={'X-AX-Internal': 'wrong-key'})[0], 401)
        self.assertNotIn(b'fixture-key', self.request('/', headers=self.login())[2])

    def test_factory_rejects_non_loopback_bind(self):
        for host in ('0.0.0.0', '192.168.1.2', 'example.com', ''):
            with self.subTest(host=host), self.assertRaises(ValueError):
                self.module.create_server(host, source_root=self.source, web_root=self.web,
                                          auth_backend=self.auth, snapshot_builder=self.snapshot)


class ManagedWebServerTests(unittest.TestCase):
    setUpClass = classmethod(WebServerTests.setUpClass.__func__)
    request = WebServerTests.request
    login = WebServerTests.login
    stop = WebServerTests.stop
    file_state = staticmethod(WebServerTests.file_state)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / 'source'
        self.source.mkdir()
        (self.source / 'legacy.json').write_text('{"original":"keep"}')
        self.workspace = Path(self.tmp.name) / 'workspace'
        self.auth = FakeAuth()
        self.server = self.module.create_server(source_root=self.source, web_root=APP / 'web',
                                               auth_backend=self.auth, workspace_root=self.workspace)
        self.assertFalse(self.workspace.exists(), 'factory must not initialize storage')
        self.server.launchagents_dir = Path(self.tmp.name) / 'agents'
        self.server.content_store.initialize()
        self.server.integration_store.initialize()
        self.source_before = self.file_state(self.source)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.cookie = self.login()

    def create(self):
        status, _, body = self.request('/api/v2/contents', 'POST', {
            'owner_account_id': 'personal', 'title': '개인 원본', 'kind': 'article', 'original': '본문',
            'variants': [{'destination_account_id': 'dept', 'platform': 'youtube', 'text': '학과 변환'}]}, self.cookie)
        self.assertEqual(status, 201, body)
        return json.loads(body)

    def raw(self, path, body=b'', headers=None, method='POST', authenticated=True):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        conn.request(method, path, body=body, headers={**(self.cookie if authenticated else {}), **(headers or {})})
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result

    def test_create_scope_update_revisions_and_manual_review(self):
        item = self.create()
        path = '/api/v2/contents/' + item['id']
        scoped = json.loads(self.request('/api/v2/contents?account=dept', headers=self.cookie)[2])
        self.assertEqual(scoped['items'][0]['owner_account_id'], 'personal')
        snapshot = json.loads(self.request('/api/v2/snapshot?account=dept', headers=self.cookie)[2])
        self.assertTrue(snapshot['workspace_writable'])
        self.assertEqual(snapshot['contents'][0]['target_accounts'], ['dept'])
        self.assertEqual(snapshot['deliveries'], [])
        edit = {'expected_revision': 1, 'title': '수정', 'kind': 'article', 'original': '새 본문'}
        status, _, body = self.request(path, 'PUT', edit, self.cookie)
        self.assertEqual(status, 200, body)
        updated = json.loads(body)
        self.assertEqual(updated['revision'], 2)
        self.assertEqual(self.request(path, 'PUT', edit, self.cookie)[0], 409)
        self.assertEqual(json.loads(self.request(path + '?revision=1', headers=self.cookie)[2])['original'], '본문')
        revisions = json.loads(self.request(path + '/revisions', headers=self.cookie)[2])
        self.assertEqual([row['revision'] for row in revisions['items']], [1, 2])
        review = {'revision': 2, 'manifest_hash': updated['manifest_hash'], 'kind': 'source', 'decision': 'pass', 'notes': '사람 확인'}
        status, _, body = self.request(path + '/reviews', 'POST', review, self.cookie)
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)['reviews'][0]['method'], 'manual')
        self.assertEqual(json.loads(body)['status'], 'idea')
        review['manifest_hash'] = '0' * 64
        self.assertEqual(self.request(path + '/reviews', 'POST', review, self.cookie)[0], 409)
        self.assertEqual(self.file_state(self.source), self.source_before)

    def test_asset_roundtrip_metadata_cas_range_and_integrity(self):
        from urllib.parse import quote
        item = self.create()
        path = '/api/v2/contents/' + item['id'] + '/assets'
        # PNG signature is the store's accepted minimum; no executable format involved.
        data = b'\x89PNG\r\n\x1a\nfixture'
        headers = {'Content-Type': 'image/png', 'X-AX-Filename': quote('그림.png'), 'X-AX-Expected-Revision': '1'}
        status, _, body = self.raw(path, data, headers)
        self.assertEqual(status, 200, body)
        saved = json.loads(body)
        asset = saved['assets'][0]
        status, response_headers, raw = self.raw(asset['url'], method='GET')
        self.assertEqual((status, raw), (200, data))
        self.assertEqual(response_headers['Content-Type'], 'image/png')
        self.assertEqual(response_headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response_headers['Cache-Control'], 'no-store')
        self.assertIn("filename*=UTF-8''%", response_headers['Content-Disposition'])
        self.assertEqual(self.raw(asset['url'], headers={'Range': 'bytes=0-2'}, method='GET')[0], 416)
        self.assertEqual(self.raw(path, data, headers)[0], 409)
        headers['X-AX-Expected-Revision'] = '2'
        for filename in ('..%2Fsecret.png', '%00bad.png', '%zz', '%FF.png'):
            self.assertEqual(self.raw(path, data, {**headers, 'X-AX-Filename': filename})[0], 400)
        self.assertEqual(self.raw(path, b'<svg/>', {**headers, 'Content-Type': 'image/svg+xml'})[0], 415)
        self.assertEqual(self.raw(path, data, {**headers, 'Content-Length': str(100 * 1024 * 1024 + 1)})[0], 413)
        physical = next(p for p in self.workspace.rglob(asset['id']) if p.is_file())
        physical.write_bytes(b'corrupt')
        status, _, body = self.raw(asset['url'], method='GET')
        self.assertEqual(status, 503)
        self.assertNotIn(str(self.workspace).encode(), body)

    def test_auth_and_csrf_before_body_schema_and_invalid_queries(self):
        path = '/api/v2/contents'
        self.assertEqual(self.raw(path, headers={'Content-Length': '100000'}, authenticated=False)[0], 401)
        self.assertEqual(self.raw(path, headers={'Content-Length': '100000', 'Origin': 'http://evil.example'})[0], 403)
        for body in ([], {'title': 'x', 'kind': 'article'}, {'owner_account_id': 'all', 'title': 'x', 'kind': 'article'},
                     {'owner_account_id': 'personal', 'title': 'x', 'kind': 'article', 'token': 'forbidden'}):
            self.assertEqual(self.request(path, 'POST', body, self.cookie)[0], 400)
        self.assertEqual(self.raw(path, b'', {'Content-Type': 'application/json', 'Content-Length': str(1024 * 1024 + 1)})[0], 413)
        for raw in (b'{"owner_account_id":"personal","title":"a","title":"b","kind":"article"}',
                    b'{"owner_account_id":"personal","title":NaN,"kind":"article"}', b'\xff', b'[]'):
            self.assertEqual(self.raw(path, raw, {'Content-Type': 'application/json'})[0], 400)
        item = self.create()
        for suffix in ('?revision=0', '?revision=1&revision=2', '?account=personal'):
            self.assertEqual(self.request(path + '/' + item['id'] + suffix, headers=self.cookie)[0], 400)
        for suffix in ('?account=all&account=dept', '?root=x', '?revision=1'):
            self.assertEqual(self.request(path + suffix, headers=self.cookie)[0], 400)
        self.assertEqual(self.request(path + '/legacy_123', 'PUT', {}, self.cookie)[0], 404)
        self.assertEqual(self.request(path + '/' + item['id'], 'PUT', {
            'expected_revision': 1, 'title': 'x', 'kind': 'article', 'owner_account_id': 'dept'}, self.cookie)[0], 400)

    def test_short_body_and_duplicate_asset_header_rejected(self):
        item = self.create()
        path = '/api/v2/contents/' + item['id'] + '/assets'
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        conn.putrequest('POST', path)
        for name, value in {**self.cookie, 'Content-Type': 'image/png', 'Content-Length': '30',
                            'X-AX-Filename': 'a.png', 'X-AX-Expected-Revision': '1'}.items():
            conn.putheader(name, value)
        conn.endheaders(b'short')
        conn.sock.shutdown(1)
        response = conn.getresponse()
        self.assertEqual(response.status, 400)
        response.read()
        conn.close()
        for header in ('X-AX-Filename', 'X-AX-Expected-Revision'):
            conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
            conn.putrequest('POST', path)
            conn.putheader('Cookie', self.cookie['Cookie'])
            conn.putheader(header, '1')
            conn.putheader(header, '2')
            conn.endheaders()
            response = conn.getresponse()
            self.assertEqual(response.status, 400)
            response.read()
            conn.close()

    def test_settings_scoped_cas_persistence_and_secret_rejection(self):
        path = '/api/v2/integrations/settings'
        payload = {'account_id': 'dept', 'provider_id': 'metricool', 'connection_id': 'main', 'expected_revision': 0,
                   'platform': 'instagram', 'target_label': '학과', 'enabled_preference': True, 'notes': '사용 선호'}
        status, _, raw = self.request(path, 'PUT', payload, self.cookie)
        self.assertEqual(status, 200, raw)
        saved = json.loads(raw)
        self.assertEqual(saved['connection_status'], 'unknown')
        self.assertEqual(saved['execution_status'], 'not_connected')
        self.assertEqual(self.request(path, 'PUT', payload, self.cookie)[0], 409)
        self.assertEqual(json.loads(self.request(path + '?account=personal', headers=self.cookie)[2]), {'items': []})
        self.assertEqual(len(json.loads(self.request(path + '?account=dept', headers=self.cookie)[2])['items']), 1)
        self.assertEqual(self.request(path, 'PUT', {**payload, 'token': 'no'}, self.cookie)[0], 400)
        self.assertEqual(self.request(path, 'PUT', {**payload, 'platform': 'shell'}, self.cookie)[0], 400)
        from common.operations.integration_store import IntegrationStore
        self.assertEqual(IntegrationStore(self.workspace).list('dept')[0], saved)
        self.assertEqual(self.file_state(self.source), self.source_before)

    def test_factory_uninitialized_and_no_workspace_modes(self):
        for workspace in (None, Path(self.tmp.name) / 'not-initialized'):
            server = self.module.create_server(source_root=self.source, web_root=APP / 'web', auth_backend=self.auth,
                                               workspace_root=workspace)
            server.launchagents_dir = Path(self.tmp.name) / 'agents'
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                status, _, body = self.request('/api/v2/contents', 'POST', {}, self.cookie, server=server)
                self.assertEqual(status, 405 if workspace is None else 503, body)
                self.assertEqual(json.loads(self.request('/api/v2/contents', headers=self.cookie, server=server)[2]), {'items': []})
                if workspace:
                    snapshot = json.loads(self.request('/api/v2/snapshot', headers=self.cookie, server=server)[2])
                    self.assertFalse(snapshot['workspace_writable'])
                    self.assertTrue(snapshot['warnings'])
                    self.assertFalse(workspace.exists())
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
        for workspace in (self.source, self.source / 'new', self.source.parent):
            with self.assertRaises(ValueError):
                self.module.create_server(source_root=self.source, web_root=APP / 'web', workspace_root=workspace)


if __name__ == '__main__':
    unittest.main()
