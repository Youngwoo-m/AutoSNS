"""실제 SIGKILL/reopen OAuth crash matrix. 임시 durable fake만 사용한다."""
from contextlib import closing
import multiprocessing
from pathlib import Path
import signal
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from common.operations.content_store import StoreError
from common.operations.credential_backend import CredentialError
from common.operations.oauth_models import CredentialRef
from common.operations.oauth_stage_backend import scoped_address
from common.operations.oauth_stage_models import OwnedCredentialRef
from common.operations.oauth_workspace import oauth_write_guard
from tests.helpers.oauth_recovery_process import ProcessFixture, recovery_worker


class OAuthRecoveryProcessCrashTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(prefix='oauth-crash-fixture-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.processes = multiprocessing.get_context('spawn')

    def fixture(self, name='workspace', *, initialize=True, vault=None):
        return ProcessFixture(self.base/name, vault or self.base/(name+'-vault.sqlite3'),
                              self.base/(name+'-calls.sqlite3'), initialize=initialize)

    def reopen(self, fixture):
        return ProcessFixture(fixture.root, fixture.vault_path, fixture.calls.path)

    def kill_at(self, fixture, action, boundary, inputs, stage_kind=None):
        parent, child = self.processes.Pipe()
        process = self.processes.Process(target=recovery_worker,
            args=(str(fixture.root), str(fixture.vault_path), str(fixture.calls.path),
                  child, action, boundary, stage_kind, inputs))
        process.start()
        child.close()
        try:
            self.assertTrue(parent.poll(15), 'child did not reach committed boundary')
            self.assertEqual(boundary, parent.recv())
            process.kill()
            process.join(15)
            self.assertFalse(process.is_alive())
            self.assertEqual(-signal.SIGKILL, process.exitcode)
        finally:
            if process.is_alive():
                process.kill()
                process.join(15)
            parent.close()
            process.close()

    def row(self, fixture):
        return dict(fixture.connections.snapshot().connections[fixture.connection_id])

    def protected_bytes(self, fixture):
        return {ref: fixture.read(ref) for ref in fixture.snapshot().protected_refs}

    def assert_history_preserved(self, fixture, saved):
        snap = fixture.snapshot()
        self.assertEqual((), snap.blockers)
        self.assertTrue(set(saved) <= snap.protected_refs)
        for ref, payload in saved.items():
            self.assertTrue(payload == fixture.read(ref), 'protected fake bytes changed')

    def assert_pending_receipt(self, fixture, kind):
        pending = [op for op in fixture.snapshot().operations.values()
                   if op.kind == kind and op.outcome == 'pending']
        self.assertEqual(1, len(pending))
        operation = pending[0]
        with closing(sqlite3.connect(fixture.root/'oauth.sqlite3')) as db:
            row = db.execute('SELECT status,operation_id FROM oauth_request_receipts WHERE id=?',
                             (operation.receipt_id,)).fetchone()
        self.assertTrue(row == ('pending', operation.operation_id))
        return operation

    def assert_get_reopen_cleanup_preserve(self, fixture, saved):
        before = fixture.calls.counts()
        snap = fixture.snapshot()
        db_bytes = (fixture.root/'oauth.sqlite3').read_bytes()
        row = self.row(fixture)
        with patch('common.operations.oauth_service.oauth_write_guard',
                   side_effect=AssertionError('GET acquired writer guard')):
            reopened = self.reopen(fixture)
            reopened.service.catalog(reopened.session)
            reopened.service.connections(reopened.session)
            reopened.service.result_for_session(reopened.session)
        self.assertEqual(before, fixture.calls.counts())
        self.assertTrue(db_bytes == (fixture.root/'oauth.sqlite3').read_bytes())
        self.assertTrue(row == self.row(reopened), 'GET changed pointer or lease')
        self.assertEqual((snap.graph_revision, snap.journal_revision),
                         (reopened.snapshot().graph_revision, reopened.snapshot().journal_revision))
        report = reopened.cleanup()
        self.assertEqual(0, report.deleted_count)
        self.assertEqual(0, report.absent_count)
        self.assertEqual(0, report.candidate_count)
        self.assertEqual(before, fixture.calls.counts(), 'protected recovery touched fake backend/provider')
        self.assertTrue(row == self.row(reopened), 'cleanup changed pointer or lease')
        self.assert_history_preserved(reopened, saved)
        return reopened

    def test_start_stage_commit_matrix_preserves_existing_active_and_pending_receipt(self):
        for boundary, expected_state, present in (
            ('before_intent', None, False), ('after_intent', 'intent', False),
            ('after_put', 'intent', True), ('after_stored', 'stored', True),
        ):
            with self.subTest(boundary=boundary):
                fixture = self.fixture(boundary)
                fixture.connected()
                old = self.row(fixture)
                saved = self.protected_bytes(fixture)
                inputs = {'body': fixture.start_body('crashed-start', 1)}
                self.kill_at(fixture, 'start', boundary, inputs, 'state_key')
                fixture = self.reopen(fixture)
                self.assertTrue(old == self.row(fixture))
                operation = self.assert_pending_receipt(fixture, 'start')
                stages = [s for s in fixture.snapshot().stages if s.operation_id == operation.operation_id]
                self.assertEqual([] if expected_state is None else [expected_state], [s.state for s in stages])
                if stages:
                    if present: self.assertEqual(32, len(fixture.read(stages[0].owned_ref)))
                    else:
                        with self.assertRaises(CredentialError) as caught: fixture.read(stages[0].owned_ref)
                        self.assertEqual('credential_not_found', caught.exception.code)
                before = fixture.calls.counts()
                with self.assertRaises(StoreError): fixture.service.start(fixture.session, inputs['body'])
                self.assertEqual(before, fixture.calls.counts())
                self.assert_get_reopen_cleanup_preserve(fixture, saved)

    def test_callback_stage_commit_matrix_preserves_consumed_claim_and_active_history(self):
        for boundary in ('after_intent', 'after_put', 'after_stored'):
            with self.subTest(boundary=boundary):
                fixture = self.fixture('callback-'+boundary)
                fixture.connected()
                old = self.row(fixture)
                _, state = fixture.start('callback-start', 1)
                saved = self.protected_bytes(fixture)
                inputs = dict(state=state, code='fake-crash-code')
                self.kill_at(fixture, 'callback', boundary, inputs, 'code')
                fixture = self.reopen(fixture)
                self.assertTrue(old == self.row(fixture))
                callback = [op for op in fixture.snapshot().operations.values()
                            if op.kind == 'callback' and op.outcome == 'pending']
                self.assertEqual(1, len(callback))
                stages = [s for s in fixture.snapshot().stages if s.operation_id == callback[0].operation_id]
                self.assertEqual(1, len(stages))
                self.assertEqual('stored' if boundary == 'after_stored' else 'intent', stages[0].state)
                self.assertIn(stages[0].owned_ref, fixture.snapshot().protected_refs)
                if boundary == 'after_intent':
                    with self.assertRaises(CredentialError) as caught:
                        fixture.read(stages[0].owned_ref)
                    self.assertEqual('credential_not_found', caught.exception.code)
                else:
                    self.assertTrue(inputs['code'].encode() == fixture.read(stages[0].owned_ref),
                                    'new callback code bytes changed')
                before = fixture.calls.counts()
                with self.assertRaises(StoreError):
                    fixture.service.receive_callback('youtube', inputs, fixture.callback)
                self.assertEqual(before, fixture.calls.counts())
                self.assert_get_reopen_cleanup_preserve(fixture, saved)

    def test_exchange_token_pointer_commit_precedes_receipt_without_remote_replay(self):
        fixture = self.fixture()
        fixture.connected()
        old = self.row(fixture)
        item = fixture.staged('second', 1)
        saved = self.protected_bytes(fixture)
        inputs = dict(attempt_id=item['attempt_id'], body=dict(request_key='crashed-continue', expected_revision=item['revision']))
        count = fixture.calls.counts()['provider_exchange']
        self.kill_at(fixture, 'continue', 'after_token_pointer', inputs)
        fixture = self.reopen(fixture)
        self.assertTrue(old == self.row(fixture))
        self.assert_pending_receipt(fixture, 'continue')
        attempt = fixture.attempts.read_owned(item['attempt_id'], fixture.session.session_binding)
        self.assertEqual('token_exchanged', attempt['state'])
        token = attempt['token_ref']
        self.assertIn(token, fixture.snapshot().protected_refs)
        self.assertEqual('referenced', next(s.state for s in fixture.snapshot().stages if s.owned_ref == token))
        saved[token] = fixture.read(token)
        with self.assertRaises(StoreError): fixture.service.resume_exchange(fixture.session, item['attempt_id'], inputs['body'])
        self.assertEqual(count+1, fixture.calls.counts()['provider_exchange'])
        self.assert_get_reopen_cleanup_preserve(fixture, saved)

    def test_proposal_commit_before_and_after_preserve_pending_inspect_without_replay(self):
        for boundary in ('before_proposal_commit', 'after_proposal_commit'):
            with self.subTest(boundary=boundary):
                fixture = self.fixture(boundary)
                fixture.connected()
                old = self.row(fixture)
                item = fixture.exchanged('second', 1)
                saved = self.protected_bytes(fixture)
                inputs = dict(attempt_id=item['attempt_id'], body=dict(
                    request_key='crashed-inspect', expected_revision=item['revision']))
                count = fixture.calls.counts()['provider_inspect']
                self.kill_at(fixture, 'inspect', boundary, inputs)
                fixture = self.reopen(fixture)
                self.assertTrue(old == self.row(fixture))
                operation = self.assert_pending_receipt(fixture, 'inspect')
                self.assertEqual('returned', operation.remote_state)
                attempt = fixture.attempts.read_owned(item['attempt_id'], fixture.session.session_binding)
                proposal = fixture.connections.proposal_for_attempt(item['attempt_id'], fixture.session.session_binding)
                if boundary == 'before_proposal_commit':
                    self.assertIsNone(proposal)
                    self.assertEqual('principal_pending', attempt['state'])
                    self.assertEqual(item['revision']+1, attempt['revision'])
                else:
                    self.assertIsNotNone(proposal)
                    self.assertEqual('target_confirmation', attempt['state'])
                    self.assertEqual(item['revision']+2, attempt['revision'])
                    self.assertFalse(proposal['consumed'])
                    self.assertEqual(attempt['token_ref'], proposal['credential_ref'])
                    self.assertIn(proposal['credential_ref'], fixture.snapshot().protected_refs)
                before = fixture.calls.counts()
                for _ in range(2):
                    fixture = self.reopen(fixture)
                    with self.assertRaises(StoreError):
                        fixture.service.inspect(fixture.session, item['attempt_id'], inputs['body'])
                self.assertEqual(before, fixture.calls.counts())
                self.assertEqual(count+1, fixture.calls.counts()['provider_inspect'])
                self.assert_get_reopen_cleanup_preserve(fixture, saved)

    def test_confirm_pointer_commit_precedes_receipt_and_preserves_previous_secret(self):
        fixture = self.fixture()
        fixture.connected()
        old = self.row(fixture)
        item = fixture.proposal('second', 1)
        saved = self.protected_bytes(fixture)
        inputs = dict(proposal_id=item['target_proposal']['proposal_id'],
                      body=dict(request_key='crashed-confirm', expected_base_revision='base', expected_connection_revision=1))
        self.kill_at(fixture, 'confirm', 'after_confirm_pointer', inputs)
        fixture = self.reopen(fixture)
        self.assert_pending_receipt(fixture, 'confirm')
        new = self.row(fixture)
        self.assertNotEqual(old['credential_ref'], new['credential_ref'])
        self.assertEqual(old['revision']+1, new['revision'])
        with self.assertRaises(StoreError): fixture.service.confirm_target(fixture.session, inputs['proposal_id'], inputs['body'])
        self.assert_get_reopen_cleanup_preserve(fixture, saved)

    def test_refresh_response_staging_and_active_cas_crashes_never_replay_or_clear_lease(self):
        for boundary in ('after_refresh_response', 'after_intent', 'after_put',
                         'after_stored', 'before_refresh_pointer', 'after_refresh_pointer'):
            with self.subTest(boundary=boundary):
                fixture = self.fixture(boundary)
                fixture.connected()
                old = self.row(fixture)
                saved = self.protected_bytes(fixture)
                inputs = {'body': dict(request_key='crashed-refresh', expected_base_revision='base', expected_connection_revision=1)}
                self.kill_at(fixture, 'refresh', boundary, inputs,
                             'token' if boundary in ('after_intent', 'after_put', 'after_stored') else None)
                fixture = self.reopen(fixture)
                operation = self.assert_pending_receipt(fixture, 'refresh')
                new = self.row(fixture)
                self.assertEqual('in_flight' if boundary == 'after_refresh_response' else 'returned', operation.remote_state)
                self.assertEqual(1, fixture.calls.counts()['provider_refresh'])
                if boundary == 'after_refresh_pointer':
                    self.assertNotEqual(old['credential_ref'], new['credential_ref'])
                    # Claim and pointer CAS each advance the existing revision.
                    self.assertEqual(old['revision']+2, new['revision'])
                    self.assertNotIn('operation_lease', new)
                    saved[new['credential_ref']] = fixture.read(new['credential_ref'])
                else:
                    self.assertEqual(old['credential_ref'], new['credential_ref'])
                    self.assertEqual(old['revision']+1, new['revision'])
                    self.assertEqual(old['credential_ref'], new['operation_lease']['credential_ref'])
                    self.assertEqual(operation.operation_id, new['operation_lease']['operation_id'])
                    public = next(row for row in fixture.service.connections(fixture.session)['items']
                                  if row['id'] == fixture.connection_id)
                    self.assertEqual(('unknown', 'unknown'), (public['state'], public['auth_status']))
                stages = [s for s in fixture.snapshot().stages if s.operation_id == operation.operation_id]
                self.assertEqual(0 if boundary == 'after_refresh_response' else 1, len(stages))
                for stage in stages:
                    self.assertIn(stage.owned_ref, fixture.snapshot().protected_refs)
                    if boundary == 'after_intent':
                        with self.assertRaises(CredentialError) as caught: fixture.read(stage.owned_ref)
                        self.assertEqual('credential_not_found', caught.exception.code)
                    else:
                        saved[stage.owned_ref] = fixture.read(stage.owned_ref)
                for _ in range(2):
                    fixture = self.reopen(fixture)
                    with self.assertRaises(StoreError): fixture.service.refresh(fixture.session, fixture.connection_id, inputs['body'])
                self.assertEqual(1, fixture.calls.counts()['provider_refresh'])
                self.assert_get_reopen_cleanup_preserve(fixture, saved)

    def test_cleanup_delete_and_mark_commit_crashes_reopen_idempotently(self):
        for boundary in ('after_exact_delete', 'after_mark_deleted'):
            with self.subTest(boundary=boundary):
                fixture = self.fixture(boundary)
                logical = CredentialRef('autosns.oauth', 'personal', 'youtube', fixture.connection_id, 1, 'token')
                with oauth_write_guard(fixture.context):
                    operation = fixture.journal.begin_operation('callback', local_only=True)
                    ref = fixture.service.stage_secret(operation.operation_id, logical, b'fake-unused')
                    fixture.journal.finish_operation(operation.operation_id, operation.revision, 'unused')
                self.kill_at(fixture, 'cleanup', boundary, {})
                fixture = self.reopen(fixture)
                marked = boundary == 'after_mark_deleted'
                self.assertEqual('deleted' if marked else 'stored', fixture.snapshot().stages[0].state)
                self.assertEqual(1, fixture.calls.counts()['raw_delete'])
                with closing(sqlite3.connect(fixture.root/'oauth.sqlite3')) as db:
                    self.assertEqual({'delete_intent': 1, 'deleted': 1} if marked else {'delete_intent': 1},
                                     dict(db.execute('SELECT code,count(*) FROM oauth_recovery_events GROUP BY code')))
                before = fixture.calls.counts()
                revisions = (fixture.snapshot().journal_revision, fixture.snapshot().graph_revision)
                report = fixture.cleanup()
                self.assertEqual(('cleaned', 0, 0 if marked else 1, 1 if marked else 0),
                    (report.status, report.deleted_count, report.absent_count, report.already_deleted_count))
                if marked:
                    self.assertEqual(before, fixture.calls.counts())
                    self.assertEqual(revisions, (fixture.snapshot().journal_revision, fixture.snapshot().graph_revision))
                self.assertEqual('deleted', fixture.snapshot().stages[0].state)
                before = fixture.calls.counts()
                revisions = (fixture.snapshot().journal_revision, fixture.snapshot().graph_revision)
                again = self.reopen(fixture).cleanup()
                self.assertEqual((0, 0, 1), (again.deleted_count, again.absent_count, again.already_deleted_count))
                self.assertEqual(before, fixture.calls.counts())
                self.assertEqual(revisions, (fixture.snapshot().journal_revision, fixture.snapshot().graph_revision))
                self.assertFalse(any(name.startswith('provider_') for name in before))
                with self.assertRaises(CredentialError): fixture.read(ref)

    def test_different_workspace_roots_separate_same_logical_and_stage_identity(self):
        vault = self.base/'shared-fake-vault.sqlite3'
        first = self.fixture('first', vault=vault)
        second = self.fixture('second', vault=vault)
        logical = CredentialRef('autosns.oauth', 'personal', 'youtube', 'same', 1, 'token')
        refs = []
        for fixture, payload in ((first, b'fake-first'), (second, b'fake-second')):
            owner = fixture.context.owner
            ref = OwnedCredentialRef(logical, owner.workspace_id, owner.root_binding, 'same-stage')
            refs.append(ref)
            with oauth_write_guard(fixture.context):
                op = fixture.journal.begin_operation('callback', local_only=True)
                stage = fixture.journal.begin_stage(owner, ref, op.operation_id, 0)
                fixture.owned.put_owned(ref, payload)
                fixture.journal.mark_stored(stage.stage_id, stage.revision)
                fixture.journal.finish_operation(op.operation_id, op.revision, 'unused')
        self.assertNotEqual(scoped_address(refs[0]), scoped_address(refs[1]))
        self.assertEqual(1, first.cleanup().deleted_count)
        self.assertTrue(b'fake-second' == second.read(refs[1]))
        self.assertEqual(1, second.cleanup().deleted_count)


if __name__ == '__main__':
    unittest.main()
