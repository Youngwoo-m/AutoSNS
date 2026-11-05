"""임시 schema2 + Memory scoped vault의 서비스 통합. 실제 provider/native I/O 없음."""
from dataclasses import replace
from contextlib import closing, contextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import threading
import unittest
from unittest.mock import patch

from . import test_oauth_service as legacy
from common.operations.content_store import StoreError
from common.operations.credential_backend import CredentialError
from common.operations.oauth_models import CredentialRef
from common.operations.oauth_service import OAuthConnectionService, SessionContext
from common.operations.oauth_stage_backend import MemoryScopedRawBackend, OwnedStageBackend
from common.operations.oauth_stage_models import OwnedCredentialRef, logical_ref
from common.operations.oauth_stage_store import OAuthStageStore, migrate_to_owned_schema
from common.operations.oauth_workspace import WorkspaceError, initialize_workspace_owner, oauth_write_guard, require_oauth_write_guard


class ObservedRawBackend(MemoryScopedRawBackend):
    def __init__(self, probe):
        super().__init__(); self.probe=probe; self.deletes=0
    def add(self, address, value):
        self.probe(); return super().add(address,value)
    def copy(self, address):
        self.probe(); return super().copy(address)
    def delete(self, address):
        self.deletes+=1
        return super().delete(address)


