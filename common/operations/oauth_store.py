"""명시 초기화하는 별도 OAuth 저장소. 비밀 원문은 받지 않는다."""
from contextlib import contextmanager, closing
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import re
import sqlite3
from uuid import uuid4
from .content_store import StoreError, ConflictError
from .oauth_models import AttemptContext, CallbackClaim, CredentialRef, validate_authorization
from .oauth_catalog import provider_catalog


def _time(value):
    try:
        result=value if isinstance(value,datetime) else datetime.fromisoformat(value)
        if result.tzinfo is None: raise ValueError()
        return result.astimezone(timezone.utc)
    except (TypeError,ValueError): raise StoreError('invalid') from None


def _ref(value):
    if not isinstance(value,CredentialRef): raise StoreError('invalid_credential_ref')
    return {key:getattr(value,key) for key in ('namespace','account_id','platform','connection_id','generation','kind')}


def _provider_platform(context):
    for provider in provider_catalog():
        if provider.id == context.provider_id:
            return provider.platform
    raise StoreError('unknown_provider')


def _validate_context_ref(context, ref):
    if (ref['account_id'] != context.account_id
            or ref['connection_id'] != context.connection_id
            or ref['platform'] != _provider_platform(context)):
        raise StoreError('credential_owner_mismatch')


def _dump(value): return json.dumps(value,separators=(',',':'),sort_keys=True,allow_nan=False)


