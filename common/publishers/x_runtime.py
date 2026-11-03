"""X의 서버 명시 조립. 기본 등록·자격·API·journal 초기화는 하지 않는다."""
from collections.abc import Mapping
from datetime import datetime,timezone,timedelta
from pathlib import Path
from types import MappingProxyType
import sys
from common.operations.admission_context import decode_bridge_context
from common.operations.execution_catalog import ExecutionCatalog,ExecutorSpec
from common.operations.models import ContractError
from common.operations.runtime_models import PublicationContext,utc
from .x import _observation
from .x_payloads import build_x_payload,NUMERIC_ID

X_BINDINGS=MappingProxyType({'personal.x':'x.personal','dept.x':'x.dept'})

def build_x_catalog(registry,*,configured=False,interpreter=None,cwd=None):
    if configured is not True:return ExecutionCatalog()
    executors={}
    for identifier,executor in X_BINDINGS.items():
        connection=registry.connections.get(identifier)
        if (not connection or connection.enabled is not True or connection.platform!='x'
                or connection.account_id!=identifier.split('.')[0] or type(connection.target_id) is not str
                or NUMERIC_ID.fullmatch(connection.target_id) is None):continue
        jobs=tuple(key for key,job in registry.jobs.items() if job.get('executor_id')==executor and job.get('enabled') is True
            and job.get('execution_owner')=='managed' and job.get('managed_eligible') is True
            and identifier in (job.get('connection_ids') or (job.get('connection_id'),)))
        if jobs:
            executors[executor]=ExecutorSpec(executor,jobs,('submit','verify'),interpreter or str(Path(sys.executable).absolute()),
                cwd or Path(__file__).resolve().parents[2],'common.publishers.x',('publish',),('LANG','LC_ALL','TZ','PATH'))
    return ExecutionCatalog(executors)

def build_x_handlers(registry,*,services_factory,clock=None,before_write=None):
    if (not callable(services_factory) or clock is not None and not callable(clock)
            or before_write is not None and not callable(before_write)):raise ContractError('x_service_required')
    clock=clock or (lambda:datetime.now(timezone.utc));handlers={}
    for identifier,executor in X_BINDINGS.items():
        if identifier not in registry.connections:continue
        def handler(context,payload,credentials,*,connection_id=identifier,action='inspect_target'):
            if not isinstance(context,Mapping) or not isinstance(payload,Mapping):raise ContractError('x_context_mismatch')
            ctx=decode_bridge_context(context,action);connection=registry.connections[connection_id]
            if (ctx.connection_id!=connection_id or ctx.platform!='x' or connection.platform!='x'
                    or connection.enabled is not True or connection.account_id!=connection_id.split('.')[0]
                    or ctx.destination_account_id!=connection.account_id or ctx.target_id!=connection.target_id
                    or NUMERIC_ID.fullmatch(ctx.target_id) is None or ctx.registry_revision!=registry.revision):raise ContractError('x_context_mismatch')
            if action=='inspect_target':
                if payload:raise ContractError('x_payload_invalid')
            elif not isinstance(ctx,PublicationContext):raise ContractError('publication_context_required')
            elif action=='publish':
                snapshot=dict(id=ctx.content_id,revision=ctx.content_revision,manifest_hash=ctx.manifest_hash,
                    owner_account_id=ctx.owner_account_id,original=payload.get('text'),variants=[],assets=[])
                from common.operations.models import thaw
                if build_x_payload(snapshot,ctx)!=thaw(payload):raise ContractError('x_prepared_mismatch')
            elif action=='verify':
                if (set(payload)!={'remote_id'} or type(payload['remote_id']) is not str
                        or NUMERIC_ID.fullmatch(payload['remote_id']) is None):raise ContractError('x_payload_invalid')
            else:
                attempt=payload.get('attempt')
                if (set(payload)!={'attempt'} or not isinstance(attempt,Mapping) or set(attempt)-{'remote_id','created_at'}
                        or type(attempt.get('remote_id')) is not str or NUMERIC_ID.fullmatch(attempt['remote_id']) is None):
                    raise ContractError('x_payload_invalid')
                if 'created_at' in attempt and attempt['created_at'] is not None:utc(attempt['created_at'])
            services=services_factory(connection_id,credentials)
            if before_write is not None:services.before_write=before_write
            target=dict(platform='x',target_id=ctx.target_id,expected_login_subject=connection.expected_login_subject)
            if action=='inspect_target':
                result=services.inspect(target);now=utc(clock())
                if (not isinstance(result,Mapping) or type(result.get('authenticated')) is not bool
                        or result.get('platform')!='x' or result['authenticated'] and result.get('target_id')!=ctx.target_id):
                    raise ContractError('x_observation_invalid')
                return dict({key:result[key] for key in ('platform','target_id','login_subject','authenticated','verification_method','status') if key in result},checked_at=now.isoformat(),expires_at=(now+timedelta(minutes=5)).isoformat())
            if action=='publish':
                for key in ('platform','connection_id','target_id','owner_account_id','destination_account_id','content_id','content_revision','manifest_hash','publication_purpose','schedule_slot'):
                    if payload.get(key)!=getattr(ctx,key):raise ContractError('x_prepared_mismatch')
                return services.submit(payload,target)
            if action=='lookup':
                rows=services.lookup(target,payload.get('attempt',{}))
                if not isinstance(rows,(list,tuple)):raise ContractError('x_observation_invalid')
                safe=[_observation(dict(row,destination_account_id=ctx.destination_account_id)) for row in rows if isinstance(row,Mapping)]
                return dict(candidates=[row for row in safe if row is not None and row['target_id']==ctx.target_id and row['remote_id']==payload['attempt']['remote_id']],checked_at=utc(clock()).isoformat())
            row=services.read_post(target,payload.get('remote_id'))
            safe=_observation(dict(row,destination_account_id=ctx.destination_account_id)) if isinstance(row,Mapping) else None
            if safe is not None and (safe['target_id']!=ctx.target_id or safe['remote_id']!=payload['remote_id']):safe=None
            return dict(observation=safe,checked_at=utc(clock()).isoformat())
        for action in ('inspect_target','publish','lookup','verify'):
            def bound(context,payload,credentials,*,_handler=handler,_action=action):return _handler(context,payload,credentials,action=_action)
            handlers[(executor,action)]=bound
    return handlers

def build_x_host(registry,catalog,store,locks,*,services_factory,credential_catalog,credential_resolver,clock=None,module_root=None):
    from .bridge_host import BridgeHost
    from .legacy_bridge import _clear
    return BridgeHost(registry,catalog,store,locks,build_x_handlers(registry,services_factory=services_factory,clock=clock,before_write=lambda:_clear(locks)),
        credential_catalog=credential_catalog,credential_resolver=credential_resolver,clock=clock,module_root=module_root)

def bridge_bootstrap():
    # 실제 앱/비용/발행 권한과 native 전송 수락 전에는 child 실행을 활성화하지 않는다.
    raise ContractError('x_runtime_unconfigured')
