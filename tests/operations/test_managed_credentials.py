"""소유 자격 읽기는 메모리 vault와 임시 owner marker만 사용한다."""
from contextlib import contextmanager
from dataclasses import FrozenInstanceError,replace
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
import threading
import unittest
from common.operations.content_store import StoreError
from common.operations.managed_connections import ManagedSnapshot
from common.operations.managed_credentials import ManagedCredentialResolver
from common.operations.models import Registry,Connection,freeze
from common.operations.oauth_models import CredentialRef
from common.operations.oauth_stage_models import OwnedCredentialRef
from common.operations.oauth_stage_backend import OwnedStageBackend,MemoryScopedRawBackend
from common.operations.oauth_workspace import initialize_workspace_owner,oauth_write_guard,require_oauth_write_guard

NOW=datetime(2026,11,2,tzinfo=timezone.utc)
SCOPE='https://www.googleapis.com/auth/youtube.readonly'
TOKEN=dict(access_token='fixture-access-private',refresh_token='fixture-refresh-private',token_type='Bearer',expires_at=(NOW+timedelta(hours=1)).isoformat(),scopes=[SCOPE])

class ManagedCredentialTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)/'workspace'
        self.context=initialize_workspace_owner(self.root);self.raw=MemoryScopedRawBackend();self.backend=OwnedStageBackend(self.context,self.raw)
        self.ref=OwnedCredentialRef(CredentialRef('autosns.oauth','personal','youtube','personal.youtube',1,'token'),self.context.owner.workspace_id,self.context.owner.root_binding,'token-stage')
        self.reference='oauth:personal:youtube:personal.youtube:1'
        self.row=dict(connection_id='personal.youtube',account_id='personal',platform='youtube',provider_id='youtube',state='connected',target_id='channel',provider_subject='channel',checked_at=NOW.isoformat(),base_revision='base',credential_ref=self.ref,credential_generation=1,revision=1,scopes=[SCOPE],authorization=dict(observed_scopes=[SCOPE],credential_expires_at=TOKEN['expires_at'],read_status='verified',credential_status='active',publication_status='blocked'))
        test=self
        class Store:
            root=test.root
            reads=0
            def snapshot(self):
                self.reads+=1
                return ManagedSnapshot('base',freeze({'personal.youtube':test.row}),freeze({test.reference:test.ref}),test.generation,test.context.owner)
        self.store=Store();self.generation=1;self.reads=0;self.on_read=None
        original=self.backend.read_owned
        def read(ref):
            self.reads+=1;require_oauth_write_guard(self.root,self.context.owner)
            data=original(ref)
            if self.on_read:self.on_read()
            return data
        self.backend.read_owned=read
        self.registry=Registry('base',{'personal':{},'dept':{}},{},{},{'personal.youtube':Connection('personal.youtube','personal','youtube',target_id='channel')},{},{},{})
        self.put(TOKEN)
    def put(self,token):
        from common.operations.oauth_stage_backend import scoped_address
        if scoped_address(self.ref) in self.raw._items:self.raw.delete(scoped_address(self.ref))
        self.backend.put_owned(self.ref,json.dumps(token).encode() if not isinstance(token,bytes) else token)
    def resolver(self,**changes):
        values=dict(connection_store=self.store,owned_backend=self.backend,workspace_context=self.context,registry_supplier=lambda:self.registry,clock=lambda:NOW);values.update(changes)
        return ManagedCredentialResolver(**values)
    def use(self,**changes):
        values=dict(account_id='personal',platform='youtube',scope='read',target_id='channel');values.update(changes)
        return self.resolver().use(self.reference,**values)
    def test_constructor_inert_and_read_yields_private_frozen_bound_credential(self):
        resolver=self.resolver();self.assertEqual(self.store.reads,0);self.assertEqual(self.reads,0)
        with resolver.use(self.reference,account_id='personal',platform='youtube',scope='read',target_id='channel') as result:
            require_oauth_write_guard(self.root,self.context.owner)
            self.assertEqual(result.bundle.access_token,TOKEN['access_token']);self.assertEqual(result.target_id,'channel')
            self.assertEqual((result.account_id,result.platform,result.connection_id,result.generation,result.scope,result.reference,result.provider_id),('personal','youtube','personal.youtube',1,'read',self.reference,'youtube'))
            self.assertEqual(result.to_dict(),{});self.assertNotIn(TOKEN['access_token'],repr(result))
            with self.assertRaises(FrozenInstanceError):result.generation=2
        self.assertEqual(self.reads,1);self.assertGreaterEqual(self.store.reads,2)
    def test_publication_always_blocked_even_if_not_checked_and_scope_present(self):
        self.row['authorization']['publication_status']='not_checked'
        with self.assertRaises(StoreError) as caught:
            with self.use(scope='publication'):self.fail('publication forbidden')
        self.assertEqual(caught.exception.code,'oauth_publication_unverified');self.assertEqual(self.reads,0)
    def test_wrong_account_platform_target_and_reference_are_rejected_before_vault(self):
        for changes in ({'account_id':'dept'},{'platform':'blogger'},{'target_id':'other'},{'scope':'arbitrary'}):
            with self.assertRaises(StoreError):
                with self.use(**changes):self.fail('invalid binding')
        with self.assertRaises(StoreError):
            with self.resolver().use('oauth:personal:youtube:personal.youtube:0',account_id='personal',platform='youtube',scope='read'):pass
        self.assertEqual(self.reads,0)
    def test_inactive_unverified_lease_or_legacy_reference_rejected(self):
        for changes in ({'state':'disconnected'},{'operation_lease':{}},{'credential_generation':2},{'provider_id':'blogger'},{'credential_ref':self.ref.ref}):
            original=dict(self.row);self.row.update(changes)
            with self.assertRaises(StoreError):
                with self.use():self.fail('invalid binding')
            self.row=original
        for field,value in (('credential_status','unknown'),('read_status','not_checked'),('observed_scopes',None)):
            original=self.row['authorization'][field];self.row['authorization'][field]=value
            with self.assertRaises(StoreError):
                with self.use():pass
            self.row['authorization'][field]=original
        self.assertEqual(self.reads,0)
    def test_workspace_foreign_owner_or_missing_marker_rejected(self):
        other=initialize_workspace_owner(self.root.parent/'other');foreign=OwnedStageBackend(other,self.raw)
        with self.assertRaises(StoreError):self.resolver(owned_backend=foreign)
        self.ref=replace(self.ref,workspace_id=other.owner.workspace_id,root_binding=other.owner.root_binding);self.row['credential_ref']=self.ref
        with self.assertRaises(StoreError):
            with self.use():pass
        self.assertEqual(self.reads,0)
    def test_expired_auth_and_bundle_or_missing_expiry_fail_closed(self):
        for expiry in (None,(NOW-timedelta(seconds=1)).isoformat()):
            self.row['authorization']['credential_expires_at']=expiry
            with self.assertRaises(StoreError):
                with self.use():pass
        self.row['authorization']['credential_expires_at']=TOKEN['expires_at']
        for expiry in (None,(NOW-timedelta(seconds=1)).isoformat()):
            self.put({**TOKEN,'expires_at':expiry})
            with self.assertRaises(StoreError):
                with self.use():pass
    def test_bundle_scope_must_be_observed_and_known_without_union(self):
        for scopes in ([],['unapproved'],[SCOPE,SCOPE]):
            self.put({**TOKEN,'scopes':scopes})
            with self.assertRaises(StoreError):
                with self.use():pass
        self.put(TOKEN);self.row['authorization']['observed_scopes']=[]
        with self.assertRaises(StoreError):
            with self.use():pass
    def test_bounded_exact_token_codec_rejects_duplicate_extra_nonbearer_invalid_json(self):
        duplicate=json.dumps(TOKEN)[:-1]+',"token_type":"Bearer"}'
        for payload in (duplicate.encode(),{**TOKEN,'extra':'private'},{**TOKEN,'token_type':'Basic'},b'x'*65537,b'not-json',json.dumps({**TOKEN,'scopes':[float('nan')]}).encode()):
            self.put(payload)
            with self.assertRaises(StoreError) as caught:
                with self.use():pass
            self.assertNotIn('fixture-access-private',str(caught.exception));self.assertEqual(caught.exception.code,'oauth_credential_invalid')
    def test_postread_rotation_disconnect_and_base_change_are_rejected(self):
        for change in (lambda:self.row.update(state='disconnected'),lambda:setattr(self,'generation',2),lambda:setattr(self,'registry',replace(self.registry,revision='other'))):
            self.on_read=change
            with self.assertRaises(StoreError) as caught:
                with self.use():pass
            self.assertEqual(caught.exception.code,'credential_changed')
            self.row['state']='connected';self.generation=1;self.registry=replace(self.registry,revision='base')
    def test_guard_is_held_through_sdk_use_and_rotation_waits(self):
        entered=threading.Event();finished=threading.Event()
        def writer():
            entered.set()
            with oauth_write_guard(self.context):finished.set()
        with self.use():
            thread=threading.Thread(target=writer);thread.start();self.assertTrue(entered.wait(2));self.assertFalse(finished.wait(.05))
        thread.join(2);self.assertFalse(thread.is_alive());self.assertTrue(finished.is_set())
    def test_no_raw_resolve_or_secret_serialization_api(self):
        self.assertFalse(hasattr(self.resolver(),'resolve'))
        with self.use() as result:self.assertEqual(result.to_dict(public=True),{})
    def test_token_type_is_case_insensitive_but_does_not_refresh_or_expand_scope(self):
        self.put({**TOKEN,'token_type':'bearer'})
        with self.use() as result:self.assertEqual(result.bundle.token_type,'Bearer');self.assertEqual(set(result.bundle.scopes),{SCOPE})

    def test_managed_connection_not_in_base_is_allowed_without_replacing_existing_target(self):
        self.registry=replace(self.registry,connections={})
        with self.use() as result:self.assertEqual(result.target_id,'channel')
        self.registry=replace(self.registry,connections={'personal.youtube':Connection('personal.youtube','personal','youtube',target_id='different')})
        with self.assertRaises(StoreError):
            with self.use():pass
        self.registry=replace(self.registry,connections={'personal.youtube':Connection('personal.youtube','personal','youtube',target_id=None)})
        with self.use() as result:self.assertEqual(result.target_id,'channel')

    def test_missing_owner_marker_never_reads_vault_or_recreates_owner(self):
        from common.operations.oauth_workspace import OWNER_MARKER_NAME
        marker=self.root/OWNER_MARKER_NAME;marker.unlink()
        with self.assertRaises(StoreError) as caught:
            with self.use():pass
        self.assertEqual(caught.exception.code,'credential_owner_mismatch');self.assertEqual(self.reads,0)
        self.assertFalse(marker.exists())

    def test_token_expiring_during_owned_read_is_not_yielded(self):
        self.put({**TOKEN,'expires_at':(NOW+timedelta(minutes=1)).isoformat()})
        current=[NOW];self.on_read=lambda:current.__setitem__(0,NOW+timedelta(minutes=2))
        with self.assertRaises(StoreError):
            with self.resolver(clock=lambda:current[0]).use(self.reference,account_id='personal',platform='youtube',scope='read'):pass
