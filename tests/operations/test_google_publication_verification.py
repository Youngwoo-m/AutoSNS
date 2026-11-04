"""고정 Google 읽기 요청과 실제 관측 결속을 가짜 transport로 검증한다."""
from dataclasses import replace
from datetime import timedelta
import unittest
from common.operations.managed_credentials import ResolvedManagedCredential
from common.operations.oauth_models import TokenBundle
from common.operations.oauth_catalog import provider_catalog
from common.operations.content_store import StoreError
from common.oauth.publication_verification import GooglePublicationVerifier
from tests.operations import test_publication_grants as fixture

class Guard:
    def __init__(self):self.active=True
    def check(self):
        if not self.active:raise StoreError('credential_changed')
class Transport:
    def __init__(self,responses):self.responses=list(responses);self.calls=[];self.after=lambda:None
    def request(self,*args):self.calls.append(args);self.after();return self.responses.pop(0)

class GooglePublicationVerificationTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.PublicationGrantTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.guard=Guard()
    def values(self,provider='youtube'):
        definition=next(p for p in provider_catalog() if p.id==provider)
        binding=replace(self.f.binding,provider_id=provider,platform=provider,connection_id='personal.'+provider,
            target_id='channel-id' if provider=='youtube' else '123',provider_subject='channel-id' if provider=='youtube' else '456')
        bundle=TokenBundle('fixture-access',None,'Bearer',(fixture.NOW+timedelta(hours=1)).isoformat(),definition.read_scopes+definition.publication_scopes)
        return binding,ResolvedManagedCredential(bundle,'personal',provider,binding.connection_id,binding.target_id,provider,'read','private-ref',1,self.guard)
    def yt(self):return {'items':[{'id':'channel-id','status':{'isLinked':True}}]}
    def blogger(self,role='AUTHOR'):return {'blog':{'id':'123'},'blog_user_info':{'userId':'456','blogId':'123','role':role,'hasAdminAccess':role=='ADMIN'}}
    def test_youtube_current_channel_and_scope_evidence_without_write_or_token_query(self):
        binding,resolved=self.values();transport=Transport([self.yt()]);verifier=GooglePublicationVerifier('youtube',transport)
        self.assertEqual(transport.calls,[])
        evidence=verifier.verify(resolved,binding,now=fixture.NOW)
        self.assertTrue(evidence.can_publish);self.assertEqual(evidence.binding,binding);self.assertEqual(evidence.observed_scopes,resolved.bundle.scopes)
        method,url,params,headers=transport.calls[0];self.assertEqual(method,'GET');self.assertEqual(url,'https://www.googleapis.com/youtube/v3/channels');self.assertEqual(params,{'part':'id,status','mine':'true','maxResults':50});self.assertNotIn('fixture-access',str(params));self.assertEqual(headers['Authorization'],'Bearer fixture-access');self.assertNotIn('fixture-access',repr(verifier))
    def test_blogger_exact_current_user_author_or_admin(self):
        for role in ('ADMIN','AUTHOR'):
            binding,resolved=self.values('blogger');transport=Transport([{'id':'456'},self.blogger(role)])
            evidence=GooglePublicationVerifier('blogger',transport).verify(resolved,binding,now=fixture.NOW)
            self.assertTrue(evidence.can_publish);self.assertEqual([c[0] for c in transport.calls],['GET','GET']);self.assertEqual(transport.calls[1][1],'https://www.googleapis.com/blogger/v3/users/self/blogs/123')
    def test_blogger_reader_wrong_principal_or_target_never_approve(self):
        binding,resolved=self.values('blogger')
        cases=[({'id':'other'},self.blogger()),({'id':'456'},self.blogger('READER')),({'id':'456'},{**self.blogger(),'blog':{'id':'999'}}),({'id':'456'},{'blog':{'id':'123'},'blog_user_info':{'userId':'456','blogId':'123','hasAdminAccess':True}})]
        for principal,response in cases:
            with self.assertRaises(StoreError):GooglePublicationVerifier('blogger',Transport([principal,response])).verify(resolved,binding,now=fixture.NOW)
    def test_missing_scope_expiry_binding_and_guard_reject_before_network(self):
        binding,resolved=self.values()
        read=next(p for p in provider_catalog() if p.id=='youtube').read_scopes
        for altered in (replace(resolved,target_id='wrong'),replace(resolved,generation=2),replace(resolved,bundle=TokenBundle('fixture',None,'Bearer',resolved.bundle.expires_at,read)),replace(resolved,bundle=TokenBundle('fixture',None,'Bearer',fixture.NOW.isoformat(),resolved.bundle.scopes))):
            transport=Transport([self.yt()])
            with self.assertRaises(StoreError):GooglePublicationVerifier('youtube',transport).verify(altered,binding,now=fixture.NOW)
            self.assertEqual(transport.calls,[])
        self.guard.active=False
        with self.assertRaises(StoreError):GooglePublicationVerifier('youtube',Transport([self.yt()])).verify(resolved,binding,now=fixture.NOW)
    def test_ambiguous_channel_link_status_remote_error_and_guard_change_deny(self):
        binding,resolved=self.values()
        for response in ({'items':[]},{'items':[self.yt()['items'][0]]*2},{'items':[{'id':'wrong','status':{'isLinked':True}}]},{'items':[{'id':'channel-id','status':{'isLinked':False}}]},{'error':{'message':'secret'}}):
            with self.assertRaises(StoreError):GooglePublicationVerifier('youtube',Transport([response])).verify(resolved,binding,now=fixture.NOW)
        transport=Transport([self.yt()]);transport.after=lambda:setattr(self.guard,'active',False)
        with self.assertRaises(StoreError):GooglePublicationVerifier('youtube',transport).verify(resolved,binding,now=fixture.NOW)

