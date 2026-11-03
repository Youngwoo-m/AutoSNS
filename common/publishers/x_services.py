"""X 단일 게시의 영속 원장. 비용 허가 전에는 읽기·쓰기 모두 호출하지 않는다."""
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import timedelta
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3

from common.operations.content_store import StoreError,ConflictError
from common.operations.models import thaw
from common.operations.runtime_models import utc
from .x_payloads import PREPARED_KEYS,NUMERIC_ID,validate_x_text
from common.operations.x_evidence import reconstruct_x_text,safe_x_url

DB_NAME='x-submissions.sqlite3'
APPLICATION_ID=0x58504F53
SCHEMA_VERSION=1
STATES=('started','submitted','unknown','known_not_posted')
COLUMNS=('logical_key','payload_hash','prepared','state','remote_id','reason_code','version','created_at','updated_at')
DDL='CREATE TABLE x_submissions(logical_key TEXT PRIMARY KEY,payload_hash TEXT NOT NULL,prepared TEXT NOT NULL,state TEXT NOT NULL,remote_id TEXT,reason_code TEXT,version INTEGER NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)'

def _json(value):return json.dumps(thaw(value),sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def _hash(raw):return hashlib.sha256(raw).hexdigest()
def _id(value):return type(value) is str and NUMERIC_ID.fullmatch(value) is not None

def _validate(prepared,target):
    if not isinstance(prepared,Mapping) or set(prepared)!=set(PREPARED_KEYS) or not isinstance(target,Mapping):raise ValueError()
    if prepared['platform']!='x' or target.get('platform','x')!='x':raise ValueError()
    if prepared['owner_account_id'] not in ('personal','dept') or prepared['destination_account_id'] not in ('personal','dept'):raise ValueError()
    if (prepared['connection_id']!=prepared['destination_account_id']+'.x'
            or target.get('connection_id',prepared['connection_id'])!=prepared['connection_id']
            or not _id(prepared['target_id']) or prepared['target_id']!=target.get('target_id')):raise ValueError()
    if type(prepared['content_revision']) is not int or prepared['content_revision']<1:raise ValueError()
    for name in ('content_id','manifest_hash','publication_purpose','schedule_slot'):
        value=prepared[name]
        if type(value) is not str or not value.strip() or len(value)>500 or any(ord(c)<32 for c in value):raise ValueError()
    text=validate_x_text(prepared['text'])
    if (prepared['body_sha256']!=_hash(text.encode('utf-8')) or not isinstance(prepared['media_sha256'],(list,tuple))
            or list(prepared['media_sha256'])!=[]):raise ValueError()
    normalized=thaw(prepared);normalized['media_sha256']=[]
    identity={name:normalized[name] for name in ('owner_account_id','destination_account_id','connection_id','target_id','content_id','content_revision','publication_purpose','schedule_slot')}
    return normalized,_hash(_json(identity).encode()),_hash(_json(normalized).encode())

class XJournal:
    def __init__(self,root):self.root=Path(root).absolute();self._initialized=False
    def _path(self):
        path=self.root/DB_NAME
        if self.root.is_symlink() or path.is_symlink() or (path.exists() and not path.is_file()) or not path.resolve().is_relative_to(self.root.resolve()):
            raise StoreError('x_storage_error')
        return path
    @staticmethod
    def _verify(db):
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if (db.execute('PRAGMA application_id').fetchone()[0]!=APPLICATION_ID or db.execute('PRAGMA user_version').fetchone()[0]!=SCHEMA_VERSION
                or tables!={'x_submissions'} or tuple(r[1] for r in db.execute('PRAGMA table_info(x_submissions)'))!=COLUMNS):
            raise StoreError('x_storage_error')
    @contextmanager
    def _db(self,write=False):
        if write and not self._initialized:raise StoreError('x_storage_error')
        db=None
        try:
            if self._path().is_file() and self._path().stat().st_mode&0o077:raise StoreError('x_storage_error')
            db=sqlite3.connect(self._path().as_uri()+('?mode=rw' if write else '?mode=ro'),uri=True,timeout=5,isolation_level=None)
            db.row_factory=sqlite3.Row;self._verify(db);yield db
        except StoreError:raise
        except (sqlite3.Error,OSError,ValueError,UnicodeError):raise StoreError('x_storage_error') from None
        finally:
            if db is not None:db.close()
    def initialize(self):
        db=None
        try:
            path=self._path();path.parent.mkdir(parents=True,exist_ok=True)
            if not path.exists():
                fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,'O_NOFOLLOW',0),0o600)
                os.close(fd)
            if path.stat().st_mode&0o077:raise StoreError('x_storage_error')
            db=sqlite3.connect(path,isolation_level=None,timeout=5)
            db.execute('BEGIN IMMEDIATE')
            objects=db.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
            if not objects and db.execute('PRAGMA application_id').fetchone()[0]==0 and db.execute('PRAGMA user_version').fetchone()[0]==0:
                db.execute(DDL);db.execute(f'PRAGMA application_id={APPLICATION_ID}');db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
            self._verify(db);db.execute('COMMIT')
        except StoreError:
            if db is not None:db.rollback()
            raise
        except (sqlite3.Error,OSError):
            if db is not None:db.rollback()
            raise StoreError('x_storage_error') from None
        finally:
            if db is not None:db.close()
        self._initialized=True
    @contextmanager
    def hold(self,key):
        if not self._initialized or not re.fullmatch(r'[a-f0-9]{64}',key):raise StoreError('x_storage_error')
        self._path();folder=self.root/'x-submission-locks'
        if folder.is_symlink():raise StoreError('x_storage_error')
        folder.mkdir(exist_ok=True);fd=os.open(folder/key,os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
        try:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise StoreError('x_submission_busy') from None
            yield
        finally:os.close(fd)
    def get(self,key):
        if not self._path().is_file():return None
        with self._db() as db:
            row=db.execute('SELECT * FROM x_submissions WHERE logical_key=?',(key,)).fetchone()
            return dict(row) if row else None
    def known(self,remote_id,target):
        if not self._path().is_file() or not _id(remote_id):return None
        with self._db() as db:
            rows=db.execute('SELECT * FROM x_submissions WHERE remote_id=? AND state IN (?,?)',
                (remote_id,'submitted','unknown')).fetchall()
            matched=[]
            for row in rows:
                prepared=json.loads(row['prepared'])
                try:normalized,key,digest=_validate(prepared,target)
                except Exception:continue
                if key==row['logical_key'] and digest==row['payload_hash']:matched.append(normalized)
            return matched[0] if len(matched)==1 else None
    def claim(self,key,payload_hash,prepared,at):
        with self._db(True) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row=db.execute('SELECT * FROM x_submissions WHERE logical_key=?',(key,)).fetchone()
                if row is not None:
                    if row['payload_hash']!=payload_hash or row['prepared']!=_json(prepared):raise StoreError('x_payload_conflict')
                    db.execute('COMMIT');return dict(row),False
                db.execute('INSERT INTO x_submissions(logical_key,payload_hash,prepared,state,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                    (key,payload_hash,_json(prepared),'started',1,at,at))
                row=dict(db.execute('SELECT * FROM x_submissions WHERE logical_key=?',(key,)).fetchone());db.execute('COMMIT');return row,True
            except BaseException:db.rollback();raise
    def transition(self,row,state,at,*,remote_id=None,reason_code=None):
        if state not in STATES:raise StoreError('x_storage_error')
        allowed={'started':{'submitted','unknown','known_not_posted'},'known_not_posted':{'started'}}
        if state not in allowed.get(row['state'],set()):raise ConflictError()
        with self._db(True) as db:
            cursor=db.execute('UPDATE x_submissions SET state=?,remote_id=?,reason_code=?,version=version+1,updated_at=? WHERE logical_key=? AND version=? AND state=?',
                (state,remote_id if remote_id is not None else row['remote_id'],reason_code,at,row['logical_key'],row['version'],row['state']))
            if cursor.rowcount!=1:raise ConflictError()
        return self.get(row['logical_key'])


def _failed(reason):return dict(outcome='failed',evidence=dict(reason=reason,confirmed_not_submitted=True))
def _unknown(remote_id=None):
    return dict(outcome='unknown',**({'remote_id':remote_id} if _id(remote_id) else {}),evidence=dict(reason='x_submission_uncertain'))
def _submitted(remote_id):return dict(outcome='submitted',remote_id=remote_id,url=None,evidence={})


class XServices:
    """권한·비용 정책은 서버가 주입한다. owner API 응답만으로 공개를 인정하지 않는다."""
    def __init__(self,client,journal,clock,*,cost_authorizer=None,public_probe=None):
        if (not callable(clock) or cost_authorizer is not None and not callable(cost_authorizer)
                or public_probe is not None and not callable(public_probe)):
            raise StoreError('invalid_x_service')
        self.client,self.journal,self.clock=client,journal,clock
        self.cost_authorizer,self.public_probe=cost_authorizer,public_probe
        self.before_write=lambda:None

    def __repr__(self):return 'XServices(<private>)'
    def _at(self):return utc(self.clock()).isoformat()
    def _cost(self,target):
        try:return self.cost_authorizer is not None and self.cost_authorizer(target) is True
        except Exception:return False
    def inspect(self,target):
        base=dict(platform='x',target_id=None,login_subject=None,authenticated=False,
            verification_method='immutable_x_user_id',status='cost_confirmation_required')
        if not isinstance(target,Mapping) or not _id(target.get('target_id')) or not self._cost(target):return base
        try:
            user=self.client.inspect_account()
            if (not isinstance(user,Mapping) or user.get('id')!=target['target_id']
                    or user.get('protected') is not False
                    or target.get('expected_login_subject') not in (None,user['id'])):
                return dict(base,status='needs_review')
            return dict(base,target_id=user['id'],login_subject=user['id'],authenticated=True,status='ready')
        except Exception:return dict(base,status='needs_auth')

    def submit(self,prepared,target):
        try:normalized,key,digest=_validate(prepared,target)
        except Exception:return _failed('x_invalid_payload')
        # 원장 재생은 유료 API가 아니므로 이미 완료한 결과는 비용 조회 없이 반환한다.
        try:
            prior=self.journal.get(key)
            if prior is not None:
                if prior['payload_hash']!=digest or prior['prepared']!=_json(normalized):return _failed('x_payload_conflict')
                if prior['state']=='submitted':return _submitted(prior['remote_id']) if _id(prior['remote_id']) else _unknown()
                if prior['state'] in ('started','unknown'):return _unknown(prior['remote_id'])
        except Exception:return _failed('x_journal_unavailable')
        if not self._cost(target):return _failed('x_cost_confirmation_required')
        if not self.inspect(target)['authenticated']:return _failed('target_unverified')
        try:
            with self.journal.hold(key):
                row,new=self.journal.claim(key,digest,normalized,self._at())
                if row['state']=='submitted':return _submitted(row['remote_id']) if _id(row['remote_id']) else _unknown()
                if not new and row['state']!='known_not_posted':return _unknown(row['remote_id'])
                if not self._cost(target):
                    if new:self.journal.transition(row,'known_not_posted',self._at(),reason_code='x_cost_confirmation_required')
                    return _failed('x_cost_confirmation_required')
                try:self.before_write()
                except Exception:
                    if new:self.journal.transition(row,'known_not_posted',self._at(),reason_code='x_write_blocked')
                    return _failed('x_write_blocked')
                if not self._cost(target):
                    if new:self.journal.transition(row,'known_not_posted',self._at(),reason_code='x_cost_confirmation_required')
                    return _failed('x_cost_confirmation_required')
                if not new:row=self.journal.transition(row,'started',self._at())
                remote_id=None
                try:
                    posted=self.client.create_post(normalized['text'])
                    remote_id=posted.get('id') if isinstance(posted,Mapping) else None
                    if not _id(remote_id):raise ValueError()
                    self.journal.transition(row,'submitted',self._at(),remote_id=remote_id)
                    return _submitted(remote_id)
                except Exception:
                    try:self.journal.transition(row,'unknown',self._at(),remote_id=remote_id if _id(remote_id) else None,reason_code='x_submission_uncertain')
                    except Exception:pass
                    return _unknown(remote_id)
        except Exception:return _unknown()

    def _visibility(self,observation):
        if self.public_probe is None:return 'unknown'
        try:
            started=utc(self.clock());proof=self.public_probe(dict(observation));finished=utc(self.clock())
            if (not isinstance(proof,Mapping) or set(proof)!={'public','remote_id','target_id','body_sha256','url','checked_at'}
                    or proof['public'] is not True
                    or any(proof[k]!=observation[k] for k in ('remote_id','target_id','body_sha256','url'))):return 'unknown'
            checked=utc(proof['checked_at'])
            return 'public' if started<=checked<=finished and finished-checked<=timedelta(seconds=60) else 'unknown'
        except Exception:return 'unknown'

    def read_post(self,target,remote_id):
        if not _id(remote_id) or not self._cost(target):return None
        try:
            approved=self.journal.known(remote_id,target)
            if approved is None or not self.inspect(target)['authenticated'] or not self._cost(target):return None
            row=self.client.read_post(remote_id)
            if (not isinstance(row,Mapping) or row.get('id')!=remote_id or row.get('author_id')!=target['target_id']
                    or row.get('withheld')):return None
            identity=reconstruct_x_text(row.get('text'),row.get('entities',{}),approved['text'])
            if identity is None:return None
            url=safe_x_url('https://x.com/i/web/status/'+remote_id,remote_id)
            if url is None:return None
            observed=dict(platform='x',remote_id=remote_id,target_id=target['target_id'],created_at=utc(row['created_at']).isoformat(),
                text=identity['text'],remote_text=row['text'],remote_text_sha256=identity['remote_text_sha256'],
                body_sha256=identity['body_sha256'],media_sha256=[],visibility='unknown',url=url,
                url_entities=thaw(row.get('entities',{})))
            if self._cost(target):observed['visibility']=self._visibility(observed)
            return observed
        except Exception:return None
    def verify(self,target,remote_id):return self.read_post(target,remote_id)
    def lookup(self,target,attempt):
        if not isinstance(attempt,Mapping):return []
        previous=attempt.get('result')
        remote=attempt.get('remote_id') or (previous.get('remote_id') if isinstance(previous,Mapping) else None)
        observed=self.read_post(target,remote) if _id(remote) else None
        return [observed] if observed is not None else []

