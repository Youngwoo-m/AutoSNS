"""서버 소유 YouTube 성과 수집기 조립. 자격 접근·API 조회는 명시 collect 안에서만 한다."""
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from types import MappingProxyType
from .bootstrap_config import BootstrapConfig
from .metrics_collection import MetricsCollectionService
from .metrics_store import MetricsStore
from .models import ContractError,Registry
from .youtube_metrics import YouTubeMetricsCollector


def _invalid():raise ContractError('metrics_configuration_required')

def _no_media_loader(*args,**kwargs):
    raise ContractError('metrics_read_only')


def build_metrics_collection_service(*,config,registry,runtime_store,metrics_store,locks,
                                     connection_ids,services_factory=None,activate=False):
    if activate is not True:raise ContractError('metrics_activation_required')
    if (not isinstance(config,BootstrapConfig) or not isinstance(registry,Registry)
            or not isinstance(metrics_store,MetricsStore) or not callable(getattr(locks,'hold',None))
            or not isinstance(connection_ids,(list,tuple)) or not connection_ids
            or (services_factory is not None and not callable(services_factory))):_invalid()
    root=getattr(runtime_store,'root',None)
    try:
        if root is None or Path(root).resolve()!=config.workspace_root.resolve() or metrics_store.root.resolve()!=config.workspace_root.resolve():_invalid()
    except (TypeError,OSError,RuntimeError):_invalid()
    registered={}
    for identifier in connection_ids:
        if type(identifier) is not str or identifier not in ('personal.youtube','dept.youtube') or identifier in registered:_invalid()
        connection=registry.connections.get(identifier)
        if (connection is None or connection.platform!='youtube' or connection.account_id+'.youtube'!=identifier
                or connection.account_id not in registry.accounts or not isinstance(connection.target_id,str)
                or not connection.target_id.strip() or connection.credential_ref!=identifier+'.credential'):_invalid()
        credential=registry.credentials.get(connection.credential_ref)
        profile=registry.profiles.get(connection.profile_ref)
        if (not isinstance(credential,Mapping) or credential.get('account_id')!=connection.account_id
                or credential.get('platform')!='youtube' or not isinstance(profile,Mapping)
                or profile.get('account_id')!=connection.account_id
                or not isinstance(profile.get('lock_resource'),str)
                or not profile['lock_resource'].startswith('profile:') or not profile['lock_resource'][8:].strip()):_invalid()
        registered[identifier]=(connection,profile['lock_resource'])
    registered=MappingProxyType(registered)
    if services_factory is None:
        def services_factory(ctx):
            from common.publishers.youtube_runtime import resolve_youtube_credentials
            from common.publishers.youtube_services import create_youtube_services
            connection,_=registered[ctx.connection_id]
            credentials=resolve_youtube_credentials(connection.credential_ref,account_id=connection.account_id,
                                                    platform='youtube',scope='read')
            return create_youtube_services(ctx.connection_id,credentials,media_loader=_no_media_loader)
    @contextmanager
    def lock_scope(ctx):
        entry=registered.get(ctx.connection_id)
        if entry is None or ctx.destination_account_id!=entry[0].account_id or ctx.target_id!=entry[0].target_id:
            raise ContractError('metrics_identity_mismatch')
        resources=[entry[1],'account:'+ctx.destination_account_id,'connection:'+ctx.connection_id]
        with locks.hold(resources,job='metrics:'+ctx.connection_id,wait=0,check_stop=False):
            yield
    collectors={identifier:YouTubeMetricsCollector(services_factory) for identifier in registered}
    return MetricsCollectionService(runtime_store,metrics_store,registry,collectors,lock_scope,enabled=True)
