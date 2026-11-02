"""명시 버전 Facebook Pages 클라이언트. 가짜 transport만 사용하며 실제 API는 호출하지 않는다."""
import json
from unittest.mock import patch
import unittest
from urllib.parse import parse_qs

from common.operations.models import ContractError
from common.publishers.facebook_client import FacebookApiClient

TOKEN='private-facebook-token'
# v26.0은 명시 버전 경로 시험용 값이며 현재 앱/API의 지원 버전을 주장하지 않는다.


def post(**changes):
    return dict(dict(id='123_456',**{'from':{'id':'123','name':'페이지'}},message='승인한 본문',created_time='2026-11-02T02:00:00+0000',permalink_url='https://www.facebook.com/123/posts/456',is_published=True,is_hidden=False),**changes)


class FacebookClientTests(unittest.TestCase):
    def client(self,responses=None):
        responses=list(responses or [(200,json.dumps({'id':'123','name':'페이지'}).encode())]);calls=[]
        def transport(method,path,headers,body):calls.append((method,path,headers,body));return responses.pop(0)
        return FacebookApiClient(TOKEN,api_version='v26.0',transport=transport),calls

    def code(self,code,call):
        with self.assertRaises(ContractError) as caught:call()
        self.assertEqual(caught.exception.code,code);self.assertNotIn(TOKEN,str(caught.exception))

    def test_explicit_version_is_required_and_constructor_is_inert(self):
        with self.assertRaises(TypeError):FacebookApiClient(TOKEN)
        for version in (None,'','latest','v0.0','v026.0','v26.1','26.0','v26.0/me','v26.0?access_token=x'):
            with self.assertRaises(ContractError):FacebookApiClient(TOKEN,api_version=version)
        client,calls=self.client();self.assertEqual(calls,[]);self.assertNotIn(TOKEN,repr(client))
        # 큰 명시 버전도 형식만 검사할 뿐 실제 지원 여부를 보장하지 않는다.
        FacebookApiClient(TOKEN,api_version='v999.0')

    def test_me_observes_only_identity_with_bearer_header_no_token_url_or_body(self):
        client,calls=self.client([(200,json.dumps(dict(id='123',name='페이지',access_token='PRIVATE',tasks=['MANAGE'])).encode())])
        self.assertEqual(client.me(),dict(id='123',name='페이지'))
        method,path,headers,body=calls[0];self.assertEqual((method,path,body),('GET','/v26.0/me?fields=id%2Cname',None))
        self.assertEqual(headers['Authorization'],'Bearer '+TOKEN);self.assertNotIn(TOKEN,path)

    def test_create_text_is_exact_immediate_feed_form_and_never_schedules(self):
        client,calls=self.client([(200,b'{"id":"123_456","extra":"PRIVATE"}')])
        self.assertEqual(client.create_text('123','승인한 & 본문\n둘'),{'id':'123_456'})
        method,path,headers,body=calls[0];self.assertEqual((method,path),('POST','/v26.0/123/feed'))
        self.assertEqual(parse_qs(body.decode('ascii')),dict(message=['승인한 & 본문\n둘'],published=['true']))
        self.assertEqual(headers['Content-Type'],'application/x-www-form-urlencoded');self.assertNotIn(TOKEN,body.decode('ascii'))
        client,_=self.client([(200,b'{"id":"999_456"}')]);self.code('facebook_invalid_response',lambda:client.create_text('123','본문'))

    def test_read_post_requires_exact_composite_id_and_owner_and_preserves_observed_flags(self):
        row=post();client,calls=self.client([(200,json.dumps(dict(row,access_token='PRIVATE')).encode())])
        expected={**row,'from':{'id':'123'}}
        self.assertEqual(client.read_post('123_456'),expected)
        self.assertEqual(calls[0][1],'/v26.0/123_456?fields=id%2Cfrom%2Cmessage%2Ccreated_time%2Cpermalink_url%2Cis_published%2Cis_hidden')
        for change in ({'id':'123_789'},{'from':{'id':'999'}},{'from':'123'},{'created_time':'not-a-time'},{'created_time':'2026-11-02T02:00:00'},{'is_published':1},{'is_hidden':'false'},{'permalink_url':'javascript:alert(1)'}):
            client,_=self.client([(200,json.dumps(post(**change)).encode())]);self.code('facebook_invalid_response',lambda:client.read_post('123_456'))
        client,_=self.client([(200,json.dumps(post(is_published=False,is_hidden=True)).encode())])
        result=client.read_post('123_456');self.assertFalse(result['is_published']);self.assertTrue(result['is_hidden']);self.assertNotIn('verified',result)

    def test_default_transport_remains_blocked_without_native_construction(self):
        with patch('socket.socket',side_effect=AssertionError('socket forbidden')):
            client=FacebookApiClient(TOKEN,api_version='v26.0')
            for call in (client.me,lambda:client.create_text('123','본문'),lambda:client.read_post('123_456')):self.code('facebook_transport_unregistered',call)

    def test_ids_utf8_and_internal_byte_limit_are_checked_before_transport(self):
        client,calls=self.client()
        for value in (True,123,None,'','１','123_456','../me','123?fields=access_token','1'*65):
            self.code('facebook_invalid_request',lambda:client.create_text(value,'본문'))
        for value in ('123','123_456_789','a_456','123/a',True,None):self.code('facebook_invalid_request',lambda:client.read_post(value))
        for text in ('',' ',None,'bad\x00text','\ud800','가'*66667):self.code('facebook_invalid_request',lambda:client.create_text('123',text))
        self.assertEqual(calls,[])
        client,_=self.client([(200,b'{"id":"123_456"}')]);self.assertEqual(client.create_text('123','a'*200000),{'id':'123_456'})

    def test_missing_fields_bad_json_and_invalid_utf8_do_not_fabricate_observations(self):
        for raw in (b'{"id":"123","id":"456","name":"page"}',b'{"id":"123","name":"page","n":NaN}',b'{"id":"123","name":"page","n":1e309}',b'[]',b'null',b'\xff',b'{',b'x'*(1024*1024+1)):
            client,_=self.client([(200,raw)]);self.code('facebook_invalid_response',client.me)
        for key in post():
            row=post();row.pop(key);client,_=self.client([(200,json.dumps(row).encode())]);self.code('facebook_invalid_response',lambda:client.read_post('123_456'))

    def test_http_errors_redirects_and_transport_exceptions_are_sanitized_without_retries(self):
        for status in (301,302,400,401,429,500):
            client,calls=self.client([(status,json.dumps({'error':{'message':TOKEN}}).encode())]);self.code('facebook_api_unavailable',client.me);self.assertEqual(len(calls),1)
        calls=[]
        def fail(*args):calls.append(1);raise OSError(TOKEN)
        client=FacebookApiClient(TOKEN,api_version='v26.0',transport=fail)
        self.code('facebook_api_unavailable',lambda:client.create_text('123','본문'));self.assertEqual(calls,[1])
        client,_=self.client([(200,json.dumps({'error':{'message':TOKEN}}).encode())]);self.code('facebook_api_unavailable',client.me)

    def test_permalinks_reject_non_facebook_origins_userinfo_ports_and_controls(self):
        for url in ('http://www.facebook.com/123/posts/456','https://evil.invalid/123/posts/456',
                    'https://www.facebook.com.evil.invalid/123/posts/456','https://user@www.facebook.com/123/posts/456',
                    'https://www.facebook.com:443/123/posts/456','https://www.facebook.com:notaport/123/posts/456',
                    ' https://www.facebook.com/123/posts/456','https://www.facebook.com/123/posts/456\n'):
            client,_=self.client([(200,json.dumps(post(permalink_url=url)).encode())])
            self.code('facebook_invalid_response',lambda:client.read_post('123_456'))

    def test_bad_tokens_and_non_text_response_values_are_fixed_errors(self):
        for token in (None,'','token with spaces','token\r\nInjected:yes','\ud800'):
            with self.assertRaises(ContractError):FacebookApiClient(token,api_version='v26.0')
        for row in ({'id':123,'name':'페이지'},{'id':'123','name':True},{'id':'123','name':'\ud800'}):
            client,_=self.client([(200,json.dumps(row).encode())]);self.code('facebook_invalid_response',client.me)

    def test_permalink_query_is_not_copied_even_on_official_host(self):
        for url in ('https://facebook.com/123/posts/456?access_token='+TOKEN,
                    'https://www.facebook.com/story.php?story_fbid=456&id=123',
                    'https://www.facebook.com/123/posts/456?tracking=x',
                    'https://www.facebook.com/123/posts/456\t'):
            client,_=self.client([(200,json.dumps(post(permalink_url=url)).encode())])
            self.code('facebook_invalid_response',lambda:client.read_post('123_456'))
