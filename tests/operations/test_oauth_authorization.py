import unittest
from common.operations.content_store import StoreError
from common.operations.oauth_models import validate_authorization


class AuthorizationMetadataTests(unittest.TestCase):
    def metadata(self):
        return dict(observed_scopes=None, credential_expires_at=None, read_status='not_checked', publication_status='not_checked', credential_status='pending')

    def test_unknown_values_are_preserved_without_granting(self):
        self.assertEqual(validate_authorization(self.metadata()), self.metadata())
        value=self.metadata(); value.update(observed_scopes=['read'], credential_expires_at='2026-11-01T10:00:00+09:00', read_status='verified', credential_status='active')
        result=validate_authorization(value)
        self.assertEqual(result['credential_expires_at'], '2026-11-01T01:00:00+00:00')
        result['observed_scopes'].append('write')
        self.assertEqual(value['observed_scopes'], ['read'])

    def test_secret_and_fabricated_permission_fields_are_rejected(self):
        for field,bad in [('access_token','secret'), ('publication_status','verified'), ('read_status','connected'), ('credential_status','ready'), ('observed_scopes','read'), ('credential_expires_at','2026-11-01T10:00:00')]:
            value=self.metadata(); value[field]=bad
            with self.subTest(field=field),self.assertRaises(StoreError): validate_authorization(value)
        value=self.metadata(); value.pop('observed_scopes')
        with self.assertRaises(StoreError): validate_authorization(value)
