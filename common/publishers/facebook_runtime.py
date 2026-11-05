"""Facebook Pages의 서버 명시 조립. 기본 등록·자격·API·journal 초기화는 하지 않는다."""
from collections.abc import Mapping
from datetime import datetime,timezone,timedelta
from pathlib import Path
from types import MappingProxyType
import hashlib
import re
import sys

from common.operations.admission_context import decode_bridge_context
from common.operations.execution_catalog import ExecutionCatalog,ExecutorSpec
from common.operations.models import ContractError
from common.operations.runtime_models import utc
from .facebook_payloads import PREPARED_KEYS,validate_facebook_text

FACEBOOK_BINDINGS=MappingProxyType({'personal.facebook':'facebook.personal','dept.facebook':'facebook.dept'})
_NUMERIC=re.compile(r'[0-9]{1,64}')
_POST=re.compile(r'([0-9]{1,64})_([0-9]{1,64})')
_OBSERVATION=('remote_id','target_id','text','body_sha256','media_sha256','created_at','url','visibility')
_TARGET=('platform','authenticated','target_id','login_subject','status','verification_method','page_type_verified','page_tasks_verified')


def build_facebook_catalog(registry,*,configured=False,interpreter=None,cwd=None):
    if configured is not True:return ExecutionCatalog()
    executors={}
    for identifier,executor in FACEBOOK_BINDINGS.items():
        connection=registry.connections.get(identifier)
        if (not connection or not connection.enabled or connection.platform!='facebook'
                or connection.account_id!=identifier.split('.')[0]
                or type(connection.target_id) is not str or _NUMERIC.fullmatch(connection.target_id) is None):continue
        jobs=tuple(key for key,job in registry.jobs.items() if job.get('executor_id')==executor
            and job.get('enabled') is True and job.get('execution_owner')=='managed'
            and job.get('managed_eligible') is True
            and identifier in (job.get('connection_ids') or (job.get('connection_id'),)))
        if jobs:
            executors[executor]=ExecutorSpec(executor,jobs,('submit','verify'),interpreter or str(Path(sys.executable).absolute()),
                cwd or Path(__file__).resolve().parents[2],'common.publishers.facebook',('publish',),('LANG','LC_ALL','TZ','PATH'))
    return ExecutionCatalog(executors)


def _known_remote(value,target):
    match=_POST.fullmatch(value) if type(value) is str else None
    if match is None or match.group(1)!=target:raise ContractError('facebook_payload_invalid')
    return value


def _payload(ctx,action,payload):
    if not isinstance(payload,Mapping):raise ContractError('facebook_payload_invalid')
    if action=='inspect_target':
        if payload:raise ContractError('facebook_payload_invalid')
        return None
    if action=='publish':
        if (set(payload)!=set(PREPARED_KEYS) or set(ctx.options)-{'text_only','visibility'}
                or ctx.options.get('text_only') is not True or ctx.options.get('visibility','public')!='public'
                or any(payload[key]!=getattr(ctx,key) for key in PREPARED_KEYS if key not in ('text','body_sha256','media_sha256'))
                or not isinstance(payload['media_sha256'],(tuple,list)) or list(payload['media_sha256'])!=[]):
            raise ContractError('facebook_prepared_mismatch')
        text=validate_facebook_text(payload['text'])
        if hashlib.sha256(text.encode('utf-8')).hexdigest()!=payload['body_sha256']:
            raise ContractError('facebook_prepared_mismatch')
        return None
    if action=='verify':
        if set(payload)!={'remote_id'}:raise ContractError('facebook_payload_invalid')
        return _known_remote(payload['remote_id'],ctx.target_id)
    attempt=payload.get('attempt')
    if (set(payload)!={'attempt'} or not isinstance(attempt,Mapping)
            or set(attempt)-{'remote_id','created_at'} or 'remote_id' not in attempt):
        raise ContractError('facebook_payload_invalid')
    return _known_remote(attempt['remote_id'],ctx.target_id)


