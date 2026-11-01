"""고정 catalog 전용 전송. 기본 fetch=None이며 import/생성은 네트워크 I/O가 없다."""
import json
import ssl
from urllib.parse import urlencode
from urllib.request import Request, HTTPRedirectHandler, HTTPSHandler, build_opener
from common.operations.content_store import StoreError

MAX_RESPONSE_BYTES = 262144


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise StoreError('oauth_redirect_rejected')


def urllib_fetch(request, *, timeout, context):
    """명시 주입용. 시스템 proxy/쿠키/리다이렉트를 사용하지 않는다."""
    from urllib.request import ProxyHandler
    return build_opener(ProxyHandler({}), _NoRedirect(), HTTPSHandler(context=context)).open(request, timeout=timeout)


class OAuthTransport:
    def __init__(self, catalog, *, fetch=None, timeout=10, max_response_bytes=MAX_RESPONSE_BYTES):
        self._catalog = {p.id:p for p in catalog}
        self._fetch = fetch
        if type(timeout) not in (int,float) or not 0 < timeout <= 30 or type(max_response_bytes) is not int or not 0 < max_response_bytes <= MAX_RESPONSE_BYTES:
            raise StoreError('invalid_oauth_transport')
        self.timeout = timeout
        self.max_response_bytes = max_response_bytes

    def rule(self, provider_id, operation, evidence_revision):
        provider = self._catalog.get(provider_id)
        rules = [] if provider is None else [r for r in provider.operations if r.operation == operation]
        if len(rules) != 1 or rules[0].contract_status != 'verified' or not rules[0].endpoint:
            raise StoreError('oauth_contract_blocked')
        rule = rules[0]
        if rule.evidence_revision != evidence_revision:
            raise StoreError('oauth_evidence_stale')
        if rule.cost_kind != 'no_additional_cost':
            raise StoreError('oauth_cost_blocked')
        return rule

    def request(self, operation, endpoint, params, credentials):
        rule = self.rule(credentials.get('provider_id'), operation, credentials.get('evidence_revision'))
        if endpoint != rule.endpoint or not endpoint.startswith('https://'):
            raise StoreError('oauth_contract_blocked')
        if self._fetch is None:
            raise StoreError('oauth_transport_unconfigured')
        encoded = urlencode(params).encode('ascii')
        url = endpoint + ('?' + encoded.decode() if rule.method == 'GET' and encoded else '')
        headers = dict(credentials.get('headers', {}))
        if rule.method == 'POST':
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        headers['Accept'] = 'application/json'
        response = None
        try:
            request = Request(url, data=encoded if rule.method == 'POST' else None, headers=headers, method=rule.method)
            response = self._fetch(request, timeout=self.timeout, context=ssl.create_default_context())
            if response.status != 200:
                raise StoreError('oauth_remote_error')
            final_url = response.geturl()
            if final_url is not None and final_url != url:
                raise StoreError('oauth_redirect_rejected')
            raw = response.read(self.max_response_bytes + 1)
            if not isinstance(raw, bytes) or len(raw) > self.max_response_bytes:
                raise StoreError('oauth_response_invalid')
            if not raw:
                if operation == 'revoke':
                    return {}
                raise StoreError('oauth_response_invalid')
            value = json.loads(raw.decode('utf-8'))
            if not isinstance(value, dict) or value.get('error'):
                raise StoreError('oauth_remote_error')
            return value
        except Exception:
            raise StoreError('oauth_transport_failed') from None
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass
