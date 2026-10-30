import hashlib
import unittest
from datetime import timedelta
from unittest.mock import Mock
from tests.operations import test_runtime_store as runtime_fixture
NOW = runtime_fixture.NOW
from common.operations.runtime_models import LookupResult
from common.operations.content_store import StoreError, ConflictError


class RecoveryFixture(unittest.TestCase):
    setUp = runtime_fixture.RuntimeStoreTests.setUp
    fixture = runtime_fixture.RuntimeStoreTests.fixture
    store = runtime_fixture.RuntimeStoreTests.store
    ready = runtime_fixture.RuntimeStoreTests.ready

    def started(self, outcome='unknown'):
        s, ctx, lease = self.ready()
        s.content_store = Mock()
        s.content_store.get.return_value = {'manifest_hash':'m','revision':1,'original':'body','assets':[], 'variants':[]}
        a = s.create_attempt('d',s.get_delivery('d')['version'],lease,ctx.context_hash,'approval',now=NOW)
        p = s.issue_permit(a['id'],lease,ctx.context_hash,'approval',NOW)
        s.consume_permit(p,lease,NOW)
        if outcome:s.finish_attempt(a['id'],outcome,remote_id='remote' if outcome=='submitted' else None,now=NOW)
        return s, ctx, lease, a

    def candidate(self, **changes):
        return dict(remote_id='remote',target_id='t',destination_account_id='personal',created_at=NOW.isoformat(),body_sha256=hashlib.sha256(b'body').hexdigest(),media_sha256=[],**changes)

    def dead(self, identity):return dict(identity,status='dead')
    def free(self, context):return {'status':'free','connection_id':context['connection_id']}
    def decision(self,s,kind='confirmed_not_posted',**evidence):
        return dict(expected_version=s.get_delivery('d')['version'],request_key='resolve',kind=kind,evidence=evidence or {'confirmed_not_posted':True},note='operator inspected remote')


