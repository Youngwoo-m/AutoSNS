"""이미지 CLI 선택·등록은 명시적이며 기동 조립에서 native 호출은 없다."""
import json
from types import SimpleNamespace
import unittest
from tests.integration import test_production_main as fixture
from common.operations.content_store import ContentStore
from common.operations.image_startup import ImageRegistration
from common.operations.models import ContractError

class ImageCliTests(unittest.TestCase):
    setUp=fixture.MainTests.setUp
    args=fixture.MainTests.args
    dependencies=fixture.MainTests.dependencies
    settings=fixture.MainTests.settings
    active_args=fixture.MainTests.active_args
    def image_dependencies(self):
        calls,deps=self.dependencies();base=deps['runtime_builder'];content=ContentStore(self.root/'managed')
        def runtime(**kwargs):
            value=base(**kwargs);value.service.store=SimpleNamespace(content_store=content);return value
        deps['runtime_builder']=runtime
        return calls,deps,content
    def registration(self,calls):
        def runner(*a,**kw):calls.append('unexpected-native');self.fail('기동에서 렌더 호출 금지')
        return ImageRegistration(runner)
    def test_check_ignores_registration_and_default_serve_omits_images(self):
        calls,deps,_=self.image_dependencies();registration=self.registration(calls);before=list(self.root.rglob('*'))
        result=fixture.module.run(self.args('--check'),image_registration=registration,**deps)
        self.assertFalse(result['images_enabled']);self.assertEqual(calls,[]);self.assertEqual(before,list(self.root.rglob('*')))
        result=fixture.module.run(self.args('--serve'),image_registration=registration,**deps)
        self.assertFalse(result['images_enabled']);application=next(r[1] for r in calls if isinstance(r,tuple) and r[0]=='application')
        self.assertNotIn('image_task_service',application);self.assertNotIn('unexpected-native',calls)
    def test_invalid_image_activation_rejected_before_runtime(self):
        for flags,registration in ((('--enable-images',),self.registration([])),(('--serve','--enable-images'),None),(('--serve','--enable-images'),{}),(('--serve','--enable-images'),ImageRegistration(None))):
            calls,deps,_=self.image_dependencies()
            with self.assertRaises(ContractError):fixture.module.run(self.args(*flags),image_registration=registration,**deps)
            self.assertEqual(calls,[])
    def test_explicit_images_only_builds_service_without_native_text_or_publish(self):
        calls,deps,content=self.image_dependencies()
        result=fixture.module.run(self.args('--serve','--enable-images'),image_registration=self.registration(calls),**deps)
        application=next(r[1] for r in calls if isinstance(r,tuple) and r[0]=='application');service=application['image_task_service']
        self.assertIs(service.content_store,content);self.assertTrue(service.enabled);self.assertTrue(result['images_enabled'])
        self.assertFalse(result['execution_enabled']);self.assertFalse(result['native_probe_performed'])
        self.assertNotIn('runner',calls);self.assertNotIn('verify',calls);self.assertNotIn('quota',calls);self.assertNotIn('unexpected-native',calls)
        self.assertLess(calls.index('initialize'),calls.index('serve'));self.assertNotIn(str(self.root),json.dumps(result))
    def test_image_and_text_activation_are_independent(self):
        self.settings();calls,deps,content=self.image_dependencies();args=self.active_args();args.enable_images=True
        result=fixture.module.run(args,image_registration=self.registration(calls),**deps)
        self.assertTrue(result['images_enabled']);self.assertTrue(result['execution_enabled']);self.assertNotIn('unexpected-native',calls)
