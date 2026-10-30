"""정적 blog launcher의 서버 조립. 환경·stdin에서 루트·모듈·자격증명을 고르지 않는다."""
from datetime import datetime, timezone, timedelta
from types import MappingProxyType

from common.operations.models import ContractError
from common.operations.runtime_models import PublicationContext, utc
from common.operations.execution_catalog import ExecutionCatalog, ExecutorSpec
from .blog_legacy import ROOT, load_blog_leaf
from .blog_observations import normalize_blog_observation


BLOG_BINDINGS = MappingProxyType({key: MappingProxyType(dict(executor_id='blog.' + key, module='common.publishers.' + module))
    for key, module in (('dept.blogger', 'blogger'), ('personal.blogger', 'blogger'),
                        ('dept.naver_blog', 'naver'), ('personal.naver_blog', 'naver'),
                        ('personal.tistory', 'tistory'))})
CREDENTIAL_CATALOG = MappingProxyType({key + '.credential': MappingProxyType(dict(
    credential_ref=key + '.credential', account_id=key.split('.')[0], platform=key.split('.')[1])) for key in BLOG_BINDINGS})


def build_blog_catalog(registry, *, interpreter=None, cwd=None):
    """명시 managed+enabled job만 등록한다. 현재 운영 등록부에서는 빈 catalog다."""
    executors = {}
    for connection_id, binding in BLOG_BINDINGS.items():
        connection = registry.connections.get(connection_id)
        if not connection or not connection.enabled or not connection.target_id: continue
        jobs = tuple(key for key, job in registry.jobs.items()
                     if job.get('executor_id') == binding['executor_id'] and job.get('enabled') is True
                     and job.get('execution_owner') == 'managed'
                     and connection_id in (job.get('connection_ids') or (job.get('connection_id'),)))
        if jobs:
            project = ROOT / ('personal/naver-blog-auto' if connection_id == 'personal.tistory' else 'dept/naver-blog-auto')
            executors[binding['executor_id']] = ExecutorSpec(binding['executor_id'], jobs, ('submit', 'verify'),
                interpreter or str(project / '.venv/bin/python'), cwd or project, binding['module'], ('publish',), ('LANG', 'LC_ALL', 'TZ', 'PATH'))
    return ExecutionCatalog(executors)


def resolve_blog_credentials(reference, *, account_id, platform, scope):
    entry = CREDENTIAL_CATALOG.get(reference)
    if (not entry or entry['account_id'] != account_id or entry['platform'] != platform or scope not in ('read', 'publication')):
        raise ContractError('credential_owner_mismatch')
    if platform != 'blogger': return None  # 브라우저의 유일 인증은 등록된 프로필이다.
    # 기존 암호화 저장소와 키 이름을 유지한다. 다른 계정/옛 평문 토큰 fallback 없음.
    import json
    from common.shared import secret_env
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    key = {'dept': 'BLOGGER_TOKEN_DEPT', 'personal': 'BLOGGER_TOKEN_GEOAI'}[account_id]
    raw = secret_env.read().get(key)
    if not isinstance(raw, str) or not raw: raise ContractError('authentication_required')
    credential = Credentials.from_authorized_user_info(json.loads(raw), ['https://www.googleapis.com/auth/blogger'])
    if not credential.valid and credential.expired and credential.refresh_token:
        credential.refresh(Request())
        secret_env.update({key: credential.to_json()})
    if not credential.valid: raise ContractError('authentication_required')
    return credential


