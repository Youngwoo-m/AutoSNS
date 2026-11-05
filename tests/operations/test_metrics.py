"""검증 게시 경계와 안전한 성과 기록 시험."""
import copy
from dataclasses import FrozenInstanceError
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from common.operations.metrics import (build_metrics_context, collect_delivery_metrics, record_metrics, build_metrics_snapshot)
from common.operations.metrics_models import MetricResult
from common.operations.metrics_store import MetricsStore
from common.operations.content_store import StoreError
from common.operations.models import Connection, Registry

NOW='2026-10-30T00:00:00+00:00'

def registry():
    return Registry('r',{'personal':{},'dept':{}},{},{},{
        'dept.youtube':Connection('dept.youtube','dept','youtube',target_id='channel'),
        'personal.naver':Connection('personal.naver','personal','naver_blog',target_id='safeworking'),
    },{},{},{})

class Runtime:
    def __init__(self):
        self.registry=registry()
        self.rows=[dict(id='d',state='verified',remote_id='video',context=dict(content_id='c',content_revision=2,manifest_hash='manifest',owner_account_id='personal',destination_account_id='dept',connection_id='dept.youtube',target_id='channel',credential_ref='SECRET',profile_ref='SECRET'))]
        self.productions=[]
    def get_delivery(self,id): return copy.deepcopy(next((d for d in self.rows if d['id']==id),None))
    def events(self,id): return [dict(kind='verification',evidence=dict(outcome='verified',checked_at=NOW,evidence=dict(remote_id='video',target_id='channel',destination_account_id='dept',visibility='public')))]
    def list_operations(self,account='all'):return copy.deepcopy(self.rows)
    def attempts(self,id):return [dict(reservation_id='reservation')]
    def get_reservation(self,id):return dict(production_ids=['production'])
    def list_productions(self):return copy.deepcopy(self.productions)

class MetricsFixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=MetricsStore(Path(self.tmp.name)/'managed');self.store.initialize();self.runtime=Runtime()
    def record(self,result,**kw):
        return record_metrics(self.store,'d',result,runtime_store=self.runtime,registry=self.runtime.registry,**kw)
    def result(self,**kw):
        return MetricResult(**dict(dict(status='ok',values={'views':0},observed_at=NOW,remote_id='video',target_id='channel',definition_id='youtube.views',basis='lifetime'),**kw))

