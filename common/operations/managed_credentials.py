"""서버 소유 OAuth 자격의 읽기 전용 임대.

실제 OAuth 정책/비용/권한 부여를 바꾸지 않는다. 현재 publication은 항상 거부한다.
read 역시 자격을 전달할 뿐 API 실행을 허가하지 않는다. caller의 기존 읽기 정책과
대상 확인이 필요하며, use 블록 전체에서 OAuth writer guard를 유지한다. 생성자는
vault·파일 생성·provider·SDK를 호출하지 않고 legacy 자격으로 fallback하지 않는다.
"""
from collections.abc import Mapping
from contextlib import contextmanager,ExitStack
from dataclasses import dataclass
from datetime import datetime,timezone
import json
from pathlib import Path

from .content_store import StoreError
from .credential_backend import CredentialError
from .managed_connections import credential_catalog,project_registry
from .models import Registry
from .oauth_catalog import provider_catalog
from .oauth_models import TokenBundle,validate_authorization
from .oauth_stage_backend import OwnedStageBackend
from .oauth_stage_models import OwnedCredentialRef,logical_ref
from .oauth_workspace import OAuthWorkspaceContext,validate_workspace_context,oauth_write_guard

_MAX_TOKEN_BYTES=65536
_TOKEN_FIELDS={'access_token','refresh_token','token_type','expires_at','scopes'}
_SAFE_ERRORS={'credential_owner_mismatch','oauth_credential_invalid','oauth_credential_expired',
              'oauth_scope_unverified','credential_changed','oauth_publication_unverified'}


def _error(code):raise StoreError(code)

def _unique(pairs):
    value={}
    for key,item in pairs:
        if key in value:raise ValueError('duplicate token field')
        value[key]=item
    return value

def _reject_constant(value):raise ValueError('invalid token constant')

def _time(value):
    if isinstance(value,str):value=datetime.fromisoformat(value.replace('Z','+00:00'))
    if not isinstance(value,datetime) or value.tzinfo is None or value.utcoffset() is None:
        _error('oauth_credential_invalid')
    return value.astimezone(timezone.utc)

def _expiry(value,now):
    if value is None:_error('oauth_credential_expired')
    if _time(value)<=now:_error('oauth_credential_expired')

def _scopes(value,known):
    if (not isinstance(value,(list,tuple)) or any(type(item) is not str or not item for item in value)
            or len(value)!=len(set(value)) or not set(value)<=known):_error('oauth_scope_unverified')
    return set(value)

def _token(raw):
    try:
        if type(raw) is not bytes or len(raw)>_MAX_TOKEN_BYTES:raise ValueError()
        value=json.loads(raw.decode('utf-8'),object_pairs_hook=_unique,parse_constant=_reject_constant)
        if type(value) is not dict or set(value)!=_TOKEN_FIELDS:raise ValueError()
        if (type(value['token_type']) is not str or value['token_type'].lower()!='bearer'
                or not isinstance(value['scopes'],list) or any(type(s) is not str for s in value['scopes'])):raise ValueError()
        bundle=TokenBundle(**{**value,'token_type':'Bearer'})
        if not bundle.access_token.strip():raise ValueError()
        return bundle
    except Exception:
        raise StoreError('oauth_credential_invalid') from None


@dataclass(frozen=True,repr=False)
class ResolvedManagedCredential:
    bundle: TokenBundle
    account_id: str
    platform: str
    connection_id: str
    target_id: str
    provider_id: str
    scope: str
    reference: str
    generation: int
    def __repr__(self):return 'ResolvedManagedCredential(<private>)'
    def to_dict(self,*,public=True):return {}


