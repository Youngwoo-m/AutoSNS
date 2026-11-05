"""이미지 제작 기동은 신뢰된 등록·명시 옵션을 요구하며 조립은 무변이다."""
from dataclasses import FrozenInstanceError
from pathlib import Path
import tempfile
import unittest
from common.operations.bootstrap_config import BootstrapConfig
from common.operations.content_store import ContentStore
from common.operations.models import ContractError
from common.operations.image_startup import ImageRegistration,validate_image_registration,build_image_task_service

class ImageStartupTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.config=BootstrapConfig(code_root=self.root/'code',source_root=self.root/'source',workspace_root=self.root/'managed')
        self.content=ContentStore(self.config.workspace_root);self.calls=[]
        def runner(*a,**k):self.calls.append('native');self.fail('조립 중 제작 금지')
        self.registration=ImageRegistration(runner)
    def test_explicit_registration_assembles_without_storage_or_native(self):
        result=build_image_task_service(config=self.config,content_store=self.content,registration=self.registration,activate=True)
        self.assertTrue(result.enabled);self.assertIs(result.content_store,self.content);self.assertIs(result.runner,self.registration.runner)
        self.assertEqual(self.calls,[]);self.assertFalse(self.config.workspace_root.exists())
        self.assertEqual(result.capabilities(),dict(provider_id='local-card',service_available=True,execution_enabled=True,review_status='not_checked'))
        self.assertIs(validate_image_registration(self.registration),self.registration)
        with self.assertRaises(FrozenInstanceError):self.registration.runner=None
    def test_default_inactive_and_nonboolean_activation_fail_without_side_effects(self):
        for activate in (False,None,0,1,'true'):
            with self.assertRaises(ContractError) as caught:
                build_image_task_service(config=self.config,content_store=self.content,registration=self.registration,activate=activate)
            self.assertEqual(caught.exception.code,'image_activation_required')
        self.assertFalse(self.config.workspace_root.exists());self.assertEqual(self.calls,[])
    def test_partial_registration_and_foreign_workspace_fail(self):
        for registration in (None,{},dict(runner=self.registration.runner),ImageRegistration(None),ImageRegistration('/bin/render')):
            with self.assertRaises(ContractError):
                build_image_task_service(config=self.config,content_store=self.content,registration=registration,activate=True)
        for config,content in ((None,self.content),(self.config,None),(self.config,ContentStore(self.root/'other'))):
            with self.assertRaises(ContractError):
                build_image_task_service(config=config,content_store=content,registration=self.registration,activate=True)
        self.assertEqual(self.calls,[]);self.assertFalse(self.config.workspace_root.exists())
    def test_physical_workspace_alias_uses_content_store_spelling(self):
        actual=self.root/'actual';actual.mkdir();alias=self.root/'alias';alias.symlink_to(actual,target_is_directory=True)
        config=BootstrapConfig(workspace_root=alias)
        content=ContentStore(actual)
        result=build_image_task_service(config=config,content_store=content,registration=self.registration,activate=True)
        self.assertEqual(result.store.root,actual);self.assertEqual(list(actual.iterdir()),[]);self.assertEqual(self.calls,[])
