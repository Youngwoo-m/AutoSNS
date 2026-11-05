"""명시 성과 수집 기동은 자격/프로필 결속만 확인하고 실제 수집 전에는 외부 호출이 없다."""
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from common.operations.bootstrap_config import BootstrapConfig
from common.operations.content_store import StoreError
from common.operations.metrics_startup import build_metrics_collection_service
from common.operations.metrics_store import MetricsStore
from common.operations.models import Registry,Connection,ContractError
from tests.operations import test_metrics as fixture

class MetricsStartupTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)/'managed'
        self.config=BootstrapConfig(workspace_root=self.root);self.runtime=fixture.Runtime();self.runtime.root=self.root
        self.registry=Registry('r',{'personal':{},'dept':{}},{'dept.youtube.credential':dict(account_id='dept',platform='youtube')},{'dept-profile':dict(account_id='dept',lock_resource='profile:youtube-dept')},{'dept.youtube':Connection('dept.youtube','dept','youtube',target_id='channel',profile_ref='dept-profile',credential_ref='dept.youtube.credential')},{},{},{})
        self.metrics=MetricsStore(self.root);self.calls=[]
        calls=self.calls
        class Locks:
            @contextmanager
            def hold(self,resources,**kwargs):calls.append(('lock',list(resources),kwargs));yield;calls.append('unlock')
        self.locks=Locks()
    def factory(self,ctx):
        self.calls.append(('factory',ctx.connection_id))
        calls=self.calls
        class Service:
            def read_statistics(self,target,remote):
                calls.append(('read',target,remote))
                return dict(id=remote,snippet=dict(channelId='channel'),status=dict(privacyStatus='public'),statistics=dict(viewCount='4'))
        return Service()
    def build(self,**kw):
        values=dict(config=self.config,registry=self.registry,runtime_store=self.runtime,metrics_store=self.metrics,locks=self.locks,connection_ids=['dept.youtube'],services_factory=self.factory,activate=True);values.update(kw)
        return build_metrics_collection_service(**values)
    def test_build_and_targets_do_not_initialize_resolve_credentials_or_collect(self):
        service=self.build();self.assertTrue(service.enabled);self.assertEqual(self.calls,[]);self.assertFalse(self.root.exists())
        self.assertEqual(len(service.targets('dept')),1);self.assertEqual(self.calls,[]);self.assertFalse(self.root.exists())
    def test_collect_holds_server_resources_before_lazy_factory_and_read(self):
        service=self.build();self.metrics.initialize();row=service.collect('d')
        self.assertEqual(row['values'],{'views':4})
        self.assertEqual(self.calls[0],('lock',['profile:youtube-dept','account:dept','connection:dept.youtube'],dict(job='metrics:dept.youtube',wait=0,check_stop=False)))
        self.assertEqual(self.calls[1],('factory','dept.youtube'));self.assertEqual(self.calls[-1],'unlock')
    def test_inactive_unknown_connection_foreign_roots_and_unbound_profile_rejected(self):
        for changes in ({'activate':False},{'activate':1},{'connection_ids':[]},{'connection_ids':['dept.youtube','dept.youtube']},{'connection_ids':['dept.x']},{'metrics_store':MetricsStore(self.root.parent/'other')},{'locks':object()}):
            with self.assertRaises((StoreError,ContractError)):self.build(**changes)
        conn=self.registry.connections['dept.youtube']
        for changed in (replace(conn,profile_ref='missing'),replace(conn,credential_ref='oauth:dept:youtube:other:1'),replace(conn,target_id=''),replace(conn,account_id='personal')):
            registry=replace(self.registry,connections={'dept.youtube':changed})
            with self.assertRaises((StoreError,ContractError)):self.build(registry=registry)
        self.assertEqual(self.calls,[]);self.assertFalse(self.root.exists())
    def test_default_factory_is_lazy_and_preserves_read_credential_scope(self):
        from unittest.mock import patch
        with patch('common.publishers.youtube_runtime.resolve_youtube_credentials') as resolve,patch('common.publishers.youtube_services.create_youtube_services') as create:
            service=self.build(services_factory=None);service.targets();resolve.assert_not_called();create.assert_not_called()
            self.metrics.initialize();create.return_value=type('ReadOnly',(),{'read_statistics':lambda _,target,remote:dict(id=remote,snippet=dict(channelId='channel'),status=dict(privacyStatus='public'),statistics=dict(viewCount='0'))})()
            result=service.collect('d');self.assertEqual(result['values'],{'views':0})
            resolve.assert_called_once_with('dept.youtube.credential',account_id='dept',platform='youtube',scope='read')
            self.assertEqual(create.call_args.args,('dept.youtube',resolve.return_value))
            with self.assertRaises(ContractError):create.call_args.kwargs['media_loader']('never',1,'asset')
