"""외부 HTTPS 정책을 실제 loopback HTTP로 시험하며 운영 인증은 사용하지 않는다."""
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from tests import test_web_server as fixtures

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ax-console' / 'app'))
import web_server
from web_external_access import ExternalAccessPolicy

ORIGIN = 'https://console.example.com'
HOST = 'console.example.com'


class FakeExternalAuth(fixtures.FakeAuth):
    def set_cookie(self, token):
        return f'ax_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=3600'

    def clear_cookie(self):
        return 'ax_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'


class WebExternalAccessHTTPTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'source').mkdir()
        (self.root / 'web').mkdir()
        (self.root / 'web' / 'app.js').write_text('fixture')
        self.auth = FakeExternalAuth()
        self.server = self.build(external_access_policy=ExternalAccessPolicy(ORIGIN))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)

    def build(self, **kwargs):
        return web_server.create_server(source_root=self.root / 'source', web_root=self.root / 'web',
            auth_backend=self.auth,
            snapshot_builder=lambda root, account='all', **kw: {'scope': account}, **kwargs)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def request(self, path, method='GET', data=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            connection.request(method, path, body=json.dumps(data) if data is not None else None,
                headers={'Host': HOST, 'Content-Type': 'application/json', **(headers or {})})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def login(self):
        status, headers, _ = self.request('/api/auth/login', 'POST', {'password': 'fixture-password'},
            {'Origin': ORIGIN})
        self.assertEqual(status, 200)
        cookie = headers['Set-Cookie']
        self.assertIn('; Secure', cookie)
        self.assertNotIn('Domain=', cookie)
        return {'Cookie': cookie.split(';', 1)[0], 'Origin': ORIGIN}

    def test_public_login_protected_assets_api_and_separate_media_listener(self):
        status, headers, _ = self.request('/login')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Strict-Transport-Security'], 'max-age=86400')
        for path in ('/web/app.js', '/api/v2/snapshot', '/media/v1/' + 'a' * 64):
            self.assertEqual(self.request(path)[0], 401)
        cookie = self.login()
        self.assertEqual(self.request('/media/v1/' + 'a' * 64, headers=cookie)[0], 404)

    def test_host_origin_cross_site_and_forwarded_headers_cannot_bypass(self):
        cookie = self.login()
        for extra in ({'Host': 'localhost'}, {'Host': f'127.0.0.1:{self.server.server_port}'},
                {'Host': HOST + ':443'}, {'Origin': 'http://' + HOST},
                {'Origin': 'https://evil.example.com'}, {'Sec-Fetch-Site': 'cross-site'},
                {'Origin': 'http://' + HOST, 'X-Forwarded-Proto': 'https', 'X-Forwarded-Host': HOST},
                {'Origin': 'http://' + HOST, 'Forwarded': 'proto=https;host=' + HOST}):
            with self.subTest(extra=extra):
                self.assertEqual(self.request('/api/v2/snapshot', headers={**cookie, **extra})[0], 403)

    def test_internal_key_header_rejected_even_with_session_without_keyfile_read(self):
        cookie = self.login()
        self.auth.KEYFILE = self.root / 'must-not-read'
        with patch.object(Path, 'open', side_effect=AssertionError('내부키 읽기 금지')):
            for key in ('', 'fixture-internal-key'):
                self.assertEqual(self.request('/api/v2/snapshot',
                    headers={**cookie, 'X-AX-Internal': key})[0], 403)

    def test_secure_session_preserves_single_operator_account_filters_and_logout(self):
        cookie = self.login()
        for account in ('personal', 'dept'):
            status, _, body = self.request('/api/v2/snapshot?account=' + account, headers=cookie)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)['scope'], account)
        status, headers, _ = self.request('/api/auth/logout', 'POST', {}, cookie)
        self.assertEqual(status, 200)
        self.assertIn('Max-Age=0', headers['Set-Cookie'])
        self.assertIn('; Secure', headers['Set-Cookie'])
        self.assertNotIn('Domain=', headers['Set-Cookie'])
        self.assertEqual(self.request('/api/v2/snapshot', headers=cookie)[0], 401)

    def test_duplicate_security_headers_rejected(self):
        for duplicate, value in (('Host', HOST), ('Origin', ORIGIN), ('X-AX-Internal', 'fixture')):
            connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
            try:
                connection.putrequest('GET', '/login', skip_host=True)
                connection.putheader('Host', HOST)
                if duplicate != 'Host':
                    connection.putheader(duplicate, value)
                connection.putheader(duplicate, value)
                connection.endheaders()
                response = connection.getresponse()
                self.assertEqual(response.status, 400)
                response.read()
            finally:
                connection.close()

    def test_external_policy_does_not_authorize_oauth_callback(self):
        self.assertEqual(self.request('/oauth/callback/google')[0], 403)

    def test_factory_rejects_untyped_policy_before_bind_and_local_default_stays_local(self):
        with patch.object(web_server._WebServer, '__init__', side_effect=AssertionError('소켓 생성 금지')):
            for policy in ({'public_origin': ORIGIN}, ORIGIN, True):
                with self.assertRaises(ValueError):
                    self.build(external_access_policy=policy)
        local = self.build()
        try:
            self.assertIsNone(local.external_access_policy)
            self.assertNotIn(HOST, local.allowed_hosts)
            self.assertEqual(local.server_address[0], '127.0.0.1')
        finally:
            local.server_close()
