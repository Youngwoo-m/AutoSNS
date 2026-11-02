"""저장 설정→등록부→제작 worker 연결. 외부 공급자와 운영 파일은 사용하지 않는다."""
from pathlib import Path
import sys
import tempfile
import unittest
from common.operations.bootstrap_config import BootstrapConfig
from common.operations.production_settings import ProductionSettingsStore,compile_production_settings
from common.operations.production_startup import build_production_runtime
from common.operations.quota import bucket_id,quota_window
from tests.operations.test_runtime_store import NOW

class CompiledProductionTests(unittest.TestCase):
    def test_saved_account_policy_drives_worker_without_live_configuration_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);settings=ProductionSettingsStore(root/'managed');settings.initialize()
            settings.save('personal',0,dict(enabled_preference=True,daily_limit=3))
            rows=[settings.get(a) for a in ('personal','dept')]
            compiled=compile_production_settings(rows,accounts={'personal':{},'dept':{}},code_root=root,interpreter=Path(sys.executable),activate=True)
            calls=[]
            class Provider:
                def generate(self,request,prompt,policy):
                    calls.append(request.owner_account_id)
                    return dict(status='completed',text='완성 원고',provider_id='claude-subscription',execution_id='fixture-only',observed_usage=None)
            config=BootstrapConfig(code_root=root,source_root=root/'source',workspace_root=root/'managed',registry_path=root/'unused')
            runtime=build_production_runtime(config=config,registry=compiled.registry,catalog=compiled.catalog,policy=compiled.policy,
                producers={'managed-text-personal':{'provider':Provider(),'media_runner':{}}},initialize=True,clock=lambda:NOW)
            store=runtime.service.store;content=store.content_store.create('personal',dict(title='기획',kind='article',original='입력'))
            requirement=next(iter(compiled.registry.policies.values()))['quota_requirements'][0]
            start,end=quota_window(requirement,NOW)
            store.observe_bucket(bucket_id('owner','personal','managed_text_generations',start,end),3,0,NOW,end)
            request=dict(job_id='managed-text-personal',scheduled_at_utc=NOW.isoformat(),phase='prepare',source='console',request_kind='new_publication',mode='live')
            runtime.service.submit(request,'console',content_id=content['id'],expected_revision=content['revision'])
            self.assertEqual(calls,[])
            self.assertEqual(runtime.worker.tick()['state'],'completed')
            self.assertEqual(calls,['personal'])
            self.assertEqual(store.content_store.get(content['id'])['original'],'완성 원고')
            before=(root/'managed/operations.sqlite3').read_bytes()
            settings.save('personal',1,dict(enabled_preference=False,daily_limit=3))
            self.assertEqual(before,(root/'managed/operations.sqlite3').read_bytes())
            self.assertTrue(runtime.service.policy.enabled)
            self.assertTrue(runtime.service.registry.jobs['managed-text-personal']['enabled'])
            after=compile_production_settings([settings.get(a) for a in ('personal','dept')],accounts={'personal':{},'dept':{}},code_root=root,interpreter=Path(sys.executable),activate=True)
            self.assertFalse(after.policy.enabled)
            self.assertEqual(dict(runtime.service.adapters),{})
