"""실제 서비스/원장/제작 관문을 사용하고 외부 I/O만 fixture로 대체한다."""
import importlib.util
import json
import signal
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from common.operations.content_store import ContentStore, StoreError
from common.operations.models import Registry, ContractError
from common.operations.runtime_store import RuntimeStore
from common.operations.production_store import ProductionStore
from common.operations.ledger import Ledger
from common.operations.execution_catalog import ExecutionCatalog, ExecutorSpec
from common.operations.runtime_models import ExecutionPolicy, SubmissionResult, LookupResult
from common.operations.quota import bucket_id, quota_window
from common.shared.axlock import AxLock, LockPaths
from tests.operations.test_runtime_store import NOW
from tests.operations.test_publication_gate import GateFixture as _GateFixture


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.content=ContentStore(self.root/'managed');self.content.initialize()
        self.snapshot=self.content.create('personal',dict(title='원고',kind='article',original='입력'))
        self.owner=dict(scope_kind='owner',scope_id='personal',metric='posts',window_kind='day',timezone='UTC',amount=1,limit=5)
        self.job=dict(id='produce',kind='production',owner_account_id='personal',policy_revision='p',required_outputs=['text'],
            executor_id='producer',schedule_owner='console',execution_owner='managed',enabled=True,subscription_only=True)
        self.registry=Registry('rev',{'personal':{}},{},{},{},{'produce':self.job},{'p':dict(subscription_only=True,quota_requirements=[self.owner])},{})
        spec=ExecutorSpec('producer',('produce',),('prepare',),'/fixture/python',self.root,'fixture',(),())
        self.catalog=ExecutionCatalog({'producer':spec},{'console':dict(job_ids=['produce'],source='console',legacy_allowed=False)}, {'produce':{}})
        self.policy=ExecutionPolicy(True,(),'cutover',{'subscription_only':True})
        self.store=RuntimeStore(self.content.root,self.registry,self.content);self.store.initialize()
        self.production=ProductionStore(self.content.root,registry=self.registry);self.production.initialize()
        self.ledger=Ledger(self.content.root,self.registry,self.content);self.ledger.initialize()
        self.locks=AxLock(LockPaths.from_root(self.root/'source'))
        start,end=quota_window(self.owner,NOW);self.store.observe_bucket(bucket_id('owner','personal','posts',start,end),5,0,NOW,end)
        self.calls=[];calls=self.calls
        class Provider:
            def generate(self,request,prompt,policy):
                calls.append(request)
                return dict(status='completed',text='완성 본문',provider_id='claude-subscription',execution_id='production-fixture',observed_usage=None)
        self.producers={'produce':{'provider':Provider(),'media_runner':{}}}

    def service(self,policy=None):
        from common.operations.execution_service import ExecutionService
        return ExecutionService(self.store,self.ledger,self.registry,self.catalog,policy or self.policy,{},self.producers,self.production,self.locks,lambda:NOW)

    def request(self):
        return dict(job_id='produce',scheduled_at_utc=NOW.isoformat(),phase='prepare',source='console',request_kind='new_publication',mode='live')

    def submit(self,service=None,snapshot=None):
        snapshot=snapshot or self.snapshot
        return (service or self.service()).submit(self.request(),'console',content_id=snapshot['id'],expected_revision=snapshot['revision'])

    def test_default_service_starts_nothing(self):
        self.assertIsNotNone(importlib.util.find_spec('common.operations.worker_service'))
        from common.operations.worker_service import WorkerService
        service=self.service(ExecutionPolicy());worker=WorkerService(service,clock=lambda:NOW,stop_event=threading.Event())
        before=(self.content.root/'operations.sqlite3').read_bytes()
        self.assertEqual(worker.tick()['state'],'disabled');self.assertEqual(worker.run(once=True),0)
        self.assertEqual(before,(self.content.root/'operations.sqlite3').read_bytes());self.assertEqual(self.calls,[])

    def test_bootstrap_resolves_registry_before_worker(self):
        service=self.service();result=self.submit(service)
        reopened=self.service()
        self.assertIn(result['execution_job_id'],reopened.registry.jobs)
        self.assertIs(reopened.registry,self.store.registry);self.assertIs(reopened.registry,self.ledger.registry())
        self.assertIs(reopened.registry,self.production.registry)

    def test_two_contents_same_base_job_and_time_create_distinct_runs(self):
        service=self.service();one=self.submit(service)
        other=self.content.create('personal',dict(title='다른 원고',kind='article',original='다른 입력'))
        two=self.submit(service,other)
        self.assertNotEqual(one['run_id'],two['run_id']);self.assertNotEqual(one['execution_job_id'],two['execution_job_id'])

    def test_same_binding_replay_is_one_run(self):
        service=self.service();one=self.submit(service)
        self.assertEqual(one,self.submit(service));self.assertEqual(len(self.store.list_runs()),1)
        self.assertEqual(self.calls,[])

    def test_changed_revision_does_not_replace_bound_input(self):
        from common.operations.worker_service import WorkerService
        service=self.service();one=self.submit(service)
        self.content.update(self.snapshot['id'],1,dict(title='수정',kind='article',original='사람 수정'))
        self.assertEqual(one,self.submit(service))
        result=WorkerService(service,clock=lambda:NOW,stop_event=threading.Event()).tick()
        self.assertEqual(result['state'],'blocked');self.assertEqual(self.calls,[])
        self.assertEqual(self.production.list_bindings()[0]['content_revision'],1)

    def test_http_options_cannot_inject_production_unit(self):
        service=self.service()
        for key in ('production_unit_id','production_id','binding_id','owner_account_id','credential_ref'):
            with self.assertRaises((StoreError,ContractError)):
                service.submit(dict(self.request(),**{key:'foreign'}),'console',content_id=self.snapshot['id'],expected_revision=1)
        self.assertEqual(self.store.list_runs(),[]);self.assertEqual(self.production.list_bindings(),[])

    def test_production_has_no_profile_lock(self):
        from common.operations.worker_service import WorkerService
        service=self.service();result=self.submit(service);resources=[];original=self.locks.hold
        from contextlib import contextmanager
        @contextmanager
        def traced(items,**kwargs):
            resources.extend(items)
            with original(items,**kwargs) as lease:yield lease
        with patch.object(self.locks,'hold',traced):
            done=WorkerService(service,clock=lambda:NOW,stop_event=threading.Event()).tick()
        self.assertEqual(done['state'],'completed');self.assertEqual(len(self.calls),1)
        self.assertFalse(any(x.startswith('profile:') for x in resources))
        self.assertEqual(self.calls[0].occurrence_id,result['binding_id']+':'+result['run_id'])
        output=self.content.get(self.snapshot['id']);link=self.store.get_production_for_output(output['id'],output['revision'],output['manifest_hash'])
        self.assertTrue(link);self.assertEqual(self.store.get_run(result['run_id'])['state'],'waiting')

    def test_binding_without_current_registered_caller_is_not_restored(self):
        service=self.service();made=self.submit(service)
        self.catalog=replace(self.catalog,callers={})
        reopened=self.service()
        self.assertNotIn(made['execution_job_id'],reopened.registry.jobs)

    def test_stale_registry_binding_does_not_restore_job(self):
        service=self.service();made=self.submit(service)
        self.registry=replace(self.registry,revision='new')
        reopened=self.service()
        self.assertNotIn(made['execution_job_id'],reopened.registry.jobs)

    def reviewed_service(self,*,crash=False):
        from common.operations.worker_service import WorkerService
        from common.operations.review_runner import RegisteredReviewRunner,SubscriptionReviewProvider,calculate_registered_inputs
        from common.operations.production_models import ProductionRequest
        from common.operations.provider_policy import resolve_job_provider_policy
        self.registry=replace(self.registry,policies={'p':dict(self.registry.policies['p'],require_calc_review=True,review_authorities={'calc':['calc'],'source':['source']})})
        service=self.service();submitted=self.submit(service);binding=self.production.list_bindings()[0]
        request=ProductionRequest('produce','personal',binding['binding_id']+':'+submitted['run_id'],self.snapshot['id'],1,binding['input_payload']['brief'],('text',))
        policy=resolve_job_provider_policy(dict(self.job),service.registry,service.policy);calls=[]
        class Reviewer:
            def __init__(self,role):self.role=role
            def generate(self,*args):
                calls.append(self.role)
                if crash and self.role=='source':raise KeyboardInterrupt('fixture crash')
                return dict(status='completed',execution_id='review-'+self.role,text='{"verdict":"pass","findings":[]}')
        runners={role:SubscriptionReviewProvider(Reviewer(role),request=request,policy=policy,principal_id=role) for role in ('calc','source')}
        service.producers['produce']['review_runner']=RegisteredReviewRunner(runners,source_checker=lambda snapshot:{'available':True,'checked':True},
            calculation_runner=lambda snapshot:calculate_registered_inputs([dict(operation='add',operands=[1,1],expected=2,tolerance=0,unit='m')]))
        return service,submitted,calls

    def test_registered_prepare_review_runner_runs_independent_roles(self):
        from common.operations.worker_service import WorkerService
        service,submitted,calls=self.reviewed_service()
        result=WorkerService(service,clock=lambda:NOW,stop_event=threading.Event()).tick()
        self.assertEqual(calls,['calc','source']);self.assertEqual(result['review_status'],'completed')
        self.assertEqual(self.store.get_run(submitted['run_id'])['state'],'completed')
        stored=self.store.get_service_run_result(submitted['run_id'])
        self.assertEqual(stored['review']['status'],'completed')

    def test_review_crash_preserves_intent_and_does_not_reinvoke_models(self):
        from common.operations.worker_service import WorkerService
        service,submitted,calls=self.reviewed_service(crash=True)
        with self.assertRaises(KeyboardInterrupt):WorkerService(service,clock=lambda:NOW,stop_event=threading.Event()).tick()
        self.assertEqual(self.store.get_service_run_result(submitted['run_id'])['review']['status'],'running')
        self.assertEqual(self.store.get_run(submitted['run_id'])['state'],'running')
        self.assertEqual(calls,['calc','source']);self.assertEqual(len(self.calls),1)
        restored=self.service()
        WorkerService(restored,clock=lambda:NOW,stop_event=threading.Event()).tick()
        result=self.store.get_service_run_result(submitted['run_id'])
        self.assertEqual(result['status'],'completed');self.assertEqual(result['review']['status'],'unknown')
        self.assertEqual(self.store.get_run(submitted['run_id'])['state'],'waiting')
        self.assertEqual(calls,['calc','source']);self.assertEqual(len(self.calls),1)

    def test_missing_review_runner_keeps_production_complete_and_review_required(self):
        from common.operations.worker_service import WorkerService
        service=self.service();submitted=self.submit(service)
        result=WorkerService(service,clock=lambda:NOW,stop_event=threading.Event()).tick()
        self.assertEqual(result['review_status'],'required')
        self.assertEqual(self.store.get_run(submitted['run_id'])['state'],'waiting')
        stored=self.store.get_service_run_result(submitted['run_id'])
        self.assertEqual(stored['status'],'completed');self.assertEqual(stored['review']['reason_code'],'independent_review_required')

    def test_bootstrap_default_has_same_registry_and_no_adapters_or_probe(self):
        from common.operations.bootstrap_config import BootstrapConfig,build_execution_service,cli_services
        config=BootstrapConfig(source_root=self.root/'source',workspace_root=self.content.root,registry_path=self.root/'registry.json')
        before=(self.content.root/'operations.sqlite3').read_bytes()
        with patch('common.publishers.build_adapters',side_effect=AssertionError('비활성 factory')):
            service=build_execution_service(config=config,registry=self.registry,catalog=self.catalog)
        self.assertIs(service.registry,service.store.registry);self.assertIs(service.registry,service.production_store.registry)
        self.assertIs(service.registry,service.ledger.registry());self.assertEqual(service.adapters,{})
        self.assertEqual(before,(self.content.root/'operations.sqlite3').read_bytes())
        self.assertEqual(cli_services(service,caller_ids={'console':'console'})['status']()['state'],'disabled')

    def test_invalid_prepare_mode_does_not_store_binding(self):
        with self.assertRaises(StoreError):
            self.service().submit(dict(self.request(),mode='invalid'),'console',content_id=self.snapshot['id'],expected_revision=1)
        self.assertEqual(self.production.list_bindings(),[])

    def test_production_restarts_after_finish_without_generating_again(self):
        from common.operations.worker_service import WorkerService
        service=self.service();result=self.submit(service)
        with patch.object(self.store,'finish_service_run',side_effect=StoreError('storage_error')):
            WorkerService(service,clock=lambda:NOW,stop_event=threading.Event()).tick()
        self.assertEqual(self.store.get_run(result['run_id'])['state'],'running');self.assertEqual(len(self.calls),1)
        reopened=self.service()
        done=WorkerService(reopened,clock=lambda:NOW,stop_event=threading.Event()).tick()
        self.assertEqual(done['state'],'completed');self.assertEqual(len(self.calls),1)



