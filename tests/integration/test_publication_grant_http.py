"""실제 관리서비스·Google검사·grant·resolver를 가짜wire와 loopback HTTP로 결속한다."""
import unittest
from tests import test_web_oauth as http_fixture
from tests.operations import test_publication_management as management_fixture
from common.oauth.publication_verification import GooglePublicationVerifier
from common.operations.publication_authority import ManagedPublicationAuthorizer
from common.operations.content_store import StoreError

BASE='/api/v2/oauth/connections/personal.youtube/publication-grant'
class PublicationGrantIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.h=http_fixture.OAuthHTTPTests();self.h.setUp();self.addCleanup(self.h.doCleanups)
        self.m=management_fixture.PublicationManagementTests();self.m.setUp();self.addCleanup(self.m.doCleanups)
        self.wire=[];owner=self
        class Transport:
            def request(self,method,url,params,headers):
                owner.wire.append((method,url,params))
                return {'items':[{'id':'channel','status':{'isLinked':True}}]}
        self.m.grants.initialize()
        self.h.server.publication_grant_service=self.m.make_service(verifiers={'youtube':GooglePublicationVerifier('youtube',Transport())})
    def body(self,data):
        return dict(request_key='explicit-user-action',expected_base_revision=data['base_revision'],expected_connection_revision=data['connection_revision'],expected_grant_revision=data['publication_grant']['revision'])
    def test_http_approve_scoped_use_revoke_and_stale_cas_preserve_legacy_registry(self):
        f=self.m.fixture
        status,initial,_=self.h.json(BASE);self.assertEqual(status,200);self.assertEqual(f.reads,0);self.assertEqual(self.wire,[])
        status,approved,_=self.h.post(BASE+'/approve',self.body(initial));self.assertEqual(status,200);self.assertEqual(approved['publication_grant']['status'],'granted')
        self.assertEqual(len(self.wire),1);self.assertEqual(self.wire[0][0],'GET')
        authorizer=ManagedPublicationAuthorizer(self.m.grants,lambda:self.m.clients)
        resolver=f.resolver(publication_authorizer=authorizer)
        with resolver.use(f.reference,account_id='personal',platform='youtube',target_id='channel',scope='publication') as credential:credential.assert_publication_authority()
        status,revoked,_=self.h.post(BASE+'/revoke',self.body(approved));self.assertEqual(status,200);self.assertEqual(revoked['publication_grant']['status'],'revoked')
        reads=f.reads
        with self.assertRaises(StoreError):
            with resolver.use(f.reference,account_id='personal',platform='youtube',target_id='channel',scope='publication'):self.fail('revoked authority used')
        self.assertEqual(f.reads,reads)
        self.assertEqual(self.h.post(BASE+'/approve',self.body(initial))[0],409)
        self.assertEqual(len(self.wire),1);self.assertFalse(f.registry.connections['personal.youtube'].enabled)
        with self.assertRaises(StoreError):credential.assert_current()
        public=str(approved)+str(revoked)
        for private in ('fixture-access-private','fixture-refresh-private','credential_fingerprint','credential_ref',str(f.root)):
            self.assertNotIn(private,public)
