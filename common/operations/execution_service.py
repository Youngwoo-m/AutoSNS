"""서버 등록 입력만 소비하는 제작·admission·별도 발행 승인 서비스."""
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import replace
from .models import Registry, ContractError, thaw
from .content_store import StoreError, ConflictError
from .runtime_models import ExecutionPolicy, utc
from .runtime_store import digest
from .dispatch import _FIELDS
from .execution_receipts import ReceiptDispatchStore,receipt_context,pending_receipt,validate_receipt,permits_binding
from .entrypoints import submit_registered, resolve_entrypoint
from .provider_policy import resolve_job_provider_policy
from .admission_context import AdmissionReadContext, validate_admission_read
from .publication_gate import build_publication_context, _clear, check_policy

_FORBIDDEN={'production_unit_id','production_id','owner_account_id','credential_ref','binding_id','input_payload'}


def _safe_options(value):
    if isinstance(value,Mapping):
        if set(value)&_FORBIDDEN:raise StoreError('invalid_request')
        for item in value.values():_safe_options(item)
    elif isinstance(value,(list,tuple)):
        for item in value:_safe_options(item)


def resolve_execution_registry(base_registry, bindings, catalog,*,receipts=()):
    if not isinstance(base_registry,Registry):raise StoreError('invalid_registry')
    jobs={key:thaw(value) for key,value in base_registry.jobs.items() if not value.get('base_job_id')}
    for binding in bindings:
        payload=binding.get('input_payload',{})
        if (digest(payload)!=binding.get('binding_id') or binding.get('execution_job_id')!='production.'+binding.get('binding_id','')
            or any(payload.get(key)!=binding.get(key) for key in ('base_job_id','content_id','content_revision','manifest_hash','owner_account_id','policy_revision','registry_revision'))):
            raise StoreError('invalid_binding')
        base=jobs.get(binding['base_job_id'])
        # 오래된 binding은 원장에 보존하되 실행 가능한 registry에 복원하지 않는다.
        if (not base or base.get('kind')!='production' or base.get('enabled') is not True
            or base.get('execution_owner')!='managed' or base.get('schedule_owner') not in ('console','launchd')
            or binding['registry_revision']!=base_registry.revision
            or binding['policy_revision']!=base.get('policy_revision')
            or binding['owner_account_id']!=base.get('owner_account_id')
            or thaw(base.get('required_outputs'))!=payload.get('required_outputs')
            or ('brief' in base and thaw(base['brief'])!=payload.get('brief'))
            or binding['base_job_id'] not in catalog.production_jobs):continue
        spec=catalog.executors.get(base.get('executor_id'))
        if not spec or binding['base_job_id'] not in spec.job_ids or 'prepare' not in spec.phases:continue
        if not any(permits_binding(receipt,base_registry,catalog,binding) for receipt in receipts):continue
        jobs[binding['execution_job_id']]=dict(base,id=binding['execution_job_id'],base_job_id=binding['base_job_id'],binding_id=binding['binding_id'])
    return replace(base_registry,jobs=jobs)


