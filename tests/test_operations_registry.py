import json
import tempfile
import unittest
from pathlib import Path
from dataclasses import replace

from common.operations.models import ContractError, ExecutionRequest
from common.operations.registry import load_registry
from common.operations.context import resolve_context
from common.operations.target_guard import validate_observed_target


def fixture():
    return {'schema_version': 1, 'revision': 'fixture-1', 'accounts': {'personal': {}, 'dept': {}},
            'credentials': {'personal.token': {'account_id': 'personal'}},
            'profiles': {'personal.browser': {'account_id': 'personal'}},
            'connections': [{'id': 'personal.youtube', 'account_id': 'personal', 'platform': 'youtube',
                'target_id': 'fixture-channel', 'credential_ref': 'personal.token',
                'profile_ref': 'personal.browser', 'expected_login_subject': 'fixture-user',
                'capabilities': ['plan']}],
            'jobs': {'managed.personal.plan': {'owner_account_id': 'personal', 'executor_id': 'local-plan',
                'schedule_owner': 'console', 'execution_owner': 'managed', 'planning_enabled': True,
                'enabled': False, 'policy_revision': 'plan-1'}},
            'policies': {'plan-1': {'scope': 'plan'}}, 'crossposts': {}}


def request(**kw):
    values = dict(run_id='fixture-run', job_id='managed.personal.plan', owner_account_id='personal',
        content_id='managed_fixture', content_revision=1, connection_id='personal.youtube',
        schedule_slot='initial', publication_purpose='initial')
    values.update(kw)
    return ExecutionRequest(**values)


