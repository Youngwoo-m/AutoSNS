"""발행 host의 읽기 자격은 조회 handler 전체에서 소유 guard를 유지한다."""
from contextlib import contextmanager
from types import SimpleNamespace
import unittest
from common.operations.models import Registry,Connection,ContractError
from common.publishers.bridge_host import BridgeHost

class ScopedBridgeCredentialTests(unittest.TestCase):
    def host(self,resolver,*,owner='personal',catalog_owner='personal'):
        ref='oauth:personal:youtube:personal.youtube:1'
        registry=Registry('r',{'personal':{},'dept':{}},{ref:dict(account_id=owner,platform='youtube')},{},
            {'personal.youtube':Connection('personal.youtube','personal','youtube',target_id='channel',credential_ref=ref)}, {},{}, {})
        host=BridgeHost(registry,None,SimpleNamespace(),None,{},credential_catalog={ref:dict(credential_ref=ref,account_id=catalog_owner,platform='youtube')},credential_resolver=resolver)
        return host,SimpleNamespace(connection_id='personal.youtube',target_id='channel'),ref
    def test_scoped_credential_guard_remains_held_through_handler_and_exception(self):
        events=[];secret=object()
        class Resolver:
            @contextmanager
            def use(self,reference,**binding):
                events.append(('enter',reference,binding));yield secret;events.append('exit')
        host,ctx,ref=self.host(Resolver())
        with host._credential_scope(ctx,'read') as credential:
            self.assertIs(credential,secret);self.assertEqual(len(events),1)
            self.assertEqual(events[0][2],dict(account_id='personal',platform='youtube',scope='read',target_id='channel'))
        self.assertEqual(events[-1],'exit')
        closed=[]
        class FinalResolver:
            @contextmanager
            def use(self,*args,**kwargs):
                try:yield secret
                finally:closed.append(True)
        host,ctx,_=self.host(FinalResolver())
        with self.assertRaises(RuntimeError):
            with host._credential_scope(ctx,'read'):raise RuntimeError('handler failure')
        self.assertEqual(closed,[True])
    def test_owner_catalog_mismatch_is_rejected_before_entering_scope(self):
        calls=[]
        class Resolver:
            def use(self,*a,**k):calls.append(a);raise AssertionError('should not read')
        for kwargs in (dict(owner='dept'),dict(catalog_owner='dept')):
            host,ctx,_=self.host(Resolver(),**kwargs)
            with self.assertRaises(ContractError):
                with host._credential_scope(ctx,'read'):pass
        self.assertEqual(calls,[])
    def test_legacy_callable_resolver_remains_inside_old_contract(self):
        calls=[];secret=object()
        def legacy(reference,**binding):calls.append((reference,binding));return secret
        host,ctx,_=self.host(legacy)
        with host._credential_scope(ctx,'read') as credential:self.assertIs(credential,secret)
        self.assertEqual(calls[0][1],dict(account_id='personal',platform='youtube',scope='read'))
