"""실제 grant DB와 메모리 vault만 사용한다. 로그인·Keychain·외부 API는 없다."""
from dataclasses import replace
from datetime import datetime,timezone,timedelta
import unittest

from common.operations.content_store import StoreError
from common.operations.managed_credentials import ManagedCredentialResolver
from common.operations.oauth_models import OAuthClientRegistration
from common.operations.publication_authority import ManagedPublicationAuthorizer,credential_fingerprint
from common.operations.publication_grants import (PublicationGrantStore,PublicationGrantPolicy,
    PublicationGrantBinding,VerifiedPublicationEvidence)
from tests.operations import test_managed_credentials as credential_fixture

SCOPE=credential_fixture.SCOPE
TOKEN=credential_fixture.TOKEN

UPLOAD='https://www.googleapis.com/auth/youtube.upload'


class ManagedPublicationAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.fixture=credential_fixture.ManagedCredentialTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.now=datetime.now(timezone.utc).replace(microsecond=0)
        self.scopes=(SCOPE,UPLOAD)
        self.token={**TOKEN,'scopes':list(self.scopes),'expires_at':(self.now+timedelta(hours=1)).isoformat()}
        self.fixture.row['scopes']=list(self.scopes)
        self.fixture.row['authorization'].update(observed_scopes=list(self.scopes),credential_expires_at=self.token['expires_at'])
        self.fixture.put(self.token)
        self.clients={'youtube':OAuthClientRegistration('youtube','fixture-client',None,
            'https://console.example.com/oauth/callback/youtube',1,self.scopes,'fixture-evidence',None)}
        self.grants=PublicationGrantStore(self.fixture.context,policy=PublicationGrantPolicy('test-policy',('youtube',)))
        self.authorizer=ManagedPublicationAuthorizer(self.grants,lambda:self.clients)
        self.resolver=ManagedCredentialResolver(self.fixture.store,self.fixture.backend,self.fixture.context,
            lambda:self.fixture.registry,clock=lambda:self.now,publication_authorizer=self.authorizer)

    def binding(self):
        f=self.fixture;row=f.row;client=self.clients['youtube']
        return PublicationGrantBinding(f.context.owner,f.registry.revision,'personal.youtube','personal','youtube',
            'youtube',row['target_id'],row['provider_subject'],row['revision'],f.ref.ref.generation,
            credential_fingerprint(f.ref),client.client_revision,client.cost_evidence_revision)

    def approve(self):
        self.grants.initialize()
        evidence=VerifiedPublicationEvidence(self.binding(),self.scopes,self.now,
            self.now+timedelta(hours=1),True,'fixture_owned_channel')
        return self.grants.issue(evidence,expected_revision=0,actor='fixture_operator',
            expires_at=self.now+timedelta(minutes=30),now=self.now)

    def use(self,scope='publication'):
        return self.resolver.use(self.fixture.reference,account_id='personal',platform='youtube',scope=scope,target_id='channel')

    def test_shortened_current_credential_expiry_invalidates_grant_before_vault(self):
        self.approve()
        self.fixture.row['authorization']['credential_expires_at']=(self.now+timedelta(minutes=10)).isoformat()
        with self.assertRaises(StoreError):
            with self.use():self.fail('grant exceeds current credential expiry')
        self.assertEqual(self.fixture.reads,0)

    def test_unapproved_grant_denies_before_vault_and_never_creates_db(self):
        with self.assertRaises(StoreError):
            with self.use():self.fail('grant required')
        self.assertEqual(self.fixture.reads,0)
        self.assertFalse((self.fixture.root/'publication-grants.sqlite3').exists())

    def test_real_grant_and_actual_scopes_allow_scoped_use_then_close_permanently(self):
        self.approve()
        with self.use() as resolved:
            resolved.assert_current();resolved.assert_publication_authority()
            self.assertEqual(resolved.scope,'publication');self.assertEqual(resolved.to_dict(),{})
            self.assertNotIn(self.token['access_token'],repr(resolved))
        with self.assertRaises(StoreError):resolved.assert_current()
        with self.assertRaises(StoreError):resolved.assert_publication_authority()
        self.assertEqual(self.fixture.reads,1)

    def test_read_lease_never_becomes_publication_even_with_valid_grant(self):
        self.approve()
        with self.use('read') as resolved:
            resolved.assert_current()
            with self.assertRaises(StoreError):resolved.assert_publication_authority()

    def test_revoke_during_same_thread_scope_denies_next_use_without_secret_reload(self):
        approved=self.approve()
        with self.use() as resolved:
            self.grants.revoke('personal.youtube',expected_revision=approved['revision'],actor='fixture_operator',now=self.now)
            with self.assertRaises(StoreError):resolved.assert_publication_authority()
        before=self.fixture.reads
        with self.assertRaises(StoreError):
            with self.use():self.fail('revoked')
        self.assertEqual(self.fixture.reads,before)

    def test_client_evidence_subject_and_registry_changes_invalidate_grant_before_vault(self):
        self.approve();original=self.clients['youtube']
        for client in (replace(original,client_revision=2),replace(original,cost_evidence_revision='changed'),replace(original,approved_scopes=(SCOPE,))):
            self.clients['youtube']=client
            with self.assertRaises(StoreError):
                with self.use():self.fail('stale client')
        self.clients['youtube']=original
        self.fixture.row['provider_subject']='different-owner'
        with self.assertRaises(StoreError):
            with self.use():self.fail('stale principal')
        self.assertEqual(self.fixture.reads,0)

    def test_expiry_and_generation_change_invalidate_existing_lease(self):
        self.approve()
        with self.use() as resolved:
            self.now+=timedelta(minutes=31)
            with self.assertRaises(StoreError):resolved.assert_current()
        self.now-=timedelta(minutes=31)
        with self.use() as resolved:
            self.fixture.row['credential_generation']=2
            with self.assertRaises(StoreError):resolved.assert_current()

    def test_observed_scopes_do_not_fill_missing_token_scopes(self):
        self.approve();self.fixture.put({**self.token,'scopes':[SCOPE]})
        with self.assertRaises(StoreError):
            with self.use():self.fail('actual token missing upload scope')

    def test_thread_escape_is_rejected_even_before_scope_exit(self):
        import threading
        self.approve();errors=[]
        with self.use() as resolved:
            def escaped():
                try:resolved.assert_current()
                except StoreError:errors.append('blocked')
            thread=threading.Thread(target=escaped);thread.start();thread.join(2)
            self.assertFalse(thread.is_alive());self.assertEqual(errors,['blocked'])
            resolved.assert_current()

    def test_google_sdk_and_clone_share_actual_grant_lifetime(self):
        from common.publishers.managed_google_credentials import ManagedGoogleCredentialResolver
        from common.operations.models import ContractError
        class SDK:
            def __init__(self,**kwargs):self.kwargs=kwargs
            def apply(self,headers):headers['Authorization']='Bearer '+self.kwargs['token']
            def before_request(self,request,method,url,headers):self.apply(headers)
            def refresh(self,*args):raise AssertionError('no remote refresh')
            def with_quota_project(self,value):return SDK(**self.kwargs)
        self.approve();resolver=ManagedGoogleCredentialResolver(self.resolver,credentials_factory=SDK)
        with resolver.use(self.fixture.reference,account_id='personal',platform='youtube',scope='publication',target_id='channel') as sdk:
            sdk.assert_publication_authority();headers={};sdk.apply(headers)
            self.assertEqual(headers['Authorization'],'Bearer '+self.token['access_token'])
            clone=sdk.with_quota_project('fixture');clone.apply({})
            with self.assertRaises(ContractError):sdk.refresh(None)
        for cached in (sdk,clone):
            with self.assertRaises(ContractError):cached.apply({})

    def test_google_sdk_denies_revoke_before_next_apply(self):
        from common.publishers.managed_google_credentials import ManagedGoogleCredentialResolver
        from common.operations.models import ContractError
        class SDK:
            def __init__(self,**kwargs):pass
            def apply(self,headers):headers['sent']=True
            def before_request(self,*args):pass
            def refresh(self,*args):raise AssertionError('no refresh')
        approved=self.approve();resolver=ManagedGoogleCredentialResolver(self.resolver,credentials_factory=SDK)
        with resolver.use(self.fixture.reference,account_id='personal',platform='youtube',scope='publication',target_id='channel') as sdk:
            self.grants.revoke('personal.youtube',expected_revision=approved['revision'],actor='fixture_operator',now=self.now)
            headers={}
            with self.assertRaises(ContractError):sdk.apply(headers)
            self.assertEqual(headers,{})
