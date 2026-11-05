"""전환 판정은 선언만으로 실발행 권한을 만들지 않는다."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from common.operations.models import thaw
from common.operations.registry import load_registry
from common.operations.runtime_store import RuntimeStore

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / 'docs/runbooks/execution-entrypoint-inventory.json'
CROSSPOSTS = ROOT / 'ax-console/config/crossposts.json'
FIXTURE = ROOT / 'tests/integration/fixtures/phase6a-crosspost-events.json'
CONNECTIONS = ('dept.blogger', 'personal.blogger', 'dept.naver_blog',
               'personal.naver_blog', 'personal.tistory', 'dept.youtube', 'personal.youtube')


def evidence():
    return dict(
        code_revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        test_results=[dict(command='python3 -m unittest tests.operations.test_cutover -v',
                           status='passed', total=1, failures=0, errors=0, skipped=0,
                           evidence_ref='test:offline-cutover')],
        connection_matrix={key: dict(implementation='passed', transport_fixture='passed',
            pure_prepare='passed', live_auth='not_run', live_publish='not_run',
            public_verify='not_run', content_verify='not_run', metrics='not_run',
            postprocessing='not_run') for key in CONNECTIONS},
        entrypoint_inventory_hash=hashlib.sha256(INVENTORY.read_bytes()).hexdigest(),
        crosspost_baseline_hash=hashlib.sha256(CROSSPOSTS.read_bytes()).hexdigest(),
        producer_policy_evidence=dict(status='passed', evidence_ref='test:producer-policy'),
        adapter_transport_evidence=dict(status='passed', evidence_ref='test:adapter-transport'),
        live_auth_evidence=[], live_publish_evidence=[],
        rollback_evidence=dict(strategy='forward_preserving_ledger', preserve_remote_ids=True,
            preserve_unknown=True, preserve_quota=True, resume_legacy=False,
            restore_test='not_run', evidence_ref='test:rollback-classification'))


class CutoverTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry(ROOT / 'ax-console/config/operations.json')
        self.inventory = json.loads(INVENTORY.read_text())
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = RuntimeStore(Path(self.temp.name) / 'no-db', self.registry)

    def assess(self, proof=None, *, registry=None, inventory=None, job_id='geoai.daily'):
        from common.operations.cutover import assess_cutover
        return assess_cutover(self.store, job_id, evidence() if proof is None else proof,
            registry=registry or self.registry, inventory=self.inventory if inventory is None else inventory)

    def test_offline_release_accepts_complete_local_proof_but_live_stays_false(self):
        from common.tools.check_operations_release import check_release
        result = check_release(evidence())
        self.assertTrue(result['offline_ready'])
        self.assertFalse(result['production_ready'])
        self.assertIn('production:live_auth_evidence_missing', result['blockers'])
        self.assertIn('production:live_publish_evidence_missing', result['blockers'])

    def test_empty_proof_is_not_ready(self):
        result = self.assess({})
        self.assertFalse(result['offline_ready'])
        self.assertFalse(result['production_ready'])

    def test_legacy_side_effects_block_even_when_evidence_claims_ready(self):
        proof = evidence()
        proof.update(production_ready=True, inventory_complete=True, legacy_side_effects=False)
        result = self.assess(proof)
        self.assertTrue(result['offline_ready'])
        self.assertFalse(result['production_ready'])
        self.assertIn('production:entrypoint_inventory_incomplete', result['blockers'])
        self.assertIn('production:legacy_execution_owner', result['blockers'])

    def test_inventory_caller_summary_cannot_hide_unfenced_leaf(self):
        inventory = copy.deepcopy(self.inventory)
        inventory['jobs']['geoai.daily'].update(managed_eligible=True, inventory_complete=True, pending_paths=[])
        result = self.assess(inventory=inventory)
        self.assertIn('production:entrypoint_inventory_incomplete', result['blockers'])
        self.assertFalse(result['production_ready'])

    def test_malformed_inventory_cannot_crash_or_enable_release(self):
        for value in (1, None, 'geoai.daily', [{}]):
            with self.subTest(job_ids=value):
                inventory = copy.deepcopy(self.inventory)
                inventory['jobs']['geoai.daily'].update(managed_eligible=True, inventory_complete=True, pending_paths=[])
                inventory['entrypoints'][0]['job_ids'] = value
                result = self.assess(inventory=inventory)
                self.assertFalse(result['offline_ready'])
                self.assertFalse(result['production_ready'])
                self.assertIn('production:entrypoint_inventory_incomplete', result['blockers'])

    def test_missing_inventory_fails_closed(self):
        result = self.assess(inventory={})
        self.assertFalse(result['offline_ready'])
        self.assertIn('production:entrypoint_inventory_incomplete', result['blockers'])

    def test_wrong_hash_cannot_replace_server_baseline(self):
        proof = evidence()
        for field in ('entrypoint_inventory_hash', 'crosspost_baseline_hash'):
            with self.subTest(field=field):
                bad = dict(proof, **{field: '0' * 64})
                self.assertFalse(self.assess(bad)['offline_ready'])

    def test_failed_skipped_empty_and_malformed_tests_are_not_ready(self):
        for change in ({'failures': 1}, {'skipped': 1}, {'errors': 1}, {'total': 0},
                       {'total': True}, {'status': 'not_run'}, {'evidence_ref': ''}):
            with self.subTest(change=change):
                proof = evidence()
                proof['test_results'][0].update(change)
                self.assertFalse(self.assess(proof)['offline_ready'])

    def test_seven_connection_support_columns_must_be_distinct(self):
        proof = evidence()
        proof['connection_matrix'].pop('personal.youtube')
        self.assertFalse(self.assess(proof)['offline_ready'])
        proof = evidence()
        proof['connection_matrix']['dept.youtube'].pop('content_verify')
        self.assertFalse(self.assess(proof)['offline_ready'])

    def test_fixture_url_id_and_self_attested_trust_never_become_live_evidence(self):
        for remote in ('fixture-video', 'https://example.com/post/1', 'test_id', 'https://www.youtube.com/watch?v=fixture123'):
            with self.subTest(remote=remote):
                proof = evidence()
                proof['live_auth_evidence'] = [dict(target_id=remote, trusted=True, status='passed')]
                proof['live_publish_evidence'] = [dict(remote_id=remote, trusted=True, status='verified')]
                result = self.assess(proof)
                self.assertFalse(result['production_ready'])
                self.assertIn('production:fixture_live_evidence', result['blockers'])

    def test_real_looking_remote_values_are_not_server_corroboration(self):
        proof = evidence()
        proof['live_auth_evidence'] = [dict(target_id='UC12345678901234567890', trusted=True)]
        proof['live_publish_evidence'] = [dict(remote_id='aBcDeFg1234', url='https://youtube.com/watch?v=aBcDeFg1234')]
        self.assertIn('production:live_ledger_verification_pending', self.assess(proof)['blockers'])

    def test_rollback_cannot_discard_new_remote_unknown_or_quota(self):
        for key, value in [('preserve_remote_ids', False), ('preserve_unknown', False),
                           ('preserve_quota', False), ('resume_legacy', True), ('strategy', 'restore_old_db')]:
            with self.subTest(key=key):
                proof = evidence()
                proof['rollback_evidence'][key] = value
                result = self.assess(proof)
                self.assertFalse(result['offline_ready'])
                self.assertIn('offline:unsafe_rollback', result['blockers'])

    def test_assessment_does_not_initialize_or_write_store(self):
        root = self.store.root
        self.assertFalse(root.exists())
        self.assess()
        self.assertFalse(root.exists())

    def test_existing_runtime_ledger_is_unchanged(self):
        self.store.initialize()
        self.store.observe_bucket('retained-quota', 100, 7, '2026-10-30T00:00:00+00:00', '2026-10-31T00:00:00+00:00')
        before = {str(p): p.read_bytes() for p in self.store.root.rglob('*') if p.is_file()}
        self.assess()
        after = {str(p): p.read_bytes() for p in self.store.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_unknown_job_and_non_mapping_input_fail_closed(self):
        self.assertFalse(self.assess(job_id='missing.job')['production_ready'])
        self.assertFalse(self.assess([])['offline_ready'])

    def test_release_mode_validates_and_cli_does_not_echo_secrets(self):
        from common.tools.check_operations_release import check_release
        self.assertFalse(check_release(evidence(), mode='invalid')['offline_ready'])
        proof = evidence()
        proof['secret'] = 'never-echo-this-secret'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'evidence.json'
            path.write_text(json.dumps(proof))
            output = subprocess.run(['python3', '-m', 'common.tools.check_operations_release',
                '--evidence', str(path), '--mode', 'offline'], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(0, output.returncode, output.stderr)
        self.assertTrue(json.loads(output.stdout)['offline_ready'])
        self.assertNotIn('never-echo-this-secret', output.stdout + output.stderr)


class CrosspostFixtureTests(unittest.TestCase):
    def test_all_23_rules_and_disabled_unknown_preserved(self):
        from common.operations.crossposts import preview_crossposts, crosspost_intents
        fixture = json.loads(FIXTURE.read_text())
        registry = load_registry(ROOT / 'ax-console/config/operations.json')
        self.assertEqual(23, len(fixture['rules']))
        self.assertEqual(fixture['rules'], list(thaw(registry.crossposts).values()))
        seen = set()
        for case in fixture['events']:
            with self.subTest(case=case['id']):
                rows = preview_crossposts(case['event'], registry)
                found = {row['rule_id']: row for row in rows if row['eligible']}
                self.assertEqual(set(case['expected_eligible_rules']), set(found))
                self.assertEqual((), crosspost_intents(case['event'], registry))
                for rule_id, status in case['expected_statuses'].items():
                    self.assertEqual(status, next(row for row in rows if row['rule_id'] == rule_id)['status'])
                seen.update(found)
                self.assertTrue(all(row['execution_enabled'] is False for row in rows))
        self.assertEqual(set(registry.crossposts), seen)
        self.assertFalse(registry.crossposts['news.tiktok']['enabled'])
        self.assertEqual(17, sum(rule.get('enabled') is None for rule in fixture['rules']))

    def test_tiktok_time_boundaries_and_delay_responsibility(self):
        from common.operations.crossposts import earliest_post_time
        fixture = json.loads(FIXTURE.read_text())
        rules = {rule['id']: rule for rule in fixture['rules']}
        for case in fixture['tiktok_time_cases']:
            with self.subTest(case=case['id']):
                rule = dict(rules[case['rule_id']], **case.get('rule_overrides', {}))
                result = earliest_post_time(rule, case['source_public_at'], case.get('last_destination_post_at'))
                self.assertEqual(case['expected_not_before'], result.isoformat())
