"""등록부로 확정한 회차 제출과 queued 전용 lease 분배. 외부 호출 없음."""
import os
import socket
import math
from datetime import datetime, timezone
from collections.abc import Mapping
from .content_store import StoreError, ConflictError
from .runtime_models import ExecutionPolicy, RunLease, utc

_PROCESS_STARTED_AT = datetime.now(timezone.utc).isoformat()
_FIELDS = {'job_id', 'scheduled_at_utc', 'phase', 'source', 'request_kind', 'mode'}


def _connections(job):
    ids = job.get('connection_ids')
    if ids is None:
        ids = [job.get('connection_id')]
    if not isinstance(ids, (list, tuple)) or not ids or not all(isinstance(x, str) and x for x in ids):
        raise StoreError('unknown_connection')
    return ids


def submit_trigger(store, request, registry, policy):
    """새 회차를 원자 기록하고 resume은 알려진 회차만 반환한다."""
    if not isinstance(request, dict) or set(request) != _FIELDS:
        raise StoreError('invalid_request')
    if (request['phase'] not in ('prepare', 'submit', 'verify') or
        request['source'] not in ('launchd', 'console') or
        request['request_kind'] not in ('new_publication', 'resume') or
        request['mode'] not in ('live', 'dry', 'shadow') or
        not isinstance(request['job_id'], str)):
        raise StoreError('invalid_request')
    normalized = dict(request, scheduled_at_utc=utc(request['scheduled_at_utc']).isoformat())
    job = registry.jobs.get(request['job_id'])
    if not job:
        raise StoreError('unknown_job')
    if job.get('execution_owner') != 'managed' or job.get('schedule_owner') not in ('launchd', 'console'):
        raise StoreError('legacy_owner')
    if job.get('enabled') is not True:
        raise StoreError('job_disabled')
    job_policy = registry.policies.get(job.get('policy_revision'))
    if not isinstance(job_policy, Mapping):
        raise StoreError('unknown_policy')
    ids = _connections(job)
    for id in ids:
        connection = registry.connections.get(id)
        if connection is None:
            raise StoreError('unknown_connection')
        if connection.account_id != job.get('owner_account_id'):
            rules = getattr(registry, 'crossposts', {}).values()
            allowed = any(rule.get('enabled') is True and rule.get('owner_account_id') == job.get('owner_account_id')
                          and rule.get('destination_connection_id') == id
                          and registry.connections.get(rule.get('source_connection_id')) is not None
                          and registry.connections[rule['source_connection_id']].account_id == job.get('owner_account_id')
                          for rule in rules)
            if not allowed:
                raise StoreError('owner_mismatch')
        if request['mode'] == 'live' and not connection.enabled:
            raise StoreError('connection_disabled')
    if request['mode'] == 'live':
        if not isinstance(policy, ExecutionPolicy) or not policy.enabled:
            raise StoreError('execution_disabled')
        if not policy.cutover_revision:
            raise StoreError('cutover_required')
        if any(id not in policy.allowed_connection_ids for id in ids):
            raise StoreError('connection_not_allowed')
        if policy.provider_policy.get('subscription_only') is True and job_policy.get('subscription_only') is not True:
            raise StoreError('provider_policy_violation')
    if request['mode'] == 'shadow':
        return dict(normalized, state='shadow')
    if request['request_kind'] == 'resume':
        # list_runs carries runtime state; the store's occurrence payload is not
        # consulted through private SQL. Match IDs via read-only public lookup.
        for run in store.list_runs():
            occurrence = run.get('occurrence')
            if occurrence and all(occurrence.get(k) == normalized[k] for k in ('job_id', 'scheduled_at_utc', 'phase')):
                if occurrence.get('mode') != normalized['mode']:
                    raise ConflictError()
                return dict(occurrence, id=run['id'], runtime=run)
        raise StoreError('unknown_occurrence')
    return store.submit_occurrence(normalized)


def run_is_due(run, now):
    scheduled=(run.get('occurrence') or {}).get('scheduled_at_utc')
    return scheduled is not None and utc(scheduled)<=utc(now)


def claim_next_run(store, worker_id, now, lease_seconds):
    now = utc(now)
    if (not isinstance(worker_id, str) or not worker_id or type(lease_seconds) not in (int, float)
        or not math.isfinite(lease_seconds) or lease_seconds <= 0):
        raise StoreError('invalid')
    identity = {'host_id': socket.gethostname(), 'pid': os.getpid(), 'started_at': _PROCESS_STARTED_AT}
    for run in store.list_runs(state='queued'):
        if not run_is_due(run, now):
            continue
        try:
            return store.claim_run(run['id'], worker_id, identity, now, lease_seconds,
                                   expected_version=run['version'])
        except ConflictError:
            continue
    return None


def heartbeat(store, lease, now):
    now = utc(now)
    if not isinstance(lease, RunLease):
        raise StoreError('invalid')
    current = store.get_run(lease.run_id)
    if (current is None or current['state'] != 'running' or current['worker_id'] != lease.worker_id
        or current['generation'] != lease.generation or not current['lease_expires_at']
        or utc(current['lease_expires_at']) <= now):
        return False
    fresh = RunLease(lease.run_id, lease.worker_id, lease.generation, utc(current['lease_expires_at']))
    try:
        store.renew_lease(fresh, now)
        return True
    except ConflictError:
        return False
