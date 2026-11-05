"""명시 application 기동→HTTP 대기열→worker→검사→새 버전 등록. leaf만 가짜다."""
import json
from pathlib import Path
import threading
import unittest
from tests import test_web_server as web_fixture
from tests.operations import test_video_tasks as media_fixture
from tests.integration import test_production_application as app_fixture
from common.operations.bootstrap_config import BootstrapConfig
from common.operations.execution_catalog import ExecutionCatalog
from common.operations.production_startup import build_production_runtime
from common.operations.registry import load_registry
from common.operations.video_startup import VideoRegistration,build_video_task_service
from common.operations.video_worker import VideoTaskWorker


class VideoWorkbenchHTTPTests(unittest.TestCase):
    request=web_fixture.WebServerTests.request
    login=web_fixture.WebServerTests.login
    make_content=media_fixture.VideoTaskTests.make_content
    ready_plan=media_fixture.VideoTaskTests.ready_plan
    factory=media_fixture.VideoTaskTests.factory
    runner=media_fixture.VideoTaskTests.runner
    authorize=staticmethod(media_fixture.VideoTaskTests.authorize)
    probe=staticmethod(media_fixture.VideoTaskTests.probe)
    inspect=staticmethod(media_fixture.VideoTaskTests.inspect)

    def setUp(self):
        media_fixture.VideoTaskTests.setUp(self)

    def run_workbench(self,owner):
        item,images,voice=self.make_content(owner=owner);self.plans.initialize()
        self.plans.save(item['id'],item['revision'],0,self.ready_plan(images,voice))
        registry_path=self.root.parent/'registry.json'
        registry_path.write_text(json.dumps(dict(schema_version=1,revision='fixture',accounts={'personal':{},'dept':{}})))
        config=BootstrapConfig(code_root=Path(__file__).resolve().parents[2],source_root=self.root.parent/'source',
            workspace_root=self.root,registry_path=registry_path)
        planning=load_registry(registry_path)
        runtime=build_production_runtime(config=config,registry=planning,catalog=ExecutionCatalog(),initialize=False)
        service=build_video_task_service(config=config,content_store=runtime.service.store.content_store,
            registration=VideoRegistration(self.factory,self.authorize,self.probe,self.inspect),activate=True)
        app=app_fixture.production_application.build_production_application(runtime=runtime,config=config,
            planning_registry=planning,port=0,web_root=web_fixture.APP/'web',auth_backend=web_fixture.FakeAuth(),
            video_task_service=service,video_worker_factory=lambda svc:VideoTaskWorker(svc,poll_seconds=.01))
        self.server=app.server;app.initialize_storage();errors=[]
        def serve():
            try:app.serve_forever(join_timeout=3)
            except BaseException as error:errors.append(error)
        thread=threading.Thread(target=serve,daemon=True);thread.start()
        def stop():
            if app.state=='serving':app.request_shutdown()
            elif app.state=='built':app.close()
            thread.join(4)
        self.addCleanup(stop)
        cookie=self.login();route='/api/v2/contents/'+item['id']+'/video-tasks'
        body=dict(expected_revision=item['revision'],expected_plan_revision=1)
        status,_,raw=self.request(route,'POST',body,cookie);self.assertEqual(status,200)
        queued=json.loads(raw);task_route='/api/v2/video-tasks/'+queued['task_id']
        finished=None
        for _ in range(80):
            status,_,raw=self.request(task_route,headers=cookie);self.assertEqual(status,200)
            current=json.loads(raw)
            if current['state']=='completed':finished=current;break
            if current['state'] not in ('queued','preparing','rendering','rendered'):self.fail(str(current))
            threading.Event().wait(.025)
        self.assertIsNotNone(finished,'가짜 leaf 영상의 등록이 기한 안에 끝나야 함')
        self.assertEqual((self.runs,self.factory_calls),(1,1))
        self.assertEqual(finished['review_status'],'not_checked')
        self.assertEqual(finished['output_revision'],item['revision']+1)
        self.assertEqual(self.contents.get(item['id'])['owner_account_id'],owner)
        self.assertEqual(self.contents.get(item['id'],item['revision']),item)
        self.assertEqual(json.loads(self.request(route,'POST',body,cookie)[2]),finished)
        self.assertEqual(self.runs,1)
        stop();self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
        self.assertEqual((app.state,app.video_worker_state,app.worker_state),('closed','stopped','not_started'))

    def test_personal_video_workbench(self):self.run_workbench('personal')
    def test_department_video_workbench(self):self.run_workbench('dept')