class ExecutionService:
    def __init__(self,store,ledger,registry,catalog,policy,adapters,producers,production_store,locks,clock):
        if not isinstance(registry,Registry):raise StoreError('invalid_registry')
        self.store,self.ledger,self.base_registry,self.catalog=store,ledger,registry,catalog
        self.policy,self.adapters,self.producers=policy,dict(adapters),dict(producers)
        self.production_store,self.locks,self.clock=production_store,locks,clock
        self.refresh_registry()
        for item in (store,production_store):item.execution_policy=policy;item.locks=locks

    def refresh_registry(self,*,pending=None):
        receipts=self.store.list_execution_receipts()
        if pending is not None:receipts.append(pending)
        self.registry=resolve_execution_registry(self.base_registry,self.production_store.list_bindings(),self.catalog,receipts=receipts)
        self.store.registry=self.registry;self.production_store.registry=self.registry;self.ledger.registry_source=self.registry
        for adapter in self.adapters.values():
            if hasattr(adapter,'registry'):adapter.registry=self.registry
            if hasattr(adapter,'bridge'):adapter.bridge.registry=self.registry
        return self.registry

    def assert_run_authority(self,run):
        receipt=self.store.get_execution_receipt(run['id'])
        return validate_receipt(receipt,self.base_registry,self.catalog,execution_job_id=run['occurrence']['job_id'])

    def _dispatch(self,request,caller_id):
        receipt=receipt_context(request,caller_id,self.registry)
        result=submit_registered(request,caller_id=caller_id,store=ReceiptDispatchStore(self.store,receipt),
            registry=self.registry,policy=self.policy,catalog=self.catalog,production_policy_resolver=resolve_job_provider_policy)
        if result.get('id'):self.assert_run_authority(self.store.get_run(result['id']))
        return result

    def require_enabled(self):
        if not isinstance(self.policy,ExecutionPolicy) or not self.policy.enabled:raise ContractError('execution_disabled')
        _clear(self.store)

    def submit(self,request,caller_id,*,content_id=None,expected_revision=None):
        if (not isinstance(request,dict) or set(request)!=_FIELDS or request.get('mode') not in ('dry','shadow','live')
            or request.get('request_kind') not in ('new_publication','resume')):raise StoreError('invalid_request')
        self.refresh_registry()
        if request['phase']=='prepare':
            if not isinstance(content_id,str) or type(expected_revision) is not int or expected_revision<1:raise StoreError('invalid_request')
            base_id=request['job_id'];base=self.registry.jobs.get(base_id)
            if not base or base.get('kind')!='production' or base.get('base_job_id'):raise StoreError('unknown_production_job')
            # 접수 검증을 먼저 수행한다. binding이 저장돼도 producer는 worker만 호출한다.
            route=resolve_entrypoint(caller_id,base_id,self.registry,self.catalog)
            if route['route']!='managed':raise StoreError('legacy_owner')
            if route['source']!=request['source']:raise StoreError('source_mismatch')
            if base.get('enabled') is not True:raise StoreError('job_disabled')
            if request['mode']=='live':self.require_enabled()
            # shadow dispatch의 전체 검증을 먼저 실행하고 durable binding 뒤 실제 dispatch한다.
            check=dict(request,mode='shadow')
            submit_registered(check,caller_id=caller_id,store=self.store,registry=self.registry,policy=self.policy,catalog=self.catalog,production_policy_resolver=resolve_job_provider_policy)
            snapshot=self.store.content_store.get(content_id,expected_revision)
            if snapshot is None:raise StoreError('not_found')
            if request['mode']=='shadow':return dict(check,state='shadow',content_id=content_id,content_revision=expected_revision,manifest_hash=snapshot['manifest_hash'])
            try:
                binding=self.production_store.bind_input(base_id,snapshot,dict(base,id=base_id),self.registry.revision,
                    create=request['request_kind']!='resume')
            except StoreError as error:
                if request['request_kind']=='resume' and error.code=='binding_not_found':
                    raise StoreError('unknown_occurrence') from None
                raise
            # 저장 전 검증한 원래 caller/source로 새 binding의 접수만 허용한다.
            pending=pending_receipt(request,caller_id,self.base_registry)
            pending['occurrence']['job_id']=binding['execution_job_id']
            self.refresh_registry(pending=pending)
            if binding['execution_job_id'] not in self.registry.jobs:raise StoreError('invalid_binding')
            result=self._dispatch(dict(request,job_id=binding['execution_job_id']),caller_id)
            return dict(run_id=result['id'],**{key:binding[key] for key in ('binding_id','base_job_id','execution_job_id','content_id','content_revision','manifest_hash')})
        if content_id is not None or expected_revision is not None:raise StoreError('invalid_request')
        result=self._dispatch(request,caller_id)
        return dict(result,**({'run_id':result['id']} if 'id' in result else {}))

    def _plan(self,delivery_id,run_id,version):
        self.require_enabled()
        if type(version) is not int or version<1:raise StoreError('invalid')
        plan=self.store.get_plan_delivery(delivery_id)
        if not plan or plan.get('version',1)!=version or plan.get('status')=='cancelled':raise ConflictError()
        _safe_options(plan.get('options',{}))
        run=self.store.get_run(run_id);occurrence=(run or {}).get('occurrence') or {}
        job=self.registry.jobs.get(occurrence.get('job_id'))
        connection=self.registry.connections.get(plan.get('connection_id'))
        if (not job or not connection or occurrence.get('mode')!='live' or occurrence.get('phase')!='submit'
            or job.get('enabled') is not True or job.get('execution_owner')!='managed'
            or job.get('owner_account_id')!=plan.get('owner_account_id')
            or connection.id not in (job.get('connection_ids') or (job.get('connection_id'),))):raise ContractError('publication_run_required')
        check_policy(self.policy,connection,self.registry.policies[job['policy_revision']],job=dict(job,id=occurrence['job_id']))
        ctx=AdmissionReadContext(connection.id,connection.account_id,connection.target_id,connection.platform,self.registry.revision,
            plan['owner_account_id'],job['policy_revision'],run_id,delivery_id,version)
        validate_admission_read(self.store,self.registry,ctx)
        return plan,ctx

    @contextmanager
    def _profile(self,connection_id):
        connection=self.registry.connections.get(connection_id)
        profile=self.registry.profiles.get(connection.profile_ref) if connection else None
        if not profile or profile.get('account_id')!=connection.account_id or not str(profile.get('lock_resource','')).startswith('profile:'):
            raise ContractError('profile_lock_required')
        with self.locks.hold([profile['lock_resource']],job='managed-observation',wait=2400):
            self.require_enabled();yield

    def observe(self,delivery_id,run_id,expected_version):
        plan,ctx=self._plan(delivery_id,run_id,expected_version)
        adapter=self.adapters.get(ctx.connection_id)
        if adapter is None:raise StoreError('adapter_unavailable')
        with self._profile(ctx.connection_id):
            self._plan(delivery_id,run_id,expected_version)
            observed=adapter.inspect_target(ctx)
            self._plan(delivery_id,run_id,expected_version)
            return self.store.record_admission_observation(delivery_id,run_id,expected_version,self.registry.revision,observed,self.clock())

    def admit(self,delivery_id,run_id,expected_version,observation_id):
        plan,readctx=self._plan(delivery_id,run_id,expected_version)
        observation=self.store.get_admission_observation(observation_id)
        if (not observation or any(observation[key]!=value for key,value in
            (('planned_delivery_id',delivery_id),('run_id',run_id),('plan_version',expected_version),('registry_revision',self.registry.revision)))):
            raise ContractError('admission_observation_required')
        rows=self.store.read_content_evidence(plan['content_id'],plan['revision'],plan['manifest_hash'])
        producers=[r['report'] for r in rows if r['kind']=='production_provenance']
        reports=[r['report'] for r in rows if r['kind']=='independent_review']
        ctx=build_publication_context(self.store,delivery_id,observation['observation'],dict(producer=producers[-1] if producers else None,reports=reports),self.policy,self.clock(),run_id=run_id)
        # A5 managed 출력은 기존 unit 증거를 확인한다. 새 owner hold를 만들지 않는다.
        self.store.get_production_for_output(ctx.content_id,ctx.content_revision,ctx.manifest_hash)
        return self.store.create_delivery(delivery_id,run_id,ctx,planned_version=expected_version,observation_id=observation_id)

    def approve(self,delivery_id,expected_version,context_hash,request_key,actor):
        self.require_enabled()
        if not isinstance(request_key,str) or not request_key or not isinstance(actor,str) or not actor:raise StoreError('invalid')
        replay=self.store.get_publication_approval_replay(delivery_id,request_key,expected_version,context_hash,actor)
        if replay is not None:return replay
        delivery=self.store.get_delivery(delivery_id)
        if not delivery:raise StoreError('not_found')
        from .runtime_models import PublicationContext
        ctx=PublicationContext(**delivery['context'])
        # 현재 plan/registry/review/auth를 재검증한다. 승인 생성 자체는 _inputs의 기존승인을 요구하지 않는다.
        rows=self.store.read_content_evidence(ctx.content_id,ctx.content_revision,ctx.manifest_hash)
        producers=[r['report'] for r in rows if r['kind']=='production_provenance']
        reports=[r['report'] for r in rows if r['kind']=='independent_review' and r['report'].get('report_hash') in ctx.review_report_hashes]
        observations=[r['evidence'] for r in self.store.events(delivery_id) if r['kind']=='target_observation']
        if not producers or not observations:raise ContractError('publication_evidence_required')
        current=build_publication_context(self.store,delivery_id,observations[-1],dict(producer=producers[-1],reports=reports),self.policy,self.clock(),run_id=ctx.run_id)
        if current.context_hash!=context_hash:raise ConflictError()
        approval_hash=digest(dict(delivery_id=delivery_id,version=expected_version,context_hash=context_hash,request_key=request_key,actor=actor))
        approval=self.store.record_publication_approval(delivery_id,expected_version,context_hash,approval_hash,ctx.review_report_hashes,actor=actor,request_key=request_key)
        return approval

    def status(self,run_id=None):
        if run_id is None:
            jobs=[dict(id=key,owner_account_id=job.get('owner_account_id'),required_outputs=thaw(job.get('required_outputs',())))
                  for key,job in self.registry.jobs.items() if job.get('kind')=='production' and not job.get('base_job_id')
                  and key in self.catalog.production_jobs and job.get('enabled') is True and job.get('execution_owner')=='managed']
            return dict(enabled=self.policy.enabled,state='ready' if self.policy.enabled else 'disabled',production_jobs=jobs,
                capabilities=dict(submit=self.policy.enabled,observe=self.policy.enabled and bool(self.adapters),approve=self.policy.enabled))
        run=self.store.get_run(run_id)
        if run is None:raise StoreError('not_found')
        deliveries=[]
        for delivery in self.store.list_operations():
            if delivery['run_id']!=run_id:continue
            attempts=self.store.attempts(delivery['id'])
            evidence=((attempts[-1].get('result') or {}).get('evidence') or {}) if attempts else {}
            actions=('thumbnail','playlist','comment','caption','public_switch','tiktok')
            raw_intents=evidence.get('followup_intents')
            raw_intents=raw_intents if isinstance(raw_intents,(tuple,list)) else ()
            intents=[dict(action=item['action'],state='not_started',required=True,separate_approval_required=True)
                for item in raw_intents if isinstance(item,Mapping) and item.get('action') in actions
                and item.get('required') is True]
            deliveries.append(dict(delivery,followup_intents=intents,followup_completion='pending' if intents else 'not_required'))
        return dict(run_id=run_id,state=run['state'],version=run['version'],deliveries=deliveries,production=self.store.get_service_run_result(run_id))

    def status_info(self):
        """HTTP 조립용 안전 metadata. 비활성/legacy도 숨기지 않고 사유를 표시한다."""
        result=dict(enabled=self.policy.enabled,production_jobs=[],publication_jobs=[],
            capabilities={key:self.policy.enabled for key in ('request','observe','admit','approve')},
            blockers=[] if self.policy.enabled else ['execution_disabled'])
        for key,job in self.base_registry.jobs.items():
            if job.get('base_job_id'):continue
            production=job.get('kind')=='production'
            spec=self.catalog.executors.get(job.get('executor_id'))
            available=bool(self.policy.enabled and job.get('enabled') is True and job.get('execution_owner')=='managed'
                and spec and key in spec.job_ids and (not production or key in self.catalog.production_jobs))
            reason=('execution_disabled' if not self.policy.enabled else 'legacy_owner' if job.get('execution_owner')!='managed'
                else 'job_disabled' if job.get('enabled') is not True else 'unknown_executor')
            row=dict(id=key,label=key,enabled=job.get('enabled') is True,available=available,owner_account_id=job.get('owner_account_id'),
                phases=['prepare'] if production else ['submit','verify'],
                connection_ids=[] if production else list(job.get('connection_ids') or ([job['connection_id']] if job.get('connection_id') else [])))
            if not available:row['reason']=reason
            result['production_jobs' if production else 'publication_jobs'].append(row)
        return result

    def _read_scope(self,delivery):
        ctx=delivery['context'];run=self.store.get_run(delivery['run_id'])
        occurrence=(run or {}).get('occurrence') or {};job=self.registry.jobs.get(occurrence.get('job_id'))
        connection=self.registry.connections.get(ctx['connection_id'])
        if (not job or job.get('enabled') is not True or job.get('execution_owner')!='managed'
            or job.get('owner_account_id')!=ctx['owner_account_id'] or job.get('policy_revision')!=ctx['policy_revision']
            or ctx['registry_revision']!=self.registry.revision or not connection
            or connection.target_id!=ctx['target_id'] or connection.account_id!=ctx['destination_account_id']
            or connection.id not in (job.get('connection_ids') or (job.get('connection_id'),))
            or occurrence.get('phase')!='submit' or occurrence.get('mode')!='live'):
            raise ContractError('publication_context_changed')
        check_policy(self.policy,connection,self.registry.policies.get(job['policy_revision']),job=dict(job,id=occurrence['job_id']))

    def verify(self,delivery_id,*,expected_version):
        from .verification import verify_delivery
        self.require_enabled();delivery=self.store.get_delivery(delivery_id)
        if not delivery:raise StoreError('not_found')
        self._read_scope(delivery)
        ctx=delivery['context'];snapshot=self.store.content_store.get(ctx['content_id'],ctx['content_revision'])
        with self._profile(ctx['connection_id']):
            return verify_delivery(self.store,delivery_id,self.adapters.get(ctx['connection_id']),snapshot,now=self.clock(),clock=self.clock,expected_version=expected_version).to_dict()

    def reconcile(self,delivery_id,*,expected_version,request_key,actor='recovery_service'):
        from .recovery import reconcile_delivery
        self.require_enabled();delivery=self.store.get_delivery(delivery_id)
        if not delivery:raise StoreError('not_found')
        self._read_scope(delivery)
        with self._profile(delivery['context']['connection_id']):
            return reconcile_delivery(self.store,delivery_id,self.adapters.get(delivery['context']['connection_id']),self.clock(),expected_version=expected_version,request_key=request_key,actor=actor)
