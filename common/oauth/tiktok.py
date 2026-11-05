"""TikTok token 관리만. Display/Upload/Direct Post 작업을 혼합하지 않는다."""
from .providers import OAuthProvider, blocked


class TikTokProvider(OAuthProvider):
    contracts = {operation:('POST','https://open.tiktokapis.com/v2/oauth/token/') for operation in ('exchange','refresh')}

    def exchange(self, attempt, code, client_secret, verifier=None):
        context, client = self._context(attempt)
        if verifier is not None or not code or not client_secret:
            blocked()
        return self._tokens(self._request('exchange',attempt,dict(client_key=client.client_id,client_secret=client_secret,code=code,grant_type='authorization_code',redirect_uri=context.redirect_uri)),separator=',')

    def refresh(self, context, bundle, client_secret):
        _, client = self._context(context)
        if not client_secret or not bundle.refresh_token:
            blocked()
        return self._tokens(self._request('refresh',context,dict(client_key=client.client_id,client_secret=client_secret,grant_type='refresh_token',refresh_token=bundle.refresh_token)),separator=',',previous=bundle)
