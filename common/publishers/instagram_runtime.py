"""Instagram 미디어의 명시 서버 조립. 기본 실행기·자격·staging·journal 초기화는 없다.

BridgeHost의 permit·STOP 경계를 재사용한다. 공개 미디어 factory의 approval_guard가
최종 검토·STOP·permit을 함께 검사하는 실제 native 연결은 아직 수락되지 않았다.
따라서 bootstrap은 항상 차단하며 이 조립만으로 서비스 ready를 선언하지 않는다.
"""
from collections.abc import Mapping
from datetime import datetime,timezone,timedelta
from pathlib import Path
from types import MappingProxyType
import sys
from common.operations.admission_context import decode_bridge_context
from common.operations.execution_catalog import ExecutionCatalog,ExecutorSpec
from common.operations.models import ContractError
from common.operations.runtime_models import PublicationContext,utc
from .instagram import (validate_instagram_prepared,sanitize_instagram_observation,
    sanitize_instagram_submission)
from .instagram_payloads import NUMERIC_ID

INSTAGRAM_BINDINGS=MappingProxyType({'personal.instagram':'instagram.personal','dept.instagram':'instagram.dept'})
_TARGET=('platform','authenticated','target_id','login_subject','status','verification_method')


def _id(value):return type(value) is str and NUMERIC_ID.fullmatch(value) is not None


def build_instagram_catalog(registry,*,configured=False,interpreter=None,cwd=None):
    if configured is not True:return ExecutionCatalog()
    executors={}
    for identifier,executor in INSTAGRAM_BINDINGS.items():
        conn=registry.connections.get(identifier)
        if (not conn or conn.enabled is not True or conn.platform!='instagram'
                or conn.account_id!=identifier.split('.')[0] or not _id(conn.target_id)):continue
        jobs=tuple(key for key,job in registry.jobs.items() if job.get('executor_id')==executor
            and job.get('enabled') is True and job.get('execution_owner')=='managed' and job.get('managed_eligible') is True
            and identifier in (job.get('connection_ids') or (job.get('connection_id'),)))
        if jobs:executors[executor]=ExecutorSpec(executor,jobs,('submit','verify'),interpreter or str(Path(sys.executable).absolute()),
            cwd or Path(__file__).resolve().parents[2],'common.publishers.instagram',('publish',),('LANG','LC_ALL','TZ','PATH'))
    return ExecutionCatalog(executors)


def _payload(ctx,action,payload):
    if not isinstance(payload,Mapping):raise ContractError('instagram_payload_invalid')
    if action=='inspect_target':
        if payload:raise ContractError('instagram_payload_invalid')
        return None
    if action=='publish':
        validate_instagram_prepared(ctx,payload)
        return None
    if not isinstance(ctx,PublicationContext):raise ContractError('publication_context_required')
    if action=='verify':
        if set(payload)!={'remote_id'} or not _id(payload.get('remote_id')):raise ContractError('instagram_payload_invalid')
        return payload['remote_id']
    attempt=payload.get('attempt')
    if (action!='lookup' or set(payload)!={'attempt'} or not isinstance(attempt,Mapping)
            or set(attempt)-{'remote_id','created_at'} or not _id(attempt.get('remote_id'))):raise ContractError('instagram_payload_invalid')
    if 'created_at' in attempt:utc(attempt['created_at'])
    return attempt['remote_id']


def _observation(row,ctx,remote_id):
    if row is None:return None
    if (not isinstance(row,Mapping) or row.get('remote_id')!=remote_id or row.get('target_id')!=ctx.target_id
            or row.get('destination_account_id') not in (None,ctx.destination_account_id)):
        raise ContractError('instagram_observation_invalid')
    # 같은 주체의 미완성/불일치 미디어 관측은 전송 실패가 아니다. 증거를 노출하지 않고
    # 다음 명시 읽기를 기다린다. 잘못된 첫 관측으로 source children을 고정하지 않는다.
    return sanitize_instagram_observation(row,ctx,remote_id)


def build_instagram_handlers(registry,*,services_factory,clock=None,before_write=None):
    if (not callable(services_factory) or clock is not None and not callable(clock)
            or before_write is not None and not callable(before_write)):
        raise ContractError('instagram_service_required')
    clock=clock if clock is not None else lambda:datetime.now(timezone.utc);handlers={}
    for identifier,executor in INSTAGRAM_BINDINGS.items():
        if identifier not in registry.connections:continue
        def handler(context,payload,credentials,*,connection_id=identifier,action='inspect_target'):
            if not isinstance(context,Mapping):raise ContractError('instagram_context_mismatch')
            ctx=decode_bridge_context(context,action);conn=registry.connections[connection_id]
            if (ctx.connection_id!=connection_id or ctx.platform!='instagram' or conn.platform!='instagram'
                    or conn.enabled is not True or conn.account_id!=connection_id.split('.')[0]
                    or ctx.destination_account_id!=conn.account_id or ctx.target_id!=conn.target_id or not _id(ctx.target_id)
                    or ctx.owner_account_id not in ('personal','dept') or ctx.owner_account_id not in registry.accounts
                    or ctx.registry_revision!=registry.revision):raise ContractError('instagram_context_mismatch')
            known=_payload(ctx,action,payload)
            service=services_factory(connection_id,credentials)
            if before_write is not None:service.before_write=before_write
            target=dict(platform='instagram',target_id=ctx.target_id,expected_login_subject=conn.expected_login_subject)
            if action=='inspect_target':
                row=service.inspect(target)
                if not isinstance(row,Mapping) or type(row.get('authenticated')) is not bool or row.get('platform')!='instagram':raise ContractError('instagram_observation_invalid')
                if row['authenticated'] and row.get('target_id')!=ctx.target_id:raise ContractError('instagram_observation_invalid')
                now=utc(clock());return dict({key:row[key] for key in _TARGET if key in row},checked_at=now.isoformat(),expires_at=(now+timedelta(minutes=5)).isoformat())
            if action=='publish':return sanitize_instagram_submission(service.submit(ctx,payload,target),ctx,payload).to_dict()
            if action=='lookup':
                values=service.lookup(ctx,target,payload['attempt'])
                if not isinstance(values,(list,tuple)):raise ContractError('instagram_observation_invalid')
                rows=[_observation(row,ctx,known) for row in values]
                return dict(candidates=[row for row in rows if row is not None],checked_at=utc(clock()).isoformat())
            return dict(observation=_observation(service.observe(ctx,target,known),ctx,known),checked_at=utc(clock()).isoformat())
        for action in ('inspect_target','publish','lookup','verify'):
            def bound(context,payload,credentials,*,_handler=handler,_action=action):return _handler(context,payload,credentials,action=_action)
            handlers[(executor,action)]=bound
    return handlers


def build_instagram_host(registry,catalog,store,locks,*,services_factory,credential_catalog,credential_resolver,clock=None,module_root=None):
    from .bridge_host import BridgeHost
    from .legacy_bridge import _clear
    return BridgeHost(registry,catalog,store,locks,
        build_instagram_handlers(registry,services_factory=services_factory,clock=clock,before_write=lambda:_clear(locks)),
        credential_catalog=credential_catalog,credential_resolver=credential_resolver,clock=clock,module_root=module_root)


def bridge_bootstrap():
    raise ContractError('instagram_runtime_unconfigured')
