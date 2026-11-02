"""실제 임시 콘텐츠/작업 저장소와 가짜 렌더 결과의 HTTP 연결 시험."""
import hashlib
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from tests import test_web_server as server_fixture
from tests.test_web_execution_server import server_module,APP,NoSocketServer
from tests.operations import test_media_plans as media_fixture
from common.operations.video_tasks import VideoTaskStore,VideoTaskService


class VideoHTTPTests(unittest.TestCase):
    request=server_fixture.WebServerTests.request
    login=server_fixture.WebServerTests.login
    make_content=media_fixture.MediaPlanTests.make_content
    ready_plan=media_fixture.MediaPlanTests.ready_plan

    def setUp(self):
        media_fixture.MediaPlanTests.setUp(self)
        self.item,images,voice=self.make_content();self.plans.initialize()
        self.record=self.plans.save(self.item['id'],self.item['revision'],0,self.ready_plan(images,voice))
        self.store=VideoTaskStore(self.root);self.store.initialize()
        self.service=VideoTaskService(self.store,self.contents,self.plans,enabled=True,runner_factory=lambda **kwargs:None)
        self.service.reuse_authorization=lambda **kw:dict(authorized=True,reviewed=True,**{key:kw['manifest'][key] for key in ('sha256','source','reuse_request_id')})
        self.server=server_module.create_server(source_root=self.root.parent/'source',workspace_root=self.root,
            web_root=APP/'web',auth_backend=server_fixture.FakeAuth(),video_task_service=self.service)
        thread=threading.Thread(target=self.server.serve_forever,daemon=True);thread.start()
        self.addCleanup(lambda:(self.server.shutdown(),self.server.server_close(),thread.join()))
        self.route='/api/v2/contents/'+self.item['id']+'/video-tasks'
        self.body=dict(expected_revision=self.item['revision'],expected_plan_revision=1)

    def test_auth_schema_origin_and_default_disabled(self):
        self.assertEqual(self.request(self.route,'POST',self.body)[0],401)
        cookie=self.login()
        self.assertEqual(self.request(self.route,'POST',self.body,{**cookie,'Origin':'https://evil.example'})[0],403)
        for field in ('owner_account_id','runner','output_path','approved'):
            self.assertEqual(self.request(self.route,'POST',{**self.body,field:'injected'},cookie)[0],400)
        self.assertEqual(self.store.list_for_content(self.item['id']),[])
        self.server.video_task_service=None
        self.assertEqual(self.request(self.route,'POST',self.body,cookie)[0],503)
        caps=json.loads(self.request('/api/v2/video/capabilities',headers=cookie)[2])
        self.assertFalse(caps['execution_enabled']);self.assertFalse(caps['service_available'])

    def test_http_queues_only_and_explicit_worker_registers_one_new_version(self):
        cookie=self.login()
        status,_,raw=self.request(self.route,'POST',self.body,cookie)
        self.assertEqual(status,200);queued=json.loads(raw);self.assertEqual(queued['state'],'queued')
        self.assertFalse((self.root/'media-artifacts').exists())
        calls=[]
        def render(prepared,**kwargs):
            calls.append(prepared)
            path=prepared.artifact_root/'short.mp4';data=b'0000ftypisomfixture';path.write_bytes(data)
            evidence=dict(kind='remotion_video',probe=dict(seconds=15,width=1080,height=1920,has_audio=True),
                audio_checked=True,font_checked=True,disclosure='AI 합성 음성',scenes=[dict(checked=True)])
            evidence['inputs']=[dict(asset_id=asset.asset_id,path=asset.path,sha256=asset.sha256,source=asset.source,
                origin='reuse',reuse_request_id=asset.reuse_request_id) for asset in prepared.scene_assets.values()]
            return dict(status='completed',assets=[dict(path=str(path),filename=path.name,media_type='video/mp4',
                size=len(data),sha256=hashlib.sha256(data).hexdigest(),evidence=evidence)])
        with patch('common.operations.video_tasks.render_prepared_short',side_effect=render):
            self.service.run_next();self.assertIsNone(self.service.run_next())
        route='/api/v2/video-tasks/'+queued['task_id']
        status,_,raw=self.request(route,headers=cookie);self.assertEqual(status,200)
        completed=json.loads(raw);self.assertEqual(completed['state'],'completed');self.assertEqual(completed['review_status'],'not_checked')
        self.assertEqual(completed['output_revision'],self.item['revision']+1)
        self.assertEqual(json.loads(self.request(self.route,'POST',self.body,cookie)[2]),completed)
        self.assertEqual(json.loads(self.request(route+'/resume','POST',{},cookie)[2]),completed)
        self.assertEqual(len(calls),1)
        self.assertEqual(len(self.contents.get(self.item['id'])['assets']),len(self.item['assets'])+1)
        self.assertEqual(self.contents.get(self.item['id'],self.item['revision']),self.item)
        listed=self.request(self.route+'?revision='+str(self.item['revision']),headers=cookie)
        self.assertEqual(json.loads(listed[2])['items'],[completed])
        self.assertNotIn(str(self.root).encode(),listed[2]);self.assertNotIn(b'manifest_hash',listed[2])

    def test_plan_conflict_and_foreign_store_fail_before_execution(self):
        cookie=self.login()
        self.assertEqual(self.request(self.route,'POST',{**self.body,'expected_plan_revision':2},cookie)[0],409)
        other=VideoTaskService(VideoTaskStore(self.root.parent/'other'),self.contents,self.plans,
            enabled=True,runner_factory=lambda **kwargs:None)
        with patch.object(server_module,'_WebServer',NoSocketServer),self.assertRaises(ValueError):
            server_module.create_server(source_root=self.root.parent/'source',workspace_root=self.root,
                web_root=APP/'web',auth_backend=server_fixture.FakeAuth(),video_task_service=other)
