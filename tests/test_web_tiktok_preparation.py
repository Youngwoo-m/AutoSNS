"""가짜 로그인과 localhost만 사용하는 TikTok 로컬 준비 HTTP 시험."""
import http.client
import json
import unittest

from tests import test_web_deliveries as fixture
from tests.operations.test_tiktok_preparation import create_plan, Probe, PUBLIC_KEYS, CAPTION, VIDEO, NOW


class TikTokPreparationHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.DeliveryHTTPTests.setUpClass.__func__(cls)
    setUp=fixture.DeliveryHTTPTests.setUp
    stop=fixture.DeliveryHTTPTests.stop
    request=fixture.DeliveryHTTPTests.request

    def plan(self,**kwargs):
        self.server.content_store.initialize();self.server.ledger.initialize()
        item,plan=create_plan(self.server.content_store,self.server.ledger,**kwargs)
        return item,plan,'/api/v2/deliveries/'+plan['id']+'/tiktok-preparation'

    def assert_safe(self,value):
        serialized=json.dumps(value,ensure_ascii=False)
        for private in ('private-original.mp4',str(self.workspace),'access_token','authorization','credential','publish_id','upload_url'):
            self.assertNotIn(private,serialized)
        self.assertIs(value['publication_enabled'],False)
        self.assertEqual(value['status'],'local_preparation_only')
        self.assertTrue(value['asset_url'].startswith('/api/v2/contents/'))

    def test_auth_missing_plan_no_initialization_and_method_boundary(self):
        path='/api/v2/deliveries/delivery_'+'a'*32+'/tiktok-preparation'
        self.assertEqual(self.request(path,authed=False)[0],401)
        self.assertEqual(self.request(path)[0],503)
        self.assertFalse(self.workspace.exists())
        self.assertEqual(self.request(path,'POST',{})[0],405)
        self.assertEqual(self.request(path+'/check')[0],405)
        self.assertEqual(self.request(path+'/check','PUT',{})[0],405)
        self.assertFalse(self.workspace.exists())

    def test_get_preserves_owner_caption_and_exact_relative_asset_download(self):
        item,plan,path=self.plan()
        status,value=self.request(path)
        self.assertEqual(status,200,value);self.assertEqual(set(value),PUBLIC_KEYS)
        self.assertEqual(value['owner_account_id'],'personal');self.assertEqual(value['destination_account_id'],'dept')
        self.assertEqual(value['caption'],CAPTION);self.assertIsNone(value['technical_check'])
        self.assertIs(value['technical_check_available'],False);self.assert_safe(value)
        self.assertEqual(value['asset_url'],f"/api/v2/contents/{item['id']}/revisions/{item['revision']}/assets/{item['assets'][0]['id']}")
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        try:
            conn.request('GET',value['asset_url'],headers={'Cookie':'fixture'})
            response=conn.getresponse();self.assertEqual(response.status,200)
            self.assertEqual(response.getheader('Content-Type'),'video/mp4');self.assertEqual(response.read(),VIDEO)
        finally:conn.close()
        self.assertEqual(self.server.content_store.get(item['id']),item)
        self.assertFalse(self.server.ledger.registry().connections['dept.tiktok'].enabled)

    def test_check_origin_queries_body_stale_and_probe_opt_in(self):
        item,plan,path=self.plan();status,value=self.request(path);self.assertEqual(status,200)
        body={'preparation_hash':value['preparation_hash']}
        self.assertEqual(self.request(path+'/check','POST',body,authed=False)[0],401)
        self.assertEqual(self.request(path+'/check','POST',body,extra_headers={'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request(path+'?account=dept')[0],400)
        self.assertEqual(self.request(path+'/check?extra=1','POST',body)[0],400)
        for invalid in ({},{**body,'actor':'admin'},[],{**body,'publication_enabled':True}):
            with self.subTest(body=invalid):self.assertEqual(self.request(path+'/check','POST',invalid)[0],400)
        self.assertEqual(self.request(path+'/check','POST',{'preparation_hash':'0'*64})[0],409)
        self.assertEqual(self.request(path+'/check','POST',body)[0],503)
        probe=Probe();self.server.tiktok_preparation_service.probe=probe
        self.server.tiktok_preparation_service.clock=lambda:NOW
        self.assertEqual(self.request(path)[0],200);self.assertEqual(probe.calls,[])
        status,checked=self.request(path+'/check','POST',body)
        self.assertEqual(status,200,checked);self.assertEqual(probe.calls,[VIDEO])
        self.assertEqual(checked['technical_check']['checked_at'],NOW.isoformat());self.assert_safe(checked)
        self.assertIsNone(self.request(path)[1]['technical_check'])
        self.server.content_store.update(item['id'],item['revision'],dict(title='변경된 원고',kind='short',original='변경'))
        self.assertEqual(self.request(path+'/check','POST',body)[0],409)
        self.assertEqual(len(probe.calls),1)

    def test_cancelled_and_legacy_plan_remain_non_publishable(self):
        _,plan,path=self.plan()
        self.server.ledger.cancel(plan['id'],plan['version'])
        self.assertEqual(self.request(path)[0],404)
        _,legacy,path=self.plan(owner='dept',slot='legacy',selection=False)
        self.assertEqual(legacy['options'],{})
        self.assertEqual(self.request(path)[0],400)

    def test_preparation_panel_is_authenticated_static_javascript(self):
        for authed,expected in ((False,401),(True,200)):
            conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
            try:
                conn.request('GET','/web/tiktok_preparation_panel.js',headers={'Cookie':'fixture'} if authed else {})
                response=conn.getresponse();self.assertEqual(response.status,expected)
                if authed:self.assertIn('javascript',response.getheader('Content-Type'))
                response.read()
            finally:conn.close()
        self.assertFalse(self.workspace.exists())
