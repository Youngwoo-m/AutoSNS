import dataclasses
import json
import unittest

from common.operations.oauth_catalog import provider_catalog
from common.operations.oauth_models import CredentialRef, TokenBundle
from common.operations.oauth_policy import OAuthPolicy, assert_zero_cost
from common.operations.content_store import StoreError


class OAuthCatalogTests(unittest.TestCase):
    def test_catalog_separates_instagram_login_flows(self):
        items = {p.id: p for p in provider_catalog()}
        self.assertEqual(len(items), 10)
        self.assertNotEqual(items['instagram_login'].login_method, items['instagram_facebook'].login_method)
        self.assertIn('instagram_business_basic', items['instagram_login'].read_scopes)
        self.assertIn('instagram_basic', items['instagram_facebook'].read_scopes)
        self.assertNotIn('instagram_business_basic', items['instagram_facebook'].read_scopes)
        self.assertEqual(items['x'].pkce_mode, 's256')
        self.assertEqual(items['youtube'].pkce_mode, 'unconfirmed')
        self.assertIn('desktop_client_separate_contract', items['youtube'].policy_reasons)

    def test_unknown_cost_has_zero_transport_calls(self):
        calls = []
        for provider in provider_catalog():
            for rule in provider.operations:
                with self.assertRaises(StoreError):
                    assert_zero_cost(rule.operation, rule.endpoint, rule.evidence_revision)
                    calls.append(rule)
        self.assertEqual(calls, [])
        with self.assertRaises(StoreError):
            assert_zero_cost('inspect', 'https://attacker.invalid', 'forged')

    def test_tistory_unsupported_naver_profile_not_publish(self):
        items = {p.id: p for p in provider_catalog()}
        self.assertTrue(all(r.endpoint is None for r in items['tistory'].operations))
        self.assertEqual(items['naver'].publication_scopes, ())
        self.assertEqual(items['naver'].login_method, 'naver_profile')
        self.assertIn('blog_publication_unsupported', items['naver'].policy_reasons)

    def test_read_scope_never_grants_execution(self):
        self.assertFalse(OAuthPolicy().live_enabled)
        for provider in provider_catalog():
            self.assertFalse(set(provider.read_scopes) & set(provider.publication_scopes))
            self.assertFalse(provider.to_dict()['execution_enabled'])
            self.assertFalse(provider.to_dict()['ready'])

    def test_private_values_never_serialize_or_repr(self):
        bundle = TokenBundle('secret-access', 'secret-refresh', 'Bearer', None, ('read',))
        ref = CredentialRef('autosns.oauth', 'personal', 'youtube', 'youtube.personal', 1, 'token')
        for value in (bundle, ref):
            self.assertNotIn('secret-', repr(value))
            self.assertNotIn('youtube.personal', repr(value))
            self.assertEqual(value.to_dict(public=True), {})
            with self.assertRaises(TypeError):
                json.dumps(value)
            with self.assertRaises(TypeError):
                dataclasses.asdict(value)
        with self.assertRaises(AttributeError):
            bundle.access_token = 'changed'

    def test_invalid_reference_is_sanitized(self):
        for args in [('wrong', 'personal', 'youtube', 'id', 1, 'token'),
                     ('autosns.oauth', 'all', 'youtube', 'id', 1, 'token'),
                     ('autosns.oauth', 'personal', 'youtube', 'id', True, 'token')]:
            with self.assertRaises(StoreError) as raised:
                CredentialRef(*args)
            self.assertEqual(str(raised.exception), 'invalid_oauth_model')


if __name__ == '__main__':
    unittest.main()
