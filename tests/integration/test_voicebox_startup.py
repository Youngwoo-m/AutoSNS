"""명시 Voicebox 기동 옵션. 가짜 factory만 사용하므로 네트워크/합성/실계정 영향이 없다."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from common.operations.models import ContractError
from common.operations.voice_tasks import VoiceTaskStore

# 기존 시험 클래스를 import하지 않고 fixture 함수만 빌려 와 중복 수집을 막는다.
_BASE_PATH=Path(__file__).resolve().parent/'test_production_main.py'
_SPEC=importlib.util.spec_from_file_location('production_main_base_fixture',_BASE_PATH)
_BASE=importlib.util.module_from_spec(_SPEC);_SPEC.loader.exec_module(_BASE)
module=_BASE.module
_MAIN=_BASE.MainTests
PROFILE='profile_A-1'


class VoiceboxStartupTests(unittest.TestCase):
    setUp=_MAIN.setUp;args=_MAIN.args;settings=_MAIN.settings
    dependencies=_MAIN.dependencies;active_args=_MAIN.active_args

    def voice_dependencies(self,**kwargs):
        calls,deps=self.dependencies(**kwargs)
        self.content_store=object();base_builder=deps['runtime_builder']
        def build_runtime(**inner):
            runtime=base_builder(**inner);runtime.service.store=SimpleNamespace(content_store=self.content_store);return runtime
        deps['runtime_builder']=build_runtime
        class Client:
            def __init__(self,profile_id,**options):calls.append(('client',profile_id,options));self.made=self
        def service(store,content_store,client,**options):
            calls.append(('service',store,content_store,client,options));return 'service-sentinel'
        deps.update(voice_client_factory=Client,voice_service_factory=service)
        return calls,deps
    def application(self,calls):return next(row[1] for row in calls if isinstance(row,tuple) and row[0]=='application')
    def voice_args(self,*extra):return self.args('--serve','--enable-voicebox','--voicebox-profile-id',PROFILE,*extra)

    def test_check_never_builds_client_or_touches_disk_even_with_voicebox_options(self):
        calls,deps=self.voice_dependencies();before=list(self.root.rglob('*'))
        result=module.run(self.args('--check','--voicebox-profile-id',PROFILE,'--voicebox-port','18000'),**deps)
        self.assertEqual(result['mode'],'check');self.assertFalse(result['voicebox_enabled'])
        self.assertEqual(calls,[]);self.assertEqual(before,list(self.root.rglob('*')))
        with self.assertRaises(ContractError):module.run(self.args('--check','--enable-voicebox','--voicebox-profile-id',PROFILE),**deps)
        self.assertEqual(calls,[])

    def test_disabled_serve_omits_voice_service_even_when_profile_is_given(self):
        calls,deps=self.voice_dependencies()
        result=module.run(self.args('--serve','--voicebox-profile-id',PROFILE),**deps)
        self.assertFalse(result['voicebox_enabled']);self.assertNotIn('voice_task_service',self.application(calls))
        self.assertFalse([row for row in calls if isinstance(row,tuple) and row[0] in ('client','service')])
        for extra in ((),('--voicebox-port','18000')):  # 기본 형태에서도 kwarg 자체가 없다.
            calls,deps=self.voice_dependencies();module.run(self.args('--serve',*extra),**deps)
            self.assertNotIn('voice_task_service',self.application(calls))

    def test_invalid_voicebox_options_are_rejected_before_any_factory(self):
        cases=[self.args('--enable-voicebox','--voicebox-profile-id',PROFILE),
            self.args('--serve','--enable-voicebox'),
            self.args('--serve','--voicebox-profile-id','bad id'),
            self.args('--serve','--enable-voicebox','--voicebox-profile-id','x'*129),
            self.args('--serve','--enable-voicebox','--voicebox-profile-id',''),
            self.voice_args('--voicebox-port','0'),self.voice_args('--voicebox-port','65536'),
            self.args('--serve','--voicebox-profile-id',PROFILE,'--voicebox-port','-5')]
        boolean=self.voice_args();boolean.voicebox_port=True;cases.append(boolean)
        for args in cases:
            calls,deps=self.voice_dependencies()
            with self.assertRaises(ContractError):module.run(args,**deps)
            self.assertEqual(calls,[])

    def test_voice_only_serve_injects_service_in_order_with_shared_content_store(self):
        self.settings();calls,deps=self.voice_dependencies()
        result=module.run(self.voice_args('--voicebox-port','18000'),**deps)
        self.assertTrue(result['voicebox_enabled']);self.assertFalse(result['execution_enabled'])
        self.assertFalse(result['native_probe_performed']);self.assertNotIn('runner',calls);self.assertNotIn('verify',calls)
        client=next(row for row in calls if isinstance(row,tuple) and row[0]=='client')
        self.assertEqual(client[1:],(PROFILE,{'port':18000}))
        service=next(row for row in calls if isinstance(row,tuple) and row[0]=='service')
        self.assertIsInstance(service[1],VoiceTaskStore)
        self.assertEqual(Path(service[1].root).resolve(),(self.root/'managed').resolve())
        self.assertIs(service[2],self.content_store);self.assertIs(service[3].made,service[3])
        self.assertEqual(service[4],{'profile_id':PROFILE,'enabled':True})
        self.assertEqual(self.application(calls)['voice_task_service'],'service-sentinel')
        names=[row if isinstance(row,str) else row[0] for row in calls]
        self.assertLess(names.index('runtime'),names.index('client'));self.assertLess(names.index('service'),names.index('application'))
        self.assertLess(names.index('application'),names.index('initialize'));self.assertLess(names.index('initialize'),names.index('serve'))

    def test_profile_and_port_are_not_exposed_in_summary(self):
        calls,deps=self.voice_dependencies()
        result=module.run(self.voice_args('--voicebox-port','18123'),**deps)
        text=json.dumps(result,ensure_ascii=False)
        self.assertNotIn(PROFILE,text);self.assertNotIn('18123',text);self.assertNotIn('profile',text)
        self.assertIs(result['voicebox_enabled'],True)
        self.assertEqual(set(module.run(self.args(),**deps)),set(result)-set())

    def test_voicebox_and_text_production_are_independent(self):
        self.settings()
        calls,deps=self.voice_dependencies()
        result=module.run(self.active_args(),**deps)  # 텍스트 제작만: Voicebox 비활성
        self.assertTrue(result['execution_enabled']);self.assertFalse(result['voicebox_enabled'])
        self.assertNotIn('voice_task_service',self.application(calls))
        calls,deps=self.voice_dependencies()
        both=self.args('--serve','--enable-production','--claude-executable','/fixture/claude','--claude-home','/fixture/home',
            '--claude-user','fixture','--enable-voicebox','--voicebox-profile-id',PROFILE)
        result=module.run(both,**deps)
        self.assertTrue(result['execution_enabled']);self.assertTrue(result['voicebox_enabled'])
        self.assertEqual(calls[:2],['runner','verify']);self.assertEqual(self.application(calls)['voice_task_service'],'service-sentinel')
