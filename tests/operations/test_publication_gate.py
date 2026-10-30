import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from tests.operations.test_runtime_store import NOW, context
from common.operations.runtime_models import ExecutionPolicy

class GateTests(unittest.TestCase):
    def test_plan_context_rejected(self):
        from common.operations.publication_gate import authorize_submission
        with self.assertRaises(Exception):
            authorize_submission(Mock(),SimpleNamespace(scope='plan'),{}, {},None,None,NOW)
    def test_disabled_builder_never_reads_store(self):
        from common.operations.publication_gate import build_publication_context
        store=Mock()
        with self.assertRaisesRegex(Exception,'execution_disabled'):
            build_publication_context(store,'d',{}, {},ExecutionPolicy(),NOW)
        store.get_plan_delivery.assert_not_called()
    def test_report_requires_server_provenance_and_independence(self):
        from common.operations.publication_gate import validate_reviews, report_hash
        producer={'principal_id':'author','execution_id':'generation'}
        r=dict(role='source',reviewer_id='reviewer',execution_id='review',content_id='c',content_revision=1,manifest_hash='m',verdict='pass',checked_at=NOW.isoformat())
        r['report_hash']=report_hash(r)
        policy={'review_authorities':{'reviewer':['source']}}
        evidence={'producer':producer,'reports':[r]}
        persisted=[{'kind':'production_provenance','evidence':producer},{'kind':'independent_review','evidence':r}]
        self.assertEqual(validate_reviews(evidence,policy,context(),persisted,NOW),(r['report_hash'],))
        for events in ([],persisted[:1]):
            with self.assertRaises(Exception):validate_reviews(evidence,policy,context(),events,NOW)
        r['execution_id']='generation';r['report_hash']=report_hash(r)
        with self.assertRaises(Exception):validate_reviews(evidence,policy,context(),persisted,NOW)

# 실제 SQLite/ContentStore와 source-root fixture를 사용하는 관문 시험.
import tempfile, sqlite3, json
from contextlib import closing
from pathlib import Path
from common.operations.content_store import ContentStore
from common.operations.runtime_store import RuntimeStore
from common.operations.models import Registry, Connection
from common.operations.publication_gate import report_hash
from common.shared.axlock import AxLock, LockPaths

class GateFixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);self.root=root
        content=ContentStore(root/'managed');content.initialize()
        self.content=content.create('personal',{'title':'fixture','kind':'article','original':'text'})
        self.policy=ExecutionPolicy(True,('x',),'fixture-cutover',{'subscription_only':True})
        requirements=[{'scope_kind':k,'scope_id':v,'metric':'posts','window_kind':'day','timezone':'UTC','limit':5,'amount':1} for k,v in [('target','t'),('api','fixture-api'),('owner','personal')]]
        self.registry=Registry('r',{'personal':{}},{},{'p':{'account_id':'personal','lock_resource':'profile:tistory'}},{'x':Connection('x','personal','tistory',target_id='t',profile_ref='p',enabled=True,expected_login_subject='subject')},{'j':{'enabled':True,'execution_owner':'managed','schedule_owner':'console','owner_account_id':'personal','connection_id':'x','policy_revision':'p'}},{'p':{'subscription_only':True,'review_authorities':{'reviewer':['source']},'quota_requirements':requirements}}, {})
        self.store=RuntimeStore(root/'managed',self.registry,content);self.store.initialize()
        self.store.execution_policy=self.policy;self.store.locks=AxLock(LockPaths.from_root(root/'source'))
        from tests.operations.production_fixture import produce_reviewed_fixture
        made=produce_reviewed_fixture(content,self.store,self.registry,self.content,NOW)
        self.registry=made['registry'];self.content=made['snapshot']
        self.producer=made['producer'];self.review=made['review']
        self.production_store=made['production_store'];self.production_unit_id=made['unit_id']
        self.plan=dict(id='d',content_id=self.content['id'],revision=self.content['revision'],manifest_hash=self.content['manifest_hash'],owner_account_id='personal',destination_account_id='personal',connection_id='x',publication_purpose='initial',schedule_slot='slot',options={},schedule_condition={'kind':'fixed','at':NOW.isoformat()},status='ready',context={'scope':'plan'},run_id='plan-run')
        with closing(sqlite3.connect(root/'managed'/'operations.sqlite3')) as db:
            db.execute('INSERT INTO deliveries VALUES(?,?,?,?,?,?,?,?)',('d',self.content['id'],self.content['revision'],'x','initial','slot','planhash',json.dumps(self.plan)))
            db.commit()
        self.run=self.store.submit_occurrence(dict(job_id='j',scheduled_at_utc=NOW.isoformat(),phase='submit',source='console',request_kind='new_publication',mode='live'))['id']
        self.observed=dict(platform='tistory',target_id='t',authenticated=True,login_subject='subject',verification_method='fixture',checked_at=NOW.isoformat(),expires_at=(NOW+timedelta(hours=1)).isoformat())
        self.ctx=self.build()
        self.store.create_delivery('d',self.run,self.ctx)
        self.store.record_evidence('d','target_observation',self.observed)
        self.store.record_publication_approval('d',1,self.ctx.context_hash,'publication-approval',self.ctx.review_report_hashes)
    def build(self,**kwargs):
        from common.operations.publication_gate import build_publication_context
        return build_publication_context(self.store,'d',kwargs.get('observed',self.observed),kwargs.get('review',self.review),kwargs.get('policy',self.policy),kwargs.get('now',NOW),run_id=self.run)
    def ready(self):
        lease=self.store.claim_run(self.run,'worker',{'host_id':'fixture','pid':1,'started_at':NOW.isoformat()},NOW)
        for b in ('a','b','c'):self.store.observe_bucket(b,5,0,NOW,NOW+timedelta(hours=1))
        reservation=self.store.reserve_quota('d',[{'bucket_id':b,'amount':1} for b in ('a','b','c')],NOW)
        from common.operations.publication_gate import authorize_submission
        permit=authorize_submission(self.store,self.ctx,self.content,self.store.get_publication_approval('d'),lease,reservation['id'],NOW)
        return permit
    def test_builder_changed_target_auth_review_policy_and_asset_rejected(self):
        for obs in (dict(self.observed,target_id='other'),dict(self.observed,expires_at=NOW.isoformat())):
            with self.assertRaises(Exception):self.build(observed=obs)
        with self.assertRaises(Exception):self.build(review={'producer':self.producer,'reports':[]})
        with self.assertRaises(Exception):self.build(policy=ExecutionPolicy(True,('x',),'c',{'subscription_only':False}))
        with self.assertRaises(Exception):self.build(now=NOW+timedelta(minutes=6))
    def test_permit_one_use_and_stop_between_authorize_consume(self):
        from common.operations.publication_gate import consume_permit
        permit=self.ready();self.assertNotIn(permit.nonce,repr(permit));self.assertNotIn(permit.nonce,json.dumps(permit.to_dict()))
        self.store.locks.set_stop('fixture')
        with self.assertRaises(Exception):consume_permit(self.store,permit,self.ctx,NOW)
        self.assertFalse(self.store.get_attempt(permit.attempt_id)['request_started'])
        state=self.store.locks.status()['control'];self.store.locks.clear_stop(state['version'])
        consume_permit(self.store,permit,self.ctx,NOW)
        with self.assertRaises(Exception):consume_permit(self.store,permit,self.ctx,NOW)
        self.assertTrue(self.store.get_attempt(permit.attempt_id)['request_started'])
    def test_plan_approval_rejected(self):
        from common.operations.publication_gate import authorize_submission
        with self.assertRaisesRegex(Exception,'publication_approval_required'):
            authorize_submission(self.store,self.ctx,self.content,{'scope':'plan','decision':'approved'},None,'r',NOW)
    def test_plan_read_preserves_bytes(self):
        path=self.root/'managed'/'operations.sqlite3';before=path.read_bytes()
        self.assertEqual(self.store.get_plan_delivery('d'),self.plan)
        self.assertIsNone(self.store.get_plan_delivery('missing'));self.assertEqual(before,path.read_bytes())
    def test_asset_bytes_are_rehashed(self):
        from common.operations.publication_gate import _snapshot
        snapshot=dict(self.content,assets=[{'id':'asset','size':4,'sha256':'0'*64}])
        fake=Mock();fake.content_store.get.return_value=snapshot;fake.content_store.read_asset.return_value=(snapshot['assets'][0],b'evil')
        with self.assertRaisesRegex(Exception,'asset_changed'):_snapshot(fake,snapshot['id'],snapshot['revision'],snapshot['manifest_hash'])
    def test_calc_review_required_by_policy(self):
        from common.operations.publication_gate import validate_reviews
        policy=dict(self.registry.policies['p'],require_calc_review=True)
        with self.assertRaisesRegex(Exception,'independent_review_required'):
            validate_reviews(self.review,policy,self.ctx,[{'kind':r['kind'],'evidence':r['report']} for r in self.store.read_content_evidence(self.ctx.content_id,self.ctx.content_revision,self.ctx.manifest_hash)],NOW)
    def test_two_process_stop_before_consume(self):
        import multiprocessing
        from common.operations.publication_gate import consume_permit
        permit=self.ready();mp=multiprocessing.get_context('fork')
        process=mp.Process(target=self.store.locks.set_stop,args=('fixture other process',));process.start();process.join(10)
        self.assertEqual(process.exitcode,0)
        with self.assertRaises(Exception):consume_permit(self.store,permit,self.ctx,NOW)
        self.assertFalse(self.store.get_attempt(permit.attempt_id)['request_started'])
    def test_two_process_consume_before_stop_keeps_result_resolution(self):
        import multiprocessing
        from common.operations.publication_gate import consume_permit
        permit=self.ready();mp=multiprocessing.get_context('fork')
        process=mp.Process(target=consume_permit,args=(self.store,permit,self.ctx,NOW));process.start();process.join(10)
        self.assertEqual(process.exitcode,0);self.store.locks.set_stop('fixture after consume')
        self.store.finish_attempt(permit.attempt_id,'unknown',evidence={'reason':'fixture'},now=NOW)
        self.assertEqual(self.store.get_delivery('d')['state'],'unknown')
    def test_prepare_snapshot_carries_verified_asset_bytes(self):
        import hashlib
        from common.operations.publication_gate import _snapshot
        asset={'id':'asset','size':4,'sha256':hashlib.sha256(b'data').hexdigest()}
        fake=Mock();fake.content_store.get.return_value=dict(self.content,assets=[asset]);fake.content_store.read_asset.return_value=(asset,b'data')
        snapshot=_snapshot(fake,self.content['id'],self.content['revision'],self.content['manifest_hash'])
        self.assertEqual(snapshot['asset_bytes'],{'asset':b'data'})
    def test_content_evidence_append_only_binding_and_readonly(self):
        rows=self.store.read_content_evidence(self.content['id'],self.content['revision'],self.content['manifest_hash'])
        self.assertEqual(len(rows),2)
        self.assertEqual(self.store.read_content_evidence(self.content['id'],self.content['revision'],'wrong'),[])
        with self.assertRaises(Exception):self.store.record_content_evidence(self.content['id'],self.content['revision'],'wrong','production_provenance',report_hash(self.producer),self.producer,now=NOW)
        with self.assertRaises(Exception):self.store.record_content_evidence(self.content['id'],self.content['revision'],self.content['manifest_hash'],'production_provenance','wrong',self.producer,now=NOW)
        path=self.store.root/'operations.sqlite3';before=path.read_bytes()
        self.store.read_content_evidence(self.content['id'],self.content['revision'],self.content['manifest_hash']);self.assertEqual(path.read_bytes(),before)

