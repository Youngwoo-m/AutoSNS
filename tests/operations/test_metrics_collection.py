"""검증된 게시 대상만 명시 수집하며 잠금 안에서 신원을 재검증한다."""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from common.operations.content_store import ContentStore,StoreError
from common.operations.metrics_collection import MetricsCollectionService
from common.operations.metrics_models import MetricResult
from common.operations.metrics_store import MetricsStore
from tests.operations import test_metrics as fixture

class MetricsCollectionTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)/'managed'
        self.store=MetricsStore(self.root);self.runtime=fixture.Runtime();self.runtime.root=self.root;self.calls=[]
        @contextmanager
        def lock(ctx):
            self.calls.append(('lock',ctx.delivery_id));yield;self.calls.append(('unlock',ctx.delivery_id))
        self.lock=lock
    def collector(self,ctx,remote_id):
        self.calls.append(('collect',remote_id))
        return MetricResult('ok',{'views':3},fixture.NOW,remote_id,ctx.target_id,'youtube.video_statistics_v1',basis='lifetime')
    def service(self,**changes):
        args=dict(runtime_store=self.runtime,metrics_store=self.store,registry=self.runtime.registry,collectors={'dept.youtube':self.collector},lock_scope=self.lock,enabled=True);args.update(changes)
        return MetricsCollectionService(**args)
    def test_constructor_targets_and_disabled_collection_are_inert(self):
        service=self.service(enabled=False)
        self.assertFalse(self.root.exists());self.assertEqual(self.calls,[])
        rows=service.targets('dept');self.assertEqual(len(rows),1)
        self.assertEqual(rows[0],dict(delivery_id='d',content_id='c',content_revision=2,owner_account_id='personal',destination_account_id='dept',platform='youtube',connection_id='dept.youtube',target_id='channel',remote_id='video',verified_at=fixture.NOW,title='c'))
        self.assertEqual(service.targets('personal'),[]);self.assertEqual(self.calls,[]);self.assertFalse(self.root.exists())
        with self.assertRaises(StoreError) as caught:service.collect('d')
        self.assertEqual(caught.exception.code,'collection_disabled')
    def test_collection_locks_then_appends_and_keeps_runtime_unchanged(self):
        self.store.initialize();before=self.runtime.get_delivery('d');result=self.service().collect('d')
        self.assertEqual(result['values'],{'views':3});self.assertEqual(result['source_kind'],'verified_delivery')
        self.assertEqual(self.calls,[('lock','d'),('collect','video'),('unlock','d')]);self.assertEqual(self.runtime.get_delivery('d'),before)
        self.assertEqual(self.store.list_observations(),[result]);self.assertEqual(result['source']['content_revision'],2)
    def test_unverified_unknown_or_unregistered_cannot_call_collector(self):
        self.store.initialize();service=self.service()
        for state in ('uploaded','scheduled','published','unknown'):
            self.runtime.rows[0]['state']=state;self.assertEqual(service.targets(),[])
            with self.assertRaises(StoreError):service.collect('d')
        self.runtime.rows[0]['state']='verified'
        self.assertEqual(self.service(collectors={}).targets(),[])
        with self.assertRaises(StoreError):self.service(collectors={}).collect('d')
        with self.assertRaises(StoreError):service.collect('missing')
        self.assertEqual(self.calls,[]);self.assertEqual(self.store.list_observations(),[])
    def test_lock_boundary_identity_change_blocks_before_collector(self):
        self.store.initialize()
        @contextmanager
        def changed(ctx):
            self.runtime.rows[0]['context']['content_revision']=3;yield
        with self.assertRaises(StoreError):self.service(lock_scope=changed).collect('d')
        self.assertEqual(self.calls,[]);self.assertEqual(self.store.list_observations(),[])
    def test_collector_identity_mismatch_or_midcollection_change_never_appends(self):
        self.store.initialize()
        def wrong(ctx,remote):return MetricResult('ok',{'views':4},fixture.NOW,'other',ctx.target_id,'test',basis='lifetime')
        with self.assertRaises(StoreError):self.service(collectors={'dept.youtube':wrong}).collect('d')
        def changed(ctx,remote):
            self.runtime.rows[0]['context']['manifest_hash']='changed';return self.collector(ctx,remote)
        with self.assertRaises(StoreError):self.service(collectors={'dept.youtube':changed}).collect('d')
        self.assertEqual(self.store.list_observations(),[])
    def test_collector_exception_records_safe_error_without_response_secret(self):
        self.store.initialize()
        def error(ctx,remote):raise RuntimeError('PRIVATE_TOKEN_VALUE')
        result=self.service(collectors={'dept.youtube':error}).collect('d')
        self.assertEqual(result['status'],'error');self.assertEqual(result['values'],{})
        self.assertNotIn('PRIVATE_TOKEN_VALUE',str(result));self.assertEqual(len(self.store.list_observations()),1)
    def test_foreign_root_unknown_or_mutable_registration_rejected(self):
        other=MetricsStore(self.root.parent/'other')
        for changes in ({'metrics_store':other},{'collectors':{'missing':self.collector}},{'collectors':{'dept.youtube':None}},{'lock_scope':None},{'enabled':1}):
            with self.assertRaises(StoreError):self.service(**changes)
        collectors={'dept.youtube':self.collector};service=self.service(collectors=collectors);collectors.clear()
        self.assertIn('dept.youtube',service.collectors)
        with self.assertRaises(TypeError):service.collectors['dept.youtube']=None
        self.assertFalse(self.root.exists())
    def test_title_only_comes_from_pinned_trusted_content_snapshot(self):
        content=ContentStore(self.root);content.initialize();item=content.create('personal',dict(title='신뢰된 제목',kind='article'))
        self.runtime.rows[0]['context'].update(content_id=item['id'],content_revision=item['revision'],manifest_hash=item['manifest_hash'])
        self.runtime.content_store=content;self.assertEqual(self.service().targets()[0]['title'],'신뢰된 제목')
        self.runtime.content_store=SimpleNamespace(get=lambda *a:dict(title='가짜 제목'))
        self.assertEqual(self.service().targets()[0]['title'],item['id'])

    def test_real_runtime_store_verified_delivery_collects_without_mutating_operation_ledger(self):
        from tests.operations import test_runtime_store as source
        from common.operations.models import Registry,Connection
        helper=source.RuntimeStoreTests();helper.setUp()
        try:
            runtime,ctx,lease=helper.ready()
            attempt=runtime.create_attempt('d',runtime.get_delivery('d')['version'],lease,ctx.context_hash,'approval',now=source.NOW)
            permit=runtime.issue_permit(attempt['id'],lease,ctx.context_hash,'approval',source.NOW)
            runtime.consume_permit(permit,lease,source.NOW)
            runtime.finish_attempt(attempt['id'],'submitted',remote_id='actual-video',now=source.NOW)
            proof=dict(remote_id='actual-video',target_id='t',destination_account_id='personal',visibility='public')
            runtime.record_evidence('d','verification',dict(outcome='verified',checked_at=fixture.NOW,evidence=proof))
            runtime.transition_delivery('d',runtime.get_delivery('d')['version'],'published',evidence=proof)
            runtime.transition_delivery('d',runtime.get_delivery('d')['version'],'verified',evidence=proof)
            registry=Registry('r',{'personal':{},'dept':{}},{},{},{'x':Connection('x','personal','youtube',target_id='t')},{},{},{})
            metrics=MetricsStore(runtime.root);metrics.initialize()
            def collector(context,remote):return MetricResult('ok',{'views':0},fixture.NOW,remote,context.target_id,'test',basis='lifetime')
            service=MetricsCollectionService(runtime,metrics,registry,{'x':collector},self.lock,enabled=True)
            before=(runtime.root/'operations.sqlite3').read_bytes()
            self.assertEqual(service.targets('personal')[0]['remote_id'],'actual-video')
            saved=service.collect('d');self.assertEqual(saved['values'],{'views':0})
            self.assertEqual(before,(runtime.root/'operations.sqlite3').read_bytes())
        finally:helper.doCleanups()
