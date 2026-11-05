"""배포 HTTP 계약: 임시 관리 저장소와 loopback만 사용한다."""
import http.client
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest

APP=Path(__file__).resolve().parents[1]/'ax-console/app'
if str(APP) not in sys.path:sys.path.insert(0,str(APP))
from web_deliveries import handle
from common.operations.content_store import ContentStore,StoreError
from common.operations.ledger import Ledger

class Auth:
    KEYFILE=None
    def is_setup(self):return True
    def cookie_of(self,h):return h
    def check(self,token):return token=='fixture'

class DeliveryBoundaryTests(unittest.TestCase):
    def test_forbidden_approval_fields_and_wrong_methods(self):
        with self.assertRaises(StoreError): handle(None,'POST','/api/v2/deliveries/delivery_'+'a'*32+'/approvals',{},lambda:{'actor':'admin'})
        self.assertIsNone(handle(None,'DELETE','/api/v2/connections',{},lambda:{}))

    def test_destination_scope_includes_personal_original_without_fake_variant(self):
        from workspace_snapshot import compose_workspace_snapshot
        with tempfile.TemporaryDirectory() as temp:
            store=ContentStore(Path(temp)/'workspace');store.initialize()
            ledger=Ledger(store.root,content_store=store);ledger.initialize()
            c=store.create('personal',{'title':'개인 원본 · 학과 계획','kind':'short','original':'원문'})
            unrelated=store.create('personal',{'title':'관련 없는 개인 원본','kind':'article'})
            ledger.create_or_get_delivery(dict(content_id=c['id'],revision=c['revision'],manifest_hash=c['manifest_hash'],connection_id='dept.tiktok',crosspost_rule_id='geoai-short.tiktok',publication_purpose='initial',schedule_slot='fixture',scheduled_at='2026-11-02T10:00:00+09:00',timezone='Asia/Seoul'))
            s=compose_workspace_snapshot({'contents':[],'deliveries':[],'schedule':[]},store.root,'dept',ledger=ledger)
            self.assertEqual([item['id'] for item in s['contents']],[c['id']])
            self.assertEqual(s['contents'][0]['owner_account_id'],'personal')
            self.assertIn('dept',s['contents'][0]['target_accounts'])
            self.assertEqual(s['schedule'][0]['title'],c['title'])
            self.assertEqual(store.get(c['id'])['variants'],[])
            self.assertEqual(store.get(unrelated['id'])['variants'],[])

class DeliveryHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location('phase3_server',APP/'web_server.py')
        cls.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.module)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name); self.workspace=root/'workspace';self.source=root/'source';self.source.mkdir()
        self.server=self.module.create_server(source_root=self.source,workspace_root=self.workspace,web_root=APP/'web',auth_backend=Auth(),snapshot_builder=lambda *a,**k:{'contents':[],'deliveries':[],'schedule':[]})
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.stop)

    def stop(self):self.server.shutdown();self.server.server_close();self.thread.join()

    def request(self,path,method='GET',body=None,authed=True,raw=None,extra_headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        headers={'Content-Type':'application/json'}
        if authed:headers['Cookie']='fixture'
        headers.update(extra_headers or {})
        try:
            conn.request(method,path,body=raw if raw is not None else json.dumps(body) if body is not None else None,headers=headers)
            response=conn.getresponse();data=json.loads(response.read());status=response.status;return status,data
        finally: conn.close()

    def content(self):
        self.server.content_store.initialize();self.server.ledger.initialize()
        c=self.server.content_store.create('personal',{'title':'HTTP 계획','kind':'article'})
        return dict(content_id=c['id'],revision=c['revision'],manifest_hash=c['manifest_hash'],connection_id='personal.youtube',publication_purpose='initial',schedule_slot='http-main',scheduled_at='2026-11-02T10:00:00+09:00',timezone='Asia/Seoul')

    def test_factory_get_no_migration_auth_and_source_readonly(self):
        self.assertFalse(self.workspace.exists())
        self.assertEqual(self.request('/api/v2/connections',authed=False)[0],401)
        self.assertEqual(self.request('/api/v2/connections')[0],200)
        self.assertFalse(self.workspace.exists())
        self.assertEqual(self.request('/api/v2/deliveries')[0],503)
        self.assertFalse(self.workspace.exists())
        self.server.workspace_root=None
        self.assertEqual(self.request('/api/v2/deliveries','POST',{})[0],405)

    def test_roundtrip_contract_errors_and_snapshot(self):
        body=self.content()
        status,connections=self.request('/api/v2/connections');self.assertEqual(status,200)
        self.assertNotIn('credential',json.dumps(connections));self.assertNotIn('profile',json.dumps(connections))
        self.assertEqual(self.request('/api/v2/deliveries','POST',dict(body,status='published'))[0],400)
        self.assertEqual(self.request('/api/v2/deliveries/preview','POST',body)[0],200)
        self.assertEqual(self.request('/api/v2/deliveries')[1],{'items':[]})
        status,r=self.request('/api/v2/deliveries','POST',body);self.assertEqual(status,200)
        self.assertEqual(self.request('/api/v2/deliveries','POST',body)[1]['id'],r['id'])
        url='/api/v2/deliveries/'+r['id']
        self.assertEqual(self.request(url)[1],r)
        self.assertEqual(self.request('/api/v2/deliveries?account=personal&content_id='+body['content_id'])[1]['items'][0]['id'],r['id'])
        status,r=self.request(url+'/approvals','POST',dict(expected_version=1,subject_hash=r['subject_hash'],decision='approved',notes=''))
        self.assertEqual(status,200);self.assertEqual(r['status'],'ready')
        args=dict(expected_version=2,scheduled_at='2026-11-02T11:00:00+09:00',timezone='Asia/Seoul')
        status,p=self.request(url+'/schedule-preview','POST',args);self.assertEqual(status,200)
        status,r=self.request(url+'/schedule','PUT',dict(args,preview_hash=p['preview_hash']));self.assertEqual(status,200);self.assertEqual(r['status'],'pending')
        self.assertEqual(self.request(url+'/schedule','PUT',dict(args,preview_hash=p['preview_hash']))[0],409)
        status,r=self.request(url+'/cancel','POST',dict(expected_version=3));self.assertEqual(status,200);self.assertEqual(r['status'],'cancelled')
        self.assertEqual(len(self.request(url+'/events')[1]['items']),4)
        status,snapshot=self.request('/api/v2/snapshot');self.assertEqual(status,200)
        self.assertEqual(snapshot['deliveries'][0]['schedule_kind'],'local_plan');self.assertEqual(snapshot['schedule'][0]['kind'],'local_plan')
        self.assertEqual(self.request('/api/v2/deliveries?account=common')[0],400)
        self.assertEqual(self.request(url+'/cancel','POST',{'expected_version':4,'execution_enabled':True})[0],400)
        self.assertEqual(self.request(url,'DELETE')[0],405)
        self.assertEqual(self.request('/api/v2/deliveries','POST',extra_headers={'Content-Length':str(1024*1024+1)})[0],413)

    def test_v1_get_does_not_migrate(self):
        self.content();conn=sqlite3.connect(self.workspace/'operations.sqlite3');conn.execute('PRAGMA user_version=1');conn.commit();conn.close()
        self.assertEqual(self.request('/api/v2/deliveries')[0],503)
        self.assertEqual(self.request('/api/v2/contents')[0],200)
        conn=sqlite3.connect(self.workspace/'operations.sqlite3');self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],1);conn.close()

if __name__=='__main__':unittest.main()