class PublicationServiceTests(unittest.TestCase):
    setUp=_GateFixture.setUp
    build=_GateFixture.build

    def service(self,adapter):
        from common.operations.execution_service import ExecutionService
        registry=self.registry
        self.store.locks.process_probe=lambda resource:False
        ledger=Ledger(self.store.root,registry,self.store.content_store);ledger.initialize()
        production=ProductionStore(self.store.root,registry=registry);production.initialize()
        return ExecutionService(self.store,ledger,registry,ExecutionCatalog(),self.policy,{'x':adapter},{},production,self.store.locks,lambda:NOW)

    def observe_quota(self):
        for req in self.registry.policies['p']['quota_requirements']:
            start,end=quota_window(req,NOW)
            self.store.observe_bucket(bucket_id(req['scope_kind'],req['scope_id'],req['metric'],start,end),5,0,NOW,end)

    def adapter(self,submit=None,inspect=None):
        observed=self.observed
        class Adapter:
            def inspect_target(self,ctx):return inspect(ctx) if inspect else observed
            def prepare(self,ctx,snapshot):return {}
            def submit(self,ctx,prepared,permit):return submit(ctx,prepared,permit) if submit else SubmissionResult('submitted',remote_id='remote-fixture',evidence={'followup_intents':{'playlist':'required_not_started'}})
            def lookup(self,ctx,attempt):return LookupResult('unsupported',evidence={'reason':'media_evidence_required'})
        return Adapter()

    def test_background_heartbeat_renews_from_its_own_connection(self):
        from common.operations.worker_service import WorkerService
        self.observe_quota();now=[NOW]
        def submit(*args):
            version=self.store.get_run(self.run)['version']
            now[0]=NOW+timedelta(seconds=10)
            deadline=__import__('time').monotonic()+1
            while self.store.get_run(self.run)['version']==version and __import__('time').monotonic()<deadline:
                threading.Event().wait(.01)
            self.assertGreater(self.store.get_run(self.run)['version'],version)
            return SubmissionResult('submitted',remote_id='heartbeat-background')
        worker=WorkerService(self.service(self.adapter(submit)),clock=lambda:now[0],stop_event=threading.Event(),heartbeat_interval=.01)
        self.assertEqual(worker.tick()['delivery_id'],'d');self.assertIsNone(worker.active_lease)

    def test_long_upload_renews_lease_without_long_db_transaction(self):
        from common.operations.worker_service import WorkerService
        now=[NOW];self.observe_quota();worker=None
        def upload(*args):
            for seconds in range(10,70,10):
                now[0]=NOW+timedelta(seconds=seconds)
                worker.heartbeat_once()
                with closing(sqlite3.connect(self.store.root/'operations.sqlite3',timeout=0)) as db:
                    db.execute('BEGIN IMMEDIATE');db.rollback()
            now[0]=NOW+timedelta(seconds=65)
            self.assertGreater(self.store.get_run(self.run)['lease_expires_at'],now[0].isoformat())
            return SubmissionResult('submitted',remote_id='after65')
        worker=WorkerService(self.service(self.adapter(upload)),clock=lambda:now[0],stop_event=threading.Event())
        result=worker.tick();self.assertEqual(result['delivery_id'],'d')
        self.assertEqual(self.store.get_delivery('d')['remote_id'],'after65')
        self.assertIsNone(worker.active_lease)

    def test_heartbeat_loss_before_submit_blocks(self):
        from common.operations.worker_service import WorkerService
        self.observe_quota();calls=[];worker=None
        def inspect(ctx):
            with patch.object(self.store,'renew_lease',side_effect=StoreError('storage_error')):worker.heartbeat_once()
            return self.observed
        worker=WorkerService(self.service(self.adapter(lambda *a:calls.append(a),inspect)),clock=lambda:NOW,stop_event=threading.Event())
        result=worker.tick();self.assertEqual(result['state'],'blocked');self.assertEqual(calls,[])
        self.assertFalse(any(a['request_started'] for a in self.store.attempts('d')))

    def test_stop_during_inflight_records_result_without_next_submit(self):
        from common.operations.worker_service import WorkerService
        self.observe_quota();stop=threading.Event();calls=[]
        def submit(*args):
            calls.append(1);stop.set();return SubmissionResult('submitted',remote_id='remote-before-stop')
        worker=WorkerService(self.service(self.adapter(submit)),clock=lambda:NOW,stop_event=stop)
        worker.tick();self.assertEqual(worker.tick()['state'],'stopped');self.assertEqual(calls,[1])
        self.assertEqual(self.store.get_delivery('d')['remote_id'],'remote-before-stop')

    def test_sigterm_drains_without_requeueing_unknown(self):
        from common.operations.worker_service import WorkerService
        self.observe_quota();worker=None
        def submit(*args):
            worker.handle_signal(signal.SIGTERM,None);raise TimeoutError()
        worker=WorkerService(self.service(self.adapter(submit)),clock=lambda:NOW,stop_event=threading.Event())
        self.assertEqual(worker.run(once=True),0)
        self.assertEqual(self.store.get_delivery('d')['state'],'unknown');self.assertTrue(worker.stop_event.is_set())

    def test_restarted_service_reconciles_without_submit(self):
        from common.operations.worker_service import WorkerService
        self.observe_quota()
        def submit(*args):raise TimeoutError()
        WorkerService(self.service(self.adapter(submit)),clock=lambda:NOW,stop_event=threading.Event()).tick()
        reopened=self.service(self.adapter(lambda *a:self.fail('재제출 금지')))
        result=reopened.reconcile('d',expected_version=self.store.get_delivery('d')['version'],request_key='reconcile-once')
        self.assertEqual(self.store.get_delivery('d')['state'],'unknown')
        self.assertEqual(len(self.store.attempts('d')),1)

    def test_admission_requires_current_observation_and_reviews(self):
        seen=[];service=self.service(self.adapter(inspect=lambda ctx:(seen.append(ctx),self.observed)[1]))
        # 계획은 유지하고 runtime만 제거해 첫 admission을 시험한다.
        with self.store._db(True) as db:
            db.execute('DELETE FROM publication_approvals');db.execute('DELETE FROM operation_evidence');db.execute('DELETE FROM runtime_deliveries')
        observed=service.observe('d',self.run,1)
        self.assertEqual(seen[0].scope,'admission_read');self.assertFalse(hasattr(seen[0],'auth_checked_at'))
        self.assertIsNone(self.store.get_delivery('d'));self.assertIsNone(self.store.get_publication_approval('d'))
        before=(self.store.root/'operations.sqlite3').read_bytes()
        self.assertEqual(self.store.get_admission_observation(observed['id'])['plan_version'],1)
        self.assertEqual(before,(self.store.root/'operations.sqlite3').read_bytes())
        admitted=service.admit('d',self.run,1,observed['id'])
        self.assertEqual(admitted['state'],'queued');self.assertIsNone(self.store.get_publication_approval('d'))
        approved=service.approve('d',admitted['version'],admitted['context_hash'],'approve-once','fixture-user')
        self.assertEqual(approved,service.approve('d',admitted['version'],admitted['context_hash'],'approve-once','fixture-user'))
        with self.assertRaises((StoreError,ContractError)):service.admit('d',self.run,2,observed['id'])

    def test_direct_verification_rechecks_current_job_before_read(self):
        from common.operations.worker_service import WorkerService
        self.observe_quota();WorkerService(self.service(self.adapter()),clock=lambda:NOW,stop_event=threading.Event()).tick()
        self.registry=replace(self.registry,jobs={**self.registry.jobs,'j':dict(self.registry.jobs['j'],enabled=False)})
        calls=[];adapter=self.adapter();adapter.verify=lambda *args:calls.append(1)
        service=self.service(adapter)
        with self.assertRaises((StoreError,ContractError)):service.verify('d',expected_version=self.store.get_delivery('d')['version'])
        self.assertEqual(calls,[])

    def test_remote_id_and_followup_intent_survive_reopen_without_followup_io(self):
        from common.operations.worker_service import WorkerService
        self.observe_quota();calls=[]
        intents=[dict(action='playlist',state='not_started',required=True,separate_approval_required=True)]
        def submit(*args):
            calls.append('upload')
            return SubmissionResult('submitted',remote_id='remote-preserved',evidence=dict(followup_intents=intents,followup_completion='pending'))
        WorkerService(self.service(self.adapter(submit)),clock=lambda:NOW,stop_event=threading.Event()).tick()
        reopened=RuntimeStore(self.store.root,self.registry,self.store.content_store);reopened.initialize()
        self.assertEqual(reopened.get_delivery('d')['remote_id'],'remote-preserved')
        self.assertEqual(reopened.attempts('d')[0]['result']['evidence']['followup_intents'],intents)
        result=self.service(self.adapter(submit)).status(self.run)
        self.assertEqual(result['deliveries'][0]['followup_completion'],'pending')
        self.assertEqual(result['deliveries'][0]['followup_intents'],intents);self.assertEqual(calls,['upload'])

    def test_global_stop_during_upload_preserves_result(self):
        from common.operations.worker_service import WorkerService
        self.observe_quota()
        def submit(*args):
            self.store.locks.set_stop('fixture inflight')
            return SubmissionResult('submitted',remote_id='accepted-before-stop')
        worker=WorkerService(self.service(self.adapter(submit)),clock=lambda:NOW,stop_event=threading.Event())
        self.assertEqual(worker.tick()['delivery_id'],'d')
        self.assertEqual(self.store.get_delivery('d')['remote_id'],'accepted-before-stop')
        self.assertEqual(worker.tick()['reason_code'],'control_blocked')

    def test_plan_options_cannot_select_production_or_credentials(self):
        calls=[];service=self.service(self.adapter(inspect=lambda ctx:calls.append(ctx)))
        for key in ('production_unit_id','production_id','owner_account_id','credential_ref','binding_id'):
            with self.store._db(True) as db:
                plan=dict(self.plan,options={'nested':{key:'foreign'}})
                db.execute('UPDATE deliveries SET payload=? WHERE id=?',(json.dumps(plan),'d'))
            with self.assertRaises(StoreError):service.observe('d',self.run,1)
        self.assertEqual(calls,[])

    def test_produce_two_targets_next_day_charges_owner_once(self):
        from common.operations.worker_service import WorkerService
        from common.operations.models import thaw
        from common.operations.quota import bucket_id,quota_window
        registry=self.registry;rows=thaw(registry.policies['p']['quota_requirements'])
        rows2=[dict(row,scope_id='t2') if row['scope_kind']=='target' else dict(row) for row in rows]
        second=replace(registry.connections['x'],id='y',target_id='t2')
        jobs=thaw(registry.jobs);jobs['j']['executor_id']='fixture-publisher'
        jobs['j2']=dict(jobs['j'],connection_id='y',policy_revision='p2')
        self.registry=replace(registry,connections={**registry.connections,'y':second},jobs=jobs,
            policies={**registry.policies,'p2':dict(thaw(registry.policies['p']),quota_requirements=rows2)})
        self.policy=replace(self.policy,allowed_connection_ids=('x','y'))
        now=[NOW];calls=[]
        def inspect(ctx):return dict(self.observed,target_id=ctx.target_id,checked_at=now[0].isoformat(),expires_at=(now[0]+timedelta(minutes=5)).isoformat())
        def submit(ctx,*args):calls.append(ctx.target_id);return SubmissionResult('submitted',remote_id='remote-'+str(len(calls)))
        adapter=self.adapter(submit,inspect);service=self.service(adapter);service.adapters['y']=adapter
        service.clock=lambda:now[0]
        spec=ExecutorSpec('fixture-publisher',('j','j2'),('submit','verify'),'/fixture/python',self.root,'fixture',('publish',),())
        service.catalog=ExecutionCatalog({'fixture-publisher':spec},{'console':dict(job_ids=['j','j2'],source='console',legacy_allowed=False)})
        self.observe_quota()
        worker=WorkerService(service,clock=service.clock,stop_event=threading.Event());worker.tick()
        for index,day in enumerate((0,1),2):
            now[0]=NOW+timedelta(days=day)
            for row in rows2:
                if row['scope_kind']=='owner':continue
                start,end=quota_window(row,now[0]);self.store.observe_bucket(bucket_id(row['scope_kind'],row['scope_id'],row['metric'],start,end),row['limit'],0,now[0],end)
            delivery_id='d'+str(index)
            plan=dict(self.plan,id=delivery_id,connection_id='y',schedule_slot='slot'+str(index),schedule_condition={'kind':'fixed','at':now[0].isoformat()})
            with self.store._db(True) as db:
                db.execute('INSERT INTO deliveries VALUES(?,?,?,?,?,?,?,?)',(delivery_id,self.content['id'],self.content['revision'],'y','initial',plan['schedule_slot'],delivery_id,json.dumps(plan)))
            run=service.submit(dict(job_id='j2',scheduled_at_utc=now[0].isoformat(),phase='submit',source='console',request_kind='new_publication',mode='live'),'console')
            observed=service.observe(delivery_id,run['run_id'],1)
            admitted=service.admit(delivery_id,run['run_id'],1,observed['id'])
            service.approve(delivery_id,admitted['version'],admitted['context_hash'],'approve-'+delivery_id,'fixture-user')
            self.assertEqual(worker.tick()['delivery_id'],delivery_id)
        self.assertEqual(calls,['t','t2','t2']);self.assertEqual(len(self.store.list_productions()),1)
        production=self.store.get_production(self.production_unit_id)
        self.assertEqual(len(production['requirements']),1)
        owner_key=production['requirements'][0]['bucket_id']
        self.assertEqual(next(row for row in self.store.quota_buckets() if row['id']==owner_key)['reserved'],1)
        for delivery_id in ('d','d2','d3'):
            reservation=self.store.get_reservation(self.store.attempts(delivery_id)[0]['reservation_id'])
            self.assertEqual(reservation['production_ids'],[self.production_unit_id])

    def test_remote_success_then_database_failure_stays_uncertain(self):
        from common.operations.worker_service import WorkerService
        self.observe_quota();calls=[]
        def submit(*args):calls.append(1);return SubmissionResult('submitted',remote_id='remote-accepted')
        service=self.service(self.adapter(submit))
        with patch.object(self.store,'finish_attempt',side_effect=StoreError('storage_error')):
            result=WorkerService(service,clock=lambda:NOW,stop_event=threading.Event()).tick()
        self.assertEqual(result['reason_code'],'storage_error')
        self.assertTrue(self.store.attempts('d')[0]['request_started'])
        self.assertEqual(self.store.get_delivery('d')['state'],'submitting')
        WorkerService(self.service(self.adapter(submit)),clock=lambda:NOW,stop_event=threading.Event()).tick()
        self.assertEqual(calls,[1])

    def test_profile_wait_has_no_lease_and_stops_before_claim(self):
        from common.operations.worker_service import WorkerService
        from common.shared.axlock import Timeout
        self.observe_quota();stop=threading.Event();service=self.service(self.adapter());original=service.locks.acquire
        def acquire(resources,*args,**kwargs):
            if any(r.startswith('profile:') for r in resources):
                self.assertEqual(self.store.get_run(self.run)['state'],'queued')
                self.assertIsNone(self.store.get_run(self.run)['lease_expires_at'])
                stop.set();raise Timeout('fixture occupied')
            return original(resources,*args,**kwargs)
        with patch.object(service.locks,'acquire',side_effect=acquire):
            result=WorkerService(service,clock=lambda:NOW,stop_event=stop).tick()
        self.assertEqual(result['reason_code'],'worker_stopping');self.assertEqual(self.store.attempts('d'),[])

    def test_missing_reviews_and_expired_observation_never_admit(self):
        service=self.service(self.adapter())
        with self.store._db(True) as db:
            db.execute('DELETE FROM publication_approvals');db.execute('DELETE FROM operation_evidence');db.execute('DELETE FROM runtime_deliveries')
        observation=service.observe('d',self.run,1)
        service.clock=lambda:NOW+timedelta(hours=2)
        with self.assertRaises((StoreError,ContractError)):service.admit('d',self.run,1,observation['id'])
        service.clock=lambda:NOW
        with self.store._db(True) as db:db.execute("DELETE FROM content_evidence WHERE kind='independent_review'")
        with self.assertRaises((StoreError,ContractError)):service.admit('d',self.run,1,observation['id'])
        self.assertIsNone(self.store.get_delivery('d'))

    def test_verification_occurrence_reads_existing_delivery_without_submit(self):
        from common.operations.worker_service import WorkerService
        from common.operations.runtime_models import VerificationResult
        self.observe_quota();service=self.service(self.adapter())
        WorkerService(service,clock=lambda:NOW,stop_event=threading.Event()).tick()
        verify=self.store.submit_occurrence(dict(job_id='j',scheduled_at_utc=NOW.isoformat(),phase='verify',source='console',request_kind='new_publication',mode='live'))
        adapter=self.adapter(lambda *args:self.fail('verify 재제출'))
        adapter.verify=lambda ctx,remote,snapshot:VerificationResult('pending',NOW,{'reason':'media_evidence_required'})
        service=self.service(adapter)
        result=WorkerService(service,clock=lambda:NOW,stop_event=threading.Event()).tick()
        self.assertEqual(result['run_id'],verify['id']);self.assertEqual(result['state'],'unknown')
        self.assertEqual(self.store.get_delivery('d')['run_id'],self.run)
        self.assertEqual(self.store.get_run(verify['id'])['state'],'waiting')
        self.assertEqual(len(self.store.attempts('d')),1)
        self.assertEqual(self.store.events('d')[-1]['evidence']['evidence']['reason'],'media_evidence_required')


