"""임시 schema2·메모리 owned vault·fake provider의 실제 loopback HTTP 경계."""
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from tests import test_web_oauth as web_tests
from common.operations.managed_connections import ManagedConnectionStore
from common.operations.oauth_stage_backend import MemoryScopedRawBackend, OwnedStageBackend
from common.operations.oauth_stage_models import OwnedCredentialRef, logical_ref
from common.operations.oauth_stage_store import OAuthStageStore, migrate_to_owned_schema
from common.operations.oauth_store import OAuthAttemptStore
from common.operations.oauth_workspace import initialize_workspace_owner, oauth_write_guard


class ObservedMemoryBackend(MemoryScopedRawBackend):
    def __init__(self):
        super().__init__()
        self.calls = []

    def add(self, address, value):
        self.calls.append('add')
        return super().add(address, value)

    def copy(self, address):
        self.calls.append('copy')
        return super().copy(address)

    def delete(self, address):
        self.calls.append('delete')
        return super().delete(address)


class OwnedOAuthHTTPTests(unittest.TestCase):
    def setUp(self):
        # TestCase를 직접 import/상속하지 않아 기존 HTTP 시험이 중복 발견되지 않는다.
        self.http = web_tests.OAuthHTTPTests()
        self.addCleanup(self.http.doCleanups)
        self.http.setUp()
        self.fixture = self.http.fixture
        self.context = initialize_workspace_owner(self.fixture.tmp.name)
        with oauth_write_guard(self.context):
            migrate_to_owned_schema(self.context)
        self.raw = ObservedMemoryBackend()
        self.stages = OAuthStageStore(self.context, self.fixture.clock)
        self.owned = OwnedStageBackend(self.context, self.raw)
        self.http.server.oauth_service = self.make_service()
        (self.http.source / 'source-sentinel.json').write_bytes(b'{"source":"unchanged"}\n')
        self.source_before = self.files(self.http.source)
        self.registry_before = json.dumps(self.fixture.registry.to_dict(), sort_keys=True)

    def tearDown(self):
        self.assertEqual(self.source_before, self.files(self.http.source))
        self.assertEqual(self.registry_before, json.dumps(self.fixture.registry.to_dict(), sort_keys=True))
        self.assertIsNone(self.fixture.registry.connections['personal.youtube'].credential_ref)
        self.assertFalse(self.http.workspace.exists())
        self.assertNotIn('delete', self.raw.calls)

    @staticmethod
    def files(root):
        return {str(p.relative_to(root)): p.read_bytes() for p in Path(root).rglob('*') if p.is_file()}

    def make_service(self):
        # 모든 자격 I/O가 owned 경로로 가도록 legacy vault도 주입하지 않는다.
        return self.fixture.make_service(
            attempt_store=OAuthAttemptStore(self.fixture.tmp.name, self.fixture.clock),
            connection_store=ManagedConnectionStore(self.fixture.tmp.name, self.fixture.clock),
            backend=None, workspace_context=self.context,
            stage_store=OAuthStageStore(self.context, self.fixture.clock),
            owned_backend=OwnedStageBackend(self.context, self.raw))

    def post(self, path, body, cookie='fixture'):
        return self.http.json(path, 'POST', body, cookie=cookie,
                              headers={'X-CSRF-Token': self.http.csrf(cookie)})

    def staged(self):
        started, state = self.http.start()
        self.assertEqual(303, self.http.callback(state)[0])
        path = '/api/v2/oauth/attempts/' + started['attempt_id']
        status, item, _ = self.http.json(path)
        self.assertEqual(200, status)
        self.assertEqual('callback_staged', item['state'])
        status, result, _ = self.http.json('/api/v2/oauth/result')
        self.assertEqual(200, status)
        self.assertEqual([item], result['items'])
        return path, item, state

    def advance(self, path, item, action):
        status, result, _ = self.post(path + '/' + action,
                                     dict(request_key=action, expected_revision=item['revision']))
        self.assertEqual(200, status)
        self.fixture.assert_public(result)
        return result

    def connected(self):
        path, item, _ = self.staged()
        item = self.advance(path, item, 'continue')
        item = self.advance(path, item, 'inspect')
        status, result, _ = self.post('/api/v2/oauth/targets/' + item['target_proposal']['proposal_id'] + '/confirm',
                                     dict(request_key='confirm', expected_base_revision='base', expected_connection_revision=0))
        self.assertEqual(200, status)
        self.assertEqual('connected', result['state'])
        return path, result

    def assert_pure_reads(self, paths, *, factory=False):
        before = self.files(self.context.root)
        snapshot = self.stages.recovery_snapshot(self.context.owner)
        calls = list(self.raw.calls), list(self.fixture.provider.calls)
        output = io.StringIO()
        with ExitStack() as stack, redirect_stdout(output), redirect_stderr(output):
            for obj, names in ((self.raw, ('add', 'copy', 'delete')),
                               (self.fixture.vault, ('get', 'put', 'delete')),
                               (self.fixture.provider, ('authorize', 'exchange', 'inspect', 'refresh', 'revoke'))):
                for name in names:
                    stack.enter_context(patch.object(obj, name, side_effect=AssertionError('조회 중 외부 I/O')))
            stack.enter_context(patch('common.operations.oauth_service.oauth_write_guard',
                                      side_effect=AssertionError('조회 중 writer guard')))
            stack.enter_context(patch('logging.Logger._log', side_effect=AssertionError('조회 중 logging')))
            self.http.server.oauth_service = self.make_service()
            if factory:
                server = self.http.module.create_server(
                    source_root=self.http.source, workspace_root=self.http.workspace,
                    web_root=web_tests.APP / 'web', auth_backend=web_tests.CookieAuth(),
                    operations_registry=self.fixture.registry,
                    oauth_service=self.http.server.oauth_service,
                    oauth_callback_policy=self.http.server.oauth_callback_policy, oauth_test_only=True)
                try:
                    self.assertEqual('127.0.0.1', server.server_address[0])
                finally:
                    server.server_close()
            for cookie in ('fixture', 'other-session'):
                for path in paths:
                    expected = 404 if '/attempts/' in path and cookie == 'other-session' else 200
                    status, _, data = self.http.request(path, cookie=cookie)
                    self.assertEqual(expected, status)
                    if path != '/connections/oauth-result':
                        self.fixture.assert_public(json.loads(data))
        self.assertEqual('', output.getvalue())
        self.assertEqual(before, self.files(self.context.root))
        after = self.stages.recovery_snapshot(self.context.owner)
        self.assertEqual((snapshot.graph_revision, snapshot.journal_revision),
                         (after.graph_revision, after.journal_revision))
        self.assertEqual(calls, (self.raw.calls, self.fixture.provider.calls))

    def test_factory_constructor_reopen_and_empty_gets_are_pure(self):
        self.assertEqual('127.0.0.1', self.http.server.server_address[0])
        self.assert_pure_reads(('/api/v2/oauth/catalog', '/api/v2/oauth/connections',
                                '/api/v2/oauth/result', '/api/v2/oauth/csrf',
                                '/api/v2/connections', '/connections/oauth-result'), factory=True)

    def test_connected_gets_and_reopen_are_pure(self):
        path, _ = self.connected()
        self.assert_pure_reads(('/api/v2/oauth/catalog', '/api/v2/oauth/connections',
                                '/api/v2/oauth/result', '/api/v2/oauth/csrf',
                                '/api/v2/connections', '/connections/oauth-result', path), factory=True)

    def test_owned_lifecycle_new_session_preserves_complete_identity(self):
        path, connected = self.connected()
        before = self.fixture.connections_store.snapshot().connections['personal.youtube']['credential_ref']
        self.assertIsInstance(before, OwnedCredentialRef)
        self.http.server.oauth_service = self.make_service()
        status, listing, _ = self.http.json('/api/v2/oauth/connections', cookie='other-session')
        self.assertEqual(200, status)
        self.assertIn('refresh', listing['items'][0]['available_actions'])
        status, refreshed, _ = self.post('/api/v2/oauth/connections/personal.youtube/refresh',
            dict(request_key='rotate-new-session', expected_base_revision='base',
                 expected_connection_revision=listing['items'][0]['connection_revision']), cookie='other-session')
        self.assertEqual(200, status)
        after = self.fixture.connections_store.snapshot().connections['personal.youtube']['credential_ref']
        self.assertIsInstance(after, OwnedCredentialRef)
        for ref in (before, after):
            logical = logical_ref(ref)
            self.assertEqual((self.context.owner.workspace_id, self.context.owner.root_binding),
                             (ref.workspace_id, ref.root_binding))
            self.assertEqual(('autosns.oauth', 'personal', 'youtube', 'personal.youtube', 'token'),
                             (logical.namespace, logical.account_id, logical.platform, logical.connection_id, logical.kind))
        self.assertGreater(logical_ref(after).generation, logical_ref(before).generation)
        self.assertNotEqual(before.stage_id, after.stage_id)
        self.http.server.oauth_service = self.make_service()
        status, disconnected, _ = self.post('/api/v2/oauth/connections/personal.youtube/disconnect',
            dict(request_key='off-new-session', expected_base_revision='base',
                 expected_connection_revision=refreshed['connection_revision']), cookie='other-session')
        self.assertEqual(200, status)
        self.assertEqual('disconnected', disconnected['state'])
        self.assertIsNone(self.fixture.connections_store.snapshot().connections['personal.youtube']['credential_ref'])
        old_binding = hashlib.sha256(b'fixture').hexdigest()
        attempt = self.fixture.attempts.read_owned(connected['attempt_id'], old_binding)
        self.assertEqual(old_binding, attempt['context'].session_binding)
        self.assertEqual(before, attempt['token_ref'])
        snapshot = self.stages.recovery_snapshot(self.context.owner)
        self.assertEqual((), snapshot.blockers)
        refs = {stage.owned_ref for stage in snapshot.stages}
        self.assertTrue({before, after} <= refs)
        self.assertEqual(['authorize', 'exchange', 'inspect', 'refresh'], self.fixture.provider.calls)
        for result in (connected, listing, refreshed, disconnected):
            self.fixture.assert_public(result)
            if 'execution_enabled' in result:
                self.assertFalse(result['execution_enabled'])

    def test_incomplete_attempt_and_proposal_reject_foreign_session(self):
        path, item, _ = self.staged()
        self.assertEqual([], self.http.json('/api/v2/oauth/result', cookie='other-session')[1]['items'])
        self.assertEqual(404, self.http.request(path, cookie='other-session')[0])
        raw_before = list(self.raw.calls)
        for action in ('continue', 'inspect'):
            status, _, _ = self.post(path + '/' + action,
                dict(request_key='foreign-' + action, expected_revision=item['revision']), cookie='other-session')
            self.assertEqual(404, status)
        self.assertEqual(raw_before, self.raw.calls)
        self.assertEqual(['authorize'], self.fixture.provider.calls)
        item = self.advance(path, item, 'continue')
        item = self.advance(path, item, 'inspect')
        raw_before = list(self.raw.calls)
        status, _, _ = self.post('/api/v2/oauth/targets/' + item['target_proposal']['proposal_id'] + '/confirm',
            dict(request_key='foreign-confirm', expected_base_revision='base', expected_connection_revision=0), cookie='other-session')
        self.assertEqual(404, status)
        self.assertEqual(raw_before, self.raw.calls)
        self.assertEqual({}, dict(self.fixture.connections_store.snapshot().connections))

    def test_csrf_origin_and_cookie_reject_before_owned_write(self):
        path, item, _ = self.staged()
        token = self.http.csrf()
        body = dict(request_key='blocked', expected_revision=item['revision'])
        before = self.files(self.context.root)
        calls = list(self.raw.calls), list(self.fixture.provider.calls)
        for cookie, headers, expected in (
            (None, {'X-CSRF-Token': token}, 401),
            ('other-session', {'X-CSRF-Token': token}, 403),
            ('fixture', {}, 403),
            ('fixture', {'X-CSRF-Token': token + 'x'}, 403),
            ('fixture', {'X-CSRF-Token': token, 'Origin': None}, 403),
            ('fixture', {'X-CSRF-Token': token, 'Origin': 'https://evil.test'}, 403)):
            self.assertEqual(expected, self.http.request(path + '/continue', 'POST', body,
                                                        cookie=cookie, headers=headers)[0])
        self.assertEqual(before, self.files(self.context.root))
        self.assertEqual(calls, (self.raw.calls, self.fixture.provider.calls))

    def test_factory_and_callback_keep_loopback_host_tls_boundaries(self):
        from web_oauth import OAuthCallbackPolicy
        with self.assertRaises(ValueError):
            self.http.module.create_server(host='0.0.0.0', source_root=self.http.source, web_root=web_tests.APP / 'web')
        with self.assertRaises(ValueError):
            self.http.module.create_server(source_root=self.http.source, web_root=web_tests.APP / 'web',
                operations_registry=self.fixture.registry,
                oauth_callback_policy=self.http.server.oauth_callback_policy)
        _, state = self.http.start()
        before = self.files(self.context.root)
        calls = list(self.raw.calls)
        from urllib.parse import urlencode
        callback = '/oauth/callback/youtube?' + urlencode({'state': state, 'code': 'secret-code'})
        self.assertEqual(403, self.http.request(callback, cookie=None)[0])
        self.http.server.oauth_callback_policy = OAuthCallbackPolicy({'youtube': self.fixture.registration.redirect_uri})
        self.assertEqual(403, self.http.callback(state)[0])
        self.assertEqual(403, self.http.request('/api/v2/oauth/catalog', host='console.test')[0])
        self.assertEqual(before, self.files(self.context.root))
        self.assertEqual(calls, self.raw.calls)
        self.assertEqual(['authorize'], self.fixture.provider.calls)

    def test_callback_result_is_private_and_exchange_remains_explicit_once(self):
        started, state = self.http.start()
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            status, headers, data = self.http.callback(state)
        self.assertEqual(303, status)
        self.assertEqual('/connections/oauth-result', headers['Location'])
        self.assertEqual(('no-store', 'no-referrer'), (headers['Cache-Control'], headers['Referrer-Policy']))
        self.assertEqual(b'', data)
        self.assertEqual('', output.getvalue())
        self.assertEqual(['authorize'], self.fixture.provider.calls)
        self.http.server.oauth_service = self.make_service()
        status, result, _ = self.http.json('/api/v2/oauth/result')
        self.assertEqual(200, status)
        self.assertEqual([started['attempt_id']], [item['attempt_id'] for item in result['items']])
        self.assertEqual('callback_staged', result['items'][0]['state'])
        self.fixture.assert_public(result)
        for secret in (state, 'secret-code', 'secret-access', 'secret-refresh'):
            self.assertNotIn(secret, json.dumps(result) + str(headers) + output.getvalue())
            self.assertNotIn(secret.encode(), (self.context.root / 'oauth.sqlite3').read_bytes())
        self.assertEqual(409, self.http.callback(state)[0])
        path = '/api/v2/oauth/attempts/' + started['attempt_id']
        body = dict(request_key='continue-once', expected_revision=result['items'][0]['revision'])
        first = self.post(path + '/continue', body)
        self.assertEqual(200, first[0])
        self.http.server.oauth_service = self.make_service()
        second = self.post(path + '/continue', body)
        self.assertEqual((first[0], first[1]), (second[0], second[1]))
        self.assertEqual(1, self.fixture.provider.calls.count('exchange'))


if __name__ == '__main__':
    unittest.main()
