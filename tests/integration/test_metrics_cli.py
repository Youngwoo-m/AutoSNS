"""성과 수집 CLI의 명시 활성화·기동 조립. 소켓·자격·실 API 없이 검증한다."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from common.operations.metrics_store import MetricsStore
from common.operations.models import ContractError
from tests.integration import test_production_main as fixture

module=fixture.module


class MetricsCLITests(unittest.TestCase):
    setUp=fixture.MainTests.setUp
    args=fixture.MainTests.args

    def settings_file(self,enabled=True,connection_ids=None):
        path=self.root/'metrics.json'
        path.write_text(json.dumps(dict(schema_version=1,enabled=enabled,connection_ids=['dept.youtube'] if connection_ids is None else connection_ids)))
        return path

    def dependencies(self):
        calls=[]
        def forbidden(*args,**kwargs):self.fail('자격·외부 수집·native 실행 금지')
        locks=SimpleNamespace(hold=forbidden)
        store=SimpleNamespace(root=self.root/'managed')
        runtime=SimpleNamespace(service=SimpleNamespace(store=store,locks=locks))
        def build_runtime(**kwargs):calls.append(('runtime',kwargs));return runtime
        class App:
            state='built'
            def initialize_storage(self):calls.append('initialize')
            def serve_forever(self):calls.append('serve');self.state='closed'
            def close(self):calls.append('close');self.state='closed'
            def request_shutdown(self):calls.append('stop')
        def application(**kwargs):calls.append(('application',kwargs));return App()
        return calls,dict(runtime_builder=build_runtime,application_builder=application),runtime,locks,forbidden

    def test_check_ignores_enabled_config_and_does_not_construct_collection_service(self):
        path=self.settings_file();calls,deps,_,_,factory=self.dependencies();before=list(self.root.rglob('*'))
        with patch.object(module,'build_metrics_collection_service',side_effect=AssertionError('builder called')):
            result=module.run(self.args('--check','--metrics-config',str(path)),metrics_services_factory=factory,**deps)
        self.assertFalse(result['metrics_enabled']);self.assertFalse(result['execution_enabled'])
        self.assertEqual(calls,[]);self.assertEqual(list(self.root.rglob('*')),before)

    def test_default_serve_omits_metrics_service_even_if_config_is_enabled(self):
        path=self.settings_file();calls,deps,_,_,factory=self.dependencies()
        with patch.object(module,'build_metrics_collection_service',side_effect=AssertionError('builder called')):
            result=module.run(self.args('--serve','--metrics-config',str(path)),metrics_services_factory=factory,**deps)
        app=next(item[1] for item in calls if isinstance(item,tuple) and item[0]=='application')
        self.assertNotIn('metrics_collection_service',app);self.assertFalse(result['metrics_enabled'])
        self.assertLess(calls.index('initialize'),calls.index('serve'));self.assertFalse((self.root/'managed').exists())

    def test_activation_requires_serve_and_enabled_configuration_before_runtime(self):
        path=self.settings_file(enabled=False)
        for args in (self.args('--enable-metrics'),self.args('--serve','--enable-metrics','--metrics-config',str(path))):
            calls,deps,_,_,factory=self.dependencies()
            with patch.object(module,'build_metrics_collection_service',side_effect=AssertionError('builder called')):
                with self.assertRaises(ContractError):module.run(args,metrics_services_factory=factory,**deps)
            self.assertEqual(calls,[])
        self.assertFalse((self.root/'managed').exists())

    def test_enabled_configuration_binds_server_dependencies_before_storage_and_serve(self):
        path=self.settings_file();calls,deps,runtime,locks,factory=self.dependencies();sentinel=object()
        def build(**kwargs):calls.append(('metrics',kwargs));return sentinel
        with patch.object(module,'build_metrics_collection_service',side_effect=build) as builder:
            result=module.run(self.args('--serve','--enable-metrics','--metrics-config',str(path)),metrics_services_factory=factory,**deps)
        self.assertTrue(result['metrics_enabled']);self.assertFalse(result['execution_enabled']);self.assertFalse(result['native_probe_performed'])
        self.assertEqual(builder.call_count,1);bound=builder.call_args.kwargs
        self.assertEqual(bound['config'].workspace_root,(self.root/'managed').resolve())
        self.assertEqual(bound['registry'].revision,'fixture');self.assertIs(bound['runtime_store'],runtime.service.store)
        self.assertIsInstance(bound['metrics_store'],MetricsStore);self.assertEqual(bound['metrics_store'].root,(self.root/'managed').resolve())
        self.assertFalse(bound['metrics_store']._initialized);self.assertIs(bound['locks'],locks)
        self.assertEqual(tuple(bound['connection_ids']),('dept.youtube',));self.assertIs(bound['services_factory'],factory);self.assertIs(bound['activate'],True)
        app=next(item[1] for item in calls if isinstance(item,tuple) and item[0]=='application')
        self.assertIs(app['metrics_collection_service'],sentinel)
        metrics_index=next(i for i,item in enumerate(calls) if isinstance(item,tuple) and item[0]=='metrics')
        self.assertLess(metrics_index,calls.index('initialize'));self.assertLess(calls.index('initialize'),calls.index('serve'))
        self.assertFalse((self.root/'managed').exists())
