"""Owned OAuth의 명시 migration, durable journal, operation 및 보수적 graph.

이 모듈은 vault에 접근하지 않는다. intent를 별도 commit한 뒤 호출자가 put하고
stored를 기록한다. remote in_flight도 실제 provider 호출보다 먼저 commit한다.
"""
from dataclasses import dataclass
from pathlib import Path
import json
import re
import sqlite3
from types import MappingProxyType
from uuid import uuid4

from .content_store import StoreError, ConflictError
from .credential_backend import CredentialError
from .oauth_models import AttemptContext, validate_authorization
from .oauth_stage_models import WorkspaceOwner, OwnedCredentialRef, encode_stored_ref, decode_stored_ref, logical_ref
from .oauth_store import OAuthDatabase, _dump, _time, _validate_context_ref, _validate_receipt_result, _provider_platform
from .oauth_workspace import validate_workspace_context, load_workspace_owner


_OPERATION_KINDS={'start','callback','continue','inspect','confirm','refresh','disconnect','revoke'}
_REMOTE={'local_only','not_started','in_flight','returned','unknown'}
_OUTCOMES={'pending','referenced','unused','unknown'}
_STAGE_STATES={'intent','stored','referenced','preserved','deleted'}
_EVENT_CODES={'delete_intent','deleted','absent','denied','locked','unavailable','integrity_failed','referenced','pending','unknown','manual_review'}
_ATTEMPT_FIELDS={'authorization','code_ref','ticket_ref','verifier_ref','token_ref','state_key_ref','ticket_expires_at','request_receipt_id','reason','operation_id','payload_version'}
_PROPOSAL_FIELDS={'connection_id','account_id','platform','base_revision','target_id','target_label','provider_subject','credential_ref','scopes','checked_at','authorization','operation_id','payload_version'}
_CONNECTION_FIELDS=_PROPOSAL_FIELDS|{'provider_id','credential_generation','revision','state','execution_enabled','operation_lease'}
_LEASE_FIELDS={'lease_id','operation','provider_id','connection_id','base_revision','connection_revision','credential_ref','credential_generation','account_id','platform','operation_id','new_ref','payload_version'}
_EXPECTED_COLUMNS={
    'oauth_attempts': 'id state_hash provider session_binding context state revision expires_at payload',
    'oauth_proposals': 'id attempt_id session_binding payload consumed',
    'oauth_connections': 'id payload',
    'oauth_request_receipts': 'id session_binding operation request_key request_hash revision status result attempt_id operation_id',
    'oauth_generations': 'namespace account_id platform connection_id generation',
    'oauth_meta': 'id generation',
    'oauth_workspace_meta': 'id format_version workspace_id root_binding canonical_root',
    'oauth_graph_meta': 'id graph_revision journal_revision',
    'oauth_operations': 'operation_id kind remote_state outcome revision receipt_id payload_version',
    'oauth_stages': 'stage_id owned_ref operation_id state revision graph_revision reason_code payload_version',
    'oauth_recovery_events': 'event_id stage_id code stage_revision payload_version',
}



class _PrivateRecord:
    def __repr__(self): return type(self).__name__+'(<private>)'
    def to_dict(self,*,public=True):
        if not public: raise StoreError('private_serialization_forbidden')
        return {}


@dataclass(frozen=True,repr=False)
class StageRecord(_PrivateRecord):
    stage_id: str
    owned_ref: OwnedCredentialRef
    operation_id: str
    state: str
    revision: int
    graph_revision: int | None
    reason_code: str | None


@dataclass(frozen=True,repr=False)
class OperationRecord(_PrivateRecord):
    operation_id: str
    kind: str
    remote_state: str
    outcome: str
    revision: int
    receipt_id: str | None


@dataclass(frozen=True,repr=False)
class RecoverySnapshot(_PrivateRecord):
    journal_revision: int
    stages: tuple
    protected_refs: frozenset
    blockers: tuple
    graph_revision: int
    operations: object
    operation_stages: object
    pending_receipts: frozenset
    legacy_protected: frozenset


def _owner_ref(owner,ref):
    if type(owner) is not WorkspaceOwner or type(ref) is not OwnedCredentialRef or (ref.workspace_id,ref.root_binding)!=(owner.workspace_id,owner.root_binding):
        raise StoreError('credential_owner_mismatch')


