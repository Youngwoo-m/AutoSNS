"""단일 managed 제출 경계. 실제 기본 adapter 등록은 비어 있다."""
from datetime import datetime, timezone, timedelta
import time
import os
import socket
import hashlib
from .models import ContractError, thaw
from .runtime_models import PublicationContext, SubmissionResult, utc
from .publication_gate import authorize_submission, consume_permit, _inputs, _snapshot, fresh_lease, require_publication_approval

from .quota import reserve_quota, settle_quota


_PROCESS_START=datetime.now(timezone.utc).isoformat()

def _identity():
    return {'host_id':socket.gethostname(),'pid':os.getpid(),'started_at':_PROCESS_START}


def _redact(value,nonce):
    if isinstance(value,str):return value.replace(nonce,'<redacted>')
    if isinstance(value,dict):return {_redact(k,nonce):_redact(v,nonce) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [_redact(v,nonce) for v in value]
    return value


def _abandon_unstarted(store,delivery_id,reservation,now):
    """DB로 확인한 미소비만 해제한다. 소비 선행/DB 불명은 held를 유지한다."""
    attempts=[a for a in store.attempts(delivery_id) if a.get('reservation_id')==reservation]
    if any(a['request_started'] for a in attempts):return
    for attempt in attempts:
        if not attempt['resolved']:
            store.finish_attempt(attempt['id'],'failed',evidence={'confirmed_not_submitted':True,'reason':'submission_gate_blocked'},now=now)
    settle_quota(store,reservation,'confirmed_not_submitted')
    delivery=store.get_delivery(delivery_id)
    if delivery['state'] in ('queued','running','retry_wait'):
        store.transition_delivery(delivery_id,delivery['version'],'needs_review',evidence={'reason':'submission_gate_blocked'})


def run_once(store,registry,adapters,policy,locks,now):
    """adapters/policy/locks는 서버 시작 시 주입하며 HTTP 입력을 받지 않는다."""
    if not policy.enabled:return None
    started=time.monotonic()
    def current_time():return utc(now)+timedelta(seconds=time.monotonic()-started)
    # mode/phase 필터를 claim 전에 적용해 dry/shadow에서 adapter 호출 0.
    identity=_identity()
    eligible={r['id']:r for r in store.list_runs() if (r.get('occurrence') or {}).get('mode')=='live' and (r.get('occurrence') or {}).get('phase')=='submit' and (r['state']=='queued' or (r['state']=='running' and r.get('process_identity')==identity))}
    deliveries=[d for d in store.list_operations() if d['run_id'] in eligible and d['state']=='queued' and d['context']['connection_id'] in adapters and eligible[d['run_id']].get('resume_delivery_id') in (None,d['id'])]
    if not deliveries:return None
    delivery=deliveries[0];run=store.get_run(delivery['run_id'])
    store.registry=registry;store.execution_policy=policy;store.locks=locks
    ctx=PublicationContext(**delivery['context']);adapter=adapters[ctx.connection_id]
    require_publication_approval(store,delivery['id'],ctx)
    connection=registry.connections[ctx.connection_id]
    # Profile refs are server-owned symbols; never accept a path or executor from a request.
    resource=connection.profile_ref
    profile=registry.profiles.get(resource) if resource else None
    if not profile or profile.get('account_id')!=connection.account_id or profile.get('lock_resource') not in ('profile:naver','profile:insta','profile:tiktok','profile:youtube-dept','profile:insta-manual','profile:safeworking','profile:tistory','profile:youtube-personal'):
        raise ContractError('profile_lock_required')
    with locks.hold([profile['lock_resource']],job='managed-publication',wait=2400):
        # No SQLite transaction/control gate/lease was held during profile wait.
        run=store.get_run(ctx.run_id)
        if run.get('resume_delivery_id') not in (None,delivery['id']):return None
        if run['state']=='queued':
            lease=store.claim_run(run['id'],'managed-worker',identity,current_time(),expected_version=run['version'])
        elif run['state']=='running' and run.get('process_identity')==identity:
            lease=fresh_lease(store,ctx.run_id,current_time())
        else:return None
        _inputs(store,ctx,current_time())
        lease=fresh_lease(store,ctx.run_id,current_time())
        snapshot=_snapshot(store,ctx.content_id,ctx.content_revision,ctx.manifest_hash)
        approval=require_publication_approval(store,delivery['id'],ctx)
        prepared=adapter.prepare(ctx,snapshot)  # contractual pure local work
        # Stable across a crash before attempt creation; different delivery/run/version/ordinal never share it.
        logical=f"{delivery['id']}:{ctx.run_id}:{ctx.context_hash}:{delivery['version']}:{len(store.attempts(delivery['id']))+1}"
        reservation='worker_reservation_'+hashlib.sha256(logical.encode()).hexdigest()
        try:
            reserve_quota(store,{'delivery_id':delivery['id'],'context':ctx},{},current_time(),reservation_id=reservation)
            permit=authorize_submission(store,ctx,snapshot,approval,lease,reservation,current_time())
            consume_permit(store,permit,ctx,current_time())
        except BaseException:
            try:_abandon_unstarted(store,delivery['id'],reservation,current_time())
            except Exception:pass  # Unknown DB outcome keeps the bounded reservation held.
            raise
        try:
            result=adapter.submit(ctx,prepared,permit)
            if not isinstance(result,SubmissionResult):raise ContractError('invalid_submission_result')
        except BaseException:
            # Once consumed, every exception is uncertain, including process interruption.
            # If DB is unavailable the durable request_started marker remains for recovery.
            store.finish_attempt(permit.attempt_id,'unknown',evidence={'reason':'submission_interrupted'},now=now)
            raise ContractError('submission_uncertain') from None
        store.finish_attempt(permit.attempt_id,result.outcome,remote_id=_redact(result.remote_id,permit.nonce),url=_redact(result.url,permit.nonce),scheduled_at=result.scheduled_at,evidence=_redact(thaw(result.evidence),permit.nonce),now=current_time())
        if result.outcome in ('submitted','scheduled'):settle_quota(store,reservation,result.outcome)
        return delivery['id']