def _observation(row,ctx,remote_id):
    if (not isinstance(row,Mapping) or row.get('remote_id')!=remote_id or row.get('target_id')!=ctx.target_id
            or row.get('destination_account_id') not in (None,ctx.destination_account_id)):
        raise ContractError('facebook_observation_invalid')
    # 서비스는 이미 정규화된 관측을 반환한다. 임의 원문·자격·오류를 bridge로 복사하지 않는다.
    return dict({key:row[key] for key in _OBSERVATION if key in row},destination_account_id=ctx.destination_account_id)


def build_facebook_handlers(registry,*,services_factory,clock=None,before_write=None):
    if (not callable(services_factory) or clock is not None and not callable(clock)
            or before_write is not None and not callable(before_write)):
        raise ContractError('facebook_service_required')
    clock=clock if clock is not None else lambda:datetime.now(timezone.utc)
    handlers={}
    for identifier,executor in FACEBOOK_BINDINGS.items():
        if identifier not in registry.connections:continue
        def handler(context,payload,credentials,*,connection_id=identifier,action='inspect_target'):
            if not isinstance(context,Mapping):raise ContractError('facebook_context_mismatch')
            ctx=decode_bridge_context(context,action);connection=registry.connections[connection_id]
            if (ctx.connection_id!=connection_id or ctx.platform!='facebook' or connection.platform!='facebook'
                    or connection.enabled is not True or connection.account_id!=connection_id.split('.')[0]
                    or ctx.destination_account_id!=connection.account_id or ctx.target_id!=connection.target_id
                    or type(ctx.target_id) is not str or _NUMERIC.fullmatch(ctx.target_id) is None
                    or ctx.owner_account_id not in ('personal','dept') or ctx.owner_account_id not in registry.accounts
                    or ctx.registry_revision!=registry.revision):raise ContractError('facebook_context_mismatch')
            remote_id=_payload(ctx,action,payload)
            services=services_factory(connection_id,credentials)
            if before_write is not None:services.before_write=before_write
            target=dict(platform='facebook',target_id=ctx.target_id,expected_login_subject=connection.expected_login_subject)
            if action=='inspect_target':
                observed=services.inspect(target)
                if not isinstance(observed,Mapping):raise ContractError('facebook_observation_invalid')
                now=utc(clock())
                return dict({key:observed[key] for key in _TARGET if key in observed},checked_at=now.isoformat(),expires_at=(now+timedelta(minutes=5)).isoformat())
            if action=='publish':return services.submit(payload,target)
            if action=='lookup':
                rows=services.lookup(target,payload['attempt'])
                if not isinstance(rows,(list,tuple)):raise ContractError('facebook_observation_invalid')
                return dict(candidates=[_observation(row,ctx,remote_id) for row in rows],checked_at=utc(clock()).isoformat())
            row=services.read_post(target,remote_id)
            return dict(observation=_observation(row,ctx,remote_id) if row is not None else None,checked_at=utc(clock()).isoformat())
        for action in ('inspect_target','publish','lookup','verify'):
            def bound(context,payload,credentials,*,_handler=handler,_action=action):
                return _handler(context,payload,credentials,action=_action)
            handlers[(executor,action)]=bound
    return handlers


def build_facebook_host(registry,catalog,store,locks,*,services_factory,credential_catalog,credential_resolver,clock=None,module_root=None):
    from .bridge_host import BridgeHost
    from .legacy_bridge import _clear
    return BridgeHost(registry,catalog,store,locks,
        build_facebook_handlers(registry,services_factory=services_factory,clock=clock,before_write=lambda:_clear(locks)),
        credential_catalog=credential_catalog,credential_resolver=credential_resolver,clock=clock,module_root=module_root)


def bridge_bootstrap():
    # Page token·tasks·공식 앱·자격·전송·공개 확인 수락 전에는 실제 child를 활성화하지 않는다.
    raise ContractError('facebook_runtime_unconfigured')
