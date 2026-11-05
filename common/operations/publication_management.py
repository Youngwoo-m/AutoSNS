"""명시 사용자 세션의 발행 사용 승인 관리. 기본 연결·기동·공급자는 활성화하지 않는다.

조회는 vault·공급자 검사·저장소 초기화를 하지 않는다. 승인만 신뢰된 읽기 resolver와
공급자 verifier를 사용하며, 요청 body에 scope·대상·증거·만료를 받지 않는다.
OAuth writer guard 안에서 관측과 현재 문맥을 재검증한 뒤 CAS로 승인 이력을 추가한다.
"""
from collections.abc import Mapping
from datetime import datetime,timezone
from pathlib import Path
import re
from types import MappingProxyType

from .content_store import StoreError,ConflictError
from .managed_connections import credential_catalog,project_registry
from .models import Registry
from .oauth_catalog import provider_catalog
from .oauth_models import OAuthClientRegistration,validate_authorization
from .oauth_service import SessionContext
from .oauth_stage_models import OwnedCredentialRef,logical_ref
from .oauth_workspace import oauth_write_guard,validate_workspace_context
from .publication_authority import credential_fingerprint
from .publication_grants import PublicationGrantStore,PublicationGrantBinding,VerifiedPublicationEvidence
from .runtime_models import utc

_BODY={'request_key','expected_base_revision','expected_connection_revision','expected_grant_revision'}
_VERIFIABLE=frozenset(('youtube','blogger'))
_SAFE={'invalid','not_found','conflict','oauth_session_required','oauth_registration_blocked',
       'credential_owner_mismatch','oauth_scope_unverified','oauth_credential_expired','credential_changed',
       'oauth_publication_unverified'}


def _error(code='oauth_publication_unverified'):raise StoreError(code) from None


def _scope_set(values):
    if (not isinstance(values,(list,tuple)) or any(type(v) is not str or not v for v in values) or
            len(values)!=len(set(values))):_error('oauth_scope_unverified')
    return set(values)


