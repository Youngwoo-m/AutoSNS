"""A9 서버 주입/HTTP 경계. 임시 자료 외 외부 I/O 없음."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests import test_web_server as server_fixture
APP=server_fixture.APP
from tests.test_web_execution import FixtureService, trigger
from common.operations.models import Registry
from common.operations.runtime_models import ExecutionPolicy
from common.shared.axlock import AxLock, LockPaths

SPEC=importlib.util.spec_from_file_location('a9_server', APP/'web_server.py')
server_module=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(server_module)

class A9Auth(server_fixture.FakeAuth):
    def cookie_of(self,header):return (header or '').removeprefix('ax_phase6_fixture_session=')
    def set_cookie(self,token):return f'ax_phase6_fixture_session={token}; HttpOnly; SameSite=Strict; Path=/'
    def clear_cookie(self):return 'ax_phase6_fixture_session=; Max-Age=0; Path=/'

class NoSocketServer:
    def __init__(self,address,handler):self.server_port=9123

class ServerInjectionTests(unittest.TestCase):
    def test_registry_and_source_lock_are_shared_without_creation(self):
        with tempfile.TemporaryDirectory() as td, patch.object(server_module,'_WebServer',NoSocketServer):
            source=Path(td)/'source';workspace=Path(td)/'workspace'
            registry=Registry('v',{}, {}, {}, {}, {}, {}, {})
            server=server_module.create_server(source_root=source,workspace_root=workspace,web_root=APP/'web',operations_registry=registry,auth_backend=A9Auth())
            self.assertIs(server.runtime_store.registry,registry);self.assertIs(server.ledger.registry(),registry)
            self.assertIs(server.production_store.registry,registry)
            self.assertIs(server.runtime_store.locks,server.production_store.locks)
            self.assertEqual(server.runtime_store.locks.paths.root,source.resolve())
            self.assertFalse(source.exists());self.assertFalse(workspace.exists())

    def test_explicit_service_stores_and_status_info_are_used(self):
        from common.operations.bootstrap_config import BootstrapConfig,build_execution_service
        from common.operations.execution_catalog import ExecutionCatalog
        with tempfile.TemporaryDirectory() as td, patch.object(server_module,'_WebServer',NoSocketServer):
            root=Path(td);config=BootstrapConfig(code_root=root/'code',source_root=root/'source',workspace_root=root/'workspace',registry_path=root/'registry')
            registry=Registry('v',{}, {}, {}, {}, {}, {}, {})
            service=build_execution_service(config=config,registry=registry,catalog=ExecutionCatalog())
            server=server_module.create_server(source_root=config.source_root,workspace_root=config.workspace_root,web_root=APP/'web',auth_backend=A9Auth(),execution_service=service)
            self.assertIs(server.runtime_store,service.store);self.assertIs(server.ledger,service.ledger)
            self.assertIs(server.production_store,service.production_store);self.assertIs(server.content_store,service.store.content_store)
            self.assertIs(server.execution_service,service);self.assertEqual(server.execution_status_info(),service.status_info())
            self.assertFalse(config.workspace_root.exists())

class ExecutionHTTPTests(unittest.TestCase):
    request=server_fixture.WebServerTests.request
    def login(self):
        status,headers,_=self.request('/api/auth/login','POST',{'password':'fixture-password'})
        self.assertEqual(status,200)
        return {'Cookie':headers['Set-Cookie'].split(';')[0]}
    def setUp(self):
        import threading
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);self.service=FixtureService()
        self.server=server_module.create_server(source_root=root/'source',workspace_root=root/'workspace',web_root=APP/'web',auth_backend=A9Auth(),execution_service=self.service,execution_policy=ExecutionPolicy(True,(),'cutover'),execution_status_info={'capabilities':{'request':True,'observe':True,'admit':True,'approve':True}})
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.stop)
    def stop(self):self.server.shutdown();self.server.server_close();self.thread.join()
    def test_auth_origin_schema_disabled_replay_and_actor(self):
        url='/api/v2/execution/requests';body={'trigger':trigger(),'content_id':'content_fixture','expected_revision':1}
        self.assertEqual(self.request(url,'POST',body)[0],401)
        cookie=self.login();self.assertEqual(self.request(url,'POST',body,{**cookie,'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request(url,'POST',{**body,'owner':'dept'},cookie)[0],400)
        self.assertEqual(self.service.calls,[])
        self.server.execution_policy=ExecutionPolicy()
        self.assertEqual(self.request(url,'POST',body,cookie)[0],409);self.assertEqual(self.service.calls,[])
        self.server.execution_policy=ExecutionPolicy(True,(),'cutover')
        first=self.request(url,'POST',body,cookie);self.assertEqual(first[0],200);self.assertEqual(self.request(url,'POST',body,cookie)[2],first[2])
        self.assertEqual(self.service.calls[-1][2],'console')
        admission={'run_id':'run_fixture','expected_version':1,'observation_id':'observation_fixture'}
        self.assertEqual(self.request('/api/v2/execution/deliveries/delivery_fixture/admit','POST',admission,cookie)[0],200)
        self.assertFalse(any(call[0]=='approve' for call in self.service.calls))
        approval={'expected_version':2,'context_hash':'b'*64,'request_key':'approval-one'}
        first=self.request('/api/v2/execution/deliveries/delivery_fixture/approve','POST',approval,cookie)
        self.assertEqual(first[0],200);self.assertEqual(self.service.calls[-1][-1],'console_user')
        self.assertEqual(self.request('/api/v2/execution/deliveries/delivery_fixture/approve','POST',approval,cookie)[2],first[2])
        self.server.execution_service=None
        self.assertEqual(self.request('/api/v2/execution/runs/run_fixture',headers=cookie)[0],503)
        self.assertNotIn(b'SECRET',first[2])

class ActualServiceFacadeTests(unittest.TestCase):
    def test_real_observation_admission_approval_separation_and_replay(self):
        from tests.integration.test_worker_service import PublicationServiceTests
        from web_execution import handle_request
        fixture=PublicationServiceTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        service=fixture.service(fixture.adapter())
        with fixture.store._db(True) as db:
            db.execute('DELETE FROM publication_approvals');db.execute('DELETE FROM operation_evidence');db.execute('DELETE FROM runtime_deliveries')
        route='/api/v2/execution/deliveries/d'
        observed=handle_request('POST',route+'/observe',{},dict(run_id=fixture.run,expected_version=1),service,policy=fixture.policy)
        admitted=handle_request('POST',route+'/admit',{},dict(run_id=fixture.run,expected_version=1,observation_id=observed['observation_id']),service,policy=fixture.policy)
        self.assertIsNone(fixture.store.get_publication_approval('d'))
        self.assertEqual(admitted['id'],'d');self.assertEqual(admitted['state'],'queued')
        approval=dict(expected_version=admitted['version'],context_hash=admitted['context_hash'],request_key='web-approval')
        first=handle_request('POST',route+'/approve',{},approval,service,policy=fixture.policy,actor='console_user')
        self.assertEqual(first['id'],'d');self.assertEqual(first['version'],admitted['version']+1)
        self.assertEqual(first,handle_request('POST',route+'/approve',{},approval,service,policy=fixture.policy,actor='console_user'))
        self.assertNotIn('nonce',json.dumps(first));self.assertNotIn('approval_hash',first)

class ActualServiceHTTPTests(unittest.TestCase):
    request=server_fixture.WebServerTests.request
    def test_actual_a8_service_through_http_preserves_separate_approval(self):
        import threading
        from tests.integration.test_worker_service import PublicationServiceTests
        fixture=PublicationServiceTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        service=fixture.service(fixture.adapter())
        with fixture.store._db(True) as db:
            db.execute('DELETE FROM publication_approvals');db.execute('DELETE FROM operation_evidence');db.execute('DELETE FROM runtime_deliveries')
        self.server=server_module.create_server(source_root=fixture.store.locks.paths.root,workspace_root=fixture.store.root,web_root=APP/'web',auth_backend=A9Auth(),execution_service=service)
        thread=threading.Thread(target=self.server.serve_forever,daemon=True);thread.start()
        self.addCleanup(lambda:(self.server.shutdown(),self.server.server_close(),thread.join()))
        _,headers,_=self.request('/api/auth/login','POST',{'password':'fixture-password'});cookie={'Cookie':headers['Set-Cookie'].split(';')[0]}
        route='/api/v2/execution/deliveries/d'
        status,_,raw=self.request(route+'/observe','POST',{'run_id':fixture.run,'expected_version':1},cookie);self.assertEqual(status,200);observed=json.loads(raw)
        status,_,raw=self.request(route+'/admit','POST',{'run_id':fixture.run,'expected_version':1,'observation_id':observed['observation_id']},cookie);self.assertEqual(status,200);admitted=json.loads(raw)
        self.assertIsNone(fixture.store.get_publication_approval('d'))
        approval={'expected_version':admitted['version'],'context_hash':admitted['context_hash'],'request_key':'http-approval'}
        status,_,raw=self.request(route+'/approve','POST',approval,cookie);self.assertEqual(status,200);first=json.loads(raw)
        self.assertEqual(first['id'],'d');self.assertEqual(self.request(route+'/approve','POST',approval,cookie)[2],raw)
