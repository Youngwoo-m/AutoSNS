"""메모리 소유 vault→관리 overlay→scoped SDK→조회 서비스 경로. 실자격/API 없음."""
from types import SimpleNamespace
import unittest
from tests.operations import test_managed_credentials as fixture
from common.operations.managed_connections import project_registry
from common.operations.models import ContractError
from common.operations.oauth_workspace import require_oauth_write_guard
from common.publishers.managed_google_credentials import ManagedGoogleCredentialResolver
from common.publishers.credential_bindings import build_managed_bridge_credential_catalog
from common.publishers.bridge_host import BridgeHost
from common.publishers.youtube_services import GoogleYoutubeServices
from tests.publishers.test_youtube import FakeGoogle,Client,context,snapshot
from common.publishers.youtube import YoutubeAdapter

class ManagedOAuthReadPathTests(unittest.TestCase):
    setUp=fixture.ManagedCredentialTests.setUp
    put=fixture.ManagedCredentialTests.put
    resolver=fixture.ManagedCredentialTests.resolver
    def test_owned_google_read_path_uses_one_guard_and_does_not_activate_publication(self):
        expires='2099-01-01T00:00:00+00:00'
        self.row.setdefault('checked_at',fixture.NOW.isoformat());self.row.setdefault('provider_subject','channel')
        self.row['authorization']['credential_expires_at']=expires
        self.put({**fixture.TOKEN,'expires_at':expires})
        projected=project_registry(self.registry,self.store.snapshot())
        self.assertFalse(projected.connections['personal.youtube'].enabled)
        ctx=context('personal.youtube',target_id='channel',registry_revision=projected.revision)
        YoutubeAdapter(projected,None).prepare(ctx,snapshot())
        from unittest.mock import Mock
        bridge=Mock();adapter=YoutubeAdapter(projected,bridge)
        result=adapter.submit(ctx,adapter.prepare(ctx,snapshot()),object())
        self.assertEqual(result.outcome,'failed');self.assertTrue(result.evidence['confirmed_not_submitted'])
        bridge.submit.assert_not_called()
        self.assertEqual(self.reads,0)
        factory_calls=[];sdk_calls=[]
        owner=self
        class FakeSDKCredentials:
            def apply(self,headers,token=None):
                require_oauth_write_guard(owner.root,owner.context.owner)
                sdk_calls.append('apply')
                headers['authorization']='Bearer '+factory_calls[-1]['token']
            def before_request(self,request,method,url,headers):
                require_oauth_write_guard(owner.root,owner.context.owner)
                sdk_calls.append('before_request');self.apply(headers)
            def refresh(self,request):
                raise AssertionError('managed read must not refresh')
        def factory(**kwargs):
            require_oauth_write_guard(self.root,self.context.owner)
            factory_calls.append(kwargs)
            return FakeSDKCredentials()
        google_resolver=ManagedGoogleCredentialResolver(self.resolver(),credentials_factory=factory)
        host=BridgeHost(projected,None,SimpleNamespace(),None,{},credential_catalog=build_managed_bridge_credential_catalog(projected,connection_ids=(ctx.connection_id,)),credential_resolver=google_resolver)
        google=FakeGoogle('personal');google.channel='channel'
        service=GoogleYoutubeServices(Client(google),media_factory=lambda *a:None)
        with host._credential_scope(ctx,'read') as credentials:
            require_oauth_write_guard(self.root,self.context.owner)
            self.assertIsNotNone(credentials)
            headers={}
            credentials.before_request(None,'GET','https://youtube.googleapis.com/youtube/v3/channels',headers)
            self.assertEqual(headers['authorization'],'Bearer '+factory_calls[0]['token'])
            result=service.inspect(dict(platform='youtube',target_id='channel',expected_login_subject='channel'))
            self.assertTrue(result['authenticated'])
        self.assertEqual(self.reads,1);self.assertEqual(len(factory_calls),1)
        self.assertEqual(sdk_calls,['before_request','apply'])
        with self.assertRaises(ContractError) as closed:credentials.apply({})
        self.assertEqual(closed.exception.code,'managed_google_credentials_unavailable')
        self.assertEqual(sdk_calls,['before_request','apply'])
        self.assertIsNone(factory_calls[0]['refresh_token'])
        self.assertFalse(any(name=='videos.insert' for name,_ in google.calls))
        with self.assertRaises(Exception):
            with host._credential_scope(ctx,'publication'):self.fail('unverified publication scope yielded')
        self.assertEqual(self.reads,1)
