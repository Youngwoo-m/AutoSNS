import unittest
from unittest.mock import Mock
from tests.operations.test_runtime_store import NOW
from common.operations.runtime_models import ExecutionPolicy

class WorkerTests(unittest.TestCase):
    def test_disabled_no_adapter_or_claim(self):
        from common.operations.worker import run_once
        store=Mock();adapter=Mock()
        self.assertIsNone(run_once(store,Mock(),{'x':adapter},ExecutionPolicy(),Mock(),NOW))
        store.list_runs.assert_not_called();adapter.submit.assert_not_called();adapter.inspect_target.assert_not_called()
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
        self.observe_quota();calls=[];store=self.store;observed=self.observed
        class FakeAdapter:
            def inspect_target(self,ctx):return observed
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
            adapter.submit.assert_not_called();adapter.prepare.assert_not_called();adapter.inspect_target.assert_not_called();store.claim_run.assert_not_called()
    def test_success_submits_once(self):
        from common.operations.worker import run_once
        self.observe_quota();adapter=Mock();adapter.inspect_target.return_value=self.observed;adapter.prepare.return_value={};adapter.submit.return_value=SubmissionResult('submitted',remote_id='fixture-id')
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
        adapter=Mock();adapter.inspect_target.return_value=self.observed;adapter.prepare.return_value={};adapter.submit.return_value=SubmissionResult('submitted',remote_id='fixture')
        self.assertEqual(run_once(self.store,self.registry,{'x':adapter},self.policy,self.store.locks,NOW),'d2')
        self.assertEqual(run_once(self.store,self.registry,{'x':adapter},self.policy,self.store.locks,NOW),'d')
        self.assertEqual(adapter.submit.call_count,2)
    def test_adapter_nonce_never_enters_result_or_error(self):
        from common.operations.worker import run_once
        self.observe_quota();seen=[];observed=self.observed
        class FakeAdapter:
            def inspect_target(self,ctx):return observed
            def prepare(self,*args):return {}
            def submit(self,ctx,prepared,permit):
                seen.append(permit.nonce)
                return SubmissionResult('submitted',remote_id='fixture',evidence={'nested':[{'value':permit.nonce}]})
        run_once(self.store,self.registry,{'x':FakeAdapter()},self.policy,self.store.locks,NOW)
        import json
        self.assertNotIn(seen[0],json.dumps(self.store.events('d')))

