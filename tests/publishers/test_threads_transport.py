"""명시 등록 Threads HTTPS transport. 가짜 연결만 사용하며 실제 네트워크는 금지한다."""
import os
from unittest.mock import patch
import unittest
from urllib.parse import urlencode

from common.operations.models import ContractError
from common.publishers.threads_client import ThreadsApiClient
from common.publishers.threads_transport import ThreadsHttpsTransport

TOKEN='private-token-with-no-logging'
HEADERS={'Accept':'application/json','Authorization':'Bearer '+TOKEN}
POST_HEADERS={**HEADERS,'Content-Type':'application/x-www-form-urlencoded'}


class Response:
    def __init__(self,status=200,raw=b'{"id":"123","username":"dept"}',error=None):self.status=status;self.raw=raw;self.error=error;self.reads=[]
    def read(self,size):
        self.reads.append(size)
        if self.error:raise self.error
        return self.raw[:size]


class Connection:
    def __init__(self,response):self.response=response;self.requests=[];self.closed=0;self.request_error=None
    def request(self,method,path,body=None,headers=None):
        self.requests.append((method,path,body,headers))
        if self.request_error:raise self.request_error
    def getresponse(self):return self.response
    def close(self):self.closed+=1


class ThreadsTransportTests(unittest.TestCase):
    def setup_transport(self,*,activate=True,response=None):
        calls=[];connection=Connection(response or Response())
        def factory(*args,**kwargs):calls.append((args,kwargs));return connection
        return ThreadsHttpsTransport(activate=activate,connection_factory=factory),calls,connection

    def assert_code(self,code,call):
        with self.assertRaises(ContractError) as caught:call()
        self.assertEqual(caught.exception.code,code);self.assertNotIn(TOKEN,str(caught.exception))

    def test_constructor_and_disabled_calls_never_construct_native_connection(self):
        transport,calls,_=self.setup_transport(activate=False)
        self.assertEqual(calls,[]);self.assertNotIn(TOKEN,repr(transport))
        self.assert_code('threads_transport_unregistered',lambda:transport('GET','/me?fields=id%2Cusername',HEADERS,None))
        self.assertEqual(calls,[])
        for activate in (1,0,None,'true'):
            with self.assertRaises(ContractError):ThreadsHttpsTransport(activate=activate)

    def test_explicit_activation_uses_fixed_tls_host_port_timeout_and_finite_read(self):
        transport,calls,connection=self.setup_transport()
        with patch.dict(os.environ,{'HTTPS_PROXY':'https://evil.invalid','HTTP_PROXY':'http://evil.invalid'}),patch('os.getenv',side_effect=AssertionError('env read forbidden')):
            result=transport('GET','/me?fields=id%2Cusername',HEADERS,None)
        self.assertEqual(calls,[(('graph.threads.net',),dict(port=443,timeout=30))]);self.assertEqual(result,(200,b'{"id":"123","username":"dept"}'))
        self.assertEqual(connection.requests,[('GET','/me?fields=id%2Cusername',None,HEADERS)])
        self.assertEqual(connection.response.reads,[1024*1024+1]);self.assertEqual(connection.closed,1)

    def test_existing_client_is_explicitly_composable_without_changing_default_client_transport(self):
        transport,_,connection=self.setup_transport();client=ThreadsApiClient(TOKEN,transport=transport)
        self.assertEqual(client.me(),{'id':'123','username':'dept'});self.assertEqual(connection.closed,1)
        self.assert_code('threads_transport_unregistered',ThreadsApiClient(TOKEN).me)

    def test_exact_post_forms_are_allowed_and_other_mutations_cannot_be_selected(self):
        for path,form in [('/123/threads',dict(media_type='TEXT',text='한글 & 줄\n둘',auto_publish_text='false')),('/123/threads_publish',dict(creation_id='456'))]:
            transport,_,connection=self.setup_transport();body=urlencode(form).encode('ascii')
            self.assertEqual(transport('POST',path,POST_HEADERS,body)[0],200)
            self.assertEqual(connection.requests[0],('POST',path,body,POST_HEADERS));self.assertEqual(connection.closed,1)

    def test_paths_hosts_query_tokens_headers_and_invalid_bodies_are_rejected_before_connection(self):
        transport,calls,_=self.setup_transport()
        bad=[('GET','https://evil.invalid/me?fields=id,username',HEADERS,None),('GET','//evil.invalid/me?fields=id,username',HEADERS,None),
            ('GET','/me?fields=id,username&access_token='+TOKEN,HEADERS,None),('GET','/me?fields=id,username&access%5ftoken=x',HEADERS,None),
            ('GET','/123?fields=id,status,error_message#fragment',HEADERS,None),('GET','/me?fields=id,username',dict(HEADERS,Host='evil.invalid'),None),
            ('GET','/me?fields=id,username',dict(HEADERS,Authorization='Bearer x\r\nHost: evil.invalid'),None),
            ('GET','/me?fields=id,username',HEADERS,b''),('DELETE','/123',HEADERS,None),
            ('POST','/123/threads',POST_HEADERS,b'media_type=TEXT&text=hello&auto_publish_text=true'),
            ('POST','/123/threads_publish',POST_HEADERS,b'creation_id=456&access_token=x'),
            ('POST','/123/threads_publish',POST_HEADERS,b'creation_id=456&creation_id=789'),
            ('POST','/123/threads',POST_HEADERS,urlencode(dict(media_type='TEXT',text=TOKEN,auto_publish_text='false')).encode())]
        for args in bad:self.assert_code('threads_invalid_request',lambda:transport(*args))
        self.assertEqual(calls,[])

    def test_redirects_errors_and_oversized_responses_never_retry_or_follow_location(self):
        for status in (301,302,307,400,401,429,500):
            response=Response(status=status,raw=TOKEN.encode());transport,calls,connection=self.setup_transport(response=response)
            self.assert_code('threads_api_unavailable',lambda:transport('GET','/me?fields=id,username',HEADERS,None))
            self.assertEqual(len(calls),1);self.assertEqual(len(connection.requests),1);self.assertEqual(connection.closed,1);self.assertEqual(response.reads,[])
        response=Response(raw=b'x'*(1024*1024+1));transport,_,connection=self.setup_transport(response=response)
        self.assert_code('threads_invalid_response',lambda:transport('GET','/me?fields=id,username',HEADERS,None));self.assertEqual(connection.closed,1)

    def test_transport_exceptions_are_sanitized_and_connection_is_closed(self):
        for mode in ('request','read'):
            transport,calls,connection=self.setup_transport()
            if mode=='request':connection.request_error=OSError(TOKEN)
            else:connection.response.error=OSError(TOKEN)
            self.assert_code('threads_api_unavailable',lambda:transport('GET','/me?fields=id,username',HEADERS,None))
            self.assertEqual(connection.closed,1);self.assertEqual(len(calls),1);self.assertEqual(len(connection.requests),1)
        calls=[]
        def fail(*args,**kwargs):calls.append(1);raise OSError(TOKEN)
        transport=ThreadsHttpsTransport(activate=True,connection_factory=fail)
        self.assert_code('threads_api_unavailable',lambda:transport('GET','/me?fields=id,username',HEADERS,None));self.assertEqual(calls,[1])

    def test_empty_fragment_and_unbounded_bearer_padding_are_rejected_before_connection(self):
        transport,calls,_=self.setup_transport()
        self.assert_code('threads_invalid_request',lambda:transport('GET','/me?fields=id,username#',HEADERS,None))
        self.assert_code('threads_invalid_request',lambda:transport('GET','/me?fields=id,username',dict(HEADERS,Authorization='Bearer a'+'='*20000),None))
        self.assertEqual(calls,[])
