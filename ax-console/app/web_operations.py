"""관리 실행 HTTP 경계. 서버 등록 복구 서비스와 읽기 전용 관측만 연결한다."""
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, parse_qs
from collections.abc import Mapping
from common.operations.content_store import StoreError
from common.operations.runtime_models import ExecutionPolicy
from common.shared.axlock import LockPaths, read_control_state

DELIVERY_ID = r'delivery_[0-9a-f]{32}'
BASE = '/api/v2/operations'
ROUTE = BASE + '/(' + DELIVERY_ID + r')(?:/(reconcile|resolve|retry))?'
SAFE_ID = r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}'

class OperationsBlocked(Exception):
    def __init__(self, code):self.code=code

def recognizes(path):
    return path in (BASE, '/api/v2/control') or re.fullmatch(ROUTE,path) is not None

def fields(body, names):
    if not isinstance(body,dict) or set(body)!=set(names):raise StoreError('invalid')
    return body

def identifier(value):
    return isinstance(value,str) and re.fullmatch(SAFE_ID,value) is not None

def command(body):
    if type(body.get('expected_version')) is not int or body['expected_version']<0 or not identifier(body.get('request_key')):raise StoreError('invalid')

def safe_fields(row, names):
    result={}
    for name in names:
        if name not in row:continue
        value=row[name]
        if value is None or type(value) in (bool,int,float):result[name]=value
        elif isinstance(value,str) and identifier(value):result[name]=value
    return result

def display_text(value):
    if not isinstance(value,str):return None
    return ''.join(c for c in value[:300] if ord(c)>=32 and ord(c)!=127)

def timestamp(value):
    if not isinstance(value,str):return None
    try:
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        return parsed.isoformat() if parsed.tzinfo is not None else None
    except ValueError:return None

def public_url(value):
    if not isinstance(value,str) or len(value)>2048 or re.search(r'[\\\x00-\x20\x7f]',value):return None
    try:
        url=urlsplit(value)
        hosts={'youtube.com','www.youtube.com','youtu.be','tiktok.com','www.tiktok.com','instagram.com','www.instagram.com','threads.net','www.threads.net','x.com','www.x.com','facebook.com','www.facebook.com','m.facebook.com','blog.naver.com','m.blog.naver.com'}
        host=url.hostname or ''
        if url.scheme!='https' or url.username or url.password or url.port is not None or url.fragment:return None
        if host not in hosts and not (host.endswith('.tistory.com') or host.endswith('.blogspot.com')):return None
        query=parse_qs(url.query,strict_parsing=True,keep_blank_values=True)
        if query:
            if host not in ('youtube.com','www.youtube.com') or set(query)!={'v'} or len(query['v'])!=1 or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',query['v'][0]):return None
        return value
    except ValueError:return None

def safe_evidence(raw):
    if not isinstance(raw,Mapping):return {}
    result={}
    if identifier(raw.get('remote_id')):result['remote_id']=raw['remote_id']
    for name in ('identity_confirmed','confirmed_not_posted','old_process_terminated','profile_lock_released','local_only'):
        if type(raw.get(name)) is bool:result[name]=raw[name]
    if type(raw.get('candidate_count')) is int and raw['candidate_count']>=0:result['candidate_count']=raw['candidate_count']
    if raw.get('outcome') in ('matched','ambiguous','not_found','unsupported','error','verified','pending','failed','submitted','scheduled','unknown'):result['outcome']=raw['outcome']
    if raw.get('visibility') in ('public','private','unlisted','scheduled'):result['visibility']=raw['visibility']
    if raw.get('reason') in ('adapter_error','invalid_adapter_result','insufficient_evidence','identity_mismatch','not_public','scheduled_future'):result['reason']=raw['reason']
    for name in ('created_at','checked_at','scheduled_at','started_at','completed_at'):
        value=timestamp(raw.get(name))
        if value:result[name]=value
    value=public_url(raw.get('url'))
    if value:result['url']=value
    for source,target,allowed in (('process','process_status',('dead','alive','unknown')),('lock','lock_status',('free','held','unknown'))):
        nested=raw.get(source)
        if isinstance(nested,Mapping) and nested.get('status') in allowed:result[target]=nested['status']
    return result

def capabilities(row,policy,adapters,process_probe,lock_probe):
    recovery=row.get('state') in ('unknown','needs_review','failed','retry_wait') or row.get('state')=='cancelled' and row.get('remote_uncertain')
    adapter=adapters.get(row.get('context',{}).get('connection_id'))
    kinds=[];actions=[];blockers=[]
    if recovery:
        if row['state']!='cancelled':kinds.append('cancel_local')
        if adapter is not None:kinds.append('link_existing');actions.append('reconcile')
        else:blockers.append('adapter_unavailable')
        if callable(process_probe) and callable(lock_probe):kinds.append('confirmed_not_posted')
        else:blockers.append('probe_unavailable')
        if kinds:actions.append('resolve')
    if not policy.enabled:blockers.append('execution_disabled')
    elif row.get('state')=='retry_wait' and not row.get('remote_uncertain') and callable(process_probe) and callable(lock_probe):actions.append('retry')
    return actions,kinds,blockers

