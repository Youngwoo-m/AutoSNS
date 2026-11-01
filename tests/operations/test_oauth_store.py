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
        self.context=AttemptContext('user','binding','personal','youtube','conn','base',0,('read',),'https://test/cb','client',1,'ev')
    def create(self):
        self.store.initialize()
        return self.store.create_attempt(self.context,'a'*64,(self.now+timedelta(minutes=10)).isoformat())
    def ref(self,kind): return CredentialRef('autosns.oauth','personal','youtube','conn',1,kind)
    def test_missing_read_does_not_create(self):
        self.assertEqual([],self.store.list_owned('binding'))
        self.assertFalse(self.store.path.exists())
        with self.assertRaises(StoreError): self.store.create_attempt(self.context,'a'*64,(self.now+timedelta(minutes=10)).isoformat())
    def test_reopen_owned_and_single_resume(self):
        item=self.create(); claim=self.store.claim_callback('a'*64,'youtube')
        staged=self.store.finalize_callback(claim,self.ref('code'),self.ref('ticket'),(self.now+timedelta(minutes=2)).isoformat())
        reopened=OAuthAttemptStore(self.tmp.name,lambda:self.now)
        self.assertEqual(item['attempt_id'],reopened.read_owned(item['attempt_id'],'binding')['attempt_id'])
        with self.assertRaises(StoreError): reopened.read_owned(item['attempt_id'],'other')
        self.assertEqual('resume_pending', reopened.claim_resume(item['attempt_id'],'binding',staged['revision'])['state'])
        with self.assertRaises(StoreError): reopened.claim_resume(item['attempt_id'],'binding',staged['revision'])
    def test_concurrent_callback_only_one(self):
        self.create()
        def claim(_):
            try: self.store.claim_callback('a'*64,'youtube'); return True
            except StoreError: return False
        with ThreadPoolExecutor(4) as pool: self.assertEqual(1,sum(pool.map(claim,range(4))))
    def test_failed_stage_consumes_state(self):
        self.create(); claim=self.store.claim_callback('a'*64,'youtube'); self.store.fail_callback(claim,'stage_failed')
        with self.assertRaises(StoreError): self.store.claim_callback('a'*64,'youtube')
        with self.assertRaises(StoreError): self.store.finalize_callback(claim,self.ref('code'),self.ref('ticket'),(self.now+timedelta(minutes=2)).isoformat())
    def test_expired_and_overlong(self):
        self.create(); self.now+=timedelta(minutes=10)
        with self.assertRaises(StoreError): self.store.claim_callback('a'*64,'youtube')
        with self.assertRaises(StoreError): self.store.create_attempt(self.context,'b'*64,(self.now+timedelta(minutes=11)).isoformat())

    def test_update_attempt_cas_and_secret_fields_rejected(self):
        item=self.create()
        with self.assertRaises(StoreError): self.store.update_attempt(item['attempt_id'],'binding',1,'token_exchanged',{'access_token':'secret'})
        claim=self.store.claim_callback('a'*64,'youtube')
        staged=self.store.finalize_callback(claim,self.ref('code'),self.ref('ticket'),(self.now+timedelta(minutes=2)).isoformat())
        resumed=self.store.claim_resume(item['attempt_id'],'binding',staged['revision'])
        updated=self.store.update_attempt(item['attempt_id'],'binding',resumed['revision'],'unknown',{})
        self.assertEqual('unknown',updated['state'])
        with self.assertRaises(StoreError): self.store.update_attempt(item['attempt_id'],'binding',resumed['revision'],'unknown',{})
    def test_ticket_expiry_and_database_has_no_raw_secret(self):
        item=self.create(); claim=self.store.claim_callback('a'*64,'youtube')
        staged=self.store.finalize_callback(claim,self.ref('code'),self.ref('ticket'),(self.now+timedelta(seconds=20)).isoformat())
        self.now+=timedelta(seconds=20)
        with self.assertRaises(StoreError): self.store.claim_resume(item['attempt_id'],'binding',staged['revision'])
        self.assertNotIn(b'access_token',self.store.path.read_bytes())

    def test_provider_platform_binding_rejects_refs_without_mutation(self):
        from dataclasses import replace
        for provider,platform in (('youtube','youtube'),('instagram_login','instagram'),('instagram_facebook','instagram'),('naver','naver_blog')):
            with self.subTest(provider=provider), TemporaryDirectory() as root:
                store=OAuthAttemptStore(root,lambda:self.now); store.initialize()
                context=replace(self.context,provider_id=provider)
                item=store.create_attempt(context,'d'*64,(self.now+timedelta(minutes=10)).isoformat())
                claim=store.claim_callback('d'*64,provider)
                ref=lambda kind,p=platform:CredentialRef('autosns.oauth','personal',p,'conn',1,kind)
                for kind in ('code','ticket'):
                    with self.assertRaises(StoreError):
                        store.finalize_callback(claim,ref('code','facebook') if kind=='code' else ref('code'),ref('ticket','facebook') if kind=='ticket' else ref('ticket'),(self.now+timedelta(minutes=1)).isoformat())
                    self.assertEqual(claim.lease_revision,store.read_owned(item['attempt_id'],'binding')['revision'])
                staged=store.finalize_callback(claim,ref('code'),ref('ticket'),(self.now+timedelta(minutes=1)).isoformat())
                resumed=store.claim_resume(item['attempt_id'],'binding',staged['revision'])
                for kind in ('token','verifier'):
                    with self.assertRaises(StoreError): store.update_attempt(item['attempt_id'],'binding',resumed['revision'],'token_exchanged',{kind+'_ref':ref(kind,'facebook')})
                    self.assertEqual(resumed,store.read_owned(item['attempt_id'],'binding'))
                store.update_attempt(item['attempt_id'],'binding',resumed['revision'],'token_exchanged',{'token_ref':ref('token')})

    def test_unregistered_provider_rejected(self):
        from dataclasses import replace
        self.store.initialize()
        with self.assertRaises(StoreError): self.store.create_attempt(replace(self.context,provider_id='google'),'e'*64,(self.now+timedelta(minutes=10)).isoformat())

    def test_generation_reservation_concurrent_and_reopen(self):
        self.store.initialize()
        def reserve(_): return self.store.reserve_generation('autosns.oauth','personal','youtube','conn')
        with ThreadPoolExecutor(4) as pool: values=list(pool.map(reserve,range(12)))
        self.assertEqual(list(range(1,13)),sorted(values))
        self.assertEqual(13,OAuthAttemptStore(self.tmp.name).reserve_generation('autosns.oauth','personal','youtube','conn'))
        with self.assertRaises(StoreError): self.store.reserve_generation('other','personal','youtube','conn')

    def test_bind_verifier_is_owned_cas_and_survives_callback_reopen(self):
        item=self.create()
        wrong=CredentialRef('autosns.oauth','personal','facebook','conn',1,'verifier')
        with self.assertRaises(StoreError): self.store.bind_verifier(item['attempt_id'],'binding',1,wrong)
        with self.assertRaises(StoreError): self.store.bind_verifier(item['attempt_id'],'other',1,self.ref('verifier'))
        bound=self.store.bind_verifier(item['attempt_id'],'binding',1,self.ref('verifier'))
        with self.assertRaises(StoreError): self.store.bind_verifier(item['attempt_id'],'binding',1,self.ref('verifier'))
        claim=self.store.claim_callback('a'*64,'youtube')
        staged=self.store.finalize_callback(claim,self.ref('code'),self.ref('ticket'),(self.now+timedelta(minutes=1)).isoformat())
        self.assertEqual(self.ref('verifier'),OAuthAttemptStore(self.tmp.name).read_owned(item['attempt_id'],'binding')['verifier_ref'])
        self.assertEqual(bound['revision']+2,staged['revision'])
        with self.assertRaises(StoreError): self.store.bind_verifier(item['attempt_id'],'binding',staged['revision'],self.ref('verifier'))

    def test_request_receipt_reopen_hash_conflict_and_safe_result_cas(self):
        self.store.initialize()
        first=self.store.claim_request('binding','start','request-1','a'*64)
        self.assertEqual('claimed',first['status'])
        reopened=OAuthAttemptStore(self.tmp.name)
        self.assertEqual('in_progress',reopened.claim_request('binding','start','request-1','a'*64)['status'])
        with self.assertRaises(StoreError): reopened.claim_request('binding','start','request-1','b'*64)
        with self.assertRaises(StoreError): reopened.finish_request(first['id'],first['revision'],{'authorize_url':'https://secret'})
        with self.assertRaises(StoreError): reopened.finish_request(first['id'],first['revision'],{'target_proposal':{'token':'secret'}})
        with self.assertRaises(StoreError): reopened.finish_request(first['id'],first['revision'],{'execution_enabled':True})
        for field in ('provider_id','platform','state'):
            with self.assertRaises(StoreError): reopened.finish_request(first['id'],first['revision'],{field:[]})
        done=reopened.finish_request(first['id'],first['revision'],{'attempt_id':'abc','account_id':'personal','provider_id':'youtube','connection_id':'conn','revision':1,'state':'consent_pending','expires_at':self.now.isoformat(),'execution_enabled':False})
        self.assertEqual('completed',done['status'])
        self.assertEqual(done,reopened.claim_request('binding','start','request-1','a'*64))
        with self.assertRaises(StoreError): reopened.finish_request(first['id'],first['revision'],{'state':'error'})

    def test_state_key_binding_receipt_owned_and_callback_preserves_ref(self):
        item=self.create()
        receipt=self.store.claim_request('binding','start','request-2','a'*64)
        ref=CredentialRef('autosns.oauth','personal','youtube','conn',1,'state_key')
        with self.assertRaises(StoreError): self.store.bind_state_key(item['attempt_id'],'other',1,ref,receipt['id'])
        foreign=self.store.claim_request('other','start','request-2','a'*64)
        with self.assertRaises(StoreError): self.store.bind_state_key(item['attempt_id'],'binding',1,ref,foreign['id'])
        bound=self.store.bind_state_key(item['attempt_id'],'binding',1,ref,receipt['id'])
        claim=self.store.claim_callback('a'*64,'youtube')
        staged=self.store.finalize_callback(claim,self.ref('code'),self.ref('ticket'),(self.now+timedelta(minutes=1)).isoformat())
        self.assertEqual(ref,staged['state_key_ref'])
        self.assertEqual(receipt['id'],staged['request_receipt_id'])
        with self.assertRaises(StoreError): self.store.bind_state_key(item['attempt_id'],'binding',bound['revision'],ref,receipt['id'])

    def test_authorization_update_receipt_validation_and_unobserved_start(self):
        item=self.create()
        self.assertIsNone(item['authorization']['observed_scopes'])
        self.assertIsNone(item['authorization']['credential_expires_at'])
        self.assertEqual('pending',item['authorization']['credential_status'])
        claim=self.store.claim_callback('a'*64,'youtube')
        staged=self.store.finalize_callback(claim,self.ref('code'),self.ref('ticket'),(self.now+timedelta(minutes=1)).isoformat())
        resumed=self.store.claim_resume(item['attempt_id'],'binding',staged['revision'])
        authorization=dict(observed_scopes=[],credential_expires_at='2030-01-01T00:00:00+00:00',read_status='not_checked',publication_status='blocked',credential_status='stored')
        with self.assertRaises(StoreError): self.store.update_attempt(item['attempt_id'],'binding',resumed['revision'],'token_exchanged',{'authorization':dict(authorization,publication_status='verified')})
        exchanged=self.store.update_attempt(item['attempt_id'],'binding',resumed['revision'],'token_exchanged',{'authorization':authorization})
        self.assertEqual(authorization,exchanged['authorization'])
        receipt=self.store.claim_request('binding','continue:'+item['attempt_id'],'meta-request','b'*64)
        result={'attempt_id':item['attempt_id'],'authorization':authorization}
        self.assertEqual(result,self.store.finish_request(receipt['id'],receipt['revision'],result)['result'])
