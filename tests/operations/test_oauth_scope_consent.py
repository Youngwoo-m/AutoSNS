"""명시 서버 scope 정책은 실제 OAuth 권한·비용·발행 허가를 만들지 않는다."""
from dataclasses import replace,FrozenInstanceError,asdict
import hashlib
import hmac
import json
import base64
import unittest
from urllib.parse import parse_qs,urlsplit
from common.operations.content_store import StoreError
from common.operations.oauth_models import TokenBundle
from unittest.mock import patch
from common.operations.oauth_scope_consent import PublicationConsentRegistration,PublicationScopeConsentPolicy
from tests.operations import test_oauth_service as fixtures

class OAuthScopeConsentTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.OAuthServiceTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.definition=self.f.provider.definition
        self.full=tuple(self.definition.read_scopes+self.definition.publication_scopes)
        self.client=replace(self.f.registration,approved_scopes=self.full)
        self.registration=PublicationConsentRegistration(self.definition.id,self.client.client_revision,self.client.cost_evidence_revision,self.full)
        self.policy=PublicationScopeConsentPolicy('consent-1',(self.registration,))
    def service(self,policy=None,client=None):
        return self.f.make_service(client_registrations={'youtube':client or self.client},scope_consent_policy=policy)
    def body(self,scopes=None):return {**self.f.body(), 'requested_scopes':list(self.full if scopes is None else scopes)}

    def test_default_partial_read_only_and_publication_denied(self):
        for scopes in ((),self.definition.read_scopes):
            PublicationScopeConsentPolicy().validate(self.definition,self.client,scopes)
        service=self.service()
        with self.assertRaises(StoreError):service.start(self.f.session,self.body())
        self.assertEqual(self.f.provider.calls,[])
        self.assertEqual(service.start(self.f.session,{**self.body(self.definition.read_scopes),'request_key':'read-start'})['state'],'consent_pending')

    def test_explicit_full_grant_bound_revision_and_no_publication_status_upgrade(self):
        service=self.service(self.policy)
        started=service.start(self.f.session,self.body())
        item=service.attempt_store.read_owned(started['attempt_id'],self.f.session.session_binding)
        self.assertEqual(item['context'].scope_policy_revision,'consent-1')
        self.assertEqual(started['authorization']['publication_status'],'blocked')
        self.assertEqual(self.f.provider.calls,['authorize'])
        service.scope_consent_policy=replace(self.policy,revision='consent-2')
        with self.assertRaises(StoreError):service._gate(item['context'],'exchange')
        self.assertEqual(self.f.provider.calls,['authorize'])

    def test_stale_client_evidence_approval_and_unknown_or_partial_scopes_reject(self):
        cases=[(self.policy,replace(self.client,client_revision=2),self.full),
            (self.policy,replace(self.client,cost_evidence_revision='changed'),self.full),
            (self.policy,replace(self.client,approved_scopes=self.full+('unknown',)),self.full),
            (self.policy,self.client,self.definition.publication_scopes),
            (self.policy,self.client,self.full+('unknown',))]
        for policy,client,scopes in cases:
            with self.subTest(scopes=scopes),self.assertRaises(StoreError):policy.validate(self.definition,client,scopes)
        self.assertEqual(self.f.provider.calls,[])

    def test_policy_is_immutable_and_hard_denies_internal_utility_providers(self):
        with self.assertRaises(FrozenInstanceError):self.policy.revision='other'
        original=list(self.full);reg=replace(self.registration,approved_scopes=original);original.append('mutated');self.assertNotIn('mutated',reg.approved_scopes)
        for provider_id in ('tiktok','naver','tistory'):
            definition=replace(self.definition,id=provider_id)
            client=replace(self.client,provider_id=provider_id)
            policy=PublicationScopeConsentPolicy('p',(replace(self.registration,provider_id=provider_id),))
            with self.assertRaises(StoreError):policy.validate(definition,client,self.full)

    def test_user_cannot_supply_policy_revision_and_read_context_stays_legacy(self):
        service=self.service(self.policy)
        with self.assertRaises(StoreError):service.start(self.f.session,{**self.body(),'scope_policy_revision':'consent-1'})
        started=service.start(self.f.session,self.body(self.definition.read_scopes))
        item=service.attempt_store.read_owned(started['attempt_id'],self.f.session.session_binding)
        self.assertIsNone(item['context'].scope_policy_revision)

    def test_legacy_read_state_hmac_omits_new_optional_field(self):
        service=self.service()
        started=service.start(self.f.session,self.body(self.definition.read_scopes))
        context=service.attempt_store.read_owned(started['attempt_id'],self.f.session.session_binding)['context']
        legacy=asdict(context);legacy.pop('scope_policy_revision')
        message=json.dumps(dict(receipt_id='receipt',context=legacy),sort_keys=True,separators=(',',':')).encode()
        expected=base64.urlsafe_b64encode(hmac.new(b'fixture-key',message,hashlib.sha256).digest()).rstrip(b'=').decode()
        self.assertEqual(service._state(context,'receipt',b'fixture-key'),expected)

    def connect_publication_fixture(self, partial=False):
        service=self.service(self.policy)
        started=service.start(self.f.session,self.body())
        state=parse_qs(urlsplit(started['authorize_url']).query)['state'][0]
        service.receive_callback('youtube',{'state':state,'code':'fixture-code'},self.f.callback)
        item=service.read_attempt(self.f.session,started['attempt_id'])
        if partial:
            bundle=TokenBundle('fixture-access','fixture-refresh','Bearer',None,self.definition.read_scopes)
            with patch.object(self.f.provider,'exchange',return_value=bundle):
                item=service.resume_exchange(self.f.session,item['attempt_id'],dict(request_key='exchange',expected_revision=item['revision']))
        else:
            item=service.resume_exchange(self.f.session,item['attempt_id'],dict(request_key='exchange',expected_revision=item['revision']))
        item=service.inspect(self.f.session,item['attempt_id'],dict(request_key='inspect',expected_revision=item['revision']))
        service.confirm_target(self.f.session,item['target_proposal']['proposal_id'],dict(request_key='confirm',expected_base_revision='base',expected_connection_revision=0))
        return service

    def test_complete_publication_consent_flow_refresh_preserves_scope_and_policy_binding(self):
        service=self.connect_publication_fixture()
        before=self.f.connections_store.snapshot().connections['personal.youtube']
        self.assertEqual(set(before['scopes']),set(self.full))
        original=before['credential_generation']
        result=service.refresh(self.f.session,'personal.youtube',dict(request_key='refresh',expected_base_revision='base',expected_connection_revision=before['revision']))
        after=self.f.connections_store.snapshot().connections['personal.youtube']
        self.assertGreater(after['credential_generation'],original)
        self.assertEqual(set(result['authorization']['observed_scopes']),set(self.full))
        self.assertEqual(result['authorization']['publication_status'],'blocked')
        self.assertFalse(result['execution_enabled'])
        context=service._completed_context(self.f.session,after)
        self.assertEqual(context.scope_policy_revision,'consent-1')
        self.assertIn('refresh',service._available_remote_actions(context))
        service.scope_consent_policy=replace(self.policy,revision='consent-2')
        calls=list(self.f.provider.calls)
        self.assertEqual(service._available_remote_actions(context),[])
        with self.assertRaises(StoreError):service.refresh(self.f.session,'personal.youtube',dict(request_key='stale-refresh',expected_base_revision='base',expected_connection_revision=after['revision']))
        self.assertEqual(self.f.provider.calls,calls)

    def test_partial_actual_grant_never_invents_requested_publication_scope(self):
        service=self.connect_publication_fixture(partial=True)
        row=self.f.connections_store.snapshot().connections['personal.youtube']
        self.assertEqual(set(row['authorization']['observed_scopes']),set(self.definition.read_scopes))
        self.assertFalse(set(self.definition.publication_scopes)&set(row['scopes']))
        self.assertEqual(row['authorization']['publication_status'],'blocked')
        context=service._completed_context(self.f.session,row)
        self.assertEqual(set(context.requested_scopes),set(self.full))
        result=service.refresh(self.f.session,'personal.youtube',dict(request_key='partial-refresh',expected_base_revision='base',expected_connection_revision=row['revision']))
        self.assertEqual(set(result['authorization']['observed_scopes']),set(self.definition.read_scopes))
        self.assertEqual(result['authorization']['publication_status'],'blocked')

    def test_catalog_advertises_only_current_explicit_policy_without_provider_calls(self):
        service=self.service(self.policy)
        row=next(r for r in service.catalog(self.f.session)['items'] if r['provider_id']=='youtube')
        self.assertEqual(row['scope_consent'],dict(available=True,policy_revision='consent-1',requested_scopes=list(self.full)))
        self.assertEqual(self.f.provider.calls,[])
        service.scope_consent_policy=PublicationScopeConsentPolicy()
        row=next(r for r in service.catalog(self.f.session)['items'] if r['provider_id']=='youtube')
        self.assertEqual(row['scope_consent'],dict(available=False,policy_revision=None,requested_scopes=[]))
        self.assertEqual(self.f.provider.calls,[])
