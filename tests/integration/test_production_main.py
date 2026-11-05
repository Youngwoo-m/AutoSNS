"""명시 제작 기동 명령. native/모델/소켓은 가짜 의존성으로 검증한다."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from common.operations.models import ContractError
from common.operations.production_settings import ProductionSettingsStore
SPEC=importlib.util.spec_from_file_location('production_main_fixture',Path(__file__).resolve().parents[2]/'ax-console/app/production_main.py')
module=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(module)

class MainTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.registry=self.root/'registry.json'
        self.registry.write_text(json.dumps(dict(schema_version=1,revision='fixture',accounts={'personal':{},'dept':{}})))
        self.base=['--source-root',str(self.root/'source'),'--workspace-root',str(self.root/'managed'),'--registry',str(self.registry)]
    def args(self,*extra):return module.parser().parse_args(self.base+list(extra))
    def settings(self):
        store=ProductionSettingsStore(self.root/'managed');store.initialize()
        store.save('personal',0,dict(enabled_preference=True,daily_limit=2))
    def dependencies(self,verified=True,quota_error=False):
        calls=[]
        class Runner:
            def __init__(self,*args):calls.append('runner')
            def verify(self):calls.append('verify');return {'verified':verified}
        runtime=SimpleNamespace(service=SimpleNamespace(store=object()))
        def build_runtime(**kwargs):calls.append(('runtime',kwargs));return runtime
        class App:
            state='built'
            def initialize_storage(self):calls.append('initialize')
            def serve_forever(self):calls.append('serve');self.state='closed'
            def close(self):calls.append('close');self.state='closed'
            def request_shutdown(self):calls.append('stop')
        app=App()
        def application(**kwargs):calls.append(('application',kwargs));return app
        def quota(*args):
            calls.append('quota')
            if quota_error:raise ContractError('invalid_quota_policy')
        return calls,dict(runner_factory=Runner,runtime_builder=build_runtime,application_builder=application,quota_preparer=quota)
    def active_args(self):return self.args('--serve','--enable-production','--claude-executable','/fixture/claude','--claude-home','/fixture/home','--claude-user','fixture')
    def test_check_default_does_not_initialize_or_construct_native_runtime(self):
        calls,deps=self.dependencies();before=list(self.root.rglob('*'))
        result=module.run(self.args(),**deps)
        self.assertEqual(result['mode'],'check');self.assertFalse(result['execution_enabled'])
        self.assertEqual(calls,[]);self.assertEqual(before,list(self.root.rglob('*')))
    def test_stored_preferences_do_not_enable_check_or_disabled_serve(self):
        self.settings();calls,deps=self.dependencies()
        self.assertFalse(module.run(self.args('--check'),**deps)['execution_enabled']);self.assertEqual(calls,[])
        result=module.run(self.args('--serve'),**deps)
        self.assertFalse(result['execution_enabled']);self.assertNotIn('runner',calls);self.assertNotIn('quota',calls)
        runtime=next(row[1] for row in calls if isinstance(row,tuple) and row[0]=='runtime')
        self.assertFalse(runtime['policy'].enabled);self.assertIsNone(runtime['subscription_runner'])
    def test_active_startup_verifies_then_prepares_quota_then_serves(self):
        self.settings();calls,deps=self.dependencies()
        result=module.run(self.active_args(),**deps)
        self.assertTrue(result['execution_enabled']);self.assertEqual(calls[:2],['runner','verify'])
        self.assertLess(calls.index('initialize'),calls.index('quota'));self.assertLess(calls.index('quota'),calls.index('serve'))
        application=next(row[1] for row in calls if isinstance(row,tuple) and row[0]=='application')
        self.assertEqual(application['planning_registry'].revision,'fixture')
    def test_active_mode_requires_explicit_prepared_account_and_auth(self):
        calls,deps=self.dependencies()
        with self.assertRaises(ContractError):module.run(self.active_args(),**deps)
        self.assertEqual(calls,[])
        self.settings();calls,deps=self.dependencies(verified=False)
        with self.assertRaises(ContractError):module.run(self.active_args(),**deps)
        self.assertEqual(calls,['runner','verify'])
    def test_quota_preparation_failure_closes_without_starting_worker(self):
        self.settings();calls,deps=self.dependencies(quota_error=True)
        with self.assertRaises(ContractError):module.run(self.active_args(),**deps)
        self.assertIn('close',calls);self.assertNotIn('serve',calls)
    def test_invalid_modes_roots_and_hosts_are_rejected_before_native(self):
        for args in (self.args('--enable-production'),self.args('--serve','--enable-production'),self.args('--host','0.0.0.0'),self.args('--port','-1')):
            calls,deps=self.dependencies()
            with self.assertRaises(ContractError):module.run(args,**deps)
            self.assertEqual(calls,[])

    def test_public_origin_check_is_readonly_and_does_not_activate(self):
        calls,deps=self.dependencies();before=list(self.root.rglob('*'))
        result=module.run(self.args('--check','--public-origin','https://console.example.com'),**deps)
        self.assertEqual(result['mode'],'check')
        self.assertFalse(result['execution_enabled'])
        self.assertEqual(calls,[])
        self.assertEqual(before,list(self.root.rglob('*')))

    def test_public_origin_forwarded_only_when_explicit_and_preserves_loopback(self):
        for origin in (None,'https://console.example.com'):
            calls,deps=self.dependencies()
            extra=[] if origin is None else ['--public-origin',origin]
            result=module.run(self.args('--serve',*extra),**deps)
            application=next(row[1] for row in calls if isinstance(row,tuple) and row[0]=='application')
            self.assertEqual(application['host'],'127.0.0.1')
            self.assertFalse(result['execution_enabled'])
            self.assertNotIn('runner',calls)
            self.assertNotIn('quota',calls)
            if origin is None:self.assertNotIn('external_access_policy',application)
            else:self.assertEqual(application['external_access_policy'].origin,origin)

    def test_invalid_public_origins_rejected_in_check_and_serve_before_side_effects(self):
        for mode in ('--check','--serve'):
            for origin in ('http://console.example.com','https://user@console.example.com',
                           'https://127.0.0.1','https://console.example.com:443',
                           'https://console.example.com/path'):
                with self.subTest(mode=mode,origin=origin):
                    calls,deps=self.dependencies();before=list(self.root.rglob('*'))
                    with self.assertRaises(ContractError) as error:
                        module.run(self.args(mode,'--public-origin',origin),**deps)
                    self.assertEqual(error.exception.code,'invalid_external_access_policy')
                    self.assertEqual(calls,[])
                    self.assertEqual(before,list(self.root.rglob('*')))

    def test_tiktok_ffprobe_check_is_format_only_and_default_summary_unchanged(self):
        calls,deps=self.dependencies();before=list(self.root.rglob('*'))
        def forbidden(*args):raise AssertionError('probe must not be constructed in check')
        with patch('subprocess.Popen',side_effect=AssertionError('no native process')),patch('common.operations.tiktok_media_probe.tempfile.TemporaryDirectory',side_effect=AssertionError('no asset temporary files')):
            result=module.run(self.args('--check','--tiktok-ffprobe','/fixture/trusted-ffprobe'),tiktok_probe_factory=forbidden,**deps)
        self.assertTrue(result['tiktok_media_check_configured'])
        self.assertFalse(result['native_probe_performed']);self.assertFalse(result['execution_enabled'])
        self.assertTrue(all(result[key] is False for key in ('voicebox_enabled','video_enabled','images_enabled','metrics_enabled')))
        self.assertEqual(calls,[]);self.assertEqual(before,list(self.root.rglob('*')))
        plain=module.run(self.args('--check'),**deps)
        self.assertNotIn('tiktok_media_check_configured',plain)

    def test_tiktok_ffprobe_serve_constructs_and_forwards_without_inspecting(self):
        calls,deps=self.dependencies();probe=SimpleNamespace(inspect=lambda raw:(_ for _ in ()).throw(AssertionError('must not inspect')))
        factory_calls=[]
        def factory(path):factory_calls.append(path);return probe
        with patch('subprocess.Popen',side_effect=AssertionError('no native process')):
            result=module.run(self.args('--serve','--tiktok-ffprobe','/fixture/trusted-ffprobe'),tiktok_probe_factory=factory,**deps)
        application=next(row[1] for row in calls if isinstance(row,tuple) and row[0]=='application')
        self.assertIs(application['tiktok_media_probe'],probe);self.assertEqual(factory_calls,['/fixture/trusted-ffprobe'])
        self.assertFalse(result['execution_enabled']);self.assertFalse(result['native_probe_performed'])
        self.assertTrue(all(result[key] is False for key in ('voicebox_enabled','video_enabled','images_enabled','metrics_enabled')))
        self.assertNotIn('runner',calls);self.assertNotIn('quota',calls)
        for name in ('voice_task_service','video_task_service','image_task_service','metrics_collection_service'):
            self.assertNotIn(name,application)

    def test_tiktok_ffprobe_default_serve_does_not_add_argument_or_use_environment(self):
        calls,deps=self.dependencies()
        with patch.dict('os.environ',{'TIKTOK_FFPROBE':'/untrusted/environment-probe'}):
            result=module.run(self.args('--serve'),tiktok_probe_factory=lambda _:(_ for _ in ()).throw(AssertionError('no default probe')),**deps)
        application=next(row[1] for row in calls if isinstance(row,tuple) and row[0]=='application')
        self.assertNotIn('tiktok_media_probe',application);self.assertNotIn('tiktok_media_check_configured',result)

    def test_tiktok_ffprobe_relative_path_and_invalid_object_rejected_before_builders(self):
        for mode in ('--check','--serve'):
            calls,deps=self.dependencies()
            with self.assertRaises(ContractError) as error:
                module.run(self.args(mode,'--tiktok-ffprobe','relative/ffprobe'),**deps)
            self.assertEqual(error.exception.code,'invalid_tiktok_media_probe');self.assertEqual(calls,[])
        calls,deps=self.dependencies()
        with self.assertRaises(ContractError) as error:
            module.run(self.args('--serve','--tiktok-ffprobe','/fixture/ffprobe'),tiktok_probe_factory=lambda _:object(),**deps)
        self.assertEqual(error.exception.code,'invalid_tiktok_media_probe');self.assertEqual(calls,[])
