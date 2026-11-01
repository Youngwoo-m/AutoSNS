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
from .oauth_models import AttemptContext, CallbackClaim, CredentialRef


def _time(value):
    try:
        result=value if isinstance(value,datetime) else datetime.fromisoformat(value)
        if result.tzinfo is None: raise ValueError()
        return result.astimezone(timezone.utc)
    except (TypeError,ValueError): raise StoreError('invalid') from None


def _ref(value):
    if not isinstance(value,CredentialRef): raise StoreError('invalid_credential_ref')
    return {key:getattr(value,key) for key in ('namespace','account_id','platform','connection_id','generation','kind')}


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
                CREATE TABLE IF NOT EXISTS oauth_meta(id INTEGER PRIMARY KEY CHECK(id=1),generation INTEGER NOT NULL);
                INSERT OR IGNORE INTO oauth_meta VALUES(1,0);
                PRAGMA user_version=1;''')
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
        for field in ('code_ref','ticket_ref','verifier_ref','token_ref'):
            if item.get(field): item[field]=CredentialRef(**item[field])
        return item
    def create_attempt(self,context,state_hash,expires_at):
        if not isinstance(context,AttemptContext) or context.account_id not in ('personal','dept'): raise StoreError('invalid')
        if not isinstance(state_hash,str) or not re.fullmatch('[0-9a-f]{64}',state_hash): raise StoreError('invalid_state_hash')
        now=_time(self.clock()); expiry=_time(expires_at)
        if not 0<(expiry-now).total_seconds()<=600: raise StoreError('invalid_expiry')
        identifier=uuid4().hex
        with self._db(True) as db:
            db.execute('INSERT INTO oauth_attempts VALUES(?,?,?,?,?,?,?,?,?)',(identifier,state_hash,context.provider_id,context.session_binding,_dump(asdict(context)),'consent_pending',1,expiry.isoformat(),'{}'))
            return self._decode(db.execute('SELECT * FROM oauth_attempts WHERE id=?',(identifier,)).fetchone())
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
                if ref['kind']!=kind or ref['account_id']!=context.account_id or ref['connection_id']!=context.connection_id: raise StoreError('credential_owner_mismatch')
            db.execute("UPDATE oauth_attempts SET state='callback_staged',revision=revision+1,payload=? WHERE id=?",(_dump(refs),claim.attempt_id))
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
        allowed={'token_ref','verifier_ref','reason'}
        if not isinstance(payload,dict) or set(payload)-allowed: raise StoreError('invalid')
        clean={}
        for key,value in payload.items():
            if key.endswith('_ref'):
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
                if key.endswith('_ref') and (value['account_id']!=item['context'].account_id or value['connection_id']!=item['context'].connection_id): raise StoreError('credential_owner_mismatch')
            old.update(clean)
            db.execute('UPDATE oauth_attempts SET state=?,revision=revision+1,payload=? WHERE id=?',(state,_dump(old),attempt_id))
            return self._decode(db.execute('SELECT * FROM oauth_attempts WHERE id=?',(attempt_id,)).fetchone())
