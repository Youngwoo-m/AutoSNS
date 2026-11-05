import unittest
from contextlib import contextmanager
from tests import test_web_metrics as web
from tests.operations import test_metrics as fixture
from common.operations.metrics_collection import MetricsCollectionService
from common.operations.metrics_models import MetricResult

class MetricsCollectionHTTPTests(unittest.TestCase):
    request=web.MetricsHTTPTests.request
    stop=web.MetricsHTTPTests.stop
    def setUp(self):
        web.MetricsHTTPTests.setUp(self)
        self.server.metrics_store.initialize();self.calls=[]
        runtime=fixture.Runtime();runtime.root=self.workspace;self.runtime=runtime
        @contextmanager
        def lock(ctx):self.calls.append('lock');yield;self.calls.append('unlock')
        def collector(ctx,remote):
            self.calls.append('collect')
            return MetricResult('ok',{'views':0},fixture.NOW,remote,ctx.target_id,'youtube.views',basis='lifetime',source={'token':'SECRET'})
        self.server.metrics_collection_service=MetricsCollectionService(runtime,self.server.metrics_store,runtime.registry,{'dept.youtube':collector},lock,enabled=True)
    def test_explicit_collection_auth_origin_identity_and_projection(self):
        targets='/api/v2/metrics/collection-targets?account=dept'
        self.assertEqual(self.request(targets,auth=False)[0],401)
        code,data=self.request(targets);self.assertEqual(code,200);self.assertEqual(len(data['items']),1)
        self.assertEqual(self.calls,[])
        code,data=self.request('/api/v2/metrics/collection-targets?account=personal');self.assertEqual(data['items'],[])
        path='/api/v2/metrics/collect';body={'delivery_id':'d'}
        self.assertEqual(self.request(path,'POST',body,origin='https://evil.test')[0],403)
        for extra in ({'remote_id':'else'},{'account_id':'personal'},{'collector':'else'}):
            self.assertEqual(self.request(path,'POST',{**body,**extra})[0],400)
        code,data=self.request(path,'POST',body);self.assertEqual(code,200)
        row=data['observation'];self.assertEqual(row['values'],{'views':0});self.assertEqual(row['source_kind'],'verified_delivery')
        self.assertNotIn('SECRET',str(data));self.assertEqual(self.calls,['lock','collect','unlock'])
        self.assertEqual(self.runtime.get_delivery('d')['state'],'verified')
        self.assertEqual(len(self.server.metrics_store.list_observations()),1)
        code,snapshot=self.request('/api/v2/metrics?account=dept')
        self.assertEqual(code,200);self.assertTrue(snapshot['collection_enabled'])
        support=next(item for item in snapshot['support'] if item['platform']=='youtube')
        self.assertEqual(support['implementation_status'],'implemented');self.assertEqual(support['auth_status'],'unknown')
        self.assertEqual(support['collection_status'],'collected');self.assertEqual(self.calls,['lock','collect','unlock'])
    def test_changed_or_unverified_context_and_disabled_service_do_not_collect(self):
        self.runtime.rows[0]['state']='scheduled'
        self.assertEqual(self.request('/api/v2/metrics/collect','POST',{'delivery_id':'d'})[0],409)
        self.assertEqual(self.calls,[])
        self.server.metrics_collection_service=None
        self.assertEqual(self.request('/api/v2/metrics/collect','POST',{'delivery_id':'d'})[0],503)
        self.assertEqual(self.calls,[])
