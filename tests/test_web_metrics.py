"""성과 HTTP 경계는 임시 source/auth/W만 사용한다."""
import http.client
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from common.operations.metrics_store import MetricsStore
from common.operations.content_store import ConflictError, StoreError
from common.operations.models import Connection, Registry
from tests.operations.test_metrics_store import observation

APP = Path(__file__).resolve().parents[1] / 'ax-console/app'
sys.path.insert(0, str(APP))

class Auth:
    KEYFILE = None
    COOKIE = 'ax_phase5_fixture_session'
    def cookie_of(self, header):
        return (header or '').removeprefix(self.COOKIE + '=')
    def check(self, token): return token == 'fixture'
    def is_setup(self): return True

class ImportReceiptTests(unittest.TestCase):
    def test_receipt_survives_reopen_and_replays_original_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            store = MetricsStore(temp); store.initialize()
            plan = dict(preview_digest='digest-a', observations=[dict(observation_key='one', observation=observation())])
            first = store.import_rows(plan, request_key='request-one')
            self.assertEqual(first['imported'], 1)
            reopened = MetricsStore(temp)
            self.assertEqual(reopened.get_import_result('digest-a', 'request-one'), first)
            reopened.initialize()
            self.assertEqual(reopened.import_rows(plan, request_key='request-one'), first)
            with self.assertRaises(ConflictError): reopened.get_import_result('digest-b', 'request-one')
            self.assertEqual(len(reopened.list_observations()), 1)
    def test_failed_import_leaves_no_receipt_or_partial_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            store = MetricsStore(temp); store.initialize()
            plan = dict(preview_digest='digest', observations=[dict(observation_key='one', observation=observation()),dict(bad=True)])
            with self.assertRaises(StoreError): store.import_rows(plan, request_key='failed')
            self.assertIsNone(store.get_import_result('digest', 'failed'))
            self.assertEqual(store.list_observations(), [])

    def test_concurrent_same_request_has_one_original_result(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as temp:
            store=MetricsStore(temp);store.initialize()
            plan=dict(preview_digest='digest',observations=[dict(observation_key='one',observation=observation())])
            def send(_):
                writer=MetricsStore(temp);writer.initialize()
                return writer.import_rows(plan,request_key='simultaneous')
            with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(send,range(2)))
            self.assertEqual(results[0],results[1]);self.assertEqual(results[0]['imported'],1)
            self.assertEqual(len(store.list_observations()),1)

class MetricsHTTPTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('metrics_server_test', APP / 'web_server.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name); self.source = root / 'source'; self.source.mkdir(); self.workspace = root / 'managed'
        self.registry = Registry('r1', {'personal': {}, 'dept': {}}, {}, {}, {'dept-youtube': Connection('dept-youtube', 'dept', 'youtube', target_id='@dept')}, {}, {}, {})
        self.server = module.create_server(source_root=self.source, workspace_root=self.workspace, web_root=APP/'web', auth_backend=Auth(), operations_registry=self.registry, snapshot_builder=lambda *a, **kw: dict(proposals=[], contents=[], warnings=[]))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start(); self.addCleanup(self.stop)
    def stop(self): self.server.shutdown(); self.server.server_close(); self.thread.join()
    def request(self, path, method='GET', body=None, auth=True, origin=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        headers = {'Content-Type': 'application/json'}
        if auth: headers['Cookie'] = Auth.COOKIE + '=fixture'
        if origin: headers['Origin'] = origin
        try:
            conn.request(method, path, json.dumps(body) if body is not None else None, headers)
            response = conn.getresponse(); return response.status, json.loads(response.read())
        finally: conn.close()
    def write_source(self, views=0):
        parts = self.source / 'common/analytics/snapshots/parts'; parts.mkdir(parents=True, exist_ok=True)
        (parts/'youtube.json').write_text(json.dumps(dict(channel={'handle':'@dept','token':'SECRET'},items=[dict(id='v1',views=views,title='옛 영상')])) )
    def test_auth_origin_get_no_initialization_or_external_calls(self):
        for path in ('/api/v2/metrics', '/api/v2/metrics/import-preview'):
            self.assertEqual(self.request(path, auth=False)[0], 401)
            self.assertEqual(self.request(path, origin='https://evil.test')[0], 403)
            with patch('common.operations.metrics.collect_delivery_metrics', side_effect=AssertionError('collector called')):
                status, data = self.request(path); self.assertEqual(status, 200); self.assertFalse(data['writable'])
        self.assertFalse(self.workspace.exists()); self.assertEqual(list(self.source.iterdir()), [])
        for query in ('account=bad','account=personal&account=dept','collect=true'):
            self.assertEqual(self.request('/api/v2/metrics?' + query)[0], 400)
        self.assertEqual(self.request('/api/v2/metrics/collect', 'POST', {})[0], 400)
        self.assertEqual(self.request('/api/v2/metrics/collect', 'POST', {'delivery_id':'d'})[0], 503)
        code,data=self.request('/api/v2/metrics/collection-targets?account=personal')
        self.assertEqual(code,200);self.assertEqual(data,{'account_id':'personal','execution_enabled':False,'items':[]})
    def test_post_auth_origin_and_initialized_get_bytes_unchanged(self):
        import hashlib
        for path,body in (('/api/v2/metrics/import',dict(preview_digest='a'*64,request_key='unauth')),('/api/v2/metrics/proposals',dict(account_id='personal',observation_ids=['none'],title='제안',note='',request_key='unauth'))):
            self.assertEqual(self.request(path,'POST',body,auth=False)[0],401)
            self.assertEqual(self.request(path,'POST',body,origin='http://evil.test')[0],403)
        self.server.metrics_store.initialize();self.write_source()
        files=[self.workspace/'metrics.sqlite3',self.source/'common/analytics/snapshots/parts/youtube.json']
        before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        for path in ('/api/v2/metrics','/api/v2/metrics/import-preview'):
            self.assertEqual(self.request(path)[0],200)
        self.assertEqual(before,{p:hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    def test_import_fresh_digest_replay_source_changes_and_strict_fields(self):
        self.server.metrics_store.initialize(); self.write_source()
        status, preview = self.request('/api/v2/metrics/import-preview'); self.assertEqual(status, 200)
        self.assertNotIn('SECRET', json.dumps(preview)); self.assertNotIn('parts', preview)
        self.assertTrue(all(row.get('id','').startswith('preview_') for row in preview['observations']))
        self.assertNotIn(str(self.source), json.dumps(preview)); self.assertTrue(preview['writable'])
        body = dict(preview_digest=preview['preview_digest'], request_key='import-one')
        self.write_source(2)
        self.assertEqual(self.request('/api/v2/metrics/import', 'POST', body)[0], 409)
        preview = self.request('/api/v2/metrics/import-preview')[1]; body['preview_digest'] = preview['preview_digest']
        first = self.request('/api/v2/metrics/import', 'POST', body); self.assertEqual(first[0], 200); self.assertGreater(first[1]['imported'], 0)
        self.write_source(9)
        self.server.metrics_store = MetricsStore(self.workspace); self.server.metrics_store.initialize()
        self.assertEqual(self.request('/api/v2/metrics/import', 'POST', body), first)
        newer = self.request('/api/v2/metrics/import-preview')[1]
        self.assertEqual(self.request('/api/v2/metrics/import', 'POST', dict(body,preview_digest=newer['preview_digest']))[0], 409)
        self.assertEqual(self.request('/api/v2/metrics/import', 'POST', dict(body,account_id='personal'))[0], 400)
    def test_account_isolation_and_unknown_legacy_not_personal(self):
        store = self.server.metrics_store; store.initialize()
        store.append_observation(observation(owner_account_id='dept',destination_account_id='dept'), 'dept')
        store.append_observation(observation(source_kind='legacy_reported',status='legacy_reported',owner_account_id=None,destination_account_id=None,uncertainties=['owner_unknown','destination_unknown']), 'unknown')
        self.assertEqual(self.request('/api/v2/metrics?account=personal')[1]['observations'], [])
        all_rows = self.request('/api/v2/metrics')[1]; self.assertEqual(len(all_rows['observations']), 2); self.assertEqual(all_rows['summary']['unassigned'], 1)
        self.assertFalse(all_rows['collection_enabled'])
    def test_proposal_retry_reopen_and_no_content_approval_execution(self):
        store = self.server.metrics_store; store.initialize()
        row = store.append_observation(observation(), 'basis')
        body = dict(account_id='personal',observation_ids=[row['id']],title='수동 제안',note='근거 메모',request_key='proposal-one')
        with patch.object(self.server.content_store,'create',side_effect=AssertionError('content created')):
            first = self.request('/api/v2/metrics/proposals','POST',body); self.assertEqual(first[0], 200)
            self.server.metrics_store = MetricsStore(self.workspace); self.server.metrics_store.initialize()
            self.assertEqual(self.request('/api/v2/metrics/proposals','POST',body),first)
            self.assertEqual(self.request('/api/v2/metrics/proposals','POST',dict(body,title='다른 제안'))[0],409)
        self.assertEqual(first[1]['proposal']['status'],'draft'); self.assertNotIn('content_id',first[1]['proposal'])
        self.assertEqual(len(self.server.metrics_store.list_proposals()),1)
        self.assertFalse((self.workspace/'operations.sqlite3').exists())
        self.assertEqual(list(self.source.iterdir()),[])
        snapshot = self.request('/api/v2/snapshot?account=personal')[1]
        self.assertEqual(snapshot['metric_proposals'],[first[1]['proposal']]); self.assertEqual(snapshot['proposals'],[])
    def test_readonly_without_workspace_and_uninitialized_write_fail(self):
        self.assertEqual(self.request('/api/v2/metrics/import','POST',dict(preview_digest='a',request_key='b'))[0],503)
        self.server.metrics_store = None; self.server.workspace_root = None
        self.assertFalse(self.request('/api/v2/metrics')[1]['writable'])
        self.assertEqual(self.request('/api/v2/metrics/proposals','POST',{})[0],503)
        self.assertFalse(self.workspace.exists())

class MetricsBoundaryTests(unittest.TestCase):
    def test_uninitialized_read_is_pure_and_write_blocked(self):
        from web_metrics import handle
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); source=root/'source';source.mkdir(); managed=root/'managed'
            registry=Registry('r',{'personal':{},'dept':{}},{},{},{},{},{},{})
            store=MetricsStore(managed)
            data=handle(store,'GET','/api/v2/metrics',{},lambda:{},source_root=source,registry=registry)
            self.assertFalse(data['writable']); self.assertEqual(data['observations'],[])
            self.assertFalse(managed.exists())
            with self.assertRaises(StoreError):handle(store,'POST','/api/v2/metrics/import',{},lambda:{},source_root=source,registry=registry)
    def test_snapshot_and_proposal_strict_contract(self):
        from web_metrics import handle
        with tempfile.TemporaryDirectory() as temp:
            registry=Registry('r',{'personal':{},'dept':{}},{},{},{},{},{},{})
            store=MetricsStore(temp);store.initialize(); row=store.append_observation(observation(),'one')
            body=dict(account_id='personal',observation_ids=[row['id']],title='제안',note='',request_key='new')
            def send(body):return handle(store,'POST','/api/v2/metrics/proposals',{},lambda:body,source_root=Path(temp),registry=registry)
            first=send(body);self.assertEqual(send(body),first)
            with self.assertRaises(ConflictError):send(dict(body,note='변경'))
            with self.assertRaises(StoreError):send(dict(body,content_id='forged'))
            data=handle(store,'GET','/api/v2/metrics',{'account':['dept']},lambda:{},source_root=Path(temp),registry=registry)
            self.assertEqual(len(data['observations']),1); self.assertEqual(data['proposals'],[])

    def test_public_snapshot_omits_unregistered_source_secrets(self):
        from web_metrics import handle
        with tempfile.TemporaryDirectory() as temp:
            registry=Registry('r',{'personal':{},'dept':{}},{},{},{},{},{},{})
            store=MetricsStore(temp); store.initialize()
            store.append_observation(observation(source={'token':'SECRET','profile':'/SECRET','raw':{'password':'SECRET'},'content_revision':2}),'unsafe-source')
            data=handle(store,'GET','/api/v2/metrics',{},lambda:{},source_root=Path(temp),registry=registry)
            self.assertNotIn('SECRET',json.dumps(data)); self.assertEqual(data['observations'][0]['source'],{'content_revision':2})
    def test_preview_has_safe_transient_ids_without_raw_parts(self):
        from web_metrics import handle
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); source=root/'source'; parts=source/'common/analytics/snapshots/parts';parts.mkdir(parents=True)
            (parts/'youtube.json').write_text(json.dumps({'items':[{'id':'v1','views':0}]}))
            registry=Registry('r',{'personal':{},'dept':{}},{},{},{},{},{},{})
            data=handle(None,'GET','/api/v2/metrics/import-preview',{},lambda:{},source_root=source,registry=registry)
            self.assertGreater(len(data['observations']),0)
            self.assertTrue(all(row.get('id','').startswith('preview_') for row in data['observations']))
            self.assertNotIn('parts',data); self.assertNotIn(str(source),json.dumps(data))
            store=MetricsStore(root/'managed');store.initialize()
            body=dict(account_id='personal',observation_ids=[data['observations'][0]['id']],title='미리보기 거부',note='',request_key='preview-proposal')
            with self.assertRaises(StoreError):
                handle(store,'POST','/api/v2/metrics/proposals',{},lambda:body,source_root=source,registry=registry)
            self.assertEqual(store.list_proposals(),[])