def validate_database_owner(db,root,provided_owner=None):
    """schema2 DB copy/rebinding을 거부한다. marker 읽기만 수행한다."""
    row=db.execute('SELECT * FROM oauth_workspace_meta WHERE id=1').fetchone()
    try:
        if row is None: raise ValueError()
        _row_texts(row,('workspace_id','root_binding','canonical_root'))
        owner=WorkspaceOwner(row['workspace_id'],row['root_binding'],row['format_version'])
        current=load_workspace_owner(root)
        if (current.root!=Path(row['canonical_root']) or current.owner!=owner
                or (provided_owner is not None and provided_owner!=owner)): raise ValueError()
        return owner
    except (ValueError,TypeError,KeyError,IndexError,RecursionError,CredentialError):
        raise StoreError('credential_owner_mismatch') from None


def migrate_to_owned_schema(context):
    """기존 명시 schema1 초기화 뒤에만 실행한다. 전체 DDL은 한 transaction이다."""
    context=validate_workspace_context(context)
    from .oauth_workspace import require_oauth_write_guard
    require_oauth_write_guard(context.root,context.owner)
    path=context.root/'oauth.sqlite3'
    if not path.is_file(): raise StoreError('not_initialized')
    db=sqlite3.connect(path.as_uri()+'?mode=rw',uri=True); db.row_factory=sqlite3.Row
    try:
        db.execute('BEGIN IMMEDIATE')
        version=db.execute('PRAGMA user_version').fetchone()[0]
        if version==2:
            validate_database_owner(db,context.root,context.owner); db.commit(); return
        if version!=1: raise StoreError('schema_mismatch')
        statements=[
            'CREATE TABLE oauth_workspace_meta(id INTEGER PRIMARY KEY CHECK(id=1),format_version INTEGER NOT NULL,workspace_id TEXT NOT NULL,root_binding TEXT NOT NULL,canonical_root TEXT NOT NULL)',
            'CREATE TABLE oauth_graph_meta(id INTEGER PRIMARY KEY CHECK(id=1),graph_revision INTEGER NOT NULL,journal_revision INTEGER NOT NULL)',
            "CREATE TABLE oauth_operations(operation_id TEXT PRIMARY KEY,kind TEXT NOT NULL,remote_state TEXT NOT NULL,outcome TEXT NOT NULL,revision INTEGER NOT NULL,receipt_id TEXT REFERENCES oauth_request_receipts(id),payload_version INTEGER NOT NULL DEFAULT 1)",
            "CREATE TABLE oauth_stages(stage_id TEXT PRIMARY KEY,owned_ref TEXT NOT NULL UNIQUE,operation_id TEXT NOT NULL REFERENCES oauth_operations(operation_id),state TEXT NOT NULL,revision INTEGER NOT NULL,graph_revision INTEGER,reason_code TEXT,payload_version INTEGER NOT NULL DEFAULT 1)",
            'CREATE TABLE oauth_recovery_events(event_id TEXT PRIMARY KEY,stage_id TEXT NOT NULL REFERENCES oauth_stages(stage_id),code TEXT NOT NULL,stage_revision INTEGER NOT NULL,payload_version INTEGER NOT NULL DEFAULT 1,UNIQUE(stage_id,stage_revision,code))',
            'ALTER TABLE oauth_request_receipts ADD COLUMN operation_id TEXT REFERENCES oauth_operations(operation_id)',
        ]
        for statement in statements: db.execute(statement)
        owner=context.owner
        db.execute('INSERT INTO oauth_workspace_meta VALUES(1,?,?,?,?)',(owner.format_version,owner.workspace_id,owner.root_binding,str(context.root)))
        db.execute('INSERT INTO oauth_graph_meta VALUES(1,0,0)')
        for table in ('oauth_attempts','oauth_proposals','oauth_connections','oauth_request_receipts','oauth_generations','oauth_meta','oauth_operations','oauth_stages','oauth_recovery_events'):
            for event in ('INSERT','UPDATE','DELETE'):
                journal=',journal_revision=journal_revision+1' if table in ('oauth_stages','oauth_recovery_events') else ''
                db.execute(f'CREATE TRIGGER {table}_{event.lower()}_graph AFTER {event} ON {table} BEGIN UPDATE oauth_graph_meta SET graph_revision=graph_revision+1{journal} WHERE id=1; END')
        db.execute('PRAGMA user_version=2'); db.commit()
    except sqlite3.Error:
        db.rollback(); raise StoreError('storage_unavailable') from None
    except Exception:
        db.rollback(); raise
    finally: db.close()


def _walk_refs(value):
    if isinstance(value,dict):
        if 'namespace' in value or 'format' in value:
            yield decode_stored_ref(value)
        else:
            for nested in value.values(): yield from _walk_refs(nested)
    elif isinstance(value,list):
        for nested in value: yield from _walk_refs(nested)


