"""서버가 주입한 페이지 권한 증명·공개 관측과 Facebook 단일 POST 원장.

개인/학과 namespace는 Facebook 개인 타임라인 게시가 아니다. Page token의 숫자
/me 응답만으로 페이지 유형·tasks·게시 권한을 추정하지 않는다. 기본 권한 증명과
공개 probe는 없으며, 실제 전송·앱·권한·비용 정책을 이 모듈에서 활성화하지 않는다.
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
from .facebook_payloads import PREPARED_KEYS,NUMERIC_ID,validate_facebook_text

DB_NAME='facebook-submissions.sqlite3'
APPLICATION_ID=0x46425047
SCHEMA_VERSION=1
STATES=('started','submitted','unknown','known_not_posted')
COLUMNS=('logical_key','payload_hash','prepared','state','remote_id','reason_code','version','created_at','updated_at')
_POST=re.compile(r'([0-9]{1,64})_([0-9]{1,64})')
DDL='CREATE TABLE facebook_submissions(logical_key TEXT PRIMARY KEY,payload_hash TEXT NOT NULL,prepared TEXT NOT NULL,state TEXT NOT NULL,remote_id TEXT,reason_code TEXT,version INTEGER NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)'


def _json(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def _hash(raw):return hashlib.sha256(raw).hexdigest()
def _id(value):return type(value) is str and NUMERIC_ID.fullmatch(value) is not None

def _post(value,page):
    match=_POST.fullmatch(value) if type(value) is str else None
    return match is not None and match.group(1)==page

def _validate(prepared,target):
    if not isinstance(prepared,Mapping) or set(prepared)!=set(PREPARED_KEYS) or not isinstance(target,Mapping):raise ValueError()
    if prepared['platform']!='facebook' or target.get('platform','facebook')!='facebook':raise ValueError()
    if prepared['owner_account_id'] not in ('personal','dept') or prepared['destination_account_id'] not in ('personal','dept'):raise ValueError()
    if (prepared['connection_id']!=prepared['destination_account_id']+'.facebook'
            or target.get('connection_id',prepared['connection_id'])!=prepared['connection_id']
            or not _id(prepared['target_id']) or prepared['target_id']!=target.get('target_id')):raise ValueError()
    if type(prepared['content_revision']) is not int or prepared['content_revision']<1:raise ValueError()
    for name in ('content_id','manifest_hash','publication_purpose','schedule_slot'):
        value=prepared[name]
        if type(value) is not str or not value.strip() or len(value)>500 or any(ord(c)<32 for c in value):raise ValueError()
    text=validate_facebook_text(prepared['text'])
    if prepared['body_sha256']!=_hash(text.encode('utf-8')) or prepared['media_sha256'] not in ([],()):raise ValueError()
    normalized={**prepared,'media_sha256':[]}
    identity={name:normalized[name] for name in ('owner_account_id','destination_account_id','connection_id','target_id',
        'content_id','content_revision','publication_purpose','schedule_slot')}
    return normalized,_hash(_json(identity).encode()),_hash(_json(normalized).encode())

def _fresh(checked,started,finished):
    checked=utc(checked)
    return started<=checked<=finished and finished-checked<=timedelta(seconds=60)


class FacebookJournal:
    def __init__(self,root):self.root=Path(root).absolute();self._initialized=False
    def _path(self):
        path=self.root/DB_NAME
        if self.root.is_symlink() or path.is_symlink() or (path.exists() and not path.is_file()) or not path.resolve().is_relative_to(self.root.resolve()):
            raise StoreError('facebook_storage_error')
        return path
    @staticmethod
    def _verify(db):
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if (db.execute('PRAGMA application_id').fetchone()[0]!=APPLICATION_ID or db.execute('PRAGMA user_version').fetchone()[0]!=SCHEMA_VERSION
                or tables!={'facebook_submissions'} or tuple(r[1] for r in db.execute('PRAGMA table_info(facebook_submissions)'))!=COLUMNS):
            raise StoreError('facebook_storage_error')
    @contextmanager
    def _db(self,write=False):
        if write and not self._initialized:raise StoreError('facebook_storage_error')
        db=None
        try:
            db=sqlite3.connect(self._path().as_uri()+('?mode=rw' if write else '?mode=ro'),uri=True,timeout=5,isolation_level=None)
            db.row_factory=sqlite3.Row;self._verify(db);yield db
        except StoreError:raise
        except (sqlite3.Error,OSError,ValueError,UnicodeError):raise StoreError('facebook_storage_error') from None
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
            raise StoreError('facebook_storage_error') from None
        finally:
            if db is not None:db.close()
        self._initialized=True
    @contextmanager
    def hold(self,key):
        if not self._initialized or not re.fullmatch(r'[a-f0-9]{64}',key):raise StoreError('facebook_storage_error')
        self._path();folder=self.root/'facebook-submission-locks'
        if folder.is_symlink():raise StoreError('facebook_storage_error')
        folder.mkdir(exist_ok=True);fd=os.open(folder/key,os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
        try:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise StoreError('facebook_submission_busy') from None
            yield
        finally:os.close(fd)
    def get(self,key):
        if not self._path().is_file():return None
        with self._db() as db:
            row=db.execute('SELECT * FROM facebook_submissions WHERE logical_key=?',(key,)).fetchone()
            return dict(row) if row else None
    def claim(self,key,payload_hash,prepared,at):
        with self._db(True) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row=db.execute('SELECT * FROM facebook_submissions WHERE logical_key=?',(key,)).fetchone()
                if row is not None:
                    if row['payload_hash']!=payload_hash or row['prepared']!=_json(prepared):raise StoreError('facebook_payload_conflict')
                    db.execute('COMMIT');return dict(row),False
                db.execute('INSERT INTO facebook_submissions(logical_key,payload_hash,prepared,state,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                    (key,payload_hash,_json(prepared),'started',1,at,at))
                row=dict(db.execute('SELECT * FROM facebook_submissions WHERE logical_key=?',(key,)).fetchone());db.execute('COMMIT');return row,True
            except BaseException:db.rollback();raise
    def transition(self,row,state,at,*,remote_id=None,reason_code=None):
        if state not in STATES:raise StoreError('facebook_storage_error')
        allowed={'started':{'submitted','unknown','known_not_posted'},'known_not_posted':{'started'}}
        if state not in allowed.get(row['state'],set()):raise ConflictError()
        with self._db(True) as db:
            cursor=db.execute('UPDATE facebook_submissions SET state=?,remote_id=?,reason_code=?,version=version+1,updated_at=? WHERE logical_key=? AND version=? AND state=?',
                (state,remote_id if remote_id is not None else row['remote_id'],reason_code,at,row['logical_key'],row['version'],row['state']))
            if cursor.rowcount!=1:raise ConflictError()
        return self.get(row['logical_key'])


def _failed(reason):return dict(outcome='failed',evidence=dict(reason=reason,confirmed_not_submitted=True))
def _unknown(reason='facebook_submission_uncertain',remote_id=None):
    result=dict(outcome='unknown',evidence=dict(reason=reason))
    if remote_id is not None:result['remote_id']=remote_id
    return result

def _submitted(remote_id):return dict(outcome='submitted',remote_id=remote_id,url=None,evidence={})


class FacebookServices:
    def __init__(self,client,journal,clock,public_probe=None,page_authorizer=None):
        if not callable(clock) or any(value is not None and not callable(value) for value in (public_probe,page_authorizer)):
            raise StoreError('invalid_facebook_service_registration')
        self.client=client;self.journal=journal;self.clock=clock;self.public_probe=public_probe;self.page_authorizer=page_authorizer
        self.before_write=lambda:None
    def _at(self):return utc(self.clock()).isoformat()
    def inspect(self,target):
        base=dict(platform='facebook',target_id=None,login_subject=None,authenticated=False,
                  verification_method='immutable_facebook_page_id_and_tasks',status='needs_review')
        if (self.page_authorizer is None or not isinstance(target,Mapping) or not _id(target.get('target_id'))
                or target.get('platform','facebook')!='facebook'):return base
        try:
            started=utc(self.clock());identity=self.client.me()
        except Exception:return {**base,'status':'needs_auth'}
        try:
            if not isinstance(identity,Mapping) or identity.get('id')!=target['target_id']:return base
            proof=self.page_authorizer(dict(target),dict(identity));finished=utc(self.clock())
            if (not isinstance(proof,Mapping) or set(proof)!={'page_id','token_subject','login_subject','can_publish','tasks_checked','checked_at','page_type'}
                    or proof['page_id']!=target['target_id'] or proof['token_subject']!=target['target_id']
                    or proof['can_publish'] is not True or proof['tasks_checked'] is not True or proof['page_type']!='page'
                    or type(proof['login_subject']) is not str or not proof['login_subject'].strip()
                    or len(proof['login_subject'])>500 or any(ord(c)<32 for c in proof['login_subject'])
                    or target.get('expected_login_subject') not in (None,proof['login_subject'])
                    or not _fresh(proof['checked_at'],started,finished)):return base
            return {**base,'authenticated':True,'target_id':target['target_id'],'login_subject':proof['login_subject'],'status':'ready'}
        except Exception:return base
    def _mark_unknown(self,row,reason):
        try:self.journal.transition(row,'unknown',self._at(),reason_code=reason)
        except Exception:pass
    def submit(self,prepared,target):
        try:normalized,key,payload_hash=_validate(prepared,target)
        except Exception:return _failed('facebook_invalid_payload')
        if not self.inspect(target)['authenticated']:return _failed('target_unverified')
        try:
            with self.journal.hold(key):
                try:row,new=self.journal.claim(key,payload_hash,normalized,self._at())
                except StoreError as exc:return _failed('facebook_payload_conflict' if exc.code=='facebook_payload_conflict' else 'facebook_journal_unavailable')
                if row['state']=='submitted':return _submitted(row['remote_id']) if _post(row['remote_id'],target['target_id']) else _unknown()
                if row['state']=='known_not_posted':
                    try:row=self.journal.transition(row,'started',self._at());new=True
                    except Exception:return _unknown()
                if row['state']!='started' or not new:return _unknown()
                try:self.before_write()
                except Exception:
                    try:self.journal.transition(row,'known_not_posted',self._at(),reason_code='facebook_write_blocked')
                    except Exception:pass
                    return _failed('facebook_write_blocked')
                remote_id=None
                try:
                    response=self.client.create_text(target['target_id'],normalized['text'])
                    remote_id=response.get('id') if isinstance(response,Mapping) else None
                    if not _post(remote_id,target['target_id']):
                        self._mark_unknown(row,'facebook_publish_unknown');return _unknown('facebook_publish_unknown')
                    self.journal.transition(row,'submitted',self._at(),remote_id=remote_id)
                    return _submitted(remote_id)
                except Exception:
                    self._mark_unknown(row,'facebook_publish_unknown')
                    return _unknown('facebook_publish_unknown',remote_id if _post(remote_id,target['target_id']) else None)
        except Exception:return _unknown()
    def _public_visibility(self,observation):
        if self.public_probe is None:return 'unknown'
        try:
            started=utc(self.clock());proof=self.public_probe({**observation,'media_sha256':[]});finished=utc(self.clock())
            if (not isinstance(proof,Mapping) or set(proof)!={'public','remote_id','target_id','body_sha256','url','checked_at'}
                    or proof['public'] is not True or any(proof[key]!=observation[key] for key in ('remote_id','target_id','body_sha256','url'))
                    or not _fresh(proof['checked_at'],started,finished)):return 'unknown'
            return 'public'
        except Exception:return 'unknown'
    def read_post(self,target,remote_id):
        if not isinstance(target,Mapping) or not _id(target.get('target_id')) or not _post(remote_id,target['target_id']):return None
        if not self.inspect(target)['authenticated']:return None
        try:
            row=self.client.read_post(remote_id)
            if (not isinstance(row,Mapping) or row.get('id')!=remote_id or not isinstance(row.get('from'),Mapping)
                    or row['from'].get('id')!=target['target_id'] or type(row.get('is_published')) is not bool
                    or type(row.get('is_hidden')) is not bool):return None
            # 실제 attachments 읽기의 빈 목록만 미디어 없음의 근거다. 필드 누락을
            # 빈 목록으로 채우거나 승인 원고의 자산 제외를 원격 증거로 쓰지 않는다.
            attachments=row.get('attachments')
            if not isinstance(attachments,(list,tuple)) or len(attachments)!=0:return None
            text=validate_facebook_text(row.get('message'));created=utc(row.get('created_time')).isoformat();url=row.get('permalink_url')
            if type(url) is not str or not url or any(ord(c)<=32 or ord(c)==127 for c in url):return None
            parsed=urlsplit(url)
            if (parsed.scheme!='https' or parsed.netloc not in ('facebook.com','www.facebook.com')
                    or parsed.hostname not in ('facebook.com','www.facebook.com') or parsed.username or parsed.password
                    or parsed.port is not None or parsed.query or parsed.fragment or not parsed.path or parsed.path=='/'):return None
            observation=dict(platform='facebook',remote_id=remote_id,target_id=target['target_id'],created_at=created,
                text=text,body_sha256=_hash(text.encode('utf-8')),media_sha256=[],visibility='unknown',url=url)
            if row['is_published'] is False or row['is_hidden'] is True:observation['visibility']='private'
            else:observation['visibility']=self._public_visibility(observation)
            return observation
        except Exception:return None
    def verify(self,target,remote_id):return self.read_post(target,remote_id)
    def lookup(self,target,attempt):
        if not isinstance(attempt,Mapping):return []
        result=attempt.get('result');remote_id=attempt.get('remote_id') or (result.get('remote_id') if isinstance(result,Mapping) else None)
        if remote_id is None:return []
        observation=self.read_post(target,remote_id)
        return [observation] if observation is not None else []
