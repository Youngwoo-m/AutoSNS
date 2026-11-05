import os
from pathlib import Path
import tempfile
import threading
import unittest

from common.operations.content_store import ConflictError, StoreError
from common.operations.models import ContractError
from common.operations.production_settings import (
    DB_NAME, ProductionSettingsStore, compile_production_settings)

ACCOUNTS = {'personal': {'name': '개인'}, 'dept': {'name': '학과'}}
ON = {'enabled_preference': True, 'daily_limit': 3}
OFF = {'enabled_preference': False, 'daily_limit': None}


def listing(root):
    return sorted(str(p.relative_to(root)) for p in Path(root).rglob('*'))


class StoreTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = self.tmp / 'settings'

    def store(self, initialize=True):
        store = ProductionSettingsStore(self.root)
        if initialize: store.initialize()
        return store

    def test_get_and_constructor_do_not_touch_disk(self):
        store = ProductionSettingsStore(self.root)
        for account in ('personal', 'dept'):
            self.assertEqual(store.get(account), {'account_id': account, 'revision': 0, 'enabled_preference': False,
                'daily_limit': None, 'applies_to': 'next_startup', 'execution_enabled': False})
        self.assertFalse(self.root.exists())
        self.root.mkdir()
        store.get('personal')
        self.assertEqual(listing(self.root), [])

    def test_save_requires_explicit_initialize(self):
        store = self.store(initialize=False)
        with self.assertRaises(StoreError) as caught:
            store.save('personal', 0, ON)
        self.assertEqual(caught.exception.code, 'storage_error')
        self.assertFalse(self.root.exists())
        store.initialize()
        self.assertTrue((self.root / DB_NAME).is_file())
        self.assertEqual(store.save('personal', 0, ON)['revision'], 1)

    def test_save_returns_current_row_and_keeps_accounts_separate(self):
        store = self.store()
        saved = store.save('personal', 0, ON)
        self.assertEqual(saved, {'account_id': 'personal', 'revision': 1, 'enabled_preference': True,
            'daily_limit': 3, 'applies_to': 'next_startup', 'execution_enabled': False})
        self.assertEqual(store.get('personal'), saved)
        self.assertEqual(store.get('dept')['revision'], 0)
        self.assertEqual(store.save('dept', 0, {'enabled_preference': False, 'daily_limit': 5})['revision'], 1)
        self.assertEqual(store.save('personal', 1, OFF)['revision'], 2)
        self.assertEqual(store.get('dept')['daily_limit'], 5)
        self.assertFalse(store.get('personal')['enabled_preference'])

    def test_stale_revision_conflicts_without_changing_row(self):
        store = self.store()
        store.save('personal', 0, ON)
        with self.assertRaises(ConflictError) as caught:
            store.save('personal', 0, {'enabled_preference': True, 'daily_limit': 9})
        self.assertEqual(caught.exception.code, 'conflict')
        with self.assertRaises(ConflictError):
            store.save('dept', 4, ON)
        self.assertEqual(store.get('personal')['daily_limit'], 3)
        self.assertEqual(store.get('dept')['revision'], 0)

    def test_concurrent_saves_allow_exactly_one_winner(self):
        store = self.store()
        barrier, results = threading.Barrier(2), []

        def worker(limit):
            mine = ProductionSettingsStore(self.root)
            mine.initialize()
            barrier.wait()
            try:
                results.append(mine.save('personal', 0, {'enabled_preference': True, 'daily_limit': limit}))
            except ConflictError as exc:
                results.append(exc)

        threads = [threading.Thread(target=worker, args=(n,)) for n in (1, 2)]
        for t in threads: t.start()
        for t in threads: t.join(15)
        self.assertEqual(len(results), 2)
        self.assertEqual(sum(isinstance(r, ConflictError) for r in results), 1)
        winner = next(r for r in results if isinstance(r, dict))
        self.assertEqual(store.get('personal'), winner)
        self.assertEqual(winner['revision'], 1)

    def test_restart_keeps_values_and_needs_new_initialize_to_write(self):
        self.store().save('dept', 0, ON)
        again = ProductionSettingsStore(self.root)
        self.assertEqual(again.get('dept')['daily_limit'], 3)
        with self.assertRaises(StoreError):
            again.save('dept', 1, OFF)
        again.initialize()
        self.assertEqual(again.get('dept')['daily_limit'], 3)
        self.assertEqual(again.save('dept', 1, OFF)['revision'], 2)

    def test_invalid_inputs_are_rejected_before_any_write(self):
        store = self.store()
        bad_payloads = [
            None, [], {}, {'enabled_preference': True}, {'daily_limit': 1},
            {'enabled_preference': True, 'daily_limit': 1, 'extra': 1},
            {'enabled_preference': 1, 'daily_limit': 1},
            {'enabled_preference': 'true', 'daily_limit': 1},
            {'enabled_preference': True, 'daily_limit': None},
            {'enabled_preference': False, 'daily_limit': 0},
            {'enabled_preference': False, 'daily_limit': -1},
            {'enabled_preference': False, 'daily_limit': True},
            {'enabled_preference': False, 'daily_limit': 1.0},
            {'enabled_preference': False, 'daily_limit': '3'},
            {'enabled_preference': False, 'daily_limit': 2147483648},
        ]
        for payload in bad_payloads:
            with self.subTest(payload=payload), self.assertRaises(StoreError) as caught:
                store.save('personal', 0, payload)
            self.assertEqual(caught.exception.code, 'invalid')
        for revision in (-1, True, 1.0, '0', None):
            with self.subTest(revision=revision), self.assertRaises(StoreError) as caught:
                store.save('personal', revision, ON)
            self.assertEqual(caught.exception.code, 'invalid')
        for account in ('other', '', None, 1, ['personal']):
            with self.subTest(account=account):
                with self.assertRaises(StoreError): store.get(account)
                with self.assertRaises(StoreError): store.save(account, 0, ON)
        self.assertEqual(store.save('personal', 0, {'enabled_preference': False, 'daily_limit': 2147483647})['daily_limit'], 2147483647)
        self.assertEqual(store.get('personal')['revision'], 1)

    def test_symlink_root_and_database_are_refused(self):
        real = self.tmp / 'real'
        real.mkdir()
        link_root = self.tmp / 'link'
        link_root.symlink_to(real, target_is_directory=True)
        linked = ProductionSettingsStore(link_root)
        for call in (lambda: linked.get('personal'), linked.initialize):
            with self.assertRaises(StoreError) as caught:
                call()
            self.assertEqual(caught.exception.code, 'storage_error')
        self.assertEqual(listing(real), [])

        self.root.mkdir()
        outside = self.tmp / 'outside.sqlite3'
        outside.write_bytes(b'')
        (self.root / DB_NAME).symlink_to(outside)
        store = ProductionSettingsStore(self.root)
        for call in (lambda: store.get('dept'), store.initialize):
            with self.assertRaises(StoreError) as caught:
                call()
            self.assertEqual(caught.exception.code, 'storage_error')
        self.assertEqual(outside.read_bytes(), b'')

    def test_saving_changes_only_the_settings_database(self):
        ops = self.root / 'operations.sqlite3'
        self.root.mkdir()
        ops.write_bytes(b'existing operations bytes')
        quota_marker = self.root / 'quota-buckets.marker'
        quota_marker.write_text('untouched')
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in (ops, quota_marker)}
        store = self.store()
        store.save('personal', 0, ON)
        store.save('dept', 0, ON)
        self.assertEqual(listing(self.root), sorted(['operations.sqlite3', 'quota-buckets.marker', DB_NAME]))
        after = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in (ops, quota_marker)}
        self.assertEqual(before, after)


    def test_foreign_database_is_not_adopted(self):
        import sqlite3
        self.root.mkdir(parents=True,exist_ok=True)
        path=self.root/'production-settings.sqlite3'
        with sqlite3.connect(path) as db:db.execute('CREATE TABLE foreign_data(value TEXT)')
        before=path.read_bytes()
        with self.assertRaises(StoreError):ProductionSettingsStore(self.root).initialize()
        self.assertEqual(before,path.read_bytes())


