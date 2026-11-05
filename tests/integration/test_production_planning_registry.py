"""조회 등록부를 보존하면서 제작만 실행하는 웹 조립 시험."""
from dataclasses import replace
import unittest
from unittest.mock import patch
from common.operations.models import Connection
from tests.integration import test_production_startup as production_fixture
from tests import test_web_execution_server as web_fixture

class PlanningRegistryTests(unittest.TestCase):
    setUp = production_fixture.ProductionStartupTests.setUp
    runtime = production_fixture.ProductionStartupTests.runtime
    ready = production_fixture.ProductionStartupTests.ready

    def planning(self):
        return replace(self.registry, revision='planning-rev', jobs={},
            connections={'personal.youtube': Connection('personal.youtube','personal','youtube',target_id='channel-personal')},
            crossposts={'personal-to-dept': dict(owner_account_id='personal',destination_account_id='dept')})

    def create(self, runtime, planning, **kwargs):
        return web_fixture.server_module.create_server(source_root=self.config.source_root,
            workspace_root=self.config.workspace_root, web_root=web_fixture.APP/'web',
            auth_backend=web_fixture.A9Auth(),execution_service=runtime.service,
            planning_registry=planning,**kwargs)

    def test_planning_channels_and_crossposts_survive_without_enabling_publication(self):
        runtime=self.runtime(initialize=False)
        planning=self.planning()
        with patch.object(web_fixture.server_module,'_WebServer',web_fixture.NoSocketServer):
            server=self.create(runtime,planning)
        self.assertIs(server.ledger.registry(),planning)
        self.assertIs(server.metrics_registry(),planning)
        self.assertIs(server.runtime_store,runtime.service.store)
        self.assertIs(server.content_store,runtime.service.store.content_store)
        self.assertEqual(server.execution_status_info()['publication_jobs'],[])
        self.assertIn('personal.youtube',server.ledger.registry().connections)
        self.assertIn('personal-to-dept',server.ledger.registry().crossposts)
        self.assertEqual(dict(runtime.service.adapters),{})
        self.assertFalse(self.config.workspace_root.exists())

    def test_account_or_job_collisions_are_rejected_before_socket_and_writes(self):
        runtime=self.runtime(initialize=False)
        for planning in (replace(self.planning(),accounts={'dept':{}}),
                         replace(self.planning(),jobs={'produce-personal':dict(kind='publication')})):
            with patch.object(web_fixture.server_module,'_WebServer') as socket:
                with self.assertRaises(ValueError):self.create(runtime,planning)
                socket.assert_not_called()
        self.assertFalse(self.config.workspace_root.exists())

    def test_general_service_cannot_override_planning_registry(self):
        runtime=self.runtime(initialize=False)
        for value in (None,web_fixture.FixtureService()):
            with patch.object(web_fixture.server_module,'_WebServer') as socket:
                with self.assertRaises(ValueError):
                    web_fixture.server_module.create_server(source_root=self.config.source_root,
                        workspace_root=self.config.workspace_root,web_root=web_fixture.APP/'web',
                        auth_backend=web_fixture.A9Auth(),execution_service=value,planning_registry=self.planning())
                socket.assert_not_called()

    def test_ambiguous_registry_options_are_rejected(self):
        runtime=self.runtime(initialize=False)
        with patch.object(web_fixture.server_module,'_WebServer') as socket:
            with self.assertRaises(ValueError):
                self.create(runtime,self.planning(),operations_registry=self.registry)
            socket.assert_not_called()

    def test_actual_application_keeps_channels_and_runs_only_production(self):
        import json
        import threading
        from tests.integration import test_production_application as app_fixture
        from tests import test_web_server as http_fixture
        from tests.operations.test_runtime_store import NOW
        runtime, contents = self.ready()
        app = app_fixture.build(runtime=runtime,config=self.config,planning_registry=self.planning(),
            host='127.0.0.1',port=0,web_root=web_fixture.APP/'web',auth_backend=web_fixture.A9Auth())
        self.server=app.server
        app.initialize_storage()
        self.assertTrue(self.server.ledger._initialized)
        self.assertTrue(self.server.metrics_store._initialized)
        errors=[]
        def serve():
            try:app.serve_forever(join_timeout=3)
            except BaseException as error:errors.append(error)
        thread=__import__('threading').Thread(target=serve)
        thread.start()
        def close():
            if app.state=='serving':app.request_shutdown()
            thread.join(5)
            self.assertFalse(thread.is_alive())
        self.addCleanup(close)
        request=lambda *a,**kw:http_fixture.WebServerTests.request(self,*a,**kw)
        status,headers,_=request('/api/auth/login','POST',{'password':'fixture-password'})
        self.assertEqual(status,200)
        cookie={'Cookie':headers['Set-Cookie'].split(';')[0]}
        status,_,body=request('/api/v2/connections',headers=cookie)
        self.assertEqual(status,200)
        self.assertIn('personal.youtube',body.decode())
        snapshot=contents['personal']
        body=dict(trigger=dict(job_id=self.job_ids['personal'],scheduled_at_utc=NOW.isoformat(),
            phase='prepare',source='console',request_kind='new_publication',mode='live'),
            content_id=snapshot['id'],expected_revision=snapshot['revision'])
        status,_,result=request('/api/v2/execution/requests','POST',body,cookie)
        self.assertEqual(status,200)
        run=json.loads(result)
        for _ in range(40):
            status,_,result=request('/api/v2/execution/runs/'+run['run_id'],headers=cookie)
            result=json.loads(result)
            if (result.get('production') or {}).get('status')=='completed':break
            threading.Event().wait(.05)
        self.assertEqual(result['production']['status'],'completed')
        self.assertEqual(len(self.calls),1)
        self.assertEqual(dict(runtime.service.adapters),{})
        close()
        self.assertEqual(errors,[])
        self.assertEqual(app.worker_state,'stopped')

    def test_real_server_failure_before_loop_does_not_trap_failed_worker(self):
        import threading
        from tests.integration import test_production_application as app_fixture
        runtime,_=self.ready()
        release=threading.Event()
        def worker():
            release.wait(2)
            raise RuntimeError('fixture worker failure')
        runtime.worker.run=worker
        app=app_fixture.build(runtime=runtime,config=self.config,planning_registry=self.planning(),
            host='127.0.0.1',port=0,web_root=web_fixture.APP/'web',auth_backend=web_fixture.A9Auth())
        def broken_server():
            release.set()
            raise ValueError('fixture loop startup failure')
        with patch.object(app.server,'serve_forever',side_effect=broken_server):
            with self.assertRaisesRegex(ValueError,'loop startup'):
                app.serve_forever(join_timeout=1)
        self.assertFalse(app._thread.is_alive())
        self.assertEqual(app.state,'closed')
        self.assertEqual(app.worker_state,'failed')
