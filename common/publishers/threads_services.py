"""Threads 텍스트 생성/게시의 영속 경계. 명시 호출 전에는 I/O가 없다.

원격 POST 직전에 원장을 기록하며 불명확한 결과는 재시도하지 않는다. 동일한 계획의
준비된 container만 다음 승인된 호출에서 재확인한다. 실제 토큰·client 구성은 서버가
주입하며 기본 bootstrap, OAuth 권한, 비용 정책을 변경하지 않는다.
"""
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
from urllib.parse import urlsplit

from common.operations.content_store import StoreError,ConflictError
from common.operations.runtime_models import utc

DB_NAME='threads-submissions.sqlite3'
APPLICATION_ID=0x54485244
SCHEMA_VERSION=1
STATES=('create_started','container_ready','publish_started','submitted','unknown','failed')
COLUMNS=('logical_key','payload_hash','prepared','state','container_id','remote_id','reason_code','version','created_at','updated_at')
PREPARED_KEYS={'platform','connection_id','target_id','owner_account_id','destination_account_id','content_id',
    'content_revision','manifest_hash','publication_purpose','schedule_slot','text','body_sha256','media_sha256'}
_ID=re.compile(r'[0-9]{1,64}')
DDL='CREATE TABLE threads_submissions(logical_key TEXT PRIMARY KEY,payload_hash TEXT NOT NULL,prepared TEXT NOT NULL,state TEXT NOT NULL,container_id TEXT,remote_id TEXT,reason_code TEXT,version INTEGER NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)'


