"""네이버 회원 프로필 전용. 블로그 대상·발행 권한은 반환하지 않는다."""
from datetime import datetime, timezone
from urllib.parse import urlencode
from .providers import OAuthProvider, blocked


class NaverProvider(OAuthProvider):
    contracts = {
        'authorize':('GET','https://nid.naver.com/oauth2.0/authorize'),
        'exchange':('POST','https://nid.naver.com/oauth2.0/token'),
        'refresh':('POST','https://nid.naver.com/oauth2.0/token'),
        'revoke':('POST','https://nid.naver.com/oauth2.0/revoke'),
        'inspect':('GET','https://openapi.naver.com/v1/nid/me'),
    }

    def authorize(self, attempt, client_config):
        context, client = self._context(attempt, client_config)
        rule = self.transport.rule(self.definition.id, 'authorize', context.evidence_revision)
        if self.contracts['authorize'] != (rule.method,rule.endpoint):
            blocked()
        state = attempt.get('state')
        if not isinstance(state,str) or not state or attempt.get('code_challenge'):
            blocked()
        return rule.endpoint + '?' + urlencode(dict(response_type='code',client_id=client.client_id,redirect_uri=context.redirect_uri,state=state))

    def exchange(self, attempt, code, client_secret, verifier=None):
        _, client = self._context(attempt)
        state = attempt.get('state')
        if verifier is not None or not state or not code or not client_secret:
            blocked()
        payload = self._request('exchange',attempt,dict(grant_type='authorization_code',client_id=client.client_id,client_secret=client_secret,code=code,state=state))
        return self._tokens(payload)

    def refresh(self, context, bundle, client_secret):
        _, client = self._context(context)
        if not bundle.refresh_token or not client_secret:
            blocked()
        return self._tokens(self._request('refresh',context,dict(grant_type='refresh_token',client_id=client.client_id,client_secret=client_secret,refresh_token=bundle.refresh_token)),previous=bundle)

    def revoke(self, context, bundle, client_secret):
        _, client = self._context(context)
        if not client_secret:
            blocked()
        payload = self._request('revoke',context,dict(client_id=client.client_id,client_secret=client_secret,token=bundle.access_token,token_type_hint='access_token'))
        if payload:
            blocked()
        return dict(remote_revoked=True,impact='paired_access_refresh_tokens')

    def inspect(self, context, bundle):
        payload = self._request('inspect',context,{}, {'Authorization':'Bearer '+bundle.access_token})
        profile = payload.get('response')
        if payload.get('resultcode') != '00' or not isinstance(profile,dict) or not isinstance(profile.get('id'),str) or not profile['id']:
            blocked()
        return dict(provider_subject=profile['id'],targets=[],observed_scopes=list(bundle.scopes),checked_at=datetime.now(timezone.utc).isoformat())
