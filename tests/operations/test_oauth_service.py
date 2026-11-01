"""실제 SQLite + 메모리 vault + 서버 주입 fake provider의 OAuth 수명주기."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import unittest
from unittest.mock import patch
from urllib.parse import urlencode, urlsplit, parse_qs

from common.operations.oauth_service import OAuthConnectionService, SessionContext, CallbackContext
from common.operations.oauth_models import OAuthClientRegistration, OAuthPolicy, TokenBundle
from common.operations.oauth_catalog import provider_catalog
from common.operations.oauth_store import OAuthAttemptStore
from common.operations.managed_connections import ManagedConnectionStore
from common.operations.credential_backend import MemoryCredentialBackend, CredentialError
from common.operations.content_store import StoreError
from common.operations.models import Registry, Connection


class FakeProvider:
    def __init__(self,provider_id='youtube'):
        base = next(p for p in provider_catalog() if p.id == provider_id)
        self.definition = replace(base, pkce_mode='s256', policy_reasons=(), operations=tuple(
            replace(r, endpoint='https://provider.test/'+r.operation, contract_status='verified', cost_kind='no_additional_cost')
            for r in base.operations))
        self.calls = []
        self.on_refresh = None
        self.target = 'target'
    def authorize(self, attempt, client_config):
        self.calls.append('authorize')
        self.challenge = attempt['code_challenge']
        return 'https://provider.test/authorize?' + urlencode({'state': attempt['state']})
    def exchange(self, attempt, code, client_secret, verifier=None):
        self.calls.append('exchange')
        import base64
        assert base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode() == self.challenge
        return TokenBundle('secret-access', 'secret-refresh', 'Bearer', None, attempt['context'].requested_scopes)
    def inspect(self, context, bundle):
        self.calls.append('inspect')
        return dict(provider_subject='subject', targets=[dict(target_id=self.target,target_label='채널',capabilities=[])],
                    observed_scopes=list(bundle.scopes), checked_at='2026-11-01T00:00:00+00:00')
    def refresh(self, context, bundle, client_secret):
        self.calls.append('refresh')
        if self.on_refresh: self.on_refresh()
        return TokenBundle('rotated-access', 'rotated-refresh', 'Bearer', None, bundle.scopes)
    def revoke(self, context, bundle, client_secret):
        self.calls.append('revoke')
        return {'remote_revoked': True}


class OAuthServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.now = datetime(2026,11,1,tzinfo=timezone.utc)
        self.clock = lambda: self.now
        self.attempts = OAuthAttemptStore(self.tmp.name,self.clock); self.attempts.initialize()
        self.connections_store = ManagedConnectionStore(self.tmp.name,self.clock)
        self.vault = MemoryCredentialBackend(); self.provider = FakeProvider(); self.provider_id='youtube'
        self.registry = Registry('base',{'personal':{},'dept':{}},{},{},
            {'personal.youtube':Connection('personal.youtube','personal','youtube',target_id='target')},{},{},{})
        self.scope = self.provider.definition.read_scopes[0]
        self.registration = OAuthClientRegistration('youtube','client',None,'https://console.test/oauth/callback/youtube',1,(self.scope,),
            self.provider.definition.operations[0].evidence_revision,None)
        self.session = SessionContext('console_user','session-binding')
        self.callback = CallbackContext('youtube',self.registration.redirect_uri)
        self.service = self.make_service()
    def make_service(self, **kwargs):
        values = dict(registry_supplier=lambda:self.registry,client_registrations={'youtube':self.registration},
            attempt_store=self.attempts,connection_store=self.connections_store,backend=self.vault,
            providers={'youtube':self.provider},policy=OAuthPolicy(True),clock=self.clock,cost_guard=lambda *args:None)
        values.update(kwargs)
        return OAuthConnectionService(**values)
    def body(self, key='start'):
        return dict(request_key=key,account_id='personal',provider_id=self.provider_id,connection_id='personal.youtube',
            expected_base_revision='base',expected_connection_revision=0,requested_scopes=[self.scope] if self.scope else [])
    def start(self,key='start'):
        started=self.service.start(self.session,self.body(key))
        state=parse_qs(urlsplit(started['authorize_url']).query)['state'][0]
        return started,state
    def staged(self):
        started,state=self.start()
        self.service.receive_callback(self.provider_id,{'state':state,'code':'secret-code'},self.callback)
        return self.service.read_attempt(self.session,started['attempt_id'])
    def exchanged(self):
        item=self.staged()
        return self.service.resume_exchange(self.session,item['attempt_id'],dict(request_key='continue',expected_revision=item['revision']))
    def proposal(self):
        item=self.exchanged()
        return self.service.inspect(self.session,item['attempt_id'],dict(request_key='inspect',expected_revision=item['revision']))
    def connected(self):
        item=self.proposal(); proposal=item['target_proposal']
        return self.service.confirm_target(self.session,proposal['proposal_id'],dict(request_key='confirm',
            expected_base_revision='base',expected_connection_revision=0))
    def assert_public(self,value):
        text=json.dumps(value)
        for secret in ('secret-code','secret-access','secret-refresh','session-binding','credential_ref','verifier_ref','ticket_ref','token_ref','client_ref'):
            self.assertNotIn(secret,text)
    def test_default_cost_gate_and_unregistered_catalog_never_call_provider(self):
        service=self.make_service(cost_guard=None)
        with self.assertRaises(StoreError): service.start(self.session,self.body())
        self.assertEqual([],self.provider.calls)
        catalog=self.make_service(client_registrations={}).catalog(self.session,'personal')
        row=next(p for p in catalog['items'] if p['provider_id']=='youtube')
        self.assertEqual('registration_blocked',row['registration_status'])
        self.assert_public(catalog)
    def test_callback_has_no_exchange_replay_and_wrong_session_are_blocked(self):
        started,state=self.start()
        result=self.service.receive_callback('youtube',{'state':state,'code':'secret-code'},self.callback)
        self.assertEqual(['authorize'],self.provider.calls); self.assert_public(result)
        with self.assertRaises(StoreError): self.service.receive_callback('youtube',{'state':state,'code':'again'},self.callback)
        with self.assertRaises(StoreError): self.service.read_attempt(SessionContext('console_user','other'),started['attempt_id'])
        self.assertEqual([],self.service.result_for_session(SessionContext('console_user','other'))['items'])
    def test_reopen_pkce_exchange_once_and_confirm_preserves_execution_disabled(self):
        item=self.staged(); self.service=self.make_service()
        resume_body=dict(request_key='continue',expected_revision=item['revision'])
        item=self.service.resume_exchange(self.session,item['attempt_id'],resume_body)
        self.assertEqual('token_exchanged',item['state']); self.assert_public(item)
        same=self.service.resume_exchange(self.session,item['attempt_id'],resume_body)
        self.assertEqual(item,same); self.assertEqual(1,self.provider.calls.count('exchange'))
        item=self.service.inspect(self.session,item['attempt_id'],dict(request_key='inspect',expected_revision=item['revision']))
        self.service=self.make_service()
        self.assertEqual(item['target_proposal'],self.service.read_attempt(self.session,item['attempt_id'])['target_proposal'])
        p=item['target_proposal']; self.assertEqual({'proposal_id','target_id','target_label','expected_base_revision','expected_connection_revision'},set(p))
        result=self.service.confirm_target(self.session,p['proposal_id'],dict(request_key='confirm',expected_base_revision='base',expected_connection_revision=0))
        self.assertEqual('connected',result['state']); self.assertFalse(result['execution_enabled']); self.assert_public(result)
        self.assertIsNone(self.registry.connections['personal.youtube'].credential_ref)
    def test_expired_ticket_does_not_exchange(self):
        item=self.staged(); self.now+=timedelta(seconds=121)
        with self.assertRaises(StoreError): self.service.resume_exchange(self.session,item['attempt_id'],dict(request_key='continue',expected_revision=item['revision']))
        self.assertNotIn('exchange',self.provider.calls)
    def test_stage_failure_consumes_state_without_exchange(self):
        started,state=self.start()
        with patch.object(self.vault,'put',side_effect=CredentialError('credential_denied')):
            with self.assertRaises(StoreError): self.service.receive_callback('youtube',{'state':state,'code':'secret-code'},self.callback)
        with self.assertRaises(StoreError): self.service.receive_callback('youtube',{'state':state,'code':'secret-code'},self.callback)
        self.assertEqual('error',self.service.read_attempt(self.session,started['attempt_id'])['state'])
        self.assertNotIn('exchange',self.provider.calls)
    def test_target_and_current_base_conflict_before_pointer_commit(self):
        item=self.proposal(); p=item['target_proposal']; self.registry=replace(self.registry,revision='changed')
        with self.assertRaises(StoreError): self.service.confirm_target(self.session,p['proposal_id'],dict(request_key='confirm',expected_base_revision='base',expected_connection_revision=0))
        self.assertEqual({},dict(self.connections_store.snapshot().connections))
    def test_callback_race_has_one_winner(self):
        started,state=self.start()
        def call(_):
            try: self.service.receive_callback('youtube',{'state':state,'code':'secret-code'},self.callback); return True
            except StoreError: return False
        with ThreadPoolExecutor(2) as pool: self.assertEqual(1,sum(pool.map(call,range(2))))
        self.assertNotIn('exchange',self.provider.calls)
    def test_plaintext_secrets_never_enter_sqlite(self):
        self.connected()
        data=Path(self.tmp.name,'oauth.sqlite3').read_bytes()
        for value in (b'secret-code',b'secret-access',b'secret-refresh'):
            self.assertNotIn(value,data)

    def test_start_retry_reopen_reconstructs_same_state_without_raw_state_storage(self):
        first,state=self.start()
        self.service=self.make_service()
        second=self.service.start(self.session,self.body())
        self.assertEqual(first,second)
        self.assertEqual(1,len(self.attempts.list_owned(self.session.session_binding)))
        self.assertNotIn(state.encode(),Path(self.tmp.name,'oauth.sqlite3').read_bytes())
        changed=self.body(); changed['requested_scopes']=[]
        with self.assertRaises(StoreError): self.service.start(self.session,changed)

    def test_actor_account_and_key_rotation_block_before_exchange(self):
        with self.assertRaises(StoreError): SessionContext('internal_key','session-binding')
        body=self.body('wrong-owner'); body['account_id']='dept'
        with self.assertRaises(StoreError): self.service.start(self.session,body)
        item=self.staged()
        service=self.make_service(client_registrations={'youtube':replace(self.registration,client_revision=2)})
        with self.assertRaises(StoreError): service.resume_exchange(self.session,item['attempt_id'],dict(request_key='rotated',expected_revision=item['revision']))
        self.assertNotIn('exchange',self.provider.calls)

    def test_finalize_crash_consumes_callback_and_cleans_only_staged_secrets(self):
        started,state=self.start()
        with patch.object(self.attempts,'finalize_callback',side_effect=StoreError('storage_unavailable')):
            with self.assertRaises(StoreError): self.service.receive_callback('youtube',{'state':state,'code':'secret-code'},self.callback)
        with self.assertRaises(StoreError): self.service.receive_callback('youtube',{'state':state,'code':'secret-code'},self.callback)
        self.assertEqual('error',self.service.read_attempt(self.session,started['attempt_id'])['state'])
        self.assertTrue(all(key[-1] not in ('code','ticket') for key in self.vault._items))

    def test_exchange_uncertain_response_is_not_resent_after_reopen(self):
        item=self.staged(); body=dict(request_key='uncertain',expected_revision=item['revision'])
        with patch.object(self.provider,'exchange',side_effect=RuntimeError('secret-access')):
            with self.assertRaises(StoreError) as raised: self.service.resume_exchange(self.session,item['attempt_id'],body)
        self.assertNotIn('secret-access',str(raised.exception))
        self.assertEqual('unknown',self.service.read_attempt(self.session,item['attempt_id'])['state'])
        self.service=self.make_service()
        with self.assertRaises(StoreError): self.service.resume_exchange(self.session,item['attempt_id'],body)
        with self.assertRaises(StoreError): self.service.resume_exchange(self.session,item['attempt_id'],dict(body,request_key='other'))
        self.assertNotIn('exchange',self.provider.calls)

    def test_inspect_wrong_target_does_not_create_proposal_or_change_original(self):
        item=self.exchanged(); self.provider.target='other-target'
        with self.assertRaises(StoreError): self.service.inspect(self.session,item['attempt_id'],dict(request_key='inspect',expected_revision=item['revision']))
        self.assertIsNone(self.connections_store.proposal_for_attempt(item['attempt_id'],self.session.session_binding))
        self.assertEqual('target',self.registry.connections['personal.youtube'].target_id)

    def test_read_snapshots_do_not_access_vault_or_provider(self):
        self.connected(); before=list(self.provider.calls)
        with patch.object(self.vault,'get',side_effect=AssertionError('GET accessed vault')):
            self.assert_public(self.service.catalog(self.session,'all'))
            self.assert_public(self.service.connections(self.session,'all'))
            self.assert_public(self.service.result_for_session(self.session))
        self.assertEqual(before,self.provider.calls)

    def test_refresh_stages_new_generation_then_deletes_old_only_after_pointer_commit(self):
        self.connected(); old=self.connections_store.snapshot().connections['personal.youtube']['credential_ref']
        observed=[]
        real_finish=self.connections_store.finish_connection_operation
        def finish(lease,**kwargs):
            observed.append(self.vault.get(old))
            observed.append(self.vault.get(kwargs['new_ref']))
            return real_finish(lease,**kwargs)
        with patch.object(self.connections_store,'finish_connection_operation',side_effect=finish):
            result=self.service.refresh(self.session,'personal.youtube',dict(request_key='refresh',expected_base_revision='base',expected_connection_revision=1))
        self.assertEqual('connected',result['state']); self.assertEqual(2,len(observed))
        new=self.connections_store.snapshot().connections['personal.youtube']['credential_ref']
        self.assertGreater(new.generation,old.generation)
        with self.assertRaises(CredentialError): self.vault.get(old)
        self.assertIn(b'rotated-access',self.vault.get(new))

    def test_refresh_after_disconnect_cannot_resurrect_pointer(self):
        self.connected()
        def disconnect_during_refresh():
            row=self.connections_store.snapshot().connections['personal.youtube']
            self.service.disconnect_local(self.session,'personal.youtube',dict(request_key='disconnect',expected_base_revision='base',expected_connection_revision=row['revision']))
        self.provider.on_refresh=disconnect_during_refresh
        with self.assertRaises(StoreError): self.service.refresh(self.session,'personal.youtube',dict(request_key='refresh',expected_base_revision='base',expected_connection_revision=1))
        row=self.connections_store.snapshot().connections['personal.youtube']
        self.assertEqual('disconnected',row['state']); self.assertIsNone(row['credential_ref'])

    def test_refresh_pointer_crash_preserves_old_ref_and_never_retries(self):
        self.connected(); old=self.connections_store.snapshot().connections['personal.youtube']['credential_ref']
        body=dict(request_key='refresh',expected_base_revision='base',expected_connection_revision=1)
        with patch.object(self.connections_store,'finish_connection_operation',side_effect=StoreError('storage_unavailable')):
            with self.assertRaises(StoreError): self.service.refresh(self.session,'personal.youtube',body)
        row=self.connections_store.snapshot().connections['personal.youtube']
        self.assertEqual(old,row['credential_ref']); self.assertIn(b'secret-access',self.vault.get(old))
        self.service=self.make_service()
        with self.assertRaises(StoreError): self.service.refresh(self.session,'personal.youtube',body)
        self.assertEqual(1,self.provider.calls.count('refresh'))

    def test_google_revoke_unknown_project_impact_is_blocked_before_provider(self):
        self.connected()
        with self.assertRaises(StoreError): self.service.revoke(self.session,'personal.youtube',dict(request_key='revoke',expected_base_revision='base',expected_connection_revision=1))
        self.assertNotIn('revoke',self.provider.calls)
        self.assertEqual('connected',self.connections_store.snapshot().connections['personal.youtube']['state'])

    def test_refresh_rechecks_current_base_before_pointer_switch(self):
        self.connected(); old=self.connections_store.snapshot().connections['personal.youtube']['credential_ref']
        self.provider.on_refresh=lambda:setattr(self,'registry',replace(self.registry,revision='changed'))
        with self.assertRaises(StoreError): self.service.refresh(self.session,'personal.youtube',dict(request_key='refresh',expected_base_revision='base',expected_connection_revision=1))
        self.assertEqual(old,self.connections_store.snapshot().connections['personal.youtube']['credential_ref'])

    def test_principal_that_echoes_token_is_not_public(self):
        item=self.exchanged()
        result=dict(provider_subject='secret-access',targets=[dict(target_id='target',target_label='채널')],observed_scopes=[self.scope],checked_at=self.now.isoformat())
        with patch.object(self.provider,'inspect',return_value=result):
            with self.assertRaises(StoreError): self.service.inspect(self.session,item['attempt_id'],dict(request_key='inspect',expected_revision=item['revision']))
        self.assert_public(self.service.result_for_session(self.session))

    def test_refresh_commit_then_error_does_not_delete_active_new_secret(self):
        self.connected(); real_finish=self.connections_store.finish_connection_operation
        def commit_then_crash(*args,**kwargs):
            real_finish(*args,**kwargs)
            raise RuntimeError('commit result lost')
        with patch.object(self.connections_store,'finish_connection_operation',side_effect=commit_then_crash):
            with self.assertRaises(StoreError): self.service.refresh(self.session,'personal.youtube',dict(request_key='refresh',expected_base_revision='base',expected_connection_revision=1))
        row=self.connections_store.snapshot().connections['personal.youtube']
        self.assertEqual('connected',row['state'])
        self.assertIn(b'rotated-access',self.vault.get(row['credential_ref']))

    def test_exchange_commit_then_error_preserves_referenced_token(self):
        item=self.staged(); real_update=self.attempts.update_attempt
        def commit_then_crash(*args,**kwargs):
            result=real_update(*args,**kwargs)
            if args[3]=='token_exchanged': raise RuntimeError('commit result lost')
            return result
        with patch.object(self.attempts,'update_attempt',side_effect=commit_then_crash):
            with self.assertRaises(StoreError): self.service.resume_exchange(self.session,item['attempt_id'],dict(request_key='continue',expected_revision=item['revision']))
        saved=self.attempts.read_owned(item['attempt_id'],self.session.session_binding)
        self.assertEqual('token_exchanged',saved['state'])
        self.assertIn(b'secret-access',self.vault.get(saved['token_ref']))

    def test_callback_commit_then_error_preserves_staged_code_and_ticket(self):
        started,state=self.start(); real_finalize=self.attempts.finalize_callback
        def commit_then_crash(*args,**kwargs):
            real_finalize(*args,**kwargs)
            raise RuntimeError('commit result lost')
        with patch.object(self.attempts,'finalize_callback',side_effect=commit_then_crash):
            with self.assertRaises(StoreError): self.service.receive_callback('youtube',{'state':state,'code':'secret-code'},self.callback)
        saved=self.attempts.read_owned(started['attempt_id'],self.session.session_binding)
        self.assertEqual('callback_staged',saved['state'])
        self.assertEqual(b'secret-code',self.vault.get(saved['code_ref']))
        self.assertEqual(32,len(self.vault.get(saved['ticket_ref'])))

    def test_new_connection_null_id_is_server_issued_once_and_confirmed_by_cas(self):
        body=self.body('new'); body['connection_id']=None
        started=self.service.start(self.session,body)
        self.assertTrue(started['connection_id'].startswith('oauth.'))
        self.service=self.make_service()
        self.assertEqual(started,self.service.start(self.session,body))
        state=parse_qs(urlsplit(started['authorize_url']).query)['state'][0]
        self.service.receive_callback('youtube',{'state':state,'code':'secret-code'},self.callback)
        item=self.service.read_attempt(self.session,started['attempt_id'])
        item=self.service.resume_exchange(self.session,item['attempt_id'],dict(request_key='new-continue',expected_revision=item['revision']))
        item=self.service.inspect(self.session,item['attempt_id'],dict(request_key='new-inspect',expected_revision=item['revision']))
        p=item['target_proposal']
        self.service.confirm_target(self.session,p['proposal_id'],dict(request_key='new-confirm',expected_base_revision='base',expected_connection_revision=0))
        rows=self.service.connections(self.session,'personal')['items']
        row=next(row for row in rows if row.get('id')==started['connection_id'])
        self.assertEqual('youtube',row['provider_id']); self.assertFalse(row['execution_enabled'])
        bad=self.body('bad-null'); bad.update(connection_id=None,expected_connection_revision=1)
        with self.assertRaises(StoreError): self.service.start(self.session,bad)

    def test_client_rotation_before_confirmation_does_not_commit_old_registration(self):
        item=self.proposal(); p=item['target_proposal']
        self.service=self.make_service(client_registrations={'youtube':replace(self.registration,client_revision=2)})
        with self.assertRaises(StoreError): self.service.confirm_target(self.session,p['proposal_id'],dict(request_key='confirm',expected_base_revision='base',expected_connection_revision=0))
        self.assertEqual({},dict(self.connections_store.snapshot().connections))

    def use_provider(self,provider_id):
        self.provider_id=provider_id; self.provider=FakeProvider(provider_id)
        self.scope=next(iter(self.provider.definition.read_scopes),'')
        self.registration=replace(self.registration,provider_id=provider_id,approved_scopes=(self.scope,) if self.scope else (),
            redirect_uri='https://console.test/oauth/callback/'+provider_id)
        self.callback=CallbackContext(provider_id,self.registration.redirect_uri)
        self.registry=replace(self.registry,connections={'personal.youtube':Connection('personal.youtube','personal',self.provider.definition.platform,target_id='target')})
        self.service=self.make_service(client_registrations={provider_id:self.registration},providers={provider_id:self.provider})

    def test_non_google_remote_revoke_and_failure_stay_separate_from_local_disconnect(self):
        self.use_provider('threads'); self.connected()
        result=self.service.revoke(self.session,'personal.youtube',dict(request_key='revoke',expected_base_revision='base',expected_connection_revision=1))
        self.assertEqual('revoked',result['state']); self.assertIn('revoke',self.provider.calls)

    def test_remote_revoke_failure_does_not_claim_revoked_or_delete_previous_secret(self):
        self.use_provider('threads'); self.connected(); old=self.connections_store.snapshot().connections['personal.youtube']['credential_ref']
        with patch.object(self.provider,'revoke',side_effect=RuntimeError('private-provider-error')):
            with self.assertRaises(StoreError) as raised: self.service.revoke(self.session,'personal.youtube',dict(request_key='revoke',expected_base_revision='base',expected_connection_revision=1))
        self.assertNotIn('private-provider-error',str(raised.exception))
        row=self.connections_store.snapshot().connections['personal.youtube']
        self.assertEqual('unknown',row['state']); self.assertEqual(old,row['credential_ref'])
        self.assertIn(b'secret-access',self.vault.get(old))

    def test_naver_exchange_without_raw_state_is_contract_blocked(self):
        self.use_provider('naver'); item=self.staged()
        with self.assertRaises(StoreError): self.service.resume_exchange(self.session,item['attempt_id'],dict(request_key='continue',expected_revision=item['revision']))
        self.assertNotIn('exchange',self.provider.calls)

    def test_unknown_non_null_connection_id_does_not_create_new_connection(self):
        body=self.body(); body['connection_id']='caller-invented'
        with self.assertRaises(StoreError): self.service.start(self.session,body)
        self.assertEqual([],self.provider.calls)

    def test_instagram_same_platform_other_login_cannot_reuse_connected_credentials(self):
        self.use_provider('instagram_login'); self.connected()
        second=FakeProvider('instagram_facebook')
        registration=replace(self.registration,provider_id='instagram_facebook',redirect_uri='https://console.test/oauth/callback/instagram_facebook',
            approved_scopes=second.definition.read_scopes)
        service=self.make_service(client_registrations={'instagram_facebook':registration},providers={'instagram_facebook':second})
        body=self.body('other-login'); body.update(provider_id='instagram_facebook',expected_connection_revision=1,requested_scopes=list(second.definition.read_scopes))
        with self.assertRaises(StoreError): service.start(self.session,body)
        self.assertEqual([],second.calls)

    def test_provider_authorize_url_cannot_expose_token_query(self):
        with patch.object(self.provider,'authorize',return_value='https://provider.test/authorize?access_token=secret-access'):
            with self.assertRaises(StoreError): self.service.start(self.session,self.body())
        self.assert_public(self.service.result_for_session(self.session))

    def test_denied_new_consent_preserves_existing_connection_and_cleans_attempt_secrets(self):
        self.connected(); old=self.connections_store.snapshot().connections['personal.youtube']['credential_ref']
        body=self.body('reconsent'); body['expected_connection_revision']=1
        started=self.service.start(self.session,body)
        state=parse_qs(urlsplit(started['authorize_url']).query)['state'][0]
        item=self.attempts.read_owned(started['attempt_id'],self.session.session_binding)
        self.service.receive_callback('youtube',{'state':state,'error':'access_denied'},self.callback)
        self.assertEqual('denied',self.service.read_attempt(self.session,started['attempt_id'])['state'])
        self.assertEqual(old,self.connections_store.snapshot().connections['personal.youtube']['credential_ref'])
        self.assertIn(b'secret-access',self.vault.get(old))
        for key in ('state_key_ref','verifier_ref'):
            with self.assertRaises(CredentialError): self.vault.get(item[key])

    def test_authorization_metadata_is_observed_persisted_and_not_attempt_expiry(self):
        item=self.staged()
        expiry='2026-11-01T01:00:00+00:00'
        bundle=TokenBundle('secret-access','secret-refresh','Bearer',expiry,(self.scope,))
        with patch.object(self.provider,'exchange',return_value=bundle):
            item=self.service.resume_exchange(self.session,item['attempt_id'],dict(request_key='continue',expected_revision=item['revision']))
        self.assertEqual(dict(observed_scopes=[self.scope],credential_expires_at=expiry,read_status='not_checked',
            publication_status='blocked',credential_status='stored'),item['authorization'])
        self.assertNotEqual(item['expires_at'],item['authorization']['credential_expires_at'])
        item=self.service.inspect(self.session,item['attempt_id'],dict(request_key='inspect',expected_revision=item['revision']))
        self.assertEqual('verified',item['authorization']['read_status'])
        p=item['target_proposal']; self.service.confirm_target(self.session,p['proposal_id'],dict(request_key='confirm',expected_base_revision='base',expected_connection_revision=0))
        self.service=self.make_service()
        with patch.object(self.vault,'get',side_effect=AssertionError('GET accessed vault')):
            result=self.service.read_attempt(self.session,item['attempt_id'])
            row=next(row for row in self.service.connections(self.session,'personal')['items'] if row['id']=='personal.youtube')
        self.assertEqual('active',result['authorization']['credential_status'])
        self.assertEqual('active',row['authorization']['credential_status']); self.assertEqual(expiry,row['authorization']['credential_expires_at'])
        self.assertFalse(row['execution_enabled']); self.assertEqual('blocked',row['authorization']['publication_status'])

    def test_missing_granted_scopes_are_not_filled_from_requested_scopes(self):
        item=self.staged(); bundle=TokenBundle('secret-access',None,'Bearer',None,())
        with patch.object(self.provider,'exchange',return_value=bundle):
            item=self.service.resume_exchange(self.session,item['attempt_id'],dict(request_key='continue',expected_revision=item['revision']))
        self.assertIsNone(item['authorization']['observed_scopes'])
        self.assertIsNone(item['authorization']['credential_expires_at'])

    def test_known_expired_credential_is_not_used_for_inspect_or_confirmation(self):
        item=self.staged(); bundle=TokenBundle('secret-access',None,'Bearer',(self.now-timedelta(seconds=1)).isoformat(),(self.scope,))
        with patch.object(self.provider,'exchange',return_value=bundle):
            with self.assertRaises(StoreError): self.service.resume_exchange(self.session,item['attempt_id'],dict(request_key='continue',expected_revision=item['revision']))
        self.assertNotIn('inspect',self.provider.calls)

    def test_callback_attempt_expiry_wrong_callback_boundary_and_null_session_are_blocked(self):
        started,state=self.start()
        with self.assertRaises(StoreError): self.service.receive_callback('youtube',{'state':state,'code':'secret-code'},CallbackContext('youtube','https://other.test/oauth/callback/youtube'))
        with self.assertRaises(StoreError): self.service.start(None,self.body('null-session'))
        self.now+=timedelta(minutes=10)
        with self.assertRaises(StoreError): self.service.receive_callback('youtube',{'state':state,'code':'secret-code'},self.callback)
        self.assertNotIn('exchange',self.provider.calls)
        self.assertEqual('expired',self.service.read_attempt(self.session,started['attempt_id'])['state'])

    def test_two_tabs_confirm_only_one_generation_and_keep_winner_secret(self):
        proposals=[]
        for key in ('tab-a','tab-b'):
            started,state=self.start(key)
            self.service.receive_callback('youtube',{'state':state,'code':'secret-code'},self.callback)
            item=self.service.read_attempt(self.session,started['attempt_id'])
            item=self.service.resume_exchange(self.session,item['attempt_id'],dict(request_key=key+'-continue',expected_revision=item['revision']))
            item=self.service.inspect(self.session,item['attempt_id'],dict(request_key=key+'-inspect',expected_revision=item['revision']))
            proposals.append(item['target_proposal'])
        def confirm(proposal):
            try:
                self.service.confirm_target(self.session,proposal['proposal_id'],dict(request_key=proposal['proposal_id'],expected_base_revision='base',expected_connection_revision=0))
                return True
            except StoreError: return False
        with ThreadPoolExecutor(2) as pool: self.assertEqual(1,sum(pool.map(confirm,proposals)))
        row=self.connections_store.snapshot().connections['personal.youtube']
        self.assertEqual('connected',row['state']); self.assertIn(b'secret-access',self.vault.get(row['credential_ref']))
        self.assertFalse(row['execution_enabled'])

    def test_refresh_observed_expiry_is_stored_with_new_active_generation(self):
        self.connected(); expiry='2026-11-01T02:00:00+00:00'
        bundle=TokenBundle('rotated-access','rotated-refresh','Bearer',expiry,(self.scope,))
        with patch.object(self.provider,'refresh',return_value=bundle):
            result=self.service.refresh(self.session,'personal.youtube',dict(request_key='refresh',expected_base_revision='base',expected_connection_revision=1))
        self.assertEqual(expiry,result['authorization']['credential_expires_at'])
        self.assertEqual('active',result['authorization']['credential_status'])
        self.service=self.make_service()
        with patch.object(self.vault,'get',side_effect=AssertionError('GET accessed vault')):
            row=next(row for row in self.service.connections(self.session,'personal')['items'] if row['id']=='personal.youtube')
        self.assertEqual(result['authorization'],row['authorization'])
        self.assertEqual('verified',row['authorization']['read_status']); self.assertEqual('blocked',row['authorization']['publication_status'])

    def test_same_actor_new_login_manages_completed_connection_after_reopen(self):
        self.connected(); self.service=self.make_service()
        new_session=SessionContext('console_user','new-login-session')
        row=next(row for row in self.service.connections(new_session,'personal')['items'] if row['id']=='personal.youtube')
        self.assertIn('disconnect',row['available_actions']); self.assertIn('refresh',row['available_actions'])
        result=self.service.disconnect_local(new_session,'personal.youtube',dict(request_key='new-login-disconnect',expected_base_revision='base',expected_connection_revision=row['connection_revision']))
        self.assertEqual('disconnected',result['state']); self.assertFalse(result['execution_enabled'])
        self.assertEqual([],self.service.result_for_session(new_session)['items'])

    def test_new_session_cannot_read_or_continue_unfinished_attempt(self):
        item=self.staged(); new_session=SessionContext('console_user','new-login-session')
        self.assertEqual([],self.service.result_for_session(new_session)['items'])
        with self.assertRaises(StoreError): self.service.read_attempt(new_session,item['attempt_id'])
        with self.assertRaises(StoreError): self.service.resume_exchange(new_session,item['attempt_id'],dict(request_key='new-continue',expected_revision=item['revision']))
        self.assertNotIn('exchange',self.provider.calls)
        self.assertEqual('callback_staged',self.service.read_attempt(self.session,item['attempt_id'])['state'])

    def test_expired_flow_does_not_expire_durable_completed_management_or_use_old_ref(self):
        self.connected()
        self.service.refresh(self.session,'personal.youtube',dict(request_key='first-refresh',expected_base_revision='base',expected_connection_revision=1))
        active=self.connections_store.snapshot().connections['personal.youtube']
        self.now+=timedelta(minutes=11); self.service=self.make_service(); new_session=SessionContext('console_user','new-login-session')
        captured=[]
        def refresh(wrapper,bundle,secret):
            captured.append(bundle.access_token)
            return TokenBundle('newest-access','newest-refresh','Bearer',None,bundle.scopes)
        with patch.object(self.provider,'refresh',side_effect=refresh):
            result=self.service.refresh(new_session,'personal.youtube',dict(request_key='new-login-refresh',expected_base_revision='base',expected_connection_revision=active['revision']))
        self.assertEqual(['rotated-access'],captured); self.assertEqual('connected',result['state'])
        current=self.connections_store.snapshot().connections['personal.youtube']
        self.assertGreater(current['credential_generation'],active['credential_generation'])
        self.assertIn(b'newest-access',self.vault.get(current['credential_ref']))

    def test_other_actor_cannot_manage_completed_connection_even_with_forged_session_object(self):
        self.connected()
        with self.assertRaises(StoreError): SessionContext('other_actor','other-session')
        forged=SessionContext('console_user','other-session'); object.__setattr__(forged,'actor','other_actor')
        with self.assertRaises(StoreError): self.service.connections(forged,'personal')
        with self.assertRaises(StoreError): self.service.disconnect_local(forged,'personal.youtube',dict(request_key='other-actor',expected_base_revision='base',expected_connection_revision=1))
        self.assertEqual('connected',self.connections_store.snapshot().connections['personal.youtube']['state'])

    def test_new_login_uses_latest_completed_registration_context(self):
        self.connected(); self.registration=replace(self.registration,client_revision=2); self.service=self.make_service()
        body=self.body('new-registration'); body['expected_connection_revision']=1
        started=self.service.start(self.session,body)
        state=parse_qs(urlsplit(started['authorize_url']).query)['state'][0]
        self.service.receive_callback('youtube',{'state':state,'code':'secret-code'},self.callback)
        item=self.service.read_attempt(self.session,started['attempt_id'])
        item=self.service.resume_exchange(self.session,item['attempt_id'],dict(request_key='second-continue',expected_revision=item['revision']))
        item=self.service.inspect(self.session,item['attempt_id'],dict(request_key='second-inspect',expected_revision=item['revision']))
        self.service.confirm_target(self.session,item['target_proposal']['proposal_id'],dict(request_key='second-confirm',expected_base_revision='base',expected_connection_revision=1))
        self.service=self.make_service(); session=SessionContext('console_user','new-login-session')
        current=self.connections_store.snapshot().connections['personal.youtube']; revisions=[]
        original=self.provider.refresh
        def refresh(wrapper,bundle,secret):
            revisions.append(wrapper['context'].client_revision)
            return original(wrapper,bundle,secret)
        with patch.object(self.provider,'refresh',side_effect=refresh):
            result=self.service.refresh(session,'personal.youtube',dict(request_key='new-registration-refresh',expected_base_revision='base',expected_connection_revision=current['revision']))
        self.assertEqual([2],revisions); self.assertEqual('connected',result['state'])

    def test_new_login_rechecks_registration_and_cost_before_remote_lifecycle(self):
        self.connected(); session=SessionContext('console_user','new-login-session')
        rotated=self.make_service(client_registrations={'youtube':replace(self.registration,client_revision=2)})
        row=next(row for row in rotated.connections(session,'personal')['items'] if row['id']=='personal.youtube')
        self.assertEqual(['disconnect'],row['available_actions'])
        body=dict(request_key='rotated-registration',expected_base_revision='base',expected_connection_revision=1)
        with self.assertRaises(StoreError): rotated.refresh(session,'personal.youtube',body)
        strict=self.make_service(cost_guard=None)
        with self.assertRaises(StoreError): strict.refresh(session,'personal.youtube',dict(body,request_key='cost-unconfirmed'))
        self.assertNotIn('refresh',self.provider.calls)
        self.assertEqual('connected',self.connections_store.snapshot().connections['personal.youtube']['state'])

    def test_new_login_can_revoke_completed_non_google_connection(self):
        self.use_provider('threads'); self.connected(); self.now+=timedelta(minutes=11)
        self.service=self.make_service(client_registrations={'threads':self.registration},providers={'threads':self.provider})
        session=SessionContext('console_user','new-login-session')
        result=self.service.revoke(session,'personal.youtube',dict(request_key='new-login-revoke',expected_base_revision='base',expected_connection_revision=1))
        self.assertEqual('revoked',result['state']); self.assertFalse(result['execution_enabled'])


if __name__=='__main__': unittest.main()
