"""명시 recovery의 실제 SQLite/owned-envelope 경계. 실 native 호출은 없다."""
from contextlib import closing
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import importlib
import io
import json
from pathlib import Path
import sqlite3
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from common.operations.content_store import StoreError
from common.operations.credential_backend import CredentialError
from common.operations.oauth_models import AttemptContext, CredentialRef
from common.operations.oauth_stage_backend import MemoryScopedRawBackend, OwnedStageBackend, scoped_address
from common.operations.oauth_stage_models import OwnedCredentialRef
from common.operations.oauth_stage_store import OAuthStageStore, migrate_to_owned_schema
from common.operations.oauth_store import OAuthAttemptStore, OAuthDatabase
from common.operations.oauth_workspace import (OWNER_MARKER_NAME, OAuthWorkspaceContext,
    initialize_workspace_owner, oauth_write_guard, load_workspace_owner)


class CountingRaw(MemoryScopedRawBackend):
    def __init__(self):
        super().__init__(); self.reads = 0; self.deletes = 0
        self.read_fault = None; self.delete_fault = None; self.after_read = None

    def copy(self, address):
        self.reads += 1
        if self.read_fault:
            raise CredentialError(self.read_fault)
        result = super().copy(address)
        if self.after_read:
            action, self.after_read = self.after_read, None
            action()
        return result

    def delete(self, address):
        self.deletes += 1
        if self.delete_fault:
            raise CredentialError(self.delete_fault)
        super().delete(address)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.context = initialize_workspace_owner(self.root)
        OAuthDatabase(self.root).initialize()
        with oauth_write_guard(self.context):
            migrate_to_owned_schema(self.context)
        self.journal = OAuthStageStore(self.context)
        self.raw = CountingRaw(); self.backend = OwnedStageBackend(self.context, self.raw)

    def api(self):
        try:
            return importlib.import_module('common.operations.oauth_recovery')
        except ModuleNotFoundError:
            self.fail('explicit recovery module is required')

    def stage(self, name='stage-one', *, state='stored', outcome='unused', remote=False):
        ref = OwnedCredentialRef(CredentialRef('autosns.oauth', 'personal', 'youtube', 'conn', 1, 'token'),
                                 self.context.owner.workspace_id, self.context.owner.root_binding, name)
        with oauth_write_guard(self.context):
            op = self.journal.begin_operation('refresh' if remote else 'callback', local_only=not remote)
            stage = self.journal.begin_stage(self.context.owner, ref, op.operation_id, 0)
            if state != 'absent':
                self.backend.put_owned(ref, b'private-payload')
            if state in ('stored', 'referenced'):
                stage = self.journal.mark_stored(stage.stage_id, stage.revision)
            if state == 'referenced':
                graph = self.snapshot()
                stage = self.journal.mark_referenced(stage.stage_id, stage.revision, graph.graph_revision)
            if outcome == 'unknown':
                self.journal.mark_operation_unknown(op.operation_id, op.revision)
            elif outcome != 'pending':
                self.journal.finish_operation(op.operation_id, op.revision, outcome)
        return stage

    def snapshot(self):
        return self.journal.recovery_snapshot(self.context.owner)

    def inspect(self, **kw):
        return self.api().inspect_recovery(self.context, self.journal, self.backend,
            expected_workspace_id=self.context.owner.workspace_id, **kw)

    def cleanup(self, **kw):
        snap = self.snapshot()
        args = dict(expected_workspace_id=self.context.owner.workspace_id,
                    expected_journal_revision=snap.journal_revision, expected_graph_revision=snap.graph_revision)
        args.update(kw)
        return self.api().cleanup_recovery(self.context, self.journal, self.backend, **args)

    def dump(self):
        with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db:
            return '\n'.join(db.iterdump())

    def protect(self, ref):
        now = datetime.now(timezone.utc)
        attempts = OAuthAttemptStore(self.root)
        context = AttemptContext('user', 'binding', 'personal', 'youtube', 'conn', 'base', 0,
                                 ('read',), 'https://test/cb', 'client', 1, 'evidence')
        with oauth_write_guard(self.context):
            attempt = attempts.create_attempt(context, 'a'*64, now+timedelta(minutes=5))
            # Set up the persisted pre-exchange boundary; the pointer write itself
            # uses the real writer and its atomic journal-reference hook.
            with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db, db:
                db.execute("UPDATE oauth_attempts SET state='resume_pending' WHERE id=?", (attempt['attempt_id'],))
            return attempts.update_attempt(attempt['attempt_id'], 'binding', attempt['revision'],
                                           'token_exchanged', {'token_ref': ref})

    def test_exact_unused_stage_is_deleted_and_second_cleanup_is_write_free(self):
        self.stage(); report = self.cleanup()
        self.assertEqual(('cleaned', 1, 0), (report.status, report.deleted_count, report.absent_count))
        self.assertEqual('deleted', self.snapshot().stages[0].state)
        before = self.dump(); calls = (self.raw.reads, self.raw.deletes)
        again = self.cleanup()
        self.assertEqual((0, 1), (again.deleted_count, again.already_deleted_count))
        self.assertEqual(before, self.dump()); self.assertEqual(calls, (self.raw.reads, self.raw.deletes))

    def test_inspect_reads_proof_but_preserves_database_and_vault(self):
        self.stage(); before = self.dump(); vault = dict(self.raw._items)
        report = self.inspect()
        self.assertEqual(('inspected', 1, 0), (report.status, report.candidate_count, report.deleted_count))
        self.assertEqual(before, self.dump()); self.assertEqual(vault, self.raw._items)
        self.assertEqual((1, 0), (self.raw.reads, self.raw.deletes))

    def test_each_stale_or_invalid_revision_blocks_before_backend(self):
        self.stage(); before = self.dump(); snap = self.snapshot()
        for args in ({'expected_journal_revision': snap.journal_revision-1},
                     {'expected_graph_revision': snap.graph_revision-1},
                     {'expected_journal_revision': True}, {'expected_graph_revision': -1}):
            with self.subTest(args=args):
                report = self.cleanup(**args)
                self.assertEqual('blocked', report.status)
        self.assertEqual((0, 0), (self.raw.reads, self.raw.deletes)); self.assertEqual(before, self.dump())

    def test_snapshot_blocker_aborts_all_before_candidate_reads(self):
        self.stage()
        with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db, db:
            db.execute('CREATE TABLE oauth_future(secret TEXT)')
        before = self.dump(); report = self.cleanup()
        self.assertEqual('blocked', report.status)
        self.assertEqual((0, 0), (self.raw.reads, self.raw.deletes)); self.assertEqual(before, self.dump())

    def test_snapshot_store_error_is_sanitized_and_aborts_before_backend(self):
        self.stage(); before = self.dump()
        api = self.api(); snap = self.snapshot()
        with patch.object(self.journal, 'recovery_snapshot', side_effect=StoreError('/private/token-secret')):
            report = api.cleanup_recovery(self.context, self.journal, self.backend,
                expected_workspace_id=self.context.owner.workspace_id,
                expected_journal_revision=snap.journal_revision, expected_graph_revision=snap.graph_revision)
        self.assertEqual('blocked', report.status)
        self.assertNotIn('token-secret', json.dumps(report.to_dict()))
        self.assertEqual((0, 0), (self.raw.reads, self.raw.deletes)); self.assertEqual(before, self.dump())

    def test_unknown_pending_and_historical_referenced_stages_are_never_read(self):
        self.stage('unknown', outcome='unknown', remote=True)
        self.stage('pending', outcome='pending')
        self.stage('history', state='referenced')
        before = self.dump(); report = self.cleanup()
        self.assertEqual((0, 3, 0), (report.candidate_count, report.preserved_count, report.deleted_count))
        self.assertEqual((0, 0), (self.raw.reads, self.raw.deletes)); self.assertEqual(before, self.dump())

    def test_absent_intent_is_finalized_without_claiming_a_deletion(self):
        self.stage(state='absent'); report = self.cleanup()
        self.assertEqual((0, 1, 0), (report.deleted_count, report.absent_count, self.raw.deletes))
        self.assertEqual('deleted', self.snapshot().stages[0].state)
        self.assertIn('absent', dict(report.reason_counts))

    def test_intent_after_successful_put_can_be_reclaimed(self):
        self.stage(state='intent'); report = self.cleanup()
        self.assertEqual(1, report.deleted_count)

    def test_multiple_candidates_use_revisions_after_own_writes(self):
        self.stage('first'); self.stage('second'); report = self.cleanup()
        self.assertEqual((2, 0), (report.deleted_count, report.preserved_count))
        self.assertEqual({'deleted'}, {stage.state for stage in self.snapshot().stages})

    def test_report_is_immutable_and_does_not_expose_identity_or_payload(self):
        stage = self.stage(); report = self.inspect()
        with self.assertRaises(FrozenInstanceError):
            report.status = 'cleaned'
        text = json.dumps(report.to_dict()) + repr(report)
        for secret in (str(self.root), stage.stage_id, self.context.owner.workspace_id,
                       self.context.key_provider.get_key().hex(), 'private-payload', 'autosns.oauth'):
            self.assertNotIn(secret, text)

    def test_historical_direct_ref_and_legacy_ref_remain_protected_without_reads(self):
        stage = self.stage(); self.protect(stage.owned_ref)
        report = self.cleanup()
        self.assertEqual((0, 1, 0), (report.deleted_count, report.preserved_count, self.raw.reads))
        # A distinct legacy attempt also contributes protection without vault reads.
        legacy = CredentialRef('autosns.oauth', 'personal', 'youtube', 'conn', 2, 'token')
        with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db, db:
            db.execute("UPDATE oauth_attempts SET state='expired', payload=?", (json.dumps({'token_ref': {
                'namespace': legacy.namespace, 'account_id': legacy.account_id, 'platform': legacy.platform,
                'connection_id': legacy.connection_id, 'generation': 2, 'kind': 'token'}}),))
        report = self.cleanup()
        self.assertEqual((0, 1, 0), (report.deleted_count, report.legacy_protected_count, self.raw.reads))

    def test_each_native_failure_preserves_and_retry_is_event_idempotent(self):
        for step in ('read_fault', 'delete_fault'):
            for code, reason in (('credential_denied', 'denied'), ('credential_locked', 'locked'),
                                 ('credential_unavailable', 'unavailable')):
                with self.subTest(step=step, code=code):
                    stage = self.stage(step+reason)
                    original = self.raw._items[scoped_address(stage.owned_ref)]
                    setattr(self.raw, step, code)
                    report = self.cleanup()
                    self.assertEqual(('partial', 0, 0), (report.status, report.deleted_count, report.absent_count))
                    self.assertGreater(dict(report.reason_counts)[reason], 0)
                    before = self.dump(); self.cleanup(); self.assertEqual(before, self.dump())
                    self.assertEqual(original, MemoryScopedRawBackend.copy(self.raw, scoped_address(stage.owned_ref)))
                    setattr(self.raw, step, None)
                    self.cleanup()

    def test_recovery_event_changes_only_journal_revision(self):
        self.stage(); before = self.snapshot()
        self.raw.read_fault = 'credential_denied'
        report = self.cleanup(); after = self.snapshot()
        self.assertEqual(before.graph_revision, after.graph_revision)
        self.assertEqual(before.journal_revision+1, after.journal_revision)
        self.assertEqual({'denied': 1}, dict(report.reason_counts))

    def test_delete_not_found_is_absent_and_never_counted_as_deleted(self):
        self.stage()

        def remove_then_not_found(address):
            MemoryScopedRawBackend.delete(self.raw, address)
            raise CredentialError('credential_not_found')

        with patch.object(self.raw, 'delete', side_effect=remove_then_not_found):
            report = self.cleanup()
        self.assertEqual(('cleaned', 0, 1), (report.status, report.deleted_count, report.absent_count))
        self.assertFalse(self.raw._items)

    def test_unexpected_backend_exception_is_fixed_unavailable_without_details(self):
        self.stage()
        with patch.object(self.raw, 'copy', side_effect=RuntimeError('/private/raw-token-sentinel')):
            report = self.cleanup()
        self.assertEqual(('partial', 0, 0), (report.status, report.deleted_count, report.absent_count))
        self.assertEqual({'unavailable': 1}, dict(report.reason_counts))
        self.assertNotIn('sentinel', json.dumps(report.to_dict()))

    def test_unowned_or_corrupt_envelope_is_never_deleted(self):
        for name, transform in (('legacy', lambda _: b'legacy-raw-token'),
                                ('tag', lambda value: value[:-1]+bytes([value[-1]^1]))):
            with self.subTest(name=name):
                stage = self.stage(name)
                address = scoped_address(stage.owned_ref)
                original = self.raw._items[address]
                self.raw._items[address] = transform(original)
                calls = self.raw.deletes
                report = self.cleanup()
                self.assertEqual((0, 0), (report.deleted_count, report.absent_count))
                self.assertGreater(dict(report.reason_counts)['integrity_failed'], 0)
                self.assertEqual(calls, self.raw.deletes)
                self.assertIn(address, self.raw._items)

    def test_new_direct_ref_after_proof_aborts_without_raw_delete(self):
        stage = self.stage()
        original = self.raw._items[scoped_address(stage.owned_ref)]
        self.raw.after_read = lambda: self.protect(stage.owned_ref)
        report = self.cleanup()
        self.assertEqual(('partial', 0), (report.status, report.deleted_count))
        self.assertEqual(0, self.raw.deletes)
        self.assertEqual(original, MemoryScopedRawBackend.copy(self.raw, scoped_address(stage.owned_ref)))

    def test_existing_delete_intent_does_not_authorize_new_protected_ref(self):
        stage = self.stage()
        with oauth_write_guard(self.context):
            self.journal.record_recovery_event(stage.stage_id, stage.revision, 'delete_intent')
        self.protect(stage.owned_ref)
        before = self.dump(); report = self.cleanup()
        self.assertEqual((0, 0), (report.candidate_count, self.raw.reads))
        self.assertEqual(before, self.dump())

    def test_pending_receipt_protects_terminal_unused_operation_stage(self):
        stage = self.stage(remote=True, outcome='pending')
        with oauth_write_guard(self.context):
            receipt = self.journal.claim_request('binding', 'refresh', 'request', 'f'*64)
            self.journal.bind_operation('receipt', receipt['id'], stage.operation_id, receipt['revision'])
            operation = self.journal.read_operation(stage.operation_id)
            self.journal.finish_operation(operation.operation_id, operation.revision, 'unused')
        before = self.dump(); report = self.cleanup()
        self.assertEqual((0, 1, 0), (report.candidate_count, report.preserved_count, self.raw.reads))
        self.assertEqual(before, self.dump())

    def test_lease_and_consumed_proposal_keep_all_history_and_operation_stages(self):
        from common.operations.managed_connections import ManagedConnectionStore
        stage = self.stage('historical-token'); item = self.protect(stage.owned_ref)
        managed = ManagedConnectionStore(self.root)
        with oauth_write_guard(self.context):
            proposal = dict(connection_id='conn', account_id='personal', platform='youtube', base_revision='base',
                target_id='target', provider_subject='subject', credential_ref=stage.owned_ref,
                scopes=('read',), checked_at=datetime.now(timezone.utc).isoformat())
            saved = managed.create_target_proposal(item['attempt_id'], 'binding', item['revision'], proposal)
            managed.confirm_target(saved, 'base', 0)
            lease = managed.claim_connection_operation('conn', 'base', 1, 'refresh')
            other = self.stage('lease-owned-stage', remote=True, outcome='pending')
            self.journal.bind_operation('lease', 'conn', other.operation_id, lease['connection_revision'])
            operation = self.journal.read_operation(other.operation_id)
            self.journal.finish_operation(operation.operation_id, operation.revision, 'unused')
        self.assertFalse(self.snapshot().blockers)
        self.assertIn(other.owned_ref, self.snapshot().protected_refs)
        before = self.dump(); report = self.cleanup()
        self.assertEqual((0, 2, 0), (report.candidate_count, report.preserved_count, self.raw.reads))
        self.assertEqual(before, self.dump())

    def test_envelope_changed_after_first_proof_is_preserved_on_delete_recheck(self):
        stage = self.stage(); address = scoped_address(stage.owned_ref)
        self.raw.after_read = lambda: self.raw._items.__setitem__(address, b'unproven-replacement')
        report = self.cleanup()
        self.assertEqual(('partial', 0, 0), (report.status, report.deleted_count, self.raw.deletes))
        self.assertEqual(b'unproven-replacement', self.raw._items[address])
        self.assertEqual(1, dict(report.reason_counts)['integrity_failed'])

    def test_backend_calls_hold_guard_but_no_database_transaction(self):
        self.stage()

        def exclusive_database_access():
            from common.operations.oauth_workspace import require_oauth_write_guard
            require_oauth_write_guard(self.root, self.context.owner)
            with closing(sqlite3.connect(self.root/'oauth.sqlite3', timeout=0)) as db:
                db.execute('BEGIN EXCLUSIVE'); db.rollback()

        self.raw.after_read = exclusive_database_access
        self.assertEqual(1, self.cleanup().deleted_count)

    def test_graph_change_during_delete_intent_aborts_before_native_delete(self):
        self.stage()
        original = self.journal.record_recovery_event

        def changed(stage_id, revision, code):
            event = original(stage_id, revision, code)
            if code == 'delete_intent':
                self.journal.begin_operation('callback', local_only=True)
            return event

        with patch.object(self.journal, 'record_recovery_event', side_effect=changed):
            report = self.cleanup()
        self.assertEqual(('partial', 0), (report.status, report.deleted_count))
        self.assertEqual(0, self.raw.deletes)

    def test_wrong_owner_and_cross_root_backend_are_blocked_without_reads(self):
        self.stage()
        self.assertEqual('blocked', self.cleanup(expected_workspace_id='0'*32).status)
        other = initialize_workspace_owner(self.root/'other')
        backend = OwnedStageBackend(other, self.raw); snap = self.snapshot()
        report = self.api().cleanup_recovery(self.context, self.journal, backend,
            expected_workspace_id=self.context.owner.workspace_id,
            expected_journal_revision=snap.journal_revision, expected_graph_revision=snap.graph_revision)
        self.assertEqual('blocked', report.status); self.assertEqual(0, self.raw.reads)

    def test_missing_or_copied_marker_is_not_adopted(self):
        self.stage(); before = self.dump(); marker = self.root/OWNER_MARKER_NAME
        saved = marker.read_bytes(); marker.unlink()
        report = self.api().inspect_recovery(self.context, self.journal, self.backend,
                                            expected_workspace_id=self.context.owner.workspace_id)
        self.assertEqual('blocked', report.status); self.assertFalse(marker.exists())
        marker.write_bytes(saved); marker.chmod(0o600)
        other = self.root/'copied'; other.mkdir(mode=0o700)
        shutil.copy2(marker, other/OWNER_MARKER_NAME)
        with self.assertRaises(CredentialError):
            load_workspace_owner(other)
        self.assertEqual(before, self.dump()); self.assertEqual(0, self.raw.reads)

    def test_copied_database_and_marker_are_blocked_without_backend_reads(self):
        self.stage(); copied = self.root/'copy'; copied.mkdir(mode=0o700)
        shutil.copy2(self.root/OWNER_MARKER_NAME, copied/OWNER_MARKER_NAME)
        shutil.copy2(self.root/'oauth.sqlite3', copied/'oauth.sqlite3')
        context = OAuthWorkspaceContext(copied, self.context.owner, self.context.key_provider)
        report = self.api().inspect_recovery(context, OAuthStageStore(context), OwnedStageBackend(context, self.raw),
                                            expected_workspace_id=self.context.owner.workspace_id)
        self.assertEqual('blocked', report.status)
        self.assertEqual((0, 0), (self.raw.reads, self.raw.deletes))

    def test_delete_success_then_metadata_failure_reopens_as_absent(self):
        from tests.helpers.oauth_scoped_crash_fixture import DurableScopedRawBackend
        with TemporaryDirectory(prefix='oauth-crash-fixture-') as temp:
            raw = DurableScopedRawBackend(Path(temp)/'fake.sqlite3')
            self.backend = OwnedStageBackend(self.context, raw)
            self.stage()
            with patch.object(self.journal, 'mark_deleted', side_effect=StoreError('private-error')):
                report = self.cleanup()
            self.assertEqual(('partial', 0), (report.status, report.deleted_count))
            # Reopen every actual component, not only the in-memory Python object.
            self.context = load_workspace_owner(self.root); self.journal = OAuthStageStore(self.context)
            self.backend = OwnedStageBackend(self.context, DurableScopedRawBackend(Path(temp)/'fake.sqlite3'))
            report = self.cleanup()
            self.assertEqual(('cleaned', 0, 1), (report.status, report.deleted_count, report.absent_count))
            self.assertEqual('deleted', self.snapshot().stages[0].state)

    def test_cli_without_opt_in_blocks_and_invalid_argv_is_sanitized(self):
        api = self.api(); output = io.StringIO()
        args = ['--workspace', str(self.root), '--mode', 'inspect', '--expected-workspace-id', self.context.owner.workspace_id]
        with patch('ctypes.CDLL', side_effect=AssertionError('real native forbidden')):
            code = api.main(args, stdout=output)
        self.assertEqual(2, code)
        self.assertEqual({'backend_required': 1}, json.loads(output.getvalue())['reason_counts'])
        output = io.StringIO()
        self.assertEqual(2, api.main(['--private-token-secret'], stdout=output))
        self.assertNotIn('private-token-secret', output.getvalue())

    def test_cli_explicit_fake_factory_inspects_and_cleans(self):
        self.stage(); api = self.api(); output = io.StringIO()
        args = ['--workspace', str(self.root), '--mode', 'inspect', '--expected-workspace-id', self.context.owner.workspace_id]
        self.assertEqual(0, api.main(args, backend_factory=lambda ctx: OwnedStageBackend(ctx, self.raw), stdout=output))
        report = json.loads(output.getvalue()); self.assertEqual(1, report['candidate_count'])
        args[3] = 'cleanup'; args += ['--expected-journal-revision', str(report['journal_revision']),
                                    '--expected-graph-revision', str(report['graph_revision'])]
        output = io.StringIO()
        self.assertEqual(0, api.main(args, backend_factory=lambda ctx: OwnedStageBackend(ctx, self.raw), stdout=output))
        self.assertEqual(1, json.loads(output.getvalue())['deleted_count'])

    def test_cli_keychain_flag_uses_fake_lazy_bridge_only(self):
        from tests.operations.test_credential_backend import FakeBridge
        bridge = FakeBridge(); self.stage()
        args = ['--workspace', str(self.root), '--mode', 'inspect', '--keychain',
                '--expected-workspace-id', self.context.owner.workspace_id]
        with patch('common.operations.keychain_backend.SecurityFrameworkBridge', return_value=bridge), \
             patch('ctypes.CDLL', side_effect=AssertionError('real native forbidden')):
            output = io.StringIO(); self.assertEqual(0, self.api().main(args, stdout=output))
        self.assertEqual(1, json.loads(output.getvalue())['absent_count'])
        self.assertEqual(1, len(bridge.calls))
        self.assertEqual(['copy'], bridge.calls)

    def test_cli_rejects_owner_and_missing_revisions_before_factory(self):
        api = self.api(); self.stage()
        for args in (['--workspace', str(self.root), '--mode', 'cleanup',
                      '--expected-workspace-id', self.context.owner.workspace_id],
                     ['--workspace', str(self.root), '--mode', 'inspect', '--expected-workspace-id', '0'*32]):
            with self.subTest(args=args):
                output = io.StringIO()
                with patch('ctypes.CDLL', side_effect=AssertionError('real native forbidden')):
                    code = api.main(args, backend_factory=lambda _: self.fail('unexpected backend construction'), stdout=output)
                self.assertEqual(2, code)
                self.assertEqual('blocked', json.loads(output.getvalue())['status'])


if __name__ == '__main__':
    unittest.main()
