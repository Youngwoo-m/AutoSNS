import json
from pathlib import Path
import tempfile
import threading
import unittest
from tests import test_web_execution_server as web_fixture
from tests import test_web_server as http_fixture
from common.operations.media_plans import default_media_plan

class MediaPlanHTTPTests(unittest.TestCase):
    request=http_fixture.WebServerTests.request
    login=http_fixture.WebServerTests.login
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.server=web_fixture.server_module.create_server(source_root=self.root/'source',workspace_root=self.root/'managed',web_root=web_fixture.APP/'web',auth_backend=http_fixture.FakeAuth())
        self.server.content_store.initialize()
        self.content=self.server.content_store.create('personal',dict(title='대본',kind='short',original='원본'))
        self.path='/api/v2/contents/'+self.content['id']+'/media-plan?revision=1'
        thread=threading.Thread(target=self.server.serve_forever,daemon=True);thread.start()
        def close():self.server.shutdown();self.server.server_close();thread.join()
        self.addCleanup(close)
    def test_authenticated_cas_plan_is_inert_and_owner_is_server_bound(self):
        self.assertEqual(self.request(self.path)[0],401)
        cookie=self.login();status,_,body=self.request(self.path,headers=cookie)
        self.assertEqual(status,200);row=json.loads(body)
        self.assertEqual(row['plan_revision'],0);self.assertEqual(row['owner_account_id'],'personal')
        self.assertFalse((self.root/'managed/media-plans.sqlite3').exists())
        body=dict(expected_revision=0,plan=row['plan'])
        self.assertEqual(self.request(self.path,'POST',body,cookie)[0],503)
        self.server.media_plan_store.initialize();before=(self.root/'managed/operations.sqlite3').read_bytes()
        self.assertEqual(self.request(self.path,'POST',body,dict(cookie,Origin='https://evil.example'))[0],403)
        status,_,data=self.request(self.path,'POST',body,cookie)
        self.assertEqual(status,200);saved=json.loads(data)
        self.assertFalse(saved['execution_enabled']);self.assertEqual(saved['review_status'],'not_checked')
        self.assertEqual(self.request(self.path,'POST',body,cookie)[0],409)
        self.assertEqual(before,(self.root/'managed/operations.sqlite3').read_bytes())
        self.assertIsNone(self.server.execution_service)
    def test_schema_version_and_owner_injection_are_rejected(self):
        cookie=self.login();self.server.media_plan_store.initialize()
        plan=default_media_plan(self.content)
        for extra in (dict(owner_account_id='dept'),dict(path='/tmp/other'),dict(run=True)):
            self.assertEqual(self.request(self.path,'POST',dict(expected_revision=0,plan=plan,**extra),cookie)[0],400)
        for revision in ('0','-1','1&revision=2','1&account=dept',''):
            self.assertEqual(self.request('/api/v2/contents/'+self.content['id']+'/media-plan?revision='+revision,headers=cookie)[0],400)
        other=self.server.content_store.create('dept',dict(title='학과',kind='short'))
        status,_,body=self.request('/api/v2/contents/'+other['id']+'/media-plan?revision=1',headers=cookie)
        self.assertEqual(status,200);self.assertEqual(json.loads(body)['owner_account_id'],'dept')

    def test_explicit_import_uses_source_plan_cas_and_preserves_old_plan(self):
        cookie=self.login();store=self.server.media_plan_store;store.initialize()
        source=store.save(self.content['id'],1,0,default_media_plan(self.content))
        next_content=self.server.content_store.add_asset(self.content['id'],1,'image.png','image/png',b'\x89PNG\r\n\x1a\n'+b'x'*30)
        path='/api/v2/contents/'+self.content['id']+'/media-plan?revision=2'
        body=dict(action='import',expected_revision=0,source_revision=1,source_plan_revision=1,voice_asset_id=None)
        self.assertEqual(self.request(path,'POST',body,dict(cookie,Origin='https://evil.example'))[0],403)
        changed=store.save(self.content['id'],1,1,source['plan'])
        self.assertEqual(self.request(path,'POST',body,cookie)[0],409)
        body['source_plan_revision']=changed['plan_revision']
        source=changed
        status,_,raw=self.request(path,'POST',body,cookie)
        self.assertEqual(status,200);result=json.loads(raw)
        self.assertEqual(result['plan'],source['plan']);self.assertEqual(result['content_revision'],2)
        self.assertEqual(store.get(self.content['id'],1),source)
        self.assertEqual(self.request(path,'POST',body,cookie)[0],409)
        self.assertEqual(self.request(path,'POST',dict(body,owner_account_id='dept'),cookie)[0],400)
