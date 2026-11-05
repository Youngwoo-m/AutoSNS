"""X confidential-client refresh. authorize/code/PKCE 완결 계약은 준비 차단."""
import base64
from urllib.parse import quote
from .providers import OAuthProvider, blocked


class XProvider(OAuthProvider):
    contracts = {'refresh':('POST','https://api.x.com/2/oauth2/token')}

    def refresh(self, context, bundle, client_secret):
        _, client = self._context(context)
        if not client_secret or not bundle.refresh_token:
            blocked()
        encoded = base64.b64encode((quote(client.client_id,safe='')+':'+quote(client_secret,safe='')).encode()).decode('ascii')
        return self._tokens(self._request('refresh',context,dict(grant_type='refresh_token',refresh_token=bundle.refresh_token),{'Authorization':'Basic '+encoded}),previous=bundle)
