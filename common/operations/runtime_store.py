"""실제 실행 원장의 짧은 CAS 트랜잭션. 외부 제출·STOP·프로필 I/O 없음."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib
import json
import math
import secrets
import sqlite3
from uuid import uuid4
from .database import initialize_database, connect_database
from .content_store import StoreError, ConflictError, _json
from .runtime_models import PublicationContext, RunLease, SubmissionPermit, utc, serial


def stamp(value=None):return utc(value if value is not None else datetime.now(timezone.utc)).isoformat()
def digest(value):return hashlib.sha256(_json(serial(value)).encode()).hexdigest()
def ident(prefix):return prefix+'_'+uuid4().hex
def positive(value):
    if type(value) not in (int,float) or not math.isfinite(value) or value<=0:raise StoreError('invalid')
def expected(value):
    if type(value) is not int or value<0:raise StoreError('invalid')


class RuntimeStore:
    def __init__(self,root,registry=None,content_store=None):
        self.root=Path(root).absolute();self.registry=registry;self.content_store=content_store;self._initialized=False
    def initialize(self):
        try:initialize_database(self.root)
        except (OSError,sqlite3.Error) as exc:raise StoreError('storage_error') from exc
        self._initialized=True
    @contextmanager
    def _db(self,write=False):
        c=None
        try:
            if write and not self._initialized:raise StoreError('storage_error')
            try:c=connect_database(self.root,writable=write)
            except FileNotFoundError:
                if write:raise
                yield None;return
            if write:c.execute('BEGIN IMMEDIATE')
            yield c
            if write:c.commit()
        except sqlite3.IntegrityError as exc:
            if c:c.rollback()
            raise ConflictError() from exc
        except (OSError,sqlite3.Error) as exc:
            if c:c.rollback()
            raise StoreError('storage_error') from exc
        except BaseException:
            if c and write:c.rollback()
            raise
        finally:
            if c is not None:c.close()
    def _v3(self,c):return c is not None and c.execute('PRAGMA user_version').fetchone()[0]==3
    def _run(self,c,id):
        row=c.execute('SELECT * FROM runtime_runs WHERE id=?',(id,)).fetchone()
        if row is None:raise StoreError('not_found')
        r=dict(row);r['process_identity']=json.loads(r['process_identity']) if r['process_identity'] else None
        occurrence=c.execute('SELECT payload FROM runs WHERE id=?',(id,)).fetchone()
        r['occurrence']=json.loads(occurrence[0]) if occurrence else None
        return r
    def _delivery(self,c,id,version=None):
        row=c.execute('SELECT * FROM runtime_deliveries WHERE id=?',(id,)).fetchone()
        if row is None:raise StoreError('not_found')
        r=dict(row);r['context']=json.loads(r['context']);r['required']=bool(r['required']);r['execution_state']=r['state']
        r['remote_uncertain']=c.execute('SELECT 1 FROM attempts WHERE delivery_id=? AND request_started=1 AND resolved=0 LIMIT 1',(id,)).fetchone() is not None
        plan=c.execute('SELECT payload FROM deliveries WHERE id=?',(id,)).fetchone();r['plan_status']=json.loads(plan[0]).get('status') if plan else None
        if version is not None:
            expected(version)
            if r['version']!=version:raise ConflictError()
        return r
    def get_run(self,id):
        with self._db() as c:
            if not self._v3(c):return None
            try:return self._run(c,id)
            except StoreError as e:
                if e.code=='not_found':return None
                raise
    def list_runs(self,state=None):
        if state is not None and state not in ('queued','running','waiting','completed','partial','failed'):raise StoreError('invalid')
        with self._db() as c:
            if not self._v3(c):return []
            rows=c.execute('SELECT id FROM runtime_runs'+(' WHERE state=?' if state else '')+' ORDER BY rowid',((state,) if state else ()))
            return [self._run(c,r[0]) for r in rows]
    def get_delivery(self,id):
        with self._db() as c:
            if not self._v3(c):return None
            try:return self._delivery(c,id)
            except StoreError as e:
                if e.code=='not_found':return None
                raise
    def list_operations(self,account='all'):
        if account not in ('all','personal','dept'):raise StoreError('invalid')
        with self._db() as c:
            if not self._v3(c):return []
            rows=[self._delivery(c,r[0]) for r in c.execute('SELECT id FROM runtime_deliveries ORDER BY rowid DESC')]
            return [r for r in rows if account=='all' or account in (r['context']['owner_account_id'],r['context']['destination_account_id'])]
    def events(self,id):
        with self._db() as c:
            if not self._v3(c):return []
            return [dict(r,evidence=json.loads(r['evidence'])) for r in c.execute('SELECT * FROM operation_evidence WHERE delivery_id=? ORDER BY id',(id,))]
    def create_run(self,run_id,*,state='queued'):
        if state!='queued':raise StoreError('invalid')
        with self._db(True) as c:
            c.execute('INSERT INTO runtime_runs(id,state,version) VALUES(?,?,1)',(run_id,state));return self._run(c,run_id)
    def create_delivery(self,delivery_id,run_id,context,*,required=True):
        if not isinstance(context,PublicationContext) or type(required) is not bool:raise StoreError('invalid')
        with self._db(True) as c:
            c.execute('INSERT INTO runtime_deliveries(id,run_id,context,context_hash,state,version,required) VALUES(?,?,?,?,?,1,?)',(delivery_id,run_id,_json(context.to_dict()),context.context_hash,'queued',int(required)))
            return self._delivery(c,delivery_id)
    def claim_run(self,run_id,worker_id,process_identity,now,lease_seconds=60,expected_version=None):
        positive(lease_seconds);now=utc(now)
        if not isinstance(worker_id,str) or not worker_id or not isinstance(process_identity,dict) or set(process_identity)!={'host_id','pid','started_at'} or type(process_identity['pid']) is not int or process_identity['pid']<=0 or not isinstance(process_identity['host_id'],str) or not process_identity['host_id']:raise StoreError('invalid')
        process_identity=dict(process_identity,started_at=stamp(process_identity['started_at']))
        with self._db(True) as c:
            r=self._run(c,run_id)
            if r['state']!='queued' or (expected_version is not None and r['version']!=expected_version):raise ConflictError()
            generation=r['generation']+1;expiry=now+timedelta(seconds=lease_seconds)
            c.execute("UPDATE runtime_runs SET state='running',version=version+1,worker_id=?,generation=?,lease_expires_at=?,process_identity=? WHERE id=?",(worker_id,generation,stamp(expiry),_json(process_identity),run_id))
            return RunLease(run_id,worker_id,generation,expiry)
    def _lease(self,c,lease,now):
        if not isinstance(lease,RunLease):raise StoreError('invalid')
        r=self._run(c,lease.run_id)
        if r['worker_id']!=lease.worker_id or r['generation']!=lease.generation or not r['lease_expires_at'] or utc(r['lease_expires_at'])<=utc(now) or lease.expires_at<=utc(now):raise ConflictError()
        return r
    def renew_lease(self,lease,now,lease_seconds=60):
        positive(lease_seconds)
        with self._db(True) as c:
            self._lease(c,lease,now);expiry=utc(now)+timedelta(seconds=lease_seconds)
            c.execute('UPDATE runtime_runs SET lease_expires_at=?,version=version+1 WHERE id=?',(stamp(expiry),lease.run_id));return RunLease(lease.run_id,lease.worker_id,lease.generation,expiry)
    def _event(self,c,delivery_id,kind,evidence,attempt_id=None):
        cur=c.execute('INSERT INTO operation_evidence(delivery_id,attempt_id,kind,evidence,created_at) VALUES(?,?,?,?,?)',(delivery_id,attempt_id,kind,_json(serial(evidence or {})),stamp()));return cur.lastrowid
    def _state(self,c,id,state,**values):
        allowed={'remote_id','url','scheduled_at'}
        if set(values)-allowed:raise StoreError('invalid')
        sql='UPDATE runtime_deliveries SET state=?,version=version+1'+''.join(','+k+'=?' for k in values)+' WHERE id=?'
        c.execute(sql,(state,*values.values(),id))
        if state in ('cancelled','needs_review'):
            c.execute('UPDATE submission_permits SET invalidated=1 WHERE consumed=0 AND attempt_id IN (SELECT id FROM attempts WHERE delivery_id=?)',(id,))
        self._aggregate(c,self._delivery(c,id)['run_id'])
    def _aggregate(self,c,run_id):
        states=[r[0] for r in c.execute('SELECT state FROM runtime_deliveries WHERE run_id=? AND required=1',(run_id,))]
        if not states:return
        uncertain=c.execute("SELECT 1 FROM attempts a JOIN runtime_deliveries d ON a.delivery_id=d.id WHERE d.run_id=? AND a.request_started=1 AND a.resolved=0 AND (a.outcome IS NOT NULL OR d.state IN ('cancelled','needs_review','unknown')) LIMIT 1",(run_id,)).fetchone()
        if uncertain:state='waiting'
        elif all(s=='verified' for s in states):state='completed'
        elif any(s in ('unknown','needs_review') for s in states):state='waiting'
        elif any(s=='verified' for s in states) and any(s in ('failed','cancelled','retry_wait') for s in states):state='partial'
        elif all(s in ('failed','cancelled') for s in states):state='failed'
        else:state='running'
        c.execute('UPDATE runtime_runs SET state=?,version=version+1 WHERE id=?',(state,run_id))
    def transition_delivery(self,delivery_id,expected_version,state,*,evidence=None,remote_id=None):
        transitions={'queued':{'running','needs_review','cancelled'},'running':{'needs_review','retry_wait','cancelled'},'uploaded':{'published','needs_review'},'scheduled':{'published','needs_review'},'published':{'verified','needs_review'},'retry_wait':{'queued','needs_review','cancelled'},'unknown':{'needs_review'},'needs_review':{'cancelled'}}
        with self._db(True) as c:
            r=self._delivery(c,delivery_id,expected_version)
            if state not in transitions.get(r['state'],set()):raise ConflictError()
            self._state(c,delivery_id,state,**({'remote_id':remote_id} if remote_id else {}));self._event(c,delivery_id,state,evidence);return self._delivery(c,delivery_id)
    def _approval(self,c,id):
        r=c.execute('SELECT * FROM publication_approvals WHERE delivery_id=? ORDER BY id DESC LIMIT 1',(id,)).fetchone()
        return dict(r,report_hashes=json.loads(r['report_hashes'])) if r else None
    def record_publication_approval(self,delivery_id,expected_version,context_hash,approval_hash,report_hashes,*,actor='console_user',decision='approved'):
        if decision not in ('approved','rejected','revoked') or not isinstance(approval_hash,str) or not approval_hash or not isinstance(report_hashes,(list,tuple)) or len(set(report_hashes))<1 or not all(isinstance(x,str) and x for x in report_hashes):raise StoreError('invalid')
        with self._db(True) as c:
            r=self._delivery(c,delivery_id,expected_version)
            if r['context_hash']!=context_hash or tuple(r['context']['review_report_hashes'])!=tuple(report_hashes):raise ConflictError()
            c.execute('INSERT INTO publication_approvals(delivery_id,context_hash,approval_hash,report_hashes,actor,decision,created_at) VALUES(?,?,?,?,?,?,?)',(delivery_id,context_hash,approval_hash,_json(list(report_hashes)),actor,decision,stamp()))
            c.execute('UPDATE runtime_deliveries SET version=version+1 WHERE id=?',(delivery_id,))
            if decision!='approved':c.execute('UPDATE submission_permits SET invalidated=1 WHERE attempt_id IN (SELECT id FROM attempts WHERE delivery_id=?)',(delivery_id,))
            return self._approval(c,delivery_id)
    def get_publication_approval(self,delivery_id):
        with self._db() as c:return self._approval(c,delivery_id) if self._v3(c) else None
    def _check_approval(self,c,d,context_hash,approval_hash,now):
        a=self._approval(c,d['id'])
        if d['context_hash']!=context_hash or not a or a['decision']!='approved' or a['context_hash']!=context_hash or a['approval_hash']!=approval_hash or utc(d['context']['auth_expires_at'])<=utc(now):raise ConflictError()
        p=c.execute('SELECT payload FROM deliveries WHERE id=?',(d['id'],)).fetchone()
        if p:
            plan=json.loads(p[0])
            if plan.get('status')=='cancelled':raise ConflictError()
            names={'content_id':'content_id','revision':'content_revision','manifest_hash':'manifest_hash','owner_account_id':'owner_account_id','destination_account_id':'destination_account_id','connection_id':'connection_id','publication_purpose':'publication_purpose','schedule_slot':'schedule_slot','options':'options','schedule_condition':'schedule_condition'}
            for key,ctxkey in names.items():
                if key in plan and plan[key]!=d['context'][ctxkey]:raise ConflictError()
        controls=list(c.execute('SELECT * FROM control_events e WHERE version=(SELECT MAX(version) FROM control_events WHERE scope=e.scope AND target_id=e.target_id)'))
        for control in controls:
            applies=control['scope']=='managed' or (control['scope']=='account' and control['target_id'] in (d['context']['owner_account_id'],d['context']['destination_account_id'])) or (control['scope']=='connection' and control['target_id']==d['context']['connection_id'])
            if applies and control['action']=='pause':raise ConflictError()
    def create_attempt(self,delivery_id,expected_version,lease,context_hash,approval_hash,*,reservation_id=None,now=None):
        now=stamp(now)
        with self._db(True) as c:
            d=self._delivery(c,delivery_id,expected_version);self._lease(c,lease,now)
            if d['run_id']!=lease.run_id or d['state'] not in ('queued','running','retry_wait'):raise ConflictError()
            self._check_approval(c,d,context_hash,approval_hash,now)
            if reservation_id:
                r=c.execute('SELECT * FROM quota_reservations WHERE id=?',(reservation_id,)).fetchone()
                if not r or r['delivery_id']!=delivery_id or r['state']!='held':raise ConflictError()
            ordinal=c.execute('SELECT COALESCE(MAX(ordinal),0)+1 FROM attempts WHERE delivery_id=?',(delivery_id,)).fetchone()[0];id=ident('attempt')
            c.execute('INSERT INTO attempts(id,delivery_id,ordinal,context_hash,approval_hash,reservation_id,generation,created_at) VALUES(?,?,?,?,?,?,?,?)',(id,delivery_id,ordinal,context_hash,approval_hash,reservation_id,lease.generation,now))
            self._state(c,delivery_id,'running');return self._attempt(c,id)
    def _attempt(self,c,id):
        row=c.execute('SELECT * FROM attempts WHERE id=?',(id,)).fetchone()
        if row is None:raise StoreError('not_found')
        r=dict(row);r['result']=json.loads(r['result']) if r['result'] else None;return r
    def get_attempt(self,id):
        with self._db() as c:
            if not self._v3(c):return None
            try:return self._attempt(c,id)
            except StoreError as e:
                if e.code=='not_found':return None
                raise
    def attempts(self,delivery_id):
        with self._db() as c:return [self._attempt(c,r[0]) for r in c.execute('SELECT id FROM attempts WHERE delivery_id=? ORDER BY ordinal',(delivery_id,))] if self._v3(c) else []
    def _submission_eligible(self,c,a,d):
        if d['state']!='running' or a['resolved'] or a['request_started']:raise ConflictError()
        if a['reservation_id']:
            reservation=self._reservation(c,a['reservation_id'])
            if reservation['state']!='held' or reservation['delivery_id']!=d['id']:raise ConflictError()
    def issue_permit(self,attempt_id,lease,context_hash,approval_hash,now,ttl_seconds=30):
        positive(ttl_seconds)
        with self._db(True) as c:
            self._lease(c,lease,now);a=self._attempt(c,attempt_id);d=self._delivery(c,a['delivery_id']);self._check_approval(c,d,context_hash,approval_hash,now)
            self._submission_eligible(c,a,d)
            if a['resolved'] or a['request_started'] or a['generation']!=lease.generation or d['run_id']!=lease.run_id or a['context_hash']!=context_hash or a['approval_hash']!=approval_hash:raise ConflictError()
            nonce=secrets.token_hex(32);expiry=min(utc(now)+timedelta(seconds=ttl_seconds),lease.expires_at,utc(d['context']['auth_expires_at']))
            c.execute('INSERT INTO submission_permits(attempt_id,nonce_hash,run_id,generation,context_hash,approval_hash,expires_at) VALUES(?,?,?,?,?,?,?)',(attempt_id,hashlib.sha256(nonce.encode()).hexdigest(),lease.run_id,lease.generation,context_hash,approval_hash,stamp(expiry)))
            return SubmissionPermit(attempt_id,nonce,lease.run_id,lease.generation,expiry,context_hash,approval_hash)
    def consume_permit(self,permit,lease,now):
        with self._db(True) as c:
            self._lease(c,lease,now);a=self._attempt(c,permit.attempt_id);d=self._delivery(c,a['delivery_id']);self._check_approval(c,d,permit.context_hash,permit.approval_hash,now)
            self._submission_eligible(c,a,d)
            p=c.execute('SELECT * FROM submission_permits WHERE attempt_id=?',(permit.attempt_id,)).fetchone()
            if not p or p['consumed'] or p['invalidated'] or utc(p['expires_at'])<=utc(now) or p['nonce_hash']!=hashlib.sha256(permit.nonce.encode()).hexdigest() or p['run_id']!=lease.run_id or p['generation']!=lease.generation or permit.run_id!=lease.run_id or permit.generation!=lease.generation or p['context_hash']!=permit.context_hash or p['approval_hash']!=permit.approval_hash or a['request_started'] or a['resolved']:raise ConflictError()
            c.execute('UPDATE submission_permits SET consumed=1 WHERE attempt_id=?',(permit.attempt_id,));c.execute('UPDATE attempts SET request_started=1 WHERE id=?',(permit.attempt_id,));self._state(c,d['id'],'submitting');self._event(c,d['id'],'request_started',{},a['id']);return self._attempt(c,a['id'])
    def invalidate_permits(self,delivery_id):
        with self._db(True) as c:c.execute('UPDATE submission_permits SET invalidated=1 WHERE attempt_id IN (SELECT id FROM attempts WHERE delivery_id=?)',(delivery_id,))
    def finish_attempt(self,attempt_id,outcome,*,remote_id=None,url=None,scheduled_at=None,evidence=None,now=None):
        if outcome not in ('submitted','scheduled','unknown','failed'):raise StoreError('invalid')
        evidence=evidence or {}
        with self._db(True) as c:
            a=self._attempt(c,attempt_id)
            if a['resolved'] or a['outcome'] is not None:raise ConflictError()
            if outcome in ('submitted','scheduled','unknown') and not a['request_started']:raise ConflictError()
            safe=outcome=='failed' and not a['request_started'] and evidence.get('confirmed_not_submitted') is True
            state={'submitted':'uploaded','scheduled':'scheduled','unknown':'unknown','failed':'retry_wait' if safe else 'unknown'}[outcome]
            result=dict(outcome=outcome,remote_id=remote_id,url=url,scheduled_at=stamp(scheduled_at) if scheduled_at else None,evidence=serial(evidence),recorded_at=stamp(now))
            c.execute('UPDATE attempts SET outcome=?,result=?,resolved=? WHERE id=?',(outcome,_json(result),int(state!='unknown'),attempt_id));c.execute('UPDATE submission_permits SET invalidated=1 WHERE attempt_id=?',(attempt_id,));self._state(c,a['delivery_id'],state,remote_id=remote_id,url=url,scheduled_at=result['scheduled_at']);self._event(c,a['delivery_id'],state,evidence,attempt_id);return self._attempt(c,attempt_id)
    def submit_occurrence(self,request,request_hash=None):
        required={'job_id','scheduled_at_utc','phase','source','request_kind','mode'}
        if not isinstance(request,dict) or set(request)!=required or request['mode'] not in ('live','dry'):raise StoreError('invalid')
        request=dict(request,scheduled_at_utc=stamp(request['scheduled_at_utc']));hashed=digest(request)
        if request_hash is not None and request_hash!=hashed:raise ConflictError()
        key=tuple(request[k] for k in ('job_id','scheduled_at_utc','phase'))
        with self._db(True) as c:
            old=c.execute('SELECT * FROM runs WHERE job_id=? AND scheduled_at_utc=? AND phase=?',key).fetchone()
            if old:
                runtime=c.execute('SELECT id FROM runtime_runs WHERE id=?',(old['id'],)).fetchone()
                if old['request_hash']!=hashed or runtime is None:raise ConflictError()
                return dict(json.loads(old['payload']),runtime=self._run(c,old['id']))
            id=ident('run');payload=dict(request,id=id)
            c.execute('INSERT INTO runs VALUES(?,?,?,?,?,?)',(id,*key,hashed,_json(payload)));c.execute("INSERT INTO runtime_runs(id,state,version) VALUES(?,'queued',1)",(id,));return dict(payload,runtime=self._run(c,id))
    def observe_bucket(self,bucket_id,limit,observed_usage,observed_at,expires_at):
        positive(limit)
        if type(observed_usage) not in (int,float) or not math.isfinite(observed_usage) or observed_usage<0 or utc(expires_at)<=utc(observed_at):raise StoreError('invalid')
        with self._db(True) as c:
            old=c.execute('SELECT observed_at FROM quota_buckets WHERE id=?',(bucket_id,)).fetchone()
            if old and utc(old[0])>utc(observed_at):raise ConflictError()
            c.execute('INSERT INTO quota_buckets VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET capacity=excluded.capacity,observed_usage=excluded.observed_usage,observed_at=excluded.observed_at,expires_at=excluded.expires_at',(bucket_id,limit,observed_usage,stamp(observed_at),stamp(expires_at)));return self._buckets(c)[bucket_id]
    def _buckets(self,c):
        result={r['id']:dict(r,reserved=0.0) for r in c.execute('SELECT * FROM quota_buckets')}
        for row in c.execute("SELECT requirements,state,settled_at FROM quota_reservations WHERE state IN ('held','settled')"):
            for req in json.loads(row[0]):
                if req['bucket_id'] in result:
                    b=result[req['bucket_id']]
                    if row['state']=='held' or not row['settled_at'] or utc(row['settled_at'])>utc(b['observed_at']):b['reserved']+=req['amount']
        return result
    def quota_buckets(self):
        with self._db() as c:return list(self._buckets(c).values()) if self._v3(c) else []
    def _reservation(self,c,id):
        r=c.execute('SELECT * FROM quota_reservations WHERE id=?',(id,)).fetchone()
        if not r:raise StoreError('not_found')
        return dict(r,requirements=json.loads(r['requirements']))
    def get_reservation(self,id):
        with self._db() as c:
            if not self._v3(c):return None
            try:return self._reservation(c,id)
            except StoreError as e:
                if e.code=='not_found':return None
                raise
    def reserve_quota(self,delivery_id,requirements,now,*,reservation_id=None):
        if not isinstance(requirements,(tuple,list)) or not requirements:raise StoreError('invalid')
        requirements=serial(requirements);seen=set()
        for req in requirements:
            if not isinstance(req,dict) or set(req)!={'bucket_id','amount'} or not isinstance(req['bucket_id'],str) or req['bucket_id'] in seen:raise StoreError('invalid')
            positive(req['amount']);seen.add(req['bucket_id'])
        with self._db(True) as c:
            self._delivery(c,delivery_id);id=reservation_id or ident('reservation')
            old=c.execute('SELECT id FROM quota_reservations WHERE id=?',(id,)).fetchone()
            if old:
                old=self._reservation(c,id)
                if old['delivery_id']!=delivery_id or old['requirements']!=requirements or old['state']!='held':raise ConflictError()
                return old
            buckets=self._buckets(c)
            for req in requirements:
                b=buckets.get(req['bucket_id'])
                if not b or utc(b['expires_at'])<=utc(now) or utc(b['observed_at'])>utc(now):raise StoreError('quota_observation_required')
                if b['observed_usage']+b['reserved']+req['amount']>b['capacity']:raise StoreError('quota_exceeded')
            c.execute("INSERT INTO quota_reservations(id,delivery_id,requirements,state,created_at) VALUES(?,?,?,'held',?)",(id,delivery_id,_json(requirements),stamp(now)));return self._reservation(c,id)
    def settle_reservation(self,reservation_id,*,release=False,now=None):
        if type(release) is not bool:raise StoreError('invalid')
        with self._db(True) as c:
            r=self._reservation(c,reservation_id)
            attempts=[dict(x) for x in c.execute('SELECT * FROM attempts WHERE reservation_id=?',(reservation_id,))]
            for a in attempts:
                if not a['request_started']:continue
                result=json.loads(a['result']) if a['result'] else {}
                resolution=result.get('resolution',{}).get('kind')
                if not a['resolved']:raise ConflictError()
                if release:
                    if resolution!='confirmed_not_posted':raise ConflictError()
                elif a['outcome'] not in ('submitted','scheduled') and resolution!='link_existing':raise ConflictError()
            state='released' if release else 'settled'
            if r['state']==state:return r
            if r['state']!='held':raise ConflictError()
            c.execute('UPDATE quota_reservations SET state=?,settled_at=? WHERE id=?',(state,stamp(now),reservation_id))
            c.execute('UPDATE submission_permits SET invalidated=1 WHERE consumed=0 AND attempt_id IN (SELECT id FROM attempts WHERE reservation_id=?)',(reservation_id,))
            return self._reservation(c,reservation_id)
    def record_evidence(self,delivery_id,kind,evidence,*,attempt_id=None):
        with self._db(True) as c:
            self._delivery(c,delivery_id)
            if attempt_id and self._attempt(c,attempt_id)['delivery_id']!=delivery_id:raise ConflictError()
            id=self._event(c,delivery_id,kind,evidence,attempt_id);return dict(id=id,delivery_id=delivery_id,kind=kind,evidence=serial(evidence))
    def resolve_delivery(self,delivery_id,expected_version,request_key,kind,evidence,note,actor):
        if kind not in ('link_existing','confirmed_not_posted','cancel_local') or not isinstance(evidence,dict) or not evidence or not isinstance(note,str) or not note or not isinstance(actor,str) or not actor or not isinstance(request_key,str) or not request_key:raise StoreError('invalid')
        command=digest(dict(delivery_id=delivery_id,expected_version=expected_version,kind=kind,evidence=evidence,note=note,actor=actor))
        with self._db(True) as c:
            old=c.execute('SELECT * FROM runtime_requests WHERE request_key=?',(request_key,)).fetchone()
            if old:
                if old['command_hash']!=command:raise ConflictError()
                return json.loads(old['result'])
            d=self._delivery(c,delivery_id,expected_version)
            if d['state'] not in ('unknown','needs_review','failed','retry_wait') and not (d['state']=='cancelled' and d['remote_uncertain'] and kind!='cancel_local'):raise ConflictError()
            attempts=list(c.execute('SELECT * FROM attempts WHERE delivery_id=? AND resolved=0',(delivery_id,)))
            if kind=='link_existing':
                if not isinstance(evidence.get('remote_id'),str) or not evidence['remote_id'] or evidence.get('identity_confirmed') is not True:raise StoreError('insufficient_evidence')
                self._state(c,delivery_id,'uploaded',remote_id=evidence['remote_id'])
            elif kind=='confirmed_not_posted':
                if any(evidence.get(key) is not True for key in ('confirmed_not_posted','old_process_terminated','profile_lock_released')):raise StoreError('insufficient_evidence')
                self._state(c,delivery_id,'retry_wait')
            else:self._state(c,delivery_id,'cancelled')
            for attempt in attempts:
                # Local cancellation cannot turn uncertainty about a started request into certainty.
                if kind=='cancel_local' and attempt['request_started']:continue
                result=json.loads(attempt['result']) if attempt['result'] else {}
                result['resolution']=dict(kind=kind,evidence=serial(evidence),note=note,actor=actor,recorded_at=stamp())
                c.execute('UPDATE attempts SET resolved=1,result=? WHERE id=?',(_json(result),attempt['id']))
            c.execute('UPDATE submission_permits SET invalidated=1 WHERE attempt_id IN (SELECT id FROM attempts WHERE delivery_id=?)',(delivery_id,))
            self._aggregate(c,d['run_id'])
            self._event(c,delivery_id,'resolved_'+kind,dict(evidence=evidence,note=note,actor=actor));result=self._delivery(c,delivery_id)
            c.execute('INSERT INTO runtime_requests VALUES(?,?,?)',(request_key,command,_json(result)));return result
    def control(self,scope,id,action,expected_version,request_key,reason,actor='console_user'):
        expected(expected_version)
        if scope not in ('managed','account','connection') or action not in ('pause','resume') or not all(isinstance(x,str) and x for x in (id,request_key,reason,actor)):raise StoreError('invalid')
        command=digest(dict(scope=scope,id=id,action=action,expected_version=expected_version,reason=reason,actor=actor))
        with self._db(True) as c:
            old=c.execute('SELECT * FROM control_events WHERE request_key=?',(request_key,)).fetchone()
            if old:
                if old['command_hash']!=command:raise ConflictError()
                return dict(old)
            current=c.execute('SELECT COALESCE(MAX(version),0) FROM control_events WHERE scope=? AND target_id=?',(scope,id)).fetchone()[0]
            if current!=expected_version:raise ConflictError()
            cur=c.execute('INSERT INTO control_events(scope,target_id,version,action,request_key,command_hash,reason,actor,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(scope,id,current+1,action,request_key,command,reason,actor,stamp()))
            return dict(c.execute('SELECT * FROM control_events WHERE id=?',(cur.lastrowid,)).fetchone())
    def control_state(self):
        with self._db() as c:
            if not self._v3(c):return []
            return [dict(r) for r in c.execute('SELECT * FROM control_events e WHERE version=(SELECT MAX(version) FROM control_events WHERE scope=e.scope AND target_id=e.target_id) ORDER BY e.id')]
