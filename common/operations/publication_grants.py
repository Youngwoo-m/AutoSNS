"""OAuth 읽기 연결과 분리한 서버 소유 발행 승인 기록.

생성자는 I/O를 하지 않는다. evidence는 신뢰된 서버의 실제 읽기 전용 공급자 검사와
명시 승인 절차에서만 생성한다. HTTP dict를 승인 증거로 받는 변환기는 제공하지 않는다.
타입 자체가 공급자 검사를 수행하지 않으며, 기본 정책은 모든 공급자를 차단한다.
모든 DB 접근 순서는 재진입 가능한 OAuth writer guard → grant DB다.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat

from .content_store import StoreError, ConflictError
from .oauth_catalog import provider_catalog
from .oauth_stage_models import WorkspaceOwner
from .oauth_workspace import (OAuthWorkspaceContext, oauth_write_guard,
                              require_oauth_write_guard, validate_workspace_context)

DB_NAME='publication-grants.sqlite3'
APPLICATION_ID=0x50475254
SCHEMA_VERSION=1
_DENIED=frozenset(('tiktok','naver','tistory'))
_SHA=re.compile(r'[0-9a-f]{64}\Z')
_BINDING_FIELDS=('registry_revision','connection_id','account_id','platform','provider_id','target_id',
                 'provider_subject','connection_revision','credential_generation','credential_fingerprint',
                 'client_revision','evidence_revision')
_DDL=(
    'CREATE TABLE publication_grant_meta(id INTEGER PRIMARY KEY CHECK(id=1),workspace_id TEXT NOT NULL,root_binding TEXT NOT NULL)',
    "CREATE TABLE publication_grants(connection_id TEXT NOT NULL,revision INTEGER NOT NULL CHECK(revision>=1),decision TEXT NOT NULL CHECK(decision IN ('granted','revoked')),binding_hash TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(connection_id,revision))",
    "CREATE TRIGGER publication_grants_no_update BEFORE UPDATE ON publication_grants BEGIN SELECT RAISE(ABORT,'append_only'); END",
    "CREATE TRIGGER publication_grants_no_delete BEFORE DELETE ON publication_grants BEGIN SELECT RAISE(ABORT,'append_only'); END",
    "CREATE TRIGGER publication_grant_meta_no_update BEFORE UPDATE ON publication_grant_meta BEGIN SELECT RAISE(ABORT,'append_only'); END",
    "CREATE TRIGGER publication_grant_meta_no_delete BEFORE DELETE ON publication_grant_meta BEGIN SELECT RAISE(ABORT,'append_only'); END",
)
_RECORD_KEYS={'binding','observed_scopes','approved_at','expires_at','revision','policy_revision','actor',
              'verification_method','checked_at','credential_expires_at','decision','recorded_at'}


def _fail(code='publication_grant_invalid'):
    raise StoreError(code) from None


def _text(value,limit=300,*,allow_url=False):
    return (type(value) is str and 0<len(value)<=limit and value==value.strip() and
            not any(ord(c)<32 or 127<=ord(c)<=159 or 0xd800<=ord(c)<=0xdfff for c in value) and
            (allow_url or '://' not in value))


def _time(value):
    if (not isinstance(value,datetime) or value.tzinfo is None or
            value.utcoffset()!=timedelta(0)):
        _fail()
    return value.astimezone(timezone.utc)


def _iso(value):return _time(value).isoformat(timespec='microseconds')


def _json(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)


class _Private:
    def __repr__(self):return type(self).__name__+'(<비공개>)'
    def to_dict(self,*,public=True):
        if public is not True:_fail('publication_grant_private_serialization_forbidden')
        return {}


@dataclass(frozen=True,repr=False)
class PublicationGrantPolicy(_Private):
    revision: str='publication-grants-deny-v1'
    allowed_providers: tuple=()
    max_ttl: timedelta=timedelta(hours=1)

    def __post_init__(self):
        known={p.id for p in provider_catalog()}
        if (not _text(self.revision) or type(self.allowed_providers) is not tuple or
                any(type(p) is not str or p not in known for p in self.allowed_providers) or
                len(self.allowed_providers)!=len(set(self.allowed_providers)) or
                not isinstance(self.max_ttl,timedelta) or not timedelta(0)<self.max_ttl):
            _fail()


@dataclass(frozen=True,repr=False)
class PublicationGrantBinding(_Private):
    owner: WorkspaceOwner
    registry_revision: str
    connection_id: str
    account_id: str
    platform: str
    provider_id: str
    target_id: str
    provider_subject: str
    connection_revision: int
    credential_generation: int
    credential_fingerprint: str
    client_revision: int
    evidence_revision: str

    def __post_init__(self):
        if type(self.owner) is not WorkspaceOwner:_fail()
        try:self.owner.__post_init__()
        except Exception:_fail()
        if (any(not _text(getattr(self,key)) for key in _BINDING_FIELDS
                if key not in ('connection_revision','credential_generation','client_revision')) or
                self.account_id not in ('personal','dept') or
                any(type(getattr(self,key)) is not int or getattr(self,key)<1
                    for key in ('connection_revision','credential_generation','client_revision')) or
                _SHA.fullmatch(self.credential_fingerprint) is None):
            _fail()
        provider=next((p for p in provider_catalog() if p.id==self.provider_id),None)
        if provider is None or provider.platform!=self.platform:_fail()


@dataclass(frozen=True,repr=False)
class VerifiedPublicationEvidence(_Private):
    binding: PublicationGrantBinding
    observed_scopes: tuple
    checked_at: datetime
    credential_expires_at: datetime
    can_publish: bool
    verification_method: str

    def __post_init__(self):
        if type(self.binding) is not PublicationGrantBinding:_fail()
        self.binding.__post_init__()
        _scopes(self.observed_scopes,self.binding.provider_id)
        _time(self.checked_at);_time(self.credential_expires_at)
        if (type(self.can_publish) is not bool or type(self.verification_method) is not str or
                re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',self.verification_method) is None):_fail()


@dataclass(frozen=True,repr=False)
class PublicationGrant(_Private):
    binding: PublicationGrantBinding
    observed_scopes: tuple
    approved_at: datetime
    expires_at: datetime
    revision: int
    policy_revision: str
    actor: str
    verification_method: str


def _scopes(value,provider_id):
    provider=next((p for p in provider_catalog() if p.id==provider_id),None)
    if (provider is None or type(value) is not tuple or any(not _text(v,2048,allow_url=True) for v in value) or
            len(value)!=len(set(value)) or not set(value)<=set(provider.read_scopes)|set(provider.publication_scopes)):
        _fail('publication_grant_scope_unverified')
    return set(value)


def _encode_binding(binding):
    return dict(owner=dict(workspace_id=binding.owner.workspace_id,root_binding=binding.owner.root_binding,
                           format_version=binding.owner.format_version),
                **{key:getattr(binding,key) for key in _BINDING_FIELDS})


def _decode_binding(value):
    if type(value) is not dict or set(value)!={'owner',*_BINDING_FIELDS}:_fail('publication_grant_storage_error')
    owner=value['owner']
    if type(owner) is not dict or set(owner)!={'workspace_id','root_binding','format_version'}:_fail('publication_grant_storage_error')
    return PublicationGrantBinding(WorkspaceOwner(**owner),**{k:value[k] for k in _BINDING_FIELDS})


def _binding_hash(binding):return hashlib.sha256(_json(_encode_binding(binding)).encode()).hexdigest()


def _unique(pairs):
    value={}
    for key,item in pairs:
        if key in value:raise ValueError()
        value[key]=item
    return value


class PublicationGrantStore(_Private):
    def __init__(self,workspace_context,*,policy=None):
        if type(workspace_context) is not OAuthWorkspaceContext:_fail()
        self.context=workspace_context
        self.policy=PublicationGrantPolicy() if policy is None else policy
        if type(self.policy) is not PublicationGrantPolicy:_fail()
        self.policy.__post_init__()
        self.root=Path(workspace_context.root)
        self._initialized=False

    @contextmanager
    def _guard(self):
        try:
            with oauth_write_guard(self.context):
                current=validate_workspace_context(self.context)
                if current.root!=self.root or current.owner!=self.context.owner:_fail('publication_grant_owner_mismatch')
                yield
        except (StoreError,ConflictError):raise
        except Exception:_fail('publication_grant_storage_error')

    def _path(self):
        path=self.root/DB_NAME
        if (self.root.is_symlink() or path.is_symlink() or
                any(p.is_symlink() for p in self.root.parents if str(p) not in ('/tmp','/var')) or
                path.exists() and not path.is_file()):_fail('publication_grant_storage_error')
        for suffix in ('-journal','-wal','-shm'):
            side=Path(str(path)+suffix)
            if side.is_symlink() or side.exists() and not side.is_file():_fail('publication_grant_storage_error')
        if path.exists() and stat.S_IMODE(path.stat().st_mode)!=0o600:_fail('publication_grant_storage_error')
        return path

    def _verify(self,db):
        actual=sorted(row[0] for row in db.execute("SELECT sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))
        if (db.execute('PRAGMA application_id').fetchone()[0]!=APPLICATION_ID or
                db.execute('PRAGMA user_version').fetchone()[0]!=SCHEMA_VERSION or actual!=sorted(_DDL)):
            _fail('publication_grant_storage_error')
        owners=db.execute('SELECT id,workspace_id,root_binding FROM publication_grant_meta').fetchall()
        if len(owners)!=1 or tuple(owners[0])!=(1,self.context.owner.workspace_id,self.context.owner.root_binding):
            _fail('publication_grant_owner_mismatch')

    @contextmanager
    def _db(self,write=False):
        require_oauth_write_guard(self.root,self.context.owner)
        db=None
        try:
            path=self._path()
            if write and not self._initialized:_fail('publication_grant_storage_error')
            if not path.exists():
                yield None;return
            db=sqlite3.connect(path.as_uri()+('?mode=rw' if write else '?mode=ro'),uri=True,timeout=5,isolation_level=None)
            db.row_factory=sqlite3.Row;self._verify(db)
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield db
            if write:db.commit()
        except StoreError:raise
        except (OSError,sqlite3.Error,ValueError,TypeError,UnicodeError):_fail('publication_grant_storage_error')
        finally:
            if db is not None:db.close()

    def initialize(self):
        with self._guard():
            path=self._path();db=None
            try:
                if not path.exists():
                    try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                    except FileExistsError:pass
                    else:os.close(fd)
                path=self._path()
                db=sqlite3.connect(path,timeout=5,isolation_level=None)
                db.execute('BEGIN IMMEDIATE')
                if (not db.execute('SELECT name FROM sqlite_master').fetchall() and
                        db.execute('PRAGMA application_id').fetchone()[0]==0 and db.execute('PRAGMA user_version').fetchone()[0]==0):
                    for statement in _DDL:db.execute(statement)
                    db.execute('INSERT INTO publication_grant_meta VALUES(1,?,?)',
                               (self.context.owner.workspace_id,self.context.owner.root_binding))
                    db.execute(f'PRAGMA application_id={APPLICATION_ID}');db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
                self._verify(db);db.commit();self._initialized=True
            except StoreError:raise
            except (OSError,sqlite3.Error):_fail('publication_grant_storage_error')
            finally:
                if db is not None:db.close()

    def _binding(self,binding):
        if type(binding) is not PublicationGrantBinding:_fail()
        binding.__post_init__()
        if binding.owner!=self.context.owner:_fail('publication_grant_owner_mismatch')

    def _admissible(self,binding,observed):
        self.policy.__post_init__()
        provider=next((p for p in provider_catalog() if p.id==binding.provider_id),None)
        return (binding.provider_id not in _DENIED and binding.provider_id in self.policy.allowed_providers and
                bool(provider and provider.publication_scopes) and
                set(provider.read_scopes)|set(provider.publication_scopes)<=observed)

    def _latest(self,db,connection_id):
        if db is None:return None
        row=db.execute('SELECT * FROM publication_grants WHERE connection_id=? ORDER BY revision DESC LIMIT 1',(connection_id,)).fetchone()
        if row is None:return None
        try:
            data=json.loads(row['payload'],object_pairs_hook=_unique)
            if type(data) is not dict or set(data)!=_RECORD_KEYS:raise ValueError()
            binding=_decode_binding(data['binding']);self._binding(binding)
            scopes=tuple(data['observed_scopes']) if type(data['observed_scopes']) is list else None
            _scopes(scopes,binding.provider_id)
            for key in ('approved_at','expires_at','checked_at','credential_expires_at','recorded_at'):
                data[key]=_time(datetime.fromisoformat(data[key]))
            if (row['connection_id']!=binding.connection_id or data['revision']!=row['revision'] or
                    type(data['revision']) is not int or data['revision']<1 or
                    data['decision']!=row['decision'] or data['decision'] not in ('granted','revoked') or
                    row['binding_hash']!=_binding_hash(binding) or not _text(data['actor'],200) or
                    not _text(data['policy_revision']) or type(data['verification_method']) is not str or
                    re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',data['verification_method']) is None or
                    not data['checked_at']<=data['approved_at']<data['expires_at']<=data['credential_expires_at']):
                raise ValueError()
            data['binding']=binding;data['observed_scopes']=scopes
            return data
        except Exception:_fail('publication_grant_storage_error')

    def _active(self,data,binding,now):
        return bool(data is not None and data['binding']==binding and data['decision']=='granted' and
                    data['policy_revision']==self.policy.revision and data['approved_at']<=now<data['expires_at'] and
                    self._admissible(binding,set(data['observed_scopes'])))

    def _status(self,binding,data,now):
        same=data is not None and data['binding']==binding
        status='blocked'
        if same:
            if data['decision']=='revoked':status='revoked'
            elif data['expires_at']<=now:status='expired'
            elif self._active(data,binding,now):status='granted'
        return dict(connection_id=binding.connection_id,account_id=binding.account_id,platform=binding.platform,
                    provider_id=binding.provider_id,target_id=binding.target_id,revision=data['revision'] if data else 0,
                    status=status,approved_at=_iso(data['approved_at']) if same else None,
                    expires_at=_iso(data['expires_at']) if same else None,policy_revision=self.policy.revision)

    def issue(self,evidence,*,expected_revision,actor,expires_at,now):
        if type(evidence) is not VerifiedPublicationEvidence:_fail()
        evidence.__post_init__();binding=evidence.binding;self._binding(binding)
        now=_time(now);expiry=_time(expires_at)
        if (type(expected_revision) is not int or expected_revision<0 or not _text(actor,200) or
                evidence.can_publish is not True or not timedelta(0)<=now-evidence.checked_at<=timedelta(seconds=60) or
                not now<expiry<=evidence.credential_expires_at or expiry-now>self.policy.max_ttl or
                not self._admissible(binding,_scopes(evidence.observed_scopes,binding.provider_id))):
            _fail('publication_grant_unverified')
        with self._guard(),self._db(write=True) as db:
            prior=self._latest(db,binding.connection_id)
            if (prior['revision'] if prior else 0)!=expected_revision:raise ConflictError()
            data=dict(binding=_encode_binding(binding),observed_scopes=sorted(evidence.observed_scopes),
                      approved_at=_iso(now),expires_at=_iso(expiry),revision=expected_revision+1,
                      policy_revision=self.policy.revision,actor=actor,verification_method=evidence.verification_method,
                      checked_at=_iso(evidence.checked_at),credential_expires_at=_iso(evidence.credential_expires_at),
                      decision='granted',recorded_at=_iso(now))
            db.execute('INSERT INTO publication_grants VALUES(?,?,?,?,?)',
                       (binding.connection_id,data['revision'],'granted',_binding_hash(binding),_json(data)))
            return self._status(binding,self._latest(db,binding.connection_id),now)

    def revoke(self,connection_id,*,expected_revision,actor,now):
        now=_time(now)
        if not _text(connection_id) or type(expected_revision) is not int or expected_revision<1 or not _text(actor,200):_fail()
        with self._guard(),self._db(write=True) as db:
            prior=self._latest(db,connection_id)
            if prior is None:_fail('not_found')
            if prior['revision']!=expected_revision:raise ConflictError()
            data={**prior,'binding':_encode_binding(prior['binding']),'observed_scopes':list(prior['observed_scopes']),
                  'revision':expected_revision+1,'decision':'revoked','actor':actor,'recorded_at':now}
            for key in ('approved_at','expires_at','checked_at','credential_expires_at','recorded_at'):data[key]=_iso(data[key])
            db.execute('INSERT INTO publication_grants VALUES(?,?,?,?,?)',
                       (connection_id,data['revision'],'revoked',_binding_hash(prior['binding']),_json(data)))
            return self._status(prior['binding'],self._latest(db,connection_id),now)

    def current(self,binding,*,now):
        self._binding(binding);now=_time(now)
        with self._guard(),self._db() as db:
            data=self._latest(db,binding.connection_id)
            if not self._active(data,binding,now):return None
            return PublicationGrant(binding,data['observed_scopes'],data['approved_at'],data['expires_at'],
                                    data['revision'],data['policy_revision'],data['actor'],data['verification_method'])

    def status(self,binding,*,now):
        self._binding(binding);now=_time(now)
        with self._guard(),self._db() as db:
            return self._status(binding,self._latest(db,binding.connection_id),now)
