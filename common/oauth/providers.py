"""공식 확인된 OAuth 수명주기만 구현하는 서버 전용 adapter."""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from common.operations.content_store import StoreError
from common.operations.oauth_models import AttemptContext, OAuthClientRegistration, TokenBundle


def blocked():
    raise StoreError('oauth_contract_blocked')


class OAuthProvider:
    def __init__(self, definition, transport):
        self.definition = definition
        self.transport = transport

    def _context(self, wrapper, client_config=None):
        if not isinstance(wrapper, dict):
            blocked()
        context = wrapper.get('context')
        client = client_config or wrapper.get('client_config')
        if not isinstance(context, AttemptContext) or not isinstance(client, OAuthClientRegistration):
            blocked()
        if (context.provider_id != self.definition.id or client.provider_id != self.definition.id or
            context.redirect_uri != client.redirect_uri or context.client_revision != client.client_revision or
            context.evidence_revision != client.cost_evidence_revision or
            not set(context.requested_scopes).issubset(client.approved_scopes) or
            not set(context.requested_scopes).issubset(self.definition.read_scopes + self.definition.publication_scopes)):
            blocked()
        return context, client

    def _request(self, operation, wrapper, params, headers=None):
        context, _ = self._context(wrapper)
        rule = self.transport.rule(self.definition.id, operation, context.evidence_revision)
        # A catalog alone cannot invent a wire contract. Each adapter fixes the URL and verb too.
        contract = self.contracts.get(operation)
        if contract != (rule.method, rule.endpoint):
            blocked()
        return self.transport.request(operation, rule.endpoint, params, dict(provider_id=self.definition.id, evidence_revision=context.evidence_revision, headers=headers or {}))

    contracts = {}

    def authorize(self, attempt, client_config):
        blocked()

    def exchange(self, attempt, code, client_secret, verifier=None):
        blocked()

    def refresh(self, context, bundle, client_secret):
        blocked()

    def revoke(self, context, bundle, client_secret):
        blocked()

    def inspect(self, context, bundle):
        blocked()

    def _tokens(self, payload, *, separator=' ', previous=None):
        try:
            access = payload['access_token']
            token_type = payload.get('token_type', 'Bearer')
            refresh = payload.get('refresh_token', previous.refresh_token if previous else None)
            scopes = payload.get('scope')
            if scopes is None:
                scopes = previous.scopes if previous else ()
            elif isinstance(scopes, str):
                scopes = tuple(dict.fromkeys(s for s in scopes.split(separator) if s))
            else:
                blocked()
            expiry = payload.get('expires_in')
            if expiry is not None:
                if isinstance(expiry, bool) or int(expiry) <= 0:
                    blocked()
                expiry = (datetime.now(timezone.utc) + timedelta(seconds=int(expiry))).isoformat()
            return TokenBundle(access, refresh, token_type, expiry, tuple(scopes))
        except Exception:
            raise StoreError('oauth_response_invalid') from None


def build_providers(catalog, transport):
    from .naver import NaverProvider
    from .tiktok import TikTokProvider
    from .x import XProvider
    from .meta import MetaProvider
    from .google import GoogleProvider
    classes = {'naver':NaverProvider,'tiktok':TikTokProvider,'x':XProvider,
               'instagram_login':MetaProvider,'instagram_facebook':MetaProvider,'threads':MetaProvider,
               'facebook_pages':MetaProvider,'youtube':GoogleProvider,'blogger':GoogleProvider}
    return {p.id:classes.get(p.id, OAuthProvider)(p, transport) for p in catalog}