class GateClockTests(GateFixture):
    def advancing_gate(self,seconds):
        from contextlib import contextmanager
        real=self.store.locks;elapsed=[0.0]
        class AdvancingLocks:
            paths=real.paths
            @contextmanager
            def hold(self,*args,**kwargs):
                with real.hold(*args,**kwargs):
                    elapsed[0]+=seconds
                    yield
        self.store.locks=AdvancingLocks()
        return elapsed
    def test_consume_wait_expires_permit(self):
        from common.operations.publication_gate import consume_permit
        from unittest.mock import patch
        permit=self.ready();elapsed=self.advancing_gate(2)
        with patch('time.monotonic',side_effect=lambda:elapsed[0]):
            with self.assertRaises(Exception):consume_permit(self.store,permit,self.ctx,NOW+timedelta(seconds=29))
        self.assertFalse(self.store.get_attempt(permit.attempt_id)['request_started'])
    def test_consume_wait_expires_auth(self):
        from common.operations.publication_gate import consume_permit
        from unittest.mock import patch
        permit=self.ready();elapsed=self.advancing_gate(3601)
        with patch('time.monotonic',side_effect=lambda:elapsed[0]):
            with self.assertRaises(Exception):consume_permit(self.store,permit,self.ctx,NOW)
        self.assertFalse(self.store.get_attempt(permit.attempt_id)['request_started'])
    def test_consume_wait_expires_lease(self):
        from common.operations.publication_gate import consume_permit
        from unittest.mock import patch
        permit=self.ready();elapsed=self.advancing_gate(61)
        with patch('time.monotonic',side_effect=lambda:elapsed[0]):
            with self.assertRaises(Exception):consume_permit(self.store,permit,self.ctx,NOW)
        self.assertFalse(self.store.get_attempt(permit.attempt_id)['request_started'])
    def test_authorize_wait_expires_lease_before_attempt(self):
        from common.operations.publication_gate import authorize_submission
        from unittest.mock import patch
        lease=self.store.claim_run(self.run,'worker',{'host_id':'fixture','pid':1,'started_at':NOW.isoformat()},NOW)
        for b in ('a','b','c'):self.store.observe_bucket(b,5,0,NOW,NOW+timedelta(hours=1))
        reservation=self.store.reserve_quota('d',[{'bucket_id':b,'amount':1} for b in ('a','b','c')],NOW)
        elapsed=self.advancing_gate(61)
        with patch('time.monotonic',side_effect=lambda:elapsed[0]):
            with self.assertRaises(Exception):authorize_submission(self.store,self.ctx,self.content,self.store.get_publication_approval('d'),lease,reservation['id'],NOW)
        self.assertEqual(self.store.attempts('d'),[])
    def test_validation_elapsed_rechecked_immediately_before_consume(self):
        from common.operations.publication_gate import consume_permit,_inputs
        from unittest.mock import patch
        permit=self.ready();elapsed=[0.0]
        def slow_validation(*args,**kwargs):
            result=_inputs(*args,**kwargs);elapsed[0]+=2;return result
        with patch('time.monotonic',side_effect=lambda:elapsed[0]):
            with patch('common.operations.publication_gate._inputs',side_effect=slow_validation):
                with self.assertRaises(Exception):consume_permit(self.store,permit,self.ctx,NOW+timedelta(seconds=29))
        self.assertFalse(self.store.get_attempt(permit.attempt_id)['request_started'])
    def test_database_transaction_wait_expiry_is_checked_inside_transaction(self):
        from contextlib import contextmanager
        from common.operations.publication_gate import consume_permit
        from unittest.mock import patch
        permit=self.ready();elapsed=[0.0];original_db=self.store._db
        @contextmanager
        def waiting_database(write=False):
            with original_db(write) as db:
                if write:elapsed[0]+=2
                yield db
        with patch('time.monotonic',side_effect=lambda:elapsed[0]):
            with patch.object(self.store,'_db',side_effect=waiting_database):
                with self.assertRaises(Exception):consume_permit(self.store,permit,self.ctx,NOW+timedelta(seconds=29))
        self.assertFalse(self.store.get_attempt(permit.attempt_id)['request_started'])
    def real_database_wait(self,kind):
        import threading,time
        from contextlib import contextmanager,closing
        from dataclasses import replace
        from unittest.mock import patch
        from common.operations.publication_gate import consume_permit
        if kind=='auth':
            self.ctx=replace(self.ctx,auth_expires_at=NOW+timedelta(seconds=30))
            self.observed['expires_at']=self.ctx.auth_expires_at.isoformat()
            with closing(sqlite3.connect(self.store.root/'operations.sqlite3')) as db:
                db.execute('UPDATE runtime_deliveries SET context=?,context_hash=? WHERE id=?',(json.dumps(self.ctx.to_dict()),self.ctx.context_hash,'d'))
                db.execute('UPDATE publication_approvals SET context_hash=? WHERE delivery_id=?',(self.ctx.context_hash,'d'));db.commit()
            self.store.record_evidence('d','target_observation',self.observed)
        permit=self.ready();start=NOW+timedelta(seconds=29)
        if kind=='lease':
            permit=replace(permit,expires_at=NOW+timedelta(seconds=60));start=NOW+timedelta(seconds=59)
            with closing(sqlite3.connect(self.store.root/'operations.sqlite3')) as db:
                db.execute('UPDATE submission_permits SET expires_at=? WHERE attempt_id=?',(permit.expires_at.isoformat(),permit.attempt_id));db.commit()
        elapsed=[0.0];entered=threading.Event();errors=[];original=self.store._db
        @contextmanager
        def waiting(write=False):
            if write:entered.set()
            with original(write) as db:yield db
        def consume():
            try:consume_permit(self.store,permit,self.ctx,start)
            except Exception as exc:errors.append(exc)
        with closing(sqlite3.connect(self.store.root/'operations.sqlite3')) as blocker:
            blocker.execute('BEGIN IMMEDIATE')
            with patch('time.monotonic',side_effect=lambda:elapsed[0]):
                with patch.object(self.store,'_db',side_effect=waiting):
                    thread=threading.Thread(target=consume);thread.start()
                    observed=entered.wait(2)
                    if observed:time.sleep(0.05)
                    elapsed[0]=2;blocker.rollback();thread.join(5)
        self.assertTrue(observed);self.assertFalse(thread.is_alive());self.assertTrue(errors)
        self.assertEqual(errors[0].code,{'permit':'permit_expired','auth':'authentication_expired','lease':'lease_expired'}[kind])
        self.assertFalse(self.store.get_attempt(permit.attempt_id)['request_started'])
    def test_two_connections_wait_expires_permit(self):self.real_database_wait('permit')
    def test_two_connections_wait_expires_auth(self):self.real_database_wait('auth')
    def test_two_connections_wait_expires_lease(self):self.real_database_wait('lease')