def _hash(raw):return hashlib.sha256(raw).hexdigest()
def _json(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def _id(value):return type(value) is str and _ID.fullmatch(value) is not None

def _validate(prepared,target):
    if not isinstance(prepared,Mapping) or set(prepared)!=PREPARED_KEYS or not isinstance(target,Mapping):raise ValueError()
    if prepared['platform']!='threads' or target.get('platform','threads')!='threads':raise ValueError()
    if prepared['owner_account_id'] not in ('personal','dept') or prepared['destination_account_id'] not in ('personal','dept'):raise ValueError()
    if prepared['connection_id']!=prepared['destination_account_id']+'.threads' or prepared['target_id']!=target.get('target_id'):raise ValueError()
    if target.get('connection_id',prepared['connection_id'])!=prepared['connection_id'] or not _id(prepared['target_id']):raise ValueError()
    if type(prepared['content_revision']) is not int or prepared['content_revision']<1:raise ValueError()
    for key in ('content_id','manifest_hash','publication_purpose','schedule_slot'):
        value=prepared[key]
        if type(value) is not str or not value.strip() or len(value)>500 or any(ord(c)<32 for c in value):raise ValueError()
    text=prepared['text']
    if type(text) is not str or not text.strip() or len(text)>500 or '\x00' in text:raise ValueError()
    raw=text.encode('utf-8')
    if prepared['body_sha256']!=_hash(raw) or prepared['media_sha256'] not in ([],()):raise ValueError()
    normalized=dict(prepared);normalized['media_sha256']=[]
    identity={k:normalized[k] for k in ('owner_account_id','destination_account_id','connection_id','target_id',
        'content_id','content_revision','publication_purpose','schedule_slot')}
    return normalized,_hash(_json(identity).encode()),_hash(_json(normalized).encode())


class ThreadsJournal:
    def __init__(self,root):self.root=Path(root).absolute();self._initialized=False
    def _path(self):
        path=self.root/DB_NAME
        if self.root.is_symlink() or path.is_symlink() or (path.exists() and not path.is_file()) or not path.resolve().is_relative_to(self.root.resolve()):
            raise StoreError('threads_storage_error')
        return path
    @staticmethod
    def _verify(db):
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if (db.execute('PRAGMA application_id').fetchone()[0]!=APPLICATION_ID or db.execute('PRAGMA user_version').fetchone()[0]!=SCHEMA_VERSION
                or tables!={'threads_submissions'} or tuple(r[1] for r in db.execute('PRAGMA table_info(threads_submissions)'))!=COLUMNS):
            raise StoreError('threads_storage_error')
    @contextmanager
    def _db(self,write=False):
        if write and not self._initialized:raise StoreError('threads_storage_error')
        db=None
        try:
            db=sqlite3.connect(self._path().as_uri()+('?mode=rw' if write else '?mode=ro'),uri=True,timeout=5,isolation_level=None)
            db.row_factory=sqlite3.Row;self._verify(db);yield db
        except StoreError:raise
        except (sqlite3.Error,OSError,ValueError,UnicodeError):raise StoreError('threads_storage_error') from None
        finally:
            if db is not None:db.close()
    def initialize(self):
        db=None
        try:
            path=self._path();path.parent.mkdir(parents=True,exist_ok=True);db=sqlite3.connect(path,isolation_level=None,timeout=5)
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
            raise StoreError('threads_storage_error') from None
        finally:
            if db is not None:db.close()
        self._initialized=True
    @contextmanager
    def hold(self,key):
        if not self._initialized or not re.fullmatch(r'[a-f0-9]{64}',key):raise StoreError('threads_storage_error')
        self._path();folder=self.root/'threads-submission-locks'
        if folder.is_symlink():raise StoreError('threads_storage_error')
        folder.mkdir(exist_ok=True)
        fd=os.open(folder/key,os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
        try:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise StoreError('threads_submission_busy') from None
            yield
        finally:os.close(fd)
    def get(self,key):
        if not self._path().is_file():return None
        with self._db() as db:
            row=db.execute('SELECT * FROM threads_submissions WHERE logical_key=?',(key,)).fetchone()
            return dict(row) if row else None
    def claim(self,key,payload_hash,prepared,at):
        with self._db(True) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row=db.execute('SELECT * FROM threads_submissions WHERE logical_key=?',(key,)).fetchone()
                if row is not None:
                    if row['payload_hash']!=payload_hash or row['prepared']!=_json(prepared):raise StoreError('threads_payload_conflict')
                    db.execute('COMMIT');return dict(row),False
                db.execute('INSERT INTO threads_submissions(logical_key,payload_hash,prepared,state,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                    (key,payload_hash,_json(prepared),'create_started',1,at,at))
                row=dict(db.execute('SELECT * FROM threads_submissions WHERE logical_key=?',(key,)).fetchone());db.execute('COMMIT');return row,True
            except BaseException:db.rollback();raise
    def transition(self,row,state,at,*,container_id=None,remote_id=None,reason_code=None):
        if state not in STATES:raise StoreError('threads_storage_error')
        with self._db(True) as db:
            cursor=db.execute('UPDATE threads_submissions SET state=?,container_id=?,remote_id=?,reason_code=?,version=version+1,updated_at=? WHERE logical_key=? AND version=? AND state=?',
                (state,container_id if container_id is not None else row['container_id'],remote_id if remote_id is not None else row['remote_id'],reason_code,at,row['logical_key'],row['version'],row['state']))
            if cursor.rowcount!=1:raise ConflictError()
        return self.get(row['logical_key'])


def _failed(reason):return dict(outcome='failed',evidence=dict(reason=reason,confirmed_not_submitted=True))
def _unknown(reason='threads_submission_uncertain',remote_id=None):
    result=dict(outcome='unknown',evidence=dict(reason=reason))
    if remote_id is not None:result['remote_id']=remote_id
    return result

def _submitted(remote_id):return dict(outcome='submitted',remote_id=remote_id,url=None,evidence={})


class ThreadsServices:
    def __init__(self,client,journal,clock,public_probe=None):
        if public_probe is not None and not callable(public_probe):raise StoreError('invalid_threads_public_probe')
        self.client=client;self.journal=journal;self.clock=clock;self.public_probe=public_probe
        self.before_write=lambda:None
    def _at(self):return utc(self.clock()).isoformat()
    def inspect(self,target):
        base=dict(platform='threads',target_id=None,login_subject=None,authenticated=False,
                  verification_method='immutable_threads_user_id',status='needs_review')
        if not isinstance(target,Mapping) or not _id(target.get('target_id')):return base
        try:
            row=self.client.me();subject=row.get('id') if isinstance(row,Mapping) else None
            if subject!=target['target_id'] or target.get('expected_login_subject') not in (None,subject):return base
            return {**base,'target_id':subject,'login_subject':subject,'authenticated':True,'status':'ready'}
        except Exception:return {**base,'status':'needs_auth'}
    def _mark_unknown(self,row,reason):
        try:self.journal.transition(row,'unknown',self._at(),reason_code=reason)
        except Exception:pass
        return _unknown(reason)
    def submit(self,prepared,target):
        try:normalized,key,payload_hash=_validate(prepared,target)
        except Exception:return _failed('threads_invalid_payload')
        if not self.inspect(target)['authenticated']:return _failed('target_unverified')
        try:
            with self.journal.hold(key):
                try:row,new=self.journal.claim(key,payload_hash,normalized,self._at())
                except StoreError as exc:
                    return _failed('threads_payload_conflict' if exc.code=='threads_payload_conflict' else 'threads_journal_unavailable')
                if row['state']=='submitted':return _submitted(row['remote_id']) if _id(row['remote_id']) else _unknown()
                if row['state']=='failed':return _failed('threads_container_failed')
                if row['state'] in ('publish_started','unknown') or row['state']=='create_started' and not new:return _unknown()
                if new:
                    try:self.before_write()
                    except Exception:
                        try:self.journal.transition(row,'failed',self._at(),reason_code='threads_write_blocked')
                        except Exception:pass  # POST는 아직 호출하지 않았다는 사실은 변하지 않는다.
                        return _failed('threads_write_blocked')
                    try:
                        result=self.client.create_text(target['target_id'],normalized['text'])
                        container=result.get('id') if isinstance(result,Mapping) else None
                        if not _id(container):return self._mark_unknown(row,'threads_create_unknown')
                        row=self.journal.transition(row,'container_ready',self._at(),container_id=container)
                    except Exception:return self._mark_unknown(row,'threads_create_unknown')
                if row['state']!='container_ready' or not _id(row['container_id']):return _unknown()
                try:status=self.client.container_status(row['container_id'])
                except Exception:return _failed('threads_container_not_ready')
                if not isinstance(status,Mapping) or status.get('id')!=row['container_id']:return _failed('threads_container_not_ready')
                state=status.get('status')
                if state in ('ERROR','EXPIRED'):
                    try:self.journal.transition(row,'failed',self._at(),reason_code='threads_container_failed')
                    except Exception:return _unknown()
                    return _failed('threads_container_failed')
                if state=='PUBLISHED':return self._mark_unknown(row,'threads_already_published')
                if state!='FINISHED':return _failed('threads_container_not_ready')
                try:self.before_write()
                except Exception:return _failed('threads_write_blocked')
                try:row=self.journal.transition(row,'publish_started',self._at())
                except Exception:return _unknown()
                remote_id=None
                try:
                    result=self.client.publish(target['target_id'],row['container_id'])
                    remote_id=result.get('id') if isinstance(result,Mapping) else None
                    if not _id(remote_id):return self._mark_unknown(row,'threads_publish_unknown')
                    self.journal.transition(row,'submitted',self._at(),remote_id=remote_id)
                    return _submitted(remote_id)
                except Exception:
                    self._mark_unknown(row,'threads_publish_unknown')
                    return _unknown('threads_publish_unknown',remote_id if _id(remote_id) else None)
        except Exception:
            # 잠금 경합/원장 오류에서는 원격 부재를 추정하거나 POST를 재실행하지 않는다.
            return _unknown()
    def _public_visibility(self,observation):
        # 소유자 API 읽기와 permalink는 익명 공개 접근의 증명이 아니다.
        if self.public_probe is None:return 'unknown'
        try:
            started=utc(self.clock())
            proof=self.public_probe({**observation,'media_sha256':[]})
            finished=utc(self.clock())
            if (not isinstance(proof,Mapping) or set(proof)!={'public','remote_id','target_id','body_sha256','url','checked_at'}
                    or proof['public'] is not True or any(proof[key]!=observation[key] for key in ('remote_id','target_id','body_sha256','url'))):return 'unknown'
            checked=utc(proof['checked_at'])
            if not started<=checked<=finished or finished-checked>timedelta(seconds=60):return 'unknown'
            return 'public'
        except Exception:return 'unknown'

    def read_post(self,target,remote_id):
        if not _id(remote_id) or not self.inspect(target)['authenticated']:return None
        try:
            row=self.client.read_post(remote_id)
            owner=row.get('owner') if isinstance(row,Mapping) else None
            text=row.get('text') if isinstance(row,Mapping) else None
            if (not isinstance(owner,Mapping) or owner.get('id')!=target['target_id'] or row.get('id')!=remote_id
                    or row.get('media_type')!='TEXT_POST' or type(text) is not str or not text.strip()
                    or len(text)>500 or '\x00' in text):return None
            created=utc(row.get('timestamp')).isoformat();url=row.get('permalink')
            if type(url) is not str or any(ord(c)<32 for c in url):return None
            parsed=urlsplit(url)
            if (parsed.scheme!='https' or parsed.hostname not in ('threads.net','www.threads.net','threads.com','www.threads.com')
                    or parsed.username or parsed.password or parsed.port not in (None,443) or parsed.query or parsed.fragment
                    or not re.fullmatch(r'/@[^/]+/post/[A-Za-z0-9_-]+',parsed.path)):return None
            observation=dict(platform='threads',remote_id=remote_id,target_id=owner['id'],created_at=created,text=text,
                body_sha256=_hash(text.encode('utf-8')),media_sha256=[],visibility='unknown',url=url,media_type='TEXT_POST')
            observation['visibility']=self._public_visibility(observation)
            return observation
        except Exception:return None
    def verify(self,target,remote_id):return self.read_post(target,remote_id)
    def lookup(self,target,attempt):
        if not isinstance(attempt,Mapping):return []
        result=attempt.get('result');remote_id=attempt.get('remote_id') or (result.get('remote_id') if isinstance(result,Mapping) else None)
        if not _id(remote_id):return []
        row=self.read_post(target,remote_id)
        return [row] if row else []