class ManagedCredentialResolver:
    def __init__(self,connection_store,owned_backend,workspace_context,registry_supplier,*,clock=None):
        if (not callable(getattr(connection_store,'snapshot',None)) or not isinstance(owned_backend,OwnedStageBackend)
                or not isinstance(workspace_context,OAuthWorkspaceContext) or not callable(registry_supplier)
                or (clock is not None and not callable(clock))):_error('credential_owner_mismatch')
        try:
            roots=(Path(connection_store.root).resolve(),Path(owned_backend.context.root).resolve(),Path(workspace_context.root).resolve())
            if len(set(roots))!=1 or owned_backend.context.owner!=workspace_context.owner:_error('credential_owner_mismatch')
        except Exception:
            raise StoreError('credential_owner_mismatch') from None
        self.connection_store=connection_store;self.owned_backend=owned_backend;self.workspace_context=workspace_context
        self.registry_supplier=registry_supplier;self.clock=clock or (lambda:datetime.now(timezone.utc))

    def _selected(self,reference,account_id,platform,target_id,now):
        context=validate_workspace_context(self.workspace_context)
        backend_context=validate_workspace_context(self.owned_backend.context)
        if context.owner!=backend_context.owner or context.root!=backend_context.root:_error('credential_owner_mismatch')
        snapshot=self.connection_store.snapshot();base=self.registry_supplier()
        if (not isinstance(base,Registry) or snapshot.base_revision!=base.revision
                or snapshot.workspace_owner!=context.owner):_error('credential_owner_mismatch')
        catalog=credential_catalog(snapshot);entry=catalog.get(reference)
        if not isinstance(entry,Mapping):_error('credential_owner_mismatch')
        ref=entry.get('credential_ref')
        if type(ref) is not OwnedCredentialRef or (ref.workspace_id,ref.root_binding)!=(context.owner.workspace_id,context.owner.root_binding):
            _error('credential_owner_mismatch')
        logical=logical_ref(ref);row=snapshot.connections.get(logical.connection_id)
        if (logical.account_id!=account_id or logical.platform!=platform or logical.kind!='token'
                or reference!=f'oauth:{account_id}:{platform}:{logical.connection_id}:{logical.generation}'
                or not isinstance(row,Mapping) or row.get('state')!='connected'
                or row.get('operation_lease') is not None or row.get('credential_ref')!=ref
                or row.get('credential_generation')!=logical.generation or row.get('base_revision')!=base.revision
                or not isinstance(row.get('target_id'),str) or not row['target_id']
                or target_id is not None and row['target_id']!=target_id):_error('credential_owner_mismatch')
        configured=project_registry(base,snapshot).connections.get(logical.connection_id)
        if (configured is None or configured.account_id!=account_id or configured.platform!=platform
                or configured.target_id!=row['target_id']):_error('credential_owner_mismatch')
        definition=next((p for p in provider_catalog() if p.id==row.get('provider_id')),None)
        if definition is None or definition.platform!=platform or not definition.read_scopes:_error('oauth_scope_unverified')
        authorization=row.get('authorization')
        if not isinstance(authorization,Mapping):_error('oauth_scope_unverified')
        authorization=validate_authorization(dict(authorization))
        if authorization['credential_status']!='active' or authorization['read_status']!='verified':_error('oauth_scope_unverified')
        required=set(definition.read_scopes);known=required|set(definition.publication_scopes)
        observed=_scopes(authorization['observed_scopes'],known)
        if not required<=observed or _scopes(row.get('scopes'),known)!=observed:_error('oauth_scope_unverified')
        _expiry(authorization['credential_expires_at'],now)
        return snapshot,base,row,ref,definition,required,known,observed

    @contextmanager
    def use(self,reference,*,account_id,platform,scope,target_id=None):
        if scope=='publication':_error('oauth_publication_unverified')
        if (scope!='read' or type(reference) is not str or not reference
                or type(account_id) is not str or account_id not in ('personal','dept')
                or type(platform) is not str or not platform
                or target_id is not None and (type(target_id) is not str or not target_id)):
            _error('credential_owner_mismatch')
        with ExitStack() as stack:
            try:stack.enter_context(oauth_write_guard(self.workspace_context))
            except Exception:raise StoreError('credential_owner_mismatch') from None
            try:
                now=_time(self.clock())
                selected=self._selected(reference,account_id,platform,target_id,now)
                snapshot,base,row,ref,definition,required,known,observed=selected
                bundle=_token(self.owned_backend.read_owned(ref))
                _expiry(bundle.expires_at,now)
                granted=_scopes(bundle.scopes,known)
                if not required<=granted or not observed<=granted:_error('oauth_scope_unverified')
            except Exception as exc:
                code=exc.code if isinstance(exc,StoreError) and exc.code in _SAFE_ERRORS else 'oauth_credential_invalid'
                raise StoreError(code) from None
            try:
                fresh=self._selected(reference,account_id,platform,target_id,_time(self.clock()))
                _expiry(bundle.expires_at,_time(self.clock()))
                if (fresh[0].generation!=snapshot.generation or fresh[0].workspace_owner!=snapshot.workspace_owner
                        or fresh[0].base_revision!=snapshot.base_revision or fresh[1]!=base or fresh[2]!=row or fresh[3]!=ref):
                    _error('credential_changed')
            except Exception:raise StoreError('credential_changed') from None
            resolved=ResolvedManagedCredential(bundle,account_id,platform,logical_ref(ref).connection_id,
                row['target_id'],definition.id,scope,reference,logical_ref(ref).generation)
            # guard 유지 중에만 SDK 변환 및 신뢰된 호출자가 자격을 사용할 수 있다.
            yield resolved
