"""명시 사용자 세션의 OAuth 조합. 생성/GET는 vault와 외부 provider를 호출하지 않는다."""
from dataclasses import dataclass, replace, asdict
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from urllib.parse import urlsplit, parse_qsl
import base64
import hashlib
import hmac
import json
import re
import secrets
from uuid import uuid4
from .content_store import StoreError, ConflictError
from .credential_backend import CredentialError, validate_ref
from .managed_connections import project_registry
from .oauth_catalog import provider_catalog
from .oauth_models import AttemptContext, CredentialRef, OAuthClientRegistration, OAuthPolicy, TokenBundle, validate_authorization
from .oauth_policy import assert_zero_cost
from .oauth_store import _time


@dataclass(frozen=True, repr=False)
class SessionContext:
    actor: str
    session_binding: str

    def __post_init__(self):
        if self.actor != 'console_user' or not isinstance(self.session_binding, str) or not self.session_binding:
            raise StoreError('oauth_session_required')


@dataclass(frozen=True)
class CallbackContext:
    """HTTP가 고정 Host/TLS callback 정책을 통과한 뒤 만드는 서버 전용 값."""
    provider_id: str
    redirect_uri: str


def _safe_text(value, maximum=256):
    if not isinstance(value, str) or not value or len(value) > maximum or any(ord(c)<32 for c in value):
        raise StoreError('oauth_response_invalid')
    return value


def _token_bytes(bundle):
    if not isinstance(bundle, TokenBundle):
        raise StoreError('oauth_response_invalid')
    return json.dumps(dict(access_token=bundle.access_token,refresh_token=bundle.refresh_token,
        token_type=bundle.token_type,expires_at=bundle.expires_at,scopes=bundle.scopes),allow_nan=False).encode()


def _token_from_bytes(value):
    try:
        data=json.loads(value)
        if set(data)!={'access_token','refresh_token','token_type','expires_at','scopes'}:
            raise ValueError()
        return TokenBundle(**data)
    except Exception:
        raise StoreError('oauth_credential_invalid') from None