class OwnedOAuthServiceTests(unittest.TestCase):
    body=legacy.OAuthServiceTests.body
    start=legacy.OAuthServiceTests.start
    staged=legacy.OAuthServiceTests.staged
    exchanged=legacy.OAuthServiceTests.exchanged
    proposal=legacy.OAuthServiceTests.proposal
    connected=legacy.OAuthServiceTests.connected
    assert_public=legacy.OAuthServiceTests.assert_public

    def setUp(self):
        legacy.OAuthServiceTests.setUp(self)
        self.context=initialize_workspace_owner(self.tmp.name)
        with oauth_write_guard(self.context): migrate_to_owned_schema(self.context)
        self.stages=OAuthStageStore(self.context,self.clock)
        self.raw=ObservedRawBackend(self.probe)
        self.owned=OwnedStageBackend(self.context,self.raw)
        self.owned.delete_owned=lambda *args: self.fail('서비스의 owned delete 호출')
        self.service=self.make_service()
        self.external_calls=[]
        self.observe_provider()

    def observe_provider(self):
        for name in ('exchange','inspect','refresh','revoke'):
            original=getattr(self.provider,name)
            def observed(*args,_original=original,_name=name,**kwargs):
                self.probe()
                with closing(sqlite3.connect(Path(self.tmp.name)/'oauth.sqlite3')) as db:
                    row=db.execute('SELECT remote_state,outcome FROM oauth_operations WHERE kind=? ORDER BY rowid DESC LIMIT 1',('continue' if _name=='exchange' else _name,)).fetchone()
                self.assertEqual(('in_flight','pending'),row)
                self.external_calls.append(_name)
                return _original(*args,**kwargs)
            setattr(self.provider,name,observed)

    def use_provider(self,name):
        legacy.OAuthServiceTests.use_provider(self,name)
        self.observe_provider()

    def make_service(self,**kwargs):
        if hasattr(self,'context'):
            kwargs=dict(workspace_context=self.context,stage_store=self.stages,owned_backend=self.owned,**kwargs)
        return legacy.OAuthServiceTests.make_service(self,**kwargs)

    def probe(self):
        require_oauth_write_guard(self.context.root,self.context.owner)
        # 외부 I/O 때 다른 SQLite writer가 즉시 transaction을 열 수 있어야 한다.
        db=sqlite3.connect(Path(self.tmp.name)/'oauth.sqlite3',timeout=0)
        try: db.execute('BEGIN IMMEDIATE'); db.rollback()
        finally: db.close()

    def snapshot(self):
        return self.stages.recovery_snapshot(self.context.owner)

    def test_owned_lifecycle_reopen_refresh_disconnect_keeps_full_identity(self):
        self.connected()
        before=self.connections_store.snapshot().connections['personal.youtube']['credential_ref']
        self.assertIsInstance(before,OwnedCredentialRef)
        self.assertEqual((),self.snapshot().blockers)
        self.service=self.make_service()
        new_session=SessionContext('console_user','new-session')
        result=self.service.refresh(new_session,'personal.youtube',dict(request_key='rotate',expected_base_revision='base',expected_connection_revision=1))
        after=self.connections_store.snapshot().connections['personal.youtube']['credential_ref']
        self.assertGreater(logical_ref(after).generation,logical_ref(before).generation)
        self.assertNotEqual(before.stage_id,after.stage_id)
        self.assertEqual('connected',result['state'])
        self.assertEqual((),self.snapshot().blockers)
        result=self.service.disconnect_local(new_session,'personal.youtube',dict(request_key='off',expected_base_revision='base',expected_connection_revision=result['connection_revision']))
        self.assertEqual('disconnected',result['state'])
        self.assertEqual(0,self.raw.deletes)
        self.assertEqual(['exchange','inspect','refresh'],self.external_calls)
        self.assert_public(result)
        self.assertEqual((),self.snapshot().blockers)

    def test_callback_expiry_after_two_stored_stages_is_unused_without_delete(self):
        started,state=self.start()
        original=self.owned.put_owned
        def expire_after_ticket(ref,payload):
            original(ref,payload)
            if logical_ref(ref).kind=='ticket': self.now+=timedelta(minutes=11)
        with patch.object(self.owned,'put_owned',side_effect=expire_after_ticket):
            with self.assertRaises(StoreError): self.service.receive_callback('youtube',dict(state=state,code='secret-code'),self.callback)
        snapshot=self.snapshot()
        callback=[op for op in snapshot.operations.values() if op.kind=='callback']
        self.assertEqual(1,len(callback)); self.assertEqual('unused',callback[0].outcome)
        unused=[s for s in snapshot.stages if s.operation_id==callback[0].operation_id]
        self.assertEqual(2,len(unused))
        self.assertTrue(all(s.state=='stored' and s.owned_ref not in snapshot.protected_refs for s in unused))
        self.assertEqual((),snapshot.blockers)
        with oauth_write_guard(self.context):
            for stage in unused:
                self.stages.record_recovery_event(stage.stage_id,stage.revision,'delete_intent')
        self.assertEqual('error',self.service.read_attempt(self.session,started['attempt_id'])['state'])
        self.assertEqual(0,self.raw.deletes)

    def test_exchange_response_record_loss_preserves_pending_receipt_and_no_replay(self):
        item=self.staged(); body=dict(request_key='exchange',expected_revision=item['revision'])
        with patch.object(self.stages,'mark_remote_returned',side_effect=StoreError('storage_unavailable')):
            with self.assertRaises(StoreError): self.service.resume_exchange(self.session,item['attempt_id'],body)
        with self.assertRaises(StoreError): self.service.resume_exchange(self.session,item['attempt_id'],body)
        op=next(op for op in self.snapshot().operations.values() if op.kind=='continue')
        self.assertEqual(('unknown','unknown'),(op.remote_state,op.outcome))
        self.assertEqual(['exchange'],self.external_calls)
        self.assertEqual(0,self.raw.deletes)

    def test_owned_get_constructor_and_reopen_have_no_backend_provider_or_guard_io(self):
        self.connected(); before=self.snapshot()
        db_path=Path(self.tmp.name)/'oauth.sqlite3'; data=db_path.read_bytes()
        with patch.object(self.raw,'copy',side_effect=AssertionError('GET vault')), \
             patch.object(self.raw,'add',side_effect=AssertionError('GET stage')), \
             patch.object(self.raw,'delete',side_effect=AssertionError('GET delete')), \
             patch('common.operations.oauth_service.oauth_write_guard',side_effect=AssertionError('GET guard')):
            self.service=self.make_service()
            self.service.catalog(self.session); self.service.connections(self.session)
            self.service.result_for_session(self.session)
        self.assertEqual(data,db_path.read_bytes())
        self.assertEqual(before.graph_revision,self.snapshot().graph_revision)
        self.assertEqual(before.journal_revision,self.snapshot().journal_revision)

    def test_constructor_rejects_incomplete_or_foreign_root_injection(self):
        values=dict(registry_supplier=lambda:self.registry,client_registrations={},attempt_store=self.attempts,
                    connection_store=self.connections_store,backend=self.vault,providers={})
        with self.assertRaises(StoreError): OAuthConnectionService(**values,workspace_context=self.context)
        with TemporaryDirectory() as other:
            foreign=initialize_workspace_owner(other)
            with self.assertRaises(StoreError):
                OAuthConnectionService(**values,workspace_context=self.context,stage_store=OAuthStageStore(foreign),owned_backend=self.owned)

    def test_callback_duplicate_put_preserves_pending_intent(self):
        started,state=self.start()
        with patch.object(self.owned,'put_owned',side_effect=CredentialError('credential_duplicate')):
            with self.assertRaises(StoreError): self.service.receive_callback('youtube',dict(state=state,code='secret-code'),self.callback)
        snapshot=self.snapshot(); op=next(op for op in snapshot.operations.values() if op.kind=='callback')
        self.assertEqual('pending',op.outcome)
        stages=[stage for stage in snapshot.stages if stage.operation_id==op.operation_id]
        self.assertEqual(['intent'],[stage.state for stage in stages])
        self.assertTrue(all(stage.owned_ref in snapshot.protected_refs for stage in stages))
        self.assertEqual(0,self.raw.deletes)
        self.assertEqual((),snapshot.blockers)
        with self.assertRaises(StoreError): self.service.receive_callback('youtube',dict(state=state,code='secret-code'),self.callback)

    def test_callback_stored_record_loss_keeps_vault_item_and_pending_intent(self):
        _,state=self.start(); count=len(self.raw._items)
        with patch.object(self.stages,'mark_stored',side_effect=StoreError('storage_unavailable')):
            with self.assertRaises(StoreError): self.service.receive_callback('youtube',dict(state=state,code='secret-code'),self.callback)
        snapshot=self.snapshot(); op=next(op for op in snapshot.operations.values() if op.kind=='callback')
        self.assertEqual('pending',op.outcome)
        self.assertEqual(count+1,len(self.raw._items))
        self.assertEqual(0,self.raw.deletes)
        self.assertEqual((),snapshot.blockers)

    def test_denied_callback_preserves_owned_history_and_calls_no_remote_provider(self):
        _,state=self.start(); before=set(self.raw._items)
        self.service.receive_callback('youtube',dict(state=state,error='access_denied'),self.callback)
        self.assertEqual(before,set(self.raw._items))
        self.assertEqual(0,self.raw.deletes)
        self.assertEqual([],self.external_calls)
        self.assertEqual((),self.snapshot().blockers)

    def test_confirm_cas_failure_preserves_proposal_and_token(self):
        item=self.proposal(); proposal=item['target_proposal']; before=set(self.raw._items)
        self.registry=replace(self.registry,revision='changed')
        with self.assertRaises(StoreError):
            self.service.confirm_target(self.session,proposal['proposal_id'],dict(request_key='conflict',expected_base_revision='base',expected_connection_revision=0))
        snapshot=self.snapshot()
        self.assertEqual({},dict(self.connections_store.snapshot().connections))
        token=self.attempts.read_owned(item['attempt_id'],self.session.session_binding)['token_ref']
        self.assertIn(token,snapshot.protected_refs)
        self.assertEqual(before,set(self.raw._items)); self.assertEqual(0,self.raw.deletes)
        self.assertEqual('pending',next(op for op in snapshot.operations.values() if op.kind=='confirm').outcome)

    def test_invalid_provider_response_is_unknown_and_retry_does_not_exchange_again(self):
        item=self.staged(); body=dict(request_key='invalid-response',expected_revision=item['revision'])
        original=self.provider.exchange
        def invalid(*args,**kwargs):
            original(*args,**kwargs)
            return {'access_token':'secret-access'}
        with patch.object(self.provider,'exchange',side_effect=invalid):
            with self.assertRaises(StoreError): self.service.resume_exchange(self.session,item['attempt_id'],body)
        with self.assertRaises(StoreError): self.service.resume_exchange(self.session,item['attempt_id'],body)
        snapshot=self.snapshot(); op=next(op for op in snapshot.operations.values() if op.kind=='continue')
        self.assertEqual(('unknown','unknown'),(op.remote_state,op.outcome))
        self.assertEqual(['exchange'],self.external_calls); self.assertEqual(0,self.raw.deletes)

    def test_receipt_finish_failure_keeps_successful_pointer_protected_and_pending(self):
        item=self.staged(); body=dict(request_key='finish-loss',expected_revision=item['revision'])
        with patch.object(self.attempts,'finish_request',side_effect=StoreError('storage_unavailable')):
            with self.assertRaises(StoreError): self.service.resume_exchange(self.session,item['attempt_id'],body)
        token=self.attempts.read_owned(item['attempt_id'],self.session.session_binding)['token_ref']
        snapshot=self.snapshot(); self.assertIn(token,snapshot.protected_refs)
        self.assertEqual((),snapshot.blockers)
        with self.assertRaises(StoreError): self.service.resume_exchange(self.session,item['attempt_id'],body)
        self.assertEqual(['exchange'],self.external_calls); self.assertEqual(0,self.raw.deletes)

    def test_refresh_keeps_guard_until_request_receipt_is_finished(self):
        self.connected(); entered=threading.Event(); release=threading.Event()
        finish=self.attempts.finish_request
        def pause(*args,**kwargs):
            self.probe(); entered.set()
            if not release.wait(5): raise AssertionError('finish release missing')
            return finish(*args,**kwargs)
        with ThreadPoolExecutor(1) as pool, patch.object(self.attempts,'finish_request',side_effect=pause):
            future=pool.submit(self.service.refresh,self.session,'personal.youtube',dict(request_key='refresh-wait',expected_base_revision='base',expected_connection_revision=1))
            try:
                self.assertTrue(entered.wait(5))
                with self.assertRaises(WorkspaceError) as raised:
                    with oauth_write_guard(self.context,timeout=0): pass
                self.assertEqual('oauth_workspace_busy',raised.exception.code)
            finally: release.set()
            self.assertEqual('connected',future.result(timeout=5)['state'])

    def test_callback_claim_and_finalization_are_guarded(self):
        claim=self.attempts.claim_callback; finalize=self.attempts.finalize_callback
        observed=[]
        def check_claim(*args,**kwargs):
            self.probe(); observed.append('claim'); return claim(*args,**kwargs)
        def check_finalize(*args,**kwargs):
            self.probe(); observed.append('finalize'); return finalize(*args,**kwargs)
        with patch.object(self.attempts,'claim_callback',side_effect=check_claim), patch.object(self.attempts,'finalize_callback',side_effect=check_finalize):
            self.staged()
        self.assertEqual(['claim','finalize'],observed)

    def test_remote_revoke_keeps_owned_secret_and_returns_terminal_journal(self):
        self.use_provider('threads'); self.connected(); before=set(self.raw._items)
        result=self.service.revoke(self.session,'personal.youtube',dict(request_key='revoke-owned',expected_base_revision='base',expected_connection_revision=1))
        snapshot=self.snapshot(); op=next(op for op in snapshot.operations.values() if op.kind=='revoke')
        self.assertEqual(('returned','referenced'),(op.remote_state,op.outcome))
        self.assertEqual('revoked',result['state']); self.assertEqual(before,set(self.raw._items))
        self.assertEqual((),snapshot.blockers); self.assertEqual(0,self.raw.deletes)

    def test_completed_start_retry_reconstructs_url_without_new_operation_or_stage(self):
        first,state=self.start(); before=self.snapshot(); addresses=set(self.raw._items)
        self.service=self.make_service()
        second=self.service.start(self.session,self.body())
        after=self.snapshot()
        self.assertEqual(first,second); self.assertEqual(addresses,set(self.raw._items))
        self.assertEqual(before.journal_revision,after.journal_revision)
        self.assertEqual(before.graph_revision,after.graph_revision)
        self.assertEqual(1,len(after.operations)); self.assertEqual([],self.external_calls)

    def test_corrupt_owned_envelope_never_falls_back_to_legacy_backend(self):
        self.start()
        address=next(iter(self.raw._items)); self.raw._items[address]=b'corrupt'
        with patch.object(self.vault,'get',side_effect=AssertionError('legacy fallback')):
            with self.assertRaises(CredentialError): self.service.start(self.session,self.body())
        self.assertEqual(0,self.raw.deletes)

    def test_client_secret_stays_legacy_read_only(self):
        client=CredentialRef('autosns.oauth','personal','youtube','personal.youtube',1,'client')
        self.vault.put(client,b'legacy-client-secret')
        self.registration=replace(self.registration,client_secret_ref=client)
        self.service=self.make_service()
        item=self.staged(); original=self.provider.exchange
        def verify_secret(attempt,code,secret,**kwargs):
            self.assertEqual('legacy-client-secret',secret)
            return original(attempt,code,secret,**kwargs)
        with patch.object(self.provider,'exchange',side_effect=verify_secret), \
             patch.object(self.vault,'put',side_effect=AssertionError('legacy write')), \
             patch.object(self.vault,'delete',side_effect=AssertionError('legacy delete')):
            result=self.service.resume_exchange(self.session,item['attempt_id'],dict(request_key='with-client',expected_revision=item['revision']))
        self.assertEqual('token_exchanged',result['state'])
        self.assertEqual(b'legacy-client-secret',self.vault.get(client))
        self.assertNotIn(b'legacy-client-secret',Path(self.tmp.name,'oauth.sqlite3').read_bytes())

    def test_refresh_pointer_failure_retains_old_and_staged_credentials_without_replay(self):
        self.connected(); old=self.connections_store.snapshot().connections['personal.youtube']['credential_ref']
        body=dict(request_key='refresh-cas-fail',expected_base_revision='base',expected_connection_revision=1)
        with patch.object(self.connections_store,'finish_connection_operation',side_effect=StoreError('storage_unavailable')):
            with self.assertRaises(StoreError): self.service.refresh(self.session,'personal.youtube',body)
        row=self.connections_store.snapshot().connections['personal.youtube']
        snapshot=self.snapshot(); op=next(op for op in snapshot.operations.values() if op.kind=='refresh')
        self.assertEqual('unknown',row['state']); self.assertEqual(old,row['credential_ref'])
        self.assertEqual(('unknown','unknown'),(op.remote_state,op.outcome))
        staged=[s for s in snapshot.stages if s.operation_id==op.operation_id]
        self.assertEqual(1,len(staged)); self.assertIn(staged[0].owned_ref,snapshot.protected_refs)
        with self.assertRaises(StoreError): self.service.refresh(self.session,'personal.youtube',body)
        self.assertEqual(1,self.external_calls.count('refresh')); self.assertEqual(0,self.raw.deletes)
        self.assertEqual((),snapshot.blockers)

    def test_revoke_response_record_loss_keeps_old_ref_and_does_not_retry(self):
        self.use_provider('threads'); self.connected()
        old=self.connections_store.snapshot().connections['personal.youtube']['credential_ref']
        body=dict(request_key='revoke-return-loss',expected_base_revision='base',expected_connection_revision=1)
        with patch.object(self.stages,'mark_remote_returned',side_effect=StoreError('storage_unavailable')):
            with self.assertRaises(StoreError): self.service.revoke(self.session,'personal.youtube',body)
        row=self.connections_store.snapshot().connections['personal.youtube']
        self.assertEqual('unknown',row['state']); self.assertEqual(old,row['credential_ref'])
        with self.assertRaises(StoreError): self.service.revoke(self.session,'personal.youtube',body)
        self.assertEqual(1,self.external_calls.count('revoke')); self.assertEqual(0,self.raw.deletes)
        self.assertEqual((),self.snapshot().blockers)

    def test_concurrent_disconnect_cannot_resurrect_pointer_after_refresh(self):
        self.connected(); entered=threading.Event(); release=threading.Event(); attempting=threading.Event()
        second=self.make_service()
        @contextmanager
        def competing_guard():
            attempting.set()
            with oauth_write_guard(self.context): yield
        second._write_guard=competing_guard
        def pause():
            entered.set()
            if not release.wait(5): raise AssertionError('provider release missing')
        self.provider.on_refresh=pause
        with ThreadPoolExecutor(2) as pool:
            rotating=pool.submit(self.service.refresh,self.session,'personal.youtube',dict(request_key='rotation',expected_base_revision='base',expected_connection_revision=1))
            try:
                self.assertTrue(entered.wait(5))
                disconnecting=pool.submit(second.disconnect_local,self.session,'personal.youtube',dict(request_key='disconnect-race',expected_base_revision='base',expected_connection_revision=1))
                self.assertTrue(attempting.wait(5))
            finally: release.set()
            self.assertEqual('connected',rotating.result(timeout=5)['state'])
            with self.assertRaises(StoreError): disconnecting.result(timeout=5)
        row=self.connections_store.snapshot().connections['personal.youtube']
        result=self.service.disconnect_local(self.session,'personal.youtube',dict(request_key='disconnect-latest',expected_base_revision='base',expected_connection_revision=row['revision']))
        self.assertEqual('disconnected',result['state']); self.assertEqual(0,self.raw.deletes)

    def test_callback_race_has_one_stage_operation_and_no_remote_calls(self):
        _,state=self.start(); barrier=threading.Barrier(2)
        def call():
            barrier.wait(timeout=5)
            try:
                self.service.receive_callback('youtube',dict(state=state,code='secret-code'),self.callback)
                return True
            except StoreError: return False
        with ThreadPoolExecutor(2) as pool:
            results=[pool.submit(call) for _ in range(2)]
            self.assertEqual(1,sum(future.result(timeout=5) for future in results))
        snapshot=self.snapshot()
        self.assertEqual(1,len([op for op in snapshot.operations.values() if op.kind=='callback']))
        self.assertEqual([],self.external_calls); self.assertEqual(0,self.raw.deletes)
        self.assertEqual((),snapshot.blockers)


if __name__=='__main__': unittest.main()
