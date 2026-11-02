"""읽기 전용 원격 관측을 본문·미디어·대상과 결합한 공개 검증."""
from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import re
from urllib.parse import urlsplit
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
    media=[] if context.get('platform') in ('threads','facebook') and context.get('options',{}).get('text_only') is True else [a['sha256'] for a in assets]
    return hashlib.sha256(text.encode('utf-8')).hexdigest(), media


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


def _threads_url(value):
    if not isinstance(value,str):return None
    try:
        parsed=urlsplit(value)
        if (parsed.scheme=='https' and parsed.hostname in ('threads.net','www.threads.net','threads.com','www.threads.com')
                and not parsed.username and not parsed.password and not parsed.port and not parsed.query and not parsed.fragment
                and re.fullmatch(r'/@[^/]+/post/[A-Za-z0-9_-]+/?',parsed.path)):
            return value
    except ValueError:pass
    return None


def _facebook_url(value):
    # URL만으로 공개 여부를 판단하지 않는다. 상위 검증의 실제 관측과 결속된 URL만 보존한다.
    if type(value) is not str or len(value)>2000 or any(ord(c)<=32 or ord(c)==127 for c in value):return None
    try:
        parsed=urlsplit(value)
        if (parsed.scheme=='https' and parsed.netloc in ('facebook.com','www.facebook.com')
                and not parsed.username and not parsed.password and parsed.port is None
                and not parsed.query and not parsed.fragment and parsed.path not in ('','/')):
            return value
    except ValueError:pass
    return None


def verify_delivery(store, delivery_id, adapter, snapshot, *, now=None, expected_version=None, clock=None):
    if clock is not None and not callable(clock):raise StoreError('invalid')
    live_clock=clock or ((lambda:datetime.now(timezone.utc)) if now is None else None)
    now = utc(now if now is not None else live_clock())
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
    # 관측 I/O가 끝난 시각까지 허용한다. 호출 시작 시각을 상한으로 쓰면 실제 원격 조회는 항상 미래가 된다.
    if live_clock is not None:now=utc(live_clock())
    if not isinstance(result, VerificationResult):
        result = VerificationResult('error', now, {'reason': 'invalid_adapter_result'})
    if result.outcome == 'verified':
        valid_time = attempt and utc(attempt['created_at']) <= result.checked_at <= now
        if delivery['context'].get('platform')=='youtube':
            from .youtube_evidence import youtube_upload_identity
            identity=youtube_upload_identity(delivery['context'],snapshot,result.evidence,attempt,now,delivery['remote_id'])
        else:
            identity=strong_identity(delivery['context'], snapshot, result.evidence, attempt, now, remote_id=delivery['remote_id'])
        if not valid_time or result.evidence.get('visibility') != 'public' or not identity:
            result = VerificationResult('pending', now, {'reason': 'insufficient_publication_evidence'})
        elif delivery['context'].get('platform')=='youtube':
            result=VerificationResult('verified',result.checked_at,dict(result.evidence,verification_method='youtube_upload_receipt_and_public_observation'))
    verified_url=None
    if result.outcome=='verified' and delivery['context'].get('platform')=='threads':
        verified_url=_threads_url(result.evidence.get('url'))
        if verified_url is None:result=VerificationResult('pending',now,{'reason':'insufficient_publication_evidence'})
    if result.outcome=='verified' and delivery['context'].get('platform')=='facebook':
        verified_url=_facebook_url(result.evidence.get('url'))
        if verified_url is None:result=VerificationResult('pending',now,{'reason':'insufficient_publication_evidence'})
    safe_keys = ('remote_id', 'target_id', 'destination_account_id', 'created_at', 'body_sha256', 'media_sha256', 'visibility')
    if result.outcome=='verified' and delivery['context'].get('platform')=='youtube':safe_keys+=('verification_method',)
    if verified_url is not None:safe_keys+=('url',)
    safe_evidence = {k: serial(result.evidence[k]) for k in safe_keys if k in result.evidence}
    if result.outcome=='verified' and delivery['context'].get('platform')=='youtube':
        safe_evidence.pop('body_sha256',None)
        safe_evidence['media_sha256']=None
    if result.evidence.get('reason') in ('adapter_error', 'invalid_adapter_result', 'insufficient_publication_evidence', 'media_evidence_required', 'remote_processing_failed', 'remote_identity_mismatch', 'remote_observation_unavailable', 'youtube_verification_error', 'blog_verification_error'):
        safe_evidence['reason'] = result.evidence['reason']
    result = VerificationResult(result.outcome, result.checked_at, safe_evidence)
    store.record_evidence(delivery_id, 'verification', result.to_dict(), attempt_id=attempt['id'] if attempt else None)
    if result.outcome == 'verified':
        if delivery['state'] != 'published':
            delivery = store.transition_delivery(delivery_id, delivery['version'], 'published', evidence=serial(result.evidence),**({'url':verified_url} if verified_url is not None else {}))
        store.transition_delivery(delivery_id, delivery['version'], 'verified', evidence=serial(result.evidence),**({'url':verified_url} if verified_url is not None else {}))
    return result
