"""실제 service/store/HTTP의 통합 수락. 실제 provider/native/운영 자료 접근 0."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from tests import test_web_oauth as http_tests
from tests.integration.test_local_toolkit_acceptance import product_webroot, overlay


class OAuthConnectionIntegration(unittest.TestCase):
    def setUp(self):
        self.http = http_tests.OAuthHTTPTests(); self.http.setUp(); self.addCleanup(self.http.doCleanups)

    def flow(self, *, new=True, key='start'):
        h = self.http
        body = h.fixture.body(key)
        if new: body['connection_id'] = None
        status, item, _ = h.post('/api/v2/oauth/attempts', body)
        self.assertEqual(200, status)
        from urllib.parse import parse_qs, urlsplit
        state = parse_qs(urlsplit(item['authorize_url']).query)['state'][0]
        self.assertEqual(303, h.callback(state)[0])
        self.assertNotIn('exchange', h.fixture.provider.calls)
        path = '/api/v2/oauth/attempts/' + item['attempt_id']
        self.assertEqual([], h.json('/api/v2/oauth/result', cookie='other-session')[1]['items'])
        self.assertEqual(404, h.json(path, cookie='other-session')[0])
        item = h.json(path)[1]
        for operation in ('continue', 'inspect'):
            status, item, _ = h.post(path + '/' + operation, dict(request_key=operation+key, expected_revision=item['revision']))
            self.assertEqual(200, status)
        self.assertEqual('target_confirmation', item['state'])
        self.assertEqual(0, len([r for r in h.json('/api/v2/oauth/connections')[1]['items'] if r.get('state') == 'connected']))
        return item

    def confirm(self, item):
        p = item['target_proposal']
        status, result, _ = self.http.post('/api/v2/oauth/targets/' + p['proposal_id'] + '/confirm',
            dict(request_key='confirm',expected_base_revision=p['expected_base_revision'],
                 expected_connection_revision=p['expected_connection_revision']))
        self.assertEqual(200, status)
        return result

    def test_new_identity_explicit_proposal_restart_new_session_lifecycle_and_original_preserved(self):
        h = self.http
        original = h.fixture.registry.connections['personal.youtube']
        item = self.flow(); self.assertTrue(item['connection_id'].startswith('oauth.'))
        result = self.confirm(item); self.assertFalse(result['execution_enabled'])
        # 동일 SQLite + 동일 MemoryVault를 다시 조립한다. 실제 native는 구성하지 않는다.
        h.server.oauth_service = h.fixture.make_service()
        status, rows, _ = h.json('/api/v2/oauth/connections?account=personal',cookie='other-session')
        self.assertEqual(200,status)
        row = next(r for r in rows['items'] if r['id'] == item['connection_id'])
        self.assertIn('refresh',row['available_actions']); self.assertEqual(1,row['connection_revision'])
        # 새 세션 CSRF로 명시 관리. 미완 attempt 소유권은 여전히 이전 세션이다.
        path = '/api/v2/oauth/connections/'+row['id']
        body = dict(request_key='new-session-refresh',expected_base_revision=rows['base_revision'],expected_connection_revision=row['connection_revision'])
        status, refreshed, _ = h.json(path+'/refresh','POST',body,cookie='other-session',headers={'X-CSRF-Token':h.csrf('other-session')})
        self.assertEqual(200,status);self.assertGreater(refreshed['connection_revision'],row['connection_revision'])
        self.assertEqual(original,h.fixture.registry.connections['personal.youtube'])
        self.assertIsNone(original.credential_ref)
        self.assertFalse(h.workspace.exists())
        h.fixture.assert_public(rows);h.fixture.assert_public(refreshed)

    def test_wrong_account_target_and_stale_cas_preserve_original_connection(self):
        h = self.http
        body = dict(h.fixture.body(), account_id='dept')
        self.assertEqual(409,h.post('/api/v2/oauth/attempts',body)[0])
        self.assertEqual([],h.fixture.provider.calls)
        item = self.flow(new=False,key='valid');p = item['target_proposal']
        self.assertEqual(409,h.post('/api/v2/oauth/targets/'+p['proposal_id']+'/confirm',
            dict(request_key='stale',expected_base_revision='stale',expected_connection_revision=0))[0])
        self.assertIsNone(h.fixture.registry.connections['personal.youtube'].credential_ref)
        self.assertEqual(200,h.json('/api/v2/oauth/attempts/'+item['attempt_id'])[0])

    def test_optional_overlay_preserves_all_modules_and_root_absolute_shell_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'web';product_webroot(root)
            index=(root/'index.html').read_text()
            self.assertIn('href="/web/styles.css"',index);self.assertIn('src="/web/app.js"',index)
            for name in ('oauth_api.js','oauth_controller.js','oauth_panel.js'):
                self.assertTrue((root/name).is_file())
            # 再適用は original/desired の両 SHA を許す。
            import json
            manifest=Path('.superpowers/sdd/2026-11-01-sns-oauth-connections/web-artifacts/manifest.json')
            if manifest.exists():overlay(root,json.loads(manifest.read_text()))


class OAuthOverlayFallback(unittest.TestCase):
    def test_missing_optional_manifests_use_tracked_checkout_without_skip(self):
        from unittest.mock import patch
        from tests.integration import test_local_toolkit_acceptance as staged
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with patch.object(staged,'OAUTH_MANIFEST',root/'missing-oauth.json'),patch.object(staged,'MANIFEST',root/'missing-toolkit.json'):
                staged.product_webroot(root/'web')
            self.assertEqual((staged.ROOT/'ax-console/app/web/app.js').read_bytes(),(root/'web/app.js').read_bytes())

if __name__ == '__main__':unittest.main()