def item(row, *, detail=False, store=None, enabled=False, policy=None, adapters=None, process_probe=None, lock_probe=None, connections=()):
    policy=policy if policy is not None else ExecutionPolicy(enabled=enabled)
    result=safe_fields(row,('id','run_id','state','execution_state','plan_status','version','remote_id','remote_uncertain','required'))
    ctx=row.get('context',{})
    result.update(safe_fields(ctx,('owner_account_id','destination_account_id','connection_id','platform','content_id','content_revision','target_id')))
    actions,kinds,blockers=capabilities(row,policy,adapters or {},process_probe,lock_probe)
    result.update(execution_enabled=policy.enabled,available_actions=actions,available_resolution_kinds=kinds,blockers=blockers)
    snapshot=None
    content_store=getattr(store,'content_store',None)
    if content_store is not None and ctx.get('content_id') and ctx.get('content_revision'):
        snapshot=content_store.get(ctx.get('content_id'),ctx.get('content_revision'))
    if snapshot:
        title=display_text(snapshot.get('title'))
        if title:result['title']=title
    connection=next((c for c in connections if c.get('id')==ctx.get('connection_id')),None)
    if connection:
        label=display_text(connection.get('target_label'))
        if label:result['target_label']=label
    for name in ('created_at','checked_at','scheduled_at'):
        value=timestamp(row.get(name))
        if value:result[name]=value
    url=public_url(row.get('url'))
    if url:result['url']=url
    if detail:
        result['attempts']=[]
        for attempt in store.attempts(row['id']):
            clean=safe_fields(attempt,('id','ordinal','outcome','request_started','resolved'))
            for name in ('created_at','started_at','completed_at'):
                value=timestamp(attempt.get(name))
                if value:clean[name]=value
            remote=attempt.get('result') or {}
            if isinstance(remote,Mapping):clean.update(safe_evidence(remote))
            result['attempts'].append(clean)
        result['evidence']=[]
        for event in store.events(row['id']):
            clean=safe_fields(event,('id','kind','attempt_id'))
            value=timestamp(event.get('created_at'))
            if value:clean['created_at']=value
            raw=event.get('evidence',{})
            clean.update(safe_evidence(raw))
            # 판정에서 검증한 근거만 표시하며 자유 메모는 노출하지 않는다.
            if isinstance(raw,Mapping):clean.update(safe_evidence(raw.get('evidence',{})))
            result['evidence'].append(clean)
    return result

def control_item(row):
    action=row.get('action','resume')
    return dict(scope=row['scope'],id=row.get('target_id',row.get('id')),state='paused' if action=='pause' else 'running',version=row.get('version',0),available_actions=['resume' if action=='pause' else 'pause'])

def list_response(store, source_root, account, policy, *, connections=(), adapters=None, process_probe=None, lock_probe=None):
    rows=store.list_operations(account) if store is not None else []
    # 서비스가 잘못 넓게 반환해도 HTTP 조회 범위를 보존한다.
    rows=[r for r in rows if account=='all' or account in (r.get('context',{}).get('owner_account_id'),r.get('context',{}).get('destination_account_id'))]
    summary=dict(active=0,completed=0,partial=0,waiting=0)
    runs=store.list_runs() if store is not None and hasattr(store,'list_runs') else []
    selected={r['run_id'] for r in rows if r.get('run_id')}
    states=[r['state'] for r in runs if account=='all' or r['id'] in selected]
    if not runs:
        states=[r['state'] for r in rows]
    for state in states:
        key='completed' if state in ('verified','completed') else 'partial' if state=='partial' else 'waiting' if state in ('waiting','unknown','needs_review','retry_wait','failed') else 'active'
        summary[key]+=1
    observed=read_control_state(LockPaths.from_root(source_root))
    controls=store.control_state() if store is not None else []
    managed=[control_item(r) for r in controls if identifier(r.get('target_id')) and (account=='all' or r['scope']=='managed' or r['scope']=='account' and r['target_id']==account or r['scope']=='connection' and r['target_id'].startswith(account+'.'))]
    if not any(r['scope']=='managed' and r['id']=='all' for r in managed):managed.insert(0,control_item(dict(scope='managed',target_id='all')))
    defaults=[('account',a) for a in ('personal','dept') if account in ('all',a)]
    defaults += [('connection',c['id']) for c in connections if account in ('all',c.get('account_id'))]
    defaults += [('connection',r.get('context',{}).get('connection_id')) for r in rows]
    for scope,id in defaults:
        if identifier(id) and not any(r['scope']==scope and r['id']==id for r in managed):managed.append(control_item(dict(scope=scope,target_id=id)))
    for row in managed:
        connection=next((c for c in connections if row['scope']=='connection' and c.get('id')==row['id']),None)
        if connection and display_text(connection.get('target_label')):row['target_label']=display_text(connection['target_label'])
    if store is None:
        for row in managed:row['available_actions']=[]
    return {
        'items':[item(r,store=store,policy=policy,adapters=adapters,process_probe=process_probe,lock_probe=lock_probe,connections=connections) for r in rows], 'summary':summary,
        'control':{'global':{'state':observed['state'],'version':observed['version'],'read_only':True},'managed':managed},
        'execution_enabled':policy.enabled,'blockers':['adapter_unavailable'] if policy.enabled else ['execution_disabled','adapter_unavailable']}

