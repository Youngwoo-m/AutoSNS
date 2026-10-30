"""불확실 제출을 재전송하지 않는 CAS 복구 서비스. 외부 쓰기 없음."""
from collections.abc import Mapping
from datetime import datetime, timezone
from .content_store import StoreError, ConflictError
from .runtime_models import PublicationContext, LookupResult, ExecutionPolicy, utc, serial
from .verification import strong_identity


def _delivery(store, delivery_id, expected_version):
    if type(expected_version) is not int or expected_version < 0:
        raise StoreError('invalid')
    delivery = store.get_delivery(delivery_id)
    if not delivery:
        raise StoreError('not_found')
    if delivery['version'] != expected_version:
        raise ConflictError()
    return delivery


def _request_key(value):
    if not isinstance(value, str) or not value:
        raise StoreError('invalid')


def _process_evidence(identity, probe):
    unknown = {'status': 'unknown'}
    if not isinstance(identity, Mapping) or not callable(probe):
        return unknown
    try:
        result = probe(dict(identity))
        if not isinstance(result, Mapping) or result.get('status') not in ('dead', 'alive'):
            return unknown
        if not isinstance(identity.get('host_id'), str) or not identity['host_id'] or type(identity.get('pid')) is not int or identity['pid'] <= 0:
            return unknown
        if result.get('host_id') != identity['host_id'] or type(result.get('pid')) is not int or result['pid'] != identity['pid'] or utc(result.get('started_at')) != utc(identity['started_at']):
            return unknown
        return dict(identity, status=result['status'])
    except Exception:
        return unknown


def _lock_evidence(context, probe):
    try:
        result = probe(dict(context)) if callable(probe) else None
        if isinstance(result, Mapping) and result.get('connection_id') == context['connection_id'] and result.get('status') in ('free', 'held'):
            return {'status': result['status'], 'connection_id': context['connection_id']}
    except Exception:
        pass
    return {'status': 'unknown'}


def recover_expired_runs(store, now, process_probe, *, lock_probe=None):
    now = utc(now)
    results = []
    for run in store.list_runs():
        if not run.get('lease_expires_at') or utc(run['lease_expires_at']) > now:
            continue
        deliveries = [d for d in store.list_operations() if d['run_id'] == run['id']]
        if not any(d['state'] in ('running', 'submitting', 'retry_wait') for d in deliveries):
            continue
        process = _process_evidence(run.get('process_identity'), process_probe)
        locks = {d['id']: _lock_evidence(d['context'], lock_probe) for d in deliveries}
        results.append(store.recover_expired_run(run['id'], run['version'], now, process, locks))
        for delivery in deliveries:
            if store.get_delivery(delivery['id'])['state'] == 'retry_wait':
                _settle_attempts(store, delivery['id'], now=now)
    return results


def _lookup(store, delivery, adapter, now):
    if adapter is None:
        raise StoreError('adapter_unavailable')
    attempts = store.attempts(delivery['id'])
    attempt = attempts[-1] if attempts else None
    try:
        result = adapter.lookup(PublicationContext(**delivery['context']), attempt)
    except Exception:
        result = LookupResult('error', evidence={'reason': 'adapter_error'})
    if not isinstance(result, LookupResult):
        result = LookupResult('error', evidence={'reason': 'invalid_adapter_result'})
    # 어댑터 증거 원문에 토큰/경로가 포함될 수 있으므로 필요한 필드만 원장에 남긴다.
    store.record_evidence(delivery['id'], 'remote_lookup', {'outcome': result.outcome, 'candidate_count': len(result.candidates), 'checked_at': now.isoformat()}, attempt_id=attempt['id'] if attempt else None)
    if result.outcome != 'matched' or len(result.candidates) != 1 or not attempt:
        return None, attempt
    content_store = getattr(store, 'content_store', None)
    if content_store is None:
        return None, attempt
    snapshot = content_store.get(delivery['context']['content_id'], delivery['context']['content_revision'])
    candidate = result.candidates[0]
    if not strong_identity(delivery['context'], snapshot, candidate, attempt, now):
        return None, attempt
    evidence = {k: serial(candidate[k]) for k in ('remote_id', 'target_id', 'destination_account_id', 'created_at', 'body_sha256', 'media_sha256')}
    evidence.update(identity_confirmed=True, checked_at=now.isoformat())
    return evidence, attempt


