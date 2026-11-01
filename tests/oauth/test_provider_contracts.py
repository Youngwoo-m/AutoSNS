"""격리 wire 시험. 실제 URL open/자격 저장소 호출 없음."""
import json
import unittest
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit
from common.operations.oauth_catalog import provider_catalog
from common.operations.oauth_models import AttemptContext, OAuthClientRegistration, TokenBundle
from common.operations.content_store import StoreError
from common.oauth import build_providers, OAuthTransport


class Response:
    def __init__(self, payload, status=200, url=None):
        self.payload = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.status = status
        self.url = url
    def read(self, size):
        return self.payload[:size]
    def close(self):
        pass
    def geturl(self):
        return self.url


class Contracts(unittest.TestCase):
    def setup_provider(self, provider_id='naver', response=None, catalog=None):
        self.calls = []
        self.response = response or Response({'access_token':'access-private', 'refresh_token':'refresh-private', 'token_type':'bearer', 'expires_in':'3600'})
        def fetch(request, *, timeout, context):
            self.calls.append((request, timeout, context))
            return self.response
        selected = next(p for p in provider_catalog() if p.id == provider_id)
        self.catalog = catalog or (replace(selected, operations=tuple(replace(r, cost_kind='no_additional_cost') for r in selected.operations)),)
        self.transport = OAuthTransport(self.catalog, fetch=fetch)
        self.provider = build_providers(self.catalog, self.transport)[provider_id]
        self.context = AttemptContext('console_user', 'binding', 'personal', provider_id, 'connection', 'base', 0, (), 'https://console.example/oauth/callback/'+provider_id, 'client', 1, selected.operations[0].evidence_revision)
        self.client = OAuthClientRegistration(provider_id, 'client-id', None, self.context.redirect_uri, 1, (), self.context.evidence_revision, None)
        self.attempt = dict(context=self.context, client_config=self.client, state='state-private')
        return self.provider

    def test_default_catalog_all_costs_block_before_fetch(self):
        for definition in provider_catalog():
            provider = self.setup_provider(definition.id, catalog=(definition,))
            with self.assertRaises(StoreError):
                provider.exchange(self.attempt, 'code-private', 'secret-private')
            self.assertEqual([], self.calls)

    def test_naver_authorize_scope_is_not_sent_and_redirect_exact(self):
        p = self.setup_provider()
        url = p.authorize(self.attempt, self.client)
        self.assertEqual('https://nid.naver.com/oauth2.0/authorize', url.split('?')[0])
        self.assertEqual({'client_id':['client-id'], 'redirect_uri':[self.context.redirect_uri], 'response_type':['code'], 'state':['state-private']}, parse_qs(urlsplit(url).query))
        self.assertEqual([], self.calls)
        with self.assertRaises(StoreError):
            p.authorize(self.attempt, replace(self.client, redirect_uri='https://wrong.example/callback'))

    def test_naver_exchange_exact_post_and_no_generic_redirect_or_scope(self):
        p = self.setup_provider()
        result = p.exchange(self.attempt, 'code-private', 'secret-private')
        req, timeout, context = self.calls[0]
        self.assertEqual('POST', req.method)
        self.assertEqual('https://nid.naver.com/oauth2.0/token', req.full_url)
        self.assertEqual({'grant_type':['authorization_code'], 'client_id':['client-id'], 'client_secret':['secret-private'], 'code':['code-private'], 'state':['state-private']}, parse_qs(req.data.decode()))
        self.assertGreater(timeout, 0)
        self.assertTrue(context.check_hostname)
        self.assertIsInstance(result, TokenBundle)
        self.assertEqual((), result.scopes)
        self.assertNotIn('access-private', repr(result))

    def test_naver_inspect_profile_does_not_invent_blog_targets(self):
        p = self.setup_provider(response=Response({'resultcode':'00', 'response':{'id':'subject', 'nickname':'label', 'email':'private@example.com'}}))
        result = p.inspect(self.attempt, TokenBundle('token', None, 'bearer', None, ()))
        self.assertEqual('subject', result['provider_subject'])
        self.assertEqual([], result['targets'])
        self.assertNotIn('private@example.com', repr(result))
        self.assertEqual('Bearer token', self.calls[0][0].get_header('Authorization'))

    def test_naver_revoke_empty_200_and_paired_impact(self):
        p = self.setup_provider(response=Response(b''))
        result = p.revoke(self.attempt, TokenBundle('token', 'refresh', 'bearer', None, ()), 'secret')
        self.assertEqual({'remote_revoked':True, 'impact':'paired_access_refresh_tokens'}, result)
        self.assertEqual({'client_id':['client-id'], 'client_secret':['secret'], 'token':['token'], 'token_type_hint':['access_token']}, parse_qs(self.calls[0][0].data.decode()))

    def test_tiktok_uses_client_key_and_refresh_rotation(self):
        p = self.setup_provider('tiktok', Response({'access_token':'new', 'refresh_token':'rotated', 'token_type':'Bearer', 'expires_in':123, 'scope':'user.info.basic,video.list'}))
        bundle = p.exchange(self.attempt, 'code', 'secret')
        fields = parse_qs(self.calls[0][0].data.decode())
        self.assertEqual(['client-id'], fields['client_key'])
        self.assertEqual([self.context.redirect_uri], fields['redirect_uri'])
        self.assertNotIn('client_id', fields)
        self.assertNotIn('state', fields)
        self.assertEqual(('user.info.basic','video.list'), bundle.scopes)
        p.refresh(self.attempt, bundle, 'secret')
        self.assertEqual(['rotated'], parse_qs(self.calls[1][0].data.decode())['refresh_token'])

    def test_contract_and_google_project_revoke_blocked(self):
        for name in ('instagram_login','instagram_facebook','facebook_pages','youtube','blogger','tistory'):
            p = self.setup_provider(name)
            with self.assertRaises(StoreError):
                p.revoke(self.attempt, TokenBundle('token',None,'Bearer',None,()), 'secret')
            self.assertEqual([], self.calls)

    def test_transport_errors_redirect_size_json_are_sanitized_no_retry(self):
        for response in (Response(b'secret-private',302), Response(b'x'*262145), Response(b'secret-private'), Response({'error_description':'secret-private','error':'bad'}), Response({},200,'https://evil.example/token')):
            p = self.setup_provider(response=response)
            with self.assertRaises(StoreError) as error:
                p.exchange(self.attempt,'code-private','secret-private')
            self.assertNotIn('private', str(error.exception))
            self.assertEqual(1,len(self.calls))

    def test_transport_endpoint_injection_and_unconfigured_fetch_blocked(self):
        self.setup_provider()
        with self.assertRaises(StoreError):
            self.transport.request('exchange','https://evil.example/token',{}, {'provider_id':'naver','evidence_revision':self.context.evidence_revision})
        self.assertEqual([],self.calls)
        t = OAuthTransport(self.catalog)
        with self.assertRaises(StoreError):
            build_providers(self.catalog,t)['naver'].exchange(self.attempt,'code','secret')

    def test_x_refresh_confidential_basic_auth(self):
        p = self.setup_provider('x')
        p.refresh(self.attempt,TokenBundle('token','refresh','bearer',None,()),'secret')
        req = self.calls[0][0]
        self.assertTrue(req.get_header('Authorization').startswith('Basic '))
        self.assertEqual({'grant_type':['refresh_token'],'refresh_token':['refresh']},parse_qs(req.data.decode()))

    def test_threads_refresh_timing_unverified_stays_blocked(self):
        p = self.setup_provider('threads')
        with self.assertRaises(StoreError):
            p.refresh(self.attempt,TokenBundle('token',None,'bearer',None,()),'secret')
        self.assertEqual([],self.calls)

    def test_pkce_unconfirmed_and_naver_missing_state_fail_before_wire(self):
        p = self.setup_provider()
        with self.assertRaises(StoreError):
            p.exchange(self.attempt,'code','secret',verifier='verifier-private')
        del self.attempt['state']
        with self.assertRaises(StoreError):
            p.exchange(self.attempt,'code','secret')
        self.assertEqual([],self.calls)

    def test_wire_exception_is_sanitized_and_not_retried(self):
        self.setup_provider()
        calls = []
        def fail(request, **kwargs):
            calls.append(request)
            raise RuntimeError('secret-private code-private token-private')
        t = OAuthTransport(self.catalog,fetch=fail)
        with self.assertRaises(StoreError) as error:
            build_providers(self.catalog,t)['naver'].exchange(self.attempt,'code','secret')
        self.assertEqual(1,len(calls))
        self.assertEqual('oauth_transport_failed',str(error.exception))

    def test_threads_exchange_uses_independent_client_and_exact_redirect(self):
        p = self.setup_provider('threads')
        bundle = p.exchange(self.attempt,'code','secret')
        req = self.calls[0][0]
        self.assertEqual('https://graph.threads.net/oauth/access_token',req.full_url)
        self.assertEqual({'client_id':['client-id'],'client_secret':['secret'],'grant_type':['authorization_code'],'redirect_uri':[self.context.redirect_uri],'code':['code']},parse_qs(req.data.decode()))
        self.assertIsInstance(bundle,TokenBundle)

    def test_forged_catalog_method_cannot_create_an_unimplemented_wire(self):
        definition = next(p for p in provider_catalog() if p.id=='naver')
        forged = replace(definition,operations=tuple(replace(r,cost_kind='no_additional_cost',method='GET') for r in definition.operations))
        p = self.setup_provider(catalog=(forged,))
        with self.assertRaises(StoreError):
            p.exchange(self.attempt,'code','secret')
        self.assertEqual([],self.calls)

    def test_shared_token_endpoint_cannot_change_grant_under_another_cost_rule(self):
        for name in ('naver','tiktok'):
            for allowed, injected in (('refresh','authorization_code'),('exchange','refresh_token')):
                definition = next(p for p in provider_catalog() if p.id==name)
                catalog = (replace(definition,operations=tuple(replace(r,cost_kind='no_additional_cost' if r.operation==allowed else 'unknown') for r in definition.operations)),)
                self.setup_provider(name,catalog=catalog)
                endpoint = next(r.endpoint for r in catalog[0].operations if r.operation==allowed)
                client_field = 'client_key' if name == 'tiktok' else 'client_id'
                fields = dict(client_secret='private-secret', grant_type=injected)
                fields[client_field] = 'id'
                if allowed == 'refresh':
                    fields['refresh_token'] = 'refresh'
                else:
                    fields['code'] = 'code'
                    fields['state' if name == 'naver' else 'redirect_uri'] = 'state' if name == 'naver' else self.context.redirect_uri
                # 필드 집합이 맞아도 grant가 다르면 해당 operation 비용으로 보낼 수 없다.
                with self.assertRaises(StoreError):
                    self.transport.request(allowed,endpoint,fields, {'provider_id':name,'evidence_revision':self.context.evidence_revision})
                self.assertEqual([],self.calls)

    def test_transport_rejects_extra_fields_missing_auth_and_changed_auth_method(self):
        cases = [
            ('naver',{'grant_type':'refresh_token','client_id':'id','client_secret':'secret','refresh_token':'refresh','code':'code'},{}),
            ('naver',{'grant_type':'refresh_token','client_id':'id','refresh_token':'refresh'},{}),
            ('tiktok',{'grant_type':'refresh_token','client_id':'id','client_secret':'secret','refresh_token':'refresh'},{}),
            ('x',{'grant_type':'refresh_token','refresh_token':'refresh'},{}),
            ('x',{'grant_type':'refresh_token','refresh_token':'refresh'},{'Authorization':'Bearer private'}),
            ('naver',{'grant_type':'refresh_token','client_id':'id','client_secret':'secret','refresh_token':'refresh'},{'Authorization':'Basic private'}),
        ]
        for name,params,headers in cases:
            self.setup_provider(name)
            endpoint = next(r.endpoint for r in self.catalog[0].operations if r.operation=='refresh')
            with self.assertRaises(StoreError):
                self.transport.request('refresh',endpoint,params,{'provider_id':name,'evidence_revision':self.context.evidence_revision,'headers':headers})
            self.assertEqual([],self.calls)

    def test_naver_revoke_nonempty_json_is_not_empty_http200(self):
        for raw in (b'{}',b'null',b' ',b'{"success":true}'):
            p = self.setup_provider(response=Response(raw))
            with self.assertRaises(StoreError):
                p.revoke(self.attempt,TokenBundle('token',None,'Bearer',None,()),'secret')
            self.assertEqual(1,len(self.calls))