class OAuthDatabase:
    def __init__(self,root,clock=None):
        self.root=Path(root); self.path=self.root/'oauth.sqlite3'
        self.clock=clock or (lambda:datetime.now(timezone.utc))
    def initialize(self):
        self.root.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            version=db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0,1): raise StoreError('schema_mismatch')
            db.executescript('''CREATE TABLE IF NOT EXISTS oauth_attempts (
                id TEXT PRIMARY KEY,state_hash TEXT UNIQUE NOT NULL,provider TEXT NOT NULL,
                session_binding TEXT NOT NULL,context TEXT NOT NULL,state TEXT NOT NULL,
                revision INTEGER NOT NULL,expires_at TEXT NOT NULL,payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS oauth_proposals(id TEXT PRIMARY KEY,attempt_id TEXT NOT NULL,session_binding TEXT NOT NULL,payload TEXT NOT NULL,consumed INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS oauth_connections(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS oauth_request_receipts(id TEXT PRIMARY KEY,session_binding TEXT NOT NULL,operation TEXT NOT NULL,request_key TEXT NOT NULL,request_hash TEXT NOT NULL,revision INTEGER NOT NULL,status TEXT NOT NULL,result TEXT,attempt_id TEXT,UNIQUE(session_binding,operation,request_key));
                CREATE TABLE IF NOT EXISTS oauth_generations(namespace TEXT NOT NULL,account_id TEXT NOT NULL,platform TEXT NOT NULL,connection_id TEXT NOT NULL,generation INTEGER NOT NULL,PRIMARY KEY(namespace,account_id,platform,connection_id));
                CREATE TABLE IF NOT EXISTS oauth_meta(id INTEGER PRIMARY KEY CHECK(id=1),generation INTEGER NOT NULL);
                INSERT OR IGNORE INTO oauth_meta VALUES(1,0);
                PRAGMA user_version=1;''')
    def _receipt(self,row,*,claimed=False):
        return dict(id=row['id'],revision=row['revision'],status=('claimed' if claimed else 'in_progress') if row['status']=='pending' else row['status'],result=json.loads(row['result']) if row['result'] else None)

    def claim_request(self,session_binding,operation,request_key,request_hash):
        if (not isinstance(session_binding,str) or not session_binding
                or not isinstance(operation,str) or not re.fullmatch(r'(?:start|continue|inspect|confirm|refresh|disconnect|revoke)(?::[A-Za-z0-9_.:-]{1,200})?',operation)
                or not isinstance(request_key,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}',request_key)
                or not isinstance(request_hash,str) or not re.fullmatch(r'[0-9a-f]{64}',request_hash)): raise StoreError('invalid')
        with self._db(True) as db:
            row=db.execute('SELECT * FROM oauth_request_receipts WHERE session_binding=? AND operation=? AND request_key=?',(session_binding,operation,request_key)).fetchone()
            if row:
                if row['request_hash']!=request_hash: raise ConflictError()
                return self._receipt(row)
            identifier=uuid4().hex
            db.execute('INSERT INTO oauth_request_receipts VALUES(?,?,?,?,?,1,?,NULL,NULL)',(identifier,session_binding,operation,request_key,request_hash,'pending'))
            return self._receipt(db.execute('SELECT * FROM oauth_request_receipts WHERE id=?',(identifier,)).fetchone(),claimed=True)

    def finish_request(self,identifier,expected_revision,safe_result):
        allowed={'attempt_id','revision','state','proposal_id','connection_id','base_revision','connection_revision','generation','account_id','provider_id','platform','expires_at','execution_enabled','reason_codes','provider_subject','target_proposal','authorization'}
        states={'registration_blocked','consent_pending','callback_staged','resume_pending','token_exchanged','principal_pending','target_confirmation','connected','denied','expired','error','revoked','disconnected','unknown','reauth_required'}
        if not isinstance(safe_result,dict) or set(safe_result)-allowed: raise StoreError('invalid_receipt_result')
        for key,value in safe_result.items():
            if key=='authorization':
                if value is not None: safe_result=dict(safe_result,authorization=validate_authorization(value))
            elif key in ('revision','connection_revision','generation'):
                if type(value) is not int or value<0: raise StoreError('invalid_receipt_result')
            elif key=='execution_enabled':
                if value is not False: raise StoreError('invalid_receipt_result')
            elif key=='account_id':
                if value not in ('personal','dept'): raise StoreError('invalid_receipt_result')
            elif key=='provider_id':
                if not isinstance(value,str) or value not in {p.id for p in provider_catalog()}: raise StoreError('invalid_receipt_result')
            elif key=='platform':
                if not isinstance(value,str) or value not in {p.platform for p in provider_catalog()}: raise StoreError('invalid_receipt_result')
            elif key=='expires_at':
                _time(value)
                if not isinstance(value,str): raise StoreError('invalid_receipt_result')
            elif key=='reason_codes':
                if not isinstance(value,list) or len(value)>32 or any(v not in ('stage_failed','denied','expired','storage_failed','callback_failed','exchange_failed','inspect_failed','manual_review') for v in value): raise StoreError('invalid_receipt_result')
            elif key=='target_proposal':
                fields={'proposal_id','target_id','target_label','expected_base_revision','expected_connection_revision'}
                if not isinstance(value,dict) or set(value)!=fields: raise StoreError('invalid_receipt_result')
                if type(value['expected_connection_revision']) is not int or value['expected_connection_revision']<0: raise StoreError('invalid_receipt_result')
                for field in fields-{'expected_connection_revision'}:
                    text=value[field]
                    if not isinstance(text,str) or len(text)>500 or any(ord(c)<32 for c in text) or (field!='target_label' and not text): raise StoreError('invalid_receipt_result')
            elif key=='state':
                if not isinstance(value,str) or value not in states: raise StoreError('invalid_receipt_result')
            elif not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}',value): raise StoreError('invalid_receipt_result')
        with self._db(True) as db:
            row=db.execute('SELECT * FROM oauth_request_receipts WHERE id=?',(identifier,)).fetchone()
            if row is None: raise StoreError('not_found')
            if type(expected_revision) is not int or row['revision']!=expected_revision or row['status']!='pending': raise ConflictError()
            db.execute("UPDATE oauth_request_receipts SET status='completed',revision=revision+1,result=? WHERE id=?",(_dump(safe_result),identifier))
            return self._receipt(db.execute('SELECT * FROM oauth_request_receipts WHERE id=?',(identifier,)).fetchone())

    def reserve_generation(self,namespace,account_id,platform,connection_id):
        try: CredentialRef(namespace,account_id,platform,connection_id,1,'token')
        except (TypeError,ValueError): raise StoreError('invalid_credential_ref') from None
        if platform not in {p.platform for p in provider_catalog()}: raise StoreError('unknown_provider')
        key=(namespace,account_id,platform,connection_id)
        with self._db(True) as db:
            row=db.execute('SELECT generation FROM oauth_generations WHERE namespace=? AND account_id=? AND platform=? AND connection_id=?',key).fetchone()
            maximum=row[0] if row else 0
            # Include references written before the reservation API existed.
            for table in ('oauth_attempts','oauth_connections'):
                for stored in db.execute('SELECT payload FROM '+table):
                    payload=json.loads(stored[0])
                    if (table=='oauth_connections'
                            and tuple(payload.get(k) for k in ('account_id','platform','connection_id'))==key[1:]):
                        high_water=payload.get('credential_generation')
                        if type(high_water) is int and high_water>0:
                            maximum=max(maximum,high_water)
                    for ref in payload.values():
                        if isinstance(ref,dict) and tuple(ref.get(k) for k in ('namespace','account_id','platform','connection_id'))==key:
                            maximum=max(maximum,ref['generation'])
            generation=maximum+1
            db.execute('INSERT OR REPLACE INTO oauth_generations VALUES(?,?,?,?,?)',(*key,generation))
            return generation

    @contextmanager
    def _db(self,write=False):
        if not self.path.is_file(): raise StoreError('not_initialized')
        db=sqlite3.connect(self.path.as_uri()+('?mode=rw' if write else '?mode=ro'),uri=True,timeout=10)
        db.row_factory=sqlite3.Row
        try:
            if db.execute('PRAGMA user_version').fetchone()[0]!=1: raise StoreError('schema_mismatch')
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield db
            db.commit()
        except sqlite3.Error: db.rollback(); raise StoreError('storage_unavailable') from None
        except Exception: db.rollback(); raise
        finally: db.close()


