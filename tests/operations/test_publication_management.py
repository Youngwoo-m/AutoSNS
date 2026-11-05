"""가짜 vault·공급자 검사와 실제 격리 grant DB로 명시 승인 관리를 확인한다."""
from dataclasses import replace
from datetime import timedelta
import json
import unittest

from common.operations.content_store import StoreError
from common.operations.oauth_models import OAuthClientRegistration
from common.operations.oauth_service import SessionContext
from common.operations.publication_grants import PublicationGrantStore,PublicationGrantPolicy,VerifiedPublicationEvidence,DB_NAME
from common.operations.publication_management import PublicationGrantManagementService
from common.operations.oauth_workspace import require_oauth_write_guard
from tests.operations import test_managed_credentials as credential_fixture
NOW=credential_fixture.NOW
TOKEN=credential_fixture.TOKEN
SCOPE=credential_fixture.SCOPE

PUBLIC_KEYS={'publication_grant','available_actions','reason_codes','base_revision','connection_revision'}
GRANT_KEYS={'connection_id','account_id','platform','provider_id','target_id','revision','status','approved_at','expires_at','policy_revision'}


class PublicationManagementTests(unittest.TestCase):
    def setUp(self):
        self.fixture=credential_fixture.ManagedCredentialTests('test_constructor_inert_and_read_yields_private_frozen_bound_credential')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        f=self.fixture
        self.scopes=(SCOPE,'https://www.googleapis.com/auth/youtube.upload')
        f.row['scopes']=list(self.scopes);f.row['authorization']['observed_scopes']=list(self.scopes)
        f.put({**TOKEN,'scopes':list(self.scopes)})
        self.policy=PublicationGrantPolicy('policy-v1',('youtube',))
        self.grants=PublicationGrantStore(f.context,policy=self.policy)
        self.clients={'youtube':OAuthClientRegistration('youtube','private-client',None,'https://console.example.com/oauth/callback/youtube',
                                                      1,self.scopes,'evidence-v1',None)}
        self.session=SessionContext('console_user','private-session-binding')
        self.verifications=[];self.guard_calls=[];self.allowed=True;self.on_verify=None;self.evidence_changes={}
        owner=self
        class Verifier:
            def verify(self,resolved,binding,*,now):
                require_oauth_write_guard(f.root,f.context.owner)
                resolved.assert_current();owner.verifications.append((resolved,binding))
                if owner.on_verify:owner.on_verify()
                args=dict(binding=binding,observed_scopes=tuple(resolved.bundle.scopes),checked_at=now,
                          credential_expires_at=NOW+timedelta(hours=1),can_publish=True,verification_method='fake_provider_probe')
                args.update(owner.evidence_changes)
                return VerifiedPublicationEvidence(**args)
        self.verifier=Verifier();self.service=self.make_service()

    def guard(self,session,binding,client):
        require_oauth_write_guard(self.fixture.root,self.fixture.context.owner)
        self.guard_calls.append((session,binding,client));return self.allowed

    def make_service(self,**changes):
        f=self.fixture
        args=dict(registry_supplier=lambda:f.registry,connection_store=f.store,resolver=f.resolver(),grant_store=self.grants,
                  client_registrations=self.clients,verifiers={'youtube':self.verifier},authorization_guard=self.guard,clock=lambda:NOW)
        args.update(changes)
        return PublicationGrantManagementService(**args)

    def body(self,row=None):
        row=row or self.service.read(self.session,'personal.youtube')
        return dict(request_key='explicit-action-1',expected_base_revision=row['base_revision'],
                    expected_connection_revision=row['connection_revision'],expected_grant_revision=row['publication_grant']['revision'])

    def approve(self,body=None):
        return self.service.approve(self.session,'personal.youtube',body or self.body())

    def assert_error(self,call,code=None):
        with self.assertRaises(StoreError) as caught:call()
        if code:self.assertEqual(caught.exception.code,code)
        self.assertNotIn(TOKEN['access_token'],str(caught.exception));self.assertNotIn('private-session-binding',str(caught.exception))

    def test_constructor_and_get_no_vault_probe_guard_or_initialization(self):
        f=self.fixture
        self.assertEqual(f.reads,0);self.assertEqual(self.verifications,[])
        result=self.service.read(self.session,'personal.youtube')
        self.assertEqual(set(result),PUBLIC_KEYS);self.assertEqual(set(result['publication_grant']),GRANT_KEYS)
        self.assertEqual(result['publication_grant']['status'],'blocked')
        self.assertEqual(result['available_actions'],[])
        self.assertIn('oauth_publication_storage_uninitialized',result['reason_codes'])
        self.assertFalse((f.root/DB_NAME).exists())
        self.assertEqual(f.reads,0);self.assertEqual(self.verifications,[]);self.assertEqual(self.guard_calls,[])
        public=json.dumps(result)
        for secret in (TOKEN['access_token'],TOKEN['refresh_token'],'private-client','private-session-binding',str(f.root),
                       'provider_subject','credential_fingerprint','credential_ref','https://'):
            self.assertNotIn(secret,public)
        self.assertNotIn(str(f.root),repr(self.service))

    def test_explicit_approve_exact_evidence_and_duplicate_cas_before_secret(self):
        self.grants.initialize();self.grants.policy=replace(self.policy,max_ttl=timedelta(hours=2))
        before=dict(self.fixture.row);body=self.body()
        result=self.approve(body)
        self.assertEqual(result['publication_grant']['status'],'granted')
        self.assertEqual(result['publication_grant']['revision'],1)
        self.assertEqual(result['publication_grant']['expires_at'],(NOW+timedelta(hours=1)).isoformat(timespec='microseconds'))
        self.assertEqual(len(self.verifications),1);self.assertEqual(self.fixture.reads,1)
        self.assertEqual(self.fixture.row,before)
        self.assert_error(lambda:self.approve(body),'conflict')
        self.assertEqual(len(self.verifications),1);self.assertEqual(self.fixture.reads,1)
        self.assertEqual(self.fixture.row['authorization']['publication_status'],'blocked')

    def test_revoke_local_only_even_when_provider_or_write_scope_no_longer_available(self):
        self.grants.initialize();self.approve();f=self.fixture;reads=f.reads
        f.row['scopes']=[SCOPE];f.row['authorization']['observed_scopes']=[SCOPE]
        service=self.make_service(verifiers={},authorization_guard=None)
        current=service.read(self.session,'personal.youtube')
        self.assertNotIn('approve',current['available_actions']);self.assertIn('revoke',current['available_actions'])
        result=service.revoke(self.session,'personal.youtube',self.body(current))
        self.assertEqual(result['publication_grant']['status'],'revoked')
        self.assertEqual(f.reads,reads);self.assertEqual(len(self.verifications),1)
        self.assert_error(lambda:service.revoke(self.session,'personal.youtube',self.body(current)),'conflict')

    def test_missing_verifier_guard_or_false_policy_never_reads_secrets(self):
        self.grants.initialize()
        for changes in (dict(verifiers={}),dict(authorization_guard=None),dict(authorization_guard=lambda *a:False)):
            with self.subTest(changes=changes):
                service=self.make_service(**changes)
                self.assert_error(lambda:service.approve(self.session,'personal.youtube',self.body()))
                self.assertEqual(self.fixture.reads,0);self.assertEqual(self.verifications,[])

    def test_stale_revisions_malformed_body_and_unauthenticated_rejected_before_secret(self):
        self.grants.initialize();body=self.body()
        for change in (dict(expected_base_revision='stale'),dict(expected_connection_revision=2),dict(expected_grant_revision=1)):
            with self.subTest(change=change):self.assert_error(lambda:self.approve({**body,**change}),'conflict')
        for bad in ({},{**body,'scope':'write'},{**body,'target_id':'another'},{**body,'expected_connection_revision':True},
                    {**body,'request_key':'bad/key'}):
            with self.subTest(body=bad):self.assert_error(lambda:self.service.approve(self.session,'personal.youtube',bad),'invalid')
        for session in (None,{'actor':'console_user'}):
            with self.subTest(session=session):self.assert_error(lambda:self.service.read(session,'personal.youtube'),'oauth_session_required')
        self.assertEqual(self.fixture.reads,0);self.assertEqual(self.verifications,[])

    def test_cross_account_target_ref_and_missing_client_fail_closed_without_vault(self):
        self.grants.initialize();f=self.fixture
        original=f.row
        for changes in (dict(account_id='dept'),dict(credential_generation=2),dict(connection_id='dept.youtube')):
            with self.subTest(changes=changes):
                f.row={**original,**changes}
                self.assert_error(lambda:self.service.read(self.session,'personal.youtube'))
                self.assertEqual(f.reads,0)
        f.row=original
        self.clients.clear()
        self.assert_error(lambda:self.service.read(self.session,'personal.youtube'),'oauth_registration_blocked')
        self.assertEqual(f.reads,0)

    def test_verifier_wrong_binding_scopes_expiry_or_false_permission_never_grants(self):
        self.grants.initialize();base=self.body()
        for kind in ('binding','scopes','expiry','permission'):
            with self.subTest(kind=kind):
                self.evidence_changes={}
                def mutate():
                    if kind=='binding':self.evidence_changes['binding']=replace(self.verifications[-1][1],target_id='other')
                self.on_verify=mutate
                if kind=='scopes':self.evidence_changes['observed_scopes']=(SCOPE,)
                elif kind=='expiry':self.evidence_changes['credential_expires_at']=NOW+timedelta(hours=2)
                elif kind=='permission':self.evidence_changes['can_publish']=False
                self.assert_error(lambda:self.approve(base))
                self.assertEqual(self.service.read(self.session,'personal.youtube')['publication_grant']['revision'],0)

    def test_registry_connection_and_registration_changes_during_provider_check_are_rejected(self):
        self.grants.initialize();f=self.fixture;body=self.body()
        for kind in ('registry','connection','registration'):
            with self.subTest(kind=kind):
                registry=f.registry;row=f.row.copy();client=self.clients['youtube']
                def change():
                    if kind=='registry':f.registry=replace(registry,revision='changed')
                    elif kind=='connection':f.row['revision']+=1
                    else:self.clients['youtube']=replace(client,client_revision=2)
                self.on_verify=change
                self.assert_error(lambda:self.approve(body))
                f.registry=registry;f.row=row;self.clients['youtube']=client
                self.assertEqual(self.service.read(self.session,'personal.youtube')['publication_grant']['revision'],0)

    def test_policy_preflight_registration_drift_rejected_before_token_read(self):
        self.grants.initialize()
        body=self.body()
        def drift(session,binding,client):
            self.clients['youtube']=replace(client,client_revision=client.client_revision+1)
            return True
        service=self.make_service(authorization_guard=drift)
        self.assert_error(lambda:service.approve(self.session,'personal.youtube',body),'conflict')
        self.assertEqual(self.fixture.reads,0)
        self.assertEqual(self.verifications,[])

    def test_current_scope_client_approval_and_expiry_drift_downgrades_public_status_only(self):
        self.grants.initialize();self.approve()
        f=self.fixture
        for kind in ('scope','client_scopes','expiry'):
            with self.subTest(kind=kind):
                scopes=list(f.row['scopes']);authorization=dict(f.row['authorization']);client=self.clients['youtube']
                if kind=='scope':
                    f.row['scopes']=[SCOPE];f.row['authorization']['observed_scopes']=[SCOPE]
                elif kind=='client_scopes':
                    self.clients['youtube']=replace(client,approved_scopes=(SCOPE,))
                else:
                    f.row['authorization']['credential_expires_at']=(NOW+timedelta(minutes=10)).isoformat()
                before=f.reads
                value=self.service.read(self.session,'personal.youtube')
                self.assertEqual(value['publication_grant']['status'],'blocked')
                self.assertEqual(value['publication_grant']['revision'],1)
                self.assertIn('oauth_publication_binding_changed',value['reason_codes'])
                self.assertIn('revoke',value['available_actions'])
                self.assertEqual(f.reads,before)
                f.row['scopes']=scopes;f.row['authorization']=authorization;self.clients['youtube']=client
        current=self.service.read(self.session,'personal.youtube')
        self.assertEqual(current['publication_grant']['status'],'granted')
        service=self.make_service(verifiers={})
        self.assertEqual(service.read(self.session,'personal.youtube')['publication_grant']['status'],'granted')
