"""고정 이미지 등록은 설정·설치 검증만 하며 제작·저장소를 실행하지 않는다."""
import json
from pathlib import Path
import tempfile
import unittest
from common.operations.bootstrap_config import BootstrapConfig
from common.operations.image_startup import ImageRegistration
from common.operations.installed_image_startup import InstalledImageSettings,load_installed_image_settings,build_installed_image_registration
from common.operations.models import ContractError

class InstalledImageStartupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.config=BootstrapConfig(code_root=self.root,source_root=self.root/'source',workspace_root=self.root/'managed')
        self.browser=self.root/'browser';self.browser.write_text('fake');self.browser.chmod(0o755)
        self.calls=[]
    def file(self,**changes):
        path=self.root/'config.json';path.write_text(json.dumps({**dict(schema_version=1,template_id='LocalCard',enabled=False,template_hash='a'*64,font_sha256='b'*64,browser_executable=None),**changes}));return path
    def renderer(self,*args,**kwargs):
        calls=self.calls;calls.append((args,kwargs))
        class Renderer:
            def verify(self):calls.append('verify');return dict(verified=True)
            def __call__(self,*a,**k):raise AssertionError('native must not execute during registration')
        return Renderer()
    def test_default_disabled_file_is_inert(self):
        settings=load_installed_image_settings(self.file())
        with self.assertRaises(ContractError):build_installed_image_registration(config=self.config,settings=settings,renderer_factory=self.renderer)
        self.assertEqual(self.calls,[]);self.assertFalse(self.config.workspace_root.exists())
    def test_exact_schema_duplicates_commands_and_bad_browser_rejected(self):
        for change in (dict(command='run'),dict(enabled='true'),dict(template_id='other'),dict(browser_executable='relative'),dict(schema_version=True),dict(template_hash='x'*64)):
            with self.assertRaises(ContractError):load_installed_image_settings(self.file(**change))
        path=self.file();path.write_text(path.read_text()[:-1]+',"enabled":true}')
        with self.assertRaises(ContractError):load_installed_image_settings(path)
        path=self.file();alias=self.root/'alias';alias.symlink_to(path)
        with self.assertRaises(ContractError):load_installed_image_settings(alias)
        path.write_bytes(b'x'*8193)
        with self.assertRaises(ContractError):load_installed_image_settings(path)
    def test_enabled_with_fixed_browser_assembles_only_verified_runner(self):
        settings=load_installed_image_settings(self.file(enabled=True,browser_executable=str(self.browser)))
        registration=build_installed_image_registration(config=self.config,settings=settings,renderer_factory=self.renderer)
        self.assertIsInstance(registration,ImageRegistration)
        self.assertEqual(self.calls[0][1],dict(expected_template_hash='a'*64,expected_font_hash='b'*64,browser_executable=self.browser))
        self.assertEqual(self.calls[1],'verify');self.assertFalse(self.config.workspace_root.exists())
    def test_missing_non_executable_or_symlink_browser_blocks_before_renderer(self):
        for browser in (None,self.root/'missing'):
            with self.assertRaises(ContractError):build_installed_image_registration(config=self.config,settings=InstalledImageSettings(True,'a'*64,'b'*64,browser),renderer_factory=self.renderer)
        self.browser.chmod(0o644)
        with self.assertRaises(ContractError):build_installed_image_registration(config=self.config,settings=InstalledImageSettings(True,'a'*64,'b'*64,str(self.browser)),renderer_factory=self.renderer)
        self.browser.chmod(0o755);alias=self.root/'alias';alias.symlink_to(self.browser)
        with self.assertRaises(ContractError):build_installed_image_registration(config=self.config,settings=InstalledImageSettings(True,'a'*64,'b'*64,str(alias)),renderer_factory=self.renderer)
        self.assertEqual(self.calls,[])
    def test_failed_readonly_renderer_verification_is_not_registered(self):
        class Renderer:
            def __init__(self,*a,**k):pass
            def verify(self):return {'verified':False}
            def __call__(self,*a,**k):raise AssertionError()
        settings=InstalledImageSettings(True,'a'*64,'b'*64,str(self.browser))
        with self.assertRaises(ContractError):build_installed_image_registration(config=self.config,settings=settings,renderer_factory=Renderer)
        self.assertFalse(self.config.workspace_root.exists())
