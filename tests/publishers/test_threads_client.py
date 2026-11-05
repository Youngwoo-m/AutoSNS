"""명시 주입 transport의 Threads 요청 계약과 파서. 실제 API/로그인/네트워크 없음."""
import json
from unittest.mock import patch
import unittest
from urllib.parse import parse_qs,urlsplit

from common.operations.models import ContractError
from common.publishers.threads_client import ThreadsApiClient

TOKEN='private-threads-token'


class ThreadsClientTests(unittest.TestCase):
    def client(self,responses=None):
        calls=[];responses=list(responses or [(200,b'{"id":"123","username":"dept"}')])
        def transport(method,path,headers,body):calls.append((method,path,headers,body));return responses.pop(0)
        return ThreadsApiClient(TOKEN,transport=transport),calls

    def code(self,code,call):
        with self.assertRaises(ContractError) as caught:call()
        self.assertEqual(caught.exception.code,code);self.assertNotIn(TOKEN,str(caught.exception))

    def test_constructor_is_inert_and_me_projects_only_expected_fields(self):
        client,calls=self.client([(200,b'{"id":"123","username":"dept","access_token":"PRIVATE"}')])
        self.assertEqual(calls,[]);self.assertNotIn(TOKEN,repr(client))
        self.assertEqual(client.me(),dict(id='123',username='dept'))
        method,path,headers,body=calls[0];self.assertEqual(method,'GET');self.assertEqual(path,'/me?fields=id%2Cusername');self.assertIsNone(body)
        self.assertEqual(headers['Authorization'],'Bearer '+TOKEN);self.assertNotIn(TOKEN,path)

    def test_create_and_publish_use_exact_numeric_paths_form_data_and_no_query_token(self):
        client,calls=self.client([(200,b'{"id":"456"}'),(200,b'{"id":"789"}')])
        self.assertEqual(client.create_text('123','한글 & 줄\n둘'),{'id':'456'});self.assertEqual(client.publish('123','456'),{'id':'789'})
        self.assertEqual([row[0:2] for row in calls],[('POST','/123/threads'),('POST','/123/threads_publish')])
        self.assertEqual(parse_qs(calls[0][3].decode('ascii')),dict(media_type=['TEXT'],text=['한글 & 줄\n둘'],auto_publish_text=['false']))
        self.assertEqual(parse_qs(calls[1][3].decode('ascii')),dict(creation_id=['456']))
        for _,path,headers,body in calls:
            self.assertNotIn(TOKEN,path);self.assertNotIn(TOKEN,body.decode('ascii'));self.assertEqual(headers['Content-Type'],'application/x-www-form-urlencoded')
            self.assertEqual(headers['Authorization'],'Bearer '+TOKEN)

    def test_status_and_read_post_query_only_documented_fields(self):
        row=dict(id='789',owner={'id':'123'},text='원문',timestamp='2026-11-02T02:00:00+0000',media_type='TEXT_POST',permalink='https://www.threads.net/@dept/post/example')
        client,calls=self.client([(200,b'{"id":"456","status":"FINISHED"}'),(200,json.dumps(row).encode())])
        self.assertEqual(client.container_status('456'),dict(id='456',status='FINISHED'))
        self.assertEqual(client.read_post('789'),row)
        self.assertEqual(calls[0][1],'/456?fields=id%2Cstatus%2Cerror_message')
        self.assertEqual(parse_qs(urlsplit(calls[1][1]).query),{'fields':['id,owner,text,timestamp,media_type,permalink']})

    def test_default_native_transport_remains_unregistered_and_never_opens_socket(self):
        with patch('socket.socket',side_effect=AssertionError('socket forbidden')):
            client=ThreadsApiClient(TOKEN)
            for call in (client.me,lambda:client.create_text('123','글'),lambda:client.publish('123','456'),lambda:client.container_status('456'),lambda:client.read_post('789')):
                self.code('threads_transport_unregistered',call)

    def test_invalid_ids_and_text_are_rejected_before_transport(self):
        client,calls=self.client()
        for value in (123,True,None,'','/me','1?access_token=x','１','1'*65):
            for call in (lambda:client.create_text(value,'글'),lambda:client.publish('123',value),lambda:client.read_post(value),lambda:client.container_status(value)):
                self.code('threads_invalid_request',call)
        for text in ('',' ',None,'가'*501,'\ud800','bad\x00text'):
            self.code('threads_invalid_request',lambda:client.create_text('123',text))
        self.assertEqual(calls,[])

    def test_bad_tokens_never_reach_transport_or_headers(self):
        for token in ('',None,'token\r\nInjected: true','token with spaces','\ud800'):
            with self.assertRaises(ContractError):ThreadsApiClient(token,transport=lambda *_:self.fail('transport called'))

    def test_json_duplicates_nonfinite_nonobject_invalid_utf8_and_oversize_are_rejected(self):
        for raw in (b'{"id":"123","id":"456"}',b'{"id":"123","n":NaN}',b'[]',b'null',b'\xff',b'{',b'x'*(1024*1024+1)):
            client,calls=self.client([(200,raw)]);self.code('threads_invalid_response',client.me);self.assertEqual(len(calls),1)
        for raw in (b'{"id":"not-numeric","username":"dept"}',b'{"id":"123"}',b'{"id":"123","username":"dept","nested":{"x":1,"x":2}}'):
            client,_=self.client([(200,raw)]);self.code('threads_invalid_response',client.me)

    def test_http_errors_redirects_and_exceptions_are_fixed_and_never_retried(self):
        for status in (301,302,400,401,429,500):
            client,calls=self.client([(status,json.dumps({'error':{'message':TOKEN}}).encode())]);self.code('threads_api_unavailable',client.me);self.assertEqual(len(calls),1)
        calls=[]
        def fail(*args):calls.append(1);raise OSError(TOKEN)
        client=ThreadsApiClient(TOKEN,transport=fail);self.code('threads_api_unavailable',client.me);self.assertEqual(calls,[1])
        client,_=self.client([(200,json.dumps({'error':{'message':TOKEN}}).encode())]);self.code('threads_api_unavailable',client.me)

    def test_response_identity_and_container_status_are_not_fabricated(self):
        client,_=self.client([(200,b'{"id":"999","status":"FINISHED"}')]);self.code('threads_invalid_response',lambda:client.container_status('456'))
        client,_=self.client([(200,b'{"id":"456","status":"UNKNOWN_NEW"}')]);self.code('threads_invalid_response',lambda:client.container_status('456'))
        client,_=self.client([(200,b'{"id":"789","owner":"123","text":"x","timestamp":"bad","media_type":"TEXT_POST","permalink":"x"}')]);self.code('threads_invalid_response',lambda:client.read_post('789'))

    def test_non_scalar_status_and_overflow_json_are_fixed_invalid_responses(self):
        client,_=self.client([(200,b'{"id":"456","status":[]}')]);self.code('threads_invalid_response',lambda:client.container_status('456'))
        client,_=self.client([(200,b'{"id":"123","username":"dept","nested":1e309}')]);self.code('threads_invalid_response',client.me)

    def test_container_error_message_is_never_copied_to_result(self):
        client,_=self.client([(200,json.dumps({'id':'456','status':'ERROR','error_message':TOKEN}).encode())])
        result=client.container_status('456')
        self.assertEqual(result,{'id':'456','status':'ERROR'});self.assertNotIn(TOKEN,str(result))
