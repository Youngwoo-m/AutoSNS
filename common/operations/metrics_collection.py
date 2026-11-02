"""공개 검증을 마친 배포의 명시 성과 수집 조립. 생성·대상 조회는 외부 호출을 하지 않는다."""
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from .content_store import ContentStore,StoreError
from .metrics import build_metrics_context,collect_delivery_metrics,record_metrics
from .metrics_store import MetricsStore
from .models import Registry


def _configuration_error():
    raise StoreError('invalid_collection_configuration')


class MetricsCollectionService:
    def __init__(self,runtime_store,metrics_store,registry,collectors,lock_scope,enabled=False):
        if (not isinstance(metrics_store,MetricsStore) or not isinstance(registry,Registry)
                or not isinstance(collectors,Mapping) or not callable(lock_scope) or type(enabled) is not bool
                or not all(callable(getattr(runtime_store,name,None)) for name in ('get_delivery','events','list_operations'))):
            _configuration_error()
        runtime_root=getattr(runtime_store,'root',None)
        if runtime_root is None or Path(runtime_root).resolve()!=metrics_store.root.resolve():
            _configuration_error()
        registered={}
        for connection_id,collector in collectors.items():
            if type(connection_id) is not str or connection_id not in registry.connections or not callable(collector):
                _configuration_error()
            registered[connection_id]=collector
        self.runtime_store=runtime_store
        self.metrics_store=metrics_store
        self.registry=registry
        self.collectors=MappingProxyType(registered)
        self.lock_scope=lock_scope
        self.enabled=enabled

    def _title(self,ctx):
        content=getattr(self.runtime_store,'content_store',None)
        if not isinstance(content,ContentStore) or content.root.resolve()!=self.metrics_store.root.resolve():
            return ctx.content_id
        try:snapshot=content.get(ctx.content_id,ctx.content_revision)
        except StoreError:return ctx.content_id
        if (not isinstance(snapshot,Mapping) or snapshot.get('id')!=ctx.content_id
                or snapshot.get('revision')!=ctx.content_revision or snapshot.get('manifest_hash')!=ctx.manifest_hash
                or snapshot.get('owner_account_id')!=ctx.owner_account_id):return ctx.content_id
        title=snapshot.get('title')
        if not isinstance(title,str) or not title.strip() or len(title)>2000:return ctx.content_id
        return title

    def targets(self,account='all'):
        if type(account) is not str or account not in ('all','personal','dept'):raise StoreError('invalid')
        rows=self.runtime_store.list_operations()
        if not isinstance(rows,(list,tuple)):raise StoreError('storage_error')
        targets=[];seen=set()
        for row in rows:
            if not isinstance(row,Mapping) or type(row.get('id')) is not str or not row['id']:
                raise StoreError('storage_error')
            if row['id'] in seen:raise StoreError('storage_error')
            seen.add(row['id'])
            try:ctx=build_metrics_context(self.runtime_store,row['id'],self.registry)
            except StoreError as exc:
                if exc.code in ('not_found','delivery_not_verified','metrics_identity_mismatch','invalid'):continue
                raise
            if ctx.connection_id not in self.collectors:continue
            if account!='all' and ctx.destination_account_id!=account:continue
            target={key:getattr(ctx,key) for key in ('delivery_id','content_id','content_revision','owner_account_id',
                'destination_account_id','platform','connection_id','target_id','remote_id','verified_at')}
            targets.append({**target,'title':self._title(ctx)})
        return targets

    def collect(self,delivery_id):
        if not self.enabled:raise StoreError('collection_disabled')
        if type(delivery_id) is not str or not delivery_id:raise StoreError('invalid')
        ctx=build_metrics_context(self.runtime_store,delivery_id,self.registry)
        collector=self.collectors.get(ctx.connection_id)
        if collector is None:raise StoreError('metrics_collector_unavailable')
        with self.lock_scope(ctx):
            locked=build_metrics_context(self.runtime_store,delivery_id,self.registry)
            if locked!=ctx:raise StoreError('metrics_context_changed')
            result=collect_delivery_metrics(locked,locked.remote_id,collector)
            # 잠금 밖에서 바뀐 원장이나 collector 부작용을 새 게시의 실적으로 귀속하지 않는다.
            current=build_metrics_context(self.runtime_store,delivery_id,self.registry)
            if current!=locked:raise StoreError('metrics_context_changed')
            return record_metrics(self.metrics_store,delivery_id,result,runtime_store=self.runtime_store,registry=self.registry)
