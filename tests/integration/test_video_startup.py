"""영상 활성화는 명시 옵션과 신뢰된 등록을 모두 요구한다. 실행기는 전부 가짜다."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from tests.integration import test_production_main as fixture
from common.operations.bootstrap_config import BootstrapConfig
from common.operations.content_store import ContentStore
from common.operations.models import ContractError
from common.operations.video_startup import VideoRegistration,build_video_task_service


class VideoStartupTests(unittest.TestCase):
    setUp=fixture.MainTests.setUp
    args=fixture.MainTests.args
    settings=fixture.MainTests.settings
    active_args=fixture.MainTests.active_args
    dependencies=fixture.MainTests.dependencies

    def registration(self,calls):
        def guarded(**kwargs):
            calls.append('unexpected-native')
            self.fail('기동 조립 단계에서 제작기·검사기를 호출하면 안 됨')
        return VideoRegistration(guarded,guarded,guarded,guarded)

    def video_dependencies(self):
        calls,deps=self.dependencies();base=deps['runtime_builder']
        content=ContentStore(self.root/'managed')
        def runtime(**kwargs):
            value=base(**kwargs);value.service.store=SimpleNamespace(content_store=content);return value
        deps['runtime_builder']=runtime
        return calls,deps,content

    def test_registration_and_disabled_build_are_inert(self):
        calls=[];registration=self.registration(calls)
        self.assertIsNone(build_video_task_service(config=None,content_store=None,registration=registration))
        config=BootstrapConfig(source_root=self.root/'source',workspace_root=self.root/'managed',registry_path=self.registry)
        content=ContentStore(config.workspace_root)
        result=build_video_task_service(config=config,content_store=content,registration=registration,activate=True)
        self.assertTrue(result.enabled);self.assertIs(result.content_store,content)
        self.assertFalse(config.workspace_root.exists());self.assertEqual(calls,[])

    def test_partial_registration_and_foreign_content_store_are_rejected(self):
        config=BootstrapConfig(source_root=self.root/'source',workspace_root=self.root/'managed',registry_path=self.registry)
        for registration in (None,{},VideoRegistration(lambda:None,None,lambda:None,lambda:None)):
            with self.assertRaises(ContractError):build_video_task_service(config=config,content_store=ContentStore(config.workspace_root),registration=registration,activate=True)
        with self.assertRaises(ContractError):build_video_task_service(config=config,content_store=ContentStore(self.root/'other'),registration=self.registration([]),activate=True)
        self.assertFalse(config.workspace_root.exists())

    def test_check_ignores_registration_and_default_serve_omits_video(self):
        calls,deps,_=self.video_dependencies();registration=self.registration(calls)
        before=list(self.root.rglob('*'))
        summary=fixture.module.run(self.args('--check'),video_registration=registration,**deps)
        self.assertFalse(summary['video_enabled']);self.assertEqual(calls,[]);self.assertEqual(before,list(self.root.rglob('*')))
        result=fixture.module.run(self.args('--serve'),video_registration=registration,**deps)
        self.assertFalse(result['video_enabled'])
        application=next(value for key,value in (row for row in calls if isinstance(row,tuple)) if key=='application')
        self.assertNotIn('video_task_service',application)

    def test_invalid_activation_is_rejected_before_native_or_runtime(self):
        for args in (self.args('--enable-video'),self.args('--serve','--enable-video'),
                     self.args('--serve','--enable-video','--enable-production','--claude-executable','/fixture/claude','--claude-home','/fixture/home','--claude-user','fixture')):
            calls,deps,_=self.video_dependencies()
            with self.assertRaises(ContractError):fixture.module.run(args,**deps)
            self.assertEqual(calls,[])

    def test_video_only_service_is_explicit_and_text_remains_disabled(self):
        calls,deps,content=self.video_dependencies()
        result=fixture.module.run(self.args('--serve','--enable-video'),video_registration=self.registration(calls),**deps)
        application=next(row[1] for row in calls if isinstance(row,tuple) and row[0]=='application')
        service=application['video_task_service']
        self.assertIs(service.content_store,content);self.assertTrue(service.enabled)
        self.assertTrue(result['video_enabled']);self.assertFalse(result['execution_enabled']);self.assertFalse(result['native_probe_performed'])
        self.assertNotIn('runner',calls);self.assertNotIn('quota',calls);self.assertNotIn('unexpected-native',calls)
        self.assertLess(calls.index('initialize'),calls.index('serve'))
        self.assertNotIn(str(self.root),json.dumps(result))

    def test_text_and_video_startup_can_be_enabled_independently(self):
        self.settings();calls,deps,_=self.video_dependencies();args=self.active_args();args.enable_video=True
        result=fixture.module.run(args,video_registration=self.registration(calls),**deps)
        self.assertTrue(result['video_enabled']);self.assertTrue(result['execution_enabled']);self.assertIn('verify',calls)
        self.assertNotIn('unexpected-native',calls)
