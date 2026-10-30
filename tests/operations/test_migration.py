"""정적 이행 보고서의 읽기·쓰기 경계 회귀 시험."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class MigrationTests(unittest.TestCase):
    def api(self):
        for name in ('common.operations.layout', 'common.operations.environment_manifest',
                     'common.tools.audit_account_paths'):
            self.assertIsNotNone(importlib.util.find_spec(name), name + ' 구현 필요')
        from common.operations import layout, environment_manifest
        from common.tools import audit_account_paths
        return layout, environment_manifest, audit_account_paths

    def test_unknown_accounts_and_relative_root_are_rejected(self):
        layout, _, _ = self.api()
        for account in ('', None, 'unknown', '../personal', 'DEPT'):
            with self.subTest(account=account), self.assertRaises(ValueError):
                layout.resolve_layout(account, '/managed')
        with self.assertRaises(ValueError):
            layout.resolve_layout('personal', 'relative')

    def test_personal_layout_is_cwd_independent_and_pure(self):
        layout, _, _ = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            old = os.getcwd()
            try:
                os.chdir(tmp)
                one = layout.resolve_layout('personal', '/managed')
                os.chdir('/')
                two = layout.resolve_layout('personal', '/managed')
            finally:
                os.chdir(old)
        self.assertEqual(one, two)
        self.assertEqual(one['content_root'], '/managed/personal/content')
        self.assertEqual(one['proposed_paths']['blog_auto'], '/managed/personal/blog-auto')
        self.assertEqual(one['proposed_paths']['shorts_auto'], '/managed/personal/shorts-auto')
        self.assertNotIn('dept', json.dumps(one))

    def test_alias_removal_requires_zero_callers_and_explicit_observation(self):
        layout, _, _ = self.api()
        alias = {'name': 'shared', 'status': 'resolved', 'observation_confirmed': True,
                 'caller_inventory_complete': True}
        self.assertFalse(layout.can_remove_alias(alias, ['caller.py']))
        self.assertTrue(layout.can_remove_alias(alias, []))
        for key in ('observation_confirmed', 'caller_inventory_complete'):
            self.assertFalse(layout.can_remove_alias({**alias, key: False}, []))
        self.assertFalse(layout.can_remove_alias({**alias, 'status': 'cycle'}, []))

    def fixture(self, root):
        code = root / 'dept/naver-blog-auto/geoai_daily.py'
        code.parent.mkdir(parents=True)
        code.write_text('import os\nBASE = "channels/youtube-shorts-auto"\n'
                        'key = os.getenv("PRIVATE_KEY", "do-not-copy")\n')
        secret = root / 'dept/naver-blog-auto/config.json'
        secret.write_text('SECRET-NEVER-READ')
        (root / 'common').mkdir()
        (root / 'common/shared').mkdir()
        (root / 'shared').symlink_to('common/shared')
        (root / 'personal').mkdir()
        (root / 'channels').mkdir()
        (root / 'dept/youtube-shorts-auto').mkdir()
        (root / 'channels/youtube-shorts-auto').symlink_to('../dept/youtube-shorts-auto')
        (root / 'personal/youtube-shorts-auto').symlink_to('../channels/youtube-shorts-auto')
        return code, secret

    def test_inventory_never_reads_secrets_follows_links_or_calls_external_services(self):
        _, env, audit = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / 'source'
            root.mkdir()
            code, secret = self.fixture(root)
            before = {str(p): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
                      for p in (code, secret)}
            files_before = sorted(str(p.relative_to(root)) for p in root.rglob('*'))
            real_open = os.open
            def guarded_open(path, flags, *args, **kwargs):
                self.assertNotEqual(Path(path), secret)
                return real_open(path, flags, *args, **kwargs)
            with patch('os.open', side_effect=guarded_open), \
                 patch('subprocess.Popen', side_effect=AssertionError('subprocess 금지')), \
                 patch('socket.socket', side_effect=AssertionError('network 금지')):
                inventory = audit.audit_inventory(root, code_root=root, workspace_root=Path(tmp).resolve() / 'managed')
                manifest = env.build_environment_manifest(inventory)
            after = {str(p): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
                     for p in (code, secret)}
            self.assertEqual(before, after)
            self.assertEqual(files_before, sorted(str(p.relative_to(root)) for p in root.rglob('*')))
            self.assertEqual(len(inventory['files']), 1)
            self.assertEqual(inventory['files'][0]['hash'], before[str(code)][0])
            self.assertNotIn('SECRET-NEVER-READ', json.dumps(inventory))
            self.assertNotIn('do-not-copy', json.dumps(manifest))
            self.assertIn('PRIVATE_KEY', json.dumps(manifest))
            personal_env = next(e for e in manifest['environments'] if e['id'].endswith('geoai_daily.py'))
            self.assertEqual(personal_env['profile_ref'], 'profile:acct-personal')
            self.assertEqual(personal_env['credential_ref'], 'credential:personal:legacy-unverified')
            aliases = {a['name']: a for a in inventory['aliases']}
            self.assertEqual(aliases['personal/youtube-shorts-auto']['status'], 'resolved')
            self.assertEqual(aliases['personal/youtube-shorts-auto']['canonical_path'],
                             str(root / 'dept/youtube-shorts-auto'))

    def test_nested_cyclic_dangling_external_aliases_are_observations(self):
        _, _, audit = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / 'shared').symlink_to('assets')
            (root / 'assets').symlink_to('shared')
            (root / 'analytics').symlink_to('/outside/private')
            (root / 'tools').symlink_to('missing')
            rows = {a['name']: a for a in audit.audit_inventory(root, code_root=root)['aliases']}
            self.assertEqual(rows['shared']['status'], 'cycle')
            self.assertEqual(rows['analytics']['status'], 'external')
            self.assertEqual(rows['tools']['status'], 'dangling')

    def test_cli_output_rejects_source_code_alias_and_existing_files(self):
        _, _, audit = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = base / 'source'
            root.mkdir()
            code = base / 'code'
            code.mkdir()
            self.fixture(root)
            (base / 'redirect').symlink_to(root, target_is_directory=True)
            for target in (root / 'new.json', code / 'new.json', base / 'redirect/new.json'):
                with self.subTest(target=target), self.assertRaises(ValueError):
                    audit.main(['--root', str(root), '--code-root', str(code), '--output', str(target)])
                self.assertFalse(target.exists())
            output = base / 'report.json'
            self.assertEqual(audit.main(['--root', str(root), '--code-root', str(code),
                                        '--output', str(output)]), 0)
            result = json.loads(output.read_text())
            self.assertFalse(result['physical_migration_ready'])
            with self.assertRaises(FileExistsError):
                audit.main(['--root', str(root), '--code-root', str(code), '--output', str(output)])

    def test_no_t10_t12_evidence_can_enable_physical_migration(self):
        layout, _, _ = self.api()
        baseline = {'source_root': '/source', 'code_root': '/code', 'workspace_root': '/managed',
                    'files': [], 'aliases': [], 'environments': [],
                    'prerequisites': {'T10': True, 'T11': True, 'T12': True}}
        report = layout.build_path_migration(baseline)
        self.assertFalse(report['physical_migration_ready'])
        self.assertTrue(report['blockers'])
        self.assertEqual(report['ledger_policy'], 'shared')
        self.assertTrue(report['preserve_original_ids'])
        self.assertTrue(report['preserve_original_paths'])
        self.assertIn('/source/personal/blog-auto', json.dumps(report))
        self.assertIn('/source/personal/shorts-auto', json.dumps(report))
        with self.assertRaises(ValueError):
            layout.build_path_migration({**baseline, 'workspace_root': '/source/managed'})

    def test_symlinked_code_parent_is_not_read(self):
        _, _, audit = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            root = base / 'source'
            root.mkdir()
            outside = base / 'outside'
            self.fixture(outside)
            (root / 'dept').symlink_to(outside / 'dept', target_is_directory=True)
            inventory = audit.audit_inventory(root, code_root=root)
            self.assertEqual(inventory['files'], [])

    def test_environment_manifest_keeps_names_and_symbolic_refs_only(self):
        _, env, _ = self.api()
        result = env.build_environment_manifest({'environments': [{
            'id': 'entry', 'interpreter': '/source/.venv/bin/python', 'cwd': '/source',
            'entrypoint': '/source/job.py', 'profile_ref': 'profile:personal',
            'credential_ref': 'credential:personal', 'environment_variable_names': ['API_KEY'],
            'environment': {'API_KEY': 'secret-value'}, 'credential': {'token': 'secret-token'}}]})
        self.assertNotIn('secret-value', json.dumps(result))
        self.assertNotIn('secret-token', json.dumps(result))
        self.assertEqual(result['environments'][0]['environment_variable_names'], ['API_KEY'])

    def test_workspace_symlink_cannot_hide_source_overlap(self):
        _, _, audit = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            source = base / 'source'
            source.mkdir()
            workspace = base / 'managed'
            workspace.symlink_to(source, target_is_directory=True)
            with self.assertRaises(ValueError):
                audit.audit_inventory(source, code_root=source, workspace_root=workspace / 'new')

    def test_missing_prerequisites_remain_blocked_and_bad_source_path_is_rejected(self):
        layout, _, _ = self.api()
        base = {'source_root': '/source', 'code_root': '/code', 'files': [], 'aliases': []}
        result = layout.build_path_migration(base)
        self.assertFalse(result['physical_migration_ready'])
        self.assertTrue(all(any(task in blocker for blocker in result['blockers'])
                            for task in ('T10', 'T11', 'T12')))
        for path in ('../escape.py', '/absolute.py'):
            with self.assertRaises(ValueError):
                layout.build_path_migration({**base, 'files': [{'path': path}]})

    def test_finite_alias_revisit_is_not_a_cycle(self):
        _, _, audit = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / 'assets').symlink_to('.')
            (root / 'shared').symlink_to('assets/assets')
            row = next(a for a in audit.audit_inventory(root, code_root=root)['aliases'] if a['name'] == 'shared')
            self.assertEqual(row['status'], 'resolved')
            self.assertEqual(row['canonical_path'], str(root))

    def test_alias_resolution_limit_is_distinct_from_a_cycle(self):
        _, _, audit = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / 'assets').symlink_to('.')
            (root / 'shared').symlink_to('/'.join(['assets'] * 45))
            row = next(a for a in audit.audit_inventory(root, code_root=root)['aliases'] if a['name'] == 'shared')
            self.assertEqual(row['status'], 'resolution_limit')

    def test_manifest_rejects_objects_and_arbitrary_values_in_callers(self):
        _, env, _ = self.api()
        result = env.build_environment_manifest({'environments': [{'id': 'job', 'callers': [
            {'credential': 'SYNTHETIC-MARKER'}, ['NESTED-MARKER'], 'API_KEY=value',
            '../escape.py', 'not-a-path', '/secret/token.json', 'dept/job.py', 'run.sh']}]})
        self.assertEqual(result['environments'][0]['callers'], ['dept/job.py', 'run.sh'])
        self.assertNotIn('MARKER', json.dumps(result))
        for malformed in (None, {'credential': 'MARKER'}, 'run.sh'):
            row = env.build_environment_manifest({'environments': [{'callers': malformed}]})['environments'][0]
            self.assertEqual(row['callers'], [])
            self.assertEqual(row['callers_observation']['status'], 'unknown')

    def test_direct_shell_import_alias_and_environment_relations_are_connected(self):
        layout, _, audit = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            daily, _ = self.fixture(root)
            wrapper = daily.parent / 'run_geoai.sh'
            wrapper.write_text('#!/bin/bash\ncd "$(dirname "$0")" || exit 1\n'
                               'exec ./.venv/bin/python geoai_daily.py --go\n'
                               'python3 ../../shared/paths.py\n')
            daily.write_text('import geoai_assets\n')
            (daily.parent / 'geoai_assets.py').write_text('VALUE = 1\n')
            (root / 'common/shared/paths.py').write_text('VALUE = 2\n')
            inv = audit.audit_inventory(root, code_root=root)
            files = {f['path']: f for f in inv['files']}
            wrapper_path = 'dept/naver-blog-auto/run_geoai.sh'
            daily_path = 'dept/naver-blog-auto/geoai_daily.py'
            self.assertIn(wrapper_path, files[daily_path]['callers'])
            self.assertIn(daily_path, files['dept/naver-blog-auto/geoai_assets.py']['callers'])
            self.assertIn(wrapper_path, files['common/shared/paths.py']['callers'])
            self.assertIn('shared', files['common/shared/paths.py']['alias'])
            self.assertIn(wrapper_path, files[daily_path]['environment_ref'])
            self.assertEqual(files[daily_path]['callers_observation']['status'], 'partial')
            self.assertEqual(files[wrapper_path]['callers_observation']['status'], 'observed_zero_in_scope')
            env = {e['id']: e for e in inv['environment_manifest']['environments']}
            self.assertIn(wrapper_path, env[daily_path]['callers'])
            self.assertEqual(env[daily_path]['callers_observation']['status'], 'partial')
            row = next(r for r in layout.build_path_migration(inv)['entries'] if r['original_path'] == daily_path)
            self.assertEqual(row['callers_observation'], files[daily_path]['callers_observation'])
            self.assertTrue(any(e['kind'] == 'python_import' for e in inv['direct_relations']))
            edge = next(e for e in inv['direct_relations'] if e['callee'] == 'common/shared/paths.py')
            self.assertEqual(edge.get('via_alias'), ['shared'])
            alias = next(a for a in inv['aliases'] if a['name'] == 'shared')
            self.assertIn(wrapper_path, alias['callers'])

    def test_unparsed_cwd_does_not_claim_observed_zero(self):
        layout, _, audit = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            daily, _ = self.fixture(root)
            (daily.parent / 'run_geoai.sh').write_text('cd "$DYNAMIC_CWD"\npython geoai_daily.py\n')
            inv = audit.audit_inventory(root, code_root=root)
            file = next(f for f in inv['files'] if f['path'].endswith('geoai_daily.py'))
            self.assertEqual(file['callers'], [])
            self.assertEqual(file['callers_observation']['status'], 'unknown')
            self.assertFalse(file['callers_observation']['complete'])
            row = next(r for r in layout.build_path_migration(inv)['entries'] if r['original_path'] == file['path'])
            self.assertEqual(row['callers_observation']['status'], 'unknown')

    def test_shell_changed_subdirectory_is_not_treated_as_script_directory(self):
        _, _, audit = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            daily, _ = self.fixture(root)
            (daily.parent / 'run_geoai.sh').write_text('cd "$(dirname "$0")/other"\npython geoai_daily.py\n')
            inv = audit.audit_inventory(root, code_root=root)
            row = next(f for f in inv['files'] if f['path'].endswith('geoai_daily.py'))
            self.assertEqual(row['callers'], [])
            self.assertEqual(row['callers_observation']['status'], 'unknown')


if __name__ == '__main__':
    unittest.main()
