"""단일 dispatcher와 별도 연결 heartbeat. SIGTERM은 진행 중 요청을 drain한다."""
from contextlib import contextmanager
from datetime import datetime, timezone
import signal
import threading
import time
from .content_store import StoreError, ConflictError
from .models import ContractError
from .dispatch import heartbeat, run_is_due
from .runtime_models import utc
from .production_models import ProductionRequest
from .provider_policy import resolve_job_provider_policy
from .production import produce_content
from .worker import run_once, _identity
from common.shared.axlock import Timeout, ControlBlocked


class WorkerService:
    def __init__(self,services,*,clock=None,stop_event=None,heartbeat_interval=10,production_quota_preparer=None):
        if type(heartbeat_interval) not in (int,float) or not 0<heartbeat_interval<60:raise StoreError('invalid')
        if production_quota_preparer is not None and not callable(production_quota_preparer):raise StoreError('invalid')
        self.production_quota_preparer=production_quota_preparer
        self.services=services;self.clock=clock or (lambda:datetime.now(timezone.utc))
        self.stop_event=stop_event if stop_event is not None else threading.Event()
        self.heartbeat_interval=heartbeat_interval;self.active_lease=None
        self._mutex=threading.RLock();self._lease_lost=False;self._heartbeat_stop=None;self._thread=None
        self._pending_fences=[]

    def handle_signal(self,signum,frame):
        self.stop_event.set()

    def check(self):
        if self.stop_event.is_set():raise ContractError('worker_stopping')
        if self._lease_lost and self.active_lease is not None:raise ContractError('heartbeat_lost')
        self.services.require_enabled()

    def __call__(self,lease):
        if lease is None:
            if self._heartbeat_stop:self._heartbeat_stop.set()
            if self._thread:self._thread.join(timeout=6)
            with self._mutex:
                lease=self.active_lease
                if lease is not None and self._lease_lost:self._pending_fences.append(lease)
                self.active_lease=None;self._lease_lost=False
            self._thread=None
            try:self._drain_fences()
            except (StoreError,ContractError):pass  # DB 복구 후 다음 claim 전에 다시 격리한다.
            return
        with self._mutex:
            self.active_lease=lease;self._lease_lost=False
        self._heartbeat_stop=threading.Event()
        self._thread=threading.Thread(target=self._heartbeat_loop,name='managed-heartbeat',daemon=True)
        self._thread.start()

    def _drain_fences(self):
        while self._pending_fences:
            lease=self._pending_fences[0]
            self.services.store.fence_lost_lease(lease,self.clock())
            self._pending_fences.pop(0)

    def _heartbeat_loop(self):
        while not self._heartbeat_stop.wait(self.heartbeat_interval):
            if not self.heartbeat_once():return

    def heartbeat_once(self):
        with self._mutex:
            if self.active_lease is None:return False
            try:
                ok=heartbeat(self.services.store,self.active_lease,self.clock())
                if ok:
                    from .publication_gate import fresh_lease
                    self.active_lease=fresh_lease(self.services.store,self.active_lease.run_id,self.clock())
            except Exception:ok=False
            if not ok:self._lease_lost=True
            return ok

    @contextmanager
    def hold_profile(self,resources,**kwargs):
        # 짧은 잠금 시도 사이에서 SIGTERM을 확인한다. 아직 run lease는 없다.
        deadline=time.monotonic()+kwargs.get('wait',2400)
        while True:
            self.check()
            try:
                held=self.services.locks.acquire(resources,kwargs['job'],wait=0)
                break
            except Timeout:
                if time.monotonic()>=deadline:raise
                self.stop_event.wait(.1)
        try:
            self.check();yield
        finally:self.services.locks._release(held)

    def _production_request(self,run):
        occurrence=run['occurrence'];job=self.services.registry.jobs.get(occurrence['job_id'])
        if not job or job.get('kind')!='production' or not job.get('binding_id'):raise StoreError('invalid_binding')
        self.services.assert_run_authority(run)
        policy=resolve_job_provider_policy(dict(job,id=occurrence['job_id']),self.services.registry,self.services.policy)
        binding=next((b for b in self.services.production_store.list_bindings() if b['binding_id']==job['binding_id']),None)
        if not binding:raise StoreError('binding_not_found')
        payload=binding['input_payload']
        request=ProductionRequest(binding['base_job_id'],binding['owner_account_id'],binding['binding_id']+':'+run['id'],
            binding['content_id'],binding['content_revision'],payload['brief'],payload['required_outputs'])
        return request,policy

    def _review(self,result,request,producer,*,execute):
        if result.get('status')!='completed':return result
        from types import SimpleNamespace
        from .publication_gate import validate_reviews
        from .review_runner import run_reviews
        snapshot=self.services.store.content_store.get(result['content_id'],result['revision'])
        job=self.services.registry.jobs[request.job_id]
        authorities=self.services.registry.policies[job['policy_revision']]
        rows=self.services.store.read_content_evidence(result['content_id'],result['revision'],result['manifest_hash'])
        reports=[row['report'] for row in rows if row['kind']=='independent_review']
        subject=SimpleNamespace(content_id=result['content_id'],content_revision=result['revision'],manifest_hash=result['manifest_hash'])
        try:
            validate_reviews(dict(producer=result['producer'],reports=reports),authorities,subject,
                [dict(kind=row['kind'],evidence=row['report']) for row in rows],self.clock())
            return dict(result,review=dict(status='completed',reason_code=None))
        except ContractError:pass
        previous=self.services.store.get_service_run_result(request.occurrence_id.split(':',1)[1])
        if (previous or {}).get('review',{}).get('status') in ('running','unknown'):
            return dict(result,review=dict(status='unknown',reason_code='review_execution_uncertain'))
        runner=producer.get('review_runner') if producer else None
        if runner is None or not execute:
            return dict(result,review=dict(status='required',reason_code='independent_review_required'))
        self.check()
        # 검토 실행 전 durable intent. crash 뒤 같은 모델 검토를 자동 재호출하지 않는다.
        with self._mutex:
            self.services.store.record_service_progress(self.active_lease,dict(result,review=dict(status='running')),self.clock())
        reviewed=run_reviews(snapshot,producer=result['producer'],authorities=authorities,runner=runner,
            runtime_store=self.services.store,now=self.clock())
        return dict(result,review=dict(status=reviewed['status'],reason_code=reviewed.get('reason_code')))

    def _prepare(self,run):
        request,policy=self._production_request(run)
        producer=self.services.producers.get(request.job_id)
        if not producer or not hasattr(producer.get('provider'),'generate'):raise StoreError('producer_unavailable')
        self.check()
        lease=self.services.store.claim_run(run['id'],'managed-production',_identity(),self.clock(),expected_version=run['version'])
        self(lease)
        try:
            self.check()
            now=utc(self.clock())
            if self.production_quota_preparer is not None:
                self.production_quota_preparer(self.services.store,self.services.base_registry,now)
            result=produce_content(request,provider=producer['provider'],media_runner=producer.get('media_runner',{}),
                content_store=self.services.store.content_store,production_store=self.services.production_store,
                runtime_store=self.services.store,policy=policy,now=now)
            result=self._review(result,request,producer,execute=True)
        except (StoreError,ContractError) as error:
            if 'result' in locals() and result.get('status')=='completed':
                result=dict(result,review=dict(status='blocked',reason_code=error.code))
            else:result=dict(status='blocked',reason_code=error.code)
        finally:self(None)
        current=self.services.store.get_run(run['id'])
        self.services.store.finish_service_run(run['id'],current['version'],result)
        return dict(state=result['status'],run_id=run['id'],production_unit_id=request.production_unit_id,review_status=result.get('review',{}).get('status'))

    def _restore_completed_production(self):
        # A5 finish/bind 뒤 worker 기록이 끊긴 경우만 처리한다. running/unknown producer 재시작 없음.
        for run in self.services.store.list_runs('running'):
            occurrence=run.get('occurrence') or {}
            if occurrence.get('mode')!='live' or occurrence.get('phase')!='prepare':continue
            try:request,policy=self._production_request(run)
            except (ContractError,StoreError) as error:
                if error.code=='storage_error':raise
                # 과거 실행의 불확실 상태를 보존하면서 다른 회차의 처리는 계속한다.
                continue
            attempt=self.services.production_store.get(request.production_unit_id)
            if not attempt or not attempt['result'] or attempt['state']=='running':continue
            result=attempt['result']
            if result.get('status')=='completed':
                self.services.store.bind_production_output(request.production_unit_id,result['content_id'],result['revision'],result['manifest_hash'],expected_production_version=attempt['version'])
                self.services.store.settle_production(request.production_unit_id,now=self.clock())
            result=self._review(result,request,self.services.producers.get(request.job_id),execute=False)
            self.services.store.finish_service_run(run['id'],run['version'],result)
            return dict(state=result['status'],run_id=run['id'])

    def _verify(self,run):
        job_id=run['occurrence']['job_id'];job=self.services.registry.jobs.get(job_id)
        if not job or job.get('enabled') is not True or job.get('execution_owner')!='managed':raise StoreError('job_disabled')
        resolve_job_provider_policy(dict(job,id=job_id),self.services.registry,self.services.policy)
        connections=job.get('connection_ids') or (job.get('connection_id'),)
        targets=[]
        for delivery in self.services.store.list_operations():
            original=self.services.store.get_run(delivery['run_id'])
            if (original and original['occurrence'].get('job_id')==job_id
                and delivery['context']['owner_account_id']==job.get('owner_account_id')
                and delivery['context']['connection_id'] in connections
                and delivery['state'] in ('uploaded','scheduled','published','unknown','needs_review')):targets.append(delivery)
        if not targets:
            result=dict(status='completed',reason_code='no_verification_targets',deliveries=[])
            self.services.store.finish_service_run(run['id'],run['version'],result)
            return dict(state='completed',run_id=run['id'],noop=True)
        resources=[]
        for delivery in targets:
            connection=self.services.registry.connections[delivery['context']['connection_id']]
            if connection.id not in self.services.adapters:raise StoreError('adapter_unavailable')
            profile=self.services.registry.profiles.get(connection.profile_ref)
            if not profile or profile.get('account_id')!=connection.account_id:raise StoreError('profile_lock_required')
            resources.append(profile['lock_resource'])
        outcomes=[]
        # 모든 대상 잠금을 확보하기 전에는 verify run lease도 잡지 않는다.
        with self.hold_profile(resources,job='managed-verification',wait=2400):
            self.check()
            current=self.services.store.get_run(run['id'])
            if not run_is_due(current,self.clock()):return {'state':'idle'}
            lease=self.services.store.claim_run(run['id'],'managed-verification',_identity(),self.clock(),expected_version=current['version'])
            self(lease)
            try:
                for delivery in targets:
                    self.check()
                    from .verification import verify_delivery
                    from .recovery import reconcile_delivery
                    current=self.services.store.get_delivery(delivery['id']);ctx=current['context']
                    adapter=self.services.adapters[ctx['connection_id']]
                    if current['state'] in ('unknown','needs_review'):
                        reconcile_delivery(self.services.store,current['id'],adapter,self.clock(),expected_version=current['version'],
                            request_key='verify:'+run['id']+':'+current['id'])
                        outcome='verified' if self.services.store.get_delivery(current['id'])['state']=='verified' else 'pending'
                    else:
                        snapshot=self.services.store.content_store.get(ctx['content_id'],ctx['content_revision'])
                        outcome=verify_delivery(self.services.store,current['id'],adapter,snapshot,now=self.clock(),expected_version=current['version']).outcome
                    outcomes.append(dict(delivery_id=current['id'],outcome=outcome))
            except (ContractError,StoreError) as error:
                outcomes.append(dict(outcome='pending',reason_code=error.code))
            finally:self(None)
        result=dict(status='completed' if len(targets)==len(outcomes) and all(row['outcome']=='verified' for row in outcomes) else 'unknown',deliveries=outcomes)
        current=self.services.store.get_run(run['id'])
        self.services.store.finish_service_run(run['id'],current['version'],result)
        return dict(state=result['status'],run_id=run['id'])

    def tick(self):
        if not self.services.policy.enabled:return {'state':'disabled'}
        if self.stop_event.is_set():return {'state':'stopped'}
        try:
            self.check()
            with self.services.locks.hold(['service:managed-worker'],job='managed-worker',wait=0):
                self._drain_fences()
                self.check();self.services.refresh_registry()
                restored=self._restore_completed_production()
                if restored:return restored
                last_result=None
                for run in self.services.store.list_runs('queued'):
                    occurrence=run.get('occurrence') or {}
                    if occurrence.get('mode')!='live' or not run_is_due(run,self.clock()):continue
                    phase=occurrence.get('phase')
                    if phase not in ('prepare','verify'):continue
                    try:
                        result=self._prepare(run) if phase=='prepare' else self._verify(run)
                        if not result.get('noop'):return result
                        last_result=result
                    except (ContractError,StoreError) as error:
                        if error.code in ('storage_error','control_blocked','worker_stopping','heartbeat_lost'):raise
                        current=self.services.store.get_run(run['id'])
                        if current['state']!='queued':raise
                        self.services.store.finish_service_run(run['id'],current['version'],dict(status='blocked',reason_code=error.code))
                        last_result=dict(state='blocked',run_id=run['id'],reason_code=error.code)
                delivery=run_once(self.services.store,self.services.registry,self.services.adapters,self.services.policy,
                    self.services.locks,self.clock(),lease_observer=self)
                return dict(state='processed',delivery_id=delivery) if delivery else last_result or {'state':'idle'}
        except Timeout:return {'state':'busy'}
        except ControlBlocked:return {'state':'blocked','reason_code':'control_blocked'}
        except (ContractError,StoreError) as error:return {'state':'blocked','reason_code':error.code}

    def run(self,once=False):
        if not self.services.policy.enabled:return 0
        previous={}
        if threading.current_thread() is threading.main_thread():
            for signum in (signal.SIGTERM,signal.SIGINT):previous[signum]=signal.signal(signum,self.handle_signal)
        try:
            while not self.stop_event.is_set():
                self.tick()
                if once:break
                self.stop_event.wait(.25)
            return 0
        finally:
            self(None)
            for signum,handler in previous.items():signal.signal(signum,handler)
