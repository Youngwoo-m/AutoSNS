import json
import unittest
from urllib.parse import urlencode, parse_qs
from common.operations.models import ContractError
from common.publishers.instagram_client import InstagramApiClient
from common.publishers.instagram_transport import InstagramHttpsTransport

TOKEN = 'private-access-token-123456'
HEADERS = {'Accept':'application/json', 'Authorization':'Bearer '+TOKEN}
URL = 'https://media.safeworking.net/media/v1/'+'a'*64


class Connection:
    def __init__(self, host, **options):
        self.host, self.options, self.calls, self.closed = host, options, [], False
        self.status, self.raw, self.failure = 200, b'{"id":"123"}', False
        self.debuglevel = 9
        self.read_sizes = []
    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.failure:
            raise OSError(TOKEN)
    def getresponse(self):
        return self
    def read(self, size):
        self.read_sizes.append(size)
        return self.raw
    def close(self):
        self.closed = True


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.connections = []
        self.configure = lambda c: None
        def factory(*args, **kwargs):
            conn = Connection(*args, **kwargs)
            self.configure(conn)
            self.connections.append(conn)
            return conn
        self.transport = InstagramHttpsTransport(activate=True, connection_factory=factory)
    def send(self, method='GET', path='/v26.0/123?fields=id%2Cusername', headers=None, form=None, body=None):
        headers = dict(HEADERS if headers is None else headers)
        if form is not None:
            body = urlencode(form).encode('ascii')
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        return self.transport(method, path, headers, body)
    def test_default_disabled_and_private_repr(self):
        with self.assertRaisesRegex(ContractError,'instagram_transport_unregistered'):
            InstagramHttpsTransport()('GET','/',{},None)
        self.assertNotIn(TOKEN,repr(self.transport))
    def test_actual_client_all_methods_exact_wire(self):
        client = InstagramApiClient(TOKEN,api_version='v26.0',transport=self.transport)
        def raw(value):
            self.configure = lambda c: setattr(c,'raw',json.dumps(value).encode())
        raw({'id':'123','username':'name'});client.inspect_account('123')
        raw({'id':'456'});caption='한글 & = + / % caption\n두 줄'
        client.create_image('123',URL,caption)
        client.create_reels('123',URL,caption)
        client.create_carousel_item('123',image_url=URL)
        client.create_carousel_item('123',video_url=URL)
        client.create_carousel('123',['456','789'],caption)
        client.publish('123','456')
        raw({'id':'456','status_code':'FINISHED'});client.container_status('456')
        raw({'id':'456','owner':{'id':'123'},'caption':caption,'media_type':'IMAGE','media_product_type':'FEED','timestamp':'2026-11-04T00:00:00Z','permalink':'https://www.instagram.com/p/abc/'})
        client.read_media('456')
        raw({'data':[{'id':'456','media_type':'IMAGE'},{'id':'789','media_type':'VIDEO'}]});client.read_children('123')
        self.assertEqual(len(self.connections),10)
        for conn in self.connections:
            self.assertEqual((conn.host,conn.options),('graph.facebook.com',{'port':443,'timeout':30}))
            self.assertEqual(conn.debuglevel,0);self.assertTrue(conn.closed)
            self.assertEqual(conn.read_sizes,[1024*1024+1])
            args, kwargs = conn.calls[0]
            self.assertEqual(kwargs['headers']['Authorization'],'Bearer '+TOKEN)
            self.assertNotIn(TOKEN,args[1]);self.assertNotIn(TOKEN,(kwargs['body'] or b'').decode())
        forms=[parse_qs(c.calls[0][1]['body'].decode(),keep_blank_values=True) for c in self.connections[1:7]]
        self.assertEqual(forms[0]['caption'],[caption]);self.assertEqual(forms[4]['children'],['["456","789"]'])
    def test_bad_requests_never_connect(self):
        invalid=[dict(path='https://evil/v26.0/123?fields=id%2Cusername'),dict(path='//evil/v26.0/123?fields=id%2Cusername'),dict(path='/v26.1/123?fields=id%2Cusername'),dict(path='/v26.0/../123?fields=id%2Cusername'),dict(path='/v26.0/123?fields=id%2Cusername&access_token='+TOKEN),dict(path='/v26.0/123?fields=id%2Cusername#x'),dict(path='/v26.0/123?fields=id%2Cusername&fields=id'),dict(path='/v26.0/123?fields=access_token'),dict(path='/v26.0/123?fields=id%2Cusername\r\nHost:evil'),dict(body=b'x'),dict(method='DELETE'),dict(headers={**HEADERS,'Host':'evil'}),dict(headers={**HEADERS,'Transfer-Encoding':'chunked'}),dict(headers={**HEADERS,'Authorization':'Bearer '+TOKEN+'\r\nX: bad'})]
        for options in invalid:
            with self.subTest(options=options),self.assertRaises(ContractError):self.send(**options)
        self.assertEqual(self.connections,[])
    def test_strict_forms_and_json_children(self):
        forms=[{'image_url':URL,'caption':'ok','access_token':TOKEN},{'media_type':'CAROUSEL','children':'456,789','caption':''},{'media_type':'CAROUSEL','children':'[456,789]','caption':''},{'media_type':'CAROUSEL','children':'["456","456"]','caption':''},{'media_type':'CAROUSEL','children':'["456"]','caption':''},{'media_type':'REELS','video_url':'http://evil.net/a','caption':''},{'image_url':URL,'caption':TOKEN},{'image_url':URL,'caption':'prefix '+TOKEN},{'creation_id':'bad'}]
        for form in forms:
            with self.subTest(form=form),self.assertRaises(ContractError):self.send('POST','/v26.0/123/media',form=form)
        self.assertEqual(self.connections,[])
        self.send('POST','/v26.0/123/media',form={'media_type':'CAROUSEL','children':'["456","789"]','caption':''})
        self.send('POST','/v26.0/123/media',headers={**HEADERS,'Authorization':'Bearer a'},form={'image_url':URL,'caption':'a cat walks'})
    def test_duplicate_form_and_smuggling_rejected(self):
        headers={**HEADERS,'Content-Type':'application/x-www-form-urlencoded'}
        for body in (b'image_url=x&image_url=y&caption=',b'image_url=%GG&caption=',b'image_url=x&caption=%FF',b'image_url=x&caption=x;access_token=secret'):
            with self.assertRaises(ContractError):self.send('POST','/v26.0/123/media',headers=headers,body=body)
        self.assertEqual(self.connections,[])
    def test_safe_response_failures_and_close(self):
        for status,raw,failure,code in ((302,b'secret',False,'instagram_api_unavailable'),(429,b'secret',False,'instagram_api_unavailable'),(500,b'secret',False,'instagram_api_unavailable'),(200,b'x'*(1024*1024+1),False,'instagram_invalid_response'),(200,'notbytes',False,'instagram_invalid_response'),(200,b'',True,'instagram_api_unavailable')):
            def configure(c):c.status,c.raw,c.failure=status,raw,failure
            self.configure=configure
            with self.assertRaises(ContractError) as caught:self.send()
            self.assertEqual(str(caught.exception),code);self.assertNotIn(TOKEN,str(caught.exception));self.assertTrue(self.connections[-1].closed)
            if status!=200:self.assertEqual(self.connections[-1].read_sizes,[])


if __name__=='__main__':unittest.main()
