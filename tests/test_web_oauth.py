"""임시 SQLite·메모리 vault·fake provider만 사용하는 HTTP 사용자 동의 경계."""
import contextlib
import http.client
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

from tests.operations import test_oauth_service as service_tests
from tests.test_web_metrics import Auth

APP=Path(__file__).resolve().parents[1]/'ax-console/app'
sys.path.insert(0,str(APP))


class CookieAuth(Auth):
    def check(self,token):return token in ('fixture','other-session')


class OAuthHTTPTests(unittest.TestCase):
    def setUp(self):
        self.fixture=service_tests.OAuthServiceTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        spec=importlib.util.spec_from_file_location('oauth_http_fixture',APP/'web_server.py')
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        from web_oauth import OAuthCallbackPolicy
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.source=self.root/'source';self.source.mkdir()
        self.workspace=self.root/'managed'
        self.server=self.module.create_server(source_root=self.source,workspace_root=self.workspace,
            web_root=APP/'web',auth_backend=CookieAuth(),operations_registry=self.fixture.registry,
            oauth_service=self.fixture.service,
            oauth_callback_policy=OAuthCallbackPolicy({'youtube':self.fixture.registration.redirect_uri},test_only=True),
            oauth_test_only=True)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.stop)
    def stop(self):self.server.shutdown();self.server.server_close();self.thread.join()
    def request(self,path,method='GET',body=None,*,cookie='fixture',headers=None,raw=None,host=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        h={'Content-Type':'application/json'}
        if method=='POST':h['Origin']='http://127.0.0.1:'+str(self.server.server_port)
        if cookie is not None:h['Cookie']=Auth.COOKIE+'='+cookie
        if host:h['Host']=host
        h.update(headers or {})
        h={k:v for k,v in h.items() if v is not None}
        try:
            conn.request(method,path,body=raw if raw is not None else json.dumps(body) if body is not None else None,headers=h)
            r=conn.getresponse();data=r.read();response=(r.status,dict(r.getheaders()),data)
            return response
        finally:conn.close()
    def json(self,*args,**kwargs):
        status,headers,data=self.request(*args,**kwargs)
        return status,json.loads(data),headers
    def csrf(self,cookie='fixture'):
        status,result,_=self.json('/api/v2/oauth/csrf',cookie=cookie)
        self.assertEqual(200,status);return result['csrf_token']
    def post(self,path,body,**kwargs):
        return self.json(path,'POST',body,headers={'X-CSRF-Token':self.csrf()},**kwargs)
    def start(self):
        status,started,_=self.post('/api/v2/oauth/attempts',self.fixture.body())
        self.assertEqual(200,status)
        return started,parse_qs(urlsplit(started['authorize_url']).query)['state'][0]
    def callback(self,state,**kwargs):
        return self.request('/oauth/callback/youtube?'+urlencode({'state':state,'code':'secret-code'}),
            cookie=None,host='console.test',headers={'Sec-Fetch-Site':'cross-site'},**kwargs)

    def test_cookie_required_internal_key_does_not_substitute_user(self):
        keyfile=self.root/'internal.key';keyfile.write_text('internal-secret')
        self.server.auth_backend.KEYFILE=keyfile
        for path in ('/api/v2/oauth/catalog','/api/v2/oauth/result','/api/v2/oauth/csrf','/connections/oauth-result'):
            self.assertEqual(401,self.request(path,cookie=None)[0])
            self.assertEqual(403,self.request(path,cookie=None,headers={'X-AX-Internal':'internal-secret'})[0])

    def test_csrf_is_session_expiry_and_process_bound(self):
        csrf=self.csrf();path='/api/v2/oauth/attempts';body=self.fixture.body()
        for token,cookie in ((None,'fixture'),(csrf,'other-session'),(csrf+'x','fixture')):
            self.assertEqual(403,self.json(path,'POST',body,cookie=cookie,headers={'Origin':'http://127.0.0.1:'+str(self.server.server_port),**({'X-CSRF-Token':token} if token else {})})[0])
        old=self.server.oauth_csrf_key;self.server.oauth_csrf_key=b'z'*32
        self.assertEqual(403,self.json(path,'POST',body,headers={'X-CSRF-Token':csrf})[0]);self.server.oauth_csrf_key=old
        with patch('oauth_session.time.time',return_value=2*10**9):
            self.assertEqual(403,self.json(path,'POST',body,headers={'X-CSRF-Token':csrf})[0])
        self.assertEqual([],self.fixture.provider.calls)

    def test_get_and_factory_do_not_initialize_or_read_vault_or_call_provider(self):
        self.assertFalse(self.workspace.exists())
        with patch.object(self.fixture.vault,'get',side_effect=AssertionError('secret read')),patch.object(self.fixture.vault,'put',side_effect=AssertionError('secret write')):
            for path in ('/api/v2/oauth/catalog?account=personal','/api/v2/oauth/connections','/api/v2/oauth/result','/api/v2/oauth/csrf'):
                self.assertEqual(200,self.request(path)[0])
        self.assertEqual([],self.fixture.provider.calls);self.assertFalse(self.workspace.exists())

    def test_unconfigured_catalog_is_safe_and_post_is_503(self):
        self.server.oauth_service=None
        status,catalog,_=self.json('/api/v2/oauth/catalog')
        self.assertEqual(200,status);self.assertFalse(catalog['live_enabled']);self.assertEqual(10,len(catalog['items']))
        self.assertTrue(all(not p['ready'] and p['registration_status']=='registration_blocked' for p in catalog['items']))
        self.assertEqual(503,self.post('/api/v2/oauth/attempts',self.fixture.body())[0])
        self.assertFalse(self.workspace.exists())

    def test_query_json_origin_and_unknown_body_are_rejected(self):
        for path in ('/api/v2/oauth/catalog?account=personal&account=dept','/api/v2/oauth/result?account=dept','/connections/oauth-result?code=secret-code'):
            self.assertEqual(400,self.request(path)[0])
        for raw in ('{"request_key":"a","request_key":"b"}','{"request_key":NaN}'):
            self.assertEqual(400,self.request('/api/v2/oauth/attempts','POST',raw=raw,headers={'X-CSRF-Token':self.csrf()})[0])
        self.assertEqual(403,self.request('/api/v2/oauth/catalog',headers={'Origin':'https://evil.test'})[0])
        self.assertEqual(403,self.request('/api/v2/oauth/catalog',headers={'Sec-Fetch-Site':'cross-site'})[0])
        for field in ('endpoint','client_secret','actor','target_id','cost'):
            self.assertEqual(400,self.post('/api/v2/oauth/attempts',dict(self.fixture.body(),**{field:'untrusted'}))[0])
        self.assertEqual([],self.fixture.provider.calls)

    def test_crosssite_callback_stages_only_and_redirects_clean_without_secrets(self):
        started,state=self.start();output=io.StringIO()
        with contextlib.redirect_stderr(output):status,headers,data=self.callback(state)
        self.assertEqual(303,status);self.assertEqual('/connections/oauth-result',headers['Location'])
        self.assertEqual('no-store',headers['Cache-Control']);self.assertEqual('no-referrer',headers['Referrer-Policy'])
        self.assertEqual(b'',data);self.assertEqual(['authorize'],self.fixture.provider.calls)
        for secret in (state,'secret-code','secret-access','secret-refresh'):
            self.assertNotIn(secret,output.getvalue()+str(headers)+data.decode())
        self.assertEqual(200,self.request('/connections/oauth-result')[0])
        self.assertEqual([],self.json('/api/v2/oauth/result',cookie='other-session')[1]['items'])
        item=self.json('/api/v2/oauth/attempts/'+started['attempt_id'])[1]
        self.assertEqual('callback_staged',item['state'])
        self.assertEqual(404,self.request('/api/v2/oauth/attempts/'+started['attempt_id'],cookie='other-session')[0])
        self.assertEqual(409,self.callback(state)[0])
        status,item,_=self.post('/api/v2/oauth/attempts/'+started['attempt_id']+'/continue',dict(request_key='continue',expected_revision=item['revision']))
        self.assertEqual(200,status);self.assertEqual('token_exchanged',item['state'])
        self.assertEqual(1,self.fixture.provider.calls.count('exchange'))
        self.assertFalse(item['execution_enabled'])

    def test_callback_fixed_policy_rejects_host_tls_duplicate_and_extra_fields(self):
        _,state=self.start()
        query=urlencode({'state':state,'code':'secret-code'})
        self.assertEqual(403,self.request('/oauth/callback/youtube?'+query,cookie=None)[0])
        for suffix in ('&state=duplicate','&client_secret=secret','&error=denied'):
            self.assertEqual(400,self.request('/oauth/callback/youtube?'+query+suffix,cookie=None,host='console.test')[0])
        from web_oauth import OAuthCallbackPolicy
        self.server.oauth_callback_policy=OAuthCallbackPolicy({'youtube':self.fixture.registration.redirect_uri})
        self.assertEqual(403,self.callback(state)[0])
        self.assertEqual(['authorize'],self.fixture.provider.calls)

    def test_test_only_policy_requires_explicit_fixture_flag(self):
        from web_oauth import OAuthCallbackPolicy
        with self.assertRaises(ValueError):
            self.module.create_server(source_root=self.source,web_root=APP/'web',auth_backend=CookieAuth(),
                operations_registry=self.fixture.registry,
                oauth_callback_policy=OAuthCallbackPolicy({'youtube':self.fixture.registration.redirect_uri},test_only=True))

    def test_csrf_unicode_missing_origin_and_readonly_post_fail_closed(self):
        token=self.csrf();body=self.fixture.body();path='/api/v2/oauth/attempts'
        self.assertEqual(403,self.json(path,'POST',body,headers={'Origin':None,'X-CSRF-Token':token})[0])
        self.assertEqual(403,self.json(path,'POST',body,headers={'X-CSRF-Token':token.split('.')[0]+'.é'})[0])
        self.server.workspace_root=None
        self.assertEqual(503,self.post(path,body)[0]);self.assertEqual([],self.fixture.provider.calls)

    def test_trusted_proxy_https_is_exact_and_not_global(self):
        from web_oauth import OAuthCallbackPolicy
        _,state=self.start()
        self.server.oauth_callback_policy=OAuthCallbackPolicy({'youtube':self.fixture.registration.redirect_uri},trusted_proxy_ips=('127.0.0.1',))
        path='/oauth/callback/youtube?'+urlencode({'state':state,'error':'access_denied'})
        for headers in ({'X-Forwarded-Proto':'http'},{'X-Forwarded-Proto':'https','X-Forwarded-Host':'console.test'}):
            self.assertEqual(403,self.request(path,cookie=None,host='console.test',headers=headers)[0])
        status,headers,_=self.request(path,cookie=None,host='console.test',headers={'X-Forwarded-Proto':'https','Sec-Fetch-Site':'cross-site'})
        self.assertEqual(303,status);self.assertEqual('/connections/oauth-result',headers['Location'])
        self.assertNotIn('exchange',self.fixture.provider.calls)
        self.assertEqual(403,self.request('/api/v2/oauth/catalog',host='console.test',headers={'X-Forwarded-Proto':'https'})[0])

    def test_duplicate_sensitive_headers_rejected_before_auth(self):
        for name,value in (('Cookie',Auth.COOKIE+'=fixture'),('Host','console.test'),('X-CSRF-Token','value'),('X-Forwarded-Proto','https')):
            conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
            try:
                conn.putrequest('GET','/api/v2/oauth/catalog',skip_host=True)
                conn.putheader('Host','127.0.0.1:'+str(self.server.server_port))
                conn.putheader('Cookie',Auth.COOKIE+'=fixture')
                if name not in ('Cookie','Host'):conn.putheader(name,value)
                conn.putheader(name,value);conn.endheaders()
                response=conn.getresponse();self.assertEqual(400,response.status);response.read()
            finally:conn.close()

    def test_error_and_unexpected_private_response_are_sanitized(self):
        from common.operations.content_store import StoreError
        for failure in (StoreError('conflict','secret-access'),RuntimeError('secret-refresh')):
            output=io.StringIO()
            with patch.object(self.fixture.service,'catalog',side_effect=failure),contextlib.redirect_stderr(output):
                status,_,data=self.request('/api/v2/oauth/catalog')
            self.assertIn(status,(409,503));self.assertNotIn(b'secret',data);self.assertNotIn('secret',output.getvalue())
        for result in ({'items':[],'credential_ref':'secret-access'},{'state':'secret-state'},{'surprise':'secret-access'}):
            with patch.object(self.fixture.service,'catalog',return_value=result):
                status,_,data=self.request('/api/v2/oauth/catalog')
            self.assertEqual(503,status);self.assertNotIn(b'secret',data)

    def test_real_store_http_inspect_target_cas_and_disconnect(self):
        started,state=self.start();self.assertEqual(303,self.callback(state)[0])
        path='/api/v2/oauth/attempts/'+started['attempt_id']
        item=self.json(path)[1]
        status,item,_=self.post(path+'/continue',dict(request_key='continue',expected_revision=item['revision']))
        self.assertEqual(200,status)
        status,item,_=self.post(path+'/inspect',dict(request_key='inspect',expected_revision=item['revision']))
        self.assertEqual(200,status);proposal=item['target_proposal']
        confirm='/api/v2/oauth/targets/'+proposal['proposal_id']+'/confirm'
        self.assertEqual(409,self.post(confirm,dict(request_key='stale',expected_base_revision='wrong',expected_connection_revision=0))[0])
        status,connection,_=self.post(confirm,dict(request_key='confirm',expected_base_revision='base',expected_connection_revision=0))
        self.assertEqual(200,status);self.assertEqual('connected',connection['state']);self.assertFalse(connection['execution_enabled'])
        status,listing,_=self.json('/api/v2/connections')
        self.assertEqual(200,status);self.assertEqual('connected',listing['items'][0]['state'])
        self.assertNotIn('credential_ref',json.dumps(listing))
        revision=listing['items'][0]['connection_revision']
        lifecycle='/api/v2/oauth/connections/personal.youtube/'
        status,refreshed,_=self.post(lifecycle+'refresh',dict(request_key='refresh',expected_base_revision='base',expected_connection_revision=revision))
        self.assertEqual(200,status);self.assertIn('refresh',self.fixture.provider.calls)
        self.assertFalse(refreshed['execution_enabled'])
        # Google project 영향 미확인이면 명시 revoke여도 원격 전송하지 않는다.
        status,_,_=self.post(lifecycle+'revoke',dict(request_key='revoke',expected_base_revision='base',expected_connection_revision=refreshed['connection_revision']))
        self.assertEqual(409,status);self.assertNotIn('revoke',self.fixture.provider.calls)
        listing=self.json('/api/v2/oauth/connections')[1]
        body=dict(request_key='disconnect',expected_base_revision='base',expected_connection_revision=listing['items'][0]['connection_revision'])
        status,result,_=self.post('/api/v2/oauth/connections/personal.youtube/disconnect',body)
        self.assertEqual(200,status);self.assertEqual('disconnected',result['state'])
        self.assertIsNone(self.fixture.registry.connections['personal.youtube'].credential_ref)

    def test_main_rejects_test_callback_before_initialization_and_closes(self):
        from unittest.mock import Mock
        server=Mock(oauth_test_only=True,workspace_root=self.workspace)
        with patch.dict('os.environ',{'AX_SOURCE_ROOT':str(self.source)},clear=True),patch.object(self.module,'create_server',return_value=server):
            with self.assertRaises(SystemExit):self.module.main()
        server.content_store.initialize.assert_not_called();server.server_close.assert_called_once()

    def test_new_connection_id_is_server_issued_for_null_input(self):
        status,item,_=self.post('/api/v2/oauth/attempts',dict(self.fixture.body(),connection_id=None))
        self.assertEqual(200,status);self.assertIsInstance(item['connection_id'],str)
        self.assertNotEqual('',item['connection_id'])

    def test_authorization_metadata_is_public_but_token_fields_are_not(self):
        metadata=dict(observed_scopes=['read'],credential_expires_at=None,read_status='not_checked',
            publication_status='blocked',credential_status='pending')
        with patch.object(self.fixture.service,'catalog',return_value={'items':[{'authorization':metadata}],'live_enabled':False}):
            status,result,_=self.json('/api/v2/oauth/catalog')
        self.assertEqual(200,status);self.assertEqual(metadata,result['items'][0]['authorization'])
        with patch.object(self.fixture.service,'catalog',return_value={'items':[{'authorization':dict(metadata,access_token='secret-access')}]}):
            self.assertEqual(503,self.json('/api/v2/oauth/catalog')[0])

    def test_uninitialized_oauth_store_gets_do_not_create_database(self):
        from common.operations.oauth_store import OAuthAttemptStore
        from common.operations.managed_connections import ManagedConnectionStore
        root=self.root/'oauth-uninitialized'
        self.server.oauth_service=self.fixture.make_service(attempt_store=OAuthAttemptStore(root,self.fixture.clock),
            connection_store=ManagedConnectionStore(root,self.fixture.clock))
        for path in ('/api/v2/oauth/catalog','/api/v2/oauth/connections','/api/v2/oauth/result'):
            self.assertEqual(200,self.request(path)[0])
        self.assertEqual(503,self.post('/api/v2/oauth/attempts',self.fixture.body())[0])
        self.assertFalse(root.exists());self.assertEqual([],self.fixture.provider.calls)

    def test_callback_expiry_and_ticket_expiry_never_exchange(self):
        from datetime import timedelta
        _,state=self.start();self.fixture.now+=timedelta(minutes=11)
        self.assertEqual(409,self.callback(state)[0]);self.assertNotIn('exchange',self.fixture.provider.calls)
        # 만료된 첫 flow와 다른 키로 두 번째 flow를 시작한다.
        status,item,_=self.post('/api/v2/oauth/attempts',self.fixture.body('second'))
        self.assertEqual(200,status);state=parse_qs(urlsplit(item['authorize_url']).query)['state'][0]
        self.assertEqual(303,self.callback(state)[0]);self.fixture.now+=timedelta(seconds=121)
        path='/api/v2/oauth/attempts/'+item['attempt_id'];current=self.json(path)[1]
        self.assertEqual('expired',current['state'])
        self.assertEqual(409,self.post(path+'/continue',dict(request_key='continue-expired',expected_revision=current['revision']))[0])
        self.assertNotIn('exchange',self.fixture.provider.calls)

    def test_real_cost_guard_blocks_before_authorize(self):
        self.server.oauth_service=self.fixture.make_service(cost_guard=None)
        status,_,_=self.post('/api/v2/oauth/attempts',self.fixture.body())
        self.assertEqual(409,status);self.assertEqual([],self.fixture.provider.calls)
