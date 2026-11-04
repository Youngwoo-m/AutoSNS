"""서버 소유 OAuth 계약. import는 I/O를 하지 않으며 비밀은 자동 직렬화하지 않는다."""
from dataclasses import dataclass
from urllib.parse import urlsplit
from .content_store import StoreError


def _invalid():
    raise StoreError('invalid_oauth_model')


def _text(value, nullable=False):
    if value is None and nullable:
        return
    if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
        _invalid()


def _tuple(value):
    if not isinstance(value, (tuple, list)):
        _invalid()
    for item in value:
        _text(item)
    return tuple(value)


def _https(value):
    _text(value)
    try:
        parsed = urlsplit(value)
        parsed.port
    except ValueError:
        _invalid()
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or parsed.query:
        _invalid()


@dataclass(frozen=True)
class OperationRule:
    operation: str
    method: str
    endpoint: str | None
    contract_status: str
    cost_kind: str
    evidence_revision: str
    checked_at: str

    def __post_init__(self):
        for name in ('operation', 'method', 'contract_status', 'cost_kind', 'evidence_revision', 'checked_at'):
            _text(getattr(self, name))
        if self.endpoint is not None:
            _https(self.endpoint)
        if self.method not in ('GET', 'POST') or self.cost_kind not in ('no_additional_cost', 'paid', 'credits', 'unknown') or self.contract_status not in ('verified', 'contract_blocked', 'unsupported'):
            _invalid()


@dataclass(frozen=True)
class ProviderDefinition:
    id: str
    platform: str
    login_method: str
    operations: tuple[OperationRule, ...]
    read_scopes: tuple[str, ...]
    publication_scopes: tuple[str, ...]
    pkce_mode: str
    redirect_policy: str
    policy_reasons: tuple[str, ...]

    def __post_init__(self):
        for name in ('id', 'platform', 'login_method', 'redirect_policy'):
            _text(getattr(self, name))
        if self.pkce_mode not in ('s256', 'unsupported', 'unconfirmed'):
            _invalid()
        if not isinstance(self.operations, (tuple, list)) or not all(isinstance(r, OperationRule) for r in self.operations):
            _invalid()
        object.__setattr__(self, 'operations', tuple(self.operations))
        for name in ('read_scopes', 'publication_scopes', 'policy_reasons'):
            object.__setattr__(self, name, _tuple(getattr(self, name)))

    def to_dict(self, *, public=True):
        return dict(provider_id=self.id, platform=self.platform, login_method=self.login_method,
                    read_scopes=list(self.read_scopes), publication_scopes=list(self.publication_scopes),
                    pkce_mode=self.pkce_mode, redirect_policy=self.redirect_policy,
                    policy_reasons=list(self.policy_reasons), ready=False, execution_enabled=False)


@dataclass(frozen=True, repr=False)
class AttemptContext:
    actor: str
    session_binding: str
    account_id: str
    provider_id: str
    connection_id: str
    base_revision: str
    connection_revision: int
    requested_scopes: tuple[str, ...]
    redirect_uri: str
    client_ref: str
    client_revision: int
    evidence_revision: str
    scope_policy_revision: str | None = None

    def __post_init__(self):
        for name in ('actor', 'session_binding', 'account_id', 'provider_id', 'connection_id', 'base_revision', 'redirect_uri', 'client_ref', 'evidence_revision'):
            _text(getattr(self, name))
        if self.account_id not in ('personal', 'dept'):
            _invalid()
        for name in ('connection_revision', 'client_revision'):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                _invalid()
        if self.scope_policy_revision is not None:
            _text(self.scope_policy_revision)
        _https(self.redirect_uri)
        object.__setattr__(self, 'requested_scopes', _tuple(self.requested_scopes))

    def __repr__(self):
        return 'AttemptContext(<private>)'


class _Private:
    __slots__ = ()

    def __setattr__(self, name, value):
        raise AttributeError('immutable_private_model')

    def __repr__(self):
        return type(self).__name__ + '(<private>)'

    def to_dict(self, *, public=True):
        if not public:
            raise StoreError('private_serialization_forbidden')
        return {}


