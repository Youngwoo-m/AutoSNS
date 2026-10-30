import unittest
from unittest.mock import Mock
from tests.operations.test_runtime_store import NOW
from common.operations.runtime_models import ExecutionPolicy

class WorkerTests(unittest.TestCase):
    def test_disabled_no_adapter_or_claim(self):
        from common.operations.worker import run_once
        store=Mock();adapter=Mock()
        self.assertIsNone(run_once(store,Mock(),{'x':adapter},ExecutionPolicy(),Mock(),NOW))
        store.list_runs.assert_not_called();adapter.submit.assert_not_called()
    def test_empty_factory(self):
        from common.publishers import build_adapters
        self.assertEqual(build_adapters(),{})

from tests.operations.test_publication_gate import GateFixture
from common.operations.runtime_models import SubmissionResult
from contextlib import contextmanager, closing
import sqlite3

class WorkerBoundaryTests(GateFixture):
    def observe_quota(self):
        from common.operations.quota import bucket_id, quota_window
        for req in self.registry.policies['p']['quota_requirements']:
            start,end=quota_window(req,NOW)
            self.store.observe_bucket(bucket_id(req['scope_kind'],req['scope_id'],req['metric'],start,end),5,0,NOW,end)
    def test_live_fake_adapter_without_transaction_and_unknown_no_resend(self):
        from common.operations.worker import run_once
        self.observe_quota();calls=[];store=self.store
        class FakeAdapter:
            def prepare(self,ctx,snapshot):return {'title':snapshot['title']}
            def submit(self,ctx,prepared,permit):
                with closing(sqlite3.connect(store.root/'operations.sqlite3',timeout=0)) as db:
                    db.execute('BEGIN IMMEDIATE');db.rollback()
                calls.append(permit.attempt_id)
                raise TimeoutError('fixture uncertain response')
        with self.assertRaisesRegex(Exception,'submission_uncertain'):run_once(store,self.registry,{'x':FakeAdapter()},self.policy,store.locks,NOW)
        self.assertEqual(store.get_delivery('d')['state'],'unknown')
        self.assertEqual(run_once(store,self.registry,{'x':FakeAdapter()},self.policy,store.locks,NOW),None)
        self.assertEqual(len(calls),1)
        self.assertTrue(all(b['reserved']==1 for b in store.quota_buckets()))
    def test_profile_wait_stop_submit_zero(self):
        from common.operations.worker import run_once
        self.observe_quota();real=self.store.locks;adapter=Mock()
        class WaitingLocks:
            paths=real.paths
            @contextmanager
            def hold(self,resources,**kwargs):
                if resources!=['control:publish-gate']:real.set_stop('fixture during wait')
                with real.hold(resources,**kwargs):yield
        with self.assertRaises(Exception):run_once(self.store,self.registry,{'x':adapter},self.policy,WaitingLocks(),NOW)
        adapter.submit.assert_not_called()
    def test_dry_shadow_zero_calls(self):
        from common.operations.worker import run_once
        for mode in ('dry','shadow'):
            store=Mock();store.list_runs.return_value=[{'id':'r','occurrence':{'mode':mode,'phase':'submit'}}];store.list_operations.return_value=[]
            adapter=Mock();self.assertIsNone(run_once(store,self.registry,{'x':adapter},self.policy,self.store.locks,NOW))
            adapter.submit.assert_not_called();adapter.prepare.assert_not_called();store.claim_run.assert_not_called()
    def test_success_submits_once(self):
        from common.operations.worker import run_once
        self.observe_quota();adapter=Mock();adapter.prepare.return_value={};adapter.submit.return_value=SubmissionResult('submitted',remote_id='fixture-id')
        self.assertEqual(run_once(self.store,self.registry,{'x':adapter},self.policy,self.store.locks,NOW),'d')
        self.assertEqual(self.store.get_delivery('d')['state'],'uploaded');self.assertEqual(adapter.submit.call_count,1)

# unittest가 imported base 자체를 중복 수집하지 않게 한다.
del GateFixture

class MultipleDeliveryTests(WorkerBoundaryTests):
    def test_second_delivery_same_live_occurrence_is_submitted(self):
        from dataclasses import replace
        from common.operations.worker import run_once
        import json
        self.observe_quota()
        second=dict(self.plan,id='d2',schedule_slot='slot2')
        with closing(sqlite3.connect(self.store.root/'operations.sqlite3')) as db:
            db.execute('INSERT INTO deliveries VALUES(?,?,?,?,?,?,?,?)',('d2',self.content['id'],1,'x','initial','slot2','second',json.dumps(second)));db.commit()
        ctx2=replace(self.ctx,schedule_slot='slot2')
        self.store.create_delivery('d2',self.run,ctx2);self.store.record_evidence('d2','target_observation',self.observed)
        self.store.record_publication_approval('d2',1,ctx2.context_hash,'second',ctx2.review_report_hashes)
        adapter=Mock();adapter.prepare.return_value={};adapter.submit.return_value=SubmissionResult('submitted',remote_id='fixture')
        self.assertEqual(run_once(self.store,self.registry,{'x':adapter},self.policy,self.store.locks,NOW),'d2')
        self.assertEqual(run_once(self.store,self.registry,{'x':adapter},self.policy,self.store.locks,NOW),'d')
        self.assertEqual(adapter.submit.call_count,2)
    def test_adapter_nonce_never_enters_result_or_error(self):
        from common.operations.worker import run_once
        self.observe_quota();seen=[]
        class FakeAdapter:
            def prepare(self,*args):return {}
            def submit(self,ctx,prepared,permit):
                seen.append(permit.nonce)
                return SubmissionResult('submitted',remote_id='fixture',evidence={'nested':[{'value':permit.nonce}]})
        run_once(self.store,self.registry,{'x':FakeAdapter()},self.policy,self.store.locks,NOW)
        import json
        self.assertNotIn(seen[0],json.dumps(self.store.events('d')))
