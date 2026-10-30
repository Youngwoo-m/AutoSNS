"""임시 원본·인증과 loopback HTTP만 사용하는 조회 서버 회귀 시험."""
import http.client
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
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
        servers = []
        with patch.dict(os.environ, {}, clear=True), patch('threading.Thread.start', side_effect=AssertionError('background')):
            for root in (self.source, other_source):
                server = self.module.create_server(source_root=root, web_root=self.web,
                                                   snapshot_builder=self.snapshot)
                servers.append(server)
                self.addCleanup(server.server_close)
                self.assertFalse((root / 'ax-console' / 'data' / 'auth').exists())
        first, second = (s.auth_backend for s in servers)
        first.setup('fixture-password')
        self.assertTrue(first.is_setup())
        self.assertFalse(second.is_setup())
        self.assertNotEqual(first.AUTH, second.AUTH)
        self.assertFalse(first.KEYFILE.exists())
        self.assertFalse(second.KEYFILE.exists())

    def test_real_auth_over_http_and_explicit_auth_directory(self):
        auth_dir = Path(self.tmp.name) / 'explicit-auth'
        with patch.dict(os.environ, {'AX_AUTH_DIR': str(auth_dir)}):
            server = self.module.create_server(source_root=self.source, web_root=self.web,
                                               snapshot_builder=self.snapshot)
        self.addCleanup(server.server_close)
        self.assertFalse(auth_dir.exists())
        server.auth_backend.setup('fixture-password')
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), thread.join()))
        status, headers, _ = self.request('/api/auth/login', 'POST', {'password': 'fixture-password'}, server=server)
        self.assertEqual(status, 200)
        cookie = {'Cookie': headers['Set-Cookie'].split(';')[0]}
        self.assertEqual(self.request('/api/v2/snapshot', headers=cookie, server=server)[0], 200)
        self.assertEqual(self.request('/api/auth/logout', 'POST', {}, cookie, server=server)[0], 200)
        self.assertEqual(self.request('/api/v2/snapshot', headers=cookie, server=server)[0], 401)
        self.assertFalse((auth_dir / 'internal.key').exists())
        self.assertFalse((self.source / 'ax-console' / 'data' / 'auth').exists())

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


if __name__ == '__main__':
    unittest.main()