def handle(store, method, path, query, read_body, *, source_root, policy=None, adapters=None, process_probe=None, lock_probe=None, registry=None, now=None):
    if path==BASE and method=='GET':
        if (set(query)-{'account'} or any(not isinstance(v,list) or len(v)!=1 for v in query.values()) or query.get('account',['all'])[0] not in ('all','personal','dept')):raise StoreError('invalid')
    elif query:raise StoreError('invalid')
    policy=policy if policy is not None else ExecutionPolicy()
    adapters=adapters or {}
    now=now if now is not None else datetime.now(timezone.utc)
    registry=registry() if callable(registry) else registry
    connections=[c.to_dict(public=True) for c in registry.connections.values()] if registry is not None else []
    if path==BASE:
        if method!='GET':return None
        return list_response(store,source_root,query.get('account',['all'])[0],policy,connections=connections,adapters=adapters,process_probe=process_probe,lock_probe=lock_probe)
    if path=='/api/v2/control':
        if method!='POST':return None
        b=fields(read_body(),('scope','id','action','expected_version','request_key','reason'));command(b)
        if (b['scope'] not in ('managed','account','connection') or b['action'] not in ('pause','resume') or not identifier(b['id']) or
            b['scope']=='managed' and b['id']!='all' or b['scope']=='account' and b['id'] not in ('personal','dept') or
            b['scope']=='connection' and not re.fullmatch(r'(personal|dept)\.[a-z0-9_.-]{1,100}',b['id']) or
            not isinstance(b['reason'],str) or not b['reason'].strip() or len(b['reason'])>2000):raise StoreError('invalid')
        if registry is not None and b['scope']=='connection' and b['id'] not in registry.connections:raise StoreError('invalid')
        if store is None:raise OperationsBlocked('execution_disabled')
        row=store.control(b['scope'],b['id'],b['action'],b['expected_version'],b['request_key'],b['reason'],actor='console_user')
        return control_item(row)
    match=re.fullmatch(ROUTE,path)
    if not match:raise StoreError('not_found')
    id,action=match.groups()
    if action is None:
        if method!='GET':return None
        row=store.get_delivery(id) if store is not None else None
        if row is None:raise StoreError('not_found')
        return item(row,detail=True,store=store,policy=policy,adapters=adapters,process_probe=process_probe,lock_probe=lock_probe,connections=connections)
    if method!='POST':return None
    names=['expected_version','request_key']+(['kind','evidence','note'] if action=='resolve' else [])
    b=fields(read_body(),names);command(b)
    if action=='resolve' and (b['kind'] not in ('link_existing','confirmed_not_posted','cancel_local') or not isinstance(b['evidence'],dict) or not isinstance(b['note'],str) or len(b['note'])>2000):raise StoreError('invalid')
    if action=='retry' and not policy.enabled:raise OperationsBlocked('execution_disabled')
    if store is None:raise OperationsBlocked('execution_disabled')
    row=store.get_delivery(id)
    if row is None:raise StoreError('not_found')
    adapter=adapters.get(row['context']['connection_id'])
    from common.operations import recovery
    try:
        if action=='reconcile':
            if adapter is None:raise OperationsBlocked('adapter_unavailable')
            result=recovery.reconcile_delivery(store,id,adapter,now,expected_version=b['expected_version'],request_key=b['request_key'],actor='console_user')
        elif action=='resolve':
            if b['kind']=='link_existing' and adapter is None:raise OperationsBlocked('adapter_unavailable')
            if b['kind']=='confirmed_not_posted' and (not callable(process_probe) or not callable(lock_probe)):raise OperationsBlocked('probe_unavailable')
            result=recovery.resolve_unknown(store,id,b,'console_user',process_probe=process_probe,lock_probe=lock_probe,adapter=adapter,now=now)
        else:
            result=recovery.retry_delivery(store,id,b,'console_user',policy=policy,registry=registry,process_probe=process_probe,lock_probe=lock_probe,now=now)
    except StoreError as exc:
        if exc.code in ('adapter_unavailable','insufficient_evidence','execution_disabled','execution_blocked','invalid_context','lease_active','managed_paused','worker_active','invalid_resume','legacy_owner','job_disabled','connection_disabled','cutover_required','connection_not_allowed','provider_policy_violation','unknown_job','unknown_connection','unknown_policy','owner_mismatch','context_changed','unknown_occurrence'):raise OperationsBlocked(exc.code) from None
        raise
    # 요청키 재전송에도 서비스가 저장한 같은 결과를 정제하여 반환한다.
    # 후속 evidence 변경에 따라 응답이 달라지지 않도록 변이 응답은 상태 필드만 반환한다.
    return safe_fields(result,('id','run_id','state','execution_state','plan_status','version','remote_id','remote_uncertain','required'))
