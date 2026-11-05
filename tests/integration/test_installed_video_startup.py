"""고정 제작기 설정에서 실제 재사용 승인자를 조립하되 렌더·기동은 하지 않는다."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from tests.integration import test_video_startup as fixture
from common.operations.bootstrap_config import BootstrapConfig
from common.operations.installed_video_startup import load_installed_video_settings,build_installed_video_registration,InstalledVideoSettings
from common.operations.models import ContractError
from common.operations.video_startup import VideoRegistration


class InstalledVideoStartupTests(unittest.TestCase):
    setUp=fixture.VideoStartupTests.setUp
    args=fixture.VideoStartupTests.args
    dependencies=fixture.VideoStartupTests.dependencies
    video_dependencies=fixture.VideoStartupTests.video_dependencies
    registration=fixture.VideoStartupTests.registration

    def settings_file(self,**changes):
        path=self.root/'video.json'
        path.write_text(json.dumps(dict(schema_version=1,template_id='SurveyShort',enabled=False,
            template_hash='a'*64,font_sha256='b'*64,**changes)))
        return path

    def test_exact_settings_and_disabled_build_do_not_construct_native(self):
        path=self.settings_file();settings=load_installed_video_settings(path);calls=[]
        config=BootstrapConfig(code_root=self.root,source_root=self.root/'source',workspace_root=self.root/'managed')
        with self.assertRaises(ContractError):build_installed_video_registration(config=config,settings=settings,installed_factory=lambda *a,**k:calls.append(k))
        self.assertEqual(calls,[]);self.assertFalse(config.workspace_root.exists())

    def test_unknown_settings_cannot_inject_commands_paths_or_flags(self):
        for change in ({'command':'run'},{'font_path':'/private/other'},{'enabled':'true'},{'template_id':'other'},{'schema_version':True}):
            path=self.root/'bad.json';path.write_text(json.dumps({**dict(schema_version=1,template_id='SurveyShort',enabled=True,template_hash='a'*64,font_sha256='b'*64),**change}))
            with self.assertRaises(ContractError):load_installed_video_settings(path)

    def test_duplicate_enabled_keys_cannot_silently_override_activation(self):
        path=self.root/'duplicate.json'
        raw=json.dumps(dict(schema_version=1,template_id='SurveyShort',enabled=False,
            template_hash='a'*64,font_sha256='b'*64))
        path.write_text(raw[:-1]+', "enabled": true}')
        with self.assertRaises(ContractError):load_installed_video_settings(path)
        self.assertFalse((self.root/'managed').exists())

    def test_fixed_registration_has_real_manual_authorizer_and_deferred_review(self):
        calls=[]
        class Installed:
            def __init__(self,root,**pins):calls.append(('construct',root,pins))
            def verify(self):calls.append('verify');return {'verified':True}
            def create_registration(self,**parts):
                calls.append(('parts',parts))
                return VideoRegistration(lambda **kw:None,parts['reuse_authorization'],parts['probe'],parts['inspect_video'],parts['defer_video_review'])
        config=BootstrapConfig(code_root=self.root,source_root=self.root/'source',workspace_root=self.root/'managed')
        result=build_installed_video_registration(config=config,settings=InstalledVideoSettings(True,'a'*64,'b'*64),installed_factory=Installed)
        self.assertTrue(result.defer_video_review)
        self.assertEqual(result.reuse_authorization.__class__.__name__,'ManagedReuseAuthorizer')
        self.assertEqual(result.inspect_video(),{})
        self.assertFalse(config.workspace_root.exists());self.assertEqual(calls[1],'verify')

    def test_cli_explicit_config_is_checked_before_runtime_and_never_auto_enables(self):
        calls,deps,_=self.video_dependencies();path=self.settings_file()
        module=fixture.fixture.module
        result=module.run(self.args('--check','--video-config',str(path)),**deps)
        self.assertFalse(result['video_enabled']);self.assertEqual(calls,[])
        with self.assertRaises(ContractError):module.run(self.args('--serve','--enable-video','--video-config',str(path)),**deps)
        self.assertEqual(calls,[])

    def test_enabled_cli_builds_registration_then_uses_existing_lifecycle(self):
        calls,deps,_=self.video_dependencies();path=self.root/'enabled.json'
        path.write_text(json.dumps(dict(schema_version=1,template_id='SurveyShort',enabled=True,template_hash='a'*64,font_sha256='b'*64)))
        module=fixture.fixture.module;registration=self.registration(calls)
        with patch.object(module,'build_installed_video_registration',return_value=registration) as builder:
            result=module.run(self.args('--serve','--enable-video','--video-config',str(path)),**deps)
        self.assertTrue(result['video_enabled']);self.assertFalse(result['execution_enabled'])
        self.assertTrue(builder.call_args.kwargs['settings'].enabled)
        self.assertLess(calls.index('initialize'),calls.index('serve'))