class ApprovalQuotaTests(WorkerBoundaryTests):
    def assert_target_api_reserved(self,amount):
        from common.operations.quota import bucket_id,quota_window
        for req in self.registry.policies['p']['quota_requirements']:
            if req['scope_kind']=='owner':continue
            start,end=quota_window(req,NOW);key=bucket_id(req['scope_kind'],req['scope_id'],req['metric'],start,end)
            self.assertEqual(next(b for b in self.store.quota_buckets() if b['id']==key)['reserved'],amount)
    def revoke(self):
        self.store.record_publication_approval('d',self.store.get_delivery('d')['version'],self.ctx.context_hash,'revoked',self.ctx.review_report_hashes,decision='revoked')
    def test_revoked_approval_three_calls_reserve_nothing(self):
        from common.operations.worker import run_once
        self.observe_quota();self.revoke();adapter=Mock()
        for _ in range(3):
            with self.assertRaises(Exception):run_once(self.store,self.registry,{'x':adapter},self.policy,self.store.locks,NOW)
        adapter.submit.assert_not_called();self.assert_target_api_reserved(0);self.assertEqual(self.store.attempts('d'),[])
    def test_revoke_after_reserve_cleans_target_api_and_does_not_repeat(self):
        from common.operations.worker import run_once
        from common.operations.quota import reserve_quota
        from unittest.mock import patch
        self.observe_quota();adapter=Mock();adapter.inspect_target.return_value=self.observed;adapter.prepare.return_value={}
        def competing_revoke(*args,**kwargs):
            reservation=reserve_quota(*args,**kwargs);self.revoke();return reservation
        with patch('common.operations.worker.reserve_quota',side_effect=competing_revoke):
            with self.assertRaises(Exception):run_once(self.store,self.registry,{'x':adapter},self.policy,self.store.locks,NOW)
        for _ in range(3):
            try:run_once(self.store,self.registry,{'x':adapter},self.policy,self.store.locks,NOW)
            except Exception:pass
        adapter.submit.assert_not_called();self.assert_target_api_reserved(0)
    def test_cleanup_db_failure_reuses_one_logical_reservation(self):
        from common.operations.worker import run_once
        from unittest.mock import patch
        self.observe_quota();adapter=Mock();adapter.inspect_target.return_value=self.observed;adapter.prepare.return_value={}
        # Approval remains valid; a transient final-gate failure and unavailable
        # cleanup must not allocate three independent target/API holds.
        with patch('common.operations.worker.authorize_submission',side_effect=RuntimeError('fixture gate failure')):
            with patch.object(self.store,'settle_reservation',side_effect=RuntimeError('fixture db unavailable')):
                for _ in range(3):
                    with self.assertRaises(Exception):run_once(self.store,self.registry,{'x':adapter},self.policy,self.store.locks,NOW)
        adapter.submit.assert_not_called();self.assert_target_api_reserved(1)
        adapter.submit.return_value=SubmissionResult('submitted',remote_id='fixture')
        self.assertEqual(run_once(self.store,self.registry,{'x':adapter},self.policy,self.store.locks,NOW),'d')
        self.assertEqual(adapter.submit.call_count,1);self.assert_target_api_reserved(1)
    def test_partial_retry_only_selected_queued_delivery_runs(self):
        from dataclasses import replace
        import json
        from common.operations.worker import run_once
        self.observe_quota()
        # Fixture is the S5 result: A verified, B explicitly requeued, C retry_wait.
        with closing(sqlite3.connect(self.store.root/'operations.sqlite3')) as db:
            db.execute("UPDATE runtime_deliveries SET state='verified' WHERE id='d'");db.commit()
        for identity,slot,state in [('B','slotB','queued'),('C','slotC','retry_wait')]:
            plan=dict(self.plan,id=identity,schedule_slot=slot)
            with closing(sqlite3.connect(self.store.root/'operations.sqlite3')) as db:
                db.execute('INSERT INTO deliveries VALUES(?,?,?,?,?,?,?,?)',(identity,self.content['id'],1,'x','initial',slot,identity,json.dumps(plan)));db.commit()
            ctx=replace(self.ctx,schedule_slot=slot)
            self.store.create_delivery(identity,self.run,ctx);self.store.record_evidence(identity,'target_observation',self.observed)
            self.store.record_publication_approval(identity,1,ctx.context_hash,identity,ctx.review_report_hashes)
            if state=='retry_wait':
                with closing(sqlite3.connect(self.store.root/'operations.sqlite3')) as db:
                    db.execute("UPDATE runtime_deliveries SET state='retry_wait' WHERE id=?",(identity,));db.commit()
        adapter=Mock();adapter.inspect_target.return_value=self.observed;adapter.prepare.return_value={};adapter.submit.return_value=SubmissionResult('submitted',remote_id='selected-B')
        self.assertEqual(run_once(self.store,self.registry,{'x':adapter},self.policy,self.store.locks,NOW),'B')
        self.assertIsNone(run_once(self.store,self.registry,{'x':adapter},self.policy,self.store.locks,NOW))
        self.assertEqual(adapter.submit.call_count,1);self.assertEqual(self.store.attempts('C'),[])
        self.assertEqual(self.store.get_delivery('d')['state'],'verified');self.assertEqual(self.store.get_delivery('C')['state'],'retry_wait')
    def test_reservation_identity_separates_new_runtime_occurrences(self):
        from dataclasses import replace
        import json
        from datetime import timedelta
        from common.operations.worker import run_once
        self.observe_quota()
        run2=self.store.submit_occurrence(dict(job_id='j',scheduled_at_utc=(NOW+timedelta(minutes=1)).isoformat(),phase='submit',source='console',request_kind='new_publication',mode='live'))['id']
        plan2=dict(self.plan,id='d2',schedule_slot='new-run-slot')
        with closing(sqlite3.connect(self.store.root/'operations.sqlite3')) as db:
            db.execute('INSERT INTO deliveries VALUES(?,?,?,?,?,?,?,?)',('d2',self.content['id'],1,'x','initial','new-run-slot','new',json.dumps(plan2)));db.commit()
        ctx2=replace(self.ctx,run_id=run2,schedule_slot='new-run-slot')
        self.store.create_delivery('d2',run2,ctx2);self.store.record_evidence('d2','target_observation',self.observed)
        self.store.record_publication_approval('d2',1,ctx2.context_hash,'new',ctx2.review_report_hashes)
        adapter=Mock();adapter.inspect_target.return_value=self.observed;adapter.prepare.return_value={};adapter.submit.return_value=SubmissionResult('submitted',remote_id='fixture')
        self.assertEqual(run_once(self.store,self.registry,{'x':adapter},self.policy,self.store.locks,NOW),'d')
        self.assertIsNone(run_once(self.store,self.registry,{'x':adapter},self.policy,self.store.locks,NOW))
        self.assertEqual(run_once(self.store,self.registry,{'x':adapter},self.policy,self.store.locks,NOW+timedelta(minutes=1)),'d2')
        first=self.store.attempts('d')[0]['reservation_id'];second=self.store.attempts('d2')[0]['reservation_id']
        self.assertNotEqual(first,second)
        self.assertEqual(self.store.get_reservation(first)['delivery_id'],'d');self.assertEqual(self.store.get_reservation(second)['delivery_id'],'d2')
        self.assert_target_api_reserved(2)
