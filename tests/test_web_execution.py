"""실행 HTTP facade: 서버 주입 fixture만 사용하며 실제 외부 호출은 없다."""
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

APP = Path(__file__).resolve().parents[1] / 'ax-console/app'
sys.path.insert(0, str(APP))

from common.operations.content_store import ConflictError, StoreError
from common.operations.runtime_models import ExecutionPolicy


def trigger(**changes):
    return dict(dict(job_id='produce', scheduled_at_utc='2026-10-30T12:00:00+00:00',
                     phase='prepare', source='console', request_kind='new_publication', mode='live'), **changes)


class FixtureService:
    """A8 공개 인터페이스의 인자와 원본 결과를 보존하는 가짜 서비스."""
    def __init__(self):
        self.calls = []
        self.occurrences = {}
        self.approvals = {}
        self.production = dict(status='completed', content_id='content_fixture', revision=3,
            manifest_hash='a'*64, producer={'credential': 'SECRET'}, observed_usage=None,
            artifact_root='/SECRET', media_evidence=[{'path': '/SECRET'}])

    def submit(self, request, caller_id, *, content_id=None, expected_revision=None):
        self.calls.append(('submit', request, caller_id, content_id, expected_revision))
        key = (request['job_id'], request['scheduled_at_utc'], request['phase'], content_id)
        return self.occurrences.setdefault(key, dict(run_id='run_fixture', binding_id='binding_fixture',
            base_job_id='produce', execution_job_id='production.bound', content_id=content_id,
            content_revision=expected_revision, manifest_hash='a'*64, nonce='SECRET', credential='SECRET'))

    def observe(self, delivery_id, run_id, expected_version):
        self.calls.append(('observe', delivery_id, run_id, expected_version))
        return dict(id='observation_fixture', planned_delivery_id=delivery_id, run_id=run_id,
                    plan_version=expected_version, registry_revision='v3', checked_at='2026-10-30T12:00:00Z',
                    observation={'authenticated': True, 'credential': 'SECRET', 'profile': '/SECRET'})

    def admit(self, delivery_id, run_id, expected_version, observation_id):
        self.calls.append(('admit', delivery_id, run_id, expected_version, observation_id))
        return dict(id=delivery_id, run_id=run_id, state='waiting', version=2,
                    context_hash='b'*64, context={'credential': 'SECRET'})

    def approve(self, delivery_id, expected_version, context_hash, request_key, actor):
        self.calls.append(('approve', delivery_id, expected_version, context_hash, request_key, actor))
        command = (delivery_id, expected_version, context_hash, actor)
        if request_key in self.approvals:
            old_command, result = self.approvals[request_key]
            if command != old_command:
                raise ConflictError()
            return result
        result = dict(id=delivery_id, version=3, state='queued', context_hash=context_hash,
                      actor=actor, decision='approved', approval_hash='SECRET', nonce='SECRET')
        self.approvals[request_key] = (command, result)
        return result

    def status(self, run_id):
        self.calls.append(('status', run_id))
        return dict(run_id=run_id, state='queued', version=1, nonce='SECRET', worker_id='/SECRET',
            deliveries=[dict(id='delivery_fixture', state='needs_auth', version=2,
                reason='media_evidence_required', context_hash='b'*64,
                context={'credential': 'SECRET'}, path='/SECRET')],
            production=self.production, error='token SECRET', credential='SECRET')


class ExecutionFacadeTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('web_execution'), '실행 HTTP facade가 필요합니다')
        self.web = importlib.import_module('web_execution')
        self.service = FixtureService()
        self.policy = ExecutionPolicy(enabled=True, cutover_revision='fixture-cutover')

    def send(self, method='POST', path='/api/v2/execution/requests', body=None, **kwargs):
        return self.web.handle_request(method, path, {}, body, self.service,
            policy=self.policy, actor='authenticated-console-user', **kwargs)

    def request_body(self, **changes):
        return dict(dict(trigger=trigger(), content_id='content_fixture', expected_revision=2), **changes)

    def assert_invalid(self, body, path='/api/v2/execution/requests'):
        count = len(self.service.calls)
        with self.assertRaises(StoreError) as caught:
            self.send(body=body, path=path)
        self.assertEqual(caught.exception.code, 'invalid')
        self.assertEqual(len(self.service.calls), count)

    def test_recognized_routes_are_exact(self):
        for path in ('/api/v2/execution/requests', '/api/v2/execution/status',
                     '/api/v2/execution/runs/run_fixture', '/api/v2/execution/deliveries/delivery_fixture/observe',
                     '/api/v2/execution/deliveries/delivery_fixture/admit', '/api/v2/execution/deliveries/delivery_fixture/approve'):
            self.assertTrue(self.web.recognizes(path), path)
        for path in ('/api/v2/execution', '/api/v2/execution/requests/', '/api/v2/execution/runs/../secrets',
                     '/api/v2/execution/runs/run%2Fsecret', '/api/v2/execution/deliveries/d/enable'):
            self.assertFalse(self.web.recognizes(path), path)

    def test_prepare_freezes_explicit_revision_and_console_caller(self):
        result = self.send(body=self.request_body())
        self.assertEqual(result, dict(run_id='run_fixture', binding_id='binding_fixture', base_job_id='produce',
            execution_job_id='production.bound', content_id='content_fixture', content_revision=2, manifest_hash='a'*64))
        self.assertEqual(self.service.calls, [('submit', trigger(), 'console', 'content_fixture', 2)])
        self.assertNotIn('SECRET', json.dumps(result))

    def test_exact_request_and_trigger_fields_reject_server_overrides(self):
        for field in ('actor', 'caller_id', 'enabled', 'owner_account_id', 'binding', 'production_unit_id', 'credential', 'permit', 'review_report'):
            self.assert_invalid(dict(self.request_body(), **{field: True}))
            self.assert_invalid(self.request_body(trigger=dict(trigger(), **{field: True})))
        for body in ({}, [], None, {'trigger': trigger()}, self.request_body(trigger={}),
                     self.request_body(trigger=trigger(source='launchd'))):
            self.assert_invalid(body)

    def test_trigger_values_are_validated_before_service_calls(self):
        for field, value in [('job_id', '../secrets'), ('scheduled_at_utc', 'yesterday'),
                             ('scheduled_at_utc', '2026-10-30T12:00:00'), ('phase', 'publish'),
                             ('mode', 'enabled'), ('request_kind', 'approve'), ('source', True)]:
            self.assert_invalid(self.request_body(trigger=trigger(**{field: value})))

    def test_prepare_requires_content_revision_and_other_phases_require_null(self):
        for content_id, revision in ((None, 2), ('content_fixture', None), ('content_fixture', True),
                                     ('content_fixture', 0), ('../private', 2)):
            self.assert_invalid(self.request_body(content_id=content_id, expected_revision=revision))
        for phase in ('submit', 'verify'):
            self.assert_invalid(self.request_body(trigger=trigger(phase=phase)))
            body = self.request_body(trigger=trigger(phase=phase), content_id=None, expected_revision=None)
            self.send(body=body)
            self.assertEqual(self.service.calls[-1], ('submit', trigger(phase=phase), 'console', None, None))

    def test_default_disabled_has_no_external_calls(self):
        for path, body in [('/api/v2/execution/requests', self.request_body()),
                           ('/api/v2/execution/deliveries/d/observe', dict(run_id='r', expected_version=1)),
                           ('/api/v2/execution/deliveries/d/admit', dict(run_id='r', expected_version=1, observation_id='o')),
                           ('/api/v2/execution/deliveries/d/approve', dict(expected_version=1, context_hash='b'*64, request_key='approve'))]:
            with self.assertRaises(self.web.ExecutionBlocked) as caught:
                self.web.handle_request('POST', path, {}, body, self.service, actor='trusted')
            self.assertEqual(caught.exception.code, 'execution_disabled')
        self.assertEqual(self.service.calls, [])

    def test_missing_service_is_unavailable(self):
        for method, path, body in [('POST', '/api/v2/execution/requests', self.request_body()),
                                   ('GET', '/api/v2/execution/runs/r', None)]:
            with self.assertRaises(self.web.ExecutionUnavailable) as caught:
                self.web.handle_request(method, path, {}, body, None, policy=self.policy)
            self.assertEqual(caught.exception.status, 503)
            self.assertEqual(caught.exception.code, 'execution_service_unavailable')

    def test_observation_request_cannot_supply_auth_success(self):
        path = '/api/v2/execution/deliveries/planned_fixture/observe'
        body = dict(run_id='run_fixture', expected_version=1)
        for field in ('authenticated', 'auth_success', 'observation', 'target_id', 'owner_account_id', 'credential', 'actor'):
            self.assert_invalid(dict(body, **{field: True}), path)
        result = self.send(path=path, body=body)
        self.assertEqual(result['id'], 'observation_fixture')
        self.assertEqual(self.service.calls, [('observe', 'planned_fixture', 'run_fixture', 1)])
        self.assertNotIn('observation', result)
        self.assertNotIn('SECRET', json.dumps(result))

    def test_planning_approval_does_not_grant_publication(self):
        self.send(body=self.request_body())
        result = self.send(path='/api/v2/execution/deliveries/d/admit',
                           body=dict(run_id='run_fixture', expected_version=1, observation_id='observation_fixture'))
        self.assertEqual(result, dict(id='d', run_id='run_fixture', state='waiting', version=2, context_hash='b'*64))
        self.assertEqual([call[0] for call in self.service.calls], ['submit', 'admit'])
        for field in ('approved', 'publication_approval', 'report_hashes', 'production_id'):
            self.assert_invalid(dict(run_id='r', expected_version=1, observation_id='o', **{field: True}),
                                '/api/v2/execution/deliveries/d/admit')

    def test_approval_actor_is_server_injected(self):
        path = '/api/v2/execution/deliveries/d/approve'
        body = dict(expected_version=2, context_hash='b'*64, request_key='approval-one')
        self.assert_invalid(dict(body, actor='forged-admin'), path)
        with self.assertRaises(StoreError):
            self.web.handle_request('POST', path, {}, body, self.service, policy=self.policy)
        self.assertEqual(self.service.calls, [])
        self.send(path=path, body=body)
        self.assertEqual(self.service.calls[-1], ('approve', 'd', 2, 'b'*64, 'approval-one', 'authenticated-console-user'))

    def test_replay_same_occurrence_or_approval_returns_original(self):
        body = self.request_body()
        first = self.send(body=body)
        self.assertEqual(self.send(body=body), first)
        self.assertEqual(len(self.service.occurrences), 1)
        path = '/api/v2/execution/deliveries/d/approve'
        approval = dict(expected_version=2, context_hash='b'*64, request_key='approval-one')
        first = self.send(path=path, body=approval)
        self.assertEqual(self.send(path=path, body=approval), first)
        self.assertEqual(len(self.service.approvals), 1)
        with self.assertRaises(ConflictError):
            self.send(path=path, body=dict(approval, context_hash='c'*64))

    def test_get_returns_only_safe_status_without_side_effect_methods(self):
        result = self.send('GET', '/api/v2/execution/runs/run_fixture')
        self.assertEqual(result['state'], 'queued')
        self.assertEqual(result['deliveries'][0]['state'], 'needs_auth')
        self.assertEqual(result['deliveries'][0]['reason'], 'media_evidence_required')
        self.assertEqual(result.get('production'), dict(status='completed', content_id='content_fixture',
                         revision=3, manifest_hash='a'*64))
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertEqual(self.service.calls, [('status', 'run_fixture')])

    def test_blocked_production_mapping_preserves_fixed_reason_only(self):
        self.service.production = dict(status='blocked', reason_code='daily_limit', artifact_root='/SECRET',
            observed_usage={'token': 'SECRET'}, result={'credential': 'SECRET'}, text='SECRET', nonce='SECRET')
        result = self.send('GET', '/api/v2/execution/runs/run_fixture')
        self.assertEqual(result.get('production'), dict(status='blocked', reason_code='daily_limit'))
        self.assertNotIn('SECRET', json.dumps(result))

    def test_unknown_production_mapping_preserves_uncertainty_and_fixed_reason(self):
        self.service.production = dict(status='unknown', reason_code='production_execution_failed',
            artifact_root='/SECRET', credential='SECRET', result={'status': 'completed'})
        result = self.send('GET', '/api/v2/execution/runs/run_fixture')
        self.assertEqual(result.get('production'), dict(status='unknown', reason_code='production_execution_failed'))
        self.assertNotIn('SECRET', json.dumps(result))

    def test_production_mapping_drops_free_reason_and_invalid_snapshot_values(self):
        self.service.production = dict(status='blocked', reason_code='/SECRET', content_id='/SECRET',
                                       revision=True, manifest_hash='SECRET', path='/SECRET')
        result = self.send('GET', '/api/v2/execution/runs/run_fixture')
        self.assertEqual(result.get('production'), dict(status='blocked'))
        self.assertNotIn('SECRET', json.dumps(result))

    def test_no_recorded_production_result_remains_null(self):
        self.service.production = None
        result = self.send('GET', '/api/v2/execution/runs/run_fixture')
        self.assertIn('production', result)
        self.assertIsNone(result['production'])

    def test_status_discovery_preserves_unknown_executor_reason(self):
        info = dict(production_jobs=[dict(id='produce', enabled=True, available=False, reason='unknown_executor')])
        result = self.web.handle_request('GET', '/api/v2/execution/status', {}, None, self.service,
                                        policy=self.policy, status_info=info)
        self.assertEqual(result['production_jobs'], [dict(id='produce', enabled=True, available=False,
                                                         reason='unknown_executor')])
        self.assertEqual(self.service.calls, [])

    def test_status_discovery_is_pure_and_uses_server_allowlist(self):
        info = dict(production_jobs=[dict(id='produce', label='원고 제작', enabled=False, available=False,
                    reason='job_disabled', command='/SECRET', credential='SECRET')],
                    capabilities=dict(request=False, observe=False, admit=False, approve=False, enable=True),
                    root='/SECRET', nonce='SECRET')
        result = self.web.handle_request('GET', '/api/v2/execution/status', {}, None, self.service, status_info=info)
        self.assertFalse(result['execution_enabled'])
        self.assertTrue(result['service_available'])
        self.assertEqual(result['production_jobs'], [dict(id='produce', label='원고 제작', enabled=False,
                         available=False, reason='job_disabled')])
        self.assertNotIn('enable', result['capabilities'])
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertEqual(self.service.calls, [])
        result = self.web.handle_request('GET', '/api/v2/execution/status', {}, None, None)
        self.assertFalse(result['service_available'])
        self.assertIn('execution_service_unavailable', result['blockers'])

    def test_unsupported_methods_queries_and_invalid_cas_are_rejected(self):
        for method, path in [('GET', '/api/v2/execution/requests'), ('POST', '/api/v2/execution/status'),
                             ('POST', '/api/v2/execution/runs/r')]:
            self.assertIsNone(self.send(method, path))
        with self.assertRaises(StoreError):
            self.web.handle_request('GET', '/api/v2/execution/runs/r', {'token': ['SECRET']}, None, self.service)
        with self.assertRaises(StoreError):
            self.send('GET', '/api/v2/execution/runs/r', {'enabled': True})
        for value in (True, -1, 1.1, '1'):
            self.assert_invalid(dict(run_id='r', expected_version=value), '/api/v2/execution/deliveries/d/observe')
        self.assertEqual(self.service.calls, [])

    def test_publication_jobs_are_server_registered_metadata_only(self):
        info = dict(publication_jobs=[dict(id='publish.dept', label='학과 배포', owner_account_id='personal',
                    enabled=True, available=True, phases=['submit', 'verify', 'fabricated'],
                    connection_ids=['dept.youtube', '/SECRET'], reason='unsupported',
                    command='/SECRET', provider_credentials='SECRET')])
        result = self.web.handle_request('GET', '/api/v2/execution/status', {}, None,
                                        self.service, policy=self.policy, status_info=info)
        self.assertEqual(result.get('publication_jobs'), [dict(id='publish.dept', label='학과 배포',
                         owner_account_id='personal', enabled=True, available=True,
                         phases=['submit', 'verify'], connection_ids=['dept.youtube'], reason='unsupported')])
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertEqual(self.service.calls, [])


if __name__ == '__main__':
    unittest.main()
