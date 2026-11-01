"""원본 등록부를 변경하지 않는 OAuth 연결 overlay와 세대 CAS."""
from dataclasses import dataclass, replace
from types import MappingProxyType
import json
from uuid import uuid4
from .oauth_store import OAuthAttemptStore, _time
from .oauth_store import OAuthDatabase, _ref, _dump
from .oauth_models import CredentialRef
from .models import Connection, Registry, freeze, thaw
from .content_store import StoreError, ConflictError

@dataclass(frozen=True)
class ManagedSnapshot:
    base_revision: str | None
    connections: object
    credential_refs: object
    generation: int


def _credential_key(ref):
    return f'oauth:{ref.account_id}:{ref.platform}:{ref.connection_id}:{ref.generation}'


def credential_catalog(snapshot):
    result={}
    for key,ref in snapshot.credential_refs.items():
        row=snapshot.connections.get(ref.connection_id)
        if row is None or row['state']!='connected' or row['account_id']!=ref.account_id or row['platform']!=ref.platform or ref.kind!='token' or ref.namespace!='autosns.oauth': raise StoreError('credential_owner_mismatch')
        result[key]=dict(id=key,account_id=ref.account_id,platform=ref.platform,credential_ref=ref)
    return result


class ManagedConnectionStore(OAuthDatabase):
    def snapshot(self):
        if not self.path.is_file(): return ManagedSnapshot(None,freeze({}),freeze({}),0)
        with self._db() as db:
            generation=db.execute('SELECT generation FROM oauth_meta WHERE id=1').fetchone()[0]
            rows={row['id']:json.loads(row['payload']) for row in db.execute('SELECT * FROM oauth_connections')}
        bases={row['base_revision'] for row in rows.values()}
        if len(bases)>1: raise StoreError('base_revision_mismatch')
        refs={}
        for row in rows.values():
            if row.get('credential_ref'):
                row['credential_ref']=CredentialRef(**row['credential_ref'])
                if row['state']=='connected': refs[_credential_key(row['credential_ref'])]=row['credential_ref']
        return ManagedSnapshot(next(iter(bases),None),freeze(rows),MappingProxyType(refs),generation)
    def _commit_target(self,db,proposal,expected_base_revision,expected_connection_revision):
        if type(expected_connection_revision) is not int or expected_connection_revision<0: raise StoreError('invalid')
        required={'connection_id','account_id','platform','base_revision','target_id','provider_subject','credential_ref','scopes','checked_at'}
        if not isinstance(proposal,dict) or not required<=proposal.keys() or set(proposal)-required-{'target_label'}: raise StoreError('invalid_proposal')
        p=dict(proposal)
        if p['account_id'] not in ('personal','dept') or not all(isinstance(p[x],str) and p[x] for x in ('connection_id','platform','base_revision','target_id','provider_subject','checked_at')): raise StoreError('invalid_proposal')
        ref=_ref(p['credential_ref'])
        if any(ref[x]!=p[x] for x in ('account_id','platform','connection_id')) or ref['kind']!='token' or ref['namespace']!='autosns.oauth': raise StoreError('credential_owner_mismatch')
        if p['base_revision']!=expected_base_revision: raise ConflictError()
        if not isinstance(p['scopes'],(list,tuple)) or not all(isinstance(x,str) for x in p['scopes']): raise StoreError('invalid_proposal')
        existing=db.execute('SELECT payload FROM oauth_connections WHERE id=?',(p['connection_id'],)).fetchone()
        old=json.loads(existing[0]) if existing else None
        if (old['revision'] if old else 0)!=expected_connection_revision: raise ConflictError()
        if old and (old['base_revision']!=expected_base_revision or any(old[x]!=p[x] for x in ('account_id','platform','target_id'))): raise ConflictError()
        bases={json.loads(row[0])['base_revision'] for row in db.execute('SELECT payload FROM oauth_connections')}
        if bases and bases!={expected_base_revision}: raise ConflictError()
        if old and ref['generation']<=old['credential_generation']: raise ConflictError()
        p.update(credential_ref=ref,credential_generation=ref['generation'],revision=expected_connection_revision+1,state='connected',execution_enabled=False)
        db.execute('INSERT OR REPLACE INTO oauth_connections VALUES(?,?)',(p['connection_id'],_dump(p)))
        db.execute('UPDATE oauth_meta SET generation=generation+1 WHERE id=1')

    def create_target_proposal(self,attempt_id,session_binding,expected_revision,proposal):
        identifier=uuid4().hex
        with self._db(True) as db:
            row=db.execute('SELECT * FROM oauth_attempts WHERE id=? AND session_binding=?',(attempt_id,session_binding)).fetchone()
            item=OAuthAttemptStore(self.root,self.clock)._decode(row)
            if item['revision']!=expected_revision or item['state'] not in ('token_exchanged','principal_pending'): raise ConflictError()
            if _time(item['expires_at'])<=_time(self.clock()): raise StoreError('expired')
            context=item['context']; p=dict(proposal)
            if any(p.get(key)!=getattr(context,key) for key in ('account_id','connection_id','base_revision')): raise StoreError('credential_owner_mismatch')
            if p.get('credential_ref')!=item.get('token_ref'): raise StoreError('credential_owner_mismatch')
            # Validate the proposed shape without changing the active pointer.
            db.execute('SAVEPOINT proposal_validation')
            try: self._commit_target(db,p,context.base_revision,context.connection_revision)
            finally: db.execute('ROLLBACK TO proposal_validation'); db.execute('RELEASE proposal_validation')
            p['credential_ref']=_ref(p['credential_ref'])
            db.execute('INSERT INTO oauth_proposals VALUES(?,?,?,?,0)',(identifier,attempt_id,session_binding,_dump(p)))
            db.execute("UPDATE oauth_attempts SET state='target_confirmation',revision=revision+1 WHERE id=?",(attempt_id,))
        return self.read_target_proposal(identifier,session_binding)
    def read_target_proposal(self,proposal_id,session_binding):
        with self._db() as db:
            row=db.execute('SELECT * FROM oauth_proposals WHERE id=? AND session_binding=?',(proposal_id,session_binding)).fetchone()
            if row is None: raise StoreError('not_found')
            p=json.loads(row['payload']); p['credential_ref']=CredentialRef(**p['credential_ref'])
            return freeze(dict(p,proposal_id=proposal_id,session_binding=session_binding,attempt_id=row['attempt_id'],consumed=bool(row['consumed'])))
    def confirm_target(self,proposal,expected_base_revision,expected_connection_revision):
        if not hasattr(proposal,'get') or not proposal.get('proposal_id') or not proposal.get('session_binding'): raise StoreError('persisted_proposal_required')
        return self.confirm_target_proposal(proposal['proposal_id'],proposal['session_binding'],expected_base_revision,expected_connection_revision)
    def confirm_target_proposal(self,proposal_id,session_binding,expected_base_revision,expected_connection_revision):
        with self._db(True) as db:
            row=db.execute('SELECT * FROM oauth_proposals WHERE id=? AND session_binding=?',(proposal_id,session_binding)).fetchone()
            if row is None: raise StoreError('not_found')
            if row['consumed']: raise ConflictError()
            attempt=db.execute('SELECT * FROM oauth_attempts WHERE id=?',(row['attempt_id'],)).fetchone()
            if attempt['state']!='target_confirmation': raise ConflictError()
            if _time(attempt['expires_at'])<=_time(self.clock()): raise StoreError('expired')
            p=json.loads(row['payload']); p['credential_ref']=CredentialRef(**p['credential_ref'])
            self._commit_target(db,p,expected_base_revision,expected_connection_revision)
            db.execute('UPDATE oauth_proposals SET consumed=1 WHERE id=?',(proposal_id,))
            db.execute("UPDATE oauth_attempts SET state='connected',revision=revision+1 WHERE id=?",(row['attempt_id'],))
        return self.snapshot()
    def disconnect_local(self,connection_id,expected_base_revision,expected_connection_revision):
        if type(expected_connection_revision) is not int or expected_connection_revision<1: raise StoreError('invalid')
        with self._db(True) as db:
            row=db.execute('SELECT payload FROM oauth_connections WHERE id=?',(connection_id,)).fetchone()
            if row is None: raise StoreError('not_found')
            p=json.loads(row[0])
            if p['revision']!=expected_connection_revision or p['base_revision']!=expected_base_revision: raise ConflictError()
            p.update(state='disconnected',revision=p['revision']+1,credential_ref=None,execution_enabled=False)
            db.execute('UPDATE oauth_connections SET payload=? WHERE id=?',(_dump(p),connection_id))
            db.execute('UPDATE oauth_meta SET generation=generation+1 WHERE id=1')
        return self.snapshot()


