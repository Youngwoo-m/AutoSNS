"""계정 관련 관측을 근거로 반환하는 읽기 전용 기획 문맥. 기획기 실행 없음."""
import json
from urllib.parse import urlsplit, urlunsplit
from .metrics import build_metrics_snapshot
from .runtime_store import RuntimeStore


def _key(row):
    # 배포·연결 별칭·콘텐츠 버전이 달라도 물리 게시의 같은 측정치는 한 번만 센다.
    # 각 관측의 버전 연결은 원본 observation.source에 그대로 남는다.
    return (row['destination_account_id'], row['platform'], row['target_id'], row['remote_id'],
            row['definition_id'], row['basis'], json.dumps(row['period'], sort_keys=True))


def _projection(rows, account):
    groups, physical_failures, order = {}, {}, {}
    for index, row in enumerate(rows):
        if row['source_kind'] == 'verified_delivery':
            key = _key(row)
            groups.setdefault(key, []).append(row)
            order[row['id']] = (row['collected_at'] or '', index)
            # 정의를 알 수 없는 예외·미등록은 특정 지표 결과가 아닌 게시 단위 실패다.
            if (row['status'] in ('error', 'unsupported')
                    and row['definition_id'] in ('collection.error', 'collection.unsupported')
                    and row['basis'] == 'unknown' and row['period'] is None):
                physical_failures.setdefault(key[:4], []).append(row)
    evidence, buckets = [], {}
    for key, metric_history in groups.items():
        metric_history.sort(key=lambda row: order[row['id']])
        latest_metric = metric_history[-1]
        linked = {row['id']: row for row in metric_history}
        for row in physical_failures.get(key[:4], ()):
            linked[row['id']] = row
        # 같은 시각은 append 순서로 정한다. 최신 실패와 이전 성공을 함께 보존한다.
        history = sorted(linked.values(), key=lambda row: order[row['id']])
        latest = history[-1]
        success = next((r for r in reversed(metric_history) if r['status'] == 'ok'), None)
        scope = 'physical_post' if latest in physical_failures.get(key[:4], ()) else 'metric'
        evidence.append(dict(delivery_id=latest_metric['delivery_id'], definition_id=latest_metric['definition_id'],
                             basis=latest_metric['basis'], period=latest_metric['period'], latest_observation_id=latest['id'],
                             latest_status=latest['status'], latest_scope=scope,
                             latest_metric_observation_id=latest_metric['id'],
                             previous_success_observation_id=success['id'] if success else None,
                             observation_ids=[r['id'] for r in history]))
        if success is None or (account != 'all' and success['destination_account_id'] != account):
            continue
        group = (success['destination_account_id'], success['platform'], success['definition_id'],
                 success['basis'], json.dumps(success['period'], sort_keys=True))
        aggregate = buckets.setdefault(group, dict(destination_account_id=success['destination_account_id'],
            platform=success['platform'], definition_id=success['definition_id'], basis=success['basis'],
            period=success['period'], values={}, observation_ids=[]))
        for metric, value in success['values'].items():
            aggregate['values'][metric] = aggregate['values'].get(metric, 0) + value
        aggregate['observation_ids'].append(success['id'])
    return evidence, list(buckets.values())


def production_budget_evidence(account_id, runtime):
    """공용 제작ID의 예산 예약/정산만 원본 소유자에게 귀속. 실제 과금은 미확인."""
    owners = {}
    for delivery in runtime.list_operations('all'):
        owner = delivery['context'].get('owner_account_id')
        for attempt in runtime.attempts(delivery['id']):
            reservation_id = attempt.get('reservation_id')
            if not reservation_id:
                continue
            reservation = runtime.get_reservation(reservation_id)
            for production_id in (reservation or {}).get('production_ids', ()):
                owners.setdefault(production_id, set()).add(owner)
    result, seen = [], set()
    for production in runtime.list_productions():
        pid = production['id']
        if pid in seen:
            continue
        seen.add(pid)
        candidates = owners.get(pid, set())
        owner = next(iter(candidates)) if len(candidates) == 1 else None
        if owner not in ('personal', 'dept'):
            owner = None
        if account_id != 'all' and owner != account_id:
            continue
        result.append(dict(production_id=pid, owner_account_id=owner, state=production['state'],
            budget_requirements=[dict(bucket_id=r['bucket_id'], amount=r['amount']) for r in production['requirements']],
            created_at=production.get('created_at'), settled_at=production.get('settled_at'),
            actual_cost=None, currency=None, monetary_status='unknown', definition_id='production.budget_reservation'))
    return result


def _sites(account_id, registry):
    rows = []
    for connection in registry.connections.values():
        if account_id != 'all' and connection.account_id != account_id:
            continue
        target = connection.target_id
        if target and '://' in target:
            parsed = urlsplit(target)
            if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
                target = None
            else:
                target = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, '', ''))
        rows.append(dict(connection_id=connection.id, account_id=connection.account_id,
                         platform=connection.platform, target_id=target, label=connection.target_label))
    return rows


def build_planning_context(account_id, registry, store, *, runtime_store=None):
    snapshot = build_metrics_snapshot(account_id, registry, store)
    rows = snapshot['observations']
    evidence, aggregates = _projection(rows, account_id)
    runtime = runtime_store if runtime_store is not None else RuntimeStore(store.root, registry=registry)
    definitions = sorted({r['definition_id'] for r in rows})
    periods = []
    for row in rows:
        value = dict(definition_id=row['definition_id'], basis=row['basis'], period=row['period'])
        if value not in periods:
            periods.append(value)
    missing = [dict(observation_id=r['id'], status=r['status'], uncertainties=list(r['uncertainties']))
               for r in rows if r['status'] in ('error', 'unsupported') or r['uncertainties']]
    if not rows:
        missing.append(dict(observation_id=None, status='not_collected', uncertainties=['수집된 성과 없음']))
    return dict(account_id=account_id, observation_ids=[r['id'] for r in rows], observations=rows,
                legacy_observation_ids=[r['id'] for r in rows if r['source_kind'] == 'legacy_reported'],
                metric_evidence=evidence, destination_metrics=aggregates,
                interval_metrics=[r for r in aggregates if r['basis'] == 'interval'],
                definitions=definitions, periods=periods, missing=missing, support=snapshot['support'],
                registered_sites=_sites(account_id, registry), proposals=snapshot['proposals'],
                production_budget_evidence=production_budget_evidence(account_id, runtime),
                collection_enabled=False,
                notes=['누적값을 기간 발생량으로 합산하지 않음', '과거 보고는 검증 게시 총계와 분리',
                       '제작 예산 예약·정산은 실제 과금 관측이 아님', '제안은 별도 저장 초안이며 원본·승인을 만들지 않음'])
