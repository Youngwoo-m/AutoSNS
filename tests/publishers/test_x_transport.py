import json
import unittest
from common.operations.models import ContractError
from common.publishers.x_client import XApiClient, ME_PATH, POST_FIELDS
from common.publishers.x_transport import XHttpsTransport

TOKEN='private-user-context-token'
HEADERS={'Accept':'application/json','Authorization':'Bearer '+TOKEN}


class Connection:
    def __init__(self,host,**options):
        self.host,self.options,self.closed,self.debuglevel=host,options,False,9
        self.calls=[];self.sizes=[];self.raw=b'{"data":{"id":"1","text":"ok"}}';self.status=200;self.failed=False
    def request(self,*args,**kwargs):
        self.calls.append((args,kwargs))
        if self.failed:raise OSError(TOKEN)
    def getresponse(self):return self
    def read(self,size):self.sizes.append(size);return self.raw
    def close(self):self.closed=True


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.connections=[];self.configure=lambda c:None
        def factory(*args,**kwargs):
            conn=Connection(*args,**kwargs);self.configure(conn);self.connections.append(conn);return conn
        self.factory=factory
        self.transport=XHttpsTransport(activate=True,cost_authorized=True,connection_factory=factory)
    def send(self,method='GET',path=ME_PATH,headers=None,body=None):return self.transport(method,path,dict(HEADERS if headers is None else headers),body)
    def test_activation_and_cost_gate_precede_all_connections(self):
        for options,code in (({},'x_transport_unregistered'),({'activate':True},'x_cost_authorization_required'),({'cost_authorized':True},'x_transport_unregistered')):
            transport=XHttpsTransport(connection_factory=self.factory,**options)
            with self.assertRaisesRegex(ContractError,code):transport('GET',ME_PATH,HEADERS,None)
        for options in ({'activate':1},{'cost_authorized':1}):
            with self.assertRaises(ContractError):XHttpsTransport(**options)
        self.assertEqual(self.connections,[])
    def test_actual_client_methods_use_fixed_https_and_original_json(self):
        client=XApiClient(TOKEN,transport=self.transport)
        self.configure=lambda c:setattr(c,'raw',b'{"data":{"id":"123","username":"account","name":"Name","protected":false}}')
        client.inspect_account()
        text='한글 😀 https://example.org/path?a=1&b=2\n& = +'
        self.configure=lambda c:setattr(c,'raw',json.dumps({'data':{'id':'456','text':text}}).encode())
        client.create_post(text)
        self.configure=lambda c:setattr(c,'raw',b'{"data":{"id":"456","author_id":"123","text":"ok","created_at":"2026-11-04T00:00:00Z"}}')
        client.read_post('456')
        for c in self.connections:
            self.assertEqual((c.host,c.options),('api.x.com',{'port':443,'timeout':30}));self.assertEqual(c.debuglevel,0);self.assertTrue(c.closed);self.assertEqual(c.sizes,[1024*1024+1])
            self.assertEqual(len(c.calls),1)
        self.assertEqual(json.loads(self.connections[1].calls[0][1]['body']),{'text':text})
        self.assertNotIn(TOKEN,repr(self.transport))
    def test_paths_headers_and_body_block_before_connection(self):
        cases=[dict(path='https://api.x.com'+ME_PATH),dict(path='//api.x.com'+ME_PATH),dict(path='/2/tweets/search/recent?query=a'),dict(path=ME_PATH+'&access_token='+TOKEN),dict(path='/2/tweets/1'+POST_FIELDS+'&expansions=author_id'),dict(path=ME_PATH+'#x'),dict(path=ME_PATH+'\r\nX: bad'),dict(method='DELETE'),dict(headers={**HEADERS,'Host':'evil'}),dict(headers={**HEADERS,'Content-Length':'0'}),dict(headers={**HEADERS,'Authorization':'Bearer x\r\nX:bad'}),dict(body=b'{}')]
        for case in cases:
            with self.subTest(case=case),self.assertRaises(ContractError):self.send(**case)
        headers={**HEADERS,'Content-Type':'application/json'}
        for body in (b'{"text":"a","text":"b"}',b'{"text":"ok","reply":{}}',b'{"text":NaN}',b'{"text":"\\ud800"}',b'{"text":""}',b'{"text":"'+TOKEN.encode()+b'"}'):
            with self.assertRaises(ContractError):self.send('POST','/2/tweets',headers,body)
        self.assertEqual(self.connections,[])
    def test_short_token_substrings_are_not_false_leaks(self):
        self.send('POST','/2/tweets',{**HEADERS,'Authorization':'Bearer a','Content-Type':'application/json'},b'{"text":"a cat walks"}')
        self.assertEqual(len(self.connections),1)
    def test_safe_status_size_socket_errors_close_without_retry(self):
        for status,raw,failed,code in ((302,b'secret',False,'x_api_unavailable'),(401,b'secret',False,'x_api_unavailable'),(429,b'secret',False,'x_api_unavailable'),(200,b'x'*(1024*1024+1),False,'x_invalid_response'),(200,'text',False,'x_invalid_response'),(200,b'',True,'x_api_unavailable')):
            def configure(c):c.status,c.raw,c.failed=status,raw,failed
            self.configure=configure
            with self.assertRaises(ContractError) as caught:self.send()
            self.assertEqual(str(caught.exception),code);self.assertNotIn(TOKEN,str(caught.exception));self.assertTrue(self.connections[-1].closed);self.assertEqual(len(self.connections[-1].calls),1)
            if status!=200:self.assertEqual(self.connections[-1].sizes,[])


if __name__=='__main__':unittest.main()
