"""등록 caller fence를 제거하면 무권한 접수/중복 회차가 생기는 회귀 시험."""
import contextlib
import io
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from common.operations.content_store import StoreError
from common.operations.models import ContractError, Registry, Connection
from common.operations.runtime_models import ExecutionPolicy
from common.operations.runtime_store import RuntimeStore
from common.operations.dispatch import submit_trigger
from common.operations.execution_catalog import ExecutorSpec, ExecutionCatalog
from common.operations.entrypoints import resolve_entrypoint, submit_registered
from common.operations.cli import main
from common.operations.registry import load_registry


def request(**changes):
    return dict(dict(job_id='publish', scheduled_at_utc='2026-10-30T00:00:00Z',
        phase='submit', source='console', request_kind='new_publication', mode='dry'), **changes)


def registry():
    common = dict(owner_account_id='personal', executor_id='fixture', schedule_owner='console',
                  execution_owner='managed', enabled=True, policy_revision='p')
    return Registry('fixture', {'personal': {}}, {}, {},
        {'x': Connection('x', 'personal', 'youtube', target_id='fixture-target')},
        {'publish': dict(common, connection_id='x'),
         'produce': dict(common, kind='production'),
         'legacy': dict(common, execution_owner='legacy'),
         'disabled': dict(common, enabled=False)},
        {'p': {'subscription_only': True}}, {})


def catalog():
    executor = ExecutorSpec('fixture', ('publish', 'produce', 'disabled'),
        ('prepare', 'submit', 'verify'), '/usr/bin/python3', Path('/tmp'),
        'tests.fixture_only', ('submit',), ())
    return ExecutionCatalog({'fixture': executor}, {
        'console': {'job_ids': ['publish', 'produce', 'disabled', 'legacy'], 'source': 'console', 'legacy_allowed': True},
        'launchd': {'job_ids': ['publish'], 'source': 'launchd', 'legacy_allowed': False}},
        {'produce': {}})


class EntrypointsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = RuntimeStore(Path(self.temp.name) / 'managed')
        self.store.initialize()
        self.registry, self.catalog, self.policy = registry(), catalog(), ExecutionPolicy()

    def submit(self, req=None, caller='console', **kwargs):
        return submit_registered(req or request(), caller_id=caller, store=self.store,
            registry=self.registry, policy=self.policy, catalog=self.catalog, **kwargs)

    def assert_code(self, code, fn):
        with self.assertRaises((StoreError, ContractError)) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)

    def test_same_occurrence_from_authorized_callers_returns_one_run(self):
        first = self.submit()
        second = self.submit(request(source='launchd', scheduled_at_utc='2026-10-30T09:00:00+09:00'), 'launchd')
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(len(self.store.list_runs()), 1)

    def test_caller_cannot_spoof_source_or_executor(self):
        with patch('subprocess.Popen', side_effect=AssertionError('외부 실행 금지')) as spawn:
            self.assert_code('source_mismatch', lambda: self.submit(request(source='launchd')))
            self.assert_code('invalid_request', lambda: self.submit(request(executor_id='evil')))
            self.assert_code('unknown_caller', lambda: self.submit(caller='unknown'))
            self.assert_code('caller_job_forbidden', lambda: self.submit(request(job_id='produce', source='launchd'), 'launchd'))
            self.assert_code('unknown_caller', lambda: resolve_entrypoint('unknown', 'legacy', self.registry, self.catalog))
        self.assertEqual(spawn.call_count, 0)
        self.assertEqual(self.store.list_runs(), [])

    def test_shadow_does_not_create_runs_or_deliveries(self):
        path = self.store.root / 'operations.sqlite3'
        before = path.read_bytes()
        self.assertEqual(self.submit(request(mode='shadow'))['state'], 'shadow')
        self.assertEqual(path.read_bytes(), before)
        empty = RuntimeStore(Path(self.temp.name) / 'uninitialized')
        result = submit_registered(request(mode='shadow'), caller_id='console', store=empty,
            registry=self.registry, policy=self.policy, catalog=self.catalog)
        self.assertEqual(result['state'], 'shadow')
        self.assertFalse(empty.root.exists())

    def test_legacy_and_disabled_never_enqueue(self):
        self.assertEqual(resolve_entrypoint('console', 'legacy', self.registry, self.catalog)['route'], 'legacy')
        self.assertEqual(resolve_entrypoint('console', 'publish', self.registry, self.catalog)['route'], 'managed')
        self.assert_code('legacy_owner', lambda: self.submit(request(job_id='legacy')))
        self.assert_code('job_disabled', lambda: self.submit(request(job_id='disabled')))
        self.assertEqual(self.store.list_runs(), [])

    def test_production_prepare_has_no_target(self):
        # A4가 명시 주입되기 전에는 target 없는 production도 접수하지 않는다.
        self.assert_code('production_policy_unavailable', lambda: self.submit(request(job_id='produce', phase='prepare')))
        from common.operations.production_models import ProviderPolicy
        policy = ProviderPolicy('fixture', 'personal', ('produce',), True, ('claude-subscription',), ('text',), ())
        resolver = lambda job, registry, execution_policy: policy
        result = self.submit(request(job_id='produce', phase='prepare'), production_policy_resolver=resolver)
        self.assertEqual(self.store.get_run(result['id'])['occurrence']['job_id'], 'produce')
        self.assert_code('invalid_production_phase', lambda: self.submit(request(job_id='produce'), production_policy_resolver=resolver))
        jobs = dict(self.registry.jobs)
        jobs['publish'] = {k: v for k, v in jobs['publish'].items() if k != 'connection_id'}
        self.registry = replace(self.registry, jobs=jobs)
        self.assert_code('unknown_connection', lambda: self.submit(request(phase='prepare')))

    def test_binding_caller_uses_current_base_job_without_expanding_permission(self):
        jobs = dict(self.registry.jobs)
        jobs['bound'] = dict(jobs['produce'], base_job_id='produce', binding_id='binding-fixture')
        self.registry = replace(self.registry, jobs=jobs)
        self.assertEqual(resolve_entrypoint('console', 'bound', self.registry, self.catalog)['base_job_id'], 'produce')
        jobs['produce'] = dict(jobs['produce'], enabled=False)
        self.registry = replace(self.registry, jobs=jobs)
        self.assert_code('job_disabled', lambda: self.submit(request(job_id='bound', phase='prepare')))
        self.assert_code('caller_job_forbidden', lambda: resolve_entrypoint('launchd', 'bound', self.registry, self.catalog))

    def test_registry_type_and_executor_mismatch_fail_closed(self):
        self.assert_code('invalid_registry', lambda: resolve_entrypoint('console', 'publish', SimpleNamespace(jobs=self.registry.jobs), self.catalog))
        jobs = dict(self.registry.jobs)
        jobs['publish'] = dict(jobs['publish'], executor_id='unregistered')
        self.registry = replace(self.registry, jobs=jobs)
        self.assert_code('unknown_executor', lambda: self.submit())

    def test_production_dispatch_requires_real_registry_and_policy_object(self):
        fake = SimpleNamespace(jobs=self.registry.jobs, policies=self.registry.policies,
                               connections=self.registry.connections)
        self.assert_code('invalid_registry', lambda: submit_trigger(self.store,
            request(job_id='produce', phase='prepare'), fake, self.policy,
            production_policy_resolver=lambda *args: True))
        self.assert_code('production_policy_unavailable', lambda: self.submit(
            request(job_id='produce', phase='prepare'), production_policy_resolver=lambda *args: True))

    def test_registry_rejects_unknown_execution_owner_and_bad_production_kind(self):
        base = dict(schema_version=1, revision='fixture', accounts={'personal': {}},
                    jobs={'j': dict(owner_account_id='personal', policy_revision='p', schedule_owner='console',
                                    execution_owner='unknown', enabled=False)}, policies={'p': {}})
        path = Path(self.temp.name) / 'registry.json'
        path.write_text(json.dumps(base))
        self.assert_code('invalid_registry', lambda: load_registry(path))
        base['jobs']['j'].update(execution_owner='managed', kind='unregistered')
        path.write_text(json.dumps(base))
        self.assert_code('invalid_registry', lambda: load_registry(path))


