"""읽기 전용 원격 관측을 본문·미디어·대상과 결합한 공개 검증."""
from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
from .content_store import StoreError, ConflictError
from .runtime_models import PublicationContext, VerificationResult, utc, serial


def snapshot_fingerprints(context, snapshot):
    if not isinstance(snapshot, Mapping) or snapshot.get('manifest_hash') != context['manifest_hash'] or snapshot.get('revision') != context['content_revision']:
        raise StoreError('content_changed')
    text = snapshot.get('original')
    variants = [v for v in snapshot.get('variants', ()) if v.get('destination_account_id') == context['destination_account_id'] and v.get('platform') == context.get('platform')]
    if len(variants) > 1:
        raise StoreError('content_changed')
    if variants:
        text = variants[0].get('text')
    assets = snapshot.get('assets')
    if not isinstance(text, str) or not isinstance(assets, (list, tuple)) or any(not isinstance(a, Mapping) or not isinstance(a.get('sha256'), str) or not a['sha256'] for a in assets):
        raise StoreError('insufficient_evidence')
    return hashlib.sha256(text.encode('utf-8')).hexdigest(), [a['sha256'] for a in assets]


def strong_identity(context, snapshot, candidate, attempt, now, *, remote_id=None):
    """제목/URL 유사성이나 클라이언트의 identity_confirmed는 사용하지 않는다."""
    if not isinstance(candidate, Mapping) or not attempt:
        return False
    try:
        body, media = snapshot_fingerprints(context, snapshot)
        return (isinstance(candidate.get('remote_id'), str) and bool(candidate['remote_id'])
                and (remote_id is None or candidate['remote_id'] == remote_id)
                and candidate.get('target_id') == context['target_id']
                and candidate.get('destination_account_id') == context['destination_account_id']
                and utc(attempt['created_at']) <= utc(candidate.get('created_at')) <= utc(now)
                and candidate.get('body_sha256') == body
                and isinstance(candidate.get('media_sha256'), (list, tuple))
                and list(candidate['media_sha256']) == media)
    except (StoreError, ValueError, TypeError, KeyError):
        return False


def verify_delivery(store, delivery_id, adapter, snapshot, *, now=None, expected_version=None):
    now = utc(now if now is not None else datetime.now(timezone.utc))
    delivery = store.get_delivery(delivery_id)
    if not delivery:
        raise StoreError('not_found')
    if expected_version is not None and delivery['version'] != expected_version:
        raise ConflictError()
    if adapter is None:
        raise StoreError('adapter_unavailable')
    if delivery['state'] == 'verified':
        return VerificationResult('verified', now, {'already_verified': True})
    if delivery['state'] not in ('uploaded', 'scheduled', 'published') or not delivery.get('remote_id'):
        return VerificationResult('pending', now, {'reason': 'reconciliation_required'})
    condition = delivery['context'].get('schedule_condition', {})
    due_times = [delivery.get('scheduled_at')]
    if condition.get('kind') == 'fixed':
        due_times.append(condition.get('at'))
    if condition.get('kind') == 'window':
        due_times.append(condition.get('from'))
    if any(utc(value) > now for value in due_times if value is not None):
        return VerificationResult('pending', now, {'reason': 'scheduled_not_due'})
    snapshot_fingerprints(delivery['context'], snapshot)
    attempts = store.attempts(delivery_id)
    attempt = attempts[-1] if attempts else None
    try:
        result = adapter.verify(PublicationContext(**delivery['context']), delivery['remote_id'], snapshot)
    except Exception:
        result = VerificationResult('error', now, {'reason': 'adapter_error'})
    if not isinstance(result, VerificationResult):
        result = VerificationResult('error', now, {'reason': 'invalid_adapter_result'})
    if result.outcome == 'verified':
        valid_time = attempt and utc(attempt['created_at']) <= result.checked_at <= now
        if not valid_time or result.evidence.get('visibility') != 'public' or not strong_identity(delivery['context'], snapshot, result.evidence, attempt, now, remote_id=delivery['remote_id']):
            result = VerificationResult('pending', now, {'reason': 'insufficient_publication_evidence'})
    safe_keys = ('remote_id', 'target_id', 'destination_account_id', 'created_at', 'body_sha256', 'media_sha256', 'visibility')
    safe_evidence = {k: serial(result.evidence[k]) for k in safe_keys if k in result.evidence}
    if result.evidence.get('reason') in ('adapter_error', 'invalid_adapter_result', 'insufficient_publication_evidence'):
        safe_evidence['reason'] = result.evidence['reason']
    result = VerificationResult(result.outcome, result.checked_at, safe_evidence)
    store.record_evidence(delivery_id, 'verification', result.to_dict(), attempt_id=attempt['id'] if attempt else None)
    if result.outcome == 'verified':
        if delivery['state'] != 'published':
            delivery = store.transition_delivery(delivery_id, delivery['version'], 'published', evidence=serial(result.evidence))
        store.transition_delivery(delivery_id, delivery['version'], 'verified', evidence=serial(result.evidence))
    return result