def project_registry(base_registry,managed_snapshot):
    if managed_snapshot.base_revision not in (None,base_registry.revision): raise StoreError('base_revision_mismatch')
    catalog=credential_catalog(managed_snapshot)
    connections=dict(base_registry.connections)
    credentials=dict(base_registry.credentials)
    for identifier,row in managed_snapshot.connections.items():
        old=connections.get(identifier)
        if row['account_id'] not in base_registry.accounts: raise StoreError('unknown_account')
        if old and (old.account_id!=row['account_id'] or old.platform!=row['platform']): raise StoreError('credential_owner_mismatch')
        if old and old.target_id is not None and old.target_id!=row['target_id']: raise ConflictError()
        if row['state']!='connected':
            if old: connections[identifier]=replace(old,enabled=False,auth_status='disconnected')
            continue
        ref=row['credential_ref']; key=_credential_key(ref)
        credentials[key]=catalog[key]
        connections[identifier]=Connection(id=identifier,account_id=row['account_id'],platform=row['platform'],target_id=row['target_id'],target_label=row.get('target_label',''),credential_ref=key,enabled=False,auth_checked_at=row['checked_at'],expected_login_subject=row['provider_subject'],auth_status='connected',capabilities=old.capabilities if old else ())
    return replace(base_registry,connections=connections,credentials=credentials)
