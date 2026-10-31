"""서버/CLI/자식이 공유하는 정적 배포 경로. HTTP/stdin/env override 없음."""
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from .models import ContractError

CODE_ROOT=Path(__file__).resolve().parents[2]
SOURCE_ROOT=Path('/Volumes/USB256/devAPP/AutoSNS')


@dataclass(frozen=True)
class BootstrapConfig:
    code_root: Path = CODE_ROOT
    source_root: Path = SOURCE_ROOT
    workspace_root: Path = CODE_ROOT/'ax-console/data/managed-workspace'
    registry_path: Path = CODE_ROOT/'ax-console/config/operations.json'

    def __post_init__(self):
        for name in ('code_root','source_root','workspace_root','registry_path'):
            path=Path(getattr(self,name))
            if not path.is_absolute():raise ContractError('invalid_bootstrap_config')
            object.__setattr__(self,name,path)


def default_bootstrap_config():
    return BootstrapConfig()


def child_store(registry,config=None):
    config=config or default_bootstrap_config()
    from .database import connect_database
    from .runtime_store import RuntimeStore
    from .content_store import ContentStore
    from common.shared.axlock import AxLock, LockPaths
    if not (config.workspace_root/'operations.sqlite3').is_file():raise ContractError('bridge_unavailable')
    with closing(connect_database(config.workspace_root,writable=False)) as db:
        if db.execute('PRAGMA user_version').fetchone()[0]!=3:raise ContractError('bridge_unavailable')
    store=RuntimeStore(config.workspace_root,registry,ContentStore(config.workspace_root))
    store._initialized=True
    locks=AxLock(LockPaths.from_root(config.source_root));store.locks=locks
    return store,locks


def build_execution_service(*,config=None,registry=None,catalog=None,policy=None,producers=None,bridge=None,clock=None,initialize=False):
    """신뢰된 서버 startup 전용. 기본 비활성, 초기화/프로세스 시작을 하지 않는다."""
    from datetime import datetime, timezone
    from .registry import load_registry
    from .runtime_models import ExecutionPolicy
    from .runtime_store import RuntimeStore
    from .production_store import ProductionStore
    from .content_store import ContentStore
    from .ledger import Ledger
    from .execution_catalog import ExecutionCatalog
    from .execution_service import ExecutionService
    from common.shared.axlock import AxLock, LockPaths
    config=config or default_bootstrap_config();policy=policy or ExecutionPolicy()
    registry=registry if registry is not None else load_registry(config.registry_path)
    catalog=catalog or ExecutionCatalog();content=ContentStore(config.workspace_root)
    store=RuntimeStore(config.workspace_root,registry,content);production=ProductionStore(config.workspace_root,registry=registry)
    ledger=Ledger(config.workspace_root,registry,content);locks=AxLock(LockPaths.from_root(config.source_root))
    if initialize:
        store.initialize();production._initialized=True;ledger._initialized=True
    else:
        # 읽기는 additive migration을 수행하지 않는다.
        exists=(config.workspace_root/'operations.sqlite3').is_file()
        if exists:
            from .database import connect_database
            with closing(connect_database(config.workspace_root,writable=False)) as db:valid=db.execute('PRAGMA user_version').fetchone()[0]==3
            store._initialized=production._initialized=ledger._initialized=valid
    service=ExecutionService(store,ledger,registry,catalog,policy,{},producers or {},production,locks,clock or (lambda:datetime.now(timezone.utc)))
    if policy.enabled:
        # 별도 startup roots는 자식 정적 설정과 일치할 때만 실제 bridge로 연결한다.
        if bridge is None:
            if config!=default_bootstrap_config():raise ContractError('child_bootstrap_mismatch')
            from common.publishers.legacy_bridge import LegacyBridge
            bridge=LegacyBridge(service.registry,catalog,store,locks,clock=service.clock)
        from common.publishers import build_adapters
        service.adapters=build_adapters(registry=service.registry,bridge=bridge)
    return service


def cli_services(service,*,caller_ids):
    from .worker_service import WorkerService
    from .entrypoints import resolve_entrypoint
    worker=WorkerService(service,clock=service.clock)
    return dict(caller_ids=dict(caller_ids),submit=service.submit,worker_once=worker.tick,status=service.status,
        reconcile=service.reconcile,guard_legacy=lambda caller,job:resolve_entrypoint(caller,job,service.registry,service.catalog))


def build_default_cli_services():
    """실제 모듈 CLI의 정적 조립. 관리전환이 승인된 CLI job은 아직 없다."""
    from .execution_catalog import ExecutionCatalog
    caller_ids={'console':'cli.console','launchd':'cli.launchd'}
    catalog=ExecutionCatalog(callers={caller_id:dict(job_ids=(),source=source,legacy_allowed=False)
        for source,caller_id in caller_ids.items()})
    service=build_execution_service(config=default_bootstrap_config(),catalog=catalog,initialize=False)
    return cli_services(service,caller_ids=caller_ids)