class OAuthConnectionService:
    def __init__(self,registry_supplier,client_registrations,attempt_store,connection_store,backend,
                 providers,policy=None,clock=None,*,cost_guard=None):
        self.registry_supplier=registry_supplier
        self.client_registrations=MappingProxyType(dict(client_registrations or {}))
        self.attempt_store=attempt_store; self.connection_store=connection_store
        self.backend=backend; self.providers=MappingProxyType(dict(providers or {}))
        self.policy=policy if policy is not None else OAuthPolicy()
        self.clock=clock or (lambda:datetime.now(timezone.utc))
        self.cost_guard=cost_guard if cost_guard is not None else assert_zero_cost
        definitions={p.id:p for p in provider_catalog()}
        for key,provider in self.providers.items():
            definition=provider.definition
            if key not in definitions or definition.id!=key or definition.platform!=definitions[key].platform:
                raise StoreError('oauth_contract_blocked')
            definitions[key]=definition
        self.definitions=MappingProxyType(definitions)

    def _session(self,session):
        if not isinstance(session,SessionContext): raise StoreError('oauth_session_required')
        SessionContext(session.actor,session.session_binding)
        return session

    def _registration(self,provider_id):
        client=self.client_registrations.get(provider_id)
        definition=self.definitions.get(provider_id)
        if (not isinstance(client,OAuthClientRegistration) or definition is None or
                client.provider_id!=provider_id or provider_id not in self.providers or self.backend is None or
                definition.pkce_mode=='unconfirmed' or definition.policy_reasons):
            raise StoreError('oauth_registration_blocked')
        if urlsplit(client.redirect_uri).path!='/oauth/callback/'+provider_id:
            raise StoreError('oauth_registration_blocked')
        return client,definition

    def _gate(self,context,operation):
        if not self.policy.live_enabled: raise StoreError('oauth_live_disabled')
        client,definition=self._registration(context.provider_id)
        if (context.client_revision!=client.client_revision or context.redirect_uri!=client.redirect_uri or
                context.client_ref!=client.client_id or context.evidence_revision!=client.cost_evidence_revision or
                not set(context.requested_scopes)<=set(client.approved_scopes)):
            raise StoreError('oauth_registration_changed')
        rule=next((r for r in definition.operations if r.operation==operation),None)
        if rule is None or rule.contract_status!='verified' or not rule.endpoint:
            raise StoreError('oauth_contract_blocked')
        if rule.evidence_revision!=context.evidence_revision: raise StoreError('oauth_evidence_stale')
        if rule.cost_kind!='no_additional_cost': raise StoreError('oauth_cost_blocked')
        if client.client_secret_ref is not None:
            self._checked_ref(context,client.client_secret_ref,'client')
        self.cost_guard(operation,rule.endpoint,context.evidence_revision)
        return self.providers[context.provider_id],dict(context=context,client_config=client)

    def _snapshot(self):
        base=self.registry_supplier(); snapshot=self.connection_store.snapshot()
        projected=project_registry(base,snapshot)
        return base,snapshot,projected

    def _current(self,context):
        base,snapshot,projected=self._snapshot()
        if base.revision!=context.base_revision: raise ConflictError()
        connection=projected.connections.get(context.connection_id)
        if connection is not None and (connection.account_id!=context.account_id or
                connection.platform!=self.definitions[context.provider_id].platform):
            raise StoreError('credential_owner_mismatch')
        managed=snapshot.connections.get(context.connection_id)
        if managed and managed.get('provider_id')!=context.provider_id:
            raise StoreError('credential_owner_mismatch')
        revision=snapshot.connections.get(context.connection_id,{}).get('revision',0)
        if revision!=context.connection_revision: raise ConflictError()
        return base,snapshot,projected

    def _owned(self,session,attempt_id):
        self._session(session)
        item=self.attempt_store.read_owned(attempt_id,session.session_binding)
        if item['context'].actor!=session.actor: raise StoreError('oauth_session_required')
        return item

    def _ref(self,context,generation,kind):
        return CredentialRef('autosns.oauth',context.account_id,self.definitions[context.provider_id].platform,
                             context.connection_id,generation,kind)

    def _checked_ref(self,context,ref,kind,generation=None):
        validate_ref(ref)
        if (ref.account_id!=context.account_id or ref.platform!=self.definitions[context.provider_id].platform or
                ref.connection_id!=context.connection_id or ref.kind!=kind or
                (generation is not None and ref.generation!=generation)):
            raise StoreError('credential_owner_mismatch')
        return ref

    def _delete(self,refs):
        # 지정한 이 서비스의 ref만 정리한다. 실패한 정리는 숨은 GET/retry로 수행하지 않는다.
        for ref in refs:
            try: self.backend.delete(ref)
            except CredentialError: pass

    def _discard_unreferenced(self,context,refs,attempt_id=None):
        """불명확한 커밋은 보존한다. 참조되지 않음을 읽기로 입증한 stage만 정리한다."""
        try:
            referenced=[row.get('credential_ref') for row in self.connection_store.snapshot().connections.values()]
            if attempt_id is not None:
                item=self.attempt_store.read_owned(attempt_id,context.session_binding)
                referenced.extend(item.get(key) for key in ('code_ref','ticket_ref','verifier_ref','state_key_ref','token_ref'))
            safe=[]
            for ref in refs:
                self._checked_ref(context,ref,ref.kind)
                if ref not in referenced: safe.append(ref)
        except Exception:
            return
        self._delete(safe)

    def _client_secret(self,context):
        client=self.client_registrations[context.provider_id]
        if client.client_secret_ref is None: return None
        ref=self._checked_ref(context,client.client_secret_ref,'client')
        return self.backend.get(ref).decode('utf-8')

    def _authorization(self,bundle=None,*,read_status='not_checked',credential_status='pending',observed_scopes=None):
        if bundle is not None and bundle.expires_at is not None:
            if _time(bundle.expires_at)<=_time(self.clock()): raise StoreError('oauth_credential_expired')
        scopes=observed_scopes if observed_scopes is not None else (list(bundle.scopes) if bundle and bundle.scopes else None)
        return validate_authorization(dict(observed_scopes=scopes,
            credential_expires_at=bundle.expires_at if bundle else None,read_status=read_status,
            publication_status='blocked',credential_status=credential_status))

    def _public_authorization(self,value):
        return validate_authorization(dict(value)) if value is not None else self._authorization()

    def _public_proposal(self,proposal,context):
        return dict(proposal_id=proposal['proposal_id'],target_id=proposal['target_id'],
                    target_label=proposal.get('target_label',''),expected_base_revision=context.base_revision,
                    expected_connection_revision=context.connection_revision)

    def _public_attempt(self,item):
        context=item['context']; state=item['state']
        if state in ('consent_pending','callback_staged') and _time(item['expires_at'])<=_time(self.clock()): state='expired'
        if state=='callback_staged' and _time(item['ticket_expires_at'])<=_time(self.clock()): state='expired'
        if item.get('reason')=='denied': state='denied'
        result=dict(attempt_id=item['attempt_id'],account_id=context.account_id,provider_id=context.provider_id,
            connection_id=context.connection_id,state=state,revision=item['revision'],expires_at=item['expires_at'],
            base_revision=context.base_revision,connection_revision=context.connection_revision,execution_enabled=False)
        result['authorization']=self._public_authorization(item.get('authorization'))
        if item.get('reason'): result['reason_codes']=[item['reason']]
        proposal=self.connection_store.proposal_for_attempt(item['attempt_id'],context.session_binding)
        if proposal is not None:
            result['provider_subject']=proposal['provider_subject']
            result['target_proposal']=self._public_proposal(proposal,context)
            result['authorization']=self._public_authorization(proposal.get('authorization'))
        return result

    def catalog(self,session,account='all'):
        self._session(session)
        if account not in ('all','personal','dept'): raise StoreError('invalid')
        items=[]
        for definition in self.definitions.values():
            row=definition.to_dict(); blockers=[]
            try: self._registration(definition.id)
            except StoreError: blockers.append('registration_blocked')
            cost=all(r.cost_kind=='no_additional_cost' for r in definition.operations if r.endpoint)
            if not cost or not any(r.endpoint for r in definition.operations): blockers.append('cost_evidence_unverified')
            row.update(registration_status='registration_blocked' if 'registration_blocked' in blockers else 'ready',
                cost_gate='no_additional_cost' if cost else 'unknown',policy_gate='allowed' if not definition.policy_reasons else 'blocked',
                blockers=blockers,ready=not blockers and not definition.policy_reasons and self.policy.live_enabled)
            items.append(row)
        return dict(items=items,live_enabled=self.policy.live_enabled)

    def connections(self,session,account='all'):
        self._session(session)
        if account not in ('all','personal','dept'): raise StoreError('invalid')
        base,snapshot,projected=self._snapshot(); items=[]
        completed=self.attempt_store.list_completed_for_actor(session.actor)
        for key,connection in projected.connections.items():
            if account!='all' and connection.account_id!=account: continue
            row=connection.to_dict(public=True); managed=snapshot.connections.get(key)
            row.update(connection_revision=managed['revision'] if managed else 0,execution_enabled=False,available_actions=[])
            if managed:
                row.update(state=managed['state'],scopes=list(managed['scopes']),read_status='verified' if managed['state']=='connected' else 'unverified')
                row['authorization']=self._public_authorization(managed.get('authorization'))
                if managed.get('provider_id'):
                    row['provider_id']=managed['provider_id']
                    try: context=self._completed_context(session,managed,completed)
                    except StoreError: context=None
                    if context is not None:
                        row['available_actions']=['disconnect']
                        if managed['state']=='connected' and not managed.get('operation_lease'):
                            row['available_actions']+=self._available_remote_actions(context)
            items.append(row)
        return dict(items=items,base_revision=base.revision)

    def _available_remote_actions(self,context):
        if not self.policy.live_enabled: return []
        provider_id=context.provider_id
        try: client,definition=self._registration(provider_id)
        except StoreError: return []
        if (context.client_revision!=client.client_revision or context.redirect_uri!=client.redirect_uri or
                context.client_ref!=client.client_id or context.evidence_revision!=client.cost_evidence_revision or
                not set(context.requested_scopes)<=set(client.approved_scopes)):
            return []
        return [rule.operation for rule in definition.operations if rule.operation in ('refresh','revoke') and
                rule.contract_status=='verified' and rule.endpoint and rule.cost_kind=='no_additional_cost' and
                rule.evidence_revision==client.cost_evidence_revision and
                not (rule.operation=='revoke' and provider_id in ('youtube','blogger'))]

    def read_attempt(self,session,attempt_id):
        return self._public_attempt(self._owned(session,attempt_id))

    def result_for_session(self,session):
        self._session(session)
        return dict(items=[self._public_attempt(item) for item in self.attempt_store.list_owned(session.session_binding)
                           if item['context'].actor==session.actor])

    def _request(self,session,operation,body,fields,action):
        self._session(session)
        if not isinstance(body,dict) or set(body)!=set(fields)|{'request_key'}: raise StoreError('invalid')
        key=body['request_key']
        if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}',key): raise StoreError('invalid')
        digest=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        receipt=self.attempt_store.claim_request(session.session_binding,operation,key,digest)
        if receipt['status']=='completed':
            if operation=='start': return self._retry_start(session,receipt)
            return receipt['result']
        if receipt['status']!='claimed': raise StoreError('oauth_request_in_progress')
        try:
            result=action(receipt)
            safe={key:value for key,value in result.items() if key!='authorize_url'}
            self.attempt_store.finish_request(receipt['id'],receipt['revision'],safe)
            return result
        except StoreError:
            raise
        except CredentialError:
            raise StoreError('oauth_credential_unavailable') from None
        except Exception:
            raise StoreError('oauth_operation_failed') from None

    def _state(self,context,receipt_id,key):
        message=json.dumps(dict(receipt_id=receipt_id,context=asdict(context)),sort_keys=True,separators=(',',':')).encode()
        return base64.urlsafe_b64encode(hmac.new(key,message,hashlib.sha256).digest()).rstrip(b'=').decode()

    def _authorize_url(self,provider,wrapper,client):
        url=provider.authorize(wrapper,client); _safe_text(url,8192)
        definition=self.definitions[wrapper['context'].provider_id]
        rule=next(r for r in definition.operations if r.operation=='authorize')
        parsed=urlsplit(url); expected=urlsplit(rule.endpoint)
        if (parsed.scheme,parsed.netloc,parsed.path)!=(expected.scheme,expected.netloc,expected.path) or parsed.fragment or parsed.username:
            raise StoreError('oauth_response_invalid')
        allowed={'client_id','redirect_uri','response_type','scope','state','code_challenge','code_challenge_method',
                 'access_type','prompt','include_granted_scopes','enable_fb_login','force_authentication'}
        pairs=parse_qsl(parsed.query,keep_blank_values=True)
        if len({key for key,_ in pairs})!=len(pairs) or any(key not in allowed for key,_ in pairs):
            raise StoreError('oauth_response_invalid')
        params=dict(pairs)
        if params.get('state')!=wrapper['state']: raise StoreError('oauth_response_invalid')
        return url

    def _retry_start(self,session,receipt):
        result=dict(receipt['result']); item=self._owned(session,result['attempt_id']); context=item['context']
        if item['state']!='consent_pending': raise ConflictError()
        if _time(item['expires_at'])<=_time(self.clock()): raise StoreError('expired')
        self._current(context); provider,wrapper=self._gate(context,'authorize')
        key_ref=self._checked_ref(context,item.get('state_key_ref'),'state_key')
        wrapper['state']=self._state(context,item['request_receipt_id'],self.backend.get(key_ref))
        if self.definitions[context.provider_id].pkce_mode=='s256':
            verifier=self.backend.get(self._checked_ref(context,item.get('verifier_ref'),'verifier',key_ref.generation))
            wrapper['code_challenge']=base64.urlsafe_b64encode(hashlib.sha256(verifier).digest()).rstrip(b'=').decode()
        result['authorize_url']=self._authorize_url(provider,wrapper,self.client_registrations[context.provider_id])
        return result

    def start(self,session,body):
        def action(receipt):
            account=body['account_id']; provider_id=body['provider_id']; connection_id=body['connection_id']
            if account not in ('personal','dept'): raise StoreError('invalid')
            if connection_id is None:
                if type(body['expected_connection_revision']) is not int or body['expected_connection_revision']!=0:
                    raise StoreError('invalid')
                connection_id='oauth.'+uuid4().hex
            _safe_text(connection_id,160)
            if not re.fullmatch(r'[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*',connection_id): raise StoreError('invalid')
            client,definition=self._registration(provider_id)
            scopes=body['requested_scopes']
            if not isinstance(scopes,list) or not all(isinstance(s,str) for s in scopes) or len(set(scopes))!=len(scopes): raise StoreError('invalid')
            if not set(scopes)<=set(client.approved_scopes) or not set(scopes)<=set(definition.read_scopes):
                raise StoreError('oauth_scope_blocked')
            if type(body['expected_connection_revision']) is not int or body['expected_connection_revision']<0: raise StoreError('invalid')
            context=AttemptContext(session.actor,session.session_binding,account,provider_id,connection_id,
                body['expected_base_revision'],body['expected_connection_revision'],tuple(scopes),client.redirect_uri,
                client.client_id,client.client_revision,client.cost_evidence_revision)
            base,_,projected=self._current(context)
            if body['connection_id'] is not None and connection_id not in projected.connections:
                raise StoreError('not_found')
            if account not in base.accounts: raise StoreError('unknown_account')
            provider,wrapper=self._gate(context,'authorize')
            generation=self.attempt_store.reserve_generation('autosns.oauth',account,definition.platform,connection_id)
            state_ref=self._ref(context,generation,'state_key'); staged=[]; item=None; state=None
            try:
                self.backend.put(state_ref,secrets.token_bytes(32)); staged.append(state_ref)
                state=self._state(context,receipt['id'],self.backend.get(state_ref))
                item=self.attempt_store.create_attempt(context,hashlib.sha256(state.encode()).hexdigest(),
                    (_time(self.clock())+timedelta(minutes=10)).isoformat())
                item=self.attempt_store.bind_state_key(item['attempt_id'],session.session_binding,item['revision'],state_ref,receipt['id'])
                wrapper['state']=state
                if definition.pkce_mode=='s256':
                    verifier=secrets.token_urlsafe(48); ref=self._ref(context,generation,'verifier')
                    self.backend.put(ref,verifier.encode()); staged.append(ref)
                    item=self.attempt_store.bind_verifier(item['attempt_id'],session.session_binding,item['revision'],ref)
                    wrapper['code_challenge']=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
                url=self._authorize_url(provider,wrapper,client)
                result=self._public_attempt(item); result['authorize_url']=url
                return result
            except Exception:
                # state 수신권도 소비해 stage 실패 뒤 진행을 재사용하지 못하게 한다.
                try:
                    if state is None: raise StoreError('oauth_start_failed')
                    claim=self.attempt_store.claim_callback(hashlib.sha256(state.encode()).hexdigest(),provider_id)
                    self.attempt_store.fail_callback(claim,'stage_failed')
                except StoreError: pass
                self._discard_unreferenced(context,staged,item['attempt_id'] if item else None)
                raise StoreError('oauth_start_failed') from None
        return self._request(session,'start',body,('account_id','provider_id','connection_id','expected_base_revision','expected_connection_revision','requested_scopes'),action)

    def receive_callback(self,provider_id,parameters,callback_context):
        if (not isinstance(callback_context,CallbackContext) or callback_context.provider_id!=provider_id or
                not isinstance(parameters,dict) or set(parameters) not in ({'state','code'},{'state','error'})):
            raise StoreError('oauth_callback_invalid')
        client=self.client_registrations.get(provider_id)
        if client is None or callback_context.redirect_uri!=client.redirect_uri: raise StoreError('oauth_callback_invalid')
        state=_safe_text(parameters['state'],2048)
        _safe_text(parameters.get('code',parameters.get('error')),8192)
        claim=self.attempt_store.claim_callback(hashlib.sha256(state.encode()).hexdigest(),provider_id)
        staged=[]; item=None
        try:
            context=claim.context
            if context.redirect_uri!=callback_context.redirect_uri: raise StoreError('oauth_callback_invalid')
            item=self.attempt_store.read_owned(claim.attempt_id,context.session_binding)
            if 'error' in parameters:
                self.attempt_store.fail_callback(claim,'denied')
                self._discard_unreferenced(context,[item[key] for key in ('state_key_ref','verifier_ref') if item.get(key)],claim.attempt_id)
                return dict(redirect_path='/connections/oauth-result')
            verifier_ref=item.get('verifier_ref') or item.get('state_key_ref')
            if verifier_ref:
                self._checked_ref(context,verifier_ref,verifier_ref.kind); generation=verifier_ref.generation
            else:
                generation=self.attempt_store.reserve_generation('autosns.oauth',context.account_id,self.definitions[provider_id].platform,context.connection_id)
            code_ref=self._ref(context,generation,'code'); ticket_ref=self._ref(context,generation,'ticket')
            self.backend.put(code_ref,parameters['code'].encode()); staged.append(code_ref)
            self.backend.put(ticket_ref,secrets.token_bytes(32)); staged.append(ticket_ref)
            expiry=min(_time(claim.expires_at),_time(self.clock())+timedelta(minutes=2))
            self.attempt_store.finalize_callback(claim,code_ref,ticket_ref,expiry.isoformat())
            return dict(redirect_path='/connections/oauth-result')
        except Exception:
            self._discard_unreferenced(claim.context,staged,claim.attempt_id)
            try: self.attempt_store.fail_callback(claim,'stage_failed')
            except StoreError: pass
            if item is not None:
                self._discard_unreferenced(claim.context,[item[key] for key in ('state_key_ref','verifier_ref') if item.get(key)],claim.attempt_id)
            raise StoreError('oauth_callback_failed') from None

    def _mark_attempt(self,item,state,reason):
        try: self.attempt_store.update_attempt(item['attempt_id'],item['context'].session_binding,item['revision'],state,{'reason':reason})
        except StoreError: pass

    def resume_exchange(self,session,attempt_id,body):
        def action(receipt):
            item=self._owned(session,attempt_id); context=item['context']
            self._current(context); provider,wrapper=self._gate(context,'exchange')
            # Naver token 교환은 state 원문을 요구한다. hash-only 계약에서는 추정/복구하지 않는다.
            if context.provider_id=='naver': raise StoreError('oauth_contract_blocked')
            generation=item['code_ref'].generation if item.get('code_ref') else None
            code_ref=self._checked_ref(context,item.get('code_ref'),'code',generation)
            ticket_ref=self._checked_ref(context,item.get('ticket_ref'),'ticket',generation)
            try:
                code=self.backend.get(code_ref).decode(); ticket=self.backend.get(ticket_ref)
                if len(ticket)!=32: raise StoreError('oauth_credential_invalid')
                verifier=None
                if self.definitions[context.provider_id].pkce_mode=='s256':
                    verifier=self.backend.get(self._checked_ref(context,item.get('verifier_ref'),'verifier',generation)).decode()
                secret=self._client_secret(context)
            except CredentialError:
                raise StoreError('oauth_credential_unavailable') from None
            claimed=self.attempt_store.claim_resume(attempt_id,session.session_binding,body['expected_revision'])
            token_ref=self._ref(context,generation,'token'); stored=False
            try:
                bundle=provider.exchange(wrapper,code,secret,verifier=verifier)
                if not isinstance(bundle,TokenBundle) or not set(bundle.scopes)<=set(context.requested_scopes): raise StoreError('oauth_scope_blocked')
                authorization=self._authorization(bundle,credential_status='stored')
                self._current(context)
                self.backend.put(token_ref,_token_bytes(bundle)); stored=True
                result=self.attempt_store.update_attempt(attempt_id,session.session_binding,claimed['revision'],'token_exchanged',{'token_ref':token_ref,'authorization':authorization})
                return self._public_attempt(result)
            except Exception:
                if stored: self._discard_unreferenced(context,[token_ref],attempt_id)
                self._mark_attempt(claimed,'unknown','exchange_failed')
                raise StoreError('oauth_exchange_unknown') from None
            finally:
                self._delete([code_ref,ticket_ref]+[item[k] for k in ('verifier_ref','state_key_ref') if item.get(k)])
        return self._request(session,'continue:'+attempt_id,body,('expected_revision',),action)

    def inspect(self,session,attempt_id,body):
        def action(receipt):
            item=self._owned(session,attempt_id); context=item['context']
            self._current(context); provider,wrapper=self._gate(context,'inspect')
            if _time(item['expires_at'])<=_time(self.clock()): raise StoreError('expired')
            ref=self._checked_ref(context,item.get('token_ref'),'token')
            bundle=_token_from_bytes(self.backend.get(ref))
            self._authorization(bundle,credential_status='stored')
            pending=self.attempt_store.update_attempt(attempt_id,session.session_binding,body['expected_revision'],'principal_pending',{})
            try:
                result=provider.inspect(wrapper,bundle)
                if not isinstance(result,dict) or set(result)!={'provider_subject','targets','observed_scopes','checked_at'}: raise StoreError('oauth_response_invalid')
                subject=_safe_text(result['provider_subject']); checked=_time(result['checked_at']).isoformat()
                observed=result['observed_scopes']
                if not isinstance(observed,(list,tuple)) or not set(observed)<=set(bundle.scopes): raise StoreError('oauth_scope_blocked')
                targets=result['targets']
                if not isinstance(targets,list) or len(targets)!=1: raise StoreError('oauth_target_unconfirmed')
                target=targets[0]
                if not isinstance(target,dict) or set(target)-{'target_id','target_label','capabilities'}: raise StoreError('oauth_response_invalid')
                target_id=_safe_text(target.get('target_id')); label=_safe_text(target.get('target_label',target_id))
                public_text=json.dumps([subject,target_id,label,observed,checked])
                if any(secret and secret in public_text for secret in (bundle.access_token,bundle.refresh_token)):
                    raise StoreError('oauth_response_invalid')
                _,snapshot,projected=self._current(context)
                connection=projected.connections.get(context.connection_id)
                if connection and connection.target_id is not None and connection.target_id!=target_id: raise ConflictError()
                proposal=dict(connection_id=context.connection_id,account_id=context.account_id,
                    platform=self.definitions[context.provider_id].platform,base_revision=context.base_revision,
                    target_id=target_id,target_label=label,provider_subject=subject,credential_ref=ref,
                    scopes=tuple(observed),checked_at=checked,
                    authorization=self._authorization(bundle,read_status='verified',credential_status='stored',observed_scopes=list(observed)))
                self.connection_store.create_target_proposal(attempt_id,session.session_binding,pending['revision'],proposal)
                return self.read_attempt(session,attempt_id)
            except Exception:
                self._mark_attempt(pending,'error','inspect_failed')
                raise StoreError('oauth_inspect_failed') from None
        return self._request(session,'inspect:'+attempt_id,body,('expected_revision',),action)

    def confirm_target(self,session,proposal_id,body):
        def action(receipt):
            proposal=self.connection_store.read_target_proposal(proposal_id,session.session_binding)
            item=self._owned(session,proposal['attempt_id']); context=item['context']
            self._gate(context,'inspect')
            base,snapshot,projected=self._current(context)
            if body['expected_base_revision']!=base.revision or body['expected_connection_revision']!=context.connection_revision: raise ConflictError()
            ref=self._checked_ref(context,proposal['credential_ref'],'token')
            self._authorization(_token_from_bytes(self.backend.get(ref)),credential_status='stored')
            connection=projected.connections.get(context.connection_id)
            if connection and connection.target_id is not None and connection.target_id!=proposal['target_id']: raise ConflictError()
            # 현재 base와 동일 snapshot projection 검증을 pointer commit보다 먼저 수행한다.
            old=snapshot.connections.get(context.connection_id)
            self.connection_store.confirm_target(proposal,base.revision,context.connection_revision)
            if old and old.get('credential_ref') and old['credential_ref']!=ref: self._delete([old['credential_ref']])
            return self.read_attempt(session,item['attempt_id'])
        return self._request(session,'confirm:'+proposal_id,body,('expected_base_revision','expected_connection_revision'),action)

    def _connection_context(self,session,connection_id,body):
        self._session(session)
        base,snapshot,projected=self._snapshot(); row=snapshot.connections.get(connection_id)
        if row is None: raise StoreError('not_found')
        if body['expected_base_revision']!=base.revision or body['expected_connection_revision']!=row['revision']: raise ConflictError()
        context=self._completed_context(session,row)
        return replace(context,connection_revision=row['revision']),row

    def _completed_context(self,session,row,completed=None):
        """완료 연결만 actor에 귀속한다. 미완 시도의 세션 결속에는 사용하지 않는다."""
        if not row.get('provider_id'): raise StoreError('oauth_provider_unconfirmed')
        records=completed if completed is not None else self.attempt_store.list_completed_for_actor(session.actor)
        candidates=[]
        for item in records:
            context=item['context']; ref=item.get('token_ref')
            if (item['state']!='connected' or context.actor!=session.actor or
                    context.connection_id!=row['connection_id'] or context.account_id!=row['account_id'] or
                    context.provider_id!=row['provider_id'] or context.base_revision!=row['base_revision'] or
                    self.definitions[context.provider_id].platform!=row['platform']):
                continue
            self._checked_ref(context,ref,'token')
            # refresh는 active 세대만 교체한다. 이전 완료 시도는 그 현재 포인터를 해석하는 근거다.
            if ref.generation<=row['credential_generation']: candidates.append(item)
        if not candidates: raise StoreError('not_found')
        return max(candidates,key=lambda item:item['token_ref'].generation)['context']

    def _public_connection(self,connection_id):
        row=self.connection_store.snapshot().connections[connection_id]
        return dict(connection_id=connection_id,account_id=row['account_id'],platform=row['platform'],state=row['state'],
                    connection_revision=row['revision'],base_revision=row['base_revision'],execution_enabled=False,
                    authorization=self._public_authorization(row.get('authorization')))

    def disconnect_local(self,session,connection_id,body):
        def action(receipt):
            context,row=self._connection_context(session,connection_id,body)
            self.connection_store.disconnect_local(connection_id,body['expected_base_revision'],body['expected_connection_revision'])
            # 로컬 overlay만 해제한다. 원격 해지나 vault 삭제 성공으로 표시하지 않는다.
            return self._public_connection(connection_id)
        return self._request(session,'disconnect:'+connection_id,body,('expected_base_revision','expected_connection_revision'),action)

    def _lifecycle(self,session,connection_id,body,operation):
        def action(receipt):
            context,row=self._connection_context(session,connection_id,body)
            provider,wrapper=self._gate(context,operation)
            if operation=='revoke' and context.provider_id in ('youtube','blogger'):
                raise StoreError('oauth_revoke_impact_unverified')
            ref=self._checked_ref(context,row['credential_ref'],'token',row['credential_generation'])
            bundle=_token_from_bytes(self.backend.get(ref)); secret=self._client_secret(context)
            lease=self.connection_store.claim_connection_operation(connection_id,body['expected_base_revision'],body['expected_connection_revision'],operation)
            staged=None
            try:
                if operation=='refresh':
                    result=provider.refresh(wrapper,bundle,secret)
                    if not isinstance(result,TokenBundle) or set(result.scopes)!=set(bundle.scopes): raise StoreError('oauth_scope_blocked')
                    current_base,_,_=self._snapshot()
                    if current_base.revision!=context.base_revision: raise ConflictError()
                    # 단일 lease 상태를 유지한 채 새 generation을 stage하고 CAS로 pointer만 전환한다.
                    generation=self.connection_store.reserve_generation('autosns.oauth',context.account_id,row['platform'],connection_id)
                    staged=self._ref(context,generation,'token'); self.backend.put(staged,_token_bytes(result))
                    authorization=self._authorization(result,read_status=row.get('authorization',{}).get('read_status','unknown'),credential_status='active')
                    self.connection_store.finish_connection_operation(lease,new_ref=staged,authorization=authorization)
                else:
                    result=provider.revoke(wrapper,bundle,secret)
                    if not isinstance(result,dict) or result.get('remote_revoked') is not True: raise StoreError('oauth_revoke_unconfirmed')
                    current_base,_,_=self._snapshot()
                    if current_base.revision!=context.base_revision: raise ConflictError()
                    self.connection_store.finish_connection_operation(lease,state='revoked')
                self._delete([ref])
                return self._public_connection(connection_id)
            except Exception:
                if staged is not None: self._discard_unreferenced(context,[staged])
                try: self.connection_store.fail_connection_operation(lease,state='unknown')
                except StoreError: pass
                raise StoreError('oauth_'+operation+'_unknown') from None
        return self._request(session,operation+':'+connection_id,body,('expected_base_revision','expected_connection_revision'),action)

    def refresh(self,session,connection_id,body):
        return self._lifecycle(session,connection_id,body,'refresh')

    def revoke(self,session,connection_id,body):
        return self._lifecycle(session,connection_id,body,'revoke')
