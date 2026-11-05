import importlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from common.operations import database
from common.operations.models import ContractError
from common.operations.content_store import ConflictError

NOW=datetime(2026,10,30,tzinfo=timezone.utc)

def context():
    from common.operations.runtime_models import PublicationContext
    return PublicationContext(content_id='c',content_revision=1,manifest_hash='m',owner_account_id='personal',destination_account_id='personal',connection_id='x',target_id='t',publication_purpose='initial',schedule_slot='s',options={'items':[{'x':1}]},schedule_condition={'kind':'fixed','at':NOW.isoformat()},registry_revision='r',policy_revision='p',auth_checked_at=NOW,auth_expires_at=NOW+timedelta(hours=1),review_report_hashes=('a','b'))

class RuntimeStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'managed'
    def store(self):
        from common.operations.runtime_store import RuntimeStore
        return RuntimeStore(self.root)
    def fixture(self,version=2):
        self.root.mkdir(); c=sqlite3.connect(self.root/'operations.sqlite3')
        for sql in database.DDL: c.execute(sql)
        c.execute("INSERT INTO contents VALUES('c','personal',1,'n','n')")
        c.execute("INSERT INTO revisions VALUES('c',1,'hash','original','fixture','n')")
        if version==2:
            for sql in database.OPERATIONS_DDL: c.execute(sql)
            c.execute("INSERT INTO runs VALUES('r','j','n','prepare','hash','{}')")
            payload=json.dumps({'status':'ready','approval':{'subject_hash':'unchanged'}})
            c.execute("INSERT INTO deliveries VALUES('d','c',1,'x','initial','s','hash',?)",(payload,))
            c.execute("INSERT INTO approvals VALUES('a','d','original-approval-hash')")
        c.execute('PRAGMA user_version='+str(version));c.commit();c.close()
    def test_implementation_available(self):
        self.assertIsNotNone(importlib.util.find_spec('common.operations.runtime_store'))
    def test_constructor_and_readonly_old_versions_do_not_write(self):
        s=self.store();self.assertEqual(s.list_operations(),[]);self.assertIsNone(s.get_run('r'));self.assertFalse(self.root.exists())
        for v in (1,2,3):
            if self.root.exists():
                import shutil;shutil.rmtree(self.root)
            self.fixture(min(v,2))
            if v==3:s.initialize()
            before={p:p.read_bytes() for p in self.root.iterdir()}
            self.assertEqual(s.list_operations(),[]);self.assertEqual(s.list_runs(),[]);self.assertIsNone(s.get_delivery('d'))
            self.assertEqual(before,{p:p.read_bytes() for p in self.root.iterdir()})
    def test_migration_preserves_every_old_row(self):
        for v in (1,2):
            if self.root.exists():
                import shutil;shutil.rmtree(self.root)
            self.fixture(v);c=sqlite3.connect(self.root/'operations.sqlite3')
            tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            before={t:c.execute('SELECT * FROM '+t).fetchall() for t in tables};c.close()
            self.store().initialize();c=sqlite3.connect(self.root/'operations.sqlite3')
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],3)
            self.assertEqual(before,{t:c.execute('SELECT * FROM '+t).fetchall() for t in tables});c.close()
    def test_migration_rolls_back(self):
        self.fixture();before=(self.root/'operations.sqlite3').read_bytes()
        with patch.object(database,'RUNTIME_DDL',('CREATE TABLE interrupted(id)','BROKEN SQL')):
            with self.assertRaises(Exception):self.store().initialize()
        self.assertEqual(before,(self.root/'operations.sqlite3').read_bytes())
    def ready(self):
        self.fixture();s=self.store();s.initialize();s.create_run('r');ctx=context();s.create_delivery('d','r',ctx)
        s.record_publication_approval('d',1,ctx.context_hash,'approval',('a','b'))
        lease=s.claim_run('r','worker',{'host_id':'host','pid':123,'started_at':NOW.isoformat()},NOW)
        return s,ctx,lease
    def test_nested_models_are_frozen_and_times_are_utc(self):
        ctx=context()
        with self.assertRaises(TypeError):ctx.options['items'][0]['x']=2
        with self.assertRaises(Exception):ctx.scope='plan'
        from common.operations.runtime_models import RunLease
        with self.assertRaises(ContractError):RunLease('r','w',1,datetime(2026,1,1))
    def test_unresolved_duplicate_and_atomic_permit_consumption(self):
        s,ctx,lease=self.ready();d=s.get_delivery('d')
        a=s.create_attempt('d',d['version'],lease,ctx.context_hash,'approval',now=NOW)
        with self.assertRaises(ConflictError):s.create_attempt('d',s.get_delivery('d')['version'],lease,ctx.context_hash,'approval',now=NOW)
        p=s.issue_permit(a['id'],lease,ctx.context_hash,'approval',NOW)
        db=(self.root/'operations.sqlite3').read_bytes();self.assertNotIn(p.nonce.encode(),db)
        s.consume_permit(p,lease,NOW)
        self.assertEqual(s.get_delivery('d')['state'],'submitting');self.assertTrue(s.get_attempt(a['id'])['request_started'])
        with self.assertRaises(ConflictError):s.consume_permit(p,lease,NOW)
        s.finish_attempt(a['id'],'unknown',now=NOW)
        with self.assertRaises(ConflictError):s.create_attempt('d',s.get_delivery('d')['version'],lease,ctx.context_hash,'approval',now=NOW)
    def test_quota_all_or_none_and_unknown_retention(self):
        s,ctx,lease=self.ready()
        for b in ('x','y'):s.observe_bucket(b,10,2,NOW,NOW+timedelta(hours=1))
        with self.assertRaises(Exception):s.reserve_quota('d',[{'bucket_id':'x','amount':2},{'bucket_id':'y','amount':9}],NOW)
        self.assertTrue(all(b['reserved']==0 for b in s.quota_buckets()))
        r=s.reserve_quota('d',[{'bucket_id':'x','amount':3},{'bucket_id':'y','amount':2}],NOW)
        a=s.create_attempt('d',s.get_delivery('d')['version'],lease,ctx.context_hash,'approval',reservation_id=r['id'],now=NOW)
        p=s.issue_permit(a['id'],lease,ctx.context_hash,'approval',NOW);s.consume_permit(p,lease,NOW);s.finish_attempt(a['id'],'unknown',now=NOW)
        with self.assertRaises(ConflictError):s.settle_reservation(r['id'],release=True)
    def test_control_cas_and_request_key(self):
        s=self.store();s.initialize()
        r=s.control('managed','all','pause',0,'request','stop')
        self.assertEqual(s.control('managed','all','pause',0,'request','stop'),r)
        with self.assertRaises(ConflictError):s.control('managed','all','resume',0,'new','resume')
        self.assertEqual(s.control_state()[0]['action'],'pause')
    def test_occurrence_atomic_idempotency_and_plan_collision(self):
        self.fixture();s=self.store();s.initialize()
        req=dict(job_id='j2',scheduled_at_utc=NOW.isoformat(),phase='publish',source='scheduler',request_kind='scheduled',mode='live')
        first=s.submit_occurrence(req);self.assertEqual(first,s.submit_occurrence(req))
        with self.assertRaises(ConflictError):s.submit_occurrence(dict(req,mode='dry'))
        collision=dict(req,job_id='j',scheduled_at_utc='2026-10-30T00:00:00+00:00',phase='prepare')
        c=sqlite3.connect(self.root/'operations.sqlite3');c.execute('UPDATE runs SET scheduled_at_utc=? WHERE id=?',(collision['scheduled_at_utc'],'r'));c.commit();c.close()
        with self.assertRaises(ConflictError):s.submit_occurrence(collision)
    def test_expired_running_not_claimable_and_stale_lease_rejected(self):
        s,ctx,lease=self.ready();later=NOW+timedelta(minutes=2)
        with self.assertRaises(ConflictError):s.claim_run('r','other',{'host_id':'h','pid':234,'started_at':NOW.isoformat()},later)
        with self.assertRaises(ConflictError):s.renew_lease(lease,later)
        with self.assertRaises(ConflictError):s.create_attempt('d',s.get_delivery('d')['version'],lease,ctx.context_hash,'approval',now=later)
    def test_revoked_approval_invalidates_permit_without_request_start(self):
        s,ctx,lease=self.ready();a=s.create_attempt('d',s.get_delivery('d')['version'],lease,ctx.context_hash,'approval',now=NOW)
        p=s.issue_permit(a['id'],lease,ctx.context_hash,'approval',NOW)
        s.record_publication_approval('d',s.get_delivery('d')['version'],ctx.context_hash,'approval',('a','b'),decision='revoked')
        with self.assertRaises(ConflictError):s.consume_permit(p,lease,NOW)
        self.assertFalse(s.get_attempt(a['id'])['request_started']);self.assertEqual(s.get_delivery('d')['state'],'running')
    def test_failed_after_request_start_is_unknown_and_cannot_retry(self):
        s,ctx,lease=self.ready();a=s.create_attempt('d',s.get_delivery('d')['version'],lease,ctx.context_hash,'approval',now=NOW)
        p=s.issue_permit(a['id'],lease,ctx.context_hash,'approval',NOW);s.consume_permit(p,lease,NOW)
        s.finish_attempt(a['id'],'failed',evidence={'confirmed_not_submitted':True},now=NOW)
        self.assertEqual(s.get_delivery('d')['state'],'unknown');self.assertFalse(s.get_attempt(a['id'])['resolved'])
    def test_resolve_is_cas_idempotent_and_preserves_plan(self):
        s,ctx,lease=self.ready();a=s.create_attempt('d',s.get_delivery('d')['version'],lease,ctx.context_hash,'approval',now=NOW)
        p=s.issue_permit(a['id'],lease,ctx.context_hash,'approval',NOW);s.consume_permit(p,lease,NOW);s.finish_attempt(a['id'],'unknown',now=NOW)
        v=s.get_delivery('d')['version'];args=('d',v,'resolve','confirmed_not_posted',{'confirmed_not_posted':True,'old_process_terminated':True,'profile_lock_released':True},'독립 확인','server-user')
        r=s.resolve_delivery(*args);self.assertEqual(r,s.resolve_delivery(*args));self.assertEqual(r['state'],'retry_wait')
        with self.assertRaises(ConflictError):s.resolve_delivery('d',v,'new','cancel_local',{'checked':True},'취소','server-user')
        c=sqlite3.connect(self.root/'operations.sqlite3');self.assertEqual(json.loads(c.execute("SELECT payload FROM deliveries WHERE id='d'").fetchone()[0])['status'],'ready');c.close()
    def test_atomic_permit_rollback(self):
        s,ctx,lease=self.ready();a=s.create_attempt('d',s.get_delivery('d')['version'],lease,ctx.context_hash,'approval',now=NOW);p=s.issue_permit(a['id'],lease,ctx.context_hash,'approval',NOW)
        with patch.object(s,'_event',side_effect=RuntimeError('interruption')):
            with self.assertRaises(RuntimeError):s.consume_permit(p,lease,NOW)
        self.assertFalse(s.get_attempt(a['id'])['request_started']);self.assertEqual(s.get_delivery('d')['state'],'running')
        s.consume_permit(p,lease,NOW);self.assertTrue(s.get_attempt(a['id'])['request_started'])
    def test_changed_plan_options_reject_permit_consumption(self):
        s,ctx,lease=self.ready();a=s.create_attempt('d',s.get_delivery('d')['version'],lease,ctx.context_hash,'approval',now=NOW);p=s.issue_permit(a['id'],lease,ctx.context_hash,'approval',NOW)
        c=sqlite3.connect(self.root/'operations.sqlite3');c.execute("UPDATE deliveries SET payload=? WHERE id='d'",(json.dumps({'status':'ready','options':{'visibility':'private'}}),));c.commit();c.close()
        with self.assertRaises(ConflictError):s.consume_permit(p,lease,NOW)
        self.assertFalse(s.get_attempt(a['id'])['request_started'])
    def test_paused_control_atomically_blocks_permit(self):
        s,ctx,lease=self.ready();a=s.create_attempt('d',s.get_delivery('d')['version'],lease,ctx.context_hash,'approval',now=NOW);p=s.issue_permit(a['id'],lease,ctx.context_hash,'approval',NOW)
        s.control('connection','x','pause',0,'paused','pause')
        with self.assertRaises(ConflictError):s.consume_permit(p,lease,NOW)
        self.assertFalse(s.get_attempt(a['id'])['request_started'])
    def test_result_contract_rejects_non_mapping_evidence_and_nonsequence_candidates(self):
        from common.operations.runtime_models import SubmissionResult,LookupResult,VerificationResult
        for create in (lambda:SubmissionResult('submitted',evidence='bad'),lambda:LookupResult('matched',candidates='bad'),lambda:LookupResult('error',evidence=[]),lambda:VerificationResult('verified',NOW,evidence='bad')):
            with self.assertRaises(ContractError):create()
    def test_single_review_and_policy_types(self):
        from dataclasses import replace
        from common.operations.runtime_models import ExecutionPolicy
        self.assertEqual(replace(context(),review_report_hashes=('source',)).review_report_hashes,('source',))
        with self.assertRaises(ContractError):ExecutionPolicy(enabled=1)
        with self.assertRaises(ContractError):ExecutionPolicy(enabled=True)
    def test_new_observation_absorbs_settled_usage_but_keeps_held(self):
        s,ctx,lease=self.ready();s.observe_bucket('x:2026-10-30',10,1,NOW,NOW+timedelta(hours=1))
        r=s.reserve_quota('d',[{'bucket_id':'x:2026-10-30','amount':2}],NOW)
        s.settle_reservation(r['id'],now=NOW+timedelta(seconds=1))
        self.assertEqual(s.quota_buckets()[0]['reserved'],2)
        held=s.reserve_quota('d',[{'bucket_id':'x:2026-10-30','amount':1}],NOW+timedelta(seconds=1))
        s.observe_bucket('x:2026-10-30',10,3,NOW+timedelta(seconds=2),NOW+timedelta(hours=1))
        self.assertEqual(s.quota_buckets()[0]['reserved'],1)
    def reserved_attempt(self):
        if self.root.exists():
            import shutil;shutil.rmtree(self.root)
        s,ctx,lease=self.ready();s.observe_bucket('daily',10,0,NOW,NOW+timedelta(hours=1))
        r=s.reserve_quota('d',[{'bucket_id':'daily','amount':3}],NOW)
        a=s.create_attempt('d',s.get_delivery('d')['version'],lease,ctx.context_hash,'approval',reservation_id=r['id'],now=NOW)
        p=s.issue_permit(a['id'],lease,ctx.context_hash,'approval',NOW)
        return s,lease,r,a,p
    def test_cancel_or_review_before_consume_invalidates_submission(self):
        for state in ('cancelled','needs_review'):
            with self.subTest(state=state):
                s,lease,r,a,p=self.reserved_attempt()
                s.transition_delivery('d',s.get_delivery('d')['version'],state)
                with self.assertRaises(ConflictError):s.consume_permit(p,lease,NOW)
                self.assertEqual(s.get_delivery('d')['state'],state);self.assertFalse(s.get_attempt(a['id'])['request_started'])
                c=sqlite3.connect(self.root/'operations.sqlite3');self.assertEqual(c.execute('SELECT invalidated FROM submission_permits').fetchone()[0],1);c.close()
                import shutil;shutil.rmtree(self.root)
    def test_consume_before_cancel_or_review_preserves_started_request(self):
        for state in ('cancelled','needs_review'):
            with self.subTest(state=state):
                s,lease,r,a,p=self.reserved_attempt();s.consume_permit(p,lease,NOW)
                with self.assertRaises(ConflictError):s.transition_delivery('d',s.get_delivery('d')['version'],state)
                self.assertEqual(s.get_delivery('d')['state'],'submitting');self.assertTrue(s.get_attempt(a['id'])['request_started'])
                import shutil;shutil.rmtree(self.root)
    def test_release_before_consume_invalidates_permit_and_blocks_issue(self):
        s,lease,r,a,p=self.reserved_attempt();s.settle_reservation(r['id'],release=True,now=NOW)
        with self.assertRaises(ConflictError):s.consume_permit(p,lease,NOW)
        self.assertFalse(s.get_attempt(a['id'])['request_started']);self.assertEqual(s.get_reservation(r['id'])['state'],'released')
        c=sqlite3.connect(self.root/'operations.sqlite3');self.assertEqual(c.execute('SELECT invalidated FROM submission_permits').fetchone()[0],1);c.close()
    def test_consume_before_release_preserves_held_reservation(self):
        s,lease,r,a,p=self.reserved_attempt();s.consume_permit(p,lease,NOW)
        with self.assertRaises(ConflictError):s.settle_reservation(r['id'],release=True,now=NOW)
        self.assertEqual(s.get_reservation(r['id'])['state'],'held');self.assertEqual(s.get_delivery('d')['state'],'submitting')
    def test_cancel_local_preserves_unknown_quota_across_new_observation(self):
        s,lease,r,a,p=self.reserved_attempt();s.consume_permit(p,lease,NOW);s.finish_attempt(a['id'],'unknown',now=NOW)
        s.resolve_delivery('d',s.get_delivery('d')['version'],'local-cancel','cancel_local',{'checked':True},'로컬 취소','server')
        self.assertEqual(s.get_delivery('d')['state'],'cancelled');self.assertTrue(s.get_delivery('d')['remote_uncertain']);self.assertFalse(s.get_attempt(a['id'])['resolved']);self.assertEqual(s.get_run('r')['state'],'waiting')
        for release in (False,True):
            with self.assertRaises(ConflictError):s.settle_reservation(r['id'],release=release,now=NOW)
        s.observe_bucket('daily',10,0,NOW+timedelta(minutes=1),NOW+timedelta(hours=1))
        self.assertEqual(s.quota_buckets()[0]['reserved'],3)
    def test_confirmed_not_posted_resolves_uncertainty_and_allows_release(self):
        s,lease,r,a,p=self.reserved_attempt();s.consume_permit(p,lease,NOW);s.finish_attempt(a['id'],'unknown',now=NOW)
        s.resolve_delivery('d',s.get_delivery('d')['version'],'proof','confirmed_not_posted',{'confirmed_not_posted':True,'old_process_terminated':True,'profile_lock_released':True},'원격 미게시 확인','server')
        s.settle_reservation(r['id'],release=True,now=NOW)
        self.assertEqual(s.get_reservation(r['id'])['state'],'released');self.assertFalse(s.get_delivery('d')['remote_uncertain'])
    def test_list_runs_includes_empty_queued_and_is_readonly(self):
        s=self.store();self.assertEqual(s.list_runs(),[]);self.assertFalse(self.root.exists())
        s.initialize();r=s.submit_occurrence(dict(job_id='j',scheduled_at_utc=NOW.isoformat(),phase='publish',source='scheduler',request_kind='scheduled',mode='live'))
        before=(self.root/'operations.sqlite3').read_bytes()
        self.assertEqual([x['id'] for x in s.list_runs('queued')],[r['id']]);self.assertEqual(s.list_runs('running'),[])
        self.assertEqual(s.list_runs(),s.list_runs('queued'));self.assertEqual(before,(self.root/'operations.sqlite3').read_bytes())
    def test_cancelled_uncertain_delivery_can_be_confirmed_with_fresh_cas(self):
        s,lease,r,a,p=self.reserved_attempt();s.consume_permit(p,lease,NOW);s.finish_attempt(a['id'],'unknown',now=NOW)
        old=s.get_delivery('d')['version'];s.resolve_delivery('d',old,'local','cancel_local',{'checked':True},'로컬 취소','server')
        proof={'confirmed_not_posted':True,'old_process_terminated':True,'profile_lock_released':True}
        with self.assertRaises(ConflictError):s.resolve_delivery('d',old,'stale','confirmed_not_posted',proof,'확정','server')
        self.assertTrue(s.list_operations()[0]['remote_uncertain'])
        s.resolve_delivery('d',s.get_delivery('d')['version'],'confirmed','confirmed_not_posted',proof,'확정','server')
        s.settle_reservation(r['id'],release=True,now=NOW);self.assertFalse(s.get_delivery('d')['remote_uncertain'])
        self.assertEqual(s.get_attempt(a['id'])['result']['resolution']['kind'],'confirmed_not_posted')
    def test_cancelled_uncertain_can_link_existing_and_settle_but_not_release(self):
        s,lease,r,a,p=self.reserved_attempt();s.consume_permit(p,lease,NOW);s.finish_attempt(a['id'],'unknown',now=NOW)
        s.resolve_delivery('d',s.get_delivery('d')['version'],'local','cancel_local',{'checked':True},'로컬 취소','server')
        s.resolve_delivery('d',s.get_delivery('d')['version'],'link','link_existing',{'remote_id':'existing','identity_confirmed':True},'정확한 대상 확인','server')
        self.assertEqual(s.get_delivery('d')['state'],'uploaded');self.assertFalse(s.get_delivery('d')['remote_uncertain'])
        with self.assertRaises(ConflictError):s.settle_reservation(r['id'],release=True,now=NOW)
        s.settle_reservation(r['id'],now=NOW);self.assertEqual(s.get_reservation(r['id'])['state'],'settled')
    def test_incomplete_nonpublication_proof_does_not_resolve_or_free_quota(self):
        s,lease,r,a,p=self.reserved_attempt();s.consume_permit(p,lease,NOW);s.finish_attempt(a['id'],'unknown',now=NOW)
        from common.operations.content_store import StoreError
        with self.assertRaises(StoreError):s.resolve_delivery('d',s.get_delivery('d')['version'],'weak','confirmed_not_posted',{'confirmed_not_posted':True},'프로세스 미확인','server')
        self.assertTrue(s.get_delivery('d')['remote_uncertain']);self.assertEqual(s.get_reservation(r['id'])['state'],'held')
