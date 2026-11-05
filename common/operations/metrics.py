"""서버가 확인한 공개 게시에 한정하는 성과 경계. 로그인·API·초기화 없음."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

from .content_store import StoreError
from .metrics_models import MetricObservation, MetricResult, _time
from .runtime_store import RuntimeStore


@dataclass(frozen=True)
class MetricsContext:
    delivery_id: str
    platform: str
    content_id: str
    content_revision: int
    manifest_hash: str
    owner_account_id: str
    destination_account_id: str
    connection_id: str
    target_id: str
    remote_id: str
    verified_at: str


def build_metrics_context(runtime_store, delivery_id, registry) -> MetricsContext:
    """클라이언트 입력 대신 원장과 등록부로 고정한다. 검증시각은 원장 이벤트 근거다."""
    delivery = runtime_store.get_delivery(delivery_id)
    if not delivery:
        raise StoreError('not_found')
    if delivery.get('state') != 'verified' or not delivery.get('remote_id') or delivery.get('remote_uncertain'):
        raise StoreError('delivery_not_verified')
    ctx = delivery.get('context', {})
    connection = registry.connections.get(ctx.get('connection_id')) if registry else None
    if (connection is None or connection.target_id != ctx.get('target_id') or not connection.target_id
            or connection.account_id != ctx.get('destination_account_id')
            or ctx.get('owner_account_id') not in ('personal', 'dept')
            or ctx.get('owner_account_id') not in registry.accounts
            or ctx.get('destination_account_id') not in registry.accounts
            or ctx.get('platform') not in (None, '', connection.platform)):
        raise StoreError('metrics_identity_mismatch')
    checked_at = None
    for event in runtime_store.events(delivery_id):
        result = event.get('evidence', {})
        evidence = result.get('evidence', {})
        if (event.get('kind') == 'verification' and result.get('outcome') == 'verified'
                and evidence.get('visibility') == 'public'
                and evidence.get('remote_id') == delivery['remote_id']
                and evidence.get('target_id') == connection.target_id
                and evidence.get('destination_account_id') == connection.account_id):
            checked_at = _time(result.get('checked_at'))
    if checked_at is None:
        raise StoreError('delivery_not_verified')
    if (not isinstance(ctx.get('content_id'), str) or not ctx['content_id']
            or type(ctx.get('content_revision')) is not int or ctx['content_revision'] < 1
            or not isinstance(ctx.get('manifest_hash'), str) or not ctx['manifest_hash']):
        raise StoreError('metrics_identity_mismatch')
    return MetricsContext(delivery_id, connection.platform, ctx['content_id'], ctx['content_revision'],
                          ctx['manifest_hash'], ctx['owner_account_id'], connection.account_id,
                          connection.id, connection.target_id, delivery['remote_id'], checked_at)


def _check_result(ctx, result):
    if not isinstance(result, MetricResult):
        raise StoreError('invalid')
    if result.remote_id not in (None, ctx.remote_id) or result.target_id not in (None, ctx.target_id):
        raise StoreError('metrics_identity_mismatch')
    return result


def collect_delivery_metrics(ctx, remote_id, collector) -> MetricResult:
    """ctx/collector는 서버 주입 전용. 등록이 없으면 미지원, 예외는 고정 오류로 반환한다."""
    if not isinstance(ctx, MetricsContext) or ctx.remote_id != remote_id:
        raise StoreError('metrics_identity_mismatch')
    collection_id = uuid4().hex
    if collector is None:
        result = MetricResult('unsupported', {}, None, ctx.remote_id, ctx.target_id, 'collection.unsupported')
    else:
        try:
            result = collector(ctx, remote_id)
        except Exception:
            result = MetricResult('error', {}, None, ctx.remote_id, ctx.target_id, 'collection.error')
    _check_result(ctx, result)
    safe = result.to_dict()
    safe['source'] = {}
    safe['collection_id'] = collection_id
    safe['collected_at'] = datetime.now(timezone.utc).isoformat()
    return MetricResult(**safe)


def record_metrics(store, delivery_id, result, *, runtime_store=None, registry=None, observation_key=None):
    """수집 ID/명시 키만 재전송으로 취급. 둘 다 없는 직접 호출은 매번 새 시도.

    collected_at 없는 직접 호출은 최초 저장 시각이 완료시각이며, 재전송은 그
    시각까지 그대로 반환한다. 저장 직전 원장 재검증과 명시 initialize는 유지.
    """
    runtime = runtime_store if runtime_store is not None else RuntimeStore(store.root, registry=registry)
    registry = registry if registry is not None else runtime.registry
    ctx = build_metrics_context(runtime, delivery_id, registry)
    _check_result(ctx, result)
    # 외부 source에는 임의 응답·비밀값이 있을 수 있으므로 복사하지 않는다.
    result_data = result.to_dict()
    result_data.pop('source')
    identity = dict(ctx.__dict__, result=result_data)
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if observation_key is not None:
        from .metrics_models import _text
        _text(observation_key, limit=1000)
    attempt_key = observation_key if observation_key is not None else result.collection_id or uuid4().hex
    collection_key = hashlib.sha256(attempt_key.encode()).hexdigest()
    source = dict(content_revision=ctx.content_revision, manifest_hash=ctx.manifest_hash,
                  verified_at=ctx.verified_at, collection_key=collection_key,
                  result_fingerprint=fingerprint)
    row = MetricObservation('verified_delivery', ctx.owner_account_id, ctx.destination_account_id,
                            ctx.platform, ctx.connection_id, ctx.target_id, ctx.remote_id, ctx.delivery_id,
                            ctx.content_id, '', result.status, result.values, result.observed_at,
                            result.collected_at or datetime.now(timezone.utc).isoformat(), None, result.definition_id,
                            result.basis, result.period, source)
    return store.append_collection(row, 'metrics:' + collection_key)


_PLATFORMS = {'youtube': 'YouTube', 'naver_blog': '네이버 블로그', 'blogger': 'Blogger',
              'instagram': 'Instagram', 'threads': 'Threads', 'x': 'X', 'tistory': 'Tistory',
              'facebook': 'Facebook', 'tiktok': 'TikTok', 'searchconsole': '검색 실적',
              'indexing': '색인 현황', 'smds': '사이트 현황'}


def _account(account_id, registry):
    if account_id not in ('all', 'personal', 'dept') or (account_id != 'all' and account_id not in registry.accounts):
        raise StoreError('invalid')


def metrics_support(account_id, registry):
    _account(account_id, registry)
    # capability나 credential 참조로 인증·구현 상태를 추측하지 않는다.
    connections = [c for c in registry.connections.values() if account_id == 'all' or c.account_id == account_id]
    platforms = dict(_PLATFORMS)
    for connection in connections:
        platforms.setdefault(connection.platform, connection.platform)
    return [dict(platform=platform, label=label, implementation_status='unregistered',
                 auth_status='unknown', collection_status='not_collected')
            for platform, label in platforms.items()]


def build_metrics_snapshot(account_id, registry, store, *, writable=False):
    _account(account_id, registry)
    rows = store.list_observations(account_id)
    return dict(account_id=account_id, observations=rows, proposals=store.list_proposals(account_id),
                support=metrics_support(account_id, registry), summary=dict(
                    verified_observations=sum(r['source_kind'] == 'verified_delivery' for r in rows),
                    legacy_reported=sum(r['source_kind'] == 'legacy_reported' for r in rows),
                    unassigned=sum(r['owner_account_id'] is None and r['destination_account_id'] is None for r in rows)),
                collection_enabled=False, writable=bool(writable))
