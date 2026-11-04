"""사용자 cookie/CSRF와 고정 callback 신뢰 경계를 갖는 OAuth HTTP 어댑터."""
from dataclasses import dataclass
import ipaddress
import re
import ssl
from types import MappingProxyType
from urllib.parse import urlsplit

from common.operations.content_store import StoreError
from common.operations.oauth_catalog import provider_catalog
from common.operations.oauth_service import CallbackContext
from oauth_session import require_oauth_session,mint_csrf,verify_csrf,OAuthSessionError

BASE='/api/v2/oauth'
SHELL='/connections/oauth-result'
CALLBACK='/oauth/callback/'
ID=r'[A-Za-z0-9_.-]{1,160}'


@dataclass(frozen=True)
class OAuthCallbackPolicy:
    """등록 URI·직접 TLS 또는 명시 trusted proxy IP를 서버 설정으로 고정한다.

    test_only는 HTTP fixture만 허용하며 별도 factory flag와 함께 사용한다.
    전달 헤더는 지정 peer에서만 신뢰한다. Host에서 redirect를 조립하지 않는다.
    """
    redirect_uris: object
    trusted_proxy_ips: tuple=()
    test_only: bool=False

    def __post_init__(self):
        if type(self.test_only) is not bool or type(self.trusted_proxy_ips) is not tuple:raise ValueError('고정 callback 정책이 필요합니다')
        known={p.id for p in provider_catalog()};uris=dict(self.redirect_uris)
        for provider,uri in uris.items():
            try:
                parsed=urlsplit(uri)
                valid=(provider in known and parsed.scheme=='https' and parsed.hostname and
                    parsed.netloc==parsed.netloc.lower() and not parsed.username and not parsed.password and
                    parsed.path==CALLBACK+provider and not parsed.query and not parsed.fragment and
                    not re.search(r'[\\\s\x00-\x1f\x7f]',uri))
                parsed.port
            except (ValueError,TypeError):valid=False
            if not valid:raise ValueError('등록된 HTTPS callback URI가 필요합니다')
        for peer in self.trusted_proxy_ips:
            try:ipaddress.ip_address(peer)
            except ValueError:raise ValueError('고정 proxy IP가 필요합니다') from None
        object.__setattr__(self,'redirect_uris',MappingProxyType(uris))

    def accepts(self,handler,path):
        provider=path.removeprefix(CALLBACK)
        uri=self.redirect_uris.get(provider)
        if not uri or handler.headers.get('Host')!=urlsplit(uri).netloc:return False
        if handler.headers.get('Forwarded') or handler.headers.get('X-Forwarded-Host'):return False
        if self.test_only:return getattr(handler.server,'oauth_test_only',False) is True
        if isinstance(handler.connection,ssl.SSLSocket):return True
        return (handler.client_address[0] in self.trusted_proxy_ips and
                handler.headers.get('X-Forwarded-Proto')=='https')


def recognizes(path):
    return path==BASE or path.startswith(BASE+'/') or path==SHELL or path.startswith(CALLBACK)


def query_fields(path):
    if path in (BASE+'/catalog',BASE+'/connections'):return {'account'}
    if path.startswith(CALLBACK):return {'state','code','error'}
    return set()


def disabled_catalog():
    items=[]
    for definition in provider_catalog():
        row=definition.to_dict()
        row.update(registration_status='registration_blocked',cost_gate='unknown',policy_gate='blocked',
            blockers=['registration_blocked','oauth_live_disabled','https_callback_unaccepted'],ready=False)
        items.append(row)
    return dict(items=items,live_enabled=False)


def _fields(body,names):
    if type(body) is not dict or set(body)!=set(names)|{'request_key'}:raise StoreError('invalid')
    if not isinstance(body['request_key'],str) or not re.fullmatch(ID,body['request_key']):raise StoreError('invalid')
    for key in ('expected_revision','expected_connection_revision'):
        if key in body and (type(body[key]) is not int or body[key]<(1 if key=='expected_revision' else 0)):raise StoreError('invalid')
    if 'expected_base_revision' in body and (not isinstance(body['expected_base_revision'],str) or not body['expected_base_revision'] or len(body['expected_base_revision'])>256):raise StoreError('invalid')
    if 'account_id' in body and body['account_id'] not in ('personal','dept'):raise StoreError('invalid')
    if 'provider_id' in body and body['provider_id'] not in {p.id for p in provider_catalog()}:raise StoreError('invalid')
    if 'connection_id' in body and body['connection_id'] is not None and (not isinstance(body['connection_id'],str) or not re.fullmatch(ID,body['connection_id'])):raise StoreError('invalid')
    if 'requested_scopes' in body:
        scopes=body['requested_scopes']
        if (type(scopes) is not list or len(scopes)>50 or any(not isinstance(s,str) or not s or len(s)>512 for s in scopes) or len(set(scopes))!=len(scopes)):raise StoreError('invalid')
    return body


