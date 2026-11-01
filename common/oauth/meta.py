"""Meta login별 별도 정의를 유지. 미확인 URL/PKCE/refresh 시점을 추정하지 않는다."""
from .providers import OAuthProvider, blocked


class MetaProvider(OAuthProvider):
    contracts = {'exchange':('POST','https://graph.threads.net/oauth/access_token')}

    def exchange(self, attempt, code, client_secret, verifier=None):
        context, client = self._context(attempt)
        if self.definition.id != 'threads' or verifier is not None or not code or not client_secret:
            blocked()
        return self._tokens(self._request('exchange',attempt,dict(client_id=client.client_id,client_secret=client_secret,grant_type='authorization_code',redirect_uri=context.redirect_uri,code=code)))