class BridgeAdmissionTests(unittest.TestCase):
    def test_registered_adapters_reject_admission_context_for_prepare_or_submit(self):
        from tests.publishers.test_blogs import registry as blogs
        from tests.publishers.test_youtube import registry as youtube
        from common.publishers import build_adapters
        from common.operations.admission_context import AdmissionReadContext
        blog=blogs();video=youtube()
        registry=replace(blog,connections={**blog.connections,**video.connections},credentials={**blog.credentials,**video.credentials})
        class Bridge:
            def read(self,*args):raise AssertionError('prepare 읽기 금지')
            def submit(self,*args):raise AssertionError('read context 제출 금지')
        adapters=build_adapters(registry=registry,bridge=Bridge())
        self.assertEqual(set(adapters),{'dept.blogger','personal.blogger','dept.naver_blog','personal.naver_blog','personal.tistory','dept.youtube','personal.youtube'})
        for key,adapter in adapters.items():
            connection=registry.connections[key]
            context=AdmissionReadContext(key,connection.account_id,connection.target_id,connection.platform,registry.revision,connection.account_id,'policy','run','plan',1)
            with self.assertRaises(ContractError):adapter.prepare(context,{})
            with self.assertRaises(ContractError):adapter.submit(context,{},None)

    def test_first_observation_uses_real_child_without_publication_context(self):
        from tests.publishers.test_legacy_bridge import BridgeTests
        from common.operations.admission_context import AdmissionReadContext
        fixture=BridgeTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        fixture.module.write_text(fixture.fixture_source().replace("'execution_owner':'managed'","'execution_owner':'managed','schedule_owner':'console'"))
        with fixture.store._db(True) as db:
            db.execute('DELETE FROM publication_approvals');db.execute('DELETE FROM operation_evidence');db.execute('DELETE FROM runtime_deliveries')
        context=AdmissionReadContext('x','personal','t','tistory','r','personal','p',fixture.run,'d',1)
        with fixture.held():
            result=fixture.bridge().read('fixture','inspect_target',context,{})
            self.assertEqual(result['target_id'],'t')
            for action in ('lookup','verify','publish'):
                with self.assertRaises(ContractError):fixture.bridge().read('fixture',action,context,{})
        self.assertIsNone(fixture.store.get_delivery('d'));self.assertFalse(fixture.marker.exists())



del _GateFixture
