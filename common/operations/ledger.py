"""실행하지 않는 불변 콘텐츠 배포 계획과 계획 승인 원장."""
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
import hashlib
import json
import re
import sqlite3

from .content_store import ContentStore, StoreError, ConflictError, _json, _now, _string
from .database import connect_database, initialize_database
from .models import Registry, ExecutionRequest, ContractError, thaw
from .registry import load_registry
from .context import resolve_context
from .schedule_time import normalize_schedule
from .approvals import approval_fingerprint, is_approval_current
from .crossposts import preview_crossposts


def digest(value): return hashlib.sha256(_json(value).encode()).hexdigest()
def invalid(): raise StoreError('invalid')
def version(value):
    if type(value) is not int or value < 1: invalid()


class Ledger:
    def __init__(self, root: Path, registry=None, content_store=None):
        self.root=Path(root).absolute()
        self.registry_source=registry or Path(__file__).resolve().parents[2]/'ax-console/config/operations.json'
        self.content_store=content_store or ContentStore(root)
        self._initialized=False

    def registry(self):
        source=self.registry_source() if callable(self.registry_source) else self.registry_source
        return source if isinstance(source,Registry) else load_registry(Path(source))

    def initialize(self):
        try: initialize_database(self.root)
        except (OSError,sqlite3.Error) as exc: raise StoreError('storage_error') from exc
        self._initialized=True

    @contextmanager
    def _db(self,write=False):
        conn=None
        try:
            if write and not self._initialized: raise StoreError('storage_error')
            conn=connect_database(self.root,writable=write)
            if conn.execute('PRAGMA user_version').fetchone()[0]!=2: raise StoreError('storage_error')
            if write: conn.execute('BEGIN IMMEDIATE')
            yield conn
            if write: conn.commit()
        except (OSError,sqlite3.Error) as exc: raise StoreError('storage_error') from exc
        finally:
            if conn is not None: conn.close()

    def connections(self): return [c.to_dict(public=True) for c in self.registry().connections.values()]

    def _snapshot(self,body,conn=None):
        snapshot=self.content_store.get(body['content_id'],body['revision'])
        if snapshot is None: raise StoreError('not_found')
        if snapshot['manifest_hash']!=body['manifest_hash']: raise ConflictError()
        for asset in snapshot['assets']:
            self.content_store.read_asset(snapshot['id'],snapshot['revision'],asset['id'])
        if conn is not None:
            row=conn.execute('SELECT manifest_hash FROM revisions WHERE content_id=? AND revision=?',(body['content_id'],body['revision'])).fetchone()
            if row is None or row[0]!=body['manifest_hash']: raise ConflictError()
        return snapshot

    def _condition(self,condition,scheduled,zone):
        if not isinstance(condition,dict): invalid()
        if condition.get('kind')=='fixed' and set(condition)=={'kind','at'}:
            normalized={'kind':'fixed','at':normalize_schedule(condition['at'],zone)}
            inside=scheduled==normalized['at']
        elif condition.get('kind')=='window' and set(condition)=={'kind','from','to'}:
            normalized={'kind':'window','from':normalize_schedule(condition['from'],zone),'to':normalize_schedule(condition['to'],zone)}
            if normalized['from']>=normalized['to']: invalid()
            inside=normalized['from']<=scheduled<normalized['to']
        else: invalid()
        return normalized,inside

    def _context(self,record,snapshot,registry):
        request=ExecutionRequest(run_id=record['run_id'],job_id='managed.'+snapshot['owner_account_id']+'.plan',owner_account_id=snapshot['owner_account_id'],content_id=snapshot['id'],content_revision=snapshot['revision'],connection_id=record['connection_id'],schedule_slot=record['schedule_slot'],publication_purpose=record['publication_purpose'],crosspost_rule_id=record.get('crosspost_rule_id'))
        ctx=resolve_context(request,registry,snapshot['owner_account_id'],allow_unverified=True).to_dict()
        ctx.update(options=record['options'],schedule_condition=record['schedule_condition'],scope='plan',dry_run=True,execution_enabled=False,policy=thaw(registry.policies[ctx['policy_revision']]),connection_capabilities=thaw(registry.connections[record['connection_id']].capabilities),crosspost_rule=thaw(registry.crossposts.get(record.get('crosspost_rule_id'))))
        return ctx

    def _subject(self,snapshot,context):
        return approval_fingerprint(snapshot,context) if context['target_id'] else None

    def _blockers(self,context,registry):
        result=[]
        if not context['target_id']: result.append({'code':'target_unverified','reason':'실제 대상이 확인되지 않았습니다.'})
        rule=registry.crossposts.get(context.get('crosspost_rule_id'))
        if rule is not None:
            for code,blocked in [('legacy_owner',rule.get('execution_owner')=='legacy' or rule.get('delivery_owner')=='legacy'),('disabled',rule.get('enabled') is False),('unknown',rule.get('enabled') is None)]:
                if blocked: result.append({'code':code,'reason':'기존 교차 경로는 관측용이며 실행 주인을 변경하지 않습니다.'})
        return result

    def _public(self,record):
        keys=('id','content_id','revision','manifest_hash','owner_account_id','destination_account_id','connection_id','platform','target_label','target_status','publication_purpose','schedule_slot','scheduled_at','timezone','schedule_condition','status','version','subject_hash','approval','blockers','created_at','updated_at')
        approval=record.get('approval')
        return {**{k:record.get(k) for k in keys},'approval':None if approval is None else {k:approval[k] for k in ('id','scope','decision','subject_hash','content_revision','source','recorded_at')},'source':'managed','schedule_kind':'local_plan','remote_state':'unavailable','execution_enabled':False}

    def _view(self,record):
        # 읽기에서도 현재 정책/검토를 반영하되 저장된 이력과 버전은 바꾸지 않는다.
        r=dict(record)
        snapshot=self._snapshot(r)
        registry=self.registry()
        try:
            context=self._context(r,snapshot,registry)
            r.update(subject_hash=self._subject(snapshot,context),blockers=self._blockers(context,registry))
            current=is_approval_current(r['approval'],snapshot,context) and not r['blockers']
        except ContractError:
            r.update(subject_hash=None,blockers=[{'code':'context_changed','reason':'현재 등록부에서 계획 대상을 다시 확인해야 합니다.'}])
            current=False
        if r['status']=='ready' and not current: r['status']='pending'
        return self._public(r)

    def _prepare(self,body):
        allowed={'content_id','revision','manifest_hash','connection_id','publication_purpose','schedule_slot','scheduled_at','timezone','schedule_condition','options','crosspost_rule_id'}
        if not isinstance(body,dict) or set(body)-allowed or not {'content_id','revision','manifest_hash','connection_id','publication_purpose','schedule_slot','scheduled_at'}<=set(body): invalid()
        if not all(isinstance(body[k],str) and body[k] for k in ('content_id','connection_id','publication_purpose','schedule_slot')): invalid()
        for key in ('content_id','connection_id','publication_purpose','schedule_slot'): _string(body[key],300)
        if body.get('crosspost_rule_id') is not None and not isinstance(body['crosspost_rule_id'],str): invalid()
        version(body['revision'])
        if not isinstance(body['manifest_hash'],str) or not re.fullmatch('[0-9a-f]{64}',body['manifest_hash']): invalid()
        options=body.get('options',{})
        if not isinstance(options,dict) or set(options)-{'visibility','title_override','description_override'}: invalid()
        if 'visibility' in options and options['visibility'] not in ('public','unlisted','private'): invalid()
        for key,limit in [('title_override',300),('description_override',200000)]:
            if key in options: _string(options[key],limit)
        zone=body.get('timezone','Asia/Seoul'); at=normalize_schedule(body['scheduled_at'],zone)
        condition,inside=self._condition(body.get('schedule_condition',{'kind':'fixed','at':body['scheduled_at']}),at,zone)
        if not inside: invalid()
        snapshot=self._snapshot(body); registry=self.registry()
        record={**body,'options':options,'scheduled_at':at,'timezone':zone,'schedule_condition':condition,'run_id':'run_'+digest([snapshot['owner_account_id'],at,'prepare'])[:32]}
        context=self._context(record,snapshot,registry)
        connection=registry.connections[body['connection_id']]
        # Capabilities are explicit allowlisted option names (or their conventional aliases).
        caps=set(connection.capabilities)
        for key in options:
            if key=='visibility':
                if 'visibility:'+options[key] not in caps: invalid()
            elif key not in caps: invalid()
        record.update(context=context,owner_account_id=snapshot['owner_account_id'],destination_account_id=context['destination_account_id'],platform=context['platform'],target_label=connection.target_label,target_status=context['target_status'],subject_hash=self._subject(snapshot,context),blockers=self._blockers(context,registry),status='pending',version=1,approval=None)
        return record

    def preview_delivery(self,body):
        record=self._prepare(body)
        snapshot=self._snapshot(record)
        event=dict(content_id=record['content_id'],revision=record['revision'],owner_account_id=record['owner_account_id'],schedule_slot=record['schedule_slot'],source_connection_id=record['connection_id'],source_public_at=record['scheduled_at'],visibility=record['options'].get('visibility'),title=snapshot.get('title'),description=snapshot.get('original'))
        return dict(self._public(dict(record,id=None,created_at=None,updated_at=None)),crossposts=preview_crossposts(event,self.registry()))

    def create_or_get_run(self,request):
        if not isinstance(request,dict) or set(request)!={'job_id','scheduled_at_utc','phase','source','request_kind'} or request['source']!='console' or request['request_kind']!='manual_plan' or request['phase'] not in ('prepare','verify'): invalid()
        if request['job_id'] not in self.registry().jobs: invalid()
        normalized=dict(request,scheduled_at_utc=normalize_schedule(request['scheduled_at_utc'],'UTC'),mode='dry')
        with self._db(True) as conn: return self._run(conn,normalized)

    def _run(self,conn,request):
        key=(request['job_id'],request['scheduled_at_utc'],request['phase']); hashed=digest(request)
        row=conn.execute('SELECT * FROM runs WHERE job_id=? AND scheduled_at_utc=? AND phase=?',key).fetchone()
        if row:
            if row['request_hash']!=hashed: raise ConflictError()
            return json.loads(row['payload'])
        result=dict(request,id='run_'+digest(key)[:32])
        conn.execute('INSERT INTO runs VALUES(?,?,?,?,?,?)',(result['id'],*key,hashed,_json(result)))
        return result

    def _event(self,conn,r,kind,summary):
        conn.execute('INSERT INTO delivery_events(delivery_id,version,kind,summary,created_at) VALUES(?,?,?,?,?)',(r['id'],r['version'],kind,summary,_now()))

    def create_or_get_delivery(self,body):
        record=self._prepare(body); hashed=digest({k:v for k,v in record.items() if k not in ('status','approval','version','blockers')})
        with self._db(True) as conn:
            self._snapshot(record,conn)
            row=conn.execute('SELECT * FROM deliveries WHERE content_id=? AND revision=? AND connection_id=? AND publication_purpose=? AND schedule_slot=?',tuple(record[k] for k in ('content_id','revision','connection_id','publication_purpose','schedule_slot'))).fetchone()
            if row:
                if row['request_hash']!=hashed: raise ConflictError()
                return self._public(json.loads(row['payload']))
            run=self._run(conn,dict(job_id=record['context']['job_id'],scheduled_at_utc=record['scheduled_at'],phase='prepare',source='console',request_kind='manual_plan',mode='dry'))
            record['run_id']=run['id']; record['context']['run_id']=run['id']; record['subject_hash']=self._subject(self._snapshot(record,conn),record['context'])
            record.update(id='delivery_'+uuid4().hex,created_at=_now(),updated_at=_now())
            conn.execute('INSERT INTO deliveries VALUES(?,?,?,?,?,?,?,?)',tuple(record[k] for k in ('id','content_id','revision','connection_id','publication_purpose','schedule_slot'))+(hashed,_json(record)))
            self._event(conn,record,'created','로컬 배포 계획 저장 · 실행 안 함')
            return self._public(record)

    def _get(self,conn,id,expected=None):
        row=conn.execute('SELECT payload FROM deliveries WHERE id=?',(id,)).fetchone()
        if row is None: raise StoreError('not_found')
        record=json.loads(row[0])
        if expected is not None:
            version(expected)
            if record['version']!=expected: raise ConflictError()
        return record

    def get_delivery(self,id):
        with self._db() as conn:
            try: return self._view(self._get(conn,id))
            except StoreError as exc:
                if exc.code=='not_found': return None
                raise

    def list_deliveries(self,account='all',content_id=None):
        if account not in ('all','dept','personal'): invalid()
        with self._db() as conn:
            records=[json.loads(row[0]) for row in conn.execute('SELECT payload FROM deliveries ORDER BY rowid DESC')]
        return [self._view(r) for r in records if (account=='all' or account in (r['owner_account_id'],r['destination_account_id'])) and (content_id is None or r['content_id']==content_id)]

    def events(self,id):
        with self._db() as conn:
            self._get(conn,id)
            return [dict(r) for r in conn.execute('SELECT id,version,kind,summary,created_at FROM delivery_events WHERE delivery_id=? ORDER BY id',(id,))]

    def _save(self,conn,r,kind):
        r['version']+=1; r['updated_at']=_now()
        conn.execute('UPDATE deliveries SET payload=? WHERE id=?',(_json(r),r['id']))
        self._event(conn,r,kind,'로컬 계획 '+kind+' · 실행 안 함')
        return self._public(r)

    def record_approval(self,delivery_id,expected_version,subject_hash,decision,notes):
        if decision not in ('approved','rejected','revoked') or not isinstance(notes,str) or len(notes)>10000: invalid()
        _string(notes,10000)
        with self._db(True) as conn:
            r=self._get(conn,delivery_id,expected_version)
            if r['status']=='cancelled': raise ConflictError()
            snapshot=self._snapshot(r,conn); registry=self.registry(); context=self._context(r,snapshot,registry)
            actual=self._subject(snapshot,context)
            if actual is None or actual!=subject_hash: raise ConflictError()
            blockers=self._blockers(context,registry)
            if blockers and decision=='approved': raise ConflictError()
            if self._context(r,snapshot,self.registry())!=context: raise ConflictError()
            a=dict(id='approval_'+uuid4().hex,scope='plan',decision=decision,subject_hash=actual,content_revision=r['revision'],source='manual',actor='console_user',notes=notes,recorded_at=_now(),registry_revision=context['registry_revision'],policy_revision=context['policy_revision'])
            conn.execute('INSERT INTO approvals VALUES(?,?,?)',(a['id'],delivery_id,_json(a)))
            r.update(context=context,approval=a,status='ready' if decision=='approved' else 'pending',subject_hash=actual,blockers=blockers)
            return self._save(conn,r,'approval_'+decision)

    def _schedule(self,r,proposed_time,timezone):
        if r['status']=='cancelled': raise ConflictError()
        snapshot=self._snapshot(r); registry=self.registry(); current=self._context(r,snapshot,registry)
        at=normalize_schedule(proposed_time,timezone)
        condition,inside=self._condition(r['schedule_condition'],at,'UTC')
        if not inside: condition={'kind':'fixed','at':at}
        context=dict(current,schedule_condition=condition)
        kept=not self._blockers(current,registry) and is_approval_current(r['approval'],snapshot,context)
        payload=dict(delivery_id=r['id'],expected_version=r['version'],scheduled_at=at,timezone=timezone,schedule_condition=condition,approval_retained=kept,registry_revision=registry.revision,policy_revision=current['policy_revision'],current_condition=r['schedule_condition'])
        payload.update(preview_hash=digest(payload),reasons=[] if kept else ['계획 승인이 필요합니다.'],crossposts=preview_crossposts(dict(content_id=r['content_id'],revision=r['revision'],owner_account_id=r['owner_account_id'],schedule_slot=r['schedule_slot'],source_connection_id=r['connection_id'],source_public_at=at,visibility=r['options'].get('visibility'),title=snapshot.get('title'),description=snapshot.get('original')),registry),source='managed',schedule_kind='local_plan',remote_state='unavailable',execution_enabled=False)
        return payload,context,snapshot

    def preview_schedule(self,delivery_id,expected_version,proposed_time,timezone):
        with self._db() as conn:
            r=self._get(conn,delivery_id,expected_version)
            return self._schedule(r,proposed_time,timezone)[0]

    def reschedule(self,delivery_id,expected_version,proposed_time,timezone,preview_hash):
        with self._db(True) as conn:
            r=self._get(conn,delivery_id,expected_version); self._snapshot(r,conn)
            preview,context,snapshot=self._schedule(r,proposed_time,timezone)
            if preview_hash!=preview['preview_hash']: raise ConflictError()
            registry=self.registry()
            fresh=self._context(r,snapshot,registry)
            fresh['schedule_condition']=context['schedule_condition']
            if fresh!=context: raise ConflictError()
            r.update(blockers=self._blockers(context,registry),scheduled_at=preview['scheduled_at'],timezone=timezone,schedule_condition=preview['schedule_condition'],context=context,subject_hash=self._subject(snapshot,context),status='ready' if preview['approval_retained'] else 'pending')
            return self._save(conn,r,'rescheduled')

    def cancel(self,delivery_id,expected_version):
        with self._db(True) as conn:
            r=self._get(conn,delivery_id,expected_version)
            if r['status']=='cancelled': raise ConflictError()
            r['status']='cancelled'
            return self._save(conn,r,'cancelled')
