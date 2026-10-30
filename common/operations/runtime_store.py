"""실제 실행 원장의 짧은 CAS 트랜잭션. 외부 제출·STOP·프로필 I/O 없음."""
from contextlib import contextmanager, nullcontext
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
from .runtime_models import PublicationContext, RunLease, SubmissionPermit, ExecutionPolicy, utc, serial


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
        # 예전 v3 읽기는 이행하지 않는다. 명시 initialize에서만 선택 표를 만든다.
        selection=c.execute('SELECT delivery_id FROM runtime_resume_targets WHERE run_id=?',(id,)).fetchone() if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='runtime_resume_targets'").fetchone() else None
        r['resume_delivery_id']=selection[0] if selection else None
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
    def get_plan_delivery(self,id):
        """내부 builder 전용 원본 계획. HTTP 응답에 직접 노출하지 않는다."""
        with self._db() as c:
            if not self._v3(c):return None
            row=c.execute('SELECT payload FROM deliveries WHERE id=?',(id,)).fetchone()
            return json.loads(row[0]) if row else None
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
    def _publication_guard(self):
        """실행 store는 승인 writer와 최종 허가를 직렬화한다. 순수 DB fixture 호환."""
        locks=getattr(self,'locks',None)
        if locks is None:
            policy=getattr(self,'execution_policy',None)
            if self.registry is not None or (isinstance(policy,ExecutionPolicy) and policy.enabled):
                raise StoreError('publication_lock_required')
            # 등록부도 활성 실행 정책도 없는 DB-only store만 이전 순수 fixture 허용.
            return nullcontext()
        guard=getattr(locks,'publication_guard',None)
        if callable(guard):return guard(job='publication-approval',wait=10)
        return locks.hold(['control:publish-gate'],job='publication-approval',wait=10)
    def record_publication_approval(self,delivery_id,expected_version,context_hash,approval_hash,report_hashes,*,actor='console_user',decision='approved'):
        if decision not in ('approved','rejected','revoked') or not isinstance(approval_hash,str) or not approval_hash or not isinstance(report_hashes,(list,tuple)) or len(set(report_hashes))<1 or not all(isinstance(x,str) and x for x in report_hashes):raise StoreError('invalid')
        with self._publication_guard():
            with self._db(True) as c:
                r=self._delivery(c,delivery_id,expected_version)
                if r['context_hash']!=context_hash or tuple(r['context']['review_report_hashes'])!=tuple(report_hashes):raise ConflictError()
                c.execute('INSERT INTO publication_approvals(delivery_id,context_hash,approval_hash,report_hashes,actor,decision,created_at) VALUES(?,?,?,?,?,?,?)',(delivery_id,context_hash,approval_hash,_json(list(report_hashes)),actor,decision,stamp()))
                c.execute('UPDATE runtime_deliveries SET version=version+1 WHERE id=?',(delivery_id,))
                if decision!='approved':c.execute('UPDATE submission_permits SET invalidated=1 WHERE attempt_id IN (SELECT id FROM attempts WHERE delivery_id=?)',(delivery_id,))
                return self._approval(c,delivery_id)
    def get_publication_approval(self,delivery_id):
        with self._db() as c:return self._approval(c,delivery_id) if self._v3(c) else None
    def refresh_auth_proof(self,delivery_id,expected_version,context,observation,now):
        """신뢰하는 gate만 호출. 의도 고정, 최신 승인 CAS, 원장/unknown/예약 보존."""
        if not isinstance(context,PublicationContext):raise StoreError('invalid')
        with self._db(True) as c:
            d=self._delivery(c,delivery_id,expected_version);old=PublicationContext(**d['context'])
            if old.intent_hash!=context.intent_hash or context.auth_checked_at<old.auth_checked_at:raise ConflictError()
            approval=self._approval(c,delivery_id)
            if not approval or approval['decision']!='approved' or approval['context_hash']!=d['context_hash']:raise ConflictError()
            self._check_approval(c,d,d['context_hash'],approval['approval_hash'],now,require_fresh_auth=False)
            content=c.execute('SELECT current_revision FROM contents WHERE id=?',(context.content_id,)).fetchone()
            if not content or content['current_revision']!=context.content_revision:raise ConflictError()
            if context.context_hash==old.context_hash:return d
            c.execute('UPDATE submission_permits SET invalidated=1 WHERE consumed=0 AND attempt_id IN (SELECT id FROM attempts WHERE delivery_id=?)',(delivery_id,))
            c.execute('UPDATE runtime_deliveries SET context=?,context_hash=?,version=version+1 WHERE id=?',(_json(context.to_dict()),context.context_hash,delivery_id))
            # 재승인이 아니라 기존 승인 의도와 새 인증 증명의 결속. 원래 승인은 append-only 보존.
            c.execute('INSERT INTO publication_approvals(delivery_id,context_hash,approval_hash,report_hashes,actor,decision,created_at) VALUES(?,?,?,?,?,?,?)',
                (delivery_id,context.context_hash,approval['approval_hash'],_json(approval['report_hashes']),'server_auth_refresh','approved',stamp(now)))
            self._event(c,delivery_id,'auth_proof_refreshed',dict(previous_context_hash=old.context_hash,context_hash=context.context_hash,intent_hash=context.intent_hash,source_approval_id=approval['id'],checked_at=stamp(now)))
            self._event(c,delivery_id,'target_observation',observation)
            return self._delivery(c,delivery_id)
    def fail_preflight(self,delivery_id,expected_version,lease,now):
        with self._db(True) as c:
            d=self._delivery(c,delivery_id,expected_version)
            run=self._run(c,d['run_id'])
            if run['worker_id']!=lease.worker_id or run['generation']!=lease.generation or d['state']!='queued':raise ConflictError()
            if c.execute('SELECT 1 FROM attempts WHERE delivery_id=? AND resolved=0',(delivery_id,)).fetchone():raise ConflictError()
            self._state(c,delivery_id,'retry_wait')
            self._event(c,delivery_id,'preflight_failed',dict(confirmed_not_submitted=True,checked_at=stamp(now)))
    def _check_approval(self,c,d,context_hash,approval_hash,now,*,require_fresh_auth=True):
        a=self._approval(c,d['id'])
        if d['context_hash']!=context_hash or not a or a['decision']!='approved' or a['context_hash']!=context_hash or a['approval_hash']!=approval_hash or (require_fresh_auth and utc(d['context']['auth_expires_at'])<=utc(now)):raise ConflictError()
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
    def create_attempt(self,delivery_id,expected_version,lease,context_hash,approval_hash,*,reservation_id=None,now=None,clock=None):
        now=stamp(now)
        with self._db(True) as c:
            if clock is not None:now=stamp(clock())
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
    def issue_permit(self,attempt_id,lease,context_hash,approval_hash,now,ttl_seconds=30,*,clock=None):
        positive(ttl_seconds)
        with self._db(True) as c:
            if clock is not None:now=clock()
            self._lease(c,lease,now);a=self._attempt(c,attempt_id);d=self._delivery(c,a['delivery_id']);self._check_approval(c,d,context_hash,approval_hash,now)
            self._submission_eligible(c,a,d)
            if a['resolved'] or a['request_started'] or a['generation']!=lease.generation or d['run_id']!=lease.run_id or a['context_hash']!=context_hash or a['approval_hash']!=approval_hash:raise ConflictError()
            nonce=secrets.token_hex(32);expiry=min(utc(now)+timedelta(seconds=ttl_seconds),lease.expires_at,utc(d['context']['auth_expires_at']))
            c.execute('INSERT INTO submission_permits(attempt_id,nonce_hash,run_id,generation,context_hash,approval_hash,expires_at) VALUES(?,?,?,?,?,?,?)',(attempt_id,hashlib.sha256(nonce.encode()).hexdigest(),lease.run_id,lease.generation,context_hash,approval_hash,stamp(expiry)))
            return SubmissionPermit(attempt_id,nonce,lease.run_id,lease.generation,expiry,context_hash,approval_hash)
    def consume_permit(self,permit,lease,now,*,clock=None):
        with self._db(True) as c:
            if clock is not None:now=clock()
            self._lease(c,lease,now);a=self._attempt(c,permit.attempt_id);d=self._delivery(c,a['delivery_id']);self._check_approval(c,d,permit.context_hash,permit.approval_hash,now)
            self._submission_eligible(c,a,d)
            p=c.execute('SELECT * FROM submission_permits WHERE attempt_id=?',(permit.attempt_id,)).fetchone()
            if not p or p['consumed'] or p['invalidated'] or utc(p['expires_at'])<=utc(now) or p['nonce_hash']!=hashlib.sha256(permit.nonce.encode()).hexdigest() or p['run_id']!=lease.run_id or p['generation']!=lease.generation or permit.run_id!=lease.run_id or permit.generation!=lease.generation or p['context_hash']!=permit.context_hash or p['approval_hash']!=permit.approval_hash or a['request_started'] or a['resolved']:raise ConflictError()
            c.execute('UPDATE submission_permits SET consumed=1 WHERE attempt_id=?',(permit.attempt_id,));c.execute('UPDATE attempts SET request_started=1 WHERE id=?',(permit.attempt_id,));self._state(c,d['id'],'submitting');self._event(c,d['id'],'request_started',{},a['id']);return self._attempt(c,a['id'])
    def redeem_bridge(self,permit,executor_id,action,prepared_hash,now,*,clock=None):
        """소비된 permit을 자식 leaf에서 딱 한 번 사용한다. 외부 I/O 없음."""
        if (not isinstance(permit,SubmissionPermit) or
            not all(isinstance(v,str) and v for v in (executor_id,action,prepared_hash)) or
            len(prepared_hash)!=64 or any(v not in '0123456789abcdef' for v in prepared_hash)):
            raise StoreError('invalid')
        with self._db(True) as c:
            if clock is not None:now=clock()
            now=utc(now)
            a=self._attempt(c,permit.attempt_id);d=self._delivery(c,a['delivery_id']);run=self._run(c,d['run_id'])
            if not run.get('worker_id') or not run.get('lease_expires_at'):raise ConflictError()
            lease=RunLease(run['id'],run['worker_id'],run['generation'],run['lease_expires_at'])
            self._lease(c,lease,now)
            p=c.execute('SELECT * FROM submission_permits WHERE attempt_id=?',(permit.attempt_id,)).fetchone()
            if (not p or not p['consumed'] or p['invalidated'] or
                utc(p['expires_at'])<=now or permit.expires_at<=now or
                stamp(permit.expires_at)!=p['expires_at'] or
                not secrets.compare_digest(p['nonce_hash'],hashlib.sha256(permit.nonce.encode()).hexdigest()) or
                p['run_id']!=lease.run_id or permit.run_id!=lease.run_id or
                p['generation']!=lease.generation or permit.generation!=lease.generation or
                a['generation']!=lease.generation or
                p['context_hash']!=permit.context_hash or a['context_hash']!=permit.context_hash or
                p['approval_hash']!=permit.approval_hash or a['approval_hash']!=permit.approval_hash or
                not a['request_started'] or a['resolved'] or a['outcome'] is not None or
                d['state']!='submitting'):
                raise ConflictError()
            self._check_approval(c,d,permit.context_hash,permit.approval_hash,now)
            content=c.execute('SELECT current_revision FROM contents WHERE id=?',(d['context']['content_id'],)).fetchone()
            revision=c.execute('SELECT manifest_hash FROM revisions WHERE content_id=? AND revision=?',
                (d['context']['content_id'],d['context']['content_revision'])).fetchone()
            if not content or content[0]!=d['context']['content_revision'] or not revision or revision[0]!=d['context']['manifest_hash']:
                raise ConflictError()
            if self.registry is not None:
                policy=self.registry.policies.get(d['context']['policy_revision'],{})
                max_age=policy.get('auth_max_age_seconds',300)
                if now-utc(d['context']['auth_checked_at'])>timedelta(seconds=max_age):raise ConflictError()
            if a['reservation_id']:
                reservation=self._reservation(c,a['reservation_id'])
                if reservation['state']!='held' or reservation['delivery_id']!=d['id']:raise ConflictError()
            c.execute('INSERT INTO bridge_redemptions VALUES(?,?,?,?,?)',
                (permit.attempt_id,executor_id,action,prepared_hash,stamp(now)))
            return dict(attempt_id=permit.attempt_id,executor_id=executor_id,action=action,
                        prepared_hash=prepared_hash,redeemed_at=stamp(now))

    def invalidate_permits(self,delivery_id):
        with self._db(True) as c:c.execute('UPDATE submission_permits SET invalidated=1 WHERE attempt_id IN (SELECT id FROM attempts WHERE delivery_id=?)',(delivery_id,))
    def finish_attempt(self,attempt_id,outcome,*,remote_id=None,url=None,scheduled_at=None,evidence=None,now=None):
        if outcome not in ('submitted','scheduled','unknown','failed'):raise StoreError('invalid')
        evidence=evidence or {}
        with self._db(True) as c:
            a=self._attempt(c,attempt_id)
            current=self._delivery(c,a['delivery_id']);run=self._run(c,current['run_id'])
            if a['resolved'] or a['outcome'] is not None or a['generation']!=run['generation']:
                self._event(c,a['delivery_id'],'late_attempt_result',dict(outcome=outcome,remote_id=remote_id,url=url,scheduled_at=stamp(scheduled_at) if scheduled_at else None,evidence=serial(evidence),recorded_at=stamp(now)),attempt_id)
                return a
            if outcome in ('submitted','scheduled','unknown') and not a['request_started']:raise ConflictError()
            safe=outcome=='failed' and not a['request_started'] and evidence.get('confirmed_not_submitted') is True
            state={'submitted':'uploaded','scheduled':'scheduled','unknown':'unknown','failed':'retry_wait' if safe else 'unknown'}[outcome]
            result=dict(outcome=outcome,remote_id=remote_id,url=url,scheduled_at=stamp(scheduled_at) if scheduled_at else None,evidence=serial(evidence),recorded_at=stamp(now))
            c.execute('UPDATE attempts SET outcome=?,result=?,resolved=? WHERE id=?',(outcome,_json(result),int(state!='unknown'),attempt_id));c.execute('UPDATE submission_permits SET invalidated=1 WHERE attempt_id=?',(attempt_id,));self._state(c,a['delivery_id'],state,remote_id=remote_id,url=url,scheduled_at=result['scheduled_at']);self._event(c,a['delivery_id'],state,evidence,attempt_id);return self._attempt(c,attempt_id)
    def recover_expired_run(self,run_id,expected_version,now,process_evidence,lock_evidence):
        """서버 복구기가 확인한 신원을 CAS lease와 다시 결합한다. I/O 없음."""
        expected(expected_version);now=utc(now)
        with self._db(True) as c:
            run=self._run(c,run_id)
            if run['version']!=expected_version or not run['lease_expires_at'] or utc(run['lease_expires_at'])>now:raise ConflictError()
            identity=run.get('process_identity') or {}
            dead=isinstance(process_evidence,dict) and process_evidence.get('status')=='dead'
            dead=dead and all(process_evidence.get(k)==identity.get(k) and identity.get(k) is not None for k in ('host_id','pid','started_at'))
            rows=[self._delivery(c,r[0]) for r in c.execute('SELECT id FROM runtime_deliveries WHERE run_id=?',(run_id,))]
            for d in rows:
                if d['state'] not in ('queued','running','submitting','retry_wait'):continue
                if d['state']=='queued' and run.get('resume_delivery_id') not in (None,d['id']):continue
                lock=lock_evidence.get(d['id'],{}) if isinstance(lock_evidence,dict) else {}
                free=lock.get('status')=='free' and lock.get('connection_id')==d['context']['connection_id']
                evidence=dict(process=process_evidence,lock=lock,checked_at=stamp(now))
                self._event(c,d['id'],'recovery_observation',evidence)
                attempts=[self._attempt(c,r[0]) for r in c.execute('SELECT id FROM attempts WHERE delivery_id=? AND resolved=0',(d['id'],))]
                for a in attempts:
                    if not a['request_started'] and (not dead or not free):continue
                    c.execute('UPDATE submission_permits SET invalidated=1 WHERE attempt_id=?',(a['id'],))
                    if a['request_started']:
                        if a['outcome'] is None:
                            result=dict(outcome='unknown',evidence=evidence,recorded_at=stamp(now))
                            c.execute("UPDATE attempts SET outcome='unknown',result=? WHERE id=?",(_json(result),a['id']))
                        self._state(c,d['id'],'unknown')
                    else:
                        proof=dict(evidence,confirmed_not_posted=True,confirmed_not_submitted=True,old_process_terminated=True,profile_lock_released=True)
                        result=dict(outcome='failed',evidence=proof,recorded_at=stamp(now),resolution=dict(kind='confirmed_not_posted',evidence=proof,note='expired before request with dead worker and free lock',actor='recovery_service',recorded_at=stamp(now)))
                        c.execute("UPDATE attempts SET outcome='failed',resolved=1,result=? WHERE id=?",(_json(result),a['id']))
                        self._state(c,d['id'],'retry_wait')
                if not attempts and dead and free and d['state']!='retry_wait':self._state(c,d['id'],'retry_wait')
                if dead and free:
                    # reserve commit 직후 종료해 attempt가 없는 예약도 같은 죽음/잠금 증명으로 회수한다.
                    orphans=[r[0] for r in c.execute("SELECT id FROM quota_reservations r WHERE delivery_id=? AND state='held' AND NOT EXISTS (SELECT 1 FROM attempts a WHERE a.reservation_id=r.id)",(d['id'],))]
                    for reservation_id in orphans:
                        c.execute("UPDATE quota_reservations SET state='released',settled_at=? WHERE id=?",(stamp(now),reservation_id))
                        self._event(c,d['id'],'unstarted_reservation_released',dict(evidence,reservation_id=reservation_id,confirmed_not_submitted=True))
            return self._run(c,run_id)

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
        for row in c.execute("SELECT requirements,state,settled_at FROM quota_reservations WHERE state IN ('held','settled') UNION ALL SELECT requirements,state,settled_at FROM quota_productions WHERE state IN ('held','settled')"):
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
        return dict(r,requirements=json.loads(r['requirements']),production_ids=[x[0] for x in c.execute('SELECT production_id FROM quota_production_links WHERE reservation_id=? ORDER BY production_id',(id,))])
    def get_production(self,id):
        with self._db() as c:
            if not self._v3(c):return None
            row=c.execute('SELECT * FROM quota_productions WHERE id=?',(id,)).fetchone()
            return dict(row,requirements=json.loads(row['requirements'])) if row else None
    def list_productions(self):
        with self._db() as c:
            if not self._v3(c):return []
            return [dict(r,requirements=json.loads(r['requirements'])) for r in c.execute('SELECT * FROM quota_productions ORDER BY id')]
    def get_reservation(self,id):
        with self._db() as c:
            if not self._v3(c):return None
            try:return self._reservation(c,id)
            except StoreError as e:
                if e.code=='not_found':return None
                raise
    def reserve_quota(self,delivery_id,requirements,now,*,reservation_id=None,production_requirements=()):
        if not isinstance(requirements,(tuple,list)) or not requirements:raise StoreError('invalid')
        requirements=serial(requirements);seen=set()
        for req in requirements:
            if not isinstance(req,dict) or set(req)!={'bucket_id','amount'} or not isinstance(req['bucket_id'],str) or req['bucket_id'] in seen:raise StoreError('invalid')
            positive(req['amount']);seen.add(req['bucket_id'])
        if not isinstance(production_requirements,(tuple,list)):raise StoreError('invalid')
        production_requirements=serial(production_requirements);production_ids=set()
        for item in production_requirements:
            if not isinstance(item,dict):raise StoreError('invalid')
            if set(item)=={'production_id','requirement'}:
                item['requirements']=[item.pop('requirement')]
            if set(item)!={'production_id','requirements'} or not isinstance(item['production_id'],str) or not item['production_id'] or item['production_id'] in production_ids:raise StoreError('invalid')
            if not isinstance(item['requirements'],list) or not item['requirements']:raise StoreError('invalid')
            for req in item['requirements']:
                if not isinstance(req,dict) or set(req)!={'bucket_id','amount'} or not isinstance(req['bucket_id'],str) or req['bucket_id'] in seen:raise StoreError('invalid')
                positive(req['amount']);seen.add(req['bucket_id'])
            production_ids.add(item['production_id'])
        with self._db(True) as c:
            self._delivery(c,delivery_id);id=reservation_id or ident('reservation')
            old=c.execute('SELECT id FROM quota_reservations WHERE id=?',(id,)).fetchone()
            if old:
                old=self._reservation(c,id)
                if old['delivery_id']!=delivery_id or old['requirements']!=requirements or old['state']!='held' or set(old['production_ids'])!=production_ids:raise ConflictError()
                return old
            new_productions=[]
            for item in production_requirements:
                prior=c.execute('SELECT * FROM quota_productions WHERE id=?',(item['production_id'],)).fetchone()
                if prior:
                    if {r['amount'] for r in json.loads(prior['requirements'])}!={r['amount'] for r in item['requirements']}:raise ConflictError()
                    if prior['state']!='released':continue
                    # Explicitly confirmed unproduced work may be reserved again.
                new_productions.append(item)
            buckets=self._buckets(c)
            for req in requirements+[r for p in new_productions for r in p['requirements']]:
                b=buckets.get(req['bucket_id'])
                if not b or utc(b['expires_at'])<=utc(now) or utc(b['observed_at'])>utc(now):raise StoreError('quota_observation_required')
                if b['observed_usage']+b['reserved']+req['amount']>b['capacity']:raise StoreError('quota_exceeded')
            c.execute("INSERT INTO quota_reservations(id,delivery_id,requirements,state,created_at) VALUES(?,?,?,'held',?)",(id,delivery_id,_json(requirements),stamp(now)))
            for item in new_productions:
                c.execute("INSERT INTO quota_productions VALUES(?,?,'held',?,NULL) ON CONFLICT(id) DO UPDATE SET requirements=excluded.requirements,state='held',created_at=excluded.created_at,settled_at=NULL",(item['production_id'],_json(item['requirements']),stamp(now)))
            for production_id in production_ids:
                c.execute('INSERT INTO quota_production_links VALUES(?,?)',(id,production_id))
            return self._reservation(c,id)
    def settle_production(self,production_id,*,release=False,now=None):
        if type(release) is not bool:raise StoreError('invalid')
        with self._db(True) as c:
            production=c.execute('SELECT * FROM quota_productions WHERE id=?',(production_id,)).fetchone()
            if production is None:raise StoreError('not_found')
            state='released' if release else 'settled'
            if production['state']==state:return dict(production)
            if production['state']!='held':raise ConflictError()
            if release:
                # Local delivery failure does not prove that creation never ran.
                if c.execute("SELECT 1 FROM quota_production_links l JOIN quota_reservations r ON r.id=l.reservation_id WHERE l.production_id=? AND r.state!='released' LIMIT 1",(production_id,)).fetchone():raise ConflictError()
                if c.execute('SELECT 1 FROM attempts a JOIN quota_production_links l ON l.reservation_id=a.reservation_id WHERE l.production_id=? AND a.request_started=1 AND a.resolved=0 LIMIT 1',(production_id,)).fetchone():raise ConflictError()
            c.execute('UPDATE quota_productions SET state=?,settled_at=? WHERE id=?',(state,stamp(now),production_id))
            return dict(c.execute('SELECT * FROM quota_productions WHERE id=?',(production_id,)).fetchone())
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
            if not release:
                c.execute("UPDATE quota_productions SET state='settled',settled_at=? WHERE state='held' AND id IN (SELECT production_id FROM quota_production_links WHERE reservation_id=?)",(stamp(now),reservation_id))
            c.execute('UPDATE submission_permits SET invalidated=1 WHERE consumed=0 AND attempt_id IN (SELECT id FROM attempts WHERE reservation_id=?)',(reservation_id,))
            return self._reservation(c,reservation_id)
    def record_evidence(self,delivery_id,kind,evidence,*,attempt_id=None):
        with self._db(True) as c:
            self._delivery(c,delivery_id)
            if attempt_id and self._attempt(c,attempt_id)['delivery_id']!=delivery_id:raise ConflictError()
            id=self._event(c,delivery_id,kind,evidence,attempt_id);return dict(id=id,delivery_id=delivery_id,kind=kind,evidence=serial(evidence))
    def get_resolution_result(self,delivery_id,expected_version,request_key,kind,evidence,note,actor):
        """동일 명령 재요청은 외부 조회/관측 없이 저장 결과를 반환한다."""
        expected(expected_version)
        command=digest(dict(delivery_id=delivery_id,expected_version=expected_version,kind=kind,evidence=evidence,note=note,actor=actor))
        with self._db() as c:
            if not self._v3(c):return None
            old=c.execute('SELECT * FROM runtime_requests WHERE request_key=?',(request_key,)).fetchone()
            if not old:return None
            if old['command_hash']!=command:raise ConflictError()
            return json.loads(old['result'])

    def record_resolution_observation(self,delivery_id,expected_version,request_key,kind,evidence,note,actor):
        """조회 결과가 불충분한 명령도 동일 request key로 다시 외부 조회하지 않는다."""
        command=digest(dict(delivery_id=delivery_id,expected_version=expected_version,kind=kind,evidence=evidence,note=note,actor=actor))
        with self._db(True) as c:
            old=c.execute('SELECT * FROM runtime_requests WHERE request_key=?',(request_key,)).fetchone()
            if old:
                if old['command_hash']!=command:raise ConflictError()
                return json.loads(old['result'])
            result=self._delivery(c,delivery_id,expected_version)
            c.execute('INSERT INTO runtime_requests VALUES(?,?,?)',(request_key,command,_json(result)))
            return result

    def resolve_delivery(self,delivery_id,expected_version,request_key,kind,evidence,note,actor,*,request_evidence=None):
        if kind not in ('link_existing','confirmed_not_posted','cancel_local') or not isinstance(evidence,dict) or not evidence or not isinstance(note,str) or not note or not isinstance(actor,str) or not actor or not isinstance(request_key,str) or not request_key:raise StoreError('invalid')
        command=digest(dict(delivery_id=delivery_id,expected_version=expected_version,kind=kind,evidence=evidence if request_evidence is None else request_evidence,note=note,actor=actor))
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
                result['resolution']=dict(kind=kind,evidence=serial(evidence),note=note,actor=actor,request_key=request_key,recorded_at=stamp())
                c.execute('UPDATE attempts SET resolved=1,result=? WHERE id=?',(_json(result),attempt['id']))
            c.execute('UPDATE submission_permits SET invalidated=1 WHERE attempt_id IN (SELECT id FROM attempts WHERE delivery_id=?)',(delivery_id,))
            self._aggregate(c,d['run_id'])
            self._event(c,delivery_id,'resolved_'+kind,dict(evidence=evidence,note=note,actor=actor));result=self._delivery(c,delivery_id)
            c.execute('INSERT INTO runtime_requests VALUES(?,?,?)',(request_key,command,_json(result)));return result

    def requeue_delivery(self,delivery_id,expected_version,request_key,actor,*,expected_run_version,process_evidence,lock_evidence,now):
        """서버 재개 전용. 대상/회차 CAS와 이전 lease 무효화를 한 번에 기록한다."""
        expected(expected_version);expected(expected_run_version);now=utc(now)
        if not all(isinstance(value,str) and value for value in (request_key,actor)):raise StoreError('invalid')
        command=digest(dict(delivery_id=delivery_id,expected_version=expected_version,kind='retry',evidence={},note='resume existing delivery',actor=actor))
        with self._db(True) as c:
            old=c.execute('SELECT * FROM runtime_requests WHERE request_key=?',(request_key,)).fetchone()
            if old:
                if old['command_hash']!=command:raise ConflictError()
                return json.loads(old['result'])
            d=self._delivery(c,delivery_id,expected_version);run=self._run(c,d['run_id'])
            if run['version']!=expected_run_version or run['state'] not in ('running','partial','failed','waiting'):raise ConflictError()
            occurrence=run.get('occurrence') or {}
            if occurrence.get('mode')!='live' or occurrence.get('phase')!='submit':raise ConflictError()
            if not run['lease_expires_at'] or utc(run['lease_expires_at'])>now:raise ConflictError()
            identity=run.get('process_identity') or {}
            if not isinstance(process_evidence,dict) or process_evidence.get('status')!='dead' or not all(process_evidence.get(key)==identity.get(key) and identity.get(key) is not None for key in ('host_id','pid','started_at')):raise StoreError('insufficient_evidence')
            if not isinstance(lock_evidence,dict) or lock_evidence.get('status')!='free' or lock_evidence.get('connection_id')!=d['context']['connection_id']:raise StoreError('insufficient_evidence')
            if d['state']!='retry_wait' or d['remote_uncertain']:raise ConflictError()
            if c.execute('SELECT 1 FROM attempts WHERE delivery_id=? AND resolved=0 LIMIT 1',(delivery_id,)).fetchone():raise ConflictError()
            # 다른 대상의 unknown은 보존한다. 아직 raw 실행 중이면 만료 복구부터 요구한다.
            if c.execute("SELECT 1 FROM runtime_deliveries WHERE run_id=? AND state IN ('submitting','running') LIMIT 1",(d['run_id'],)).fetchone():raise ConflictError()
            attempts=[self._attempt(c,r[0]) for r in c.execute('SELECT id FROM attempts WHERE delivery_id=? ORDER BY ordinal',(delivery_id,))]
            if attempts:
                last=attempts[-1];result=last['result'] or {}
                safe=(not last['request_started'] and last['outcome']=='failed' and result.get('evidence',{}).get('confirmed_not_submitted') is True) or result.get('resolution',{}).get('kind')=='confirmed_not_posted'
                if not safe:raise ConflictError()
            approval=self._approval(c,delivery_id)
            if not approval:raise ConflictError()
            # 로컬 재개는 외부 요청 권한이 아니다. 새 worker가 잠금 아래 인증을 다시 관측한다.
            self._check_approval(c,d,d['context_hash'],approval['approval_hash'],now,require_fresh_auth=False)
            self._state(c,delivery_id,'queued')
            c.execute('UPDATE submission_permits SET invalidated=1 WHERE consumed=0 AND attempt_id IN (SELECT id FROM attempts WHERE delivery_id=?)',(delivery_id,))
            c.execute("UPDATE runtime_runs SET state='queued',version=version+1,worker_id=NULL,lease_expires_at=NULL,process_identity=NULL WHERE id=?",(d['run_id'],))
            c.execute('INSERT INTO runtime_resume_targets(run_id,delivery_id) VALUES(?,?) ON CONFLICT(run_id) DO UPDATE SET delivery_id=excluded.delivery_id',(d['run_id'],delivery_id))
            self._event(c,delivery_id,'retry_queued',dict(process=process_evidence,lock=lock_evidence,checked_at=stamp(now),actor=actor,request_key=request_key))
            result=self._delivery(c,delivery_id)
            c.execute('INSERT INTO runtime_requests VALUES(?,?,?)',(request_key,command,_json(result)))
            return result
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

    def record_content_evidence(self,content_id,revision,manifest_hash,kind,report_hash,report,*,now=None):
        """서버 검토 ingestion 전용. HTTP 입력/수동 검토 흉내를 연결하지 않는다."""
        if (kind not in ('production_provenance','independent_review') or not isinstance(report,dict) or
            type(revision) is not int or revision<1 or not isinstance(report_hash,str) or
            report_hash!=digest({k:v for k,v in report.items() if k!='report_hash'})):
            raise StoreError('invalid_content_evidence')
        with self._db(True) as c:
            row=c.execute('SELECT manifest_hash FROM revisions WHERE content_id=? AND revision=?',(content_id,revision)).fetchone()
            if not row or row[0]!=manifest_hash:raise ConflictError()
            old=c.execute('SELECT report FROM content_evidence WHERE content_id=? AND revision=? AND manifest_hash=? AND kind=? AND report_hash=?',(content_id,revision,manifest_hash,kind,report_hash)).fetchone()
            raw=_json(serial(report))
            if old and old[0]!=raw:raise ConflictError()
            if not old:c.execute('INSERT INTO content_evidence(content_id,revision,manifest_hash,kind,report_hash,report,recorded_at) VALUES(?,?,?,?,?,?,?)',(content_id,revision,manifest_hash,kind,report_hash,raw,stamp(now)))
        return dict(content_id=content_id,revision=revision,manifest_hash=manifest_hash,kind=kind,report_hash=report_hash,report=serial(report))

    def read_content_evidence(self,content_id,revision,manifest_hash):
        """누락된 이전 v3 저널도 쓰기 없이 빈 목록으로 관측한다."""
        with self._db() as c:
            if not self._v3(c) or not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='content_evidence'").fetchone():return []
            rows=c.execute('SELECT * FROM content_evidence WHERE content_id=? AND revision=? AND manifest_hash=? ORDER BY id',(content_id,revision,manifest_hash))
            return [dict(r,report=json.loads(r['report'])) for r in rows]
