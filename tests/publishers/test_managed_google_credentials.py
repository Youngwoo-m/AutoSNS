"""관리 자격의 사용 guard 안에서만 Google SDK 자격을 만든다. 가짜 resolver/factory만 사용."""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
import sys
import traceback
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from common.operations.models import ContractError
from common.operations.oauth_models import TokenBundle
from common.publishers.managed_google_credentials import ManagedGoogleCredentialResolver

SECRET='private-access-token-never-print'
REF='dept.youtube.credential'


def resolved(**changes):
    value=dict(reference=REF,account_id='dept',platform='youtube',scope='read',target_id='UC-dept',provider_id='youtube',connection_id='dept.youtube',generation=1,
        bundle=TokenBundle(SECRET,'DO-NOT-USE-REFRESH','Bearer',(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),('https://www.googleapis.com/auth/youtube.readonly',)))
    return SimpleNamespace(**dict(value,**changes))


class Resolver:
    def __init__(self,value=None):self.value=resolved() if value is None else value;self.calls=[];self.active=False
    @contextmanager
    def use(self,reference,**kwargs):
        self.calls.append(('enter',reference,kwargs));self.active=True
        try:yield self.value
        finally:self.active=False;self.calls.append(('exit',))


class ManagedGoogleCredentialTests(unittest.TestCase):
    def use(self,resolver,**changes):
        return resolver.use(REF,**dict(dict(account_id='dept',platform='youtube',scope='read',target_id='UC-dept'),**changes))

    def test_constructor_is_inert_and_credentials_remain_inside_underlying_guard(self):
        underlying=Resolver();calls=[]
        def factory(**kwargs):self.assertTrue(underlying.active);calls.append(kwargs);return object()
        wrapper=ManagedGoogleCredentialResolver(underlying,credentials_factory=factory)
        self.assertEqual(underlying.calls,[]);self.assertEqual(calls,[]);self.assertFalse(callable(wrapper))
        with self.use(wrapper) as credential:
            self.assertTrue(underlying.active);self.assertIsNotNone(credential)
            self.assertEqual(len(calls),1);self.assertEqual(calls[0]['token'],SECRET)
            self.assertEqual(calls[0]['scopes'],list(underlying.value.bundle.scopes))
            self.assertEqual(set(calls[0]),{'token','scopes','expiry','refresh_token'})
            self.assertIsNone(calls[0]['refresh_token']);self.assertIsInstance(calls[0]['expiry'],datetime)
        self.assertFalse(underlying.active);self.assertEqual(underlying.calls[0],('enter',REF,dict(account_id='dept',platform='youtube',scope='read',target_id='UC-dept')))
        self.assertEqual(underlying.calls[-1],('exit',))

    def test_utc_offset_expiry_is_normalized_to_google_sdk_naive_utc(self):
        aware=(datetime.now(timezone.utc)+timedelta(hours=2)).astimezone(timezone(timedelta(hours=9)))
        row=resolved(bundle=TokenBundle(SECRET,None,'Bearer',aware.isoformat(),('scope',)))
        underlying=Resolver(row);calls=[]
        wrapper=ManagedGoogleCredentialResolver(underlying,credentials_factory=lambda **kw:calls.append(kw) or object())
        with self.use(wrapper):pass
        self.assertEqual(calls[0]['expiry'],aware.astimezone(timezone.utc).replace(tzinfo=None));self.assertIsNone(calls[0]['expiry'].tzinfo)

    def test_resolved_identity_mismatches_never_construct_sdk_credentials(self):
        changes=[dict(reference='other'),dict(account_id='personal'),dict(platform='blogger'),dict(scope='publication'),dict(target_id='UC-other'),dict(provider_id='blogger')]
        for change in changes:
            underlying=Resolver(resolved(**change));calls=[];wrapper=ManagedGoogleCredentialResolver(underlying,credentials_factory=lambda **kw:calls.append(kw))
            with self.assertRaises(ContractError):
                with self.use(wrapper):self.fail('mismatched credential yielded')
            self.assertEqual(calls,[]);self.assertFalse(underlying.active)

    def test_expired_missing_or_invalid_bundle_never_constructs_credentials_or_leaks_token(self):
        expiries=[None,'invalid',(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),'2099-01-01T00:00:00']
        for expiry in expiries:
            row=resolved(bundle=TokenBundle(SECRET,None,'Bearer',expiry,('scope',)))
            calls=[];wrapper=ManagedGoogleCredentialResolver(Resolver(row),credentials_factory=lambda **kw:calls.append(kw))
            with self.assertRaises(ContractError) as caught:
                with self.use(wrapper):pass
            self.assertNotIn(SECRET,str(caught.exception));self.assertEqual(calls,[])
        for bundle in (None,SimpleNamespace(access_token=SECRET,scopes=('scope',),expires_at='BAD SECRET')):
            wrapper=ManagedGoogleCredentialResolver(Resolver(resolved(bundle=bundle)),credentials_factory=lambda **kw:self.fail('factory called'))
            with self.assertRaises(ContractError):
                with self.use(wrapper):pass

    def test_underlying_and_factory_errors_are_sanitized_with_guard_exit(self):
        class FailingResolver:
            @contextmanager
            def use(self,*args,**kwargs):raise RuntimeError(SECRET);yield
        wrappers=[ManagedGoogleCredentialResolver(FailingResolver(),credentials_factory=lambda **kw:None)]
        underlying=Resolver()
        def fail(**kwargs):raise RuntimeError(SECRET)
        wrappers.append(ManagedGoogleCredentialResolver(underlying,credentials_factory=fail))
        for wrapper in wrappers:
            with self.assertRaises(ContractError) as caught:
                with self.use(wrapper):pass
            self.assertNotIn(SECRET,str(caught.exception));self.assertIsNone(caught.exception.__cause__);self.assertIsNone(caught.exception.__context__)
        self.assertFalse(underlying.active)

    def test_publication_is_delegated_and_remains_blocked_by_underlying_policy(self):
        calls=[]
        class ReadOnly:
            @contextmanager
            def use(self,reference,**kwargs):calls.append(kwargs['scope']);raise ContractError('managed_publication_disabled',SECRET);yield
        wrapper=ManagedGoogleCredentialResolver(ReadOnly(),credentials_factory=lambda **kw:self.fail('factory called'))
        with self.assertRaises(ContractError) as caught:
            with self.use(wrapper,scope='publication'):pass
        self.assertEqual(calls,['publication']);self.assertNotIn(SECRET,str(caught.exception))

    def test_default_google_import_is_lazy_and_blogger_scope_is_supported(self):
        row=resolved(reference='dept.blogger.credential',platform='blogger',provider_id='blogger',connection_id='dept.blogger',target_id='blog-id')
        underlying=Resolver(row);calls=[]
        wrapper=ManagedGoogleCredentialResolver(underlying)
        self.assertEqual(calls,[])
        with patch.dict(sys.modules,{'google':SimpleNamespace(),'google.oauth2':SimpleNamespace(),'google.oauth2.credentials':SimpleNamespace(Credentials=lambda **kw:calls.append(kw) or object())}):
            with wrapper.use('dept.blogger.credential',account_id='dept',platform='blogger',scope='read',target_id='blog-id'):pass
        self.assertEqual(len(calls),1);self.assertIsNone(calls[0]['refresh_token'])

    def test_api_exception_exits_guard_and_does_not_expose_original_exception(self):
        underlying=Resolver();wrapper=ManagedGoogleCredentialResolver(underlying,credentials_factory=lambda **kw:object())
        with self.assertRaises(ContractError) as caught:
            with self.use(wrapper):
                self.assertTrue(underlying.active)
                raise RuntimeError(SECRET)
        self.assertFalse(underlying.active);self.assertEqual(underlying.calls[-1],('exit',))
        self.assertNotIn(SECRET,str(caught.exception));self.assertTrue(caught.exception.__suppress_context__)
        self.assertNotIn(SECRET,''.join(traceback.format_exception(caught.exception)))
