"""발행 사용 승인 HTTP: 임시 웹·가짜 서비스, 실제 OAuth·게시 없음."""
import unittest
from types import SimpleNamespace
from tests import test_web_oauth as fixture

BASE='/api/v2/oauth/connections/personal.youtube/publication-grant'
class PublicationGrantHTTPTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.OAuthHTTPTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.calls=[]
        self.result=dict(publication_grant=dict(connection_id='personal.youtube',account_id='personal',platform='youtube',provider_id='youtube',target_id='channel',revision=0,status='blocked',approved_at=None,expires_at=None,policy_revision='p1'),available_actions=['approve'],reason_codes=[],base_revision='b1',connection_revision=1)
        def op(name):
            def call(*args):self.calls.append((name,args));return self.result
            return call
        self.service=SimpleNamespace(read=op('read'),approve=op('approve'),revoke=op('revoke'))
        self.f.server.publication_grant_service=self.service
    def body(self):return dict(request_key='grant-1',expected_base_revision='b1',expected_connection_revision=1,expected_grant_revision=0)
    def test_explicit_get_and_post_share_cookie_csrf_and_exact_body(self):
        status,data,_=self.f.json(BASE);self.assertEqual(status,200);self.assertEqual(data,self.result)
        self.assertEqual(self.calls[0][0],'read');self.assertEqual(self.calls[0][1][1],'personal.youtube')
        for action in ('approve','revoke'):
            status,data,_=self.f.post(BASE+'/'+action,self.body());self.assertEqual(status,200)
            self.assertEqual(self.calls[-1][0],action);self.assertEqual(self.calls[-1][1][2],self.body())
    def test_missing_session_csrf_crosssite_and_extra_fields_never_call_service(self):
        self.assertEqual(self.f.request(BASE,cookie=None)[0],401)
        self.assertEqual(self.f.request(BASE+'/approve','POST',self.body())[0],403)
        for body in ({**self.body(),'target_id':'other'},{**self.body(),'expected_grant_revision':True},{**self.body(),'expected_grant_revision':-1},{**self.body(),'expected_connection_revision':0}):
            self.assertEqual(self.f.post(BASE+'/approve',body)[0],400)
        self.assertEqual(self.f.json(BASE+'/approve','POST',self.body(),headers={'Origin':'https://evil.invalid','X-CSRF-Token':self.f.csrf()})[0],403)
        self.assertEqual(self.calls,[])
    def test_default_service_off_and_private_response_are_closed(self):
        self.f.server.publication_grant_service=None
        self.assertEqual(self.f.json(BASE)[0],503)
        self.assertEqual(self.f.post(BASE+'/approve',self.body())[0],503)
        self.f.server.publication_grant_service=self.service
        self.result['publication_grant']['credential_fingerprint']='private'
        status,data,_=self.f.json(BASE);self.assertEqual(status,503);self.assertNotIn('private',str(data))
    def test_wrong_route_method_query_and_response_identity_are_rejected(self):
        self.assertEqual(self.f.json(BASE+'?account=dept')[0],400)
        self.assertEqual(self.f.post(BASE+'/inspect',self.body())[0],404)
        self.result['publication_grant']['connection_id']='dept.youtube'
        self.assertEqual(self.f.json(BASE)[0],503)

    def test_explicit_external_https_origin_works_without_trusting_forwarded_headers(self):
        from web_external_access import ExternalAccessPolicy
        csrf=self.f.csrf()
        self.f.server.external_access_policy=ExternalAccessPolicy('https://console.example.com')
        self.f.server.allowed_hosts={'console.example.com'}
        status,data,_=self.f.json(BASE+'/approve','POST',self.body(),host='console.example.com',headers={'Origin':'https://console.example.com','X-CSRF-Token':csrf})
        self.assertEqual(status,200);self.assertEqual(data,self.result)
        self.assertEqual(self.f.json(BASE+'/approve','POST',self.body(),host='console.example.com',headers={'Origin':'http://console.example.com','X-CSRF-Token':csrf,'X-Forwarded-Proto':'https'})[0],403)
