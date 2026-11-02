"""저장된 개인·학과 음성 설정은 명시 기동에서만 계정 facade로 조립한다."""
import json
from types import SimpleNamespace
import unittest
from tests.integration import test_voicebox_startup as fixture
from common.operations.account_voice_service import AccountVoiceTaskService
from common.operations.content_store import ContentStore
from common.operations.models import ContractError
from common.operations.voice_settings import VoiceSettingsStore
from common.operations.voice_tasks import VoiceTaskService

class AccountVoiceStartupTests(unittest.TestCase):
    setUp=fixture._MAIN.setUp
    args=fixture._MAIN.args
    dependencies=fixture._MAIN.dependencies
    def saved_settings(self,personal='profile_personal_A',dept='profile_dept_B'):
        store=VoiceSettingsStore(self.root/'managed');store.initialize()
        for account,profile in (('personal',personal),('dept',dept)):
            store.save(account,0,dict(enabled_preference=profile is not None,profile_id=profile))
        return store
    def account_dependencies(self):
        calls,deps=self.dependencies();base=deps['runtime_builder'];content=ContentStore(self.root/'managed')
        def runtime(**kwargs):
            value=base(**kwargs);value.service.store=SimpleNamespace(content_store=content);return value
        class Client:
            def __init__(self,profile_id,**kwargs):calls.append(('client',profile_id,kwargs));self.profile_id=profile_id
            def ready(self):raise AssertionError('기동 조립 중 readiness 조회 금지')
            def generate(self,**kwargs):raise AssertionError('기동 조립 중 합성 금지')
        deps.update(runtime_builder=runtime,voice_client_factory=Client)
        return calls,deps,content
    def application(self,calls):return next(row[1] for row in calls if isinstance(row,tuple) and row[0]=='application')
    def test_explicit_startup_assembles_account_bound_real_services_without_io(self):
        settings=self.saved_settings();before=list(self.root.rglob('*'));calls,deps,content=self.account_dependencies()
        result=fixture.module.run(self.args('--serve','--enable-voicebox','--voicebox-port','18000'),**deps)
        facade=self.application(calls)['voice_task_service']
        self.assertIsInstance(facade,AccountVoiceTaskService);self.assertIs(facade.content_store,content)
        self.assertEqual(set(facade.services),{'personal','dept'})
        for account,profile in (('personal','profile_personal_A'),('dept','profile_dept_B')):
            service=facade.services[account];self.assertIsInstance(service,VoiceTaskService)
            self.assertIs(service.store,facade.store);self.assertIs(service.content_store,content)
            self.assertEqual(service.profile_id,profile);self.assertEqual(service.client.profile_id,profile);self.assertTrue(service.enabled)
        self.assertEqual([row[1] for row in calls if isinstance(row,tuple) and row[0]=='client'],['profile_personal_A','profile_dept_B'])
        self.assertEqual(before,list(self.root.rglob('*')));self.assertEqual(settings.get('personal')['revision'],1)
        self.assertTrue(result['voicebox_enabled']);self.assertFalse(result['execution_enabled']);self.assertFalse(result['native_probe_performed'])
        self.assertNotIn('profile_personal_A',json.dumps(result));self.assertNotIn('runner',calls);self.assertNotIn('verify',calls)
        self.assertLess(calls.index('initialize'),calls.index('serve'))
    def test_enabled_saved_settings_do_not_enable_check_or_default_serve(self):
        self.saved_settings();calls,deps,_=self.account_dependencies();before=list(self.root.rglob('*'))
        result=fixture.module.run(self.args('--check'),**deps)
        self.assertFalse(result['voicebox_enabled']);self.assertEqual(calls,[]);self.assertEqual(before,list(self.root.rglob('*')))
        result=fixture.module.run(self.args('--serve'),**deps)
        self.assertFalse(result['voicebox_enabled']);self.assertNotIn('voice_task_service',self.application(calls))
        self.assertFalse([row for row in calls if isinstance(row,tuple) and row[0]=='client'])
    def test_no_enabled_account_settings_rejected_before_runtime(self):
        for initialize in (False,True):
            if initialize:self.saved_settings(None,None)
            calls,deps,_=self.account_dependencies();before=list(self.root.rglob('*'))
            with self.assertRaises(ContractError) as caught:fixture.module.run(self.args('--serve','--enable-voicebox'),**deps)
            self.assertEqual(caught.exception.code,'voicebox_profile_required');self.assertEqual(calls,[]);self.assertEqual(before,list(self.root.rglob('*')))
    def test_explicit_legacy_profile_overrides_saved_accounts_and_keeps_common_service(self):
        self.saved_settings();calls,deps,content=self.account_dependencies()
        result=fixture.module.run(self.args('--serve','--enable-voicebox','--voicebox-profile-id','legacy_voice'),**deps)
        service=self.application(calls)['voice_task_service']
        self.assertIsInstance(service,VoiceTaskService);self.assertNotIsInstance(service,AccountVoiceTaskService)
        self.assertIs(service.content_store,content);self.assertEqual(service.profile_id,'legacy_voice');self.assertTrue(service.enabled)
        self.assertEqual([row[1] for row in calls if isinstance(row,tuple) and row[0]=='client'],['legacy_voice'])
        self.assertTrue(result['voicebox_enabled'])
    def test_single_enabled_account_has_no_fallback_for_other_account(self):
        self.saved_settings('only_personal',None);calls,deps,_=self.account_dependencies()
        fixture.module.run(self.args('--serve','--enable-voicebox'),**deps)
        facade=self.application(calls)['voice_task_service'];self.assertEqual(set(facade.services),{'personal'})
        self.assertFalse(facade.capabilities('dept')['execution_enabled']);self.assertTrue(facade.capabilities('personal')['execution_enabled'])
