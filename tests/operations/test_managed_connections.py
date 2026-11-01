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
    def confirm(self,p,base,revision):
        from common.operations.oauth_store import OAuthAttemptStore
        from common.operations.oauth_models import AttemptContext
        from datetime import datetime,timezone,timedelta
        from uuid import uuid4
        import hashlib
        now=datetime.now(timezone.utc); attempts=OAuthAttemptStore(self.tmp.name)
        context=AttemptContext('user','binding','personal','youtube','conn',base,revision,('read',),'https://test/cb','client',1,'ev')
        digest=hashlib.sha256(uuid4().bytes).hexdigest()
        item=attempts.create_attempt(context,digest,(now+timedelta(minutes=10)).isoformat())
        claim=attempts.claim_callback(digest,'youtube')
        ref=lambda k:CredentialRef('autosns.oauth','personal','youtube','conn',1,k)
        staged=attempts.finalize_callback(claim,ref('code'),ref('ticket'),(now+timedelta(minutes=1)).isoformat())
        resumed=attempts.claim_resume(item['attempt_id'],'binding',staged['revision'])
        exchanged=attempts.update_attempt(item['attempt_id'],'binding',resumed['revision'],'token_exchanged',{'token_ref':ref('token')})
        saved=self.store.create_target_proposal(item['attempt_id'],'binding',exchanged['revision'],p)
        return self.store.confirm_target(saved,base,revision)
    def test_confirm_snapshot_projection_and_disconnect_preserves_base(self):
        self.confirm(self.proposal(),'base',0)
        snap=self.store.snapshot(); projected=project_registry(self.base,snap)
        self.assertFalse(projected.connections['conn'].enabled)
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
        self.assertEqual('target',saved['target_id'])
        reopened.confirm_target_proposal(proposal['proposal_id'],'binding','base',0)
        with self.assertRaises(StoreError): reopened.confirm_target_proposal(proposal['proposal_id'],'binding','base',0)