def build_blog_handlers(registry, *, services_factory=None, content_store=None, before_write=None, clock=None):
    """handler는 신뢰된 서버 DI만 캡처한다. payload는 service/credential/profile을 못 고른다."""
    clock = clock or (lambda: datetime.now(timezone.utc))
    if services_factory is None:
        from .blog_services import create_blog_services
        services_factory = create_blog_services
    handlers = {}
    for key, binding in BLOG_BINDINGS.items():
        if key not in registry.connections: continue
        def handler(context, payload, credentials, *, connection_id=key, action='inspect_target'):
            ctx = PublicationContext(**context)
            connection = registry.connections[connection_id]
            if (ctx.connection_id != connection_id or ctx.platform != connection.platform or
                ctx.destination_account_id != connection.account_id or ctx.target_id != connection.target_id or
                not ctx.target_id or ctx.registry_revision != registry.revision):
                raise ContractError('blog_context_mismatch')
            target = dict(connection_id=connection_id, platform=connection.platform, target_id=ctx.target_id,
                          expected_login_subject=connection.expected_login_subject)
            services = services_factory(connection_id, credentials)
            if before_write is not None:
                services.before_write = before_write
            if content_store is not None and hasattr(services, 'asset_reader'):
                services.asset_reader = lambda asset_id: content_store.read_asset(ctx.content_id, ctx.content_revision, asset_id)
            leaf = load_blog_leaf(connection_id)
            now = utc(clock())
            if action == 'inspect_target':
                result = leaf.managed_inspect(target, services)
                return dict(result, checked_at=now.isoformat(), expires_at=(now + timedelta(minutes=5)).isoformat())
            if action == 'publish':
                for name in ('connection_id', 'target_id', 'platform', 'owner_account_id', 'destination_account_id'):
                    if payload.get(name) != context[name]: raise ContractError('blog_prepared_mismatch')
                return leaf.managed_submit(payload, target, services)
            if action == 'lookup':
                result = leaf.managed_lookup(target, payload.get('attempt', {}), services)
                observations = [normalize_blog_observation(ctx.platform, item, context=context, checked_at=now)
                                for item in result.get('items', [])]
                return dict(candidates=observations, unsupported=result.get('unsupported', False), checked_at=now.isoformat())
            raw = leaf.managed_verify(target, payload.get('remote_id'), services)
            if not raw: return dict(observation=None, checked_at=now.isoformat())
            observation = normalize_blog_observation(ctx.platform, raw, context=context, checked_at=now)
            return dict(observation=observation, checked_at=now.isoformat())
        for action in ('inspect_target', 'lookup', 'verify', 'publish'):
            def bound(context, payload, credentials, *, _handler=handler, _action=action):
                return _handler(context, payload, credentials, action=_action)
            handlers[(binding['executor_id'], action)] = bound
    return handlers


def build_blog_host(registry, catalog, store, locks, *, services_factory=None,
                    credential_catalog=CREDENTIAL_CATALOG, credential_resolver=resolve_blog_credentials, module_root=None, clock=None):
    from .bridge_host import BridgeHost
    from .legacy_bridge import _clear
    extra = {} if module_root is None else {'module_root': module_root}
    return BridgeHost(registry, catalog, store, locks,
                      build_blog_handlers(registry, services_factory=services_factory, content_store=getattr(store, 'content_store', None), before_write=lambda: _clear(locks), clock=clock),
                      credential_catalog=credential_catalog, credential_resolver=credential_resolver, clock=clock, **extra)


def bridge_bootstrap(platform):
    """고정 운영 파일만 읽는다. 현재 비활성 등록부는 DB/프로필 접근 전에 거절된다."""
    from common.operations.registry import load_registry
    registry = load_registry(ROOT / 'ax-console/config/operations.json')
    catalog = build_blog_catalog(registry)
    executors = {key: spec for key, spec in catalog.executors.items()
                 if spec.module == 'common.publishers.' + ('naver' if platform == 'naver_blog' else platform)}
    if not executors: raise ContractError('bridge_unavailable')
    catalog = ExecutionCatalog(executors)
    from common.operations.runtime_store import RuntimeStore
    from common.operations.content_store import ContentStore
    from common.shared.axlock import AxLock, LockPaths
    # 관리 저장소 위치 변경은 서버 코드/배포 설정 검토 대상이다. 요청/env override가 없다.
    root = ROOT / 'ax-console/data/managed-workspace'
    if not (root / 'operations.sqlite3').is_file(): raise ContractError('bridge_unavailable')
    store = RuntimeStore(root, registry, ContentStore(root))
    # DDL 이행을 실행하지 않는다. 이미 초기화된 v3 저장소만 사용한다.
    from common.operations.database import connect_database
    with connect_database(root, writable=False) as db:
        if db.execute('PRAGMA user_version').fetchone()[0] != 3: raise ContractError('bridge_unavailable')
    store._initialized = True
    return build_blog_host(registry, catalog, store, AxLock(LockPaths.from_root(ROOT)))