def _public(value):
    """서비스 public projection 외 private 필드가 생기면 응답을 중단한다."""
    forbidden={'access_token','refresh_token','token','client_secret','credential_ref','credential_refs',
        'client_secret_ref','code','code_ref','client_ref','verifier','verifier_ref','code_verifier',
        'ticket','ticket_ref','token_ref','session_binding','state_hash','state_key_ref'}
    allowed={'items','live_enabled','provider_id','platform','login_method','read_scopes','publication_scopes',
        'pkce_mode','redirect_policy','policy_reasons','ready','execution_enabled','registration_status',
        'cost_gate','policy_gate','blockers','attempt_id','account_id','connection_id','state','revision',
        'expires_at','base_revision','connection_revision','reason_codes','provider_subject','target_proposal',
        'proposal_id','target_id','target_label','expected_base_revision','expected_connection_revision',
        'authorize_url','id','target_status','capabilities','planning_enabled','auth_status','scopes',
        'read_status','available_actions','csrf_token','authorization','observed_scopes',
        'credential_expires_at','publication_status','credential_status','scope_consent','available','policy_revision','requested_scopes'}
    states={'registration_blocked','consent_pending','callback_staged','resume_pending','token_exchanged',
        'principal_pending','target_confirmation','connected','denied','expired','error','revoked','unknown',
        'disconnected','reauth_required'}
    def check(obj):
        if isinstance(obj,dict):
            if set(obj)-allowed or any(str(k).lower() in forbidden for k in obj):raise StoreError('oauth_response_invalid')
            if 'state' in obj and obj['state'] not in states:raise StoreError('oauth_response_invalid')
            for child in obj.values():check(child)
        elif isinstance(obj,(list,tuple)):
            for child in obj:check(child)
    check(value);return value



def _grant_public(value,connection_id):
    keys={'connection_id','account_id','platform','provider_id','target_id','revision','status','approved_at','expires_at','policy_revision'}
    if type(value) is not dict or set(value)!={'publication_grant','available_actions','reason_codes','base_revision','connection_revision'}:raise StoreError('oauth_response_invalid')
    grant=value['publication_grant']
    if (type(grant) is not dict or set(grant)!=keys or grant['connection_id']!=connection_id
            or grant['account_id'] not in ('personal','dept') or grant['status'] not in ('blocked','granted','revoked','expired')
            or type(grant['revision']) is not int or grant['revision']<0
            or type(value['connection_revision']) is not int or value['connection_revision']<1):raise StoreError('oauth_response_invalid')
    for text in ('connection_id','platform','provider_id','target_id','policy_revision'):
        if type(grant[text]) is not str or not grant[text] or len(grant[text])>300 or any(ord(c)<32 for c in grant[text]):raise StoreError('oauth_response_invalid')
    if grant['provider_id'] not in {p.id for p in provider_catalog() if p.platform==grant['platform']}:raise StoreError('oauth_response_invalid')
    for field in ('approved_at','expires_at'):
        if grant[field] is not None:
            from datetime import datetime
            try:
                stamp=datetime.fromisoformat(grant[field].replace('Z','+00:00'))
                if stamp.tzinfo is None or stamp.utcoffset() is None:raise ValueError()
            except (TypeError,ValueError,AttributeError):raise StoreError('oauth_response_invalid') from None
    if (type(value['base_revision']) is not str or not value['base_revision'] or len(value['base_revision'])>256
            or type(value['available_actions']) is not list or len(set(value['available_actions']))!=len(value['available_actions'])
            or not set(value['available_actions'])<={'approve','revoke'}
            or type(value['reason_codes']) is not list or any(type(v) is not str or not re.fullmatch(r'oauth_[a-z_]{1,64}',v) for v in value['reason_codes'])):raise StoreError('oauth_response_invalid')
    return value


def _callback(handler,method,path,query):
    if method!='GET':return handler._error(405,'지원하지 않는 요청입니다')
    # _validated_target에서 fixed 정책 검증 후 이 경로만 쿠키 없이 수신한다.
    if handler.headers.get('Content-Length') not in (None,'0'):raise StoreError('invalid')
    if set(query) not in ({'state','code'},{'state','error'}):raise StoreError('invalid')
    params={k:v[0] for k,v in query.items()}
    if any(not v or len(v)>2048 or any(ord(c)<32 for c in v) for v in params.values()):raise StoreError('invalid')
    service=handler.server.oauth_service
    if service is None:return handler._error(503,'OAuth 연결 서비스가 준비되지 않았습니다')
    provider=path[len(CALLBACK):];uri=handler.server.oauth_callback_policy.redirect_uris[provider]
    service.receive_callback(provider,params,CallbackContext(provider,uri))
    return handler._send(303,body=b'',headers={'Location':SHELL})