class CompilerTests(unittest.TestCase):
    def rows(self, personal=None, dept=None, **overrides):
        base = {'applies_to': 'next_startup', 'execution_enabled': False}
        make = lambda account, values: {**base, 'account_id': account, 'revision': 1 if values else 0,
            **(values or OFF)}
        rows = [make('personal', personal), make('dept', dept)]
        return [{**row, **overrides} for row in rows] if overrides else rows

    def compile(self, rows=None, **kwargs):
        return compile_production_settings(self.rows() if rows is None else rows, accounts=ACCOUNTS,
            code_root='/trusted/code', interpreter='/trusted/python', **kwargs)

    def test_defaults_compile_to_disabled_jobs_with_no_quota(self):
        result = self.compile()
        registry = result.registry
        self.assertEqual(set(registry.jobs), {'managed-text-personal', 'managed-text-dept'})
        for account in ('personal', 'dept'):
            job = registry.jobs['managed-text-' + account]
            self.assertIs(job['enabled'], False)
            self.assertEqual(job['kind'], 'production')
            self.assertEqual(job['owner_account_id'], account)
            self.assertEqual(job['executor_id'], 'managed-text-producer')
            self.assertEqual((job['execution_owner'], job['schedule_owner']), ('managed', 'console'))
            self.assertIs(job['subscription_only'], True)
            self.assertEqual(tuple(job['required_outputs']), ('text',))
            self.assertEqual(tuple(registry.policies[job['policy_revision']]['quota_requirements']), ())
        self.assertEqual(dict(registry.accounts), ACCOUNTS)
        for table in (registry.credentials, registry.profiles, registry.connections, registry.crossposts):
            self.assertEqual(len(table), 0)
        self.assertIs(result.policy.enabled, False)
        self.assertEqual(result.policy.allowed_connection_ids, ())
        self.assertIs(result.policy.provider_policy['subscription_only'], True)
        spec = result.catalog.executors['managed-text-producer']
        self.assertEqual((spec.interpreter, str(spec.cwd)), ('/trusted/python', '/trusted/code'))
        self.assertEqual(spec.module, 'common.operations.production_startup')
        self.assertEqual((spec.phases, spec.mutation_actions, spec.environment_names), (('prepare',), (), ()))
        self.assertEqual(set(spec.job_ids), set(registry.jobs))
        self.assertEqual(set(result.catalog.production_jobs), set(registry.jobs))
        self.assertEqual(set(result.catalog.callers), {'console'})
        self.assertEqual(result.catalog.callers['console']['source'], 'console')

    def test_activate_is_false_by_default_and_needs_an_enabled_account(self):
        rows = self.rows(personal=ON)
        self.assertIs(self.compile(rows).policy.enabled, False)
        self.assertIs(self.compile(rows, activate=True).policy.enabled, True)
        self.assertIs(self.compile(self.rows(), activate=True).policy.enabled, False)
        for bad in (1, 'yes', None):
            with self.subTest(activate=bad), self.assertRaises(ContractError):
                self.compile(rows, activate=bad)

    def test_personal_and_dept_are_compiled_independently(self):
        rows = self.rows(personal=ON, dept={'enabled_preference': False, 'daily_limit': 7})
        registry = self.compile(rows, activate=True).registry
        personal, dept = registry.jobs['managed-text-personal'], registry.jobs['managed-text-dept']
        self.assertIs(personal['enabled'], True)
        self.assertIs(dept['enabled'], False)
        (quota,) = registry.policies[personal['policy_revision']]['quota_requirements']
        self.assertEqual((quota['scope_kind'], quota['scope_id'], quota['metric']), ('owner', 'personal', 'managed_text_generations'))
        self.assertEqual((quota['window_kind'], quota['timezone'], quota['amount'], quota['limit']), ('day', 'Asia/Seoul', 1, 3))
        self.assertEqual(tuple(registry.policies[dept['policy_revision']]['quota_requirements']), ())
        self.assertNotEqual(personal['policy_revision'], dept['policy_revision'])

    def test_registry_revision_and_cutover_are_stable_and_meaningful(self):
        first = self.compile(self.rows(personal=ON))
        again = self.compile(list(reversed(self.rows(personal=ON))))
        self.assertEqual(first.registry.revision, again.registry.revision)
        self.assertEqual(first.policy.cutover_revision, again.policy.cutover_revision)
        self.assertEqual(first.registry.to_dict(), again.registry.to_dict())
        changed = self.compile(self.rows(personal={'enabled_preference': True, 'daily_limit': 4}))
        self.assertNotEqual(first.registry.revision, changed.registry.revision)
        self.assertNotEqual(self.compile().registry.revision, first.registry.revision)
        other = compile_production_settings(self.rows(personal=ON), accounts={**ACCOUNTS, 'extra': {}},
            code_root='/trusted/code', interpreter='/trusted/python')
        self.assertNotEqual(first.registry.revision, other.registry.revision)
        self.assertTrue(first.policy.cutover_revision)

    def test_unknown_missing_duplicate_and_malformed_rows_are_rejected(self):
        good = self.rows(personal=ON)
        stranger = dict(good[0], account_id='stranger')
        cases = {
            'unknown': [stranger, good[1]],
            'missing': [good[0]],
            'duplicate': [good[0], good[0]],
            'empty': [],
            'not_list': {'personal': good[0], 'dept': good[1]},
            'extra_key': [dict(good[0], extra=1), good[1]],
            'missing_key': [{k: v for k, v in good[0].items() if k != 'revision'}, good[1]],
            'negative_revision': [dict(good[0], revision=-1), good[1]],
            'bool_revision': [dict(good[0], revision=True), good[1]],
            'zero_limit': [dict(good[0], daily_limit=0), good[1]],
            'bool_limit': [dict(good[0], daily_limit=True), good[1]],
            'huge_limit': [dict(good[0], daily_limit=2147483648), good[1]],
            'enabled_without_limit': [dict(good[0], daily_limit=None), good[1]],
            'int_enabled': [dict(good[0], enabled_preference=1), good[1]],
            'executing': [dict(good[0], execution_enabled=True), good[1]],
            'applies_to': [dict(good[0], applies_to='now'), good[1]],
        }
        for name, rows in cases.items():
            with self.subTest(name), self.assertRaises(ContractError):
                self.compile(rows)

    def test_accounts_and_trusted_paths_are_validated(self):
        rows = self.rows()
        for accounts in ({'personal': {}}, {'dept': {}}, {}, None, [], {'personal': {}, 'dept': {}, 3: {}},
                         {'personal': {}, 'dept': {'bad': object()}}):
            with self.subTest(accounts=accounts), self.assertRaises(ContractError):
                compile_production_settings(rows, accounts=accounts, code_root='/c', interpreter='/p')
        for code_root, interpreter in (('relative', '/p'), ('/c', 'python'), (None, '/p'), ('/c', 3)):
            with self.subTest(code_root=code_root, interpreter=interpreter), self.assertRaises(ContractError):
                compile_production_settings(rows, accounts=ACCOUNTS, code_root=code_root, interpreter=interpreter)

    def test_compiler_is_pure_and_output_is_json_safe(self):
        import json
        from unittest import mock
        rows = self.rows(personal=ON)
        snapshot = json.dumps(rows, sort_keys=True)
        with mock.patch('builtins.open', side_effect=AssertionError('io')), \
             mock.patch('sqlite3.connect', side_effect=AssertionError('io')), \
             mock.patch.object(Path, 'exists', side_effect=AssertionError('io')):
            result = self.compile(rows, activate=True)
        self.assertEqual(json.dumps(rows, sort_keys=True), snapshot)
        json.dumps(result.registry.to_dict(), allow_nan=False)
        json.dumps(result.policy.to_dict(), allow_nan=False)
        with self.assertRaises(Exception):
            result.registry.jobs['managed-text-personal']['enabled'] = False


if __name__ == '__main__':
    unittest.main()
