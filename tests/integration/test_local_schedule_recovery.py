"""실제 로컬 예약 원장 재사용과 기술사 원문 보존 회귀. 외부 I/O는 fixture뿐이다."""
import hashlib
import json
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from common.operations.content_store import StoreError
from common.operations.execution_catalog import ExecutionCatalog, ExecutorSpec
from common.operations.local_toolkit import LocalToolkitService
from common.operations.models import ContractError
from common.operations.runtime_models import SubmissionResult
from common.operations.runtime_store import RuntimeStore
from common.operations.schedule_time import normalize_schedule
from common.operations.tool_cost_policy import ToolkitPolicy
from common.operations.worker_service import WorkerService
from tests.integration import test_worker_service as fixtures
from tests.operations.test_runtime_store import NOW


class LocalScheduleRecoveryTests(unittest.TestCase):
    setUp = fixtures.PublicationServiceTests.setUp
    build = fixtures.PublicationServiceTests.build
    service = fixtures.PublicationServiceTests.service
    adapter = fixtures.PublicationServiceTests.adapter
    observe_quota = fixtures.PublicationServiceTests.observe_quota

    def toolkit(self, policy=None):
        return LocalToolkitService(registry=self.registry, content_store=self.store.content_store,
            runtime_store=self.store, policy=policy or ToolkitPolicy(True), clock=lambda: NOW)

    def tick(self, service):
        return WorkerService(service, clock=lambda: NOW, stop_event=threading.Event()).tick()

    def test_toolkit_schedule_inspect_requires_real_delivery(self):
        toolkit = self.toolkit()
        with self.assertRaises(StoreError) as missing:
            toolkit.schedule_inspect({'delivery_id': 'missing'})
        self.assertEqual(missing.exception.code, 'not_found')
        self.observe_quota()
        calls = []
        scheduled = NOW
        def submit(*args):
            calls.append('fixture-submit')
            return SubmissionResult('submitted', remote_id='existing-remote', scheduled_at=scheduled)
        service = self.service(self.adapter(submit))
        self.tick(service)
        before = (self.store.root/'operations.sqlite3').read_bytes()
        with patch.object(service, 'submit', side_effect=AssertionError('읽기 중 접수 금지')), \
             patch('socket.socket', side_effect=AssertionError('외부 호출 금지')), \
             patch('subprocess.Popen', side_effect=AssertionError('프로세스 금지')):
            result = toolkit.schedule_inspect({'delivery_id': 'd'})
        delivery = self.store.get_delivery('d')
        for key in ('state', 'remote_id', 'scheduled_at'):
            self.assertEqual(result[key], delivery[key])
        self.assertEqual(result['target_id'], 't')
        self.assertEqual(result['remote_id'], 'existing-remote')
        self.assertEqual(result['scheduled_at'], NOW.isoformat())
        self.assertFalse(result['execution_enabled'])
        self.assertIn('execution_disabled', result['reason_codes'])
        self.assertNotIn('credential_ref', json.dumps(result))
        self.assertEqual(before, (self.store.root/'operations.sqlite3').read_bytes())
        self.assertEqual(calls, ['fixture-submit'])
        blocked = self.toolkit(ToolkitPolicy()).schedule_inspect({'delivery_id': 'd'})
        self.assertTrue(blocked['reason_codes'])
        self.assertFalse(blocked['execution_enabled'])

    def test_timezone_unknown_and_restart_never_resubmit(self):
        for value, zone in (
            ('2026-11-01T01:30:00-04:00', 'America/New_York'),
            ('2026-03-08T02:30:00-05:00', 'America/New_York'),
            ('2026-10-30T09:00:00+00:00', 'Asia/Seoul')):
            with self.subTest(value=value), self.assertRaises(ContractError):
                normalize_schedule(value, zone)
        self.assertEqual(normalize_schedule('2026-10-30T09:00:00+09:00'), '2026-10-30T00:00:00+00:00')
        self.observe_quota()
        def uncertain(*args):
            raise TimeoutError('fixture uncertain')
        self.tick(self.service(self.adapter(uncertain)))
        self.assertEqual(self.store.get_delivery('d')['state'], 'unknown')
        reopened = RuntimeStore(self.store.root, self.registry, self.store.content_store)
        reopened.initialize()
        self.assertEqual(reopened.get_delivery('d')['state'], 'unknown')
        submit_calls = []
        service = self.service(self.adapter(lambda *args: submit_calls.append(args)))
        # 원래 fixture 회차는 영수증 없는 기존 원장이다. 서비스가 재접수하지 않는다.
        spec = ExecutorSpec('fixture-publisher', ('j',), ('submit',), '/fixture/python', self.root, 'fixture', (), ())
        service.catalog = ExecutionCatalog({'fixture-publisher': spec}, {'console': dict(job_ids=['j'], source='console', legacy_allowed=False)})
        from dataclasses import replace
        self.registry = replace(self.registry, jobs={**self.registry.jobs, 'j': dict(self.registry.jobs['j'], executor_id='fixture-publisher')})
        service.base_registry = self.registry
        request = dict(job_id='j', scheduled_at_utc=NOW.isoformat(), phase='submit', source='console', request_kind='new_publication', mode='live')
        with self.assertRaises(StoreError) as legacy:
            service.submit(request, 'console')
        self.assertEqual(legacy.exception.code, 'execution_receipt_required')
        # 영수증이 있는 실제 ExecutionService 접수는 같은 회차를 재사용한다.
        producer = fixtures.ServiceTests()
        producer.setUp()
        self.addCleanup(producer.doCleanups)
        one = producer.submit()
        two = producer.submit()
        self.assertEqual(one, two)
        self.assertEqual(len(producer.store.list_runs()), 1)
        self.assertEqual(producer.calls, [])
        self.tick(service)
        schedule_read = self.toolkit().schedule_inspect({'delivery_id': 'd'})
        self.assertEqual(schedule_read['state'], 'unknown')
        self.assertEqual(submit_calls, [])
        self.assertEqual(len(self.store.attempts('d')), 1)

    def test_stop_and_missing_quota_block_before_submit(self):
        calls = []
        service = self.service(self.adapter(lambda *args: calls.append(args)))
        self.store.locks.set_stop('fixture stop')
        self.assertEqual(self.tick(service)['reason_code'], 'control_blocked')
        self.assertEqual(calls, [])
        control = self.store.locks.status()['control']
        self.store.locks.clear_stop(control['version'])
        result = self.tick(service)
        self.assertEqual(result['state'], 'blocked')
        self.assertEqual(calls, [])
        self.assertFalse(any(a['request_started'] for a in self.store.attempts('d')))

    def test_toolkit_preview_does_not_change_engineer_jobs_or_policies(self):
        root = Path(__file__).resolve().parents[2]
        paths = [root/'personal/claude-jobs/jobs.json', root/'ax-console/config/operations.json',
                 root/'ax-console/config/crossposts.json']
        paths += [root/f'personal/claude-jobs/jobs/{exam}-{kind}.md'
                  for exam in ('survey', 'civil', 'safety', 'building') for kind in ('daily', 'friend')]
        engineer_paths = paths[3:]
        paths += [root/'personal/claude-jobs/공통규칙.md', root/'personal/claude-jobs/managed/production-contract.md', root/'personal/claude-jobs/managed/review-contract.md', root/'common/operations/provider_policy.py']
        job_config_bytes_before = {str(p): p.read_bytes() for p in paths}
        jobs = json.loads(paths[0].read_text())['jobs']
        self.assertTrue({f'{exam}-{kind}' for exam in ('survey','civil','safety','building') for kind in ('daily','friend')} <= {j['key'] for j in jobs})
        for path in engineer_paths:
            text = path.read_text()
            self.assertIn('PDF', text)
            self.assertIn('기술사', text)
        common_rules = (root/'personal/claude-jobs/공통규칙.md').read_text()
        self.assertIn('calc-verifier', common_rules)
        self.assertIn('source-reviewer', common_rules)
        self.assertIn('subscription_only', (root/'common/operations/provider_policy.py').read_text())
        policies_before = repr(self.registry.policies)
        with patch('socket.socket', side_effect=AssertionError('외부 호출 금지')), \
             patch('subprocess.Popen', side_effect=AssertionError('프로세스 금지')):
            toolkit = self.toolkit()
            toolkit.capabilities('personal')
            toolkit.schedule_inspect({'delivery_id': 'd'})
            result = toolkit.csv_preview({'account_id': 'personal', 'csv_text':
                'platform,target_id,remote_id,metric_name,value,observed_at,basis\ntistory,t,r,views,0,2026-01-01T00:00:00Z,lifetime\n'})
        self.assertEqual(result['status'], 'completed')
        job_config_bytes_after = {str(p): p.read_bytes() for p in paths}
        self.assertEqual(job_config_bytes_after, job_config_bytes_before)
        self.assertEqual(policies_before, repr(self.registry.policies))
        self.assertEqual({p: hashlib.sha256(b).hexdigest() for p,b in job_config_bytes_before.items()},
                         {p: hashlib.sha256(b).hexdigest() for p,b in job_config_bytes_after.items()})
