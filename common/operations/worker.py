"""단일 managed 제출 경계. 실제 기본 adapter 등록은 비어 있다."""
from datetime import datetime, timezone, timedelta
import time
import os
import socket
from .models import ContractError, thaw
from .runtime_models import PublicationContext, SubmissionResult, utc
from .publication_gate import authorize_submission, consume_permit, _inputs, _snapshot, fresh_lease

from .quota import reserve_quota, settle_quota


_PROCESS_START=datetime.now(timezone.utc).isoformat()

def _identity():
    return {'host_id':socket.gethostname(),'pid':os.getpid(),'started_at':_PROCESS_START}


def _redact(value,nonce):
    if isinstance(value,str):return value.replace(nonce,'<redacted>')
    if isinstance(value,dict):return {_redact(k,nonce):_redact(v,nonce) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [_redact(v,nonce) for v in value]
    return value


def run_once(store,registry,adapters,policy,locks,now):
    """adapters/policy/locks는 서버 시작 시 주입하며 HTTP 입력을 받지 않는다."""
    if not policy.enabled:return None
    started=time.monotonic()
    def current_time():return utc(now)+timedelta(seconds=time.monotonic()-started)
    # mode/phase 필터를 claim 전에 적용해 dry/shadow에서 adapter 호출 0.
    identity=_identity()
    eligible={r['id'] for r in store.list_runs() if (r.get('occurrence') or {}).get('mode')=='live' and (r.get('occurrence') or {}).get('phase')=='submit' and (r['state']=='queued' or (r['state']=='running' and r.get('process_identity')==identity))}
    deliveries=[d for d in store.list_operations() if d['run_id'] in eligible and d['state'] in ('queued','retry_wait') and d['context']['connection_id'] in adapters]
    if not deliveries:return None
    delivery=deliveries[0];run=store.get_run(delivery['run_id'])
    store.registry=registry;store.execution_policy=policy;store.locks=locks
    ctx=PublicationContext(**delivery['context']);adapter=adapters[ctx.connection_id]
    connection=registry.connections[ctx.connection_id]
    # Profile refs are server-owned symbols; never accept a path or executor from a request.
    resource=connection.profile_ref
    profile=registry.profiles.get(resource) if resource else None
    if not profile or profile.get('account_id')!=connection.account_id or profile.get('lock_resource') not in ('profile:naver','profile:insta','profile:tiktok','profile:youtube-dept','profile:insta-manual','profile:safeworking','profile:tistory','profile:youtube-personal'):
        raise ContractError('profile_lock_required')
    with locks.hold([profile['lock_resource']],job='managed-publication',wait=2400):
        # No SQLite transaction/control gate/lease was held during profile wait.
        run=store.get_run(ctx.run_id)
        if run['state']=='queued':
            lease=store.claim_run(run['id'],'managed-worker',identity,current_time(),expected_version=run['version'])
        elif run['state']=='running' and run.get('process_identity')==identity:
            lease=fresh_lease(store,ctx.run_id,current_time())
        else:return None
        _inputs(store,ctx,current_time())
        lease=fresh_lease(store,ctx.run_id,current_time())
        snapshot=_snapshot(store,ctx.content_id,ctx.content_revision,ctx.manifest_hash)
        prepared=adapter.prepare(ctx,snapshot)  # contractual pure local work
        reservation=reserve_quota(store,{'delivery_id':delivery['id'],'context':ctx},{},current_time())
        approval=store.get_publication_approval(delivery['id'])
        permit=authorize_submission(store,ctx,snapshot,approval,lease,reservation,current_time())
        consume_permit(store,permit,ctx,current_time())
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
