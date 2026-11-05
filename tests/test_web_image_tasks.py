import hashlib,json,struct,tempfile,threading
from pathlib import Path
import unittest
from tests import test_web_execution_server as web_fixture
from tests import test_web_server as http_fixture
from common.operations.image_tasks import ImageTaskStore,ImageTaskService

SPEC=dict(template='steps',title='안전 점검',body=['확인','기록'],footer='검토 전')
class ImageTaskHTTPTests(unittest.TestCase):
    request=http_fixture.WebServerTests.request
    login=http_fixture.WebServerTests.login
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.server=web_fixture.server_module.create_server(source_root=self.root/'source',workspace_root=self.root/'managed',web_root=web_fixture.APP/'web',auth_backend=http_fixture.FakeAuth())
        self.server.content_store.initialize();self.server.image_task_store.initialize()
        self.content=self.server.content_store.create('personal',dict(title='개인 원고',kind='card'))
        self.calls=[]
        def runner(spec,*,owner_account_id,artifact_root):
            self.calls.append((spec,owner_account_id))
            path=artifact_root/'card.png';raw=b'\x89PNG\r\n\x1a\n'+struct.pack('>I',13)+b'IHDR'+struct.pack('>II',1080,1350)+b'\x08\x02\x00\x00\x00'+b'\x00'*20;path.write_bytes(raw)
            return dict(path=str(path),size=len(raw),sha256=hashlib.sha256(raw).hexdigest(),width=1080,height=1350)
        self.server.image_task_service=ImageTaskService(self.server.image_task_store,self.server.content_store,runner=runner,enabled=True)
        self.path='/api/v2/contents/'+self.content['id']+'/image-tasks'
        thread=threading.Thread(target=self.server.serve_forever,daemon=True);thread.start()
        def close():self.server.shutdown();self.server.server_close();thread.join()
        self.addCleanup(close)
    def test_auth_origin_server_owner_idempotence_and_version_filter(self):
        self.assertEqual(self.request(self.path+'?revision=1')[0],401)
        cookie=self.login();body=dict(expected_revision=1,spec=SPEC)
        self.assertEqual(self.request(self.path,'POST',body,dict(cookie,Origin='https://evil.example'))[0],403)
        self.assertEqual(self.request(self.path,'POST',dict(body,owner_account_id='dept'),cookie)[0],400)
        status,_,raw=self.request(self.path,'POST',body,cookie);self.assertEqual(status,200)
        row=json.loads(raw);self.assertEqual(row['state'],'completed');self.assertEqual(row['review_status'],'not_checked')
        self.assertEqual(set(row),{'task_id','state','reason_code','content_id','input_revision','output_revision','asset_id','review_status'})
        self.assertEqual(self.calls[0][1],'personal')
        self.assertEqual(self.request(self.path,'POST',body,cookie)[0],200);self.assertEqual(len(self.calls),1)
        status,_,raw=self.request(self.path+'?revision=2',headers=cookie);self.assertEqual(json.loads(raw),{'items':[]})
        status,_,raw=self.request(self.path+'?revision=1',headers=cookie);self.assertEqual(len(json.loads(raw)['items']),1)
        for query in ('','?revision=0','?revision=1&revision=2','?revision=1&owner=dept'):
            self.assertEqual(self.request(self.path+query,headers=cookie)[0],400)
    def test_default_web_has_no_renderer_and_no_native_fallback(self):
        self.server.image_task_service=None;cookie=self.login()
        status,_,raw=self.request('/api/v2/capabilities/image-production',headers=cookie)
        self.assertEqual(status,200);self.assertFalse(json.loads(raw)['execution_enabled'])
        self.assertEqual(self.request(self.path,'POST',dict(expected_revision=1,spec=SPEC),cookie)[0],503)
        self.assertEqual(self.calls,[])
