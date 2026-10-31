"""실제 소켓·운영 저장소 없이 검증하는 로컬 도구 기동 설정."""
import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

APP = Path(__file__).resolve().parents[1] / 'ax-console' / 'app'
sys.path.insert(0, str(APP))


class ToolkitStartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('toolkit_startup_fixture', APP / 'web_server.py')
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_environment_policy_is_strict_and_requires_explicit_workspace(self):
        parser = getattr(self.module, '_toolkit_policy_from_env', None)
        self.assertTrue(callable(parser), '기동 환경 정책 해석 함수가 필요합니다')
        for env, enabled in (({}, False), ({'AX_LOCAL_TOOLKIT': '0'}, False),
                             ({'AX_LOCAL_TOOLKIT': '1', 'AX_WORKSPACE_ROOT': '/managed'}, True)):
            with self.subTest(env=env):
                self.assertIs(parser(env).enabled, enabled)
        for value in ('', ' ', '\t', 'true', '2', '01', ' 1', '1 ', 'secret-invalid-value'):
            with self.subTest(value=value), self.assertRaises(SystemExit) as raised:
                parser({'AX_LOCAL_TOOLKIT': value, 'AX_WORKSPACE_ROOT': '/managed'})
            if value.strip():
                self.assertNotIn(value, str(raised.exception))
            self.assertRegex(str(raised.exception), '[가-힣]')
        for workspace in (None, '', ' ', '\t'):
            env = {'AX_LOCAL_TOOLKIT': '1'}
            if workspace is not None:
                env['AX_WORKSPACE_ROOT'] = workspace
            with self.subTest(workspace=workspace), self.assertRaises(SystemExit):
                parser(env)

    def test_invalid_main_configuration_never_reaches_factory(self):
        for value, workspace in (('', '/managed'), (' ', '/managed'), ('true', '/managed'),
                                 ('2', '/managed'), ('1', None), ('1', ''), ('1', ' ')):
            env = {'AX_SOURCE_ROOT': '/source', 'AX_LOCAL_TOOLKIT': value}
            if workspace is not None:
                env['AX_WORKSPACE_ROOT'] = workspace
            with self.subTest(value=value, workspace=workspace), patch.dict(os.environ, env, clear=True), \
                    patch.object(self.module, 'create_server') as factory:
                with self.assertRaises(SystemExit):
                    self.module.main()
                factory.assert_not_called()

    def test_main_injects_only_local_policy_and_closes_server(self):
        # 미설정과 0은 활성 기동 후 옵션 제거/원복도 같은 경계로 검증한다.
        for value, enabled in ((None, False), ('0', False), ('1', True)):
            env = {'AX_SOURCE_ROOT': '/source', 'AX_WORKSPACE_ROOT': '/managed',
                   'AX_OPERATIONS_REGISTRY': '/registry.json', 'AX_HOST': '127.0.0.1', 'AX_PORT': '8769'}
            if value is not None:
                env['AX_LOCAL_TOOLKIT'] = value
            server = Mock(workspace_root=Path('/managed'))
            server.serve_forever.side_effect = KeyboardInterrupt
            with self.subTest(value=value), patch.dict(os.environ, env, clear=True), \
                    patch.object(self.module, 'create_server', return_value=server) as factory:
                self.module.main()
                args, kwargs = factory.call_args
                self.assertEqual(args, ('127.0.0.1', 8769))
                self.assertEqual(set(kwargs), {'source_root', 'web_root', 'workspace_root',
                                               'operations_registry', 'toolkit_policy'})
                self.assertEqual(kwargs['source_root'], Path('/source'))
                self.assertEqual(kwargs['workspace_root'], Path('/managed'))
                self.assertEqual(kwargs['operations_registry'], Path('/registry.json'))
                self.assertEqual(kwargs['web_root'], APP / 'web')
                self.assertIs(kwargs['toolkit_policy'].enabled, enabled)
                for name in ('content_store', 'integration_store', 'ledger', 'runtime_store', 'metrics_store'):
                    getattr(server, name).initialize.assert_called_once_with()
                server.serve_forever.assert_called_once_with()
                server.server_close.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
