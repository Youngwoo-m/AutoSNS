"""Owned schema의 실제 SQLite 통합과 보수적 참조 graph."""
from contextlib import closing
import importlib
import json
import sqlite3
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from common.operations.content_store import StoreError, ConflictError
from common.operations.oauth_models import CredentialRef, AttemptContext
from common.operations.oauth_stage_models import OwnedCredentialRef
from common.operations.oauth_store import OAuthAttemptStore
from common.operations.oauth_workspace import initialize_workspace_owner


class StageStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.context=initialize_workspace_owner(self.root)
        self.now=datetime(2026,11,2,tzinfo=timezone.utc)
        self.attempts=OAuthAttemptStore(self.root,lambda:self.now); self.attempts.initialize()

    def api(self):
        try: return importlib.import_module('common.operations.oauth_stage_store')
        except ModuleNotFoundError: self.fail('durable owned stage store is required')

    def guard(self):
        from common.operations.oauth_workspace import oauth_write_guard
        return oauth_write_guard(self.context)

    def migrate(self):
        api=self.api()
        with self.guard(): api.migrate_to_owned_schema(self.context)
        return api.OAuthStageStore(self.context,lambda:self.now)

    def ref(self,stage='token-stage',kind='token',generation=1):
        return OwnedCredentialRef(CredentialRef('autosns.oauth','personal','youtube','conn',generation,kind),self.context.owner.workspace_id,self.context.owner.root_binding,stage)

    def attempt(self):
        context=AttemptContext('user','binding','personal','youtube','conn','base',0,('read',),'https://test/cb','client',1,'ev')
        return self.attempts.create_attempt(context,'a'*64,self.now+timedelta(minutes=10))

    def test_schema1_reads_do_not_migrate_and_initialize_preserves_schema2(self):
        before=(self.root/'oauth.sqlite3').read_bytes()
        self.assertEqual([],self.attempts.list_owned('binding'))
        self.assertEqual(before,(self.root/'oauth.sqlite3').read_bytes())
        self.migrate(); self.attempts.initialize()
        with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db, db: self.assertEqual(2,db.execute('PRAGMA user_version').fetchone()[0])

    def test_journal_intent_is_durable_cas_and_requires_real_operation(self):
        store=self.migrate(); ref=self.ref()
        with self.guard():
            with self.assertRaises(StoreError): store.begin_stage(self.context.owner,ref,'missing',0)
            op=store.begin_operation('callback',local_only=True)
            stage=store.begin_stage(self.context.owner,ref,op.operation_id,0)
            self.assertEqual('intent',store.recovery_snapshot(self.context.owner).stages[0].state)
            stored=store.mark_stored(stage.stage_id,stage.revision)
            with self.assertRaises(ConflictError): store.mark_stored(stage.stage_id,stage.revision)
            self.assertEqual('stored',stored.state)
        self.assertEqual(ref,self.api().OAuthStageStore(self.context).recovery_snapshot(self.context.owner).stages[0].owned_ref)
        self.assertNotIn(self.context.key_provider.get_key().hex().encode(),(self.root/'oauth.sqlite3').read_bytes())

    def test_operation_cas_cannot_promote_remote_unknown_to_unused(self):
        store=self.migrate()
        with self.guard():
            op=store.begin_operation('refresh')
            op=store.mark_remote_in_flight(op.operation_id,op.revision)
            with self.assertRaises(ConflictError): store.mark_remote_returned(op.operation_id,1)
            op=store.mark_operation_unknown(op.operation_id,op.revision)
            with self.assertRaises(ConflictError): store.finish_operation(op.operation_id,op.revision,'unused')
            self.assertEqual('unknown',store.read_operation(op.operation_id).outcome)

    def test_direct_writer_requires_guard_and_attempt_only_bumps_graph(self):
        store=self.migrate(); before=store.recovery_snapshot(self.context.owner)
        with self.assertRaises(Exception) as caught: self.attempt()
        self.assertEqual('oauth_guard_required',str(caught.exception))
        with self.guard(): self.attempt()
        after=store.recovery_snapshot(self.context.owner)
        self.assertGreater(after.graph_revision,before.graph_revision)
        self.assertEqual((),after.blockers)  # new attempt does not require connection row

    def test_unknown_payload_and_dangling_edge_block_entire_snapshot(self):
        store=self.migrate()
        with self.guard(): item=self.attempt()
        with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db, db:
            db.execute('UPDATE oauth_attempts SET payload=?',('{"future_secret_ref":{}}',))
        self.assertTrue(store.recovery_snapshot(self.context.owner).blockers)

    def test_owned_callback_token_proposal_confirm_reopen_refresh_roundtrip(self):
        from common.operations.managed_connections import ManagedConnectionStore, credential_catalog
        store=self.migrate(); managed=ManagedConnectionStore(self.root,lambda:self.now)
        def stage(kind,generation=1):
            op=store.begin_operation('callback',local_only=True)
            ref=self.ref(kind+str(generation),kind,generation)
            record=store.begin_stage(self.context.owner,ref,op.operation_id,0)
            store.mark_stored(record.stage_id,record.revision)
            return ref
        with self.guard():
            item=self.attempt(); code=stage('code'); ticket=stage('ticket')
            claim=self.attempts.claim_callback('a'*64,'youtube')
            item=self.attempts.finalize_callback(claim,code,ticket,self.now+timedelta(seconds=60))
            self.assertEqual(code,item['code_ref'])
            item=self.attempts.claim_resume(item['attempt_id'],'binding',item['revision'])
            token=stage('token'); item=self.attempts.update_attempt(item['attempt_id'],'binding',item['revision'],'token_exchanged',{'token_ref':token})
            proposal=dict(connection_id='conn',account_id='personal',platform='youtube',base_revision='base',target_id='target',provider_subject='subject',credential_ref=token,scopes=('read',),checked_at=self.now.isoformat())
            saved=managed.create_target_proposal(item['attempt_id'],'binding',item['revision'],proposal)
            confirm=store.begin_operation('confirm',local_only=True)
            saved=store.bind_operation('proposal',saved['proposal_id'],confirm.operation_id,0)
            self.assertIsNotNone(saved)
            managed.confirm_target(saved,'base',0)
            reopened=ManagedConnectionStore(self.root,lambda:self.now)
            snapshot=reopened.snapshot(); self.assertEqual(token,snapshot.connections['conn']['credential_ref'])
            self.assertEqual(token,next(iter(credential_catalog(snapshot).values()))['credential_ref'])
            lease=reopened.claim_connection_operation('conn','base',1,'refresh')
            self.assertEqual(token,lease['credential_ref'])
            operation=store.begin_operation('refresh')
            lease=store.bind_operation('lease','conn',operation.operation_id,lease['connection_revision'])
            self.assertIsNotNone(lease)
            refreshed=stage('token',2)
            self.assertEqual(refreshed,reopened.finish_connection_operation(lease,new_ref=refreshed).connections['conn']['credential_ref'])
            self.assertEqual(3,self.attempts.reserve_generation('autosns.oauth','personal','youtube','conn'))
        graph=store.recovery_snapshot(self.context.owner)
        self.assertFalse(graph.blockers)
        self.assertTrue({code,ticket,token,refreshed}<=graph.protected_refs)
        self.assertTrue(all(s.state=='referenced' for s in graph.stages))

    def stored(self,store,kind='token',stage='stage',operation=None):
        op=operation or store.begin_operation('callback',local_only=True)
        ref=self.ref(stage,kind)
        record=store.begin_stage(self.context.owner,ref,op.operation_id,0)
        return ref,store.mark_stored(record.stage_id,record.revision),op

    def test_foreign_owned_attempt_read_is_rejected(self):
        from dataclasses import replace
        from common.operations.oauth_stage_models import encode_stored_ref
        store=self.migrate()
        with self.guard(): item=self.attempt()
        with TemporaryDirectory() as other:
            foreign=initialize_workspace_owner(other).owner
            ref=replace(self.ref(kind='verifier'),workspace_id=foreign.workspace_id,root_binding=foreign.root_binding)
            with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db,db:
                db.execute('UPDATE oauth_attempts SET payload=?',(json.dumps({'verifier_ref':encode_stored_ref(ref)}),))
            with self.assertRaises(StoreError): self.attempts.read_owned(item['attempt_id'],'binding')

    def test_missing_journal_pointer_rolls_back_entire_attempt_update(self):
        store=self.migrate()
        with self.guard():
            item=self.attempt()
            before=store.recovery_snapshot(self.context.owner).graph_revision
            with self.assertRaises(StoreError): self.attempts.bind_verifier(item['attempt_id'],'binding',1,self.ref(kind='verifier'))
            self.assertEqual(1,self.attempts.read_owned(item['attempt_id'],'binding')['revision'])
            self.assertEqual(before,store.recovery_snapshot(self.context.owner).graph_revision)

    def test_unknown_versions_and_dangling_proposal_are_blockers(self):
        store=self.migrate()
        with self.guard(): ref,record,op=self.stored(store)
        with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db,db:
            db.execute('UPDATE oauth_stages SET payload_version=99')
        self.assertIn('invalid_stage',store.recovery_snapshot(self.context.owner).blockers)
        with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db,db:
            db.execute('UPDATE oauth_stages SET payload_version=1')
            from common.operations.oauth_stage_models import encode_stored_ref
            payload=dict(connection_id='conn',account_id='personal',platform='youtube',base_revision='base',target_id='target',provider_subject='subject',scopes=['read'],checked_at=self.now.isoformat(),credential_ref=encode_stored_ref(ref))
            db.execute('INSERT INTO oauth_proposals VALUES(?,?,?,?,0)',('proposal','missing','binding',json.dumps(payload)))
        self.assertIn('dangling_attempt',store.recovery_snapshot(self.context.owner).blockers)

    def test_pending_receipt_and_unknown_operation_protect_indirect_stages(self):
        store=self.migrate()
        with self.guard():
            receipt=self.attempts.claim_request('binding','start','key','a'*64)
            op=store.begin_operation('start',receipt_id=receipt['id'],local_only=True)
            ref,record,_=self.stored(store,operation=op)
            op=store.finish_operation(op.operation_id,op.revision,'unused')
            graph=store.recovery_snapshot(self.context.owner)
            self.assertIn(ref,graph.protected_refs)
            self.assertIn(op.operation_id,graph.pending_receipts)
            self.attempts.finish_request(receipt['id'],1,{'state':'error'})
            self.assertNotIn(ref,store.recovery_snapshot(self.context.owner).protected_refs)
            unknown=store.begin_operation('refresh')
            other,_,_=self.stored(store,stage='other',operation=unknown)
            unknown=store.mark_remote_in_flight(unknown.operation_id,unknown.revision)
            store.mark_operation_unknown(unknown.operation_id,unknown.revision)
            self.assertIn(other,store.recovery_snapshot(self.context.owner).protected_refs)

    def test_owner_copy_database_and_schema0_unknown_are_rejected(self):
        import shutil
        store=self.migrate()
        with TemporaryDirectory() as other:
            other_context=initialize_workspace_owner(other)
            shutil.copyfile(self.root/'oauth.sqlite3',Path(other)/'oauth.sqlite3')
            with self.assertRaises(StoreError): self.api().OAuthStageStore(other_context).recovery_snapshot(other_context.owner)
        with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db,db: db.execute('PRAGMA user_version=99')
        with self.guard(),self.assertRaises(StoreError): self.api().migrate_to_owned_schema(self.context)
        with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db,db: db.execute('PRAGMA user_version=0')
        with self.guard(),self.assertRaises(StoreError): self.api().migrate_to_owned_schema(self.context)

    def test_migration_failure_rolls_back_ddl_and_preserves_unrelated_bytes(self):
        for name in ('operations.sqlite3','metrics.sqlite3','registry.json'):
            (self.root/name).write_bytes(b'unrelated sentinel')
        with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db,db:
            db.execute('CREATE TABLE oauth_stages(collision TEXT)')
        with self.guard(),self.assertRaises(StoreError): self.api().migrate_to_owned_schema(self.context)
        with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db:
            self.assertEqual(1,db.execute('PRAGMA user_version').fetchone()[0])
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='oauth_workspace_meta'").fetchone())
        for name in ('operations.sqlite3','metrics.sqlite3','registry.json'):
            self.assertEqual(b'unrelated sentinel',(self.root/name).read_bytes())

    def test_stage_event_enum_and_deleted_cas_require_explicit_delete_intent(self):
        store=self.migrate()
        with self.guard():
            ref,record,op=self.stored(store)
            store.finish_operation(op.operation_id,op.revision,'unused')
            with self.assertRaises(ConflictError): store.mark_deleted(record.stage_id,record.revision)
            with self.assertRaises(StoreError): store.record_recovery_event(record.stage_id,record.revision,'secret from native')
            store.record_recovery_event(record.stage_id,record.revision,'delete_intent')
            deleted=store.mark_deleted(record.stage_id,record.revision)
            self.assertEqual('deleted',deleted.state)
            with self.assertRaises(ConflictError): store.mark_deleted(record.stage_id,record.revision)

    def test_legacy_refs_are_protected_without_fabricated_operation(self):
        # schema1 rows retain their complete logical identities after migration.
        item=self.attempt(); legacy=CredentialRef('autosns.oauth','personal','youtube','conn',1,'verifier')
        self.attempts.bind_verifier(item['attempt_id'],'binding',1,legacy)
        store=self.migrate(); graph=store.recovery_snapshot(self.context.owner)
        self.assertIn(legacy,graph.protected_refs); self.assertIn(legacy,graph.legacy_protected)
        self.assertEqual({},dict(graph.operations)); self.assertFalse(graph.blockers)

    def test_invalid_graph_revision_and_operation_version_fail_closed(self):
        store=self.migrate()
        with self.guard():
            ref,record,op=self.stored(store)
            graph=store.recovery_snapshot(self.context.owner)
            with self.assertRaises(ConflictError): store.mark_referenced(record.stage_id,record.revision,graph.graph_revision-1)
        with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db,db:
            db.execute('UPDATE oauth_operations SET payload_version=5')
        self.assertIn('invalid_operation',store.recovery_snapshot(self.context.owner).blockers)

    def test_unreferenced_owned_generation64_is_reserved_after_reopen(self):
        store=self.migrate()
        with self.guard():
            op=store.begin_operation('refresh')
            ref=self.ref(generation=64)
            stage=store.begin_stage(self.context.owner,ref,op.operation_id,0)
            store.mark_stored(stage.stage_id,stage.revision)
            self.assertEqual(65,OAuthAttemptStore(self.root).reserve_generation('autosns.oauth','personal','youtube','conn'))

    def test_bind_operation_returns_cas_updated_attempt_and_receipt(self):
        store=self.migrate()
        with self.guard():
            item=self.attempt(); op=store.begin_operation('callback',local_only=True)
            with self.assertRaises(ConflictError): store.bind_operation('attempt',item['attempt_id'],op.operation_id,99)
            bound=store.bind_operation('attempt',item['attempt_id'],op.operation_id,item['revision'])
            self.assertIsNotNone(bound)
            self.assertEqual(item['revision']+1,bound['revision'])
            self.assertEqual(op.operation_id,bound['operation_id'])
            self.assertEqual(op.revision,store.read_operation(op.operation_id).revision)
            receipt=self.attempts.claim_request('binding','refresh:conn','refresh-key','b'*64)
            refresh=store.begin_operation('refresh')
            with self.assertRaises(ConflictError): store.bind_operation('receipt',receipt['id'],refresh.operation_id,99)
            receipt=store.bind_operation('receipt',receipt['id'],refresh.operation_id,receipt['revision'])
            self.assertEqual(2,receipt['revision'])
            self.assertEqual(2,store.read_operation(refresh.operation_id).revision)
            self.attempts.finish_request(receipt['id'],receipt['revision'],{'state':'error'})
            self.assertFalse(store.recovery_snapshot(self.context.owner).blockers)

    def test_future_attempt_state_and_hidden_nested_ref_block_graph(self):
        store=self.migrate()
        with self.guard(): self.attempt()
        with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db,db:
            db.execute("UPDATE oauth_attempts SET state='future_state'")
        self.assertTrue(store.recovery_snapshot(self.context.owner).blockers)

    def test_owned_journal_cannot_be_written_into_schema1(self):
        item=self.attempt()
        with self.assertRaises(StoreError): self.attempts.bind_verifier(item['attempt_id'],'binding',1,self.ref(kind='verifier'))
        self.assertEqual(1,self.attempts.read_owned(item['attempt_id'],'binding')['revision'])

    def connected(self,store):
        from common.operations.managed_connections import ManagedConnectionStore
        managed=ManagedConnectionStore(self.root,lambda:self.now)
        item=self.attempt()
        refs={kind:self.stored(store,kind,kind)[0] for kind in ('code','ticket','token')}
        claim=self.attempts.claim_callback('a'*64,'youtube')
        item=self.attempts.finalize_callback(claim,refs['code'],refs['ticket'],self.now+timedelta(seconds=60))
        item=self.attempts.claim_resume(item['attempt_id'],'binding',item['revision'])
        item=self.attempts.update_attempt(item['attempt_id'],'binding',item['revision'],'token_exchanged',{'token_ref':refs['token']})
        proposal=dict(connection_id='conn',account_id='personal',platform='youtube',base_revision='base',target_id='target',provider_subject='subject',credential_ref=refs['token'],scopes=('read',),checked_at=self.now.isoformat())
        saved=managed.create_target_proposal(item['attempt_id'],'binding',item['revision'],proposal)
        managed.confirm_target(saved,'base',0)
        return managed,item,refs

    def test_every_attempt_ref_completed_expired_and_consumed_proposal_is_protected(self):
        store=self.migrate()
        with self.guard():
            item=self.attempt()
            receipt=self.attempts.claim_request('binding','start','key','a'*64)
            state_key=self.stored(store,'state_key','state-key')[0]
            item=self.attempts.bind_state_key(item['attempt_id'],'binding',item['revision'],state_key,receipt['id'])
            verifier=self.stored(store,'verifier','verifier')[0]
            item=self.attempts.bind_verifier(item['attempt_id'],'binding',item['revision'],verifier)
            code=self.stored(store,'code','code')[0]; ticket=self.stored(store,'ticket','ticket')[0]
            claim=self.attempts.claim_callback('a'*64,'youtube')
            item=self.attempts.finalize_callback(claim,code,ticket,self.now+timedelta(seconds=60))
            item=self.attempts.claim_resume(item['attempt_id'],'binding',item['revision'])
            token=self.stored(store,'token','token')[0]
            item=self.attempts.update_attempt(item['attempt_id'],'binding',item['revision'],'token_exchanged',{'token_ref':token})
            from common.operations.managed_connections import ManagedConnectionStore
            managed=ManagedConnectionStore(self.root,lambda:self.now)
            p=dict(connection_id='conn',account_id='personal',platform='youtube',base_revision='base',target_id='target',provider_subject='subject',credential_ref=token,scopes=('read',),checked_at=self.now.isoformat())
            saved=managed.create_target_proposal(item['attempt_id'],'binding',item['revision'],p)
            managed.confirm_target(saved,'base',0)
            self.attempts.finish_request(receipt['id'],receipt['revision'],{'state':'connected','attempt_id':item['attempt_id']})
            graph=store.recovery_snapshot(self.context.owner)
            for op in graph.operations.values(): store.finish_operation(op.operation_id,op.revision,'referenced')
            managed.disconnect_local('conn','base',1)
        # Neither active catalog nor clock expiry is an input to the recovery graph.
        store.clock=lambda:self.now+timedelta(days=30)
        graph=store.recovery_snapshot(self.context.owner)
        self.assertEqual({state_key,verifier,code,ticket,token},set(graph.protected_refs))
        self.assertFalse(graph.blockers)

    def test_operation_lease_protects_indirect_unused_stage_until_lease_removed(self):
        store=self.migrate()
        with self.guard():
            managed,item,refs=self.connected(store)
            op=store.begin_operation('refresh')
            orphan,_,_=self.stored(store,stage='orphan',operation=op)
            lease=managed.claim_connection_operation('conn','base',1,'refresh')
            lease=store.bind_operation('lease','conn',op.operation_id,lease['connection_revision'])
            store.finish_operation(op.operation_id,op.revision,'unused')
            graph=store.recovery_snapshot(self.context.owner)
            self.assertIn(orphan,graph.protected_refs); self.assertFalse(graph.blockers)
            self.assertEqual({},dict(managed.snapshot().credential_refs))
            managed.fail_connection_operation(lease)
            self.assertNotIn(orphan,store.recovery_snapshot(self.context.owner).protected_refs)

    def test_malformed_ref_json_and_version_are_global_blockers(self):
        store=self.migrate()
        with self.guard(): self.attempt()
        from common.operations.oauth_stage_models import encode_stored_ref
        wrong_ref=encode_stored_ref(self.ref(kind='code'))
        cases=['[]','{"authorization":null,"authorization":null}',json.dumps({'payload_version':True}),json.dumps({'verifier_ref':wrong_ref}),json.dumps({'verifier_ref':dict(wrong_ref,format='owned_v99')}),json.dumps({'reason':{'hidden_ref':wrong_ref}})]
        for payload in cases:
            with self.subTest(payload_kind=cases.index(payload)):
                with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db,db:
                    db.execute("UPDATE oauth_attempts SET payload=?,state='consent_pending'",(payload,))
                self.assertTrue(store.recovery_snapshot(self.context.owner).blockers)

    def test_unknown_column_and_inconsistent_operation_state_are_blockers(self):
        store=self.migrate()
        with self.guard(): op=store.begin_operation('refresh')
        with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db,db:
            db.execute("UPDATE oauth_operations SET remote_state='in_flight',outcome='unused'")
        self.assertTrue(store.recovery_snapshot(self.context.owner).blockers)
        with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db,db:
            db.execute("UPDATE oauth_operations SET remote_state='not_started',outcome='pending'")
            db.execute('ALTER TABLE oauth_connections ADD COLUMN future_refs TEXT')
        self.assertTrue(store.recovery_snapshot(self.context.owner).blockers)

    def test_stage_delete_intent_rejects_pending_protected_stage(self):
        store=self.migrate()
        with self.guard():
            ref,record,op=self.stored(store)
            with self.assertRaises(ConflictError): store.record_recovery_event(record.stage_id,record.revision,'delete_intent')

    def test_constructor_and_schema1_get_create_no_owner_or_lock(self):
        with TemporaryDirectory() as other:
            root=Path(other); attempts=OAuthAttemptStore(root); attempts.initialize()
            before={p.name:p.read_bytes() for p in root.iterdir()}
            # A supplied context is passive; only explicit validation/migration uses it.
            from dataclasses import replace
            passive=replace(self.context,root=root)
            self.api().OAuthStageStore(passive)
            self.assertEqual([],attempts.list_owned('binding'))
            self.assertEqual(before,{p.name:p.read_bytes() for p in root.iterdir()})
            self.assertFalse((root/'.oauth-workspace-owner.json').exists())
            self.assertFalse((root/'.oauth-workspace.lock').exists())

    def test_owned_backend_intent_stored_and_absent_cleanup_use_exact_journal(self):
        from common.operations.oauth_stage_backend import OwnedStageBackend, MemoryScopedRawBackend
        store=self.migrate(); backend=OwnedStageBackend(self.context,MemoryScopedRawBackend())
        secret=b'private-token-payload-never-in-sqlite'
        with self.guard():
            op=store.begin_operation('callback',local_only=True)
            ref=self.ref(); intent=store.begin_stage(self.context.owner,ref,op.operation_id,0)
            self.assertEqual('intent',store.recovery_snapshot(self.context.owner).stages[0].state)
            backend.put_owned(ref,secret)
            self.assertEqual(secret,backend.read_owned(ref))
            record=store.mark_stored(intent.stage_id,intent.revision)
            store.finish_operation(op.operation_id,op.revision,'unused')
            store.record_recovery_event(record.stage_id,record.revision,'delete_intent')
            backend.delete_owned(ref)
            store.record_recovery_event(record.stage_id,record.revision,'absent')
            self.assertEqual('deleted',store.mark_deleted(record.stage_id,record.revision).state)
        self.assertNotIn(secret,(self.root/'oauth.sqlite3').read_bytes())

    def test_preserved_and_referenced_stage_transitions_use_exact_cas(self):
        store=self.migrate()
        with self.guard():
            ref,record,op=self.stored(store)
            preserved=store.mark_preserved(record.stage_id,record.revision,'locked')
            with self.assertRaises(ConflictError): store.mark_preserved(record.stage_id,record.revision,'locked')
            with self.assertRaises(StoreError): store.mark_preserved(record.stage_id,preserved.revision,'native raw message')
            graph=store.recovery_snapshot(self.context.owner)
            referenced=store.mark_referenced(record.stage_id,preserved.revision,graph.graph_revision)
            self.assertEqual('referenced',referenced.state)
            with self.assertRaises(ConflictError): store.mark_deleted(record.stage_id,referenced.revision)

    def test_receipt_auto_binding_is_bidirectional_and_operation_cas_is_terminal(self):
        store=self.migrate()
        with self.guard():
            receipt=self.attempts.claim_request('binding','refresh:conn','key','a'*64)
            op=store.begin_operation('refresh',receipt_id=receipt['id'])
            self.assertEqual(1,op.revision)
            with self.assertRaises(ConflictError): store.begin_operation('refresh',receipt_id=receipt['id'])
            op=store.mark_remote_in_flight(op.operation_id,op.revision)
            op=store.mark_remote_returned(op.operation_id,op.revision)
            op=store.finish_operation(op.operation_id,op.revision,'unused')
            with self.assertRaises(ConflictError): store.finish_operation(op.operation_id,op.revision,'referenced')
            self.assertEqual('completed',self.attempts.finish_request(receipt['id'],receipt['revision'],{'state':'error'})['status'])
            self.assertFalse(store.recovery_snapshot(self.context.owner).blockers)

    def test_dangling_receipt_proposal_fail_closed_snapshot(self):
        store=self.migrate()
        with self.guard():
            receipt=self.attempts.claim_request('binding','inspect','key','a'*64)
            self.attempts.finish_request(receipt['id'],receipt['revision'],{'state':'target_confirmation','proposal_id':'missing'})
        self.assertIn('dangling_proposal',store.recovery_snapshot(self.context.owner).blockers)

    def test_missing_table_returns_blocked_snapshot(self):
        store=self.migrate()
        with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db,db:
            db.execute('DROP TABLE oauth_proposals')
        self.assertIn('missing_table',store.recovery_snapshot(self.context.owner).blockers)

    def test_lease_old_new_owned_refs_roundtrip_without_unwrapping(self):
        from common.operations.oauth_stage_models import encode_stored_ref
        store=self.migrate()
        with self.guard():
            managed,item,refs=self.connected(store)
            lease=managed.claim_connection_operation('conn','base',1,'refresh')
            op=store.begin_operation('refresh')
            new=self.ref('new-token','token',2)
            record=store.begin_stage(self.context.owner,new,op.operation_id,0)
            store.mark_stored(record.stage_id,record.revision)
            with managed._db(True) as db:
                row=db.execute('SELECT payload FROM oauth_connections WHERE id=?',('conn',)).fetchone()
                payload=json.loads(row[0]); payload['operation_lease']['new_ref']=encode_stored_ref(new)
                db.execute('UPDATE oauth_connections SET payload=? WHERE id=?',(json.dumps(payload),'conn'))
            reloaded=managed.snapshot().connections['conn']['operation_lease']
            self.assertEqual(refs['token'],reloaded['credential_ref']); self.assertEqual(new,reloaded['new_ref'])
            self.assertIn(new,store.recovery_snapshot(self.context.owner).protected_refs)
            refreshed=managed.finish_connection_operation(reloaded,new_ref=new)
            self.assertEqual(new,refreshed.connections['conn']['credential_ref'])

    def test_receipt_result_hidden_ref_and_unknown_json_type_are_blockers(self):
        store=self.migrate()
        with self.guard(): receipt=self.attempts.claim_request('binding','inspect','key','a'*64)
        with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db,db:
            db.execute("UPDATE oauth_request_receipts SET result=?,status='completed'",(json.dumps({'provider_subject':{'hidden_ref':{}}}),))
        self.assertIn('invalid_receipt',store.recovery_snapshot(self.context.owner).blockers)

    def test_recovery_event_retry_is_idempotent_but_revalidates_eligibility(self):
        store=self.migrate()
        with self.guard():
            ref,record,op=self.stored(store)
            store.finish_operation(op.operation_id,op.revision,'unused')
            event=store.record_recovery_event(record.stage_id,record.revision,'delete_intent')
            before=store.recovery_snapshot(self.context.owner)
            self.assertEqual(event,store.record_recovery_event(record.stage_id,record.revision,'delete_intent'))
            after=store.recovery_snapshot(self.context.owner)
            self.assertEqual((before.graph_revision,before.journal_revision),(after.graph_revision,after.journal_revision))
            # The original decision cannot authorize a retry after new uncertainty.
            with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db,db:
                db.execute("UPDATE oauth_operations SET outcome='unknown',remote_state='unknown' WHERE operation_id=?",(op.operation_id,))
            with self.assertRaises(ConflictError): store.record_recovery_event(record.stage_id,record.revision,'delete_intent')
            with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db,db:
                db.execute("UPDATE oauth_operations SET outcome='unused',remote_state='local_only' WHERE operation_id=?",(op.operation_id,))
            self.attempt()
            from common.operations.oauth_stage_models import encode_stored_ref
            with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db,db:
                db.execute('UPDATE oauth_attempts SET payload=?',(json.dumps({'token_ref':encode_stored_ref(ref)}),))
            with self.assertRaises(ConflictError): store.record_recovery_event(record.stage_id,record.revision,'delete_intent')
            with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db,db:
                db.execute("UPDATE oauth_attempts SET payload='{}'")
                self.assertEqual(1,db.execute('SELECT count(*) FROM oauth_recovery_events').fetchone()[0])
            store.mark_preserved(record.stage_id,record.revision,'locked')
            with self.assertRaises(ConflictError): store.record_recovery_event(record.stage_id,record.revision,'delete_intent')

    def test_known_rows_are_fully_parsed_even_without_credential_refs(self):
        store=self.migrate()
        with self.guard(): self.attempt()
        with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db,db:
            db.execute("UPDATE oauth_attempts SET expires_at='future-json-format'")
            db.execute('UPDATE oauth_meta SET generation=-1')
        graph=store.recovery_snapshot(self.context.owner)
        self.assertIn('invalid_attempt',graph.blockers)
        self.assertIn('invalid_managed_meta',graph.blockers)

    def test_successful_migration_preserves_operations3_metrics1_and_registry_bytes(self):
        before={}
        for name,version in (('operations.sqlite3',3),('metrics.sqlite3',1)):
            with closing(sqlite3.connect(self.root/name)) as db,db:
                db.execute('CREATE TABLE sentinel(value TEXT)')
                db.execute('INSERT INTO sentinel VALUES(?)',('existing',))
                db.execute('PRAGMA user_version='+str(version))
            before[name]=(self.root/name).read_bytes()
        (self.root/'registry.json').write_bytes(b'{"registry":"unchanged"}\n')
        before['registry.json']=(self.root/'registry.json').read_bytes()
        self.migrate()
        for name,data in before.items(): self.assertEqual(data,(self.root/name).read_bytes())
        for name,version in (('operations.sqlite3',3),('metrics.sqlite3',1)):
            with closing(sqlite3.connect(self.root/name)) as db:
                self.assertEqual(version,db.execute('PRAGMA user_version').fetchone()[0])

    def assert_malformed_graph_denies_cleanup_without_changes(self,store,record):
        with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db:
            before=tuple(db.iterdump())
            count=db.execute('SELECT count(*) FROM oauth_recovery_events').fetchone()[0]
        with self.assertRaises(ConflictError): store.record_recovery_event(record.stage_id,record.revision,'delete_intent')
        with self.assertRaises(ConflictError): store.mark_deleted(record.stage_id,record.revision)
        graph=store.recovery_snapshot(self.context.owner)
        self.assertTrue(graph.blockers)
        self.assertEqual('stored',next(stage for stage in graph.stages if stage.stage_id==record.stage_id).state)
        with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db:
            self.assertEqual(before,tuple(db.iterdump()))
            self.assertEqual(count,db.execute('SELECT count(*) FROM oauth_recovery_events').fetchone()[0])

    def test_hidden_owned_ref_in_lease_id_blocks_cleanup_before_commit_hook(self):
        from common.operations.oauth_stage_models import encode_stored_ref
        store=self.migrate()
        with self.guard():
            managed,_,_=self.connected(store)
            managed.claim_connection_operation('conn','base',1,'refresh')
            orphan,record,op=self.stored(store,stage='unused-orphan')
            store.finish_operation(op.operation_id,op.revision,'unused')
            store.record_recovery_event(record.stage_id,record.revision,'delete_intent')
            with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db,db:
                payload=json.loads(db.execute('SELECT payload FROM oauth_connections').fetchone()[0])
                payload['operation_lease']['lease_id']={'future_ref':encode_stored_ref(orphan)}
                db.execute('UPDATE oauth_connections SET payload=?',(json.dumps(payload),))
            self.assert_malformed_graph_denies_cleanup_without_changes(store,record)

    def test_connection_missing_required_fields_blocks_cleanup(self):
        store=self.migrate()
        with self.guard():
            self.connected(store)
            _,record,op=self.stored(store,stage='unused-orphan')
            store.finish_operation(op.operation_id,op.revision,'unused')
            store.record_recovery_event(record.stage_id,record.revision,'delete_intent')
            with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db,db:
                db.execute('UPDATE oauth_connections SET payload=?',(json.dumps({'connection_id':'conn','state':'connected'}),))
            self.assert_malformed_graph_denies_cleanup_without_changes(store,record)

    def migration_at_first_boundary(self,boundaries):
        from unittest.mock import patch
        original=sqlite3.connect; armed=[]; calls=[]; errors=[]; api=self.api()
        def connect(*args,**kwargs):
            db=original(*args,**kwargs)
            if not armed:
                armed.append(True)
                def trace(sql):
                    if any(sql.startswith(boundary) for boundary in boundaries):
                        db.set_trace_callback(None); calls.append(sql.split()[0])
                        try:
                            with self.guard(): api.migrate_to_owned_schema(self.context)
                        except Exception as error: errors.append(type(error).__name__)
                db.set_trace_callback(trace)
            return db
        return patch('common.operations.oauth_store.sqlite3.connect',side_effect=connect),calls,errors

    def test_schema1_to2_migration_at_writer_begin_cannot_bypass_guard(self):
        race,calls,errors=self.migration_at_first_boundary(('BEGIN IMMEDIATE',))
        with race,self.assertRaises(Exception) as caught:
            self.attempts.claim_request('binding','start','race-key','a'*64)
        self.assertEqual('oauth_guard_required',str(caught.exception))
        self.assertEqual(['BEGIN'],calls); self.assertEqual([],errors)
        with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db:
            self.assertEqual(2,db.execute('PRAGMA user_version').fetchone()[0])
            self.assertEqual(0,db.execute('SELECT count(*) FROM oauth_request_receipts').fetchone()[0])

    def test_initialize_migration_at_first_transaction_or_ddl_cannot_downgrade(self):
        race,calls,errors=self.migration_at_first_boundary(('BEGIN IMMEDIATE','CREATE TABLE IF NOT EXISTS oauth_attempts'))
        with race: self.attempts.initialize()
        self.assertEqual(1,len(calls)); self.assertEqual([],errors)
        with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db:
            self.assertEqual(2,db.execute('PRAGMA user_version').fetchone()[0])
            self.assertEqual(1,db.execute('SELECT count(*) FROM oauth_workspace_meta').fetchone()[0])

    def test_all_table_shapes_fail_closed_and_preserve_valid_legacy_rows(self):
        store=self.migrate()
        with self.guard():
            managed,_,_=self.connected(store)
            managed.claim_connection_operation('conn','base',1,'refresh')
            _,record,op=self.stored(store,stage='unused-orphan')
            store.finish_operation(op.operation_id,op.revision,'unused')
            event_id=store.record_recovery_event(record.stage_id,record.revision,'delete_intent')
            receipt=self.attempts.claim_request('binding','inspect','strict-key','a'*64)
            with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db:
                connection=json.loads(db.execute('SELECT payload FROM oauth_connections').fetchone()[0])
                proposal=json.loads(db.execute('SELECT payload FROM oauth_proposals').fetchone()[0])
            cases=[]
            for field in ('target_id','scopes','execution_enabled','provider_id','credential_generation'):
                value=dict(connection); value.pop(field)
                cases.append(('connection_missing_'+field,'UPDATE oauth_connections SET payload=?',(json.dumps(value),),'UPDATE oauth_connections SET payload=?',(json.dumps(connection),)))
            value=dict(connection,credential_ref=None); value.pop('operation_lease')
            cases.append(('connected_null_ref','UPDATE oauth_connections SET payload=?',(json.dumps(value),),'UPDATE oauth_connections SET payload=?',(json.dumps(connection),)))
            value=dict(proposal); value.pop('target_id')
            cases.append(('proposal_missing_target','UPDATE oauth_proposals SET payload=?',(json.dumps(value),),'UPDATE oauth_proposals SET payload=?',(json.dumps(proposal),)))
            cases.extend([
                ('receipt_unknown_operation','UPDATE oauth_request_receipts SET operation=? WHERE id=?',('future',receipt['id']),'UPDATE oauth_request_receipts SET operation=? WHERE id=?',('inspect',receipt['id'])),
                ('receipt_bad_hash','UPDATE oauth_request_receipts SET request_hash=? WHERE id=?',('future',receipt['id']),'UPDATE oauth_request_receipts SET request_hash=? WHERE id=?',('a'*64,receipt['id'])),
                ('event_negative_revision','UPDATE oauth_recovery_events SET stage_revision=-1',(),'UPDATE oauth_recovery_events SET stage_revision=?',(record.revision,)),
                ('operation_binary_id','INSERT INTO oauth_operations VALUES(?,?,?,?,?,?,?)',(b'unknown','callback','local_only','unused',1,None,1),'DELETE FROM oauth_operations WHERE operation_id=?',(b'unknown',)),
            ])
            for name,sql,params,undo,undo_params in cases:
                with self.subTest(boundary=name):
                    with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db,db: db.execute(sql,params)
                    try: self.assert_malformed_graph_denies_cleanup_without_changes(store,record)
                    finally:
                        with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db,db:
                            db.execute('DELETE FROM oauth_recovery_events WHERE event_id!=?',(event_id,))
                            db.execute(undo,undo_params)
            self.assertFalse(store.recovery_snapshot(self.context.owner).blockers)

    def test_unlinked_referenced_stage_cannot_authorize_delete_intent(self):
        store=self.migrate()
        with self.guard():
            _,record,op=self.stored(store)
            store.finish_operation(op.operation_id,op.revision,'unused')
            graph=store.recovery_snapshot(self.context.owner)
            referenced=store.mark_referenced(record.stage_id,record.revision,graph.graph_revision)
            with self.assertRaises(ConflictError): store.record_recovery_event(record.stage_id,referenced.revision,'delete_intent')
            with closing(sqlite3.connect(self.root/'oauth.sqlite3')) as db:
                self.assertEqual(0,db.execute('SELECT count(*) FROM oauth_recovery_events').fetchone()[0])

    def test_full_legacy_attempt_proposal_connection_receipt_and_lease_remain_valid(self):
        from tests.operations.test_managed_connections import ManagedTests
        from common.operations.managed_connections import ManagedConnectionStore,credential_catalog
        helper=ManagedTests('test_confirm_snapshot_projection_and_disconnect_preserves_base')
        managed=ManagedConnectionStore(self.root)
        helper.confirm(helper.proposal(),'base',0,store=managed)
        lease=managed.claim_connection_operation('conn','base',1,'refresh')
        legacy_receipt=OAuthAttemptStore(self.root).claim_request('binding','inspect:conn','legacy-key','a'*64)
        store=self.migrate(); graph=store.recovery_snapshot(self.context.owner)
        self.assertFalse(graph.blockers)
        self.assertEqual(3,len(graph.legacy_protected))
        self.assertEqual({},dict(graph.operations)); self.assertEqual((),graph.stages)
        self.assertEqual(lease['credential_ref'],managed.snapshot().connections['conn']['operation_lease']['credential_ref'])
        self.assertEqual({},credential_catalog(managed.snapshot()))
        with self.guard():
            OAuthAttemptStore(self.root).finish_request(legacy_receipt['id'],legacy_receipt['revision'],{'state':'unknown'})
            managed.fail_connection_operation(lease)
        self.assertFalse(store.recovery_snapshot(self.context.owner).blockers)
