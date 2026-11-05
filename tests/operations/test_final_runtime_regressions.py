"""최종 검토 반례: 임시 원장과 읽기/쓰기 계수 가짜 어댑터만 사용한다."""
from datetime import timedelta
from unittest.mock import patch
from common.shared.axlock import AxLock
from common.operations.recovery import recover_expired_runs, retry_delivery
from tests.operations import test_runtime_acceptance as acceptance
from tests.operations.test_runtime_store import NOW
from common.operations.publication_gate import refresh_auth_observation, consume_permit
from common.operations.runtime_models import PublicationContext, ExecutionPolicy
from common.operations.content_store import ConflictError
from dataclasses import replace
import unittest


class ObservedRemote(acceptance.RemoteFixture):
    def __init__(self, observation):
        super().__init__()
        self.observation = observation
        self.inspections = 0
        self.preparations = 0

    def inspect_target(self, ctx):
        self.inspections += 1
        return self.observation

    def prepare(self, *args):
        self.preparations += 1
        return super().prepare(*args)


class FinalRuntimeRegressions(unittest.TestCase):
    build = acceptance.RuntimeAcceptanceTests.build
    work = acceptance.RuntimeAcceptanceTests.work
    add_delivery = acceptance.RuntimeAcceptanceTests.add_delivery
    observe_quota = acceptance.RuntimeAcceptanceTests.observe_quota
    dead = staticmethod(acceptance.RuntimeAcceptanceTests.dead)
    free = staticmethod(acceptance.RuntimeAcceptanceTests.free)

    def setUp(self):
        acceptance.RuntimeAcceptanceTests.setUp(self)
        self.store.locks = AxLock(self.store.locks.paths, process_probe=lambda _: False)
        self.observe_quota()

    def fresh(self, now):
        return dict(self.observed, checked_at=now.isoformat(), expires_at=(now+timedelta(hours=1)).isoformat())

    def resume(self, now):
        return retry_delivery(self.store, 'd', {'expected_version':self.store.get_delivery('d')['version'], 'request_key':'retry'},
            'fixture', policy=self.policy, registry=self.registry, process_probe=self.dead, lock_probe=self.free, now=now)

    def test_future_candidate_is_skipped_and_due_sibling_runs(self):
        run = self.store.submit_occurrence(dict(job_id='j', scheduled_at_utc=(NOW+timedelta(days=1)).isoformat(),
            phase='submit',source='console',request_kind='new_publication',mode='live'))['id']
        self.add_delivery('future', run)
        adapter = ObservedRemote(self.observed)
        self.assertEqual(self.work(self.store, adapter), 'd')
        self.assertIsNone(self.work(self.store, adapter))
        self.assertEqual((adapter.inspections,adapter.preparations,len(adapter.submitted)), (1,1,1))
        self.assertEqual(self.store.get_run(run)['state'],'queued')
        self.assertEqual(self.store.attempts('future'),[])

    def test_claim_crash_queued_recovery_and_same_id_resume(self):
        adapter = ObservedRemote(self.observed)
        with patch('common.operations.worker._inputs', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):self.work(self.store,adapter)
        later = NOW+timedelta(minutes=2)
        recover_expired_runs(self.store,later,self.dead,lock_probe=self.free)
        self.assertEqual(self.store.get_delivery('d')['state'],'retry_wait')
        self.resume(later)
        self.assertEqual(self.work(self.store,adapter,later),'d')
        self.assertEqual(len(adapter.submitted),1)

    def test_six_minute_fresh_auth_same_ids(self):
        later = NOW+timedelta(minutes=6)
        adapter = ObservedRemote(self.fresh(later))
        self.assertEqual(self.work(self.store,adapter,later),'d')
        self.assertEqual(self.store.get_delivery('d')['run_id'],self.run)
        self.assertEqual((adapter.inspections,len(adapter.submitted)),(1,1))

    def test_current_target_mismatch_blocks_before_prepare(self):
        adapter = ObservedRemote(dict(self.observed,target_id='other'))
        with self.assertRaisesRegex(Exception,'target_mismatch'):self.work(self.store,adapter)
        self.assertEqual((adapter.inspections,adapter.preparations,len(adapter.submitted)),(1,0,0))

    def test_worker_current_subject_mismatch_blocks_before_prepare(self):
        adapter=ObservedRemote(dict(self.observed,login_subject='other'))
        before=self.store.get_publication_approval('d')
        with self.assertRaisesRegex(Exception,'target_mismatch'):self.work(self.store,adapter)
        self.assertEqual((adapter.inspections,adapter.preparations,len(adapter.submitted)),(1,0,0))
        self.assertEqual(self.store.get_publication_approval('d'),before)

    def test_worker_unauthenticated_blocks_before_prepare(self):
        adapter=ObservedRemote(dict(self.observed,authenticated=False))
        with self.assertRaisesRegex(Exception,'target_mismatch'):self.work(self.store,adapter)
        self.assertEqual((adapter.inspections,adapter.preparations,len(adapter.submitted)),(1,0,0))

    def test_future_only_has_no_adapter_calls(self):
        future=NOW+timedelta(days=1)
        run=self.store.submit_occurrence(dict(job_id='j',scheduled_at_utc=future.isoformat(),phase='submit',source='console',request_kind='new_publication',mode='live'))['id']
        self.add_delivery('future',run)
        self.store.transition_delivery('d',self.store.get_delivery('d')['version'],'cancelled')
        adapter=ObservedRemote(self.observed)
        self.assertIsNone(self.work(self.store,adapter))
        self.assertEqual((adapter.inspections,adapter.preparations,len(adapter.submitted)),(0,0,0))

    def test_claim_immediate_process_death_and_live_unknown_probes(self):
        self.store.claim_run(self.run,'dead-worker',{'host_id':'fixture','pid':123,'started_at':NOW.isoformat()},NOW)
        later=NOW+timedelta(minutes=6)
        for probe in (lambda identity:dict(identity,status='alive'),lambda identity:{'status':'dead'},lambda identity:dict(identity,pid=999,status='dead')):
            recover_expired_runs(self.store,later,probe,lock_probe=self.free)
            self.assertEqual(self.store.get_delivery('d')['state'],'queued')
        recover_expired_runs(self.store,later,self.dead,lock_probe=lambda context:{'status':'held','connection_id':'x'})
        self.assertEqual(self.store.get_delivery('d')['state'],'queued')
        recover_expired_runs(self.store,later,self.dead,lock_probe=self.free)
        self.assertEqual(self.store.get_delivery('d')['state'],'retry_wait')
        self.resume(later)
        adapter=ObservedRemote(self.fresh(later))
        self.assertEqual(self.work(self.store,adapter,later),'d')
        self.assertEqual(len(self.store.attempts('d')),1)

    def test_prepare_error_recorded_and_expired_auth_can_resume(self):
        adapter=ObservedRemote(self.observed)
        with patch.object(adapter,'prepare',side_effect=ValueError('fixture')):
            with self.assertRaises(ValueError):self.work(self.store,adapter)
        self.assertEqual(self.store.get_delivery('d')['state'],'retry_wait')
        self.assertEqual(self.store.attempts('d'),[])
        self.assertTrue(any(e['kind']=='preflight_failed' for e in self.store.events('d')))
        later=NOW+timedelta(hours=2)
        recover_expired_runs(self.store,later,self.dead,lock_probe=self.free)
        self.resume(later)
        adapter.observation=self.fresh(later)
        self.assertEqual(self.work(self.store,adapter,later),'d')

    def test_crash_after_reserve_before_attempt_releases_only_orphan_hold(self):
        adapter=ObservedRemote(self.observed);reservations=[]
        from common.operations.quota import reserve_quota
        def reserve_then_crash(*args,**kwargs):
            reservations.append(reserve_quota(*args,**kwargs))
            raise KeyboardInterrupt
        with patch('common.operations.worker.reserve_quota',side_effect=reserve_then_crash),patch('common.operations.worker._abandon_unstarted',side_effect=RuntimeError('process gone')):
            with self.assertRaises(KeyboardInterrupt):self.work(self.store,adapter)
        self.assertEqual(self.store.attempts('d'),[])
        later=NOW+timedelta(minutes=6)
        recover_expired_runs(self.store,later,lambda identity:dict(identity,status='alive'),lock_probe=self.free)
        self.assertEqual(self.store.get_reservation(reservations[0])['state'],'held')
        recover_expired_runs(self.store,later,self.dead,lock_probe=self.free)
        self.assertEqual(self.store.get_reservation(reservations[0])['state'],'released')
        self.resume(later);adapter.observation=self.fresh(later)
        self.assertEqual(self.work(self.store,adapter,later),'d')
        self.assertTrue(all(bucket['reserved']==1 for bucket in self.store.quota_buckets()))

    def test_auth_refresh_cleanup_failure_reuses_same_logical_reservation(self):
        adapter=ObservedRemote(self.observed)
        with patch('common.operations.worker.authorize_submission',side_effect=RuntimeError('gate failure')),patch.object(self.store,'settle_reservation',side_effect=RuntimeError('cleanup unavailable')):
            for seconds in (1,2,3):
                now=NOW+timedelta(seconds=seconds);adapter.observation=self.fresh(now)
                with self.assertRaises(RuntimeError):self.work(self.store,adapter,now)
        self.assertTrue(all(bucket['reserved']==1 for bucket in self.store.quota_buckets()))
        self.assertEqual(self.work(self.store,adapter,NOW+timedelta(seconds=4)),'d')
        self.assertEqual(len(adapter.submitted),1)

    def refresh(self, now, version=None):
        return refresh_auth_observation(self.store,'d',self.fresh(now),now,
            expected_version=self.store.get_delivery('d')['version'] if version is None else version)

    def test_refresh_invalidates_old_permit_preserves_unstarted_attempt(self):
        permit=acceptance.fixtures.GateFixture.ready(self)
        before=self.store.attempts('d')
        prior=self.store.get_publication_approval('d')
        now=NOW+timedelta(seconds=1)
        fresh=self.refresh(now)
        self.assertEqual(fresh.intent_hash,self.ctx.intent_hash)
        self.assertNotEqual(fresh.context_hash,self.ctx.context_hash)
        with self.assertRaises(Exception):consume_permit(self.store,permit,self.ctx,now)
        self.assertEqual(self.store.attempts('d'),before)
        self.assertEqual(self.store.get_reservation(before[0]['reservation_id'])['state'],'held')
        approval=self.store.get_publication_approval('d')
        self.assertEqual(approval['approval_hash'],prior['approval_hash'])
        self.assertNotEqual(approval['id'],prior['id'])
        self.assertEqual(approval['actor'],'server_auth_refresh')
        self.assertTrue(any(e['kind']=='auth_proof_refreshed' and e['evidence']['source_approval_id']==prior['id'] for e in self.store.events('d')))

    def test_refresh_preserves_unknown_attempt_and_held_quota(self):
        adapter=ObservedRemote(self.observed);adapter.lost_response=True
        with self.assertRaisesRegex(Exception,'submission_uncertain'):self.work(self.store,adapter)
        attempts=self.store.attempts('d');before=self.store.get_delivery('d')
        self.refresh(NOW+timedelta(minutes=6))
        after=self.store.get_delivery('d')
        self.assertEqual((after['state'],after['remote_uncertain'],after['remote_id']),(before['state'],True,before['remote_id']))
        self.assertEqual(self.store.attempts('d'),attempts)
        self.assertEqual(self.store.get_reservation(attempts[0]['reservation_id'])['state'],'held')
        self.assertIsNone(self.work(self.store,adapter,NOW+timedelta(minutes=6)))
        self.assertEqual(len(adapter.submitted),1)

    def test_refresh_preserves_posted_remote_id_and_attempt(self):
        adapter=ObservedRemote(self.observed)
        self.work(self.store,adapter)
        before=self.store.get_delivery('d');attempts=self.store.attempts('d')
        self.refresh(NOW+timedelta(minutes=6))
        after=self.store.get_delivery('d')
        self.assertEqual((after['state'],after['remote_id'],after['url']),(before['state'],before['remote_id'],before['url']))
        self.assertEqual(self.store.attempts('d'),attempts)
        self.assertEqual(self.store.get_reservation(attempts[0]['reservation_id'])['state'],'settled')

    def test_refresh_cas_and_revocation_competition(self):
        version=self.store.get_delivery('d')['version']
        self.refresh(NOW+timedelta(seconds=1),version)
        with self.assertRaises(Exception):self.refresh(NOW+timedelta(seconds=2),version)
        original=self.store.refresh_auth_proof
        def revoke_then_refresh(*args):
            d=self.store.get_delivery('d');ctx=PublicationContext(**d['context'])
            self.store.record_publication_approval('d',d['version'],ctx.context_hash,'revoked',ctx.review_report_hashes,decision='revoked')
            return original(*args)
        with patch.object(self.store,'refresh_auth_proof',side_effect=revoke_then_refresh):
            with self.assertRaises(ConflictError):self.refresh(NOW+timedelta(seconds=3))
        self.assertEqual(self.store.get_publication_approval('d')['decision'],'revoked')

    def test_fresh_auth_cannot_change_intent(self):
        for field,value in [('manifest_hash','other'),('target_id','other'),('policy_revision','other'),('review_report_hashes',('other',)),('options',{'changed':True}),('schedule_slot','other')]:
            with self.subTest(field=field):
                changed=replace(self.ctx,**{field:value},auth_checked_at=NOW+timedelta(seconds=1))
                with self.assertRaises(ConflictError):self.store.refresh_auth_proof('d',self.store.get_delivery('d')['version'],changed,self.fresh(NOW+timedelta(seconds=1)),NOW)
        latest=self.store.content_store.get(self.ctx.content_id)
        self.store.content_store.update(self.ctx.content_id,latest['revision'],{'title':latest['title'],'kind':latest['kind'],'original':'changed'})
        with self.assertRaisesRegex(Exception,'content_changed'):self.refresh(NOW+timedelta(seconds=1))

    def test_refresh_content_update_between_validation_and_cas_rejected(self):
        old=self.store.get_publication_approval('d');original=self.store.refresh_auth_proof
        def update_then_refresh(*args):
            self.store.content_store.update(self.ctx.content_id,1,{'title':'changed','kind':'article','original':'changed'})
            return original(*args)
        with patch.object(self.store,'refresh_auth_proof',side_effect=update_then_refresh):
            with self.assertRaises(ConflictError):self.refresh(NOW+timedelta(seconds=1))
        self.assertEqual(self.store.get_publication_approval('d'),old)

    def test_worker_changed_plan_schedule_blocks_refresh(self):
        original=self.store.get_plan_delivery;approval=self.store.get_publication_approval('d')
        adapter=ObservedRemote(self.fresh(NOW+timedelta(seconds=1)))
        with patch.object(self.store,'get_plan_delivery',side_effect=lambda identity:dict(original(identity),schedule_slot='changed')):
            with self.assertRaisesRegex(Exception,'publication_context_changed'):self.work(self.store,adapter,NOW+timedelta(seconds=1))
        self.assertEqual(self.store.get_publication_approval('d'),approval)
        self.assertEqual(len(adapter.submitted),0)

    def test_worker_changed_policy_blocks_refresh(self):
        self.registry=replace(self.registry,revision='new-registry',jobs={'j':dict(self.registry.jobs['j'],policy_revision='new-policy')},
            policies=dict(self.registry.policies,**{'new-policy':self.registry.policies['p']}))
        approval=self.store.get_publication_approval('d');adapter=ObservedRemote(self.fresh(NOW+timedelta(seconds=1)))
        with self.assertRaisesRegex(Exception,'publication_context_changed'):self.work(self.store,adapter,NOW+timedelta(seconds=1))
        self.assertEqual(self.store.get_publication_approval('d'),approval)
        self.assertEqual(len(adapter.submitted),0)

    def test_worker_changed_review_blocks_refresh(self):
        from common.operations.publication_gate import report_hash
        revised=dict(self.review['reports'][0],execution_id='new-independent-review')
        revised['report_hash']=report_hash(revised)
        original=self.store.read_content_evidence
        def replaced_reviews(*args):
            return [dict(row,report=revised) if row['kind']=='independent_review' else row for row in original(*args)]
        approval=self.store.get_publication_approval('d');adapter=ObservedRemote(self.fresh(NOW+timedelta(seconds=1)))
        with patch.object(self.store,'read_content_evidence',side_effect=replaced_reviews):
            with self.assertRaisesRegex(Exception,'independent_review_required'):self.work(self.store,adapter,NOW+timedelta(seconds=1))
        self.assertEqual(self.store.get_publication_approval('d'),approval)
        self.assertEqual(len(adapter.submitted),0)

    def test_current_subject_and_authentication_required(self):
        for changed in ({'login_subject':'other'},{'authenticated':False}):
            with self.subTest(changed=changed):
                adapter=ObservedRemote(dict(self.observed,**changed))
                with self.assertRaisesRegex(Exception,'target_mismatch'):
                    refresh_auth_observation(self.store,'d',adapter.inspect_target(self.ctx),NOW,expected_version=self.store.get_delivery('d')['version'])
                self.assertEqual(len(adapter.submitted),0)

    def test_profile_wait_fresh_inspect_then_prepare_stop_still_blocks(self):
        from contextlib import contextmanager
        real=self.store.locks;elapsed=[0.0];adapter=ObservedRemote(self.fresh(NOW+timedelta(minutes=6)))
        class Waiting:
            paths=real.paths
            @contextmanager
            def hold(self,resources,**kwargs):
                with real.hold(resources,**kwargs):
                    if resources!=['control:publish-gate']:elapsed[0]+=360
                    yield
        self.store.locks=Waiting()
        original=adapter.prepare
        def prepare(*args):
            result=original(*args);real.set_stop('fixture after prepare');return result
        with patch('time.monotonic',side_effect=lambda:elapsed[0]),patch.object(adapter,'prepare',side_effect=prepare):
            with self.assertRaises(Exception):self.work(self.store,adapter)
        self.assertEqual((adapter.inspections,adapter.preparations,len(adapter.submitted)),(1,1,0))

    def test_disabled_and_unregistered_inspect_zero(self):
        from common.operations.worker import run_once
        adapter=ObservedRemote(self.observed)
        self.assertIsNone(run_once(self.store,self.registry,{'x':adapter},ExecutionPolicy(),self.store.locks,NOW))
        self.assertIsNone(run_once(self.store,self.registry,{},self.policy,self.store.locks,NOW))
        self.assertEqual((adapter.inspections,adapter.preparations,len(adapter.submitted)),(0,0,0))

    def test_readonly_inspect_runs_under_profile_lock_before_any_attempt(self):
        from contextlib import contextmanager,closing
        import sqlite3
        real=self.store.locks;held=[];adapter=ObservedRemote(self.observed);original=adapter.inspect_target
        class ObservedLocks:
            paths=real.paths
            @contextmanager
            def hold(self,resources,**kwargs):
                with real.hold(resources,**kwargs):
                    held.extend(resources)
                    try:yield
                    finally:
                        for resource in resources:held.remove(resource)
        self.store.locks=ObservedLocks()
        def inspect(ctx):
            self.assertEqual(held,['profile:tistory'])
            self.assertEqual(self.store.attempts('d'),[])
            with closing(sqlite3.connect(self.store.root/'operations.sqlite3',timeout=0)) as db:
                db.execute('BEGIN IMMEDIATE');db.rollback()
            return original(ctx)
        with patch.object(adapter,'inspect_target',side_effect=inspect):self.assertEqual(self.work(self.store,adapter),'d')
        self.assertEqual(held,[])

    def test_disabled_connection_inspect_zero(self):
        self.registry=replace(self.registry,connections={'x':replace(self.registry.connections['x'],enabled=False)})
        adapter=ObservedRemote(self.observed)
        with self.assertRaisesRegex(Exception,'connection_disabled'):self.work(self.store,adapter)
        self.assertEqual((adapter.inspections,adapter.preparations,len(adapter.submitted)),(0,0,0))

    def test_builder_fresh_candidate_alone_cannot_authorize(self):
        from common.operations.publication_gate import authorize_submission
        from common.operations.quota import reserve_quota
        later=NOW+timedelta(minutes=6)
        fresh=self.build(observed=self.fresh(later),now=later)
        self.assertNotEqual(fresh.context_hash,self.ctx.context_hash)
        self.assertEqual(self.store.get_delivery('d')['context_hash'],self.ctx.context_hash)
        lease=self.store.claim_run(self.run,'worker',{'host_id':'fixture','pid':1,'started_at':NOW.isoformat()},later)
        reservation=reserve_quota(self.store,{'delivery_id':'d','context':self.ctx},{},later)
        with self.assertRaisesRegex(Exception,'publication_context_required'):
            authorize_submission(self.store,fresh,self.content,self.store.get_publication_approval('d'),lease,reservation,later)
        self.assertEqual(self.store.attempts('d'),[])

    def test_subject_still_bound_when_registry_has_no_expected_subject(self):
        self.registry=replace(self.registry,connections={'x':replace(self.registry.connections['x'],expected_login_subject=None)})
        adapter=ObservedRemote(dict(self.observed,login_subject='other'))
        with self.assertRaisesRegex(Exception,'target_mismatch'):self.work(self.store,adapter)
        self.assertEqual((adapter.inspections,adapter.preparations,len(adapter.submitted)),(1,0,0))