class RegistryTests(unittest.TestCase):
    def load(self, data=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'registry.json'
            path.write_text(json.dumps(data or fixture()))
            before = path.read_bytes()
            result = load_registry(path)
            self.assertEqual(before, path.read_bytes())
            return result

    def error(self, code, callback):
        with self.assertRaises(ContractError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code)

    def test_registry_is_deeply_immutable_and_context_is_plan_only(self):
        registry = self.load()
        with self.assertRaises(TypeError):
            registry.jobs['managed.personal.plan']['enabled'] = True
        ctx = resolve_context(request(), registry, 'personal')
        self.assertEqual(ctx.target_id, 'fixture-channel')
        self.assertTrue(ctx.dry_run)
        self.assertEqual(ctx.scope, 'plan')
        self.assertFalse(ctx.execution_enabled)
        self.assertNotIn('credential_ref', ctx.to_dict(public=True))
        self.error('invalid_request', lambda: resolve_context(request(dry_run=False), registry, 'personal'))
        self.error('invalid_request', lambda: resolve_context(request(action='submit'), registry, 'personal'))

    def test_unknown_account_and_preference_never_fall_back(self):
        registry = self.load()
        self.error('unknown_account', lambda: resolve_context(request(owner_account_id='other'), registry, 'other'))
        self.error('unknown_connection', lambda: resolve_context(request(connection_id='youtube'), registry, 'personal'))
        self.error('owner_mismatch', lambda: resolve_context(request(), registry, 'dept'))

    def test_duplicates_missing_refs_and_wrong_owned_refs(self):
        for mutation, code in [
            (lambda d: d['connections'].append(d['connections'][0].copy()), 'invalid_registry'),
            (lambda d: d['connections'][0].update(credential_ref='missing'), 'invalid_registry'),
            (lambda d: d['credentials']['personal.token'].update(account_id='dept'), 'credential_owner_mismatch'),
            (lambda d: d['profiles']['personal.browser'].update(account_id='dept'), 'profile_owner_mismatch'),
            (lambda d: d['connections'][0].update(account_id='common'), 'unknown_account'),
        ]:
            with self.subTest(code=code):
                data = fixture()
                mutation(data)
                self.error(code, lambda: self.load(data))

    def test_unverified_is_draft_only(self):
        data = fixture()
        data['connections'][0]['target_id'] = None
        registry = self.load(data)
        self.error('target_unverified', lambda: resolve_context(request(), registry, 'personal'))
        ctx = resolve_context(request(), registry, 'personal', allow_unverified=True)
        self.assertEqual(ctx.target_status, 'unverified')
        self.error('target_unverified', lambda: resolve_context(request(action='prepare'), registry, 'personal', allow_unverified=True))
        self.error('target_unverified', lambda: validate_observed_target(ctx, dict(platform='youtube', target_id=None,
            authenticated=True, login_subject='fixture-user', verification_method='fixture')))

    def test_exact_cross_account_pair_required(self):
        data = fixture()
        data['connections'].append(dict(id='dept.youtube', account_id='dept', platform='youtube', target_id='fixture-dept'))
        registry = self.load(data)
        self.error('crosspost_not_allowed', lambda: resolve_context(request(connection_id='dept.youtube'), registry, 'personal'))
        data['crossposts']['fixture-rule'] = dict(owner_account_id='personal', source_connection_id='personal.youtube',
            destination_connection_id='dept.youtube', enabled=True, delivery_owner='legacy')
        registry = self.load(data)
        ctx = resolve_context(request(connection_id='dept.youtube', crosspost_rule_id='fixture-rule'), registry, 'personal')
        self.assertEqual(ctx.destination_account_id, 'dept')
        self.error('crosspost_not_allowed', lambda: resolve_context(request(crosspost_rule_id='fixture-rule'), registry, 'personal'))

    def test_fixture_target_guard(self):
        ctx = resolve_context(request(), self.load(), 'personal')
        observed = dict(platform='youtube', target_id='fixture-channel', authenticated=True,
            login_subject='fixture-user', verification_method='fixture')
        validate_observed_target(ctx, observed)
        self.error('target_mismatch', lambda: validate_observed_target(ctx, dict(observed, target_id='other')))
        self.error('authentication_required', lambda: validate_observed_target(ctx, dict(observed, authenticated=False)))
        self.error('login_subject_mismatch', lambda: validate_observed_target(ctx, dict(observed, login_subject='other')))

    def test_sibling_rules_merge_and_keep_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'operations.json'
            data = fixture()
            data['connections'].append(dict(id='dept.youtube', account_id='dept', platform='youtube', target_id=None))
            path.write_text(json.dumps(data))
            rule = dict(id='fixture-crosspost', owner_account_id='personal', source_connection_id='personal.youtube',
                destination_connection_id='dept.youtube', activation_evidence={'status': 'unknown'}, enabled=None)
            (path.parent / 'crossposts.json').write_text(json.dumps({'schema_version': 1, 'rules': [rule]}))
            registry = load_registry(path)
            self.assertIsNone(registry.crossposts['fixture-crosspost']['enabled'])
            with self.assertRaises(TypeError):
                registry.crossposts['fixture-crosspost']['activation_evidence']['status'] = 'enabled'

    def test_unknown_nested_accounts_and_duplicate_json_keys(self):
        data = fixture()
        data['accounts']['common'] = {}
        data['connections'][0]['account_id'] = 'common'
        self.error('unknown_account', lambda: self.load(data))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'registry.json'
            path.write_text('{"schema_version": 1, "schema_version": 1}')
            self.error('invalid_registry', lambda: load_registry(path))

    def test_unknown_schedule_owner_only_observed_legacy(self):
        data = fixture()
        data['jobs']['legacy.fixture'] = dict(owner_account_id='personal', executor_id='legacy',
            schedule_owner=None, execution_owner='legacy', planning_enabled=False, enabled=False, policy_revision='plan-1')
        registry = self.load(data)
        self.assertIsNone(registry.jobs['legacy.fixture']['schedule_owner'])
        self.error('planning_disabled', lambda: resolve_context(request(job_id='legacy.fixture'), registry, 'personal'))
        data['jobs']['legacy.fixture']['planning_enabled'] = True
        self.error('invalid_registry', lambda: self.load(data))

    def test_shipped_registry(self):
        registry = load_registry(Path('ax-console/config/operations.json'))
        for account in ('personal', 'dept'):
            job = registry.jobs[f'managed.{account}.plan']
            self.assertTrue(job['planning_enabled'])
            self.assertFalse(job['enabled'])
        self.assertIsNone(registry.connections['dept.instagram'].target_id)
        self.assertNotIn('dept.facebook', registry.connections)