class TokenBundle(_Private):
    __slots__ = ('access_token', 'refresh_token', 'token_type', 'expires_at', 'scopes')

    def __init__(self, access_token: str, refresh_token: str | None, token_type: str,
                 expires_at: str | None, scopes: tuple[str, ...]):
        _text(access_token)
        _text(refresh_token, True)
        _text(token_type)
        _text(expires_at, True)
        for name, value in dict(access_token=access_token, refresh_token=refresh_token,
                                token_type=token_type, expires_at=expires_at, scopes=_tuple(scopes)).items():
            object.__setattr__(self, name, value)


class CredentialRef(_Private):
    __slots__ = ('namespace', 'account_id', 'platform', 'connection_id', 'generation', 'kind')

    def __init__(self, namespace: str, account_id: str, platform: str, connection_id: str,
                 generation: int, kind: str):
        for value in (namespace, account_id, platform, connection_id, kind):
            _text(value)
        if namespace != 'autosns.oauth' or account_id not in ('personal', 'dept') or type(generation) is not int or generation < 1 or kind not in ('client', 'code', 'verifier', 'ticket', 'token', 'state_key'):
            _invalid()
        for name, value in dict(namespace=namespace, account_id=account_id, platform=platform,
                                connection_id=connection_id, generation=generation, kind=kind).items():
            object.__setattr__(self, name, value)

    def __eq__(self, other):
        if not isinstance(other, CredentialRef):
            return NotImplemented
        return all(getattr(self, key) == getattr(other, key) for key in self.__slots__)

    def __hash__(self):
        return hash(tuple(getattr(self, key) for key in self.__slots__))


@dataclass(frozen=True, repr=False)
class OAuthClientRegistration:
    provider_id: str
    client_id: str
    client_secret_ref: CredentialRef | None
    redirect_uri: str
    client_revision: int
    approved_scopes: tuple[str, ...]
    cost_evidence_revision: str
    expected_project_id: str | None

    def __post_init__(self):
        for name in ('provider_id', 'client_id', 'redirect_uri', 'cost_evidence_revision'):
            _text(getattr(self, name))
        _text(self.expected_project_id, True)
        _https(self.redirect_uri)
        if type(self.client_revision) is not int or self.client_revision < 1:
            _invalid()
        if self.client_secret_ref is not None and (not isinstance(self.client_secret_ref, CredentialRef) or self.client_secret_ref.kind != 'client'):
            _invalid()
        object.__setattr__(self, 'approved_scopes', _tuple(self.approved_scopes))

    def __repr__(self):
        return 'OAuthClientRegistration(<private>)'


@dataclass(frozen=True, repr=False)
class CallbackClaim:
    attempt_id: str
    lease_revision: int
    expires_at: str
    context: AttemptContext

    def __post_init__(self):
        _text(self.attempt_id)
        _text(self.expires_at)
        if type(self.lease_revision) is not int or self.lease_revision < 1 or not isinstance(self.context, AttemptContext):
            _invalid()


@dataclass(frozen=True)
class OAuthPolicy:
    live_enabled: bool = False

    def __post_init__(self):
        if type(self.live_enabled) is not bool:
            _invalid()


def validate_authorization(value):
    """비밀 없는 인증 관측만 정규화한다. 요청 scope로 허용 권한을 합성하지 않는다."""
    from datetime import datetime, timezone
    fields = {'observed_scopes', 'credential_expires_at', 'read_status', 'publication_status', 'credential_status'}
    if not isinstance(value, dict) or set(value) != fields:
        _invalid()
    scopes = value['observed_scopes']
    if scopes is not None:
        if not isinstance(scopes, (list, tuple)) or len(scopes) > 100:
            _invalid()
        for scope in scopes:
            _text(scope)
            if len(scope) > 500:
                _invalid()
        scopes = list(scopes)
    expiry = value['credential_expires_at']
    if expiry is not None:
        try:
            parsed = datetime.fromisoformat(expiry)
            if parsed.tzinfo is None:
                _invalid()
            expiry = parsed.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError):
            _invalid()
    choices = {
        'read_status': ('not_checked', 'verified', 'unknown', 'error'),
        'publication_status': ('not_checked', 'blocked'),
        'credential_status': ('pending', 'stored', 'active', 'reauth_required', 'unknown'),
    }
    for field, allowed in choices.items():
        if value[field] not in allowed:
            _invalid()
    return dict(value, observed_scopes=scopes, credential_expires_at=expiry)
