import multiprocessing
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from common.operations.models import Connection
from common.operations.runtime_models import ExecutionPolicy
from common.operations.runtime_store import RuntimeStore
from common.operations.content_store import StoreError
from tests.operations.test_runtime_store import NOW
from common.operations.dispatch import submit_trigger, claim_next_run, heartbeat


def registry():
    return SimpleNamespace(jobs={'j':{'execution_owner':'managed','schedule_owner':'console','enabled':True,'owner_account_id':'personal','connection_id':'x','policy_revision':'p'}}, policies={'p':{'subscription_only':True}},connections={'x':Connection('x','personal','youtube',target_id='t',enabled=True)})

def request(**changes):
    return dict(dict(job_id='j',scheduled_at_utc=NOW.isoformat(),phase='submit',source='console',request_kind='new_publication',mode='live'),**changes)

def claim_process(root,q):
    s=RuntimeStore(root);s.initialize()
    lease=claim_next_run(s,'worker',NOW,60)
    q.put(lease.run_id if lease else None)

class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=RuntimeStore(Path(self.temp.name)/'managed');self.store.initialize()
        self.registry=registry();self.policy=ExecutionPolicy(True,('x',),'cutover',{'subscription_only':True})
    def submit(self,**changes):return submit_trigger(self.store,request(**changes),self.registry,self.policy)
    def test_same_occurrence_idempotent_and_phase_independent(self):
        one=self.submit();self.assertEqual(self.store.get_run(one['id'])['occurrence']['job_id'],'j')
        self.assertEqual(self.store.list_runs()[0]['occurrence']['phase'],'submit')
        self.assertEqual(one['id'],self.submit(scheduled_at_utc='2026-10-30T09:00:00+09:00')['id'])
        self.assertNotEqual(one['id'],self.submit(phase='prepare')['id'])
        self.assertNotEqual(one['id'],self.submit(phase='verify')['id'])
    def test_shadow_writes_zero(self):
        before=(self.store.root/'operations.sqlite3').read_bytes()
        self.assertEqual(self.submit(mode='shadow')['state'],'shadow')
        self.assertEqual(before,(self.store.root/'operations.sqlite3').read_bytes())
    def test_live_disabled_legacy_and_policy_rejected(self):
        for policy in (ExecutionPolicy(),ExecutionPolicy(True,(),'c'),ExecutionPolicy(True,('x',),'c',{'subscription_only':True})):
            if policy.enabled and policy.allowed_connection_ids:self.registry.policies['p']['subscription_only']=False
            with self.assertRaises(StoreError):submit_trigger(self.store,request(),self.registry,policy)
        self.registry.jobs['j']['execution_owner']='legacy'
        with self.assertRaises(StoreError):self.submit(mode='dry')
        self.assertEqual(self.store.list_runs(),[])
    def test_request_override_and_unknown_resume_rejected(self):
        with self.assertRaises(StoreError):self.submit(connection_id='evil')
        with self.assertRaises(StoreError):self.submit(request_kind='resume')
        one=self.submit();self.assertEqual(one['id'],self.submit(request_kind='resume')['id'])
    def test_claim_stale_heartbeat_and_no_expired_reassignment(self):
        self.submit();lease=claim_next_run(self.store,'w',NOW,10)
        self.assertIsNone(claim_next_run(self.store,'w2',NOW,10))
        self.assertTrue(heartbeat(self.store,lease,NOW+timedelta(seconds=1)))
        self.assertTrue(heartbeat(self.store,lease,NOW+timedelta(seconds=11)))
        self.assertTrue(heartbeat(self.store,lease,NOW+timedelta(seconds=65)))
        self.assertFalse(heartbeat(self.store,lease,NOW+timedelta(seconds=126)))
        from common.operations.runtime_models import RunLease
        stale=RunLease(lease.run_id,lease.worker_id,lease.generation+1,NOW+timedelta(days=1))
        self.assertFalse(heartbeat(self.store,stale,NOW+timedelta(seconds=66)))
        self.assertIsNone(claim_next_run(self.store,'w2',NOW+timedelta(days=1),10))
        self.assertEqual(set(self.store.get_run(lease.run_id)['process_identity']),{'host_id','pid','started_at'})
    def test_two_processes_claim_once(self):
        self.submit();mp=multiprocessing.get_context('spawn');q=mp.Queue()
        procs=[mp.Process(target=claim_process,args=(str(self.store.root),q)) for _ in range(2)]
        for p in procs:p.start()
        for p in procs:p.join(15);self.assertEqual(p.exitcode,0)
        self.assertEqual(sum(q.get(timeout=2) is not None for _ in procs),1)

    def test_legacy_schedule_owner_and_unknown_source_rejected(self):
        self.registry.jobs['j']['schedule_owner']='legacy'
        with self.assertRaises(StoreError):self.submit()
        self.registry.jobs['j']['schedule_owner']='console'
        with self.assertRaises(StoreError):self.submit(source='manual')
        self.assertEqual(self.store.list_runs(),[])
    def test_future_queued_is_skipped_and_due_behind_it_claimed(self):
        future=self.submit(scheduled_at_utc=(NOW+timedelta(days=1)).isoformat())
        self.assertIsNone(claim_next_run(self.store,'w',NOW,60))
        due=self.submit()
        lease=claim_next_run(self.store,'w',NOW,60)
        self.assertEqual(lease.run_id,due['id'])
        self.assertEqual(self.store.get_run(future['id'])['state'],'queued')