class RecoveryTests(RecoveryFixture):
    def test_unknown_remote_success_restart_never_resubmits(self):
        from common.operations.recovery import reconcile_delivery, retryable_delivery_ids
        from common.operations.runtime_store import RuntimeStore
        candidate=self.candidate()
        class LostResponseAdapter:
            submissions=0
            def submit(self,ctx,prepared,permit):
                self.submissions+=1
                raise TimeoutError('remote accepted but response lost')
            def lookup(self,ctx,attempt):return LookupResult('matched',[candidate])
        s,ctx,lease,a=self.started(None);adapter=LostResponseAdapter()
        with self.assertRaises(TimeoutError):adapter.submit(ctx,{},None)
        # 새 프로세스에서 원장을 다시 열어 만료 lease를 복구한다.
        restarted=RuntimeStore(s.root,content_store=s.content_store);restarted.initialize()
        from common.operations.recovery import recover_expired_runs
        recover_expired_runs(restarted,NOW+timedelta(minutes=2),self.dead,lock_probe=self.free)
        result=reconcile_delivery(restarted,'d',adapter,NOW+timedelta(minutes=2),expected_version=restarted.get_delivery('d')['version'],request_key='lookup')
        self.assertEqual(result['state'],'uploaded');self.assertEqual(adapter.submissions,1)
        self.assertEqual(retryable_delivery_ids(restarted,'r'),[])

    def test_weak_zero_multiple_changed_body_or_media_stay_unknown(self):
        from common.operations.recovery import reconcile_delivery
        candidates=[[],[self.candidate(),self.candidate()], [{'remote_id':'other','title':'same'}]]
        for field,value in [('body_sha256','changed'),('media_sha256',['changed'])]:
            c=self.candidate();c[field]=value;candidates.append([c])
        for items in candidates:
            with self.subTest(items=items):
                s,ctx,lease,a=self.started();adapter=Mock();adapter.lookup.return_value=LookupResult('matched',items)
                result=reconcile_delivery(s,'d',adapter,NOW,expected_version=s.get_delivery('d')['version'],request_key='lookup')
                self.assertEqual(result['state'],'unknown');adapter.submit.assert_not_called()
                self.tmp.cleanup();self.setUp()

    def test_manual_raw_booleans_and_unknown_or_wrong_identity_probe_block(self):
        from common.operations.recovery import resolve_unknown
        s,ctx,lease,a=self.started();decision=self.decision(s,old_process_terminated=True,profile_lock_released=True,confirmed_not_posted=True)
        for probe in [None,lambda i:True,lambda i:dict(i,status='unknown'),lambda i:dict(i,status='dead',pid=999)]:
            with self.assertRaises(StoreError):resolve_unknown(s,'d',decision,'server-user',process_probe=probe,lock_probe=self.free)
        self.assertEqual(s.get_delivery('d')['state'],'unknown')

    def test_manual_process_and_lock_confirmed_allows_retry_and_releases_quota(self):
        from common.operations.recovery import resolve_unknown,retryable_delivery_ids
        s,ctx,lease,a=self.started()
        result=resolve_unknown(s,'d',self.decision(s),'server-user',process_probe=self.dead,lock_probe=self.free,now=NOW+timedelta(minutes=2))
        self.assertEqual(result['state'],'retry_wait');self.assertEqual(retryable_delivery_ids(s,'r'),['d'])

    def test_cancel_preserves_unknown_then_lookup_can_link(self):
        from common.operations.recovery import resolve_unknown,reconcile_delivery,retryable_delivery_ids
        s,ctx,lease,a=self.started()
        result=resolve_unknown(s,'d',self.decision(s,'cancel_local',reason='local only'),'server-user')
        self.assertTrue(result['remote_uncertain']);self.assertEqual(s.get_run('r')['state'],'waiting');self.assertEqual(retryable_delivery_ids(s,'r'),[])
        adapter=Mock();adapter.lookup.return_value=LookupResult('matched',[self.candidate()])
        result=reconcile_delivery(s,'d',adapter,NOW,expected_version=result['version'],request_key='later')
        self.assertEqual(result['state'],'uploaded')

    def test_stale_cas_blocks_lookup(self):
        from common.operations.recovery import reconcile_delivery
        s,ctx,lease,a=self.started();adapter=Mock()
        with self.assertRaises(ConflictError):reconcile_delivery(s,'d',adapter,NOW,expected_version=1,request_key='stale')
        adapter.lookup.assert_not_called()

    def test_recovery_alive_unknown_no_retry_and_dead_started_unknown(self):
        from common.operations.recovery import recover_expired_runs,retryable_delivery_ids
        s,ctx,lease,a=self.started(None)
        for status in ['alive','unknown']:
            recover_expired_runs(s,NOW+timedelta(minutes=2),lambda i:dict(i,status=status),lock_probe=self.free)
            self.assertEqual(retryable_delivery_ids(s,'r'),[])
        recover_expired_runs(s,NOW+timedelta(minutes=2),self.dead,lock_probe=self.free)
        self.assertEqual(s.get_delivery('d')['state'],'unknown');self.assertEqual(retryable_delivery_ids(s,'r'),[])

    def test_expired_before_request_requires_dead_and_free_and_late_result_is_evidence(self):
        from common.operations.recovery import recover_expired_runs,retryable_delivery_ids
        s,ctx,lease=self.ready();a=s.create_attempt('d',s.get_delivery('d')['version'],lease,ctx.context_hash,'approval',now=NOW)
        recover_expired_runs(s,NOW+timedelta(minutes=2),self.dead)
        self.assertEqual(retryable_delivery_ids(s,'r'),[])
        recover_expired_runs(s,NOW+timedelta(minutes=2),self.dead,lock_probe=self.free)
        self.assertEqual(s.get_delivery('d')['state'],'retry_wait');self.assertEqual(retryable_delivery_ids(s,'r'),['d'])
        version=s.get_delivery('d')['version'];s.finish_attempt(a['id'],'submitted',remote_id='late',now=NOW+timedelta(minutes=3))
        self.assertEqual(s.get_delivery('d')['version'],version)
        self.assertTrue(any(e['kind']=='late_attempt_result' for e in s.events('d')))

    def test_lookup_storage_failure_never_submits(self):
        from common.operations.recovery import reconcile_delivery
        s,ctx,lease,a=self.started();adapter=Mock();adapter.lookup.return_value=LookupResult('matched',[self.candidate()]);s.resolve_delivery=Mock(side_effect=StoreError('storage_error'))
        with self.assertRaises(StoreError):reconcile_delivery(s,'d',adapter,NOW,expected_version=s.get_delivery('d')['version'],request_key='lookup')
        self.assertEqual(s.get_delivery('d')['state'],'unknown');adapter.submit.assert_not_called()

    def test_manual_and_reconcile_request_key_replay_and_payload_conflict(self):
        from common.operations.recovery import resolve_unknown,reconcile_delivery
        s,ctx,lease,a=self.started();decision=self.decision(s)
        result=resolve_unknown(s,'d',decision,'server-user',process_probe=self.dead,lock_probe=self.free,now=NOW)
        self.assertEqual(resolve_unknown(s,'d',decision,'server-user',now=NOW+timedelta(seconds=3)),result)
        with self.assertRaises(ConflictError):resolve_unknown(s,'d',dict(decision,note='changed'),'server-user')
        self.tmp.cleanup();self.setUp();s,ctx,lease,a=self.started()
        adapter=Mock();adapter.lookup.return_value=LookupResult('matched',[self.candidate()]);version=s.get_delivery('d')['version']
        result=reconcile_delivery(s,'d',adapter,NOW,expected_version=version,request_key='again')
        self.assertEqual(reconcile_delivery(s,'d',adapter,NOW+timedelta(seconds=3),expected_version=version,request_key='again'),result)
        self.assertEqual(adapter.lookup.call_count,1)

    def test_unknown_holds_quota_then_explicit_confirmation_releases(self):
        from common.operations.recovery import resolve_unknown,recover_expired_runs
        s,ctx,lease=self.ready();s.observe_bucket('target',10,0,NOW,NOW+timedelta(hours=1))
        reservation=s.reserve_quota('d',[{'bucket_id':'target','amount':1}],NOW)
        a=s.create_attempt('d',s.get_delivery('d')['version'],lease,ctx.context_hash,'approval',reservation_id=reservation['id'],now=NOW)
        permit=s.issue_permit(a['id'],lease,ctx.context_hash,'approval',NOW);s.consume_permit(permit,lease,NOW)
        recover_expired_runs(s,NOW+timedelta(minutes=2),self.dead,lock_probe=self.free)
        self.assertEqual(s.get_reservation(reservation['id'])['state'],'held')
        self.assertEqual(s.get_run('r')['state'],'waiting')
        resolve_unknown(s,'d',self.decision(s),'server-user',process_probe=self.dead,lock_probe=self.free,now=NOW+timedelta(minutes=2))
        self.assertEqual(s.get_reservation(reservation['id'])['state'],'released')
        self.assertEqual(s.quota_buckets()[0]['reserved'],0)

    def test_store_recovery_stale_cas_and_wrong_identity_do_not_release_attempt(self):
        s,ctx,lease=self.ready();a=s.create_attempt('d',s.get_delivery('d')['version'],lease,ctx.context_hash,'approval',now=NOW)
        run=s.get_run('r');proof=self.dead(run['process_identity']);locks={'d':self.free(ctx.to_dict())}
        with self.assertRaises(ConflictError):s.recover_expired_run('r',run['version']-1,NOW+timedelta(minutes=2),proof,locks)
        proof['pid']=999;s.recover_expired_run('r',run['version'],NOW+timedelta(minutes=2),proof,locks)
        self.assertEqual(s.get_delivery('d')['state'],'running');self.assertFalse(s.get_attempt(a['id'])['resolved'])

    def test_partial_failure_excludes_verified_success(self):
        import sqlite3
        from common.operations.recovery import recover_expired_runs,retryable_delivery_ids
        from common.operations.verification import verify_delivery
        from common.operations.runtime_models import VerificationResult
        s,ctx,lease,a=self.started('submitted')
        connection=sqlite3.connect(s.root/'operations.sqlite3')
        try:
            connection.execute("INSERT INTO deliveries VALUES('d2','c',1,'x','other','s2','hash','{}')");connection.commit()
        finally:connection.close()
        s.create_delivery('d2','r',ctx);s.record_publication_approval('d2',1,ctx.context_hash,'approval',('a','b'))
        s.create_attempt('d2',s.get_delivery('d2')['version'],lease,ctx.context_hash,'approval',now=NOW)
        adapter=Mock();evidence=self.candidate();evidence['visibility']='public';adapter.verify.return_value=VerificationResult('verified',NOW,evidence)
        verify_delivery(s,'d',adapter,s.content_store.get(),now=NOW)
        recover_expired_runs(s,NOW+timedelta(minutes=2),self.dead,lock_probe=self.free)
        self.assertEqual(s.get_run('r')['state'],'partial');self.assertEqual(retryable_delivery_ids(s,'r'),['d2'])

    def test_not_found_reconciliation_request_is_also_idempotent(self):
        from common.operations.recovery import reconcile_delivery
        s,ctx,lease,a=self.started();adapter=Mock();adapter.lookup.return_value=LookupResult('not_found')
        version=s.get_delivery('d')['version'];first=reconcile_delivery(s,'d',adapter,NOW,expected_version=version,request_key='no-match')
        second=reconcile_delivery(s,'d',adapter,NOW+timedelta(seconds=1),expected_version=version,request_key='no-match')
        self.assertEqual(first,second);self.assertEqual(adapter.lookup.call_count,1)

    def test_expired_before_attempt_can_retry_only_after_dead_and_free(self):
        from common.operations.recovery import recover_expired_runs,retryable_delivery_ids
        s,ctx,lease=self.ready();s.transition_delivery('d',s.get_delivery('d')['version'],'running')
        recover_expired_runs(s,NOW+timedelta(minutes=2),self.dead,lock_probe=self.free)
        self.assertEqual(retryable_delivery_ids(s,'r'),['d'])
