import unittest
from tempfile import TemporaryDirectory
from common.operations.managed_connections import ManagedConnectionStore, project_registry, credential_catalog
from common.operations.oauth_models import CredentialRef
from common.operations.models import Registry,Connection
from common.operations.content_store import StoreError

class ManagedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store=ManagedConnectionStore(self.tmp.name); self.store.initialize()
        self.base=Registry('base',{'personal':{},'dept':{}},{'legacy':{'account_id':'personal'}},{},{'conn':Connection('conn','personal','youtube',target_id='target',credential_ref='legacy')},{},{},{})
    def proposal(self):
        return dict(connection_id='conn',account_id='personal',platform='youtube',base_revision='base',target_id='target',target_label='Target',provider_subject='subject',credential_ref=CredentialRef('autosns.oauth','personal','youtube','conn',1,'token'),scopes=('read',),checked_at='2026-01-01T00:00:00+00:00')
    def confirm(self,p,base,revision,provider="youtube"):
        from common.operations.oauth_store import OAuthAttemptStore
        from common.operations.oauth_models import AttemptContext
        from datetime import datetime,timezone,timedelta
        from uuid import uuid4
        import hashlib
        now=datetime.now(timezone.utc); attempts=OAuthAttemptStore(self.tmp.name)
        context=AttemptContext('user','binding','personal',provider,'conn',base,revision,('read',),'https://test/cb','client',1,'ev')
        digest=hashlib.sha256(uuid4().bytes).hexdigest()
        item=attempts.create_attempt(context,digest,(now+timedelta(minutes=10)).isoformat())
        claim=attempts.claim_callback(digest,provider)
        from common.operations.oauth_catalog import provider_catalog
        platform=next(d.platform for d in provider_catalog() if d.id==provider)
        ref=lambda k:CredentialRef('autosns.oauth','personal',platform,'conn',p['credential_ref'].generation,k)
        staged=attempts.finalize_callback(claim,ref('code'),ref('ticket'),(now+timedelta(minutes=1)).isoformat())
        resumed=attempts.claim_resume(item['attempt_id'],'binding',staged['revision'])
        exchanged=attempts.update_attempt(item['attempt_id'],'binding',resumed['revision'],'token_exchanged',{'token_ref':ref('token')})
        saved=self.store.create_target_proposal(item['attempt_id'],'binding',exchanged['revision'],p)
        return self.store.confirm_target(saved,base,revision)
    def test_confirm_snapshot_projection_and_disconnect_preserves_base(self):
        self.confirm(self.proposal(),'base',0)
        snap=self.store.snapshot(); projected=project_registry(self.base,snap)
        self.assertFalse(projected.connections['conn'].enabled)
        self.assertIsNone(snap.connections['conn']['authorization'])
        self.assertEqual(1,len(credential_catalog(snap)))
        self.assertEqual('legacy',self.base.connections['conn'].credential_ref)
        self.store.disconnect_local('conn','base',1)
        self.assertEqual({},credential_catalog(self.store.snapshot()))
        self.assertIn('legacy',project_registry(self.base,self.store.snapshot()).credentials)
    def test_cas_and_base_revision(self):
        self.confirm(self.proposal(),'base',0)
        with self.assertRaises(StoreError): self.confirm(self.proposal(),'base',0)
        with self.assertRaises(StoreError): self.confirm(self.proposal(),'changed',1)
        wrong=Registry('changed',self.base.accounts,self.base.credentials,{},self.base.connections,{},{},{})
        with self.assertRaises(StoreError): project_registry(wrong,self.store.snapshot())
    def test_cross_account_ref_and_target_conflict(self):
        p=self.proposal(); p['credential_ref']=CredentialRef('autosns.oauth','dept','youtube','conn',1,'token')
        with self.assertRaises(StoreError): self.confirm(p,'base',0)
        p=self.proposal(); p['target_id']='other'; self.confirm(p,'base',0)
        with self.assertRaises(StoreError): project_registry(self.base,self.store.snapshot())

    def test_concurrent_cas_and_existing_database_unchanged(self):
        from concurrent.futures import ThreadPoolExecutor
        from pathlib import Path
        original=Path(self.tmp.name)/'operations.sqlite3'; original.write_bytes(b'existing database sentinel')
        def confirm(_):
            try: self.confirm(self.proposal(),'base',0); return True
            except StoreError: return False
        with ThreadPoolExecutor(4) as pool: self.assertEqual(1,sum(pool.map(confirm,range(4))))
        self.assertEqual(b'existing database sentinel',original.read_bytes())
        self.assertEqual(1,ManagedConnectionStore(self.tmp.name).snapshot().generation)

    def test_persisted_proposal_session_and_once(self):
        from common.operations.oauth_store import OAuthAttemptStore
        from common.operations.oauth_models import AttemptContext
        from datetime import datetime,timezone,timedelta
        now=datetime.now(timezone.utc)
        attempts=OAuthAttemptStore(self.tmp.name)
        context=AttemptContext('user','binding','personal','youtube','conn','base',0,('read',),'https://test/cb','client',1,'ev')
        item=attempts.create_attempt(context,'c'*64,(now+timedelta(minutes=10)).isoformat())
        # Only a completed inspect may create a target proposal.
        with self.assertRaises(StoreError): self.store.create_target_proposal(item['attempt_id'],'binding',1,self.proposal())
        claim=attempts.claim_callback('c'*64,'youtube')
        ref=lambda k:CredentialRef('autosns.oauth','personal','youtube','conn',1,k)
        staged=attempts.finalize_callback(claim,ref('code'),ref('ticket'),(now+timedelta(minutes=1)).isoformat())
        resumed=attempts.claim_resume(item['attempt_id'],'binding',staged['revision'])
        exchanged=attempts.update_attempt(item['attempt_id'],'binding',resumed['revision'],'token_exchanged',{'token_ref':ref('token')})
        proposal=self.store.create_target_proposal(item['attempt_id'],'binding',exchanged['revision'],self.proposal())
        reopened=ManagedConnectionStore(self.tmp.name)
        with self.assertRaises(StoreError): reopened.read_target_proposal(proposal['proposal_id'],'other')
        saved=reopened.read_target_proposal(proposal['proposal_id'],'binding')
        self.assertIsNone(reopened.proposal_for_attempt(item['attempt_id'],'other'))
        self.assertEqual(saved,reopened.proposal_for_attempt(item['attempt_id'],'binding'))
        self.assertEqual('target',saved['target_id'])
        reopened.confirm_target_proposal(proposal['proposal_id'],'binding','base',0)
        with self.assertRaises(StoreError): reopened.confirm_target_proposal(proposal['proposal_id'],'binding','base',0)

    def test_wrong_platform_proposal_and_persisted_confirmation_are_rejected(self):
        from common.operations.oauth_store import OAuthAttemptStore, _dump, _ref
        from common.operations.oauth_models import AttemptContext
        from datetime import datetime,timezone,timedelta
        now=datetime.now(timezone.utc); attempts=OAuthAttemptStore(self.tmp.name)
        context=AttemptContext('user','binding','personal','youtube','conn','base',0,('read',),'https://test/cb','client',1,'ev')
        item=attempts.create_attempt(context,'f'*64,(now+timedelta(minutes=10)).isoformat())
        claim=attempts.claim_callback('f'*64,'youtube')
        ref=lambda k:CredentialRef('autosns.oauth','personal','youtube','conn',1,k)
        staged=attempts.finalize_callback(claim,ref('code'),ref('ticket'),(now+timedelta(minutes=1)).isoformat())
        resumed=attempts.claim_resume(item['attempt_id'],'binding',staged['revision'])
        exchanged=attempts.update_attempt(item['attempt_id'],'binding',resumed['revision'],'token_exchanged',{'token_ref':ref('token')})
        wrong=self.proposal(); wrong['platform']='facebook'
        with self.assertRaises(StoreError): self.store.create_target_proposal(item['attempt_id'],'binding',exchanged['revision'],wrong)
        self.assertEqual(exchanged,attempts.read_owned(item['attempt_id'],'binding'))
        saved=self.store.create_target_proposal(item['attempt_id'],'binding',exchanged['revision'],self.proposal())
        # A persisted pre-fix proposal must also be checked at final commit.
        wrong['credential_ref']=_ref(CredentialRef('autosns.oauth','personal','facebook','conn',1,'token'))
        with self.store._db(True) as db: db.execute('UPDATE oauth_proposals SET payload=? WHERE id=?',(_dump(wrong),saved['proposal_id']))
        with self.assertRaises(StoreError): self.store.confirm_target(saved,'base',0)
        self.assertEqual(0,self.store.snapshot().generation)
        self.assertFalse(self.store.read_target_proposal(saved['proposal_id'],'binding')['consumed'])
        self.assertEqual('target_confirmation',attempts.read_owned(item['attempt_id'],'binding')['state'])

    def test_refresh_lease_reopen_and_disconnect_blocks_late_commit(self):
        self.confirm(self.proposal(),'base',0)
        lease=self.store.claim_connection_operation('conn','base',1,'refresh')
        with self.assertRaises(StoreError): self.store.claim_connection_operation('conn','base',lease['connection_revision'],'refresh')
        with self.assertRaises(StoreError): self.store.finish_connection_operation(lease)
        with self.assertRaises(StoreError): self.store.finish_connection_operation(lease,new_ref=CredentialRef('autosns.oauth','personal','facebook','conn',2,'token'))
        self.assertEqual(1,self.store.snapshot().connections['conn']['credential_generation'])
        self.assertEqual(2,self.store.reserve_generation('autosns.oauth','personal','youtube','conn'))
        ref=CredentialRef('autosns.oauth','personal','youtube','conn',2,'token')
        reopened=ManagedConnectionStore(self.tmp.name)
        refreshed=reopened.finish_connection_operation(lease,new_ref=ref)
        row=refreshed.connections['conn']; self.assertEqual(2,row['credential_generation'])
        lease=reopened.claim_connection_operation('conn','base',row['revision'],'refresh')
        reopened.disconnect_local('conn','base',lease['connection_revision'])
        with self.assertRaises(StoreError): reopened.finish_connection_operation(lease,new_ref=CredentialRef('autosns.oauth','personal','youtube','conn',3,'token'))
        self.assertEqual('disconnected',reopened.snapshot().connections['conn']['state'])
        self.assertEqual(2,reopened.snapshot().connections['conn']['credential_generation'])

    def test_revoke_and_failed_refresh_preserve_generation_and_reject_replay(self):
        self.confirm(self.proposal(),'base',0)
        lease=self.store.claim_connection_operation('conn','base',1,'refresh')
        refresh_lease=lease
        failed=self.store.fail_connection_operation(lease,'reauth_required')
        row=failed.connections['conn']; self.assertEqual(1,row['credential_generation'])
        self.assertEqual(self.proposal()['credential_ref'],row['credential_ref'])
        lease=self.store.claim_connection_operation('conn','base',row['revision'],'revoke')
        revoked=self.store.finish_connection_operation(lease,state='revoked')
        self.assertEqual('revoked',revoked.connections['conn']['state'])
        with self.assertRaises(StoreError): self.store.finish_connection_operation(refresh_lease,new_ref=CredentialRef('autosns.oauth','personal','youtube','conn',2,'token'))
        self.assertEqual(1,revoked.connections['conn']['credential_generation'])
        with self.assertRaises(StoreError): self.store.finish_connection_operation(lease,state='revoked')

    def test_instagram_provider_is_server_derived_persisted_and_not_switchable(self):
        p=self.proposal(); p['platform']='instagram'
        p['credential_ref']=CredentialRef('autosns.oauth','personal','instagram','conn',1,'token')
        snap=self.confirm(p,'base',0,provider='instagram_login')
        self.assertEqual('instagram_login',snap.connections['conn']['provider_id'])
        reopened=ManagedConnectionStore(self.tmp.name)
        self.assertEqual('instagram_login',reopened.snapshot().connections['conn']['provider_id'])
        other=dict(p,credential_ref=CredentialRef('autosns.oauth','personal','instagram','conn',2,'token'))
        with self.assertRaises(StoreError): self.confirm(other,'base',1,provider='instagram_facebook')
        self.assertEqual(1,reopened.snapshot().connections['conn']['credential_generation'])
        lease=reopened.claim_connection_operation('conn','base',1,'refresh')
        self.assertEqual('instagram_login',lease['provider_id'])
        refreshed=reopened.finish_connection_operation(lease,new_ref=other['credential_ref'])
        self.assertEqual('instagram_login',refreshed.connections['conn']['provider_id'])
        spoofed=dict(p,provider_id='instagram_facebook')
        with self.assertRaises(StoreError): self.confirm(spoofed,'base',refreshed.connections['conn']['revision'],provider='instagram_login')

    def test_inactive_projection_has_no_legacy_fallback_and_preserves_state(self):
        from dataclasses import replace
        from common.operations.models import freeze
        self.confirm(self.proposal(),'base',0)
        base=replace(self.base,connections=dict(self.base.connections,conn=replace(self.base.connections['conn'],profile_ref='legacy-profile'),untouched=Connection('untouched','personal','youtube',credential_ref='legacy',profile_ref='legacy-profile')))
        for state in ('disconnected','unknown','reauth_required','revoked'):
            snapshot=self.store.snapshot(); row=dict(snapshot.connections['conn'],state=state,credential_ref=None)
            projected=project_registry(base,replace(snapshot,connections=freeze({'conn':row}),credential_refs=freeze({})))
            connection=projected.connections['conn']
            self.assertIsNone(connection.credential_ref); self.assertIsNone(connection.profile_ref)
            self.assertEqual(state,connection.auth_status); self.assertFalse(connection.enabled)
            self.assertEqual(base.connections['untouched'],projected.connections['untouched'])
        self.assertEqual('legacy',base.connections['conn'].credential_ref)
        self.assertEqual('legacy-profile',base.connections['conn'].profile_ref)

    def test_authorization_confirm_refresh_and_failure_are_atomic(self):
        authorization=dict(observed_scopes=['observed'],credential_expires_at='2030-01-01T09:00:00+09:00',read_status='verified',publication_status='blocked',credential_status='stored')
        p=dict(self.proposal(),authorization=authorization)
        snap=self.confirm(p,'base',0)
        self.assertEqual('active',snap.connections['conn']['authorization']['credential_status'])
        self.assertEqual('2030-01-01T00:00:00+00:00',snap.connections['conn']['authorization']['credential_expires_at'])
        from common.operations.oauth_store import OAuthAttemptStore
        self.assertEqual('active',OAuthAttemptStore(self.tmp.name).list_owned('binding')[0]['authorization']['credential_status'])
        lease=self.store.claim_connection_operation('conn','base',1,'refresh')
        updated=dict(authorization,observed_scopes=['reduced'],credential_status='active')
        ref=CredentialRef('autosns.oauth','personal','youtube','conn',2,'token')
        with self.assertRaises(StoreError): self.store.finish_connection_operation(lease,new_ref=ref,authorization=dict(updated,access_token='secret'))
        self.assertEqual(1,self.store.snapshot().connections['conn']['credential_generation'])
        refreshed=self.store.finish_connection_operation(lease,new_ref=ref,authorization=updated)
        row=refreshed.connections['conn']; self.assertEqual(('reduced',),row['authorization']['observed_scopes'])
        lease=self.store.claim_connection_operation('conn','base',row['revision'],'refresh')
        failed=self.store.fail_connection_operation(lease,'reauth_required').connections['conn']
        self.assertEqual('reauth_required',failed['authorization']['credential_status'])
        self.assertEqual('unknown',failed['authorization']['read_status'])
        disconnected=self.store.disconnect_local('conn','base',failed['revision']).connections['conn']
        self.assertEqual('unknown',disconnected['authorization']['credential_status'])
