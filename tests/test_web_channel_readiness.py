import unittest
from types import SimpleNamespace
from unittest.mock import patch
from tests import test_web_metrics as fixture
from common.operations.managed_connections import ManagedSnapshot
from common.operations.models import freeze
from common.operations.oauth_models import CredentialRef

class ChannelReadinessHTTPTests(unittest.TestCase):
    setUp=fixture.MetricsHTTPTests.setUp
    stop=fixture.MetricsHTTPTests.stop
    request=fixture.MetricsHTTPTests.request
    def test_auth_query_no_initialization_no_secrets_or_mutation(self):
        path='/api/v2/channels/readiness?account=dept'
        self.assertEqual(self.request(path,auth=False)[0],401)
        self.assertEqual(self.request(path,origin='https://evil.test')[0],403)
        with patch('common.operations.oauth_stage_backend.OwnedStageBackend.read_owned',side_effect=AssertionError('vault forbidden')):
            code,data=self.request(path)
        self.assertEqual(code,200);self.assertEqual(data['account_id'],'dept')
        self.assertEqual(len(data['channels']),9)
        self.assertTrue(all(row['account_id']=='dept' and row['live_enabled'] is False for row in data['channels']))
        self.assertFalse(self.workspace.exists())
        self.assertNotIn('credential_ref',str(data));self.assertNotIn('access_token',str(data))
        for query in ('account=bad','account=dept&account=personal','account=dept&connect=true'):
            self.assertEqual(self.request('/api/v2/channels/readiness?'+query)[0],400)
        self.assertEqual(self.request('/api/v2/channels/readiness','POST',{})[0],405)
    def test_local_overlay_connection_record_is_shown_without_reading_secret(self):
        reference=CredentialRef('autosns.oauth','dept','youtube','dept-youtube',1,'token')
        row=dict(connection_id='dept-youtube',account_id='dept',platform='youtube',provider_id='youtube',state='connected',target_id='@dept',credential_ref=reference,credential_generation=1,checked_at='2026-11-02T00:00:00+00:00',provider_subject='channel-subject',authorization=dict(observed_scopes=['https://www.googleapis.com/auth/youtube.readonly'],credential_expires_at='2099-01-01T00:00:00+00:00',read_status='verified',credential_status='active',publication_status='blocked'))
        snapshot=ManagedSnapshot('r1',freeze({'dept-youtube':row}),freeze({'oauth:dept:youtube:dept-youtube:1':reference}),1)
        store=SimpleNamespace(snapshot=lambda:snapshot)
        self.server.oauth_service=SimpleNamespace(registry_supplier=lambda:self.registry,connection_store=store)
        code,data=self.request('/api/v2/channels/readiness?account=dept')
        self.assertEqual(code,200)
        channel=next(item for item in data['channels'] if item['platform']=='youtube')
        self.assertEqual(channel['authentication_status'],'connected');self.assertFalse(channel['live_enabled'])
        self.assertFalse(self.workspace.exists())