def _settle_attempts(store, delivery_id, *, now, request_key=None):
    for attempt in store.attempts(delivery_id):
        result = attempt.get('result') or {}
        resolution = result.get('resolution', {})
        if not attempt.get('reservation_id') or not attempt['resolved']:
            continue
        if request_key is not None and resolution.get('request_key') != request_key:
            continue
        reservation = store.get_reservation(attempt['reservation_id'])
        if reservation is None or reservation['state'] != 'held':
            continue
        release = resolution.get('kind') == 'confirmed_not_posted'
        release = release or (not attempt['request_started'] and attempt['outcome'] == 'failed'
                              and result.get('evidence', {}).get('confirmed_not_submitted') is True)
        used = resolution.get('kind') == 'link_existing' or attempt['outcome'] in ('submitted', 'scheduled')
        if release or used:
            store.settle_reservation(attempt['reservation_id'], release=release, now=now)


def reconcile_delivery(store, delivery_id, adapter, now, *, expected_version, request_key, actor='recovery_service'):
    _request_key(request_key)
    request_evidence = {'source': 'reconcile'}
    note = 'server adapter matched remote identity'
    replay = store.get_resolution_result(delivery_id, expected_version, request_key, 'link_existing', request_evidence, note, actor)
    if replay is not None:
        _settle_attempts(store, delivery_id, request_key=request_key, now=utc(now))
        return replay
    delivery = _delivery(store, delivery_id, expected_version)
    if delivery['state'] not in ('unknown', 'needs_review', 'failed', 'retry_wait') and not (delivery['state'] == 'cancelled' and delivery['remote_uncertain']):
        raise ConflictError()
    now = utc(now)
    evidence, attempt = _lookup(store, delivery, adapter, now)
    if evidence is None:
        return store.record_resolution_observation(delivery_id, expected_version, request_key, 'link_existing', request_evidence, note, actor)
    result = store.resolve_delivery(delivery_id, expected_version, request_key, 'link_existing', evidence, note, actor, request_evidence=request_evidence)
    _settle_attempts(store, delivery_id, request_key=request_key, now=now)
    return result


def resolve_unknown(store, delivery_id, decision, actor, *, process_probe=None, lock_probe=None, adapter=None, now=None):
    if not isinstance(decision, dict) or set(decision) != {'expected_version', 'request_key', 'kind', 'evidence', 'note'} or not isinstance(actor, str) or not actor:
        raise StoreError('invalid')
    _request_key(decision['request_key'])
    kind = decision['kind']
    evidence = decision['evidence']
    if not isinstance(evidence, dict) or not evidence or not isinstance(decision['note'], str) or not decision['note']:
        raise StoreError('invalid')
    now = utc(now if now is not None else datetime.now(timezone.utc))
    request_evidence = dict(evidence)
    replay = store.get_resolution_result(delivery_id, decision['expected_version'], decision['request_key'], kind, request_evidence, decision['note'], actor)
    if replay is not None:
        if kind != 'cancel_local':
            _settle_attempts(store, delivery_id, request_key=decision['request_key'], now=now)
        return replay
    delivery = _delivery(store, delivery_id, decision['expected_version'])
    if kind == 'link_existing':
        confirmed, _ = _lookup(store, delivery, adapter, now)
        if not confirmed or confirmed['remote_id'] != evidence.get('remote_id'):
            raise StoreError('insufficient_evidence')
        evidence = confirmed
    elif kind == 'confirmed_not_posted':
        run = store.get_run(delivery['run_id'])
        process = _process_evidence(run.get('process_identity') if run else None, process_probe)
        lock = _lock_evidence(delivery['context'], lock_probe)
        if evidence.get('confirmed_not_posted') is not True or process['status'] != 'dead' or lock['status'] != 'free':
            raise StoreError('insufficient_evidence')
        evidence = {'confirmed_not_posted': True, 'old_process_terminated': True, 'profile_lock_released': True, 'process': process, 'lock': lock, 'checked_at': now.isoformat()}
    elif kind == 'cancel_local':
        evidence = {'local_only': True}
    else:
        raise StoreError('invalid')
    result = store.resolve_delivery(delivery_id, decision['expected_version'], decision['request_key'], kind, evidence, decision['note'], actor, request_evidence=request_evidence)
    if kind != 'cancel_local':
        _settle_attempts(store, delivery_id, request_key=decision['request_key'], now=now)
    return result


