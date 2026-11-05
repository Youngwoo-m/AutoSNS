"""A8 독립 검토 반례. 외부 I/O는 임시 DB와 fixture 전송만 사용한다."""
from contextlib import redirect_stdout
from dataclasses import replace
from datetime import timedelta
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from common.operations.content_store import StoreError
from common.operations.execution_catalog import ExecutionCatalog
from common.operations.models import ContractError
from common.operations.runtime_models import SubmissionResult
from common.operations.worker_service import WorkerService
from tests.integration.test_worker_service import ServiceTests as _Production, PublicationServiceTests as _Publication
from tests.operations.test_runtime_store import NOW


class CallerReceiptTests(unittest.TestCase):
    setUp=_Production.setUp
    service=_Production.service
    request=_Production.request
    submit=_Production.submit

    def worker(self,service):return WorkerService(service,clock=lambda:NOW,stop_event=threading.Event())

    def test_queued_console_caller_revoked_with_launchd_remaining_never_produces(self):
        service=self.service();queued=self.submit(service)
        self.catalog=replace(self.catalog,callers={'launchd-only':dict(job_ids=['produce'],source='launchd',legacy_allowed=False)})
        restarted=self.service();self.worker(restarted).tick()
        self.assertEqual(self.calls,[])
        self.assertNotIn(queued['execution_job_id'],restarted.registry.jobs)
        self.assertNotEqual(self.store.get_run(queued['run_id'])['state'],'running')

    def test_original_caller_survives_schedule_owner_source_normalization(self):
        self.job=dict(self.job,schedule_owner='launchd')
        self.registry=replace(self.registry,jobs={'produce':self.job})
        service=self.service();queued=self.submit(service)
        self.assertEqual(self.store.get_run(queued['run_id'])['occurrence']['source'],'launchd')
        receipt=self.store.get_execution_receipt(queued['run_id'])
        self.assertEqual(receipt['caller_id'],'console');self.assertEqual(receipt['request_source'],'console')
        self.assertEqual(receipt['occurrence']['source'],'launchd')
        self.worker(self.service()).tick();self.assertEqual(len(self.calls),1)

    def test_normalized_source_caller_cannot_replace_revoked_original_identity(self):
        self.job=dict(self.job,schedule_owner='launchd')
        self.registry=replace(self.registry,jobs={'produce':self.job})
        queued=self.submit(self.service())
        self.catalog=replace(self.catalog,callers={'launchd-only':dict(job_ids=['produce'],source='launchd',legacy_allowed=False)})
        self.worker(self.service()).tick();self.assertEqual(self.calls,[])
        self.assertNotEqual(self.store.get_run(queued['run_id'])['state'],'running')

    def test_same_source_other_caller_does_not_restore_revoked_original(self):
        queued=self.submit(self.service())
        self.catalog=replace(self.catalog,callers={'different-console':dict(job_ids=['produce'],source='console',legacy_allowed=False)})
        self.worker(self.service()).tick();self.assertEqual(self.calls,[])
        self.assertEqual(self.store.get_execution_receipt(queued['run_id'])['caller_id'],'console')

    def test_receipt_and_occurrence_are_atomic_and_reads_do_not_write(self):
        service=self.service();queued=self.submit(service)
        self.assertEqual(queued,self.submit(service))
        before=(self.store.root/'operations.sqlite3').read_bytes()
        receipt=self.store.get_execution_receipt(queued['run_id'])
        self.assertEqual(receipt['occurrence']['job_id'],queued['execution_job_id'])
        self.assertEqual(before,(self.store.root/'operations.sqlite3').read_bytes())
        with self.store._db(True) as db:db.execute('DELETE FROM execution_receipts WHERE run_id=?',(queued['run_id'],))
        self.worker(self.service()).tick();self.assertEqual(self.calls,[])

    def test_receipt_insert_failure_rolls_back_occurrence_then_replay_recovers(self):
        service=self.service()
        with self.store._db(True) as db:
            db.execute("CREATE TRIGGER receipt_failure BEFORE INSERT ON execution_receipts BEGIN SELECT RAISE(ABORT,'fixture receipt failure'); END")
        with self.assertRaises(StoreError):self.submit(service)
        self.assertEqual(self.store.list_runs(),[]);self.assertEqual(self.store.list_execution_receipts(),[])
        saved=self.production.list_bindings();self.assertEqual(len(saved),1)
        with self.store._db(True) as db:db.execute('DROP TRIGGER receipt_failure')
        queued=self.submit(service);self.assertEqual(queued['binding_id'],saved[0]['binding_id'])
        self.worker(service).tick();self.assertEqual(len(self.calls),1)

    def test_other_authorized_source_replay_keeps_first_identity(self):
        self.catalog=replace(self.catalog,callers={**self.catalog.callers,'launchd':dict(job_ids=['produce'],source='launchd',legacy_allowed=False)})
        service=self.service();queued=self.submit(service)
        replay=service.submit(dict(self.request(),source='launchd'),'launchd',content_id=self.snapshot['id'],expected_revision=1)
        self.assertEqual(queued,replay);self.assertEqual(len(self.store.list_runs()),1)
        self.assertEqual(self.store.get_execution_receipt(queued['run_id'])['caller_id'],'console')
        self.catalog=replace(self.catalog,callers={'launchd':self.catalog.callers['launchd']})
        self.worker(self.service()).tick();self.assertEqual(self.calls,[])

    def test_revoked_first_caller_does_not_block_other_authorized_production(self):
        self.catalog=replace(self.catalog,callers={**self.catalog.callers,'other':dict(job_ids=['produce'],source='console',legacy_allowed=False)})
        service=self.service();first=self.submit(service)
        second=self.content.create('personal',dict(title='두 번째',kind='article',original='입력2'))
        next_run=service.submit(self.request(),'other',content_id=second['id'],expected_revision=1)
        self.catalog=replace(self.catalog,callers={'other':self.catalog.callers['other']})
        self.worker(self.service()).tick()
        self.assertEqual(self.store.get_run(first['run_id'])['state'],'failed')
        self.assertEqual(len(self.calls),1);self.assertEqual(self.calls[0].content_id,second['id'])
        self.assertEqual(self.store.get_run(next_run['run_id'])['state'],'waiting')

    def test_other_receipt_on_same_binding_does_not_authorize_revoked_run(self):
        self.catalog=replace(self.catalog,callers={**self.catalog.callers,'other':dict(job_ids=['produce'],source='console',legacy_allowed=False)})
        service=self.service();first=self.submit(service)
        later=dict(self.request(),scheduled_at_utc=(NOW+timedelta(seconds=1)).isoformat())
        second=service.submit(later,'other',content_id=self.snapshot['id'],expected_revision=1)
        self.assertEqual(first['binding_id'],second['binding_id'])
        self.catalog=replace(self.catalog,callers={'other':self.catalog.callers['other']})
        restarted=self.service();self.assertIn(first['execution_job_id'],restarted.registry.jobs)
        WorkerService(restarted,clock=lambda:NOW+timedelta(seconds=1),stop_event=threading.Event()).tick()
        self.assertEqual(self.store.get_run(first['run_id'])['state'],'failed')
        self.assertEqual(self.store.get_service_run_result(first['run_id'])['reason_code'],'unknown_caller')
        self.assertEqual(len(self.calls),1)
        self.assertEqual(self.calls[0].occurrence_id,second['binding_id']+':'+second['run_id'])

    def test_current_caller_source_changed_under_same_id_blocks_claim(self):
        queued=self.submit(self.service())
        self.catalog=replace(self.catalog,callers={'console':dict(job_ids=['produce'],source='launchd',legacy_allowed=False)})
        self.worker(self.service()).tick();self.assertEqual(self.calls,[])