def validate_owned_pointers(db,owner):
    """UOW commit 전 소유·journal 일치 검증 및 referenced 전환을 함께 수행한다."""
    for table in ('oauth_attempts','oauth_proposals','oauth_connections'):
        for row in db.execute('SELECT payload FROM '+table).fetchall():
            try: refs=tuple(_walk_refs(json.loads(row[0])))
            except (ValueError,TypeError,RecursionError,CredentialError): raise StoreError('invalid_credential_ref') from None
            for ref in refs:
                if not isinstance(ref,OwnedCredentialRef): continue
                _owner_ref(owner,ref)
                stage=db.execute('SELECT * FROM oauth_stages WHERE stage_id=?',(ref.stage_id,)).fetchone()
                if stage is None or stage['owned_ref']!=_dump(encode_stored_ref(ref)) or stage['state'] in ('intent','deleted'):
                    raise StoreError('credential_stage_mismatch')
                if stage['state']!='referenced':
                    graph=db.execute('SELECT graph_revision FROM oauth_graph_meta WHERE id=1').fetchone()[0]
                    db.execute("UPDATE oauth_stages SET state='referenced',revision=revision+1,graph_revision=?,reason_code=NULL WHERE stage_id=?",(graph,ref.stage_id))


class OAuthStageStore(OAuthDatabase):
    def __init__(self,context,clock=None):
        self.context=context
        super().__init__(context.root,clock)

    def _check_owner(self,db,owner=None):
        validate_workspace_context(self.context)
        return validate_database_owner(db,self.root,owner or self.context.owner)

    def _stage(self,row):
        if row is None: raise StoreError('not_found')
        _row_texts(row,('stage_id','owned_ref','operation_id','state'),nullable=('reason_code',))
        if (type(row['payload_version']) is not int or row['payload_version']!=1 or row['state'] not in _STAGE_STATES
                or type(row['revision']) is not int or row['revision']<1
                or (row['graph_revision'] is not None and (type(row['graph_revision']) is not int or row['graph_revision']<0))
                or (row['reason_code'] is not None and row['reason_code'] not in _EVENT_CODES)): raise StoreError('schema_mismatch')
        ref=decode_stored_ref(_json(row['owned_ref']))
        _owner_ref(self.context.owner,ref)
        if ref.stage_id!=row['stage_id']: raise StoreError('credential_stage_mismatch')
        return StageRecord(row['stage_id'],ref,row['operation_id'],row['state'],row['revision'],row['graph_revision'],row['reason_code'])

    def _operation(self,row):
        if row is None: raise StoreError('not_found')
        _row_texts(row,('operation_id','kind','remote_state','outcome'),nullable=('receipt_id',))
        if (type(row['payload_version']) is not int or row['payload_version']!=1 or row['kind'] not in _OPERATION_KINDS
                or row['remote_state'] not in _REMOTE or row['outcome'] not in _OUTCOMES
                or type(row['revision']) is not int or row['revision']<1
                or (row['remote_state']=='in_flight' and row['outcome']!='pending')
                or ((row['remote_state']=='unknown')!=(row['outcome']=='unknown'))): raise StoreError('schema_mismatch')
        return OperationRecord(row['operation_id'],row['kind'],row['remote_state'],row['outcome'],row['revision'],row['receipt_id'])

    def begin_operation(self,kind,*,receipt_id=None,local_only=False,operation_id=None):
        if kind not in _OPERATION_KINDS or type(local_only) is not bool: raise StoreError('invalid')
        identifier=operation_id or uuid4().hex
        if type(identifier) is not str or not identifier or len(identifier)>200: raise StoreError('invalid')
        with self._db(True) as db:
            self._check_owner(db)
            if receipt_id is not None:
                receipt=db.execute('SELECT * FROM oauth_request_receipts WHERE id=?',(receipt_id,)).fetchone()
                if receipt is None or receipt['operation_id'] is not None or receipt['operation'].split(':')[0]!=kind or receipt['status']!='pending': raise ConflictError()
            db.execute('INSERT INTO oauth_operations VALUES(?,?,?,?,1,?,1)',(identifier,kind,'local_only' if local_only else 'not_started','pending',receipt_id))
            if receipt_id: db.execute('UPDATE oauth_request_receipts SET operation_id=? WHERE id=?',(identifier,receipt_id))
            return self._operation(db.execute('SELECT * FROM oauth_operations WHERE operation_id=?',(identifier,)).fetchone())

    def read_operation(self,operation_id):
        with self._db() as db:
            self._check_owner(db)
            return self._operation(db.execute('SELECT * FROM oauth_operations WHERE operation_id=?',(operation_id,)).fetchone())

    def _transition_operation(self,identifier,expected_revision,remote,outcome,allowed):
        with self._db(True) as db:
            self._check_owner(db)
            old=self._operation(db.execute('SELECT * FROM oauth_operations WHERE operation_id=?',(identifier,)).fetchone())
            if type(expected_revision) is not int or old.revision!=expected_revision or (old.remote_state,old.outcome) not in allowed: raise ConflictError()
            db.execute('UPDATE oauth_operations SET remote_state=?,outcome=?,revision=revision+1 WHERE operation_id=?',(remote or old.remote_state,outcome or old.outcome,identifier))
            return self._operation(db.execute('SELECT * FROM oauth_operations WHERE operation_id=?',(identifier,)).fetchone())

    def mark_remote_in_flight(self,operation_id,expected_revision):
        return self._transition_operation(operation_id,expected_revision,'in_flight',None,{('not_started','pending')})

    def mark_remote_returned(self,operation_id,expected_revision):
        return self._transition_operation(operation_id,expected_revision,'returned',None,{('in_flight','pending')})

    def mark_operation_unknown(self,operation_id,expected_revision):
        return self._transition_operation(operation_id,expected_revision,'unknown','unknown',{('in_flight','pending'),('returned','pending'),('not_started','pending')})

    def finish_operation(self,operation_id,expected_revision,outcome):
        if outcome not in ('referenced','unused'): raise StoreError('invalid')
        return self._transition_operation(operation_id,expected_revision,None,outcome,{('local_only','pending'),('not_started','pending'),('returned','pending')})

    def begin_stage(self,owner,owned_ref,operation_id,expected_revision):
        _owner_ref(owner,owned_ref)
        if type(expected_revision) is not int or expected_revision!=0: raise ConflictError()
        with self._db(True) as db:
            self._check_owner(db,owner)
            op=self._operation(db.execute('SELECT * FROM oauth_operations WHERE operation_id=?',(operation_id,)).fetchone())
            if op.outcome!='pending': raise ConflictError()
            if db.execute('SELECT 1 FROM oauth_stages WHERE stage_id=?',(owned_ref.stage_id,)).fetchone(): raise ConflictError()
            db.execute('INSERT INTO oauth_stages VALUES(?,?,?,\'intent\',1,NULL,NULL,1)',(owned_ref.stage_id,_dump(encode_stored_ref(owned_ref)),operation_id))
            return self._stage(db.execute('SELECT * FROM oauth_stages WHERE stage_id=?',(owned_ref.stage_id,)).fetchone())

    def _transition_stage(self,stage_id,expected_revision,state,allowed,*,graph_revision=None,reason_code=None):
        with self._db(True) as db:
            self._check_owner(db)
            old=self._stage(db.execute('SELECT * FROM oauth_stages WHERE stage_id=?',(stage_id,)).fetchone())
            if type(expected_revision) is not int or old.revision!=expected_revision or old.state not in allowed: raise ConflictError()
            if graph_revision is not None and (type(graph_revision) is not int or graph_revision!=db.execute('SELECT graph_revision FROM oauth_graph_meta WHERE id=1').fetchone()[0]): raise ConflictError()
            db.execute('UPDATE oauth_stages SET state=?,revision=revision+1,graph_revision=?,reason_code=? WHERE stage_id=?',(state,graph_revision,reason_code,stage_id))
            return self._stage(db.execute('SELECT * FROM oauth_stages WHERE stage_id=?',(stage_id,)).fetchone())

    def mark_stored(self,stage_id,expected_revision):
        return self._transition_stage(stage_id,expected_revision,'stored',{'intent'})

    def mark_referenced(self,stage_id,expected_revision,graph_revision):
        return self._transition_stage(stage_id,expected_revision,'referenced',{'stored','preserved'},graph_revision=graph_revision)

    def mark_preserved(self,stage_id,expected_revision,reason_code):
        if reason_code not in _EVENT_CODES-{'delete_intent','deleted'}: raise StoreError('invalid')
        return self._transition_stage(stage_id,expected_revision,'preserved',{'intent','stored','preserved'},reason_code=reason_code)

    def record_recovery_event(self,stage_id,expected_revision,code):
        if code not in _EVENT_CODES: raise StoreError('invalid')
        with self._db(True) as db:
            self._check_owner(db)
            stage=self._stage(db.execute('SELECT * FROM oauth_stages WHERE stage_id=?',(stage_id,)).fetchone())
            if type(expected_revision) is not int or stage.revision!=expected_revision: raise ConflictError()
            if code=='delete_intent': self._require_unused(db,stage)
            existing=db.execute('SELECT event_id FROM oauth_recovery_events WHERE stage_id=? AND stage_revision=? AND code=?',(stage_id,expected_revision,code)).fetchone()
            if existing: return existing['event_id']
            identifier=uuid4().hex
            db.execute('INSERT INTO oauth_recovery_events VALUES(?,?,?,?,1)',(identifier,stage_id,code,expected_revision))
            return identifier

    def mark_deleted(self,stage_id,expected_revision):
        # Cleanup must also prove current graph safety before vault delete; this CAS
        # records completion only after an explicit delete_intent for this revision.
        with self._db(True) as db:
            self._check_owner(db)
            stage=self._stage(db.execute('SELECT * FROM oauth_stages WHERE stage_id=?',(stage_id,)).fetchone())
            if type(expected_revision) is not int or stage.revision!=expected_revision or stage.state not in ('intent','stored','preserved'): raise ConflictError()
            self._require_unused(db,stage)
            if not db.execute("SELECT 1 FROM oauth_recovery_events WHERE stage_id=? AND stage_revision=? AND code='delete_intent'",(stage_id,expected_revision)).fetchone(): raise ConflictError()
            db.execute("UPDATE oauth_stages SET state='deleted',revision=revision+1 WHERE stage_id=?",(stage_id,))
            return self._stage(db.execute('SELECT * FROM oauth_stages WHERE stage_id=?',(stage_id,)).fetchone())

    def _require_unused(self,db,stage):
        graph=_snapshot(self,db,self.context.owner)
        op=graph.operations.get(stage.operation_id)
        if (stage.state not in ('intent','stored','preserved') or graph.blockers or stage.owned_ref in graph.protected_refs or op is None
                or op.outcome!='unused' or op.remote_state not in ('local_only','not_started','returned')): raise ConflictError()

    def bind_operation(self,target_type,target_id,operation_id,expected_revision=None):
        """실 operation을 결속하고 caller가 CAS에 재사용할 갱신 target을 반환한다.

        attempt revision은 +1, lease connection revision은 유지한다. proposal은
        consumed(0)을 CAS 값으로 쓴다. receipt 수동 결속은 receipt/op revision +1.
        """
        tables={'attempt':'oauth_attempts','proposal':'oauth_proposals','receipt':'oauth_request_receipts','lease':'oauth_connections'}
        if target_type not in tables: raise StoreError('invalid')
        with self._db(True) as db:
            self._check_owner(db)
            op=self._operation(db.execute('SELECT * FROM oauth_operations WHERE operation_id=?',(operation_id,)).fetchone())
            row=db.execute('SELECT * FROM '+tables[target_type]+' WHERE id=?',(target_id,)).fetchone()
            if row is None: raise StoreError('not_found')
            if op.outcome!='pending': raise ConflictError()
            if target_type=='receipt':
                if expected_revision is not None and (type(expected_revision) is not int or row['revision']!=expected_revision): raise ConflictError()
                if row['operation_id'] is not None or op.receipt_id is not None or row['operation'].split(':')[0]!=op.kind or row['status']!='pending': raise ConflictError()
                db.execute('UPDATE oauth_request_receipts SET operation_id=?,revision=revision+1 WHERE id=?',(operation_id,target_id))
                db.execute('UPDATE oauth_operations SET receipt_id=?,revision=revision+1 WHERE operation_id=?',(target_id,operation_id))
                return self._receipt(db.execute('SELECT * FROM oauth_request_receipts WHERE id=?',(target_id,)).fetchone())
            payload=_json(row['payload']); target=payload.get('operation_lease') if target_type=='lease' else payload
            revision=row['revision'] if target_type=='attempt' else payload.get('revision') if target_type=='lease' else row['consumed']
            if expected_revision is not None and (type(expected_revision) is not int or revision!=expected_revision): raise ConflictError()
            if not isinstance(target,dict) or target.get('operation_id') is not None or (target_type=='proposal' and row['consumed']): raise ConflictError()
            if target_type=='lease' and op.kind!=target.get('operation'): raise ConflictError()
            target['operation_id']=operation_id
            revision_sql=',revision=revision+1' if target_type=='attempt' else ''
            db.execute('UPDATE '+tables[target_type]+' SET payload=?'+revision_sql+' WHERE id=?',(_dump(payload),target_id))
            if target_type=='attempt':
                from .oauth_store import OAuthAttemptStore
                return OAuthAttemptStore(self.root,self.clock)._decode(db.execute('SELECT * FROM oauth_attempts WHERE id=?',(target_id,)).fetchone())
            from .models import freeze
            if target_type=='lease':
                lease=dict(target,credential_ref=self._decode_stored_ref(target['credential_ref']))
                if lease.get('new_ref') is not None: lease['new_ref']=self._decode_stored_ref(lease['new_ref'])
                return freeze(lease)
            return freeze(dict(payload,credential_ref=self._decode_stored_ref(payload['credential_ref']),proposal_id=target_id,session_binding=row['session_binding'],attempt_id=row['attempt_id'],consumed=False))

    def recovery_snapshot(self,owner):
        with self._db() as db:
            self._check_owner(db,owner)
            return _snapshot(self,db,owner)