class GooglePublicationTransportTests(unittest.TestCase):
    def arguments(self):return ('GET','https://www.googleapis.com/youtube/v3/channels',{'part':'id,status','mine':'true','maxResults':50},{'Authorization':'Bearer fixture-access','Accept':'application/json'})
    def transport(self,raw=b'{"items":[]}',status=200,redirect=False,limit=262144):
        from common.oauth.publication_verification import GooglePublicationTransport
        calls=[]
        class Response:
            closed=False
            def geturl(self):return 'https://evil.example.com' if redirect else calls[-1][0].full_url
            def read(self,size):self.limit=size;return raw
            def close(self):self.closed=True
        response=Response();response.status=status
        def fetch(request,**options):calls.append((request,options));return response
        return GooglePublicationTransport(fetch,max_response_bytes=limit),calls,response
    def test_default_off_and_explicit_fetch_tls_read_request(self):
        import ssl
        from common.oauth.publication_verification import GooglePublicationTransport
        with self.assertRaises(StoreError):GooglePublicationTransport().request(*self.arguments())
        transport,calls,response=self.transport()
        self.assertEqual(calls,[])
        self.assertEqual(transport.request(*self.arguments()),{'items':[]})
        request,options=calls[0]
        self.assertEqual(request.get_method(),'GET');self.assertIsNone(request.data)
        self.assertTrue(request.full_url.startswith('https://www.googleapis.com/youtube/v3/channels?'))
        self.assertNotIn('fixture-access',request.full_url)
        self.assertEqual(request.get_header('Authorization'),'Bearer fixture-access')
        self.assertTrue(options['context'].check_hostname)
        self.assertEqual(options['context'].verify_mode,ssl.CERT_REQUIRED)
        self.assertEqual(response.limit,262145);self.assertTrue(response.closed)
    def test_wrong_hosts_verbs_params_and_injected_headers_never_fetch(self):
        transport,calls,_=self.transport();method,url,params,headers=self.arguments()
        for args in [('POST',url,params,headers),(method,url+'?x=1',params,headers),(method,'https://evil.example.com',params,headers),(method,url,{**params,'access_token':'fixture'},headers),(method,url,params,{**headers,'Host':'evil'}),(method,url,params,{**headers,'Authorization':'Bearer fixture\r\nX: bad'})]:
            with self.assertRaises(StoreError):transport.request(*args)
        self.assertEqual(calls,[])
    def test_redirect_status_size_duplicate_nonfinite_secret_and_errors_redacted(self):
        cases=[dict(redirect=True),dict(status=403),dict(raw=b'x'*20,limit=10),dict(raw=b'{"id":1,"id":2}'),dict(raw=b'{"id":NaN}'),dict(raw=b'{"access_token":"SECRET"}'),dict(raw=b'{"error":{"message":"SECRET"}}'),dict(raw=b'[]')]
        for options in cases:
            transport,_,response=self.transport(**options)
            with self.assertRaises(StoreError) as caught:transport.request(*self.arguments())
            self.assertNotIn('SECRET',str(caught.exception));self.assertTrue(response.closed)
    def test_blogger_endpoints_are_fixed_and_get_only(self):
        transport,calls,_=self.transport(b'{"id":"456"}');headers=self.arguments()[3]
        transport.request('GET','https://www.googleapis.com/blogger/v3/users/self',{'fields':'id'},headers)
        transport.request('GET','https://www.googleapis.com/blogger/v3/users/self/blogs/123',{'maxPosts':0},headers)
        self.assertEqual(len(calls),2)
        with self.assertRaises(StoreError):transport.request('GET','https://www.googleapis.com/blogger/v3/users/self/blogs/../123',{'maxPosts':0},headers)