class DispatcherRecoveryTests(unittest.TestCase):
    setUp=_Publication.setUp
    build=_Publication.build
    service=_Publication.service
    observe_quota=_Publication.observe_quota
    adapter=_Publication.adapter

    def add_delivery(self):
        run=self.store.submit_occurrence(dict(job_id='j',scheduled_at_utc=(NOW+timedelta(seconds=1)).isoformat(),phase='submit',source='console',request_kind='new_publication',mode='live'))['id']
        plan=dict(self.plan,id='second',schedule_slot='second')
        with self.store._db(True) as db:
            db.execute('INSERT INTO deliveries VALUES(?,?,?,?,?,?,?,?)',('second',self.content['id'],self.content['revision'],'x','initial','second','second',json.dumps(plan)))
        ctx=replace(self.ctx,run_id=run,schedule_slot='second')
        self.store.create_delivery('second',run,ctx);self.store.record_evidence('second','target_observation',self.observed)
        self.store.record_publication_approval('second',1,ctx.context_hash,'second-approval',ctx.review_report_hashes)
        return run

    def test_empty_verify_does_not_starve_approved_submit(self):
        self.observe_quota();service=self.service(self.adapter())
        verify=self.store.submit_occurrence(dict(job_id='j',scheduled_at_utc=NOW.isoformat(),phase='verify',source='console',request_kind='new_publication',mode='live'))['id']
        worker=WorkerService(service,clock=lambda:NOW,stop_event=threading.Event())
        worker.tick();worker.tick()
        self.assertEqual(self.store.get_delivery('d')['state'],'uploaded')
        self.assertEqual(self.store.get_run(verify)['state'],'completed')
        self.assertEqual(len(self.store.attempts('d')),1)

    def test_invalid_prepare_does_not_starve_approved_submit(self):
        self.observe_quota();service=self.service(self.adapter())
        bad=self.store.submit_occurrence(dict(job_id='removed-production',scheduled_at_utc=NOW.isoformat(),phase='prepare',source='console',request_kind='new_publication',mode='live'))['id']
        worker=WorkerService(service,clock=lambda:NOW,stop_event=threading.Event())
        worker.tick();worker.tick()
        self.assertEqual(self.store.get_delivery('d')['state'],'uploaded')
        self.assertEqual(self.store.get_run(bad)['state'],'failed')
        self.assertEqual(self.store.get_service_run_result(bad)['reason_code'],'invalid_binding')

    def test_transient_heartbeat_failure_is_fenced_then_other_job_can_run(self):
        self.observe_quota();worker=None;lose=[True]
        def inspect(ctx):
            if lose[0]:
                lose[0]=False
                with patch.object(self.store,'renew_lease',side_effect=StoreError('storage_error')):worker.heartbeat_once()
            return self.observed
        worker=WorkerService(self.service(self.adapter(inspect=inspect)),clock=lambda:NOW+timedelta(seconds=1),stop_event=threading.Event())
        self.assertEqual(worker.tick()['reason_code'],'heartbeat_lost')
        self.assertIsNone(worker.active_lease)
        self.assertEqual(self.store.get_delivery('d')['state'],'needs_review')
        expiry=self.store.get_run(self.run)['lease_expires_at']
        self.assertIsNotNone(expiry)
        self.assertLessEqual(expiry,(NOW+timedelta(seconds=1)).isoformat())
        self.add_delivery();worker.tick()
        self.assertEqual(self.store.get_delivery('second')['state'],'uploaded')
        self.assertEqual(self.store.get_delivery('d')['state'],'needs_review')
        self.assertEqual(self.store.attempts('d'),[])

    def test_heartbeat_loss_inflight_preserves_unknown_and_allows_other_job(self):
        self.observe_quota();worker=None;calls=[]
        def submit(ctx,*args):
            calls.append(ctx.schedule_slot)
            if ctx.schedule_slot=='slot':
                with patch.object(self.store,'renew_lease',side_effect=StoreError('storage_error')):worker.heartbeat_once()
                raise TimeoutError('fixture response loss')
            return SubmissionResult('submitted',remote_id='second-only')
        worker=WorkerService(self.service(self.adapter(submit)),clock=lambda:NOW+timedelta(seconds=1),stop_event=threading.Event())
        worker.tick();self.assertEqual(self.store.get_delivery('d')['state'],'unknown')
        self.add_delivery();worker.tick()
        self.assertEqual(self.store.get_delivery('second')['state'],'uploaded')
        self.assertEqual(self.store.get_delivery('d')['state'],'unknown');self.assertEqual(calls,['slot','second'])

    def test_fence_database_failure_blocks_claim_until_recovered(self):
        self.observe_quota();worker=None;lose=[True]
        def inspect(ctx):
            if lose[0]:
                lose[0]=False
                with patch.object(self.store,'renew_lease',side_effect=StoreError('storage_error')):worker.heartbeat_once()
            return self.observed
        worker=WorkerService(self.service(self.adapter(inspect=inspect)),clock=lambda:NOW+timedelta(seconds=1),stop_event=threading.Event())
        with patch.object(self.store,'fence_lost_lease',side_effect=StoreError('storage_error')):
            worker.tick();self.add_delivery()
            self.assertEqual(worker.tick()['reason_code'],'storage_error')
            self.assertEqual(self.store.get_delivery('second')['state'],'queued')
            self.assertEqual(self.store.attempts('second'),[])
        self.assertEqual(worker.tick()['delivery_id'],'second')
        self.assertEqual(self.store.get_delivery('d')['state'],'needs_review')
        self.assertEqual(self.store.get_delivery('second')['state'],'uploaded')