def retryable_delivery_ids(store, run_id):
    run = store.get_run(run_id)
    if not run:
        return []
    result = []
    for delivery in store.list_operations():
        if delivery['run_id'] != run_id or delivery['state'] != 'retry_wait' or delivery['remote_uncertain']:
            continue
        attempts = store.attempts(delivery['id'])
        if any(not a['resolved'] for a in attempts):
            continue
        if run.get('process_identity'):
            proof = None
            if attempts:
                evidence = (attempts[-1].get('result') or {}).get('resolution', {}).get('evidence', {})
                if evidence.get('old_process_terminated') is True and evidence.get('profile_lock_released') is True:
                    proof = evidence
            if proof is None:
                observations = [e['evidence'] for e in store.events(delivery['id']) if e['kind'] == 'recovery_observation']
                if not observations:
                    continue
                proof = observations[-1]
            process = _process_evidence(run['process_identity'], lambda identity: proof.get('process'))
            lock = _lock_evidence(delivery['context'], lambda context: proof.get('lock'))
            if process['status'] != 'dead' or lock['status'] != 'free':
                continue
        result.append(delivery['id'])
    return result


def retry_delivery(store, delivery_id, decision, actor, *, policy=None, registry=None,
                   process_probe=None, lock_probe=None, now=None):
    """서버 전용 재개. 외부 제출 없이 같은 delivery와 run만 다시 큐에 넣는다."""
    if not isinstance(policy, ExecutionPolicy) or not policy.enabled:
        raise StoreError('execution_disabled')
    if not isinstance(decision, dict) or set(decision) != {'expected_version', 'request_key'} or not isinstance(actor, str) or not actor:
        raise StoreError('invalid')
    _request_key(decision['request_key'])
    replay = store.get_resolution_result(delivery_id, decision['expected_version'], decision['request_key'], 'retry', {}, 'resume existing delivery', actor)
    if replay is not None:
        return replay
    delivery = _delivery(store, delivery_id, decision['expected_version'])
    run = store.get_run(delivery['run_id'])
    occurrence = (run or {}).get('occurrence') or {}
    if occurrence.get('mode') != 'live' or occurrence.get('phase') != 'submit' or registry is None:
        raise StoreError('invalid_resume')
    from .dispatch import submit_trigger
    request = {key: occurrence.get(key) for key in ('job_id', 'scheduled_at_utc', 'phase', 'mode')}
    request.update(source='console', request_kind='resume')
    resumed = submit_trigger(store, request, registry, policy)
    if resumed['id'] != delivery['run_id']:
        raise ConflictError()
    context = delivery['context']
    job = registry.jobs[occurrence['job_id']]
    connection_ids = job.get('connection_ids', [job.get('connection_id')])
    connection = registry.connections.get(context['connection_id'])
    if context['connection_id'] not in policy.allowed_connection_ids:
        raise StoreError('connection_not_allowed')
    if (context['connection_id'] not in connection_ids or connection is None
        or job.get('owner_account_id') != context['owner_account_id']
        or job.get('policy_revision') != context['policy_revision']
        or connection.account_id != context['destination_account_id']
        or connection.target_id != context['target_id']
        or (context.get('platform') and connection.platform != context['platform'])):
        raise StoreError('context_changed')
    now = utc(now if now is not None else datetime.now(timezone.utc))
    if not run.get('lease_expires_at') or utc(run['lease_expires_at']) > now:
        raise StoreError('worker_active')
    process = _process_evidence(run.get('process_identity'), process_probe)
    lock = _lock_evidence(delivery['context'], lock_probe)
    if process['status'] != 'dead' or lock['status'] != 'free':
        raise StoreError('insufficient_evidence')
    return store.requeue_delivery(delivery_id, decision['expected_version'], decision['request_key'], actor,
                                  expected_run_version=run['version'], process_evidence=process,
                                  lock_evidence=lock, now=now)
