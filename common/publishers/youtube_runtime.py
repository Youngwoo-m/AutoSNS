"""서버 고정 YouTube launcher/handler 조립. 요청·환경 경로 override 없음."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import os
from types import MappingProxyType
from common.operations.models import ContractError
from common.operations.runtime_models import PublicationContext, utc
from common.operations.execution_catalog import ExecutionCatalog, ExecutorSpec
from .youtube_services import observation

ROOT = Path(__file__).resolve().parents[2]
YOUTUBE_BINDINGS = MappingProxyType({
    'dept.youtube': 'youtube.dept',
    'personal.youtube': 'youtube.personal',
})
CREDENTIAL_CATALOG = MappingProxyType({key + '.credential': MappingProxyType(dict(
    credential_ref=key + '.credential', account_id=key.split('.')[0], platform='youtube')) for key in YOUTUBE_BINDINGS})


def build_youtube_catalog(registry, *, interpreter=None, cwd=None):
    executors = {}
    for key, executor in YOUTUBE_BINDINGS.items():
        connection = registry.connections.get(key)
        if not connection or not connection.enabled or not connection.target_id: continue
        jobs = tuple(job_id for job_id, job in registry.jobs.items()
                     if job.get('executor_id') == executor and job.get('enabled') is True
                     and job.get('execution_owner') == 'managed' and job.get('managed_eligible') is True
                     and key in (job.get('connection_ids') or (job.get('connection_id'),)))
        if jobs:
            executors[executor] = ExecutorSpec(executor, jobs, ('submit', 'verify'), interpreter or ROOT / 'dept/youtube-shorts-auto/.venv/bin/python',
                cwd or ROOT / 'dept/youtube-shorts-auto', 'common.publishers.youtube', ('publish',), ('LANG', 'LC_ALL', 'TZ', 'PATH'))
    return ExecutionCatalog(executors)


def resolve_youtube_credentials(reference, *, account_id, platform, scope):
    entry = CREDENTIAL_CATALOG.get(reference)
    if (not entry or entry['account_id'] != account_id or platform != 'youtube' or scope not in ('read', 'publication')):
        raise ContractError('credential_owner_mismatch')
    # 기존 암호화 키만 exact로 읽는다. token_store의 평문/타 계정 fallback은 사용하지 않는다.
    import json
    from common.shared import secret_env
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    key = {'dept': 'YOUTUBE_TOKEN_DEPT', 'personal': 'YOUTUBE_TOKEN_GEOAI'}[account_id]
    raw = secret_env.read().get(key)
    if not isinstance(raw, str) or not raw: raise ContractError('authentication_required')
    # 저장 토큰의 기존 동의 scope를 유지한다. 새 권한을 요청하지 않는다.
    credential = Credentials.from_authorized_user_info(json.loads(raw))
    if not credential.valid and credential.expired and credential.refresh_token:
        credential.refresh(Request())
        secret_env.update({key: credential.to_json()})
    if not credential.valid: raise ContractError('authentication_required')
    return credential


def build_youtube_handlers(registry, *, services_factory=None, media_loader=None, clock=None):
    clock = clock or (lambda: datetime.now(timezone.utc))
    if services_factory is None:
        from .youtube_services import create_youtube_services
        def services_factory(key, credentials):
            if media_loader is None: raise ContractError('youtube_media_loader_required')
            return create_youtube_services(key, credentials, media_loader=media_loader)
    handlers = {}
    for key, executor in YOUTUBE_BINDINGS.items():
        if key not in registry.connections: continue
        def handler(context, payload, credentials, *, connection_id=key, action='inspect_target'):
            ctx = PublicationContext(**context)
            connection = registry.connections[connection_id]
            if (ctx.connection_id != connection_id or ctx.platform != 'youtube' or connection.platform != 'youtube' or
                ctx.destination_account_id != connection.account_id or ctx.target_id != connection.target_id or
                not ctx.target_id or ctx.registry_revision != registry.revision):
                raise ContractError('youtube_context_mismatch')
            target = dict(platform='youtube', target_id=ctx.target_id, expected_login_subject=connection.expected_login_subject)
            services = services_factory(connection_id, credentials)
            now = utc(clock())
            if action == 'inspect_target':
                return dict(services.inspect(target), checked_at=now.isoformat(), expires_at=(now + timedelta(minutes=5)).isoformat())
            if action == 'publish':
                for name in ('connection_id', 'target_id', 'platform', 'owner_account_id', 'destination_account_id', 'content_id', 'content_revision', 'manifest_hash'):
                    if payload.get(name) != context[name]: raise ContractError('youtube_prepared_mismatch')
                return services.submit(payload, target)
            if action == 'lookup':
                rows = services.lookup(target, payload.get('attempt', {}))
                return dict(candidates=[observation(row, context) for row in rows], checked_at=now.isoformat())
            raw = services.read_video(target, payload.get('remote_id'))
            return dict(observation=observation(raw, context) if raw else None, checked_at=now.isoformat())
        for action in ('inspect_target', 'lookup', 'verify', 'publish'):
            def bound(context, payload, credentials, *, _handler=handler, _action=action):
                return _handler(context, payload, credentials, action=_action)
            handlers[(executor, action)] = bound
    return handlers


def build_youtube_host(registry, catalog, store, locks, *, services_factory=None,
                       credential_catalog=CREDENTIAL_CATALOG, credential_resolver=resolve_youtube_credentials, clock=None, module_root=None):
    from .bridge_host import BridgeHost
    content_store = getattr(store, 'content_store', None)
    loader = getattr(content_store, 'read_asset', None)
    return BridgeHost(registry, catalog, store, locks,
        build_youtube_handlers(registry, services_factory=services_factory, media_loader=loader, clock=clock),
        credential_catalog=credential_catalog, credential_resolver=credential_resolver, clock=clock,
        **({'module_root': module_root} if module_root is not None else {}))


def bridge_bootstrap():
    from common.operations.registry import load_registry
    registry = load_registry(ROOT / 'ax-console/config/operations.json')
    catalog = build_youtube_catalog(registry)
    if not catalog.executors: raise ContractError('bridge_unavailable')
    if any(not Path(spec.interpreter).is_file() or not os.access(spec.interpreter, os.X_OK)
           for spec in catalog.executors.values()):
        raise ContractError('environment_unavailable')
    root = ROOT / 'ax-console/data/managed'
    if not (root / 'operations.sqlite3').is_file(): raise ContractError('bridge_unavailable')
    from common.operations.database import connect_database
    with connect_database(root, writable=False) as db:
        if db.execute('PRAGMA user_version').fetchone()[0] != 3: raise ContractError('bridge_unavailable')
    from common.operations.runtime_store import RuntimeStore
    from common.operations.content_store import ContentStore
    from common.shared.axlock import AxLock, LockPaths
    store = RuntimeStore(root, registry, ContentStore(root))
    store._initialized = True  # DDL 이행은 실행하지 않는다.
    return build_youtube_host(registry, catalog, store, AxLock(LockPaths.from_root(ROOT)))