def handle(handler,method,path,query):
    try:
        if path.startswith(CALLBACK):return _callback(handler,method,path,query)
        session=require_oauth_session(handler)
        if path==SHELL:
            if method!='GET':return handler._error(405,'지원하지 않는 요청입니다')
            return handler._static('index.html')
        service=handler.server.oauth_service
        account=query.get('account',['all'])[0]
        if method=='GET':
            if path==BASE+'/csrf':result=mint_csrf(session,handler.server.oauth_csrf_key)
            elif path==BASE+'/catalog':result=service.catalog(session,account) if service else disabled_catalog()
            elif path==BASE+'/connections':
                result=service.connections(session,account) if service else dict(items=[],base_revision=handler.server.metrics_registry().revision)
            elif path==BASE+'/result':result=service.result_for_session(session) if service else dict(items=[])
            elif (grant_match:=re.fullmatch(BASE+'/connections/('+ID+')/publication-grant',path)):
                grants=getattr(handler.server,'publication_grant_service',None)
                if grants is None:raise StoreError('storage_unavailable')
                result=_grant_public(grants.read(session,grant_match[1]),grant_match[1])
                return handler._send(200,result)
            else:
                match=re.fullmatch(BASE+'/attempts/('+ID+')',path)
                if not match:raise StoreError('not_found')
                if service is None:raise StoreError('storage_error')
                result=service.read_attempt(session,match[1])
            return handler._send(200,_public(result))
        if method!='POST':return handler._error(405,'지원하지 않는 요청입니다')
        external=getattr(handler.server,'external_access_policy',None)
        expected_origin=external.origin if external is not None else 'http://'+handler.headers.get('Host','')
        if handler.headers.get('Origin')!=expected_origin:
            raise OAuthSessionError(403,'oauth_origin_required')
        if not verify_csrf(session,handler.headers.get('X-CSRF-Token'),handler.server.oauth_csrf_key):
            raise OAuthSessionError(403,'oauth_csrf_invalid')
        body=handler._read_body(1024*1024,json_body=True)
        grant_match=re.fullmatch(BASE+'/connections/('+ID+')/publication-grant/(approve|revoke)',path)
        if grant_match:
            names=('expected_base_revision','expected_connection_revision','expected_grant_revision')
            _fields(body,names)
            if (type(body['expected_grant_revision']) is not int or body['expected_grant_revision']<0
                    or body['expected_connection_revision']<1):raise StoreError('invalid')
            grants=getattr(handler.server,'publication_grant_service',None)
            if grants is None or handler.server.workspace_root is None:raise StoreError('storage_unavailable')
            result=getattr(grants,grant_match[2])(session,grant_match[1],body)
            return handler._send(200,_grant_public(result,grant_match[1]))
        if path==BASE+'/attempts':
            names=('account_id','provider_id','connection_id','expected_base_revision','expected_connection_revision','requested_scopes')
            operation='start';identifier=None
        else:
            match=re.fullmatch(BASE+r'/(attempts|targets|connections)/('+ID+r')/(continue|inspect|confirm|refresh|disconnect|revoke)',path)
            if not match:raise StoreError('not_found')
            kind,identifier,action=match.groups()
            if (kind,action) not in {('attempts','continue'),('attempts','inspect'),('targets','confirm'),('connections','refresh'),('connections','disconnect'),('connections','revoke')}:raise StoreError('not_found')
            names=('expected_revision',) if kind=='attempts' else ('expected_base_revision','expected_connection_revision')
            operation={'continue':'resume_exchange','inspect':'inspect','confirm':'confirm_target','refresh':'refresh','disconnect':'disconnect_local','revoke':'revoke'}[action]
        _fields(body,names)
        if service is None or handler.server.workspace_root is None:return handler._send(503,{'error':'OAuth 연결 서비스가 준비되지 않았습니다','code':'oauth_service_unavailable'})
        result=getattr(service,operation)(session,body) if identifier is None else getattr(service,operation)(session,identifier,body)
        return handler._send(200,_public(result))
    except OAuthSessionError as exc:
        return handler._send(exc.status,{'error':'사용자 세션과 요청 권한을 확인하세요','code':exc.code})
    except StoreError as exc:
        if exc.code in ('not_found','oauth_session_required'):status=404
        elif exc.code in ('invalid','unknown_account','unknown_provider','oauth_callback_invalid'):status=400
        elif exc.code=='too_large':status=413
        elif exc.code=='unsupported_media':status=415
        elif exc.code in ('storage_error','storage_unavailable','schema_mismatch','not_initialized','oauth_credential_unavailable','oauth_response_invalid'):status=503
        else:status=409
        # 오류 원문/제공자 응답/경로/자격은 전달하지 않는다.
        code=exc.code if re.fullmatch(r'(?:oauth_[a-z_]{1,48}|conflict|expired|invalid|not_found|unknown_account|unknown_provider|base_revision_mismatch|credential_owner_mismatch)',exc.code) else 'oauth_service_unavailable'
        return handler._send(status,{'error':'OAuth 연결 요청을 처리할 수 없습니다','code':code})
    except Exception:
        return handler._send(503,{'error':'OAuth 연결 서비스가 준비되지 않았습니다','code':'oauth_service_unavailable'})