class PublicationGrantManagementService:
    def __init__(self,*,registry_supplier,connection_store,resolver,grant_store,client_registrations,
                 verifiers,authorization_guard=None,clock=None):
        if (not callable(registry_supplier) or not callable(getattr(connection_store,'snapshot',None)) or
                not callable(getattr(resolver,'use',None)) or type(grant_store) is not PublicationGrantStore or
                not isinstance(client_registrations,Mapping) or not isinstance(verifiers,Mapping) or
                any(provider not in _VERIFIABLE or not callable(getattr(verifier,'verify',None)) for provider,verifier in verifiers.items()) or
                authorization_guard is not None and not callable(authorization_guard) or
                clock is not None and not callable(clock)):_error('invalid')
        context=getattr(resolver,'workspace_context',None)
        if (context is None or context.owner!=grant_store.context.owner or context.root!=grant_store.context.root or
                getattr(resolver,'connection_store',None) is not connection_store):_error('credential_owner_mismatch')
        self.registry=registry_supplier;self.connections=connection_store;self.resolver=resolver
        self.store=grant_store;self.clients=client_registrations;self.verifiers=MappingProxyType(dict(verifiers))
        self.authorization_guard=authorization_guard;self.clock=clock or (lambda:datetime.now(timezone.utc))

    def __repr__(self):return 'PublicationGrantManagementService(<비공개>)'

    @staticmethod
    def _session(session):
        if type(session) is not SessionContext:_error('oauth_session_required')
        session.__post_init__()
        return session

    def _state(self,connection_id):
        if (type(connection_id) is not str or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,300}',connection_id)):_error('invalid')
        context=validate_workspace_context(self.store.context)
        if Path(self.connections.root).resolve()!=context.root:_error('credential_owner_mismatch')
        snapshot=self.connections.snapshot();registry=self.registry()
        if (not isinstance(registry,Registry) or snapshot.workspace_owner!=context.owner or
                snapshot.base_revision!=registry.revision):_error('credential_owner_mismatch')
        row=snapshot.connections.get(connection_id)
        if not isinstance(row,Mapping) or row.get('state')!='connected':_error('not_found')
        if row.get('operation_lease') is not None:_error('credential_changed')
        catalog=credential_catalog(snapshot)
        ref=row.get('credential_ref')
        if type(ref) is not OwnedCredentialRef:_error('credential_owner_mismatch')
        logical=logical_ref(ref)
        reference=f'oauth:{logical.account_id}:{logical.platform}:{logical.connection_id}:{logical.generation}'
        entry=catalog.get(reference)
        current=project_registry(registry,snapshot).connections.get(connection_id)
        if (not isinstance(entry,Mapping) or entry.get('credential_ref')!=ref or
                (ref.workspace_id,ref.root_binding)!=(context.owner.workspace_id,context.owner.root_binding) or
                logical.connection_id!=connection_id or row.get('connection_id')!=connection_id or
                row.get('account_id')!=logical.account_id or row.get('platform')!=logical.platform or
                row.get('credential_generation')!=logical.generation or row.get('base_revision')!=registry.revision or
                current is None or current.account_id!=logical.account_id or current.platform!=logical.platform or
                current.target_id!=row.get('target_id')):_error('credential_owner_mismatch')
        client=self.clients.get(row.get('provider_id'))
        if type(client) is not OAuthClientRegistration or client.provider_id!=row.get('provider_id'):_error('oauth_registration_blocked')
        binding=PublicationGrantBinding(owner=context.owner,registry_revision=registry.revision,
            connection_id=connection_id,account_id=logical.account_id,platform=logical.platform,
            provider_id=client.provider_id,target_id=row['target_id'],provider_subject=row['provider_subject'],
            connection_revision=row['revision'],credential_generation=logical.generation,
            credential_fingerprint=credential_fingerprint(ref),client_revision=client.client_revision,
            evidence_revision=client.cost_evidence_revision)
        provider=next((p for p in provider_catalog() if p.id==binding.provider_id),None)
        authorization=row.get('authorization')
        if provider is None or not isinstance(authorization,Mapping):_error('oauth_scope_unverified')
        authorization=validate_authorization(dict(authorization))
        observed=_scope_set(authorization['observed_scopes'])
        if (authorization['credential_status']!='active' or authorization['read_status']!='verified' or
                observed!=_scope_set(row.get('scopes')) or
                not set(provider.read_scopes)<=observed or
                not observed<=set(provider.read_scopes)|set(provider.publication_scopes)):_error('oauth_scope_unverified')
        return dict(binding=binding,client=client,reference=reference,observed=observed,provider=provider,
                    credential_expires_at=utc(authorization['credential_expires_at']))

    def _reasons(self,state,now):
        binding=state['binding'];reasons=[]
        if binding.provider_id not in _VERIFIABLE:reasons.append('oauth_publication_provider_blocked')
        if binding.provider_id not in self.store.policy.allowed_providers:reasons.append('oauth_publication_policy_blocked')
        if (not state['provider'].publication_scopes or
                not set(state['provider'].publication_scopes)<=state['observed'] or
                not state['observed']<=set(state['client'].approved_scopes)):
            reasons.append('oauth_publication_scope_consent_required')
        if state['credential_expires_at']<=now:reasons.append('oauth_credential_expired')
        if binding.provider_id not in self.verifiers:reasons.append('oauth_publication_verifier_unavailable')
        if self.authorization_guard is None:reasons.append('oauth_publication_authorization_unavailable')
        if not self.store._initialized:reasons.append('oauth_publication_storage_uninitialized')
        return reasons

    def _response(self,state,now):
        binding=state['binding'];status=self.store.status(binding,now=now)
        reasons=self._reasons(state,now)
        if status['status']=='granted':
            grant=self.store.current(binding,now=now)
            if (grant is None or set(grant.observed_scopes)!=state['observed'] or
                    not set(grant.observed_scopes)<=set(state['client'].approved_scopes) or
                    grant.expires_at>state['credential_expires_at'] or state['credential_expires_at']<=now):
                status={**status,'status':'blocked'}
                reasons.append('oauth_publication_binding_changed')
        actions=[]
        if not reasons:actions.append('approve')
        # 회수는 공급자 검사·token·쓰기 scope가 없어도 현재 owner/대상에 대해 수행한다.
        if self.store._initialized and status['revision']>0 and status['status'] in ('granted','expired','blocked'):
            actions.append('revoke')
        return dict(publication_grant=status,available_actions=actions,reason_codes=reasons,
                    base_revision=binding.registry_revision,connection_revision=binding.connection_revision)

    @staticmethod
    def _body(body):
        if (type(body) is not dict or set(body)!=_BODY or type(body['request_key']) is not str or
                re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}',body['request_key']) is None or
                type(body['expected_base_revision']) is not str or not body['expected_base_revision'] or
                type(body['expected_connection_revision']) is not int or body['expected_connection_revision']<1 or
                type(body['expected_grant_revision']) is not int or body['expected_grant_revision']<0):_error('invalid')

    def _cas(self,state,body,now):
        binding=state['binding']
        if (body['expected_base_revision']!=binding.registry_revision or
                body['expected_connection_revision']!=binding.connection_revision or
                body['expected_grant_revision']!=self.store.status(binding,now=now)['revision']):raise ConflictError()

    @staticmethod
    def _safe(call):
        try:return call()
        except StoreError as error:
            _error(error.code if error.code in _SAFE else 'oauth_publication_unverified')
        except Exception:_error()

    def read(self,session,connection_id):
        self._session(session)
        def action():
            with oauth_write_guard(self.store.context):
                return self._response(self._state(connection_id),utc(self.clock()))
        return self._safe(action)

    def approve(self,session,connection_id,body):
        self._session(session);self._body(body)
        def action():
            with oauth_write_guard(self.store.context):
                now=utc(self.clock());state=self._state(connection_id);self._cas(state,body,now)
                if self._reasons(state,now):_error()
                binding=state['binding'];client=state['client']
                if self.authorization_guard(session,binding,client) is not True:_error()
                if self._state(connection_id)!=state:raise ConflictError()
                self._cas(state,body,utc(self.clock()))
                with self.resolver.use(state['reference'],account_id=binding.account_id,platform=binding.platform,
                                       target_id=binding.target_id,scope='read') as resolved:
                    if self.authorization_guard(session,binding,client) is not True:_error()
                    if (resolved.account_id!=binding.account_id or resolved.platform!=binding.platform or
                            resolved.connection_id!=binding.connection_id or resolved.target_id!=binding.target_id or
                            resolved.provider_id!=binding.provider_id or resolved.generation!=binding.credential_generation or
                            resolved.reference!=state['reference'] or resolved.scope!='read'):_error('credential_owner_mismatch')
                    resolved.assert_current()
                    evidence=self.verifiers[binding.provider_id].verify(resolved,binding,now=now)
                    expiry=utc(resolved.bundle.expires_at)
                    if (type(evidence) is not VerifiedPublicationEvidence or evidence.binding!=binding or
                            set(evidence.observed_scopes)!=state['observed'] or
                            set(evidence.observed_scopes)!=_scope_set(resolved.bundle.scopes) or
                            evidence.credential_expires_at!=expiry):_error()
                    resolved.assert_current()
                    fresh=self._state(connection_id)
                    if fresh!=state:raise ConflictError()
                    if self.authorization_guard(session,binding,client) is not True:_error()
                    checked=utc(self.clock());self._cas(fresh,body,checked)
                    self.store.issue(evidence,expected_revision=body['expected_grant_revision'],actor=session.actor,
                                     expires_at=min(checked+self.store.policy.max_ttl,expiry),now=checked)
                    return self._response(fresh,checked)
        return self._safe(action)

    def revoke(self,session,connection_id,body):
        self._session(session);self._body(body)
        def action():
            with oauth_write_guard(self.store.context):
                now=utc(self.clock());state=self._state(connection_id);self._cas(state,body,now)
                if not self.store._initialized:_error()
                self.store.revoke(connection_id,expected_revision=body['expected_grant_revision'],actor=session.actor,now=now)
                return self._response(state,now)
        return self._safe(action)