class ModuleCLITests(unittest.TestCase):
    def test_actual_module_status_is_configured_disabled(self):
        root=Path(__file__).resolve().parents[2]
        result=subprocess.run([sys.executable,'-m','common.operations.cli','status'],cwd=root,capture_output=True,text=True,check=False)
        self.assertEqual(result.returncode,0);self.assertEqual(result.stderr,'')
        self.assertEqual(json.loads(result.stdout)['state'],'disabled')

    def test_trusted_fixture_bootstrap_never_initializes_claims_or_builds_adapters(self):
        from common.operations import cli
        from common.operations.bootstrap_config import BootstrapConfig
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);path=root/'operations.json'
            path.write_text(json.dumps(dict(schema_version=1,revision='fixture',accounts={'personal':{}},jobs={},policies={})))
            config=BootstrapConfig(source_root=root/'source',workspace_root=root/'workspace',registry_path=path)
            for command in (['status'],['worker','--once']):
                output=StringIO()
                with patch('common.operations.bootstrap_config.default_bootstrap_config',return_value=config), \
                     patch('common.operations.database.initialize_database',side_effect=AssertionError('DDL 금지')), \
                     patch('common.operations.runtime_store.RuntimeStore.claim_run',side_effect=AssertionError('claim 금지')), \
                     patch('common.publishers.build_adapters',side_effect=AssertionError('adapter 금지')), \
                     patch('common.shared.axlock.AxLock.acquire',side_effect=AssertionError('잠금/프로필 금지')),redirect_stdout(output):
                    code=cli.module_main(command)
                self.assertEqual(code,0);self.assertEqual(json.loads(output.getvalue())['state'],'disabled')
            self.assertFalse(config.workspace_root.exists());self.assertFalse(config.source_root.exists())

    def test_invalid_config_is_unconfigured_without_initialization(self):
        from common.operations import cli
        from common.operations.bootstrap_config import BootstrapConfig
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);config=BootstrapConfig(source_root=root/'source',workspace_root=root/'workspace',registry_path=root/'missing.json')
            output=StringIO()
            with patch('common.operations.bootstrap_config.default_bootstrap_config',return_value=config),redirect_stdout(output):
                code=cli.module_main(['status'])
            self.assertEqual(json.loads(output.getvalue())['state'],'unconfigured')
            self.assertFalse(config.workspace_root.exists());self.assertFalse(config.source_root.exists())

    def test_unsupported_existing_database_is_unconfigured_and_unchanged(self):
        from common.operations import cli
        from common.operations.bootstrap_config import BootstrapConfig
        import sqlite3
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);workspace=root/'workspace';workspace.mkdir();registry=root/'operations.json'
            registry.write_text(json.dumps(dict(schema_version=1,revision='fixture',accounts={'personal':{}},jobs={},policies={})))
            dbpath=workspace/'operations.sqlite3';db=sqlite3.connect(dbpath);db.execute('PRAGMA user_version=99');db.close()
            config=BootstrapConfig(source_root=root/'source',workspace_root=workspace,registry_path=registry);before=dbpath.read_bytes()
            output=StringIO()
            with patch('common.operations.bootstrap_config.default_bootstrap_config',return_value=config),redirect_stdout(output):
                cli.module_main(['status'])
            self.assertEqual(json.loads(output.getvalue())['state'],'unconfigured');self.assertEqual(dbpath.read_bytes(),before)
            self.assertFalse(config.source_root.exists())



del _Production,_Publication
