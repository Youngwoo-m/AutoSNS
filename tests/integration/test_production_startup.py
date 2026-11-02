"""제작 전용 startup factory. 가짜 공급자만 사용하며 외부 I/O·발행은 없다."""
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from common.operations.bootstrap_config import BootstrapConfig
from common.operations.content_store import StoreError
from common.operations.execution_catalog import ExecutionCatalog, ExecutorSpec
from common.operations.models import ContractError, Registry
from common.operations.production_startup import build_production_runtime
from common.operations.quota import bucket_id, quota_window
from common.operations.runtime_models import ExecutionPolicy
from tests.operations.test_runtime_store import NOW

OWNERS = ('personal', 'dept')


class ProductionStartupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = BootstrapConfig(source_root=self.root / 'source', workspace_root=self.root / 'managed',
                                      registry_path=self.root / 'registry.json')
        self.quota = {owner: dict(scope_kind='owner', scope_id=owner, metric='posts', window_kind='day',
                                  timezone='UTC', amount=1, limit=5) for owner in OWNERS}
        self.job_ids = {owner: 'produce-' + owner for owner in OWNERS}
        jobs = {self.job_ids[owner]: dict(id=self.job_ids[owner], kind='production', owner_account_id=owner,
                policy_revision='p-' + owner, required_outputs=['text'], executor_id='producer',
                schedule_owner='console', execution_owner='managed', enabled=True, subscription_only=True)
                for owner in OWNERS}
        policies = {'p-' + owner: dict(subscription_only=True, quota_requirements=[self.quota[owner]]) for owner in OWNERS}
        self.registry = Registry('rev', {owner: {} for owner in OWNERS}, {}, {}, {}, jobs, policies, {})
        spec = ExecutorSpec('producer', tuple(self.job_ids.values()), ('prepare',), '/fixture/python', self.root, 'fixture', (), ())
        self.catalog = ExecutionCatalog({'producer': spec},
            {'console': dict(job_ids=list(self.job_ids.values()), source='console', legacy_allowed=False)},
            {job_id: {} for job_id in self.job_ids.values()})
        self.enabled = ExecutionPolicy(True, (), 'cutover', {'subscription_only': True})
        self.calls = []
        calls = self.calls

        class Provider:
            def generate(self, request, prompt, policy):
                calls.append((request.job_id, request.owner_account_id))
                return dict(status='completed', text='완성 본문', provider_id='claude-subscription',
                            execution_id='production-fixture-' + request.owner_account_id, observed_usage=None)
        self.producers = {job_id: {'provider': Provider(), 'media_runner': {}} for job_id in self.job_ids.values()}

    def runtime(self, **overrides):
        args = dict(config=self.config, registry=self.registry, catalog=self.catalog, producers=self.producers,
                    clock=lambda: NOW, initialize=True)
        return build_production_runtime(**dict(args, **overrides))

    def ready(self):
        """저장소를 초기화하고 owner별 원고와 quota bucket을 준비한 enabled runtime."""
        runtime = self.runtime(policy=self.enabled)
        store = runtime.service.store
        for owner in OWNERS:
            start, end = quota_window(self.quota[owner], NOW)
            store.observe_bucket(bucket_id('owner', owner, 'posts', start, end), 5, 0, NOW, end)
        contents = {owner: store.content_store.create(owner, dict(title=owner + ' 원고', kind='article', original=owner + ' 입력'))
                    for owner in OWNERS}
        return runtime, contents

    def submit(self, runtime, owner, snapshot):
        request = dict(job_id=self.job_ids[owner], scheduled_at_utc=NOW.isoformat(), phase='prepare',
                       source='console', request_kind='new_publication', mode='live')
        return runtime.service.submit(request, 'console', content_id=snapshot['id'], expected_revision=snapshot['revision'])

    def test_disabled_factory_does_not_touch_filesystem(self):
        runtime = self.runtime(initialize=False)
        self.assertFalse(runtime.service.policy.enabled)
        self.assertFalse(self.config.workspace_root.exists());self.assertFalse(self.config.source_root.exists())
        self.assertEqual(runtime.worker.tick()['state'], 'disabled')
        self.assertFalse(self.config.workspace_root.exists());self.assertFalse(self.config.source_root.exists())
        self.assertEqual(self.calls, [])

    def test_disabled_factory_leaves_existing_database_unchanged(self):
        self.ready()
        path = self.config.workspace_root / 'operations.sqlite3'
        before = path.read_bytes()
        runtime = self.runtime(initialize=False)
        self.assertEqual(runtime.worker.tick()['state'], 'disabled')
        self.assertEqual(before, path.read_bytes());self.assertEqual(self.calls, [])

    def test_enabled_without_initialize_creates_nothing_and_cannot_write(self):
        runtime = self.runtime(policy=self.enabled, initialize=False)
        self.assertFalse(self.config.workspace_root.exists());self.assertFalse(self.config.source_root.exists())
        request = dict(job_id=self.job_ids['personal'], scheduled_at_utc=NOW.isoformat(), phase='prepare',
                       source='console', request_kind='new_publication', mode='live')
        with self.assertRaises((StoreError, ContractError)):
            runtime.service.submit(request, 'console', content_id='missing', expected_revision=1)
        self.assertFalse(self.config.workspace_root.exists());self.assertEqual(self.calls, [])

    def test_publication_registration_is_rejected_before_any_write(self):
        publication = dict(id='publish', kind='publication', owner_account_id='personal', policy_revision='p-personal',
                           executor_id='producer', schedule_owner='console', execution_owner='managed', enabled=True,
                           connection_ids=['conn'])
        jobs = {**self.registry.jobs, 'publish': publication}
        spec = self.catalog.executors['producer']
        cases = {
            'publication_job': dict(registry=replace(self.registry, jobs=jobs)),
            'connection': dict(registry=replace(self.registry, connections={'conn': {}})),
            'crosspost': dict(registry=replace(self.registry, crossposts={'rule': {}})),
            'legacy_caller': dict(catalog=replace(self.catalog, callers={
                'console': dict(job_ids=list(self.job_ids.values()), source='console', legacy_allowed=True)})),
            'caller_unknown_job': dict(catalog=replace(self.catalog, callers={
                'console': dict(job_ids=['publish'], source='console', legacy_allowed=False)})),
            'submit_executor': dict(catalog=replace(self.catalog, executors={
                'producer': replace(spec, phases=('prepare', 'submit'))})),
            'mutating_executor': dict(catalog=replace(self.catalog, executors={
                'producer': replace(spec, mutation_actions=('upload',))})),
            'unregistered_executor_job': dict(catalog=replace(self.catalog, executors={
                'producer': replace(spec, job_ids=spec.job_ids + ('publish',))})),
            'connection_policy': dict(policy=ExecutionPolicy(True, ('conn',), 'cutover', {})),
            'foreign_producer': dict(producers={**self.producers, 'publish': self.producers[self.job_ids['personal']]}),
            'producer_without_generate': dict(producers={self.job_ids['personal']: {'provider': object()}}),
        }
        for name, override in cases.items():
            with self.subTest(name):
                with self.assertRaises(ContractError):
                    self.runtime(**dict(override, policy=override.get('policy', self.enabled)))
                self.assertFalse(self.config.workspace_root.exists());self.assertFalse(self.config.source_root.exists())
        self.assertEqual(self.calls, [])

    def test_untrusted_flags_are_not_accepted(self):
        for kwargs in (dict(config=None), dict(config=str(self.config.workspace_root)), dict(initialize='yes')):
            with self.subTest(kwargs):
                with self.assertRaises(ContractError):
                    self.runtime(**kwargs)
        with self.assertRaises(ContractError):
            self.runtime(policy={'enabled': True})
        self.assertFalse(self.config.workspace_root.exists())

    def test_enabled_pure_production_service_never_has_adapters(self):
        with patch('common.publishers.build_adapters', side_effect=AssertionError('발행 adapter 금지')), \
             patch('common.publishers.legacy_bridge.LegacyBridge', side_effect=AssertionError('bridge 금지')):
            runtime = self.runtime(policy=self.enabled)
        service = runtime.service
        self.assertTrue(service.policy.enabled);self.assertEqual(dict(service.adapters), {})
        with self.assertRaises(TypeError):
            service.adapters['conn'] = object()
        self.assertIs(runtime.worker.services, service)
        self.assertIs(service.registry, service.store.registry);self.assertIs(service.registry, service.production_store.registry)
        status = service.status()
        self.assertFalse(status['capabilities']['observe'])
        self.assertEqual({row['id'] for row in status['production_jobs']}, set(self.job_ids.values()))
        self.assertEqual(service.status_info()['publication_jobs'], [])
        self.assertEqual(service.status()['capabilities'], dict(submit=True, observe=False, approve=False))

    def test_producer_is_not_called_until_explicit_tick(self):
        runtime, contents = self.ready()
        self.submit(runtime, 'personal', contents['personal'])
        rebuilt = self.runtime(policy=self.enabled, initialize=False)
        self.assertEqual(self.calls, [])
        self.assertEqual(rebuilt.worker.tick()['state'], 'completed')
        self.assertEqual(len(self.calls), 1)

    def test_two_owners_stay_separated(self):
        runtime, contents = self.ready()
        # 다른 owner의 job에 원고를 연결할 수 없다.
        with self.assertRaises(StoreError):
            self.submit(runtime, 'dept', contents['personal'])
        self.assertEqual(runtime.service.production_store.list_bindings(), [])
        self.assertEqual(runtime.service.store.list_runs(), [])
        runs = {owner: self.submit(runtime, owner, contents[owner]) for owner in OWNERS}
        self.assertNotEqual(runs['personal']['execution_job_id'], runs['dept']['execution_job_id'])
        results = [runtime.worker.tick() for _ in OWNERS]
        self.assertEqual([row['state'] for row in results], ['completed', 'completed'])
        self.assertEqual(sorted(self.calls), sorted((self.job_ids[owner], owner) for owner in OWNERS))
        store = runtime.service.store
        links = []
        for owner in OWNERS:
            head = store.content_store.get(contents[owner]['id'])
            self.assertEqual(head['owner_account_id'], owner)
            links.append(store.get_production_for_output(head['id'], head['revision'], head['manifest_hash'])['production_id'])
        self.assertEqual(len(set(links)), 2)
        self.assertEqual(runtime.worker.tick()['state'], 'idle');self.assertEqual(len(self.calls), 2)

    def test_prepare_worker_creates_immutable_output_and_requires_review(self):
        runtime, contents = self.ready()
        snapshot = contents['personal'];store = runtime.service.store
        submitted = self.submit(runtime, 'personal', snapshot)
        self.assertEqual(self.calls, [])
        result = runtime.worker.tick()
        self.assertEqual(result['state'], 'completed');self.assertEqual(result['review_status'], 'required')
        self.assertEqual(self.calls, [(self.job_ids['personal'], 'personal')])
        first = store.content_store.get(snapshot['id'], snapshot['revision'])
        self.assertEqual(first['manifest_hash'], snapshot['manifest_hash']);self.assertEqual(first['original'], snapshot['original'])
        head = store.content_store.get(snapshot['id'])
        self.assertTrue(store.get_production_for_output(head['id'], head['revision'], head['manifest_hash']))
        self.assertEqual(store.get_run(submitted['run_id'])['state'], 'waiting')
        stored = store.get_service_run_result(submitted['run_id'])
        self.assertEqual(stored['status'], 'completed');self.assertEqual(stored['review']['status'], 'required')
        self.assertEqual(stored['review']['reason_code'], 'independent_review_required')
        self.assertEqual(dict(runtime.service.adapters), {})

    def test_replay_and_restart_do_not_call_provider_twice(self):
        runtime, contents = self.ready()
        first = self.submit(runtime, 'personal', contents['personal'])
        self.assertEqual(first, self.submit(runtime, 'personal', contents['personal']))
        self.assertEqual(len(runtime.service.store.list_runs()), 1);self.assertEqual(self.calls, [])
        self.assertEqual(runtime.worker.tick()['state'], 'completed');self.assertEqual(len(self.calls), 1)
        for _ in range(2):
            restarted = self.runtime(policy=self.enabled, initialize=False)
            self.assertEqual(restarted.worker.tick()['state'], 'idle')
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(runtime.service.production_store.list_bindings()), 1)

    def test_status_and_methods_expose_production_only(self):
        runtime, contents = self.ready()
        service = runtime.service
        self.assertEqual(service.status_info()['capabilities'],
                         dict(request=True, observe=False, admit=False, approve=False))
        self.assertEqual(service.status_info()['publication_jobs'], [])
        self.assertEqual(service.status()['capabilities'], dict(submit=True, observe=False, approve=False))
        before = (self.config.workspace_root / 'operations.sqlite3').read_bytes()
        for method in ('observe', 'admit', 'approve', 'verify', 'reconcile'):
            with self.subTest(method=method), self.assertRaises(ContractError):
                getattr(service, method)('foreign')
        for phase in ('submit', 'verify'):
            with self.assertRaises(ContractError):
                service.submit(dict(phase=phase), 'console')
        self.assertEqual(before, (self.config.workspace_root / 'operations.sqlite3').read_bytes())
        self.assertEqual(self.calls, [])

    def test_missing_provider_is_not_advertised_as_ready(self):
        runtime = self.runtime(policy=self.enabled, producers={})
        for job in runtime.service.status_info()['production_jobs']:
            self.assertFalse(job['available'])
            self.assertEqual(job['reason'], 'producer_unavailable')
        self.assertEqual(self.calls, [])

    def test_authenticated_web_request_to_worker_and_output(self):
        import json
        import threading
        from tests import test_web_execution_server as web_fixture
        from tests import test_web_server as http_fixture
        runtime, contents = self.ready()
        self.server = web_fixture.server_module.create_server(
            source_root=self.config.source_root, workspace_root=self.config.workspace_root,
            web_root=web_fixture.APP / 'web', auth_backend=web_fixture.A9Auth(),
            execution_service=runtime.service)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        def close():
            self.server.shutdown(); self.server.server_close(); thread.join()
        self.addCleanup(close)
        request = lambda *args, **kwargs: http_fixture.WebServerTests.request(self, *args, **kwargs)
        path = '/api/v2/execution/requests'
        snapshot = contents['dept']
        body = dict(trigger=dict(job_id=self.job_ids['dept'], scheduled_at_utc=NOW.isoformat(),
            phase='prepare', source='console', request_kind='new_publication', mode='live'),
            content_id=snapshot['id'], expected_revision=snapshot['revision'])
        self.assertEqual(request(path, 'POST', body)[0], 401)
        status, headers, _ = request('/api/auth/login', 'POST', dict(password='fixture-password'))
        self.assertEqual(status, 200)
        cookie = {'Cookie': headers['Set-Cookie'].split(';')[0]}
        self.assertEqual(request(path, 'POST', body, dict(cookie, Origin='https://evil.example'))[0], 403)
        status, _, response = request(path, 'POST', body, cookie)
        self.assertEqual(status, 200)
        run = json.loads(response)
        self.assertEqual(self.calls, [])
        self.assertEqual(runtime.worker.tick()['state'], 'completed')
        status, _, response = request('/api/v2/execution/runs/' + run['run_id'], headers=cookie)
        self.assertEqual(status, 200)
        output = json.loads(response)['production']
        self.assertEqual(output['status'], 'completed')
        self.assertEqual(output['review']['status'], 'required')
        saved = runtime.service.store.content_store.get(output['content_id'], output['revision'])
        self.assertEqual(saved['owner_account_id'], 'dept')
        self.assertEqual(saved['original'], '완성 본문')
        self.assertEqual(dict(runtime.service.adapters), {})


if __name__ == '__main__':
    unittest.main()