class CLITests(unittest.TestCase):
    def invoke(self, args, services=None):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = main(args, services=services)
        return code, output.getvalue()

    def test_submit_defaults_and_explicit_prepare_binding(self):
        class Services:
            caller_ids = {'console': 'fixture-console', 'launchd': 'fixture-launchd'}
            def submit(self, request, caller_id, *, content_id=None, expected_revision=None):
                self.received = (request, caller_id, content_id, expected_revision)
                return {'state': 'accepted'}
        services = Services()
        code, _ = self.invoke(['submit', '--job', 'produce', '--scheduled-at', '2026-10-30T00:00:00Z',
                               '--phase', 'prepare', '--source', 'console', '--content', 'c', '--revision', '3'], services)
        self.assertEqual(code, 0)
        req, caller, content, revision = services.received
        self.assertEqual(req, request(job_id='produce', phase='prepare'))
        self.assertEqual((caller, content, revision), ('fixture-console', 'c', 3))

    def test_parser_rejects_unsafe_or_incomplete_arguments(self):
        base = ['submit', '--job', 'publish', '--scheduled-at', '2026-10-30T00:00:00Z', '--phase', 'submit', '--source', 'console']
        for suffix in (['--root', '/tmp/evil'], ['--permit', 'evil'], ['--mode', 'unknown'], ['--content', 'c', '--revision', '1']):
            self.assertNotEqual(self.invoke(base + suffix)[0], 0)
        prepare = base.copy(); prepare[prepare.index('submit', 1)] = 'prepare'
        self.assertNotEqual(self.invoke(prepare)[0], 0)
        self.assertNotEqual(self.invoke(['worker'])[0], 0)

    def test_status_and_guard_use_services_without_bootstrap_or_execution(self):
        class Services:
            def status(self): return {'enabled': False}
            def guard_legacy(self, caller_id, job_id):
                return {'route': 'legacy' if caller_id == 'known' else 'managed'}
        services = Services()
        with patch.object(RuntimeStore, 'initialize', side_effect=AssertionError('초기화 금지')), \
             patch('subprocess.Popen', side_effect=AssertionError('실행 금지')):
            self.assertEqual(self.invoke(['status'], services)[0], 0)
            self.assertEqual(self.invoke(['guard-legacy', '--caller', 'known', '--job', 'j'], services)[0], 0)
            self.assertNotEqual(self.invoke(['guard-legacy', '--caller', 'unknown', '--job', 'j'], services)[0], 0)
            self.assertNotEqual(self.invoke(['guard-legacy', '--caller', 'known', '--job', 'j'])[0], 0)
            self.assertEqual(self.invoke(['status'])[0], 0)

    def test_worker_and_reconcile_require_explicit_registered_services(self):
        class Services:
            def worker_once(self): return {'state': 'disabled'}
            def reconcile(self, delivery_id, *, expected_version, request_key):
                return {'id': delivery_id, 'version': expected_version, 'key': request_key}
        services = Services()
        self.assertEqual(self.invoke(['worker', '--once'], services)[0], 0)
        self.assertEqual(self.invoke(['reconcile', '--delivery', 'd', '--expected-version', '2', '--request-key', 'k'], services)[0], 0)
        self.assertNotEqual(self.invoke(['worker', '--once'])[0], 0)
        self.assertNotEqual(self.invoke(['reconcile', '--delivery', 'd', '--expected-version', '-1', '--request-key', 'k'], services)[0], 0)

    def test_cli_only_emits_public_result_fields(self):
        class Services:
            def status(self):
                return {'enabled': False, 'state': 'disabled', 'nonce': 'fixture-private',
                        'permit': {'nonce': 'fixture-private'}, 'token': 'fixture-private'}
        code, output = self.invoke(['status'], Services())
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output), {'enabled': False, 'state': 'disabled'})
