import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ax-console' / 'app'))
from web_integrations import validate_settings_body, settings_response
from common.operations.content_store import StoreError

class WebIntegrationTests(unittest.TestCase):
    def test_flat_contract_and_exact_fields(self):
        body = dict(account_id='personal', provider_id='local', connection_id='main', expected_revision=0,
                    platform='kakao', target_label='테스트', enabled_preference=False, notes='')
        account, provider, connection, revision, payload = validate_settings_body(body)
        self.assertEqual((account, provider, connection, revision), ('personal', 'local', 'main', 0))
        self.assertEqual(payload['platform'], 'kakao')
        for extra in ('token', 'connection_status', 'credential_ref', 'scope'):
            with self.assertRaises(StoreError):
                validate_settings_body(dict(body, **{extra: 'secret'}))
        with self.assertRaises(StoreError):
            validate_settings_body({'payload': body})
        self.assertEqual(settings_response([body]), {'items': [body]})
