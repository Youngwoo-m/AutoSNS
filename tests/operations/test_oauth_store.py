import unittest
from tempfile import TemporaryDirectory
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
from common.operations.oauth_store import OAuthAttemptStore
from common.operations.oauth_models import AttemptContext, CredentialRef
from common.operations.content_store import StoreError

class AttemptTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.now=datetime(2026,1,1,tzinfo=timezone.utc)
        self.store=OAuthAttemptStore(self.tmp.name,lambda:self.now)
        self.context=AttemptContext('user','binding','personal','google','conn','base',0,('read',),'https://test/cb','client',1,'ev')
    def create(self):
        self.store.initialize()
        return self.store.create_attempt(self.context,'a'*64,(self.now+timedelta(minutes=10)).isoformat())
    def ref(self,kind): return CredentialRef('autosns.oauth','personal','youtube','conn',1,kind)
    def test_missing_read_does_not_create(self):
        self.assertEqual([],self.store.list_owned('binding'))
        self.assertFalse(self.store.path.exists())
        with self.assertRaises(StoreError): self.store.create_attempt(self.context,'a'*64,(self.now+timedelta(minutes=10)).isoformat())
    def test_reopen_owned_and_single_resume(self):
        item=self.create(); claim=self.store.claim_callback('a'*64,'google')
        staged=self.store.finalize_callback(claim,self.ref('code'),self.ref('ticket'),(self.now+timedelta(minutes=2)).isoformat())
        reopened=OAuthAttemptStore(self.tmp.name,lambda:self.now)
        self.assertEqual(item['attempt_id'],reopened.read_owned(item['attempt_id'],'binding')['attempt_id'])
        with self.assertRaises(StoreError): reopened.read_owned(item['attempt_id'],'other')
        self.assertEqual('resume_pending', reopened.claim_resume(item['attempt_id'],'binding',staged['revision'])['state'])
        with self.assertRaises(StoreError): reopened.claim_resume(item['attempt_id'],'binding',staged['revision'])
    def test_concurrent_callback_only_one(self):
        self.create()
        def claim(_):
            try: self.store.claim_callback('a'*64,'google'); return True
            except StoreError: return False
        with ThreadPoolExecutor(4) as pool: self.assertEqual(1,sum(pool.map(claim,range(4))))
    def test_failed_stage_consumes_state(self):
        self.create(); claim=self.store.claim_callback('a'*64,'google'); self.store.fail_callback(claim,'stage_failed')
        with self.assertRaises(StoreError): self.store.claim_callback('a'*64,'google')
        with self.assertRaises(StoreError): self.store.finalize_callback(claim,self.ref('code'),self.ref('ticket'),(self.now+timedelta(minutes=2)).isoformat())
    def test_expired_and_overlong(self):
        self.create(); self.now+=timedelta(minutes=10)
        with self.assertRaises(StoreError): self.store.claim_callback('a'*64,'google')
        with self.assertRaises(StoreError): self.store.create_attempt(self.context,'b'*64,(self.now+timedelta(minutes=11)).isoformat())

    def test_update_attempt_cas_and_secret_fields_rejected(self):
        item=self.create()
        with self.assertRaises(StoreError): self.store.update_attempt(item['attempt_id'],'binding',1,'token_exchanged',{'access_token':'secret'})
        claim=self.store.claim_callback('a'*64,'google')
        staged=self.store.finalize_callback(claim,self.ref('code'),self.ref('ticket'),(self.now+timedelta(minutes=2)).isoformat())
        resumed=self.store.claim_resume(item['attempt_id'],'binding',staged['revision'])
        updated=self.store.update_attempt(item['attempt_id'],'binding',resumed['revision'],'unknown',{})
        self.assertEqual('unknown',updated['state'])
        with self.assertRaises(StoreError): self.store.update_attempt(item['attempt_id'],'binding',resumed['revision'],'unknown',{})
    def test_ticket_expiry_and_database_has_no_raw_secret(self):
        item=self.create(); claim=self.store.claim_callback('a'*64,'google')
        staged=self.store.finalize_callback(claim,self.ref('code'),self.ref('ticket'),(self.now+timedelta(seconds=20)).isoformat())
        self.now+=timedelta(seconds=20)
        with self.assertRaises(StoreError): self.store.claim_resume(item['attempt_id'],'binding',staged['revision'])
        self.assertNotIn(b'access_token',self.store.path.read_bytes())
