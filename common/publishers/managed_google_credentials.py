"""관리 OAuth 사용 guard 안에서만 Google SDK 자격을 조립한다.

모듈 import·생성자는 Google SDK/자격 저장소/네트워크에 접근하지 않는다.
호출형 token 반환 API는 제공하지 않는다. 실제 API 작업은 use()의 with 안에서 수행한다.
"""
from contextlib import contextmanager
from datetime import datetime,timezone

from common.operations.models import ContractError
from common.operations.oauth_models import TokenBundle

_ERROR='managed_google_credentials_unavailable'


def _text(value):
    if not isinstance(value,str) or not value.strip() or '\x00' in value:
        return False
    try:value.encode('utf-8')
    except UnicodeError:return False
    return True


def _credentials_factory(**kwargs):
    # 생성자에서 import하지 않는다. Refresh token/client secret/token URI는 전달하지 않는다.
    from google.oauth2.credentials import Credentials
    return Credentials(**kwargs)


def _unavailable():
    raise ContractError(_ERROR) from None


def _guard_sdk(credential,resolved,state,seen):
    """Guard authorization application and every SDK clone with one scoped lease.

    Both before_request and apply are needed: googleapiclient batch serialization
    can call apply directly. Managed access tokens never refresh automatically.
    https://github.com/googleapis/google-api-python-client/blob/main/googleapiclient/_auth.py
    """
    current=getattr(resolved,'assert_current',None)
    if not callable(current):_unavailable()
    if id(credential) in seen:
        return credential
    originals={name:getattr(credential,name,None) for name in ('apply','before_request','refresh')}
    if not all(callable(method) for method in originals.values()):_unavailable()
    def check():
        failed=not state['active']
        if not failed:
            try:current()
            except Exception:failed=True
        if failed:_unavailable()
    def publication():
        check()
        assertion=getattr(resolved,'assert_publication_authority',None)
        failed=not callable(assertion)
        if not failed:
            try:assertion()
            except Exception:failed=True
        if failed:_unavailable()
    def invoke(method,*args,**kwargs):
        failed=False;value=None
        try:value=method(*args,**kwargs)
        except Exception:failed=True
        if failed:_unavailable()
        return value
    def guarded(method):
        def call(*args,**kwargs):
            check()
            return invoke(method,*args,**kwargs)
        return call
    def no_refresh(*args,**kwargs):
        check()
        _unavailable()
    def clone(method):
        def call(*args,**kwargs):
            check()
            value=invoke(method,*args,**kwargs)
            return _guard_sdk(value,resolved,state,seen)
        return call
    # Capture original bound methods before attaching closures. SDK objects with
    # immutable slots fail closed rather than returning an unguarded credential.
    clones={name:getattr(credential,name) for name in dir(credential)
            if name.startswith('with_') and callable(getattr(credential,name))}
    setattr(credential,'apply',guarded(originals['apply']))
    setattr(credential,'before_request',guarded(originals['before_request']))
    setattr(credential,'refresh',no_refresh)
    setattr(credential,'assert_current',check)
    setattr(credential,'assert_publication_authority',publication)
    for name,method in clones.items():
        setattr(credential,name,no_refresh if name=='with_non_blocking_refresh' else clone(method))
    seen[id(credential)]=credential
    check()
    return credential


class ManagedGoogleCredentialResolver:
    def __init__(self,resolver,*,credentials_factory=None):
        if (not callable(getattr(resolver,'use',None))
                or credentials_factory is not None and not callable(credentials_factory)):
            raise ContractError(_ERROR)
        self.resolver=resolver
        self.credentials_factory=credentials_factory if credentials_factory is not None else _credentials_factory

    @contextmanager
    def use(self,reference,*,account_id,platform,scope,target_id=None):
        if (not _text(reference) or account_id not in ('personal','dept')
                or platform not in ('youtube','blogger') or scope not in ('read','publication')
                or target_id is not None and not _text(target_id)):
            raise ContractError(_ERROR)
        failed=False
        try:
            # publication 허용 여부도 기존 resolver 정책이 결정한다. 읽기 scope로 강등하지 않는다.
            with self.resolver.use(reference,account_id=account_id,platform=platform,scope=scope,target_id=target_id) as resolved:
                if (resolved.reference!=reference or resolved.account_id!=account_id
                        or resolved.platform!=platform or resolved.scope!=scope or resolved.provider_id!=platform
                        or target_id is not None and resolved.target_id!=target_id):
                    raise ValueError('credential_identity_mismatch')
                current=getattr(resolved,'assert_current',None)
                if scope=='publication':
                    if not callable(current) or not callable(getattr(resolved,'assert_publication_authority',None)):
                        raise ValueError('missing_publication_authority')
                    resolved.assert_publication_authority()
                if callable(current):current()
                bundle=resolved.bundle
                if (not isinstance(bundle,TokenBundle) or not _text(bundle.access_token)
                        or not isinstance(bundle.scopes,tuple) or not bundle.scopes
                        or not all(_text(item) for item in bundle.scopes)
                        or not isinstance(bundle.expires_at,str)):
                    raise ValueError('invalid_credential_bundle')
                expires=datetime.fromisoformat(bundle.expires_at.replace('Z','+00:00'))
                if expires.tzinfo is None or expires.utcoffset() is None:
                    raise ValueError('invalid_credential_expiry')
                expires=expires.astimezone(timezone.utc)
                if expires<=datetime.now(timezone.utc):
                    raise ValueError('expired_credential')
                # google-auth는 expiry를 naive UTC datetime과 비교한다.
                credential=self.credentials_factory(token=bundle.access_token,scopes=list(bundle.scopes),
                    expiry=expires.replace(tzinfo=None),refresh_token=None)
                if credential is None:
                    raise ValueError('invalid_sdk_credential')
                state={'active':True}
                if callable(current):credential=_guard_sdk(credential,resolved,state,{})
                try:
                    yield credential
                finally:
                    state['active']=False
        except Exception:
            failed=True
        # with의 종료·사용자 API 예외도 외부 원문 없이 고정 코드로 전달한다.
        # 고정 예외만 노출하고 from None으로 원래 예외의 traceback 연결을 숨긴다.
        if failed:
            raise ContractError(_ERROR) from None
