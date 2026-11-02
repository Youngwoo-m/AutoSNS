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

    def test_worker_prepares_new_day_and_does_not_reset_consumed_limit(self):
        from datetime import timedelta
        from common.operations.production_quota import prepare_managed_text_quota
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);settings=ProductionSettingsStore(root/'managed');settings.initialize()
            settings.save('personal',0,dict(enabled_preference=True,daily_limit=1))
            compiled=compile_production_settings([settings.get(a) for a in ('personal','dept')],accounts={'personal':{},'dept':{}},code_root=root,interpreter=Path(sys.executable),activate=True)
            calls=[];clock=[NOW]
            class Provider:
                def generate(self,request,prompt,policy):
                    calls.append(request.content_id)
                    return dict(status='completed',text='다음날 원고',provider_id='claude-subscription',execution_id='rollover-fixture',observed_usage=None)
            runtime=build_production_runtime(config=BootstrapConfig(code_root=root,source_root=root/'source',workspace_root=root/'managed',registry_path=root/'unused'),registry=compiled.registry,catalog=compiled.catalog,policy=compiled.policy,
                producers={'managed-text-personal':{'provider':Provider(),'media_runner':{}}},quota_preparer=prepare_managed_text_quota,initialize=True,clock=lambda:clock[0])
            first=prepare_managed_text_quota(runtime.service.store,compiled.registry,clock[0])[0]['bucket_id']
            def submit(title):
                content=runtime.service.store.content_store.create('personal',dict(title=title,kind='article',original='입력'))
                trigger=dict(job_id='managed-text-personal',scheduled_at_utc=clock[0].isoformat(),phase='prepare',source='console',request_kind='new_publication',mode='live')
                runtime.service.submit(trigger,'console',content_id=content['id'],expected_revision=content['revision'])
            submit('전날 접수')
            clock[0]+=timedelta(days=1)
            self.assertEqual(runtime.worker.tick()['state'],'completed')
            buckets=runtime.service.store.quota_buckets()
            self.assertEqual(len(buckets),2)
            self.assertEqual(next(b for b in buckets if b['id']==first)['reserved'],0)
            submit('한도 확인')
            self.assertEqual(runtime.worker.tick()['state'],'blocked')
            self.assertEqual(len(calls),1)
            clock[0]+=timedelta(days=1)
            submit('새 날짜 첫 접수')
            self.assertEqual(runtime.worker.tick()['state'],'completed')
            self.assertEqual(len(calls),2)