class MetricsTests(MetricsFixture):
    def test_scheduled_or_unverified_never_calls_collector(self):
        collector=Mock()
        for state in ('scheduled','uploaded','published','needs_review'):
            self.runtime.rows[0]['state']=state
            with self.assertRaises(StoreError):
                ctx=build_metrics_context(self.runtime,'d',self.runtime.registry)
                collect_delivery_metrics(ctx,'video',collector)
        collector.assert_not_called()
        self.assertEqual([],self.store.list_observations())
    def test_verified_event_and_registry_target_are_required(self):
        self.runtime.events=lambda _:[]
        with self.assertRaises(StoreError):build_metrics_context(self.runtime,'d',self.runtime.registry)
        self.runtime=Runtime();self.runtime.rows[0]['context']['target_id']='elsewhere'
        with self.assertRaises(StoreError):build_metrics_context(self.runtime,'d',self.runtime.registry)
    def test_context_is_frozen_safe_and_bound_to_remote(self):
        ctx=build_metrics_context(self.runtime,'d',self.runtime.registry)
        with self.assertRaises(FrozenInstanceError):ctx.target_id='other'
        self.assertNotIn('SECRET',repr(ctx))
        collector=Mock()
        with self.assertRaises(StoreError):collect_delivery_metrics(ctx,'other',collector)
        collector.assert_not_called()
    def test_zero_error_and_unsupported_are_distinct(self):
        ctx=build_metrics_context(self.runtime,'d',self.runtime.registry)
        self.assertEqual('unsupported',collect_delivery_metrics(ctx,'video',None).status)
        self.assertEqual('error',collect_delivery_metrics(ctx,'video',lambda *_:1/0).status)
        zero=collect_delivery_metrics(ctx,'video',lambda *_:self.result())
        self.assertEqual({'views':0},zero.to_dict()['values'])
        for result in (zero,collect_delivery_metrics(ctx,'video',None),collect_delivery_metrics(ctx,'video',lambda *_:1/0)):
            self.record(result)
        rows=self.store.list_observations();self.assertEqual(['ok','unsupported','error'],[r['status'] for r in rows])
    def test_record_rechecks_remote_target_and_current_state(self):
        for result in (self.result(remote_id='other'),self.result(target_id='other')):
            with self.assertRaises(StoreError):self.record(result)
        self.runtime.rows[0]['state']='scheduled'
        with self.assertRaises(StoreError):self.record(self.result())
        self.assertEqual([],self.store.list_observations())
    def test_safe_provenance_and_idempotent_source_key(self):
        result=self.result(source={'access_token':'SECRET','raw_response':{'token':'SECRET'},'content_revision':999})
        first=self.record(result,observation_key='once');second=self.record(result,observation_key='once')
        self.assertEqual(first,second);self.assertEqual(1,len(self.store.list_observations()))
        self.assertNotIn('SECRET',str(first));self.assertEqual(2,first['source']['content_revision']);self.assertEqual('manifest',first['source']['manifest_hash'])
    def test_snapshot_related_accounts_and_legacy_separate(self):
        self.record(self.result())
        for account in ('personal','dept','all'):
            snap=build_metrics_snapshot(account,self.runtime.registry,self.store)
            self.assertEqual(1,len(snap['observations']));self.assertEqual(1,snap['summary']['verified_observations']);self.assertFalse(snap['collection_enabled'])
        support=build_metrics_snapshot('dept',self.runtime.registry,self.store)['support']
        self.assertTrue({'instagram','threads','x','tistory','facebook'} <= {r['platform'] for r in support})
    def test_get_does_not_create_managed_files_or_query_credentials(self):
        empty=MetricsStore(Path(self.tmp.name)/'absent')
        reg=registry()
        self.assertEqual([],build_metrics_snapshot('dept',reg,empty)['observations'])
        self.assertFalse(empty.root.exists())
        with self.assertRaises(StoreError):build_metrics_snapshot('unknown',reg,empty)

    def test_real_runtime_verified_evidence_is_read_without_mutation(self):
        from tests.operations import test_runtime_store as fixtures
        helper=fixtures.RuntimeStoreTests()
        helper.setUp()
        try:
            runtime,ctx,lease=helper.ready()
            delivery=runtime.get_delivery('d')
            attempt=runtime.create_attempt('d',delivery['version'],lease,ctx.context_hash,'approval',now=fixtures.NOW)
            permit=runtime.issue_permit(attempt['id'],lease,ctx.context_hash,'approval',fixtures.NOW)
            runtime.consume_permit(permit,lease,fixtures.NOW)
            runtime.finish_attempt(attempt['id'],'submitted',remote_id='real-video',now=fixtures.NOW)
            ev=dict(remote_id='real-video',target_id='t',destination_account_id='personal',visibility='public')
            runtime.record_evidence('d','verification',dict(outcome='verified',checked_at=NOW,evidence=ev))
            d=runtime.get_delivery('d');runtime.transition_delivery('d',d['version'],'published',evidence=ev)
            d=runtime.get_delivery('d');runtime.transition_delivery('d',d['version'],'verified',evidence=ev)
            reg=Registry('r',{'personal':{},'dept':{}},{},{},{'x':Connection('x','personal','youtube',target_id='t')},{},{},{})
            before={p.name:p.read_bytes() for p in runtime.root.iterdir() if p.is_file()}
            fixed=build_metrics_context(runtime,'d',reg)
            self.assertEqual('real-video',fixed.remote_id)
            self.assertEqual(NOW,fixed.verified_at)
            self.assertEqual(before,{p.name:p.read_bytes() for p in runtime.root.iterdir() if p.is_file()})
        finally:
            helper.doCleanups()

    def test_collection_returns_only_safe_source(self):
        ctx=build_metrics_context(self.runtime,'d',self.runtime.registry)
        result=collect_delivery_metrics(ctx,'video',lambda *_:self.result(source={'access_token':'SECRET','raw_response':{'secret':'SECRET'}}))
        self.assertNotIn('SECRET',str(result.to_dict()))
