"""격리된 원장/소스 루트에서 실제 worker 관문과 복구를 연결한 S7 수락시험."""
from contextlib import closing
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
import sqlite3
import unittest
from unittest.mock import patch

from common.operations.content_store import StoreError
from common.operations.models import ContractError
from common.operations.quota import bucket_id, quota_window, reserve_quota
from common.operations.recovery import (
    recover_expired_runs, reconcile_delivery, retry_delivery, retryable_delivery_ids,
)
from common.operations.runtime_models import LookupResult, RunLease, SubmissionResult, VerificationResult
from common.operations.runtime_store import RuntimeStore
from common.operations.verification import verify_delivery
from common.operations.worker import run_once
from tests.operations import test_publication_gate as fixtures
from tests.operations.test_runtime_store import NOW


class RemoteFixture:
    """가짜 원격 저장소는 원장과 독립적으로 살아 있어 응답 유실을 표현한다."""
    def __init__(self, lost_response=False):
        self.lost_response = lost_response
        self.submitted = []
        self.remote = {}
        self.lookups = 0
        self.verifications = 0

    def prepare(self, context, snapshot):
        return {'body_sha256': hashlib.sha256(snapshot['original'].encode()).hexdigest(),
                'media_sha256': [a['sha256'] for a in snapshot['assets']]}

    def submit(self, context, prepared, permit):
        self.submitted.append(permit.attempt_id)
        candidate = dict(prepared, remote_id='remote-' + str(len(self.submitted)),
                         target_id=context.target_id,
                         destination_account_id=context.destination_account_id,
                         created_at=(NOW + timedelta(seconds=1)).isoformat())
        self.remote[permit.attempt_id] = candidate
        if self.lost_response:
            raise TimeoutError('fixture: remote accepted; response lost')
        return SubmissionResult('submitted', remote_id=candidate['remote_id'])

    def lookup(self, context, attempt):
        self.lookups += 1
        candidate = self.remote.get(attempt['id'])
        return LookupResult('matched' if candidate else 'not_found', [candidate] if candidate else [])

    def verify(self, context, remote_id, snapshot):
        self.verifications += 1
        candidate = next(c for c in self.remote.values() if c['remote_id'] == remote_id)
        return VerificationResult('verified', NOW + timedelta(minutes=2),
                                  dict(candidate, visibility='public'))