def _json(value):
    def unique(pairs):
        result={}
        for key,item in pairs:
            if key in result: raise ValueError()
            result[key]=item
        return result
    return json.loads(value,object_pairs_hook=unique,parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))


def _text(value,*,empty=False):
    if type(value) is not str or (not empty and not value) or any(ord(c)<32 for c in value): raise ValueError()


def _row_texts(row,required,*,nullable=()):
    for field in required: _text(row[field])
    for field in nullable:
        if row[field] is not None: _text(row[field])


def _positive(value,minimum=1):
    if type(value) is not int or value<minimum: raise ValueError()


def _payload(raw,allowed):
    """Version1의 모든 slot을 검사한다. 허용 이름도 임의 container는 받지 않는다."""
    value=_json(raw)
    proposal_required={'connection_id','account_id','platform','base_revision','target_id','provider_subject','credential_ref','scopes','checked_at'}
    required=(proposal_required|{'provider_id','credential_generation','revision','state','execution_enabled'} if allowed is _CONNECTION_FIELDS
              else proposal_required if allowed is _PROPOSAL_FIELDS
              else _LEASE_FIELDS-{'operation_id','new_ref','payload_version'} if allowed is _LEASE_FIELDS else set())
    if type(value) is not dict or set(value)-allowed or not required<=set(value): raise ValueError()
    text_fields={'connection_id','account_id','platform','base_revision','target_id','target_label','provider_subject','checked_at','provider_id','operation_id','ticket_expires_at','request_receipt_id','reason','state','lease_id','operation'}
    ref_fields={'code_ref','ticket_ref','verifier_ref','token_ref','state_key_ref','credential_ref','new_ref'}
    for field,item in value.items():
        if field in text_fields: _text(item,empty=field=='target_label')
        elif field in ('revision','credential_generation','connection_revision'): _positive(item)
        elif field=='payload_version':
            if type(item) is not int or item!=1: raise ValueError()
        elif field=='execution_enabled':
            if item is not False: raise ValueError()
        elif field=='scopes':
            if type(item) is not list or any(type(scope) is not str for scope in item): raise ValueError()
        elif field=='authorization':
            if item is not None: validate_authorization(item)
        elif field=='operation_lease':
            if item is not None:
                if type(item) is not dict: raise ValueError()
                _payload(_dump(item),_LEASE_FIELDS)
        elif field in ref_fields:
            if item is not None or not (allowed is _CONNECTION_FIELDS and field=='credential_ref'):
                decode_stored_ref(item)
        else: raise ValueError()
    if 'ticket_expires_at' in value: _time(value['ticket_expires_at'])
    return value


