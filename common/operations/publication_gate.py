"""별도 발행 승인과 일회성 permit. 외부 adapter는 이 모듈에서 호출하지 않는다."""
import hashlib
import json
import time
from collections.abc import Mapping
from datetime import timedelta
from .models import ContractError, thaw
from .content_store import StoreError
from .runtime_models import PublicationContext, ExecutionPolicy, RunLease, utc
from common.shared.axlock import read_control_state


def report_hash(report):
    return hashlib.sha256(json.dumps({k:v for k,v in report.items() if k!='report_hash'},sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def validate_reviews(evidence, policy, ctx, persisted, now):
    """서버 보존 provenance와 권한 등록부를 함께 확인한다."""
    if not isinstance(evidence,Mapping):raise ContractError('independent_review_required')
    producer=evidence.get('producer');reports=evidence.get('reports')
    if (not isinstance(producer,Mapping) or set(producer)!={'principal_id','execution_id'} or
        not all(isinstance(v,str) and v for v in producer.values()) or
        not isinstance(reports,(list,tuple)) or not reports):raise ContractError('independent_review_required')
    if not any(e['kind']=='production_provenance' and e['evidence']==producer for e in persisted):raise ContractError('review_provenance_required')
    required={'source'}
    if policy.get('require_calc_review') is True:required.add('calc')
    seen=set();principals={producer['principal_id']};executions={producer['execution_id']};hashes=[]
    fields={'role','reviewer_id','execution_id','content_id','content_revision','manifest_hash','verdict','checked_at','report_hash'}
    for report in reports:
        if not isinstance(report,Mapping) or set(report)!=fields:raise ContractError('invalid_review_report')
        role=report['role'];principal=report['reviewer_id'];execution=report['execution_id']
        if (role not in ('source','calc') or role in seen or not isinstance(principal,str) or not principal or
            not isinstance(execution,str) or not execution or principal in principals or execution in executions or
            role not in policy.get('review_authorities',{}).get(principal,()) or report['verdict']!='pass' or
            report['content_id']!=ctx.content_id or report['content_revision']!=ctx.content_revision or
            report['manifest_hash']!=ctx.manifest_hash or utc(report['checked_at'])>utc(now) or
            report['report_hash']!=report_hash(report)):
            raise ContractError('independent_review_required')
        if not any(e['kind']=='independent_review' and e['evidence']==report for e in persisted):raise ContractError('review_provenance_required')
        seen.add(role);principals.add(principal);executions.add(execution);hashes.append(report['report_hash'])
    if not required<=seen:raise ContractError('independent_review_required')
    return tuple(sorted(hashes))


def check_policy(policy, connection, job_policy):
    if not isinstance(policy,ExecutionPolicy) or not policy.enabled:raise ContractError('execution_disabled')
    if not connection.enabled:raise ContractError('connection_disabled')
    if connection.id not in policy.allowed_connection_ids:raise ContractError('connection_not_allowed')
    if not policy.cutover_revision:raise ContractError('cutover_required')
    if policy.provider_policy.get('subscription_only') is not True or job_policy.get('subscription_only') is not True:
        raise ContractError('provider_policy_violation')


def _snapshot(store, content_id, revision, manifest_hash):
    snapshot=store.content_store.get(content_id,revision)
    latest=store.content_store.get(content_id)
    if not snapshot or not latest or latest['revision']!=revision or snapshot['manifest_hash']!=manifest_hash:
        raise ContractError('content_changed')
    asset_bytes={}
    for asset in snapshot.get('assets',()):
        meta,raw=store.content_store.read_asset(content_id,revision,asset['id'])
        if len(raw)!=asset['size'] or hashlib.sha256(raw).hexdigest()!=asset['sha256']:raise ContractError('asset_changed')
        asset_bytes[asset['id']]=raw
    return dict(snapshot,asset_bytes=asset_bytes)


def build_publication_context(store,delivery_id,observed_target,review_evidence,policy,now,*,run_id=None):
    if not isinstance(policy,ExecutionPolicy) or not policy.enabled:raise ContractError('execution_disabled')
    plan=store.get_plan_delivery(delivery_id)
    if not plan or plan.get('status')=='cancelled':raise ContractError('plan_unavailable')
    existing=store.get_delivery(delivery_id)
    run_id=run_id or (existing['run_id'] if existing else None)
    run=store.get_run(run_id) if run_id else None
    occurrence=run.get('occurrence') if run else None
    if not occurrence or occurrence.get('mode')!='live' or occurrence.get('phase')!='submit' or occurrence.get('request_kind') not in ('new_publication','resume'):
        raise ContractError('publication_run_required')
    registry=store.registry;job=registry.jobs.get(occurrence.get('job_id'))
    if not job or job.get('execution_owner')!='managed' or job.get('enabled') is not True:raise ContractError('job_disabled')
    job_ids=job.get('connection_ids') or (job.get('connection_id'),)
    connection=registry.connections.get(plan.get('connection_id'))
    if not connection or connection.id not in job_ids:raise ContractError('connection_mismatch')
    job_policy=registry.policies.get(job.get('policy_revision'))
    if not job_policy:raise ContractError('unknown_policy')
    check_policy(policy,connection,job_policy)
    owner=plan['owner_account_id']
    if job.get('owner_account_id')!=owner:raise ContractError('owner_mismatch')
    if connection.account_id!=owner:
        if not any(r.get('enabled') is True and r.get('owner_account_id')==owner and r.get('destination_connection_id')==connection.id and registry.connections[r['source_connection_id']].account_id==owner for r in registry.crossposts.values()):raise ContractError('crosspost_not_allowed')
    if not connection.target_id or plan.get('destination_account_id')!=connection.account_id:raise ContractError('target_unverified')
    snapshot=_snapshot(store,plan['content_id'],plan['revision'],plan['manifest_hash'])
    if snapshot['owner_account_id']!=owner:raise ContractError('owner_mismatch')
    obs=observed_target
    if (not isinstance(obs,Mapping) or obs.get('platform')!=connection.platform or obs.get('target_id')!=connection.target_id or
        obs.get('authenticated') is not True or not obs.get('verification_method') or not obs.get('login_subject') or
        (connection.expected_login_subject and obs['login_subject']!=connection.expected_login_subject)):
        raise ContractError('target_mismatch')
    checked=utc(obs.get('checked_at'));expires=utc(obs.get('expires_at'));now=utc(now)
    max_age=job_policy.get('auth_max_age_seconds',300)
    if type(max_age) not in (int,float) or max_age<=0 or not checked<=now<expires or now-checked>timedelta(seconds=max_age):raise ContractError('authentication_expired')
    values=dict(content_id=plan['content_id'],content_revision=plan['revision'],manifest_hash=plan['manifest_hash'],owner_account_id=owner,destination_account_id=connection.account_id,connection_id=connection.id,target_id=connection.target_id,publication_purpose=plan['publication_purpose'],schedule_slot=plan['schedule_slot'],options=plan.get('options',{}),schedule_condition=plan['schedule_condition'],registry_revision=registry.revision,policy_revision=job['policy_revision'],auth_checked_at=checked,auth_expires_at=expires,run_id=run_id,platform=connection.platform)
    subject=type('ReviewSubject',(),values)()
    values['review_report_hashes']=validate_reviews(review_evidence,job_policy,subject,_review_records(store,values['content_id'],values['content_revision'],values['manifest_hash']),now)
    ctx=PublicationContext(**values)
    if existing and (existing['run_id']!=run_id or PublicationContext(**existing['context']).intent_hash!=ctx.intent_hash):raise ContractError('publication_context_changed')
    return ctx


def refresh_auth_observation(store,delivery_id,observed_target,now,*,expected_version):
    """서버 전용. live 정책/프로필 잠금 아래 읽기 관측을 검증하고 CAS 결합한다."""
    delivery=store.get_delivery(delivery_id)
    if not delivery or delivery['version']!=expected_version:raise ContractError('conflict')
    old=PublicationContext(**delivery['context'])
    require_publication_approval(store,delivery_id,old)
    observations=[e['evidence'] for e in store.events(delivery_id) if e['kind']=='target_observation']
    if (not observations or not isinstance(observed_target,Mapping) or
        observed_target.get('login_subject')!=observations[-1].get('login_subject')):
        raise ContractError('target_mismatch')
    events=_review_records(store,old.content_id,old.content_revision,old.manifest_hash)
    producers=[e['evidence'] for e in events if e['kind']=='production_provenance']
    reports=[e['evidence'] for e in events if e['kind']=='independent_review' and e['evidence'].get('report_hash') in old.review_report_hashes]
    if not producers:raise ContractError('publication_evidence_required')
    ctx=build_publication_context(store,delivery_id,observed_target,{'producer':producers[-1],'reports':reports},store.execution_policy,now)
    # 토큰/임의 adapter 필드는 저장하지 않는다.
    observation={key:observed_target[key] for key in ('platform','target_id','authenticated','login_subject','verification_method','checked_at','expires_at')}
    store.refresh_auth_proof(delivery_id,expected_version,ctx,observation,now)
    return ctx


def _review_records(store,content_id,revision,manifest_hash):
    return [{'kind':r['kind'],'evidence':r['report']} for r in store.read_content_evidence(content_id,revision,manifest_hash)]


def _inputs(store,ctx,now):
    delivery=next((d for d in store.list_operations() if d['run_id']==ctx.run_id and d['context_hash']==ctx.context_hash),None)
    if not delivery:raise ContractError('publication_context_required')
    events=_review_records(store,ctx.content_id,ctx.content_revision,ctx.manifest_hash)
    producers=[e['evidence'] for e in events if e['kind']=='production_provenance']
    reports=[e['evidence'] for e in events if e['kind']=='independent_review' and e['evidence'].get('report_hash') in ctx.review_report_hashes]
    # Authentication observation is server persisted, never reconstructed from a client flag.
    observations=[e['evidence'] for e in store.events(delivery['id']) if e['kind']=='target_observation']
    if not producers or not observations:raise ContractError('publication_evidence_required')
    rebuilt=build_publication_context(store,delivery['id'],observations[-1],{'producer':producers[-1],'reports':reports},store.execution_policy,now,run_id=ctx.run_id)
    if rebuilt.context_hash!=ctx.context_hash:raise ContractError('publication_context_changed')
    return delivery


def _clear(store):
    if read_control_state(store.locks.paths)['state']!='clear':raise ContractError('control_blocked')


def fresh_lease(store,run_id,now):
    run=store.get_run(run_id)
    if not run or not run.get('worker_id') or utc(run['lease_expires_at'])<=utc(now):raise ContractError('lease_expired')
    return RunLease(run_id,run['worker_id'],run['generation'],run['lease_expires_at'])


def _clock(now):
    started=time.monotonic();base=utc(now)
    return lambda:base+timedelta(seconds=max(0,time.monotonic()-started))


def _time_valid(store,ctx,lease,now,permit=None):
    from .dispatch import run_is_due
    if not run_is_due(store.get_run(ctx.run_id),now):raise ContractError('run_not_due')
    max_age=store.registry.policies[ctx.policy_revision].get('auth_max_age_seconds',300)
    if not ctx.auth_checked_at<=now<ctx.auth_expires_at or now-ctx.auth_checked_at>timedelta(seconds=max_age):
        raise ContractError('authentication_expired')
    if lease.expires_at<=now:raise ContractError('lease_expired')
    if permit is not None and permit.expires_at<=now:raise ContractError('permit_expired')


def require_publication_approval(store,delivery_id,ctx,approval=None):
    current=store.get_publication_approval(delivery_id)
    if (not isinstance(current,Mapping) or current.get('scope','publication')!='publication' or
        current.get('decision')!='approved' or current.get('context_hash')!=ctx.context_hash or
        set(current.get('report_hashes',()))!=set(ctx.review_report_hashes) or
        (approval is not None and current!=approval)):
        raise ContractError('publication_approval_required')
    return current


def authorize_submission(store,ctx,snapshot,approval,lease,reservation_id,now):
    current_time=_clock(now)
    if not isinstance(ctx,PublicationContext):raise ContractError('publication_context_required')
    if not isinstance(approval,Mapping) or approval.get('scope','publication')!='publication' or approval.get('decision')!='approved':raise ContractError('publication_approval_required')
    def checked_clock():
        checked=current_time();_time_valid(store,ctx,lease,checked);return checked
    with store.locks.hold(['control:publish-gate'],job='publication-authorize',wait=10):
        _clear(store);delivery=_inputs(store,ctx,current_time())
        if snapshot.get('manifest_hash')!=ctx.manifest_hash:raise ContractError('content_changed')
        require_publication_approval(store,delivery['id'],ctx,approval)
        if not reservation_id:raise ContractError('quota_reservation_required')
        checked=current_time();_time_valid(store,ctx,lease,checked)
        attempt=store.create_attempt(delivery['id'],delivery['version'],lease,ctx.context_hash,approval['approval_hash'],reservation_id=reservation_id,now=checked,clock=checked_clock)
        checked=current_time();_time_valid(store,ctx,lease,checked)
        return store.issue_permit(attempt['id'],lease,ctx.context_hash,approval['approval_hash'],checked,clock=checked_clock)


def consume_permit(store,permit,ctx,now):
    current_time=_clock(now)
    if not isinstance(ctx,PublicationContext) or permit.context_hash!=ctx.context_hash:raise ContractError('publication_context_required')
    with store.locks.hold(['control:publish-gate'],job='publication-consume',wait=10):
        _clear(store);_inputs(store,ctx,current_time())
        # Refresh after gate wait and all validation, immediately before atomic consume.
        lease=fresh_lease(store,ctx.run_id,current_time())
        if permit.generation!=lease.generation:raise ContractError('lease_changed')
        checked=current_time();_time_valid(store,ctx,lease,checked,permit)
        def checked_clock():
            checked=current_time();_time_valid(store,ctx,lease,checked,permit);return checked
        store.consume_permit(permit,lease,checked,clock=checked_clock)
