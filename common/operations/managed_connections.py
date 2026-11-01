"""원본 등록부를 변경하지 않는 OAuth 연결 overlay와 세대 CAS."""
from dataclasses import dataclass, replace
from types import MappingProxyType
import json
from uuid import uuid4
from .oauth_store import OAuthAttemptStore, _time
from .oauth_store import OAuthDatabase, _ref, _dump, _provider_platform, _validate_context_ref
from .oauth_models import CredentialRef, validate_authorization
from .oauth_catalog import provider_catalog
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


def _check_provider_platform(provider_id,platform):
    provider=next((p for p in provider_catalog() if p.id==provider_id),None)
    if provider is None or provider.platform!=platform: raise StoreError('credential_owner_mismatch')


def _credential_blocked(row):
    authorization = row.get('authorization')
    return bool(row.get('operation_lease')) or (authorization is not None and authorization['credential_status'] != 'active')


def credential_catalog(snapshot):
    result={}
    for key,ref in snapshot.credential_refs.items():
        row=snapshot.connections.get(ref.connection_id)
        if row is None or row['state']!='connected' or row['account_id']!=ref.account_id or row['platform']!=ref.platform or ref.kind!='token' or ref.namespace!='autosns.oauth': raise StoreError('credential_owner_mismatch')
        _check_provider_platform(row.get('provider_id'),row['platform'])
        if _credential_blocked(row): continue
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
            row['authorization']=validate_authorization(row['authorization']) if row.get('authorization') is not None else None
            if row.get('credential_ref'):
                row['credential_ref']=CredentialRef(**row['credential_ref'])
                if row['state']=='connected' and not _credential_blocked(row): refs[_credential_key(row['credential_ref'])]=row['credential_ref']
        return ManagedSnapshot(next(iter(bases),None),freeze(rows),MappingProxyType(refs),generation)
    def _commit_target(self,db,proposal,expected_base_revision,expected_connection_revision,provider_id):
        if type(expected_connection_revision) is not int or expected_connection_revision<0: raise StoreError('invalid')
        required={'connection_id','account_id','platform','base_revision','target_id','provider_subject','credential_ref','scopes','checked_at'}
        if not isinstance(proposal,dict) or not required<=proposal.keys() or set(proposal)-required-{'target_label','authorization'}: raise StoreError('invalid_proposal')
        p=dict(proposal)
        p['authorization']=validate_authorization(p['authorization']) if p.get('authorization') is not None else None
        if p['authorization'] is not None: p['authorization']['credential_status']='active'
        if p['account_id'] not in ('personal','dept') or not all(isinstance(p[x],str) and p[x] for x in ('connection_id','platform','base_revision','target_id','provider_subject','checked_at')): raise StoreError('invalid_proposal')
        _check_provider_platform(provider_id,p['platform'])
        ref=_ref(p['credential_ref'])
        if any(ref[x]!=p[x] for x in ('account_id','platform','connection_id')) or ref['kind']!='token' or ref['namespace']!='autosns.oauth': raise StoreError('credential_owner_mismatch')
        if p['base_revision']!=expected_base_revision: raise ConflictError()
        if not isinstance(p['scopes'],(list,tuple)) or not all(isinstance(x,str) for x in p['scopes']): raise StoreError('invalid_proposal')
        existing=db.execute('SELECT payload FROM oauth_connections WHERE id=?',(p['connection_id'],)).fetchone()
        old=json.loads(existing[0]) if existing else None
        if (old['revision'] if old else 0)!=expected_connection_revision or (old and old.get('operation_lease')): raise ConflictError()
        if old and old.get('provider_id')!=provider_id: raise StoreError('credential_owner_mismatch')
        if old and (old['base_revision']!=expected_base_revision or any(old[x]!=p[x] for x in ('account_id','platform','target_id'))): raise ConflictError()
        bases={json.loads(row[0])['base_revision'] for row in db.execute('SELECT payload FROM oauth_connections')}
        if bases and bases!={expected_base_revision}: raise ConflictError()
        if old and ref['generation']<=old['credential_generation']: raise ConflictError()
        p.update(provider_id=provider_id,credential_ref=ref,credential_generation=ref['generation'],revision=expected_connection_revision+1,state='connected',execution_enabled=False)
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
            if p.get('authorization') is not None: p['authorization']=validate_authorization(p['authorization'])
            if any(p.get(key)!=getattr(context,key) for key in ('account_id','connection_id','base_revision')): raise StoreError('credential_owner_mismatch')
            if p.get('platform')!=_provider_platform(context): raise StoreError('credential_owner_mismatch')
            if p.get('credential_ref')!=item.get('token_ref'): raise StoreError('credential_owner_mismatch')
            _validate_context_ref(context,_ref(p['credential_ref']))
            # Validate the proposed shape without changing the active pointer.
            db.execute('SAVEPOINT proposal_validation')
            try: self._commit_target(db,p,context.base_revision,context.connection_revision,context.provider_id)
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
            p['authorization']=validate_authorization(p['authorization']) if p.get('authorization') is not None else None
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
            item=OAuthAttemptStore(self.root,self.clock)._decode(attempt)
            context=item['context']
            if (any(p.get(key)!=getattr(context,key) for key in ('account_id','connection_id','base_revision'))
                    or p.get('platform')!=_provider_platform(context)
                    or p['credential_ref']!=item.get('token_ref')): raise StoreError('credential_owner_mismatch')
            _validate_context_ref(context,_ref(p['credential_ref']))
            self._commit_target(db,p,expected_base_revision,expected_connection_revision,context.provider_id)
            db.execute('UPDATE oauth_proposals SET consumed=1 WHERE id=?',(proposal_id,))
            payload=json.loads(attempt['payload'])
            authorization=validate_authorization(p['authorization']) if p.get('authorization') is not None else None
            if authorization is not None: authorization['credential_status']='active'
            payload['authorization']=authorization
            db.execute("UPDATE oauth_attempts SET state='connected',revision=revision+1,payload=? WHERE id=?",(_dump(payload),row['attempt_id']))
        return self.snapshot()
    def proposal_for_attempt(self,attempt_id,session_binding):
        with self._db() as db:
            row=db.execute('SELECT id FROM oauth_proposals WHERE attempt_id=? AND session_binding=? AND consumed=0',(attempt_id,session_binding)).fetchone()
        return self.read_target_proposal(row['id'],session_binding) if row else None

    def claim_connection_operation(self,connection_id,expected_base_revision,expected_connection_revision,operation):
        if operation not in ('refresh','revoke'): raise StoreError('invalid')
        with self._db(True) as db:
            row=db.execute('SELECT payload FROM oauth_connections WHERE id=?',(connection_id,)).fetchone()
            if row is None: raise StoreError('not_found')
            p=json.loads(row[0])
            if (type(expected_connection_revision) is not int or p['revision']!=expected_connection_revision
                    or p['base_revision']!=expected_base_revision or p.get('operation_lease')): raise ConflictError()
            if p['state'] not in ('connected','reauth_required','unknown') or not p.get('credential_ref'): raise ConflictError()
            _check_provider_platform(p.get('provider_id'),p['platform'])
            ref=CredentialRef(**p['credential_ref'])
            if any(getattr(ref,k)!=p[k] for k in ('account_id','platform','connection_id')) or ref.kind!='token': raise StoreError('credential_owner_mismatch')
            lease=dict(lease_id=uuid4().hex,operation=operation,provider_id=p['provider_id'],connection_id=connection_id,base_revision=p['base_revision'],connection_revision=p['revision']+1,credential_ref=p['credential_ref'],credential_generation=p['credential_generation'],account_id=p['account_id'],platform=p['platform'])
            p.update(revision=p['revision']+1,operation_lease=lease)
            db.execute('UPDATE oauth_connections SET payload=? WHERE id=?',(_dump(p),connection_id))
            db.execute('UPDATE oauth_meta SET generation=generation+1 WHERE id=1')
        return freeze(dict(lease,credential_ref=ref))

    def _finish_operation(self,lease,new_ref,state,authorization=None):
        if authorization is not None: authorization=validate_authorization(authorization)
        if not hasattr(lease,'get'): raise StoreError('invalid')
        supplied=dict(lease); supplied['credential_ref']=_ref(supplied.get('credential_ref'))
        with self._db(True) as db:
            row=db.execute('SELECT payload FROM oauth_connections WHERE id=?',(supplied.get('connection_id'),)).fetchone()
            if row is None: raise StoreError('not_found')
            p=json.loads(row[0])
            if (p.get('operation_lease')!=supplied or p['revision']!=supplied.get('connection_revision')
                    or p['state'] not in ('connected','reauth_required','unknown')): raise ConflictError()
            _check_provider_platform(p.get('provider_id'),p['platform'])
            if p['provider_id']!=supplied.get('provider_id'): raise StoreError('credential_owner_mismatch')
            if new_ref is not None:
                ref=_ref(new_ref)
                if supplied['operation']!='refresh' or state!='connected': raise StoreError('invalid')
                if ref['kind']!='token' or any(ref[k]!=p[k] for k in ('account_id','platform','connection_id')): raise StoreError('credential_owner_mismatch')
                if ref['generation']<=p['credential_generation']: raise ConflictError()
                p.update(credential_ref=ref,credential_generation=ref['generation'])
            elif state=='connected': raise StoreError('invalid')
            if state=='revoked':
                if supplied['operation']!='revoke': raise StoreError('invalid')
                p['credential_ref']=None
            if authorization is not None:
                if state!='connected': raise StoreError('invalid')
                p['authorization']=dict(authorization,credential_status='active')
            elif state!='connected' and p.get('authorization') is not None:
                p['authorization']=validate_authorization(dict(p['authorization'],credential_status='reauth_required' if state=='reauth_required' else 'unknown',read_status='unknown',publication_status='blocked'))
            p.pop('operation_lease'); p.update(state=state,revision=p['revision']+1,execution_enabled=False)
            db.execute('UPDATE oauth_connections SET payload=? WHERE id=?',(_dump(p),p['connection_id']))
            db.execute('UPDATE oauth_meta SET generation=generation+1 WHERE id=1')
        return self.snapshot()

    def finish_connection_operation(self,lease,new_ref=None,state=None,authorization=None):
        if state not in (None,'revoked') or (new_ref is None and state is None): raise StoreError('invalid')
        return self._finish_operation(lease,new_ref,'connected' if new_ref is not None and state is None else state,authorization)

    def fail_connection_operation(self,lease,state='unknown'):
        if state not in ('unknown','reauth_required'): raise StoreError('invalid')
        return self._finish_operation(lease,None,state)

    def disconnect_local(self,connection_id,expected_base_revision,expected_connection_revision):
        if type(expected_connection_revision) is not int or expected_connection_revision<1: raise StoreError('invalid')
        with self._db(True) as db:
            row=db.execute('SELECT payload FROM oauth_connections WHERE id=?',(connection_id,)).fetchone()
            if row is None: raise StoreError('not_found')
            p=json.loads(row[0])
            if p['revision']!=expected_connection_revision or p['base_revision']!=expected_base_revision: raise ConflictError()
            p.pop('operation_lease',None)
            if p.get('authorization') is not None: p['authorization']=validate_authorization(dict(p['authorization'],credential_status='unknown',read_status='unknown',publication_status='blocked'))
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
        blocked = _credential_blocked(row)
        if row['state']!='connected' or blocked:
            if old: connections[identifier]=replace(old,enabled=False,auth_status='unknown' if row['state']=='connected' and blocked else row['state'],credential_ref=None,profile_ref=None)
            elif row['state']=='connected' and blocked:
                connections[identifier]=Connection(id=identifier,account_id=row['account_id'],platform=row['platform'],target_id=row['target_id'],target_label=row.get('target_label',''),credential_ref=None,enabled=False,auth_checked_at=row['checked_at'],expected_login_subject=row['provider_subject'],auth_status='unknown')
            continue
        ref=row['credential_ref']; key=_credential_key(ref)
        credentials[key]=catalog[key]
        connections[identifier]=Connection(id=identifier,account_id=row['account_id'],platform=row['platform'],target_id=row['target_id'],target_label=row.get('target_label',''),credential_ref=key,enabled=False,auth_checked_at=row['checked_at'],expected_login_subject=row['provider_subject'],auth_status='connected',capabilities=old.capabilities if old else ())
    return replace(base_registry,connections=connections,credentials=credentials)
