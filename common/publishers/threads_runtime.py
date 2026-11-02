"""Threads의 서버 명시 조립. 기본 등록·자격·API·journal 초기화는 하지 않는다."""
from collections.abc import Mapping
from datetime import datetime,timezone,timedelta
from pathlib import Path
from types import MappingProxyType
import sys
from common.operations.admission_context import decode_bridge_context
from common.operations.execution_catalog import ExecutionCatalog,ExecutorSpec
from common.operations.models import ContractError
from common.operations.runtime_models import utc

THREADS_BINDINGS=MappingProxyType({'personal.threads':'threads.personal','dept.threads':'threads.dept'})

def build_threads_catalog(registry,*,configured=False,interpreter=None,cwd=None):
    if configured is not True:return ExecutionCatalog()
    executors={}
    for identifier,executor in THREADS_BINDINGS.items():
        connection=registry.connections.get(identifier)
        if not connection or not connection.enabled or connection.platform!='threads' or not connection.target_id:continue
        jobs=tuple(key for key,job in registry.jobs.items() if job.get('executor_id')==executor and job.get('enabled') is True
            and job.get('execution_owner')=='managed' and job.get('managed_eligible') is True
            and identifier in (job.get('connection_ids') or (job.get('connection_id'),)))
        if jobs:
            executors[executor]=ExecutorSpec(executor,jobs,('submit','verify'),interpreter or str(Path(sys.executable).absolute()),
                cwd or Path(__file__).resolve().parents[2],'common.publishers.threads',('publish',),('LANG','LC_ALL','TZ','PATH'))
    return ExecutionCatalog(executors)

def build_threads_handlers(registry,*,services_factory,clock=None,before_write=None):
    if not callable(services_factory):raise ContractError('threads_service_required')
    clock=clock or (lambda:datetime.now(timezone.utc));handlers={}
    for identifier,executor in THREADS_BINDINGS.items():
        if identifier not in registry.connections:continue
        def handler(context,payload,credentials,*,connection_id=identifier,action='inspect_target'):
            ctx=decode_bridge_context(context,action);connection=registry.connections[connection_id]
            if (ctx.connection_id!=connection_id or ctx.platform!='threads' or connection.platform!='threads'
                    or ctx.destination_account_id!=connection.account_id or ctx.target_id!=connection.target_id
                    or not ctx.target_id or ctx.registry_revision!=registry.revision):raise ContractError('threads_context_mismatch')
            services=services_factory(connection_id,credentials)
            if before_write is not None:services.before_write=before_write
            target=dict(platform='threads',target_id=ctx.target_id,expected_login_subject=connection.expected_login_subject)
            if action=='inspect_target':
                result=services.inspect(target);now=utc(clock())
                return dict(result,checked_at=now.isoformat(),expires_at=(now+timedelta(minutes=5)).isoformat())
            if action=='publish':
                for key in ('platform','connection_id','target_id','owner_account_id','destination_account_id','content_id','content_revision','manifest_hash','publication_purpose','schedule_slot'):
                    if payload.get(key)!=getattr(ctx,key):raise ContractError('threads_prepared_mismatch')
                return services.submit(payload,target)
            if action=='lookup':
                rows=services.lookup(target,payload.get('attempt',{}))
                if not isinstance(rows,(list,tuple)):raise ContractError('threads_observation_invalid')
                return dict(candidates=[dict(row,destination_account_id=ctx.destination_account_id) for row in rows],checked_at=utc(clock()).isoformat())
            row=services.read_post(target,payload.get('remote_id'))
            return dict(observation=dict(row,destination_account_id=ctx.destination_account_id) if row is not None else None,checked_at=utc(clock()).isoformat())
        for action in ('inspect_target','publish','lookup','verify'):
            def bound(context,payload,credentials,*,_handler=handler,_action=action):return _handler(context,payload,credentials,action=_action)
            handlers[(executor,action)]=bound
    return handlers

def build_threads_host(registry,catalog,store,locks,*,services_factory,credential_catalog,credential_resolver,clock=None,module_root=None):
    from .bridge_host import BridgeHost
    from .legacy_bridge import _clear
    return BridgeHost(registry,catalog,store,locks,build_threads_handlers(registry,services_factory=services_factory,clock=clock,before_write=lambda:_clear(locks)),
        credential_catalog=credential_catalog,credential_resolver=credential_resolver,clock=clock,module_root=module_root)

def bridge_bootstrap():
    # 실제 앱/비용/발행 권한과 native 전송 수락 전에는 child 실행을 활성화하지 않는다.
    raise ContractError('threads_runtime_unconfigured')
