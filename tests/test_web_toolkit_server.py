"""임시 loopback·등록부만 사용하는 로컬 SNS 도구 HTTP 경계."""
import http.client
import base64
import builtins
import importlib.util
import json
import shutil
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from common.operations.models import Registry, Connection
from common.operations.tool_cost_policy import ToolkitPolicy
from tests.test_web_metrics import Auth
APP=Path(__file__).resolve().parents[1]/'ax-console/app'
sys.path.insert(0,str(APP))
CSV='platform,target_id,remote_id,metric_name,value,observed_at,basis\nyoutube,target,remote,views,0,2026-01-01T00:00:00Z,lifetime\n'

class ToolkitHTTPTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('toolkit_http_fixture',APP/'web_server.py');self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.source=self.root/'source';self.source.mkdir();self.workspace=self.root/'managed'
        from tests.integration.test_local_toolkit_acceptance import product_webroot
        self.webroot=self.root/'web';product_webroot(self.webroot)
        self.registry=Registry('r1',{'personal':{},'dept':{}},{},{},{'c':Connection('c','personal','youtube',target_id='target')},{},{},{})
        self.server=self.module.create_server(source_root=self.source,workspace_root=self.workspace,web_root=self.webroot,auth_backend=Auth(),operations_registry=self.registry,toolkit_policy=ToolkitPolicy(True))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.stop)
    def stop(self):self.server.shutdown();self.server.server_close();self.thread.join()
    def request(self,path,method='GET',body=None,auth=True,origin=None,raw=None,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3);h={'Content-Type':'application/json'}
        if auth:h['Cookie']=Auth.COOKIE+'=fixture'
        if origin:h['Origin']=origin
        h.update(headers or {})
        try:
            conn.request(method,path,raw if raw is not None else json.dumps(body) if body is not None else None,h);response=conn.getresponse();data=response.read();return response.status,json.loads(data)
        finally:conn.close()
    def initialize(self):
        self.server.content_store.initialize();self.server.metrics_store.initialize()
        return self.server.content_store.create('personal',dict(title='원제목',kind='article',original='원문',variants=[dict(destination_account_id='personal',platform='youtube',text='본문')]))
    def test_tools_auth_origin_body_limits_and_readonly(self):
        url='/api/v2/tools/capabilities'
        self.assertEqual(self.request(url,auth=False)[0],401);self.assertEqual(self.request(url,origin='https://evil.test')[0],403)
        self.assertEqual(self.request(url+'?account=dept&account=personal')[0],400);self.assertEqual(self.request(url+'?cost=free')[0],400)
        self.assertEqual(self.request(url)[0],200);self.assertFalse(self.workspace.exists());self.assertEqual(list(self.source.iterdir()),[])
        for raw in ('{"account_id":"personal","account_id":"dept"}','{"account_id":NaN}'):
            self.assertEqual(self.request('/api/v2/tools/research-preview','POST',raw=raw)[0],400)
        self.assertEqual(self.request('/api/v2/tools/research-preview','POST',{},headers={'Content-Length':str(1024*1024+1)})[0],413)
        self.assertEqual(self.request('/api/v2/tools/research-preview','POST',dict(account_id='personal'))[0],503)
    def test_csv_import_receipt_keeps_operations_unchanged(self):
        self.initialize();before=(self.workspace/'operations.sqlite3').read_bytes()
        status,preview=self.request('/api/v2/tools/metrics-csv-preview','POST',dict(account_id='personal',csv_text=CSV));self.assertEqual(status,200)
        self.assertNotIn('plan',preview);self.assertNotIn('source',preview['rows'][0]);body=dict(account_id='personal',csv_text=CSV,preview_digest=preview['preview_digest'],request_key='fixture-import')
        first=self.request('/api/v2/tools/metrics-csv-import','POST',body);self.assertEqual(first[0],200);self.assertEqual(first,self.request('/api/v2/tools/metrics-csv-import','POST',body));self.assertEqual(before,(self.workspace/'operations.sqlite3').read_bytes())
        self.assertEqual(self.server.metrics_store.list_observations()[0]['status'],'legacy_reported')
        self.assertEqual(self.request('/api/v2/tools/metrics-csv-import','POST',dict(body,csv_text=CSV.replace(',0,',',1,')))[0],409)
    def test_cost_and_target_tampering_never_calls_leaf(self):
        c=self.initialize();body=dict(content_id=c['id'],revision=c['revision'],connection_id='c',keywords=[])
        with patch('common.operations.local_toolkit.build_packaging_preview') as leaf:
            for key in ('cost','target_id','provider','credential','policy'):
                self.assertEqual(self.request('/api/v2/tools/packaging-preview','POST',dict(body,**{key:'free'}))[0],400)
            leaf.assert_not_called()
        with patch('common.operations.local_toolkit.evaluate_tool_action',return_value=dict(allowed=False,reason_codes=['cost_not_zero'])),patch('common.operations.local_toolkit.build_packaging_preview') as leaf:
            status,result=self.request('/api/v2/tools/packaging-preview','POST',body);self.assertEqual(status,200);self.assertEqual(result['status'],'blocked');leaf.assert_not_called()
        self.assertEqual(self.request('/api/v2/tools/packaging-preview','POST',dict(body,revision=999))[0],409)
        self.assertIs(self.server.toolkit_service.content_store,self.server.content_store);self.assertIs(self.server.toolkit_service.metrics_store,self.server.metrics_store);self.assertIs(self.server.toolkit_service.runtime_store,self.server.runtime_store)
    def test_full_cas_save_after_staging_requires_new_review(self):
        c=self.initialize();self.server.content_store.record_review(c['id'],1,c['manifest_hash'],'source','pass','fixture')
        status,preview=self.request('/api/v2/tools/packaging-preview','POST',dict(content_id=c['id'],revision=1,connection_id='c',keywords=['측량']));self.assertEqual(status,200)
        candidate=next(candidate for candidate in preview['candidates'] if candidate['title']!=c['title'])
        payload={key:c[key] for key in ('title','kind','series','status','original','variants','sources')};payload.update(title=candidate['title'],expected_revision=1)
        status,new=self.request('/api/v2/contents/'+c['id'],'PUT',payload);self.assertEqual(status,200);self.assertEqual(new['revision'],2);self.assertEqual(new['reviews'],[]);self.assertNotEqual(new['manifest_hash'],c['manifest_hash'])
        self.assertEqual(self.request('/api/v2/contents/'+c['id'],'PUT',payload)[0],409)

    def test_default_disabled_and_static_modules_require_auth(self):
        server=self.module.create_server(source_root=self.source,workspace_root=self.workspace,web_root=self.webroot,auth_backend=Auth(),operations_registry=self.registry)
        try:
            self.assertFalse(server.toolkit_service.policy.enabled);self.assertFalse(server.execution_policy.enabled)
            self.assertIsNone(server.toolkit_service.thumbnail_renderer);self.assertIsNone(server.toolkit_service.thumbnail_authorizer)
            self.assertFalse(self.workspace.exists())
        finally:server.server_close()
        for name in ('toolkit_api.js','toolkit_controller.js','toolkit_panel.js'):
            for authed,want in ((False,401),(True,200)):
                conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
                try:
                    conn.request('GET','/web/'+name,headers={'Cookie':Auth.COOKIE+'=fixture'} if authed else {});response=conn.getresponse();self.assertEqual(response.status,want);response.read()
                finally:conn.close()

    def test_enabled_thumbnail_render_without_renderer_is_unavailable(self):
        c=self.initialize()
        self.assertTrue(self.server.toolkit_service.policy.enabled)
        self.assertIsNone(self.server.toolkit_service.thumbnail_renderer)
        status,result=self.request('/api/v2/tools/thumbnail-render','POST',dict(content_id=c['id'],revision=c['revision'],asset_id=None,preset_id='landscape.v1',title='제목'))
        self.assertEqual(status,200)
        self.assertEqual(result,dict(status='unavailable',reason_codes=['renderer_unavailable']))
        self.assertFalse(self.server.execution_policy.enabled)

    def test_enabled_thumbnail_inspect_without_decoder_is_unavailable(self):
        c=self.initialize()
        # 실제 저장소의 hash/자산 읽기 경로를 통과하는 고정 PNG다.
        png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a1ZkAAAAASUVORK5CYII=')
        c=self.server.content_store.add_asset(c['id'],c['revision'],'fixture.png','image/png',png)
        body=dict(content_id=c['id'],revision=c['revision'],asset_id=c['assets'][0]['id'])
        def assert_unavailable():
            status,result=self.request('/api/v2/tools/thumbnail-inspect','POST',body)
            self.assertEqual(status,200)
            self.assertEqual(result['status'],'unavailable')
            self.assertEqual(result['findings'],['decoder_unavailable'])
            self.assertEqual(result['sha256'],c['assets'][0]['sha256'])
            self.assertIsNone(result['width']);self.assertIsNone(result['height'])
        # Python3.15의 실제 decoder 부재도 별도로 확인한다. Pillow 환경에서는
        # 아래 import 경계 반례로 같은 응답 계약을 skip 없이 검증한다.
        if importlib.util.find_spec('PIL') is None:
            with self.subTest(decoder='environment_absent'):assert_unavailable()
        original_import=builtins.__import__
        def without_pillow(name,*args,**kwargs):
            if name=='PIL' or name.startswith('PIL.'):raise ImportError('fixture decoder absent')
            return original_import(name,*args,**kwargs)
        with self.subTest(decoder='import_boundary_absent'),patch('builtins.__import__',side_effect=without_pillow):
            assert_unavailable()