class RuntimeAcceptanceTests(unittest.TestCase):
    # 준비 함수만 재사용한다. 관문 단위시험은 이 클래스에서 중복 수집하지 않는다.
    setUp = fixtures.GateFixture.setUp
    build = fixtures.GateFixture.build

    @staticmethod
    def dead(identity):
        return dict(identity, status='dead')

    @staticmethod
    def free(context):
        return {'status': 'free', 'connection_id': context['connection_id']}

    def observe_quota(self):
        for requirement in self.registry.policies['p']['quota_requirements']:
            start, end = quota_window(requirement, NOW)
            key = bucket_id(requirement['scope_kind'], requirement['scope_id'], requirement['metric'], start, end)
            self.store.observe_bucket(key, 5, 0, NOW, end)

    def work(self, store, adapter, now=NOW):
        return run_once(store, self.registry, {'x': adapter}, self.policy, self.store.locks, now)

    def reopen(self):
        store = RuntimeStore(self.store.root, self.registry, self.store.content_store)
        store.initialize()
        store.locks = self.store.locks
        return store

    def assert_recovered_once(self, adapter):
        before = self.store.attempts('d')
        self.assertEqual(len(before), 1)
        self.assertTrue(before[0]['request_started'])
        self.assertFalse(before[0]['resolved'])
        reservation = before[0]['reservation_id']
        self.assertEqual(self.store.get_reservation(reservation)['state'], 'held')
        self.assertEqual(len(adapter.remote), 1)
        # 원본이 아닌 임시 DB를 새 RuntimeStore로 열고 만료 실행을 복구한다.
        restarted = self.reopen()
        later = NOW + timedelta(minutes=2)
        recover_expired_runs(restarted, later, self.dead, lock_probe=self.free)
        self.assertEqual(restarted.get_delivery('d')['state'], 'unknown')
        self.assertEqual(retryable_delivery_ids(restarted, self.run), [])
        self.assertIsNone(self.work(restarted, adapter, later))
        self.assertEqual(restarted.get_reservation(reservation)['state'], 'held')
        version = restarted.get_delivery('d')['version']
        linked = reconcile_delivery(restarted, 'd', adapter, later,
                                    expected_version=version, request_key='recover-existing')
        self.assertEqual(linked['state'], 'uploaded')
        self.assertEqual(linked['remote_id'], next(iter(adapter.remote.values()))['remote_id'])
        self.assertEqual(restarted.get_reservation(reservation)['state'], 'settled')
        # 동일 복구 명령 재전송은 읽기 전용 lookup도 되풀이하지 않는다.
        self.assertEqual(reconcile_delivery(restarted, 'd', adapter, later,
                         expected_version=version, request_key='recover-existing'), linked)
        snapshot = restarted.content_store.get(self.content['id'], 1)
        self.assertEqual(verify_delivery(restarted, 'd', adapter, snapshot, now=later).outcome, 'verified')
        self.assertEqual(restarted.get_run(self.run)['state'], 'completed')
        self.assertIsNone(self.work(restarted, adapter, later))
        final = self.reopen()
        self.assertEqual(final.get_delivery('d')['state'], 'verified')
        self.assertEqual(len(final.attempts('d')), 1)
        self.assertEqual(adapter.submitted, [before[0]['id']])
        self.assertEqual((adapter.lookups, adapter.verifications), (1, 1))
        self.assertTrue(all(b['reserved'] == 1 for b in final.quota_buckets()))

    def test_worker_response_loss_restart_lookup_verify_never_resubmits(self):
        self.observe_quota()
        adapter = RemoteFixture(lost_response=True)
        with self.assertRaises(ContractError) as error:
            self.work(self.store, adapter)
        self.assertEqual(error.exception.code, 'submission_uncertain')
        self.assertEqual(self.store.get_delivery('d')['state'], 'unknown')
        self.assert_recovered_once(adapter)

    def test_worker_remote_accept_then_result_ledger_failure_restart_recovers(self):
        self.observe_quota()
        adapter = RemoteFixture()
        # permit 소비/request_started commit은 실제 수행. 결과 기록만 DB 장애로 실패한다.
        with patch.object(self.store, 'finish_attempt', side_effect=StoreError('storage_error')):
            with self.assertRaises(StoreError):
                self.work(self.store, adapter)
        self.assertEqual(self.store.get_delivery('d')['state'], 'submitting')
        self.assert_recovered_once(adapter)

    def add_delivery(self, identity, run=None):
        run = run or self.run
        plan = dict(self.plan, id=identity, schedule_slot=identity)
        with closing(sqlite3.connect(self.store.root / 'operations.sqlite3')) as db:
            db.execute('INSERT INTO deliveries VALUES(?,?,?,?,?,?,?,?)',
                       (identity, self.content['id'], 1, 'x', 'initial', identity, identity, json.dumps(plan)))
            db.commit()
        context = replace(self.ctx, run_id=run, schedule_slot=identity)
        self.store.create_delivery(identity, run, context)
        self.store.record_evidence(identity, 'target_observation', self.observed)
        self.store.record_publication_approval(identity, 1, context.context_hash, identity, context.review_report_hashes)
        return context

    def test_partial_retry_service_requeues_same_ids_worker_only_submits_selected(self):
        self.observe_quota()
        adapter = RemoteFixture()
        self.work(self.store, adapter)
        snapshot = self.store.content_store.get(self.content['id'], 1)
        later = NOW + timedelta(minutes=2)
        verify_delivery(self.store, 'd', adapter, snapshot, now=later)
        run = self.store.get_run(self.run)
        lease = RunLease(self.run, run['worker_id'], run['generation'], run['lease_expires_at'])
        # 완료된 채널 옆의 두 대상은 제출 전 종료를 영속 상태로 준비한다.
        reservations = []
        for identity in ('selected', 'other'):
            context = self.add_delivery(identity)
            reservation = reserve_quota(self.store, {'delivery_id': identity, 'context': context}, {}, NOW)
            attempt = self.store.create_attempt(identity, self.store.get_delivery(identity)['version'], lease,
                                               context.context_hash, identity, reservation_id=reservation, now=NOW)
            self.store.finish_attempt(attempt['id'], 'failed', evidence={'confirmed_not_submitted': True}, now=NOW)
            reservations.append(reservation)
        self.assertEqual(self.store.get_run(self.run)['state'], 'partial')
        recover_expired_runs(self.store, later, self.dead, lock_probe=self.free)
        self.assertTrue(all(self.store.get_reservation(r)['state'] == 'released' for r in reservations))
        # 다른 회차의 불확실 대상도 자동 제출 대상에 섞이지 않는다.
        unknown_run = self.store.submit_occurrence(dict(job_id='j',
            scheduled_at_utc=(NOW + timedelta(minutes=1)).isoformat(), phase='submit',
            source='console', request_kind='new_publication', mode='live'))['id']
        self.add_delivery('uncertain', unknown_run)
        adapter.lost_response = True
        with self.assertRaises(ContractError):
            self.work(self.store, adapter, later)
        adapter.lost_response = False
        uncertain = self.store.get_delivery('uncertain')
        self.assertEqual(uncertain['state'], 'unknown')
        uncertain_attempt = self.store.attempts('uncertain')[0]
        self.assertEqual(self.store.get_reservation(uncertain_attempt['reservation_id'])['state'], 'held')
        success = self.store.get_delivery('d')
        other = self.store.get_delivery('other')
        decision = {'expected_version': self.store.get_delivery('selected')['version'], 'request_key': 'retry-selected'}
        before = self.store.get_delivery('selected')
        approval = self.store.get_publication_approval('selected')
        result = retry_delivery(self.store, 'selected', decision, 'fixture-user', policy=self.policy,
                                registry=self.registry, process_probe=self.dead, lock_probe=self.free, now=later)
        self.assertEqual((result['id'], result['run_id'], result['state']), ('selected', self.run, 'queued'))
        self.assertEqual(result['context'], before['context'])
        self.assertEqual(self.store.get_publication_approval('selected'), approval)
        self.assertEqual(retry_delivery(self.store, 'selected', decision, 'fixture-user',
                         policy=self.policy, registry=self.registry, now=later), result)
        # 같은 회차 호출도 기존 run만 재사용한다.
        occurrence = self.store.get_run(self.run)['occurrence']
        self.assertEqual(self.store.submit_occurrence({key: occurrence[key] for key in ('job_id', 'scheduled_at_utc', 'phase', 'source', 'request_kind', 'mode')})['id'], self.run)
        self.assertEqual(self.work(self.store, adapter, later), 'selected')
        self.assertIsNone(self.work(self.store, adapter, later))
        self.assertEqual(self.store.get_delivery('d'), success)
        self.assertEqual(self.store.get_delivery('other'), other)
        self.assertEqual(len(self.store.attempts('selected')), 2)
        self.assertFalse(self.store.attempts('selected')[0]['request_started'])
        self.assertTrue(self.store.attempts('selected')[1]['request_started'])
        self.assertEqual(len(adapter.submitted), 3)  # 기존 성공 1 + 기존 unknown 1 + 선택 재개 1
        self.assertEqual(self.store.get_delivery('uncertain'), uncertain)
        self.assertEqual(len(self.store.attempts('uncertain')), 1)
        self.assertEqual(self.store.get_reservation(uncertain_attempt['reservation_id'])['state'], 'held')
        self.assertEqual(len(self.store.attempts('d')), 1)
        self.assertEqual(len(self.store.attempts('other')), 1)
        self.assertEqual(self.store.get_run(self.run)['state'], 'partial')
        for requirement in self.registry.policies['p']['quota_requirements']:
            start, end = quota_window(requirement, NOW)
            key = bucket_id(requirement['scope_kind'], requirement['scope_id'], requirement['metric'], start, end)
            bucket = next(b for b in self.store.quota_buckets() if b['id'] == key)
            self.assertEqual(bucket['reserved'], 1 if requirement['scope_kind'] == 'owner' else 3)

    def test_same_run_unknown_does_not_block_explicit_retry_of_independent_failed_target(self):
        """목표 수락조건: 같은 회차 unknown은 보존하고 명시한 미제출 대상만 재개한다."""
        self.same_run_unknown_retry()

    def test_resume_selection_survives_restart_and_preserves_queued_sibling(self):
        """선택 필터를 빼면 먼저 나열되는 queued 형제가 제출되어 실패한다."""
        self.same_run_unknown_retry(queued_sibling=True)

    def same_run_unknown_retry(self, queued_sibling=False):
        self.observe_quota()
        adapter = RemoteFixture()
        self.work(self.store, adapter)
        later = NOW + timedelta(minutes=2)
        verify_delivery(self.store, 'd', adapter, self.content, now=later)
        run = self.store.get_run(self.run)
        lease = RunLease(self.run, run['worker_id'], run['generation'], run['lease_expires_at'])
        held = None
        for identity in ('uncertain', 'selected', 'other'):
            context = self.add_delivery(identity)
            reservation = reserve_quota(self.store, {'delivery_id': identity, 'context': context}, {}, NOW)
            attempt = self.store.create_attempt(identity, self.store.get_delivery(identity)['version'], lease,
                                               context.context_hash, identity, reservation_id=reservation, now=NOW)
            if identity == 'uncertain':
                permit = self.store.issue_permit(attempt['id'], lease, context.context_hash, identity, NOW)
                self.store.consume_permit(permit, lease, NOW)
                self.store.finish_attempt(attempt['id'], 'unknown', now=NOW)
                held = reservation
            else:
                self.store.finish_attempt(attempt['id'], 'failed', evidence={'confirmed_not_submitted': True}, now=NOW)
        recover_expired_runs(self.store, later, self.dead, lock_probe=self.free)
        if queued_sibling:
            self.add_delivery('queued-sibling')
        sibling = self.store.get_delivery('queued-sibling') if queued_sibling else None
        other = self.store.get_delivery('other')
        uncertain_attempt = self.store.attempts('uncertain')[0]
        occurrence = self.store.get_run(self.run)['occurrence']
        uncertain = self.store.get_delivery('uncertain')
        success = self.store.get_delivery('d')
        selected = self.store.get_delivery('selected')
        self.assertEqual((success['state'], uncertain['state'], selected['state']),
                         ('verified', 'unknown', 'retry_wait'))
        self.assertEqual(self.store.get_reservation(held)['state'], 'held')
        resumed = retry_delivery(self.store, 'selected',
            {'expected_version': selected['version'], 'request_key': 'independent-retry'},
            'fixture-user', policy=self.policy, registry=self.registry,
            process_probe=self.dead, lock_probe=self.free, now=later)
        self.assertEqual((resumed['id'], resumed['run_id'], resumed['state']),
                         ('selected', self.run, 'queued'))
        self.store = self.reopen()
        self.assertEqual(self.store.get_run(self.run)['resume_delivery_id'], 'selected')
        self.assertEqual(self.store.get_run(self.run)['occurrence'], occurrence)
        self.assertEqual(self.work(self.store, adapter, later), 'selected')
        self.assertIsNone(self.work(self.store, adapter, later))
        self.assertEqual(self.store.get_delivery('d'), success)
        self.assertEqual(self.store.get_delivery('uncertain'), uncertain)
        self.assertEqual(self.store.get_reservation(held)['state'], 'held')
        self.assertEqual(len(self.store.attempts('uncertain')), 1)
        self.assertEqual(self.store.get_delivery('other'), other)
        self.assertEqual(self.store.attempts('uncertain'), [uncertain_attempt])
        self.assertEqual(self.store.get_run(self.run)['state'], 'waiting')
        self.store.finish_attempt(uncertain_attempt['id'], 'submitted', remote_id='late-remote', now=later)
        self.assertEqual(self.store.get_delivery('uncertain'), uncertain)
        self.assertEqual(self.store.attempts('uncertain'), [uncertain_attempt])
        self.assertEqual(self.store.get_reservation(held)['state'], 'held')
        self.assertTrue(any(e['kind'] == 'late_attempt_result' for e in self.store.events('uncertain')))
        self.assertEqual(len(adapter.submitted), 2)
        if queued_sibling:
            self.assertEqual(self.store.get_delivery('queued-sibling'), sibling)
            self.assertEqual(self.store.attempts('queued-sibling'), [])
            selected = self.store.get_delivery('selected')
            later += timedelta(minutes=2)
            retry_delivery(self.store, 'other',
                {'expected_version': other['version'], 'request_key': 'next-explicit-retry'},
                'fixture-user', policy=self.policy, registry=self.registry,
                process_probe=self.dead, lock_probe=self.free, now=later)
            self.store = self.reopen()
            self.assertEqual(self.store.get_run(self.run)['resume_delivery_id'], 'other')
            self.assertEqual(self.work(self.store, adapter, later), 'other')
            self.assertIsNone(self.work(self.store, adapter, later))
            self.assertEqual(self.store.get_delivery('selected'), selected)
            self.assertEqual(self.store.get_delivery('queued-sibling'), sibling)
            self.assertEqual(self.store.get_delivery('uncertain'), uncertain)
            self.assertEqual(self.store.get_delivery('d'), success)
            self.assertEqual(self.store.get_reservation(held)['state'], 'held')
            self.assertEqual(len(adapter.submitted), 3)
