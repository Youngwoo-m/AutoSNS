"""서버 정책 기반 대상·공용 API·제작비 한도. 사용량 원자성은 store 소유."""
import hashlib
import json
import math
from collections.abc import Mapping
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from .content_store import StoreError
from .runtime_models import PublicationContext, utc


def bucket_id(scope_kind, scope_id, metric, window_start, window_end):
    if scope_kind not in ('target', 'api', 'owner') or not all(isinstance(v, str) and v for v in (scope_id, metric)):
        raise StoreError('invalid_quota_policy')
    start, end = utc(window_start), utc(window_end)
    if start >= end:
        raise StoreError('invalid_quota_policy')
    key = [scope_kind, scope_id, metric, start.isoformat(), end.isoformat()]
    return 'quota_' + hashlib.sha256(json.dumps(key, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def quota_window(requirement, now):
    if requirement.get('window_kind') == 'day':
        try:
            zone = ZoneInfo(requirement['timezone'])
        except (KeyError, TypeError, ZoneInfoNotFoundError) as exc:
            raise StoreError('invalid_quota_policy') from exc
        day = utc(now).astimezone(zone).date()
        return (utc(datetime.combine(day, time.min, zone)),
                utc(datetime.combine(day + timedelta(days=1), time.min, zone)))
    if 'window_kind' in requirement:
        raise StoreError('invalid_quota_policy')
    try:
        return utc(requirement['window_start']), utc(requirement['window_end'])
    except KeyError as exc:
        raise StoreError('invalid_quota_policy') from exc


def _context(store, ctx):
    if isinstance(ctx, PublicationContext):
        matches = [d for d in store.list_operations() if d.get('context_hash') == ctx.context_hash]
        if len(matches) != 1:
            raise StoreError('delivery_required')
        return matches[0]['id'], ctx
    if not isinstance(ctx, Mapping) or set(ctx) != {'delivery_id', 'context'} or not isinstance(ctx['context'], PublicationContext):
        raise StoreError('invalid')
    row = store.get_delivery(ctx['delivery_id'])
    if row is None or row['context_hash'] != ctx['context'].context_hash:
        raise StoreError('context_changed')
    return ctx['delivery_id'], ctx['context']


def reserve_quota(store, ctx, observed_usage, now):
    now = utc(now)
    delivery_id, context = _context(store, ctx)
    registry = store.registry
    policy = registry.policies.get(context.policy_revision) if registry else None
    rows = policy.get('quota_requirements') if isinstance(policy, Mapping) else None
    if not isinstance(rows, (list, tuple)) or not rows:
        raise StoreError('quota_policy_required')
    if not isinstance(observed_usage, Mapping):
        raise StoreError('invalid')
    requirements, productions, observations, kinds = [], [], [], set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise StoreError('invalid_quota_policy')
        try:
            kind, scope, metric = row['scope_kind'], row['scope_id'], row['metric']
            limit, amount = row['limit'], row['amount']
        except KeyError as exc:
            raise StoreError('invalid_quota_policy') from exc
        if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in (limit, amount)):
            raise StoreError('invalid_quota_policy')
        if (kind == 'target' and scope != context.target_id) or (kind == 'owner' and scope != context.owner_account_id):
            raise StoreError('quota_scope_mismatch')
        start, end = quota_window(row, now)
        id = bucket_id(kind, scope, metric, start, end)
        if not start <= now < end:
            raise StoreError('quota_window_expired')
        kinds.add(kind)
        requirement = {'bucket_id': id, 'amount': amount}
        if kind == 'owner':
            production_label = row.get('production_id', 'original')
            if not isinstance(production_label, str) or not production_label:
                raise StoreError('invalid_quota_policy')
            identity = [context.owner_account_id, context.content_id, context.content_revision,
                        context.manifest_hash, metric, production_label]
            production_id = 'production_' + hashlib.sha256(json.dumps(identity, separators=(',', ':')).encode()).hexdigest()
            productions.append({'production_id': production_id, 'requirement': requirement})
            existing = store.get_production(production_id)
            if existing is not None and existing['state'] != 'released':
                # Creation belongs to its original accounting period. Reposting
                # the same produced artifact does not create it again tomorrow.
                continue
        else:
            requirements.append(requirement)
        observation = observed_usage.get(id)
        if observation is not None:
            if not isinstance(observation, Mapping) or set(observation) != {'observed_usage', 'observed_at', 'expires_at'}:
                raise StoreError('invalid_quota_observation')
            at, expires = utc(observation['observed_at']), utc(observation['expires_at'])
            if not start <= at <= now < expires <= end:
                raise StoreError('quota_observation_required')
            observations.append((id, limit, observation['observed_usage'], at, expires))
        else:
            # Capacity is policy-owned even when a prior observation is reused.
            old = next((b for b in store.quota_buckets() if b['id'] == id), None)
            if old is None or old['capacity'] != limit:
                raise StoreError('quota_observation_required')
    all_requirements = requirements + [p['requirement'] for p in productions]
    if kinds != {'target', 'api', 'owner'} or len({r['bucket_id'] for r in all_requirements}) != len(all_requirements):
        raise StoreError('invalid_quota_policy')
    # Observations do not consume capacity. All reservations are made together by
    # one RuntimeStore transaction, so competing callers cannot overbook.
    for observation in observations:
        store.observe_bucket(*observation)
    return store.reserve_quota(delivery_id, requirements, now, production_requirements=productions)['id']


def settle_quota(store, reservation_id, outcome):
    if outcome in ('submitted', 'scheduled'):
        store.settle_reservation(reservation_id)
    elif outcome in ('confirmed_not_submitted', 'confirmed_not_posted'):
        store.settle_reservation(reservation_id, release=True)
    elif outcome in ('unknown', 'failed'):
        return  # 실패만으로 미제출을 확정하지 않는다.
    else:
        raise StoreError('invalid_outcome')