def _snapshot(store,db,owner):
    blockers=set(); protected=set(); legacy=set(); operations={}; stages=[]; operation_stages={}; pending=set()
    # All queries below share the read transaction opened by OAuthDatabase._db.
    known={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'oauth_%'")}
    if not set(_EXPECTED_COLUMNS)<=known:
        return RecoverySnapshot(0,(),frozenset(),('missing_table',),0,MappingProxyType({}),MappingProxyType({}),frozenset(),frozenset())
    if known!=set(_EXPECTED_COLUMNS): blockers.add('unknown_table')
    for table,columns in _EXPECTED_COLUMNS.items():
        if {row[1] for row in db.execute('PRAGMA table_info('+table+')')}!=set(columns.split()):
            return RecoverySnapshot(0,(),frozenset(),('unknown_columns',),0,MappingProxyType({}),MappingProxyType({}),frozenset(),frozenset())
    meta=db.execute('SELECT * FROM oauth_graph_meta WHERE id=1').fetchone()
    if meta is None or any(type(meta[k]) is not int or meta[k]<0 for k in ('graph_revision','journal_revision')):
        return RecoverySnapshot(0,(),frozenset(),('invalid_graph_meta',),0,MappingProxyType({}),MappingProxyType({}),frozenset(),frozenset())
    tables={name:[dict(row) for row in db.execute('SELECT * FROM '+name)] for name in ('oauth_operations','oauth_stages','oauth_attempts','oauth_proposals','oauth_connections','oauth_request_receipts','oauth_recovery_events','oauth_generations','oauth_meta')}
    for row in tables['oauth_operations']:
        try: operations[row['operation_id']]=store._operation(row)
        except (StoreError,CredentialError,ValueError,TypeError): blockers.add('invalid_operation')
    for row in tables['oauth_stages']:
        try:
            stage=store._stage(row); stages.append(stage)
            if stage.operation_id not in operations: blockers.add('dangling_operation')
            operation_stages.setdefault(stage.operation_id,set()).add(stage.owned_ref)
        except (StoreError,CredentialError,ValueError,TypeError,RecursionError): blockers.add('invalid_stage')
    stage_by_ref={stage.owned_ref:stage for stage in stages}
    def add_ref(raw,kind=None,context=None,payload=None):
        ref=decode_stored_ref(raw); logical=logical_ref(ref)
        if kind is not None and logical.kind!=kind: raise ValueError()
        if context is not None: _validate_context_ref(context,raw)
        if payload is not None and any(getattr(logical,k)!=payload[k] for k in ('account_id','platform','connection_id')): raise ValueError()
        if isinstance(ref,OwnedCredentialRef):
            _owner_ref(owner,ref)
            if ref not in stage_by_ref or stage_by_ref[ref].state in ('intent','deleted'): blockers.add('dangling_stage')
        else: legacy.add(ref)
        protected.add(ref)
        return ref
    def edge_op(payload):
        identifier=payload.get('operation_id')
        if identifier is not None and identifier not in operations: blockers.add('dangling_operation')
        return identifier
    attempts={}; receipts={row['id']:row for row in tables['oauth_request_receipts']}
    for row in tables['oauth_attempts']:
        try:
            _row_texts(row,('id','state_hash','provider','session_binding','context','state','expires_at','payload'))
            if not re.fullmatch('[0-9a-f]{64}',row['state_hash']): raise ValueError()
            payload=_payload(row['payload'],_ATTEMPT_FIELDS); context=AttemptContext(**_json(row['context']))
            _time(row['expires_at']); _provider_platform(context)
            if type(row['revision']) is not int or row['revision']<1: raise ValueError()
            if row['state'] not in {'consent_pending','callback_receiving','callback_staged','resume_pending','token_exchanged','principal_pending','target_confirmation','connected','denied','expired','error','unknown'}: raise ValueError()
            if context.provider_id!=row['provider'] or context.session_binding!=row['session_binding']: raise ValueError()
            for field in ('code_ref','ticket_ref','verifier_ref','state_key_ref','token_ref'):
                if payload.get(field) is not None: add_ref(payload[field],field[:-4],context=context)
            if payload.get('authorization') is not None: validate_authorization(payload['authorization'])
            edge_op(payload)
            if payload.get('request_receipt_id'):
                receipt=receipts.get(payload['request_receipt_id'])
                if receipt is None or receipt['attempt_id']!=row['id']: blockers.add('dangling_receipt')
            attempts[row['id']]=(row,payload,context)
        except (ValueError,TypeError,KeyError,RecursionError,StoreError,CredentialError): blockers.add('invalid_attempt')
    for row in tables['oauth_proposals']:
        try:
            _row_texts(row,('id','attempt_id','session_binding','payload'))
            payload=_payload(row['payload'],_PROPOSAL_FIELDS); add_ref(payload['credential_ref'],'token',payload=payload); edge_op(payload)
            if row['consumed'] not in (0,1): raise ValueError()
            attempt=attempts.get(row['attempt_id'])
            if attempt is None: blockers.add('dangling_attempt')
            else:
                if row['session_binding']!=attempt[0]['session_binding'] or payload['credential_ref']!=attempt[1].get('token_ref'): raise ValueError()
                _validate_context_ref(attempt[2],payload['credential_ref'])
        except (ValueError,TypeError,KeyError,RecursionError,StoreError,CredentialError): blockers.add('invalid_proposal')
    proposal_ids={row['id'] for row in tables['oauth_proposals']}
    lease_operations=set()
    for row in tables['oauth_connections']:
        try:
            _row_texts(row,('id','payload'))
            payload=_payload(row['payload'],_CONNECTION_FIELDS)
            if payload['state']=='connected' and payload['credential_ref'] is None: raise ValueError()
            if payload['connection_id']!=row['id'] or payload.get('state') not in ('connected','reauth_required','unknown','disconnected','revoked'): raise ValueError()
            if payload.get('credential_ref') is not None:
                ref=add_ref(payload['credential_ref'],'token',payload=payload)
                if type(payload['credential_generation']) is not int or logical_ref(ref).generation!=payload['credential_generation']: raise ValueError()
            edge_op(payload)
            if payload.get('authorization') is not None: validate_authorization(payload['authorization'])
            if payload.get('operation_lease') is not None:
                lease=payload['operation_lease']
                if type(lease) is not dict: raise ValueError()
                _payload(_dump(lease),_LEASE_FIELDS)
                if any(lease[k]!=payload[k] for k in ('account_id','platform','connection_id','provider_id','base_revision')): raise ValueError()
                if (lease['credential_ref']!=payload['credential_ref'] or type(lease['connection_revision']) is not int
                        or lease['connection_revision']!=payload['revision'] or lease['operation'] not in ('refresh','revoke')
                        or type(lease['credential_generation']) is not int or lease['credential_generation']!=payload['credential_generation']): raise ValueError()
                add_ref(lease['credential_ref'],'token',payload=payload)
                if lease.get('new_ref') is not None: add_ref(lease['new_ref'],'token',payload=payload)
                identifier=edge_op(lease)
                if identifier: lease_operations.add(identifier)
        except (ValueError,TypeError,KeyError,RecursionError,StoreError,CredentialError): blockers.add('invalid_connection')
    for row in tables['oauth_request_receipts']:
        try:
            _row_texts(row,('id','session_binding','operation','request_key','request_hash','status'),nullable=('result','attempt_id','operation_id'))
            if (not re.fullmatch(r'(?:start|continue|inspect|confirm|refresh|disconnect|revoke)(?::[A-Za-z0-9_.:-]{1,200})?',row['operation'])
                    or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}',row['request_key']) or not re.fullmatch('[0-9a-f]{64}',row['request_hash'])): raise ValueError()
            if (row['status']=='pending' and row['result'] is not None) or (row['status']=='completed' and row['result'] is None): raise ValueError()
            if row['status'] not in ('pending','completed','unknown') or type(row['revision']) is not int or row['revision']<1: raise ValueError()
            if row['attempt_id'] is not None and row['attempt_id'] not in attempts: blockers.add('dangling_attempt')
            if row['result'] is not None:
                # Receipt results carry safe DTOs only, never stored-ref encodings.
                result=_validate_receipt_result(_json(row['result']))
                if result.get('attempt_id') is not None and result['attempt_id'] not in attempts: blockers.add('dangling_attempt')
                if result.get('proposal_id') is not None and result['proposal_id'] not in proposal_ids: blockers.add('dangling_proposal')
                if result.get('target_proposal') is not None:
                    target=result['target_proposal']
                    if type(target) is not dict or set(target)!={'proposal_id','target_id','target_label','expected_base_revision','expected_connection_revision'}: raise ValueError()
                    if target['proposal_id'] not in proposal_ids: blockers.add('dangling_proposal')
            identifier=row['operation_id']
            if identifier is not None:
                op=operations.get(identifier)
                if op is None or op.receipt_id!=row['id'] or row['operation'].split(':')[0]!=op.kind: blockers.add('dangling_operation')
                if row['status'] in ('pending','unknown'): pending.add(identifier)
        except (ValueError,TypeError,KeyError,RecursionError,StoreError): blockers.add('invalid_receipt')
    for op in operations.values():
        if op.receipt_id is not None and (op.receipt_id not in receipts or receipts[op.receipt_id]['operation_id']!=op.operation_id): blockers.add('dangling_receipt')
        if op.outcome in ('pending','unknown') or op.remote_state in ('in_flight','unknown') or op.operation_id in pending|lease_operations:
            protected.update(operation_stages.get(op.operation_id,()))
    stages_by_id={stage.stage_id:stage for stage in stages}
    for row in tables['oauth_recovery_events']:
        try:
            _row_texts(row,('event_id','stage_id','code')); _positive(row['stage_revision'])
            if (type(row['payload_version']) is not int or row['payload_version']!=1 or row['code'] not in _EVENT_CODES
                    or row['stage_id'] not in stages_by_id or row['stage_revision']>stages_by_id[row['stage_id']].revision): raise ValueError()
        except (ValueError,TypeError,KeyError): blockers.add('invalid_recovery_event')
    for row in tables['oauth_generations']:
        try:
            decode_stored_ref(dict(row,kind='token'))
        except (ValueError,TypeError,CredentialError): blockers.add('invalid_generation')
    if len(tables['oauth_meta'])!=1 or tables['oauth_meta'][0]['id']!=1 or type(tables['oauth_meta'][0]['generation']) is not int or tables['oauth_meta'][0]['generation']<0:
        blockers.add('invalid_managed_meta')
    return RecoverySnapshot(meta['journal_revision'],tuple(stages),frozenset(protected),tuple(sorted(blockers)),meta['graph_revision'],MappingProxyType(operations),MappingProxyType({key:frozenset(value) for key,value in operation_stages.items()}),frozenset(pending),frozenset(legacy))