class OAuthAttemptStore(OAuthDatabase):
    def _decode(self,row):
        if row is None: raise StoreError('not_found')
        item=dict(row); item['attempt_id']=item.pop('id'); item.pop('state_hash')
        item['context']=AttemptContext(**json.loads(item['context']))
        item.update(json.loads(item.pop('payload')))
        item['authorization']=validate_authorization(item['authorization']) if item.get('authorization') is not None else None
        for field in ('code_ref','ticket_ref','verifier_ref','token_ref','state_key_ref'):
            if item.get(field): item[field]=CredentialRef(**item[field])
        return item
    def create_attempt(self,context,state_hash,expires_at):
        if not isinstance(context,AttemptContext) or context.account_id not in ('personal','dept'): raise StoreError('invalid')
        _provider_platform(context)
        if not isinstance(state_hash,str) or not re.fullmatch('[0-9a-f]{64}',state_hash): raise StoreError('invalid_state_hash')
        now=_time(self.clock()); expiry=_time(expires_at)
        if not 0<(expiry-now).total_seconds()<=600: raise StoreError('invalid_expiry')
        identifier=uuid4().hex
        with self._db(True) as db:
            db.execute('INSERT INTO oauth_attempts VALUES(?,?,?,?,?,?,?,?,?)',(identifier,state_hash,context.provider_id,context.session_binding,_dump(asdict(context)),'consent_pending',1,expiry.isoformat(),_dump({'authorization':validate_authorization(dict(observed_scopes=None,credential_expires_at=None,read_status='not_checked',publication_status='blocked',credential_status='pending'))})))
            return self._decode(db.execute('SELECT * FROM oauth_attempts WHERE id=?',(identifier,)).fetchone())
    def bind_state_key(self,attempt_id,session_binding,expected_revision,state_key_ref,request_receipt_id):
        ref=_ref(state_key_ref)
        if ref['kind']!='state_key': raise StoreError('invalid_credential_ref')
        with self._db(True) as db:
            row=db.execute('SELECT * FROM oauth_attempts WHERE id=? AND session_binding=?',(attempt_id,session_binding)).fetchone()
            item=self._decode(row)
            if type(expected_revision) is not int or item['revision']!=expected_revision or item['state']!='consent_pending': raise ConflictError()
            if _time(item['expires_at'])<=_time(self.clock()): raise StoreError('expired')
            _validate_context_ref(item['context'],ref)
            receipt=db.execute('SELECT * FROM oauth_request_receipts WHERE id=? AND session_binding=?',(request_receipt_id,session_binding)).fetchone()
            if receipt is None or receipt['operation']!='start' or receipt['status']!='pending' or receipt['attempt_id'] is not None: raise ConflictError()
            payload=json.loads(row['payload'])
            if payload.get('state_key_ref'): raise ConflictError()
            payload.update(state_key_ref=ref,request_receipt_id=request_receipt_id)
            db.execute('UPDATE oauth_request_receipts SET attempt_id=? WHERE id=?',(attempt_id,request_receipt_id))
            db.execute('UPDATE oauth_attempts SET payload=?,revision=revision+1 WHERE id=?',(_dump(payload),attempt_id))
            return self._decode(db.execute('SELECT * FROM oauth_attempts WHERE id=?',(attempt_id,)).fetchone())

    def bind_verifier(self,attempt_id,session_binding,expected_revision,verifier_ref):
        ref=_ref(verifier_ref)
        if ref['kind']!='verifier': raise StoreError('invalid_credential_ref')
        with self._db(True) as db:
            row=db.execute('SELECT * FROM oauth_attempts WHERE id=? AND session_binding=?',(attempt_id,session_binding)).fetchone()
            item=self._decode(row)
            if type(expected_revision) is not int or item['revision']!=expected_revision or item['state']!='consent_pending': raise ConflictError()
            if _time(item['expires_at'])<=_time(self.clock()): raise StoreError('expired')
            _validate_context_ref(item['context'],ref)
            payload=json.loads(row['payload'])
            if payload.get('verifier_ref'): raise ConflictError()
            payload['verifier_ref']=ref
            db.execute('UPDATE oauth_attempts SET payload=?,revision=revision+1 WHERE id=?',(_dump(payload),attempt_id))
            return self._decode(db.execute('SELECT * FROM oauth_attempts WHERE id=?',(attempt_id,)).fetchone())

    def claim_callback(self,state_hash,provider):
        with self._db(True) as db:
            row=db.execute('SELECT * FROM oauth_attempts WHERE state_hash=? AND provider=?',(state_hash,provider)).fetchone()
            if row is None or row['state']!='consent_pending': raise ConflictError()
            if _time(row['expires_at'])<=_time(self.clock()): raise StoreError('expired')
            rev=row['revision']+1
            db.execute("UPDATE oauth_attempts SET state='callback_receiving',revision=? WHERE id=?",(rev,row['id']))
            return CallbackClaim(row['id'],rev,row['expires_at'],self._decode(row)['context'])
    def _claim_row(self,db,claim):
        row=db.execute('SELECT * FROM oauth_attempts WHERE id=?',(claim.attempt_id,)).fetchone()
        if row is None or row['revision']!=claim.lease_revision or row['state']!='callback_receiving': raise ConflictError()
        if self._decode(row)['context']!=claim.context: raise ConflictError()
        return row
    def finalize_callback(self,claim,code_ref,ticket_ref,expires_at):
        with self._db(True) as db:
            row=self._claim_row(db,claim); now=_time(self.clock()); expiry=_time(expires_at)
            if not now<expiry<=min(_time(row['expires_at']),now+timedelta(seconds=120)): raise StoreError('expired')
            refs={'code_ref':_ref(code_ref),'ticket_ref':_ref(ticket_ref),'ticket_expires_at':expiry.isoformat()}
            for name,kind in (('code_ref','code'),('ticket_ref','ticket')):
                ref=refs[name]; context=claim.context
                if ref['kind']!=kind: raise StoreError('credential_owner_mismatch')
                _validate_context_ref(context,ref)
            payload=json.loads(row['payload']); payload.update(refs)
            db.execute("UPDATE oauth_attempts SET state='callback_staged',revision=revision+1,payload=? WHERE id=?",(_dump(payload),claim.attempt_id))
            return self._decode(db.execute('SELECT * FROM oauth_attempts WHERE id=?',(claim.attempt_id,)).fetchone())
    def fail_callback(self,claim,reason):
        with self._db(True) as db:
            self._claim_row(db,claim)
            # Arbitrary exception strings can contain secrets; only fixed local reasons persist.
            reason=reason if reason in ('stage_failed','denied','expired','storage_failed') else 'callback_failed'
            db.execute("UPDATE oauth_attempts SET state='error',revision=revision+1,payload=? WHERE id=?",(_dump({'reason':reason}),claim.attempt_id))
    def read_owned(self,attempt_id,session_binding):
        with self._db() as db:
            return self._decode(db.execute('SELECT * FROM oauth_attempts WHERE id=? AND session_binding=?',(attempt_id,session_binding)).fetchone())
    def list_owned(self,session_binding):
        if not self.path.is_file(): return []
        with self._db() as db:
            return [self._decode(row) for row in db.execute('SELECT * FROM oauth_attempts WHERE session_binding=? ORDER BY id',(session_binding,))]
    def claim_resume(self,attempt_id,session_binding,expected_revision):
        if type(expected_revision) is not int or expected_revision<1: raise StoreError('invalid')
        with self._db(True) as db:
            row=db.execute('SELECT * FROM oauth_attempts WHERE id=? AND session_binding=?',(attempt_id,session_binding)).fetchone()
            item=self._decode(row)
            if item['revision']!=expected_revision or item['state']!='callback_staged': raise ConflictError()
            if min(_time(item['expires_at']),_time(item['ticket_expires_at']))<=_time(self.clock()): raise StoreError('expired')
            db.execute("UPDATE oauth_attempts SET state='resume_pending',revision=revision+1 WHERE id=?",(attempt_id,))
            return self._decode(db.execute('SELECT * FROM oauth_attempts WHERE id=?',(attempt_id,)).fetchone())

    def update_attempt(self,attempt_id,session_binding,expected_revision,state,payload):
        if type(expected_revision) is not int or expected_revision<1: raise StoreError('invalid')
        transitions={'resume_pending':{'token_exchanged','unknown','error'},'token_exchanged':{'principal_pending','target_confirmation','error','unknown'},'principal_pending':{'target_confirmation','error','unknown'},'target_confirmation':{'connected','error'}}
        allowed={'token_ref','verifier_ref','reason','authorization'}
        if not isinstance(payload,dict) or set(payload)-allowed: raise StoreError('invalid')
        clean={}
        for key,value in payload.items():
            if key=='authorization': clean[key]=validate_authorization(value) if value is not None else None
            elif key.endswith('_ref'):
                clean[key]=_ref(value)
                if clean[key]['kind']!=key.removesuffix('_ref'): raise StoreError('invalid_credential_ref')
            elif value in ('exchange_failed','inspect_failed','storage_failed','manual_review'): clean[key]=value
            else: raise StoreError('invalid')
        with self._db(True) as db:
            row=db.execute('SELECT * FROM oauth_attempts WHERE id=? AND session_binding=?',(attempt_id,session_binding)).fetchone()
            item=self._decode(row)
            if item['revision']!=expected_revision or state not in transitions.get(item['state'],set()): raise ConflictError()
            old=json.loads(row['payload'])
            for key,value in clean.items():
                if key.endswith('_ref'): _validate_context_ref(item['context'],value)
            old.update(clean)
            db.execute('UPDATE oauth_attempts SET state=?,revision=revision+1,payload=? WHERE id=?',(state,_dump(old),attempt_id))
            return self._decode(db.execute('SELECT * FROM oauth_attempts WHERE id=?',(attempt_id,)).fetchone())
