"""실제 permit fixture와 가짜 자격을 이용한 scope/잠금 순서. API·vault 호출 없음."""
from contextlib import contextmanager
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from common.operations.models import ContractError
from common.publishers.bridge_host import BridgeHost
from tests.publishers import test_instagram_bridge_host as fixture_module


class ManagedScopeTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture_module.InstagramBridgeHostTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.events=[];self.active=False;self.guard_count=0;self.invalid_on_check=None
        owner=self
        class Resolver:
            def __call__(self,*args,**kwargs):raise AssertionError('no callable fallback')
            @contextmanager
            def use(self,reference,**binding):
                owner.events.append('enter');owner.active=True
                owner.assertEqual(binding['scope'],'publication');owner.assertEqual(binding['target_id'],owner.f.ctx.target_id)
                def authority():
                    owner.assertTrue(owner.active);owner.guard_count+=1;owner.events.append('guard')
                    if owner.guard_count==owner.invalid_on_check:raise RuntimeError('private token')
                try:yield SimpleNamespace(assert_publication_authority=authority)
                finally:owner.active=False;owner.events.append('exit')
        self.resolver=Resolver()
    def test_scope_spans_redemption_and_handler_with_publication_gate_released(self):
        original_gate=self.f.locks.publication_guard;original_redeem=self.f.store.redeem_bridge
        @contextmanager
        def gate(*,job,wait=10):
            with original_gate(job=job,wait=wait):
                if job=='bridge-leaf':self.assertTrue(self.active);self.events.append('gate-enter')
                yield
            if job=='bridge-leaf':self.events.append('gate-exit')
        def redeem(*args,**kwargs):
            self.assertTrue(self.active);self.events.append('redeem');return original_redeem(*args,**kwargs)
        original_submit=self.f.service.submit
        def submit(*args):
            self.assertTrue(self.active);self.assertNotIn('control:publish-gate',self.f.locks._owned_locks)
            self.events.append('handler');return original_submit(*args)
        self.f.service.submit=submit
        with patch.object(self.f.locks,'publication_guard',side_effect=gate),patch.object(self.f.store,'redeem_bridge',side_effect=redeem):
            with self.f.request() as frame:result=self.f.execute(self.f.host(resolver=self.resolver),frame)
        self.assertEqual(result['outcome'],'submitted');self.assertEqual(self.f.redemptions(),1)
        self.assertEqual(self.events,['enter','guard','gate-enter','guard','redeem','gate-exit','handler','exit'])
        self.assertFalse(self.active)
    def test_failed_initial_or_gate_authority_never_consumes_redemption(self):
        for at in (1,2):
            self.invalid_on_check=at;self.guard_count=0;self.events=[]
            with self.f.request() as frame:
                with self.assertRaises(ContractError) as caught:self.f.execute(self.f.host(resolver=self.resolver),frame)
            self.assertEqual(caught.exception.code,'managed_publication_unverified')
            self.assertNotIn('private token',str(caught.exception));self.assertFalse(self.active)
            self.assertEqual(self.f.redemptions(),0);self.assertEqual(self.f.factories,[])
    def test_use_enter_failure_never_redeems_and_handler_exception_exits_scope(self):
        class Denied:
            @contextmanager
            def use(self,*args,**kwargs):raise ContractError('oauth_publication_unverified');yield
        with self.f.request() as frame:
            with self.assertRaises(ContractError):self.f.execute(self.f.host(resolver=Denied()),frame)
        self.assertEqual(self.f.redemptions(),0)
        def failed(*args):self.assertTrue(self.active);raise RuntimeError('leaf failed')
        self.f.service.submit=failed
        with self.f.request() as frame:
            with self.assertRaises(RuntimeError):self.f.execute(self.f.host(resolver=self.resolver),frame)
        self.assertEqual(self.events[-1],'exit');self.assertFalse(self.active);self.assertEqual(self.f.redemptions(),1)
    def test_profile_connection_without_credential_never_enters_managed_resolver(self):
        class Resolver:
            def use(self,*args,**kwargs):raise AssertionError('profile has no credential')
        host=BridgeHost(SimpleNamespace(connections={'profile':SimpleNamespace(credential_ref=None)}),None,SimpleNamespace(),None,{},credential_resolver=Resolver())
        for scope in ('read','publication'):
            with host._credential_scope(SimpleNamespace(connection_id='profile'),scope) as credential:self.assertIsNone(credential)
