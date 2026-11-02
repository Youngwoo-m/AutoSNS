"""명시 로컬 이미지 제작 원장. 생성자/조회는 무변이이며 실제 제작은 기본 비활성이다."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import struct
from uuid import UUID, uuid4
from .content_store import ConflictError, StoreError, MAX_ASSET_BYTES
from .models import ContractError, freeze

DB_NAME='image-tasks.sqlite3'
APPLICATION_ID=0x494d4147
SCHEMA_VERSION=1
PROVIDER_ID='local-card'
STATES=('started','unknown','rendered','completed','failed','content_changed')
COLUMNS=('task_id','intent_hash','owner_account_id','content_id','input_revision','manifest_hash','spec','spec_hash','provider_id','origin',
         'state','reason_code','path','sha256','size','width','height','output_revision','asset_id')
DDL='CREATE TABLE image_tasks(task_id TEXT PRIMARY KEY,intent_hash TEXT NOT NULL UNIQUE,owner_account_id TEXT NOT NULL,content_id TEXT NOT NULL,input_revision INTEGER NOT NULL,manifest_hash TEXT NOT NULL,spec TEXT NOT NULL,spec_hash TEXT NOT NULL,provider_id TEXT NOT NULL,origin TEXT NOT NULL,state TEXT NOT NULL,reason_code TEXT,path TEXT,sha256 TEXT,size INTEGER,width INTEGER,height INTEGER,output_revision INTEGER,asset_id TEXT)'

def _hash(raw):return hashlib.sha256(raw).hexdigest()
def _json(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def _invalid():raise ContractError('invalid_image_request')
def _text(value,limit,required=False):
    if type(value) is not str or len(value)>limit or '\x00' in value or (required and not value.strip()):_invalid()
    try:value.encode('utf-8')
    except UnicodeError:_invalid()
    return value

def validate_image_spec(spec):
    if not isinstance(spec,dict) or set(spec)!={'template','title','body','footer'} or spec['template'] not in ('card','steps'):_invalid()
    if not isinstance(spec['body'],list) or not 1<=len(spec['body'])<=6:_invalid()
    return dict(template=spec['template'],title=_text(spec['title'],80,True),
                body=[_text(text,120,True) for text in spec['body']],footer=_text(spec['footer'],120))

def _task_id(value):
    try:parsed=UUID(value)
    except (TypeError,ValueError,AttributeError):raise ContractError('invalid_task') from None
    if str(parsed)!=value or parsed.version!=4:raise ContractError('invalid_task')
    return value

def _public(row):
    return {**{k:row[k] for k in ('task_id','state','reason_code','content_id','input_revision','output_revision','asset_id')},
            'review_status':'not_checked'}

class ImageTaskStore:
    def __init__(self,root):self.root=Path(root).absolute();self._initialized=False
    def _path(self):
        path=self.root/DB_NAME
        if self.root.is_symlink() or path.is_symlink() or not path.resolve().is_relative_to(self.root.resolve()):
            raise ContractError('image_storage_unsafe')
        return path
    @staticmethod
    def _verify(db):
        if (db.execute('PRAGMA application_id').fetchone()[0]!=APPLICATION_ID or db.execute('PRAGMA user_version').fetchone()[0]!=1
            or tuple(row[1] for row in db.execute('PRAGMA table_info(image_tasks)'))!=COLUMNS
            or {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}!={'image_tasks'}):
            raise ContractError('image_storage_foreign')
    @contextmanager
    def _db(self,write=False):
        if write and not self._initialized:raise ContractError('image_storage_error')
        db=None
        try:
            db=sqlite3.connect(self._path().as_uri()+('?mode=rw' if write else '?mode=ro'),uri=True,timeout=5,isolation_level=None)
            db.row_factory=sqlite3.Row;self._verify(db);yield db
        except (sqlite3.Error,OSError,ValueError) as exc:
            if isinstance(exc,ContractError):raise
            raise ContractError('image_storage_error') from exc
        finally:
            if db is not None:db.close()
    def initialize(self):
        path=self._path();path.parent.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(path,isolation_level=None)
        try:
            db.execute('BEGIN IMMEDIATE')
            tables=db.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
            if not tables and db.execute('PRAGMA user_version').fetchone()[0]==0 and db.execute('PRAGMA application_id').fetchone()[0]==0:
                db.execute(DDL);db.execute(f'PRAGMA application_id={APPLICATION_ID}');db.execute('PRAGMA user_version=1')
            self._verify(db);db.execute('COMMIT')
        except BaseException:
            db.rollback();raise
        finally:db.close()
        self._initialized=True
    def list_for_content(self,content_id):
        if type(content_id) is not str or not content_id:_invalid()
        if not self._path().exists():return []
        with self._db() as db:return [_public(dict(r)) for r in db.execute('SELECT * FROM image_tasks WHERE content_id=? ORDER BY rowid',(content_id,))]
    def get(self,task_id):
        _task_id(task_id)
        if not self._path().exists():raise ContractError('image_task_not_found')
        with self._db() as db:
            row=db.execute('SELECT * FROM image_tasks WHERE task_id=?',(task_id,)).fetchone()
            if row is None:raise ContractError('image_task_not_found')
            return dict(row)
    def claim(self,snapshot,spec):
        raw=_json(spec);spec_hash=_hash(raw.encode())
        identity=dict(owner=snapshot['owner_account_id'],content_id=snapshot['id'],revision=snapshot['revision'],manifest_hash=snapshot['manifest_hash'],provider_id=PROVIDER_ID,spec_hash=spec_hash)
        intent=_hash(_json(identity).encode())
        with self._db(True) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                old=db.execute('SELECT * FROM image_tasks WHERE intent_hash=?',(intent,)).fetchone()
                if old is not None:db.execute('COMMIT');return dict(old),False
                task_id=str(uuid4())
                db.execute('INSERT INTO image_tasks(task_id,intent_hash,owner_account_id,content_id,input_revision,manifest_hash,spec,spec_hash,provider_id,origin,state) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (task_id,intent,snapshot['owner_account_id'],snapshot['id'],snapshot['revision'],snapshot['manifest_hash'],raw,spec_hash,PROVIDER_ID,'generated','started'))
                row=dict(db.execute('SELECT * FROM image_tasks WHERE task_id=?',(task_id,)).fetchone());db.execute('COMMIT');return row,True
            except BaseException:db.rollback();raise
    def transition(self,task_id,from_state,**fields):
        if not fields or not set(fields)<={'state','reason_code','path','sha256','size','width','height','output_revision','asset_id'}:raise ContractError('image_storage_error')
        if 'state' in fields and fields['state'] not in STATES:raise ContractError('image_storage_error')
        with self._db(True) as db:
            keys=list(fields);db.execute('UPDATE image_tasks SET '+','.join(k+'=?' for k in keys)+' WHERE task_id=? AND state=?',tuple(fields[k] for k in keys)+(task_id,from_state))
        return self.get(task_id)
    def artifact_root(self,task_id,create=False):
        _task_id(task_id);root=self.root/'image-artifacts'/task_id
        if self.root.is_symlink() or root.parent.is_symlink() or root.is_symlink() or not root.resolve().is_relative_to(self.root.resolve()):raise ContractError('image_storage_unsafe')
        if create:
            if not self._initialized:raise ContractError('image_storage_error')
            root.mkdir(parents=True,exist_ok=False)
        return root
    @contextmanager
    def task_lock(self,task_id):
        root=self.artifact_root(task_id);fd=os.open(root/'.lock',os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
        try:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise ContractError('image_task_busy') from None
            yield
        finally:os.close(fd)

class ImageTaskService:
    def __init__(self,store,content_store,runner=None,enabled=False):
        if store.root!=Path(content_store.root).absolute() or type(enabled) is not bool:raise ContractError('invalid_image_registration')
        self.store=store;self.content_store=content_store;self.runner=runner;self.enabled=enabled
    def capabilities(self):return dict(provider_id=PROVIDER_ID,service_available=callable(self.runner),execution_enabled=self.enabled and callable(self.runner),review_status='not_checked')
    def list_for_content(self,content_id):return self.store.list_for_content(content_id)
    def _enabled(self):
        if not self.enabled:raise ContractError('image_disabled')
    def create(self,content_id,expected_revision,spec):
        self._enabled()
        if type(content_id) is not str or not content_id or type(expected_revision) is not int or expected_revision<1:_invalid()
        normalized=validate_image_spec(spec)
        if not callable(self.runner):raise ContractError('image_renderer_unavailable')
        snapshot=self.content_store.get(content_id,expected_revision)
        if snapshot is None:raise ContractError('image_content_not_found')
        row,new=self.store.claim(snapshot,normalized)
        if not new:return _public(row)
        head=self.content_store.get(content_id)
        if not head or head['revision']!=expected_revision or head['manifest_hash']!=snapshot['manifest_hash']:
            return _public(self.store.transition(row['task_id'],'started',state='content_changed',reason_code='content_changed'))
        try:root=self.store.artifact_root(row['task_id'],True)
        except Exception:return _public(self.store.transition(row['task_id'],'started',state='failed',reason_code='image_storage_error'))
        with self.store.task_lock(row['task_id']):
            try:result=self.runner(freeze(normalized),owner_account_id=snapshot['owner_account_id'],artifact_root=root)
            except Exception:return _public(self.store.transition(row['task_id'],'started',state='unknown',reason_code='image_render_unknown'))
            try:raw,path=self._validate_output(row,result)
            except Exception:return _public(self.store.transition(row['task_id'],'started',state='failed',reason_code='image_output_invalid'))
            row=self.store.transition(row['task_id'],'started',state='rendered',path=str(path.relative_to(root)),sha256=_hash(raw),size=len(raw),width=1080,height=1350)
            return _public(self._ingest(row))
    def _validate_output(self,row,result):
        if not isinstance(result,dict) or set(result)!={'path','sha256','size','width','height'}:raise ContractError('image_output_invalid')
        root=self.store.artifact_root(row['task_id']);path=Path(result['path'])
        if (not path.is_absolute() or not path.is_relative_to(root) or path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve())
                or any(parent.is_symlink() for parent in path.parents if parent==root or root in parent.parents)):
            raise ContractError('image_output_invalid')
        fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
        with os.fdopen(fd,'rb') as f:raw=f.read(MAX_ASSET_BYTES+1)
        if (len(raw)>MAX_ASSET_BYTES or len(raw)<33 or raw[:8]!=b'\x89PNG\r\n\x1a\n' or raw[8:16]!=b'\x00\x00\x00\rIHDR'
                or struct.unpack('>II',raw[16:24])!=(1080,1350) or type(result['size']) is not int or result['size']!=len(raw)
                or result['sha256']!=_hash(raw) or type(result['width']) is not int or result['width']!=1080
                or type(result['height']) is not int or result['height']!=1350):raise ContractError('image_output_invalid')
        return raw,path
    def resume(self,task_id):
        self._enabled();row=self.store.get(task_id)
        if row['state']!='rendered':return _public(row)
        with self.store.task_lock(task_id):return _public(self._ingest(self.store.get(task_id)))
    def _ingest(self,row):
        if row['state']!='rendered':return row
        try:
            root=self.store.artifact_root(row['task_id'])
            raw,_=self._validate_output(row,dict(path=str(root/row['path']),sha256=row['sha256'],size=row['size'],width=row['width'],height=row['height']))
        except Exception:return self.store.transition(row['task_id'],'rendered',state='failed',reason_code='image_artifact_invalid')
        filename='local-card-'+row['task_id']+'.png'
        for _ in range(3):
            try:
                head=self.content_store.get(row['content_id'])
                if not head or head['owner_account_id']!=row['owner_account_id']:raise ConflictError()
                if head['revision']==row['input_revision']:
                    if head['manifest_hash']!=row['manifest_hash']:raise ConflictError()
                    self.content_store.add_asset(row['content_id'],row['input_revision'],filename,'image/png',raw)
                    continue
                if head['revision']!=row['input_revision']+1:raise ConflictError()
                base=self.content_store.get(row['content_id'],row['input_revision'])
                if base['manifest_hash']!=row['manifest_hash'] or any(head[k]!=base[k] for k in ('owner_account_id','title','kind','series','status','original','variants','sources')):raise ConflictError()
                if len(head['assets'])!=len(base['assets'])+1 or head['assets'][:-1]!=base['assets']:raise ConflictError()
                asset=head['assets'][-1]
                if any(asset[k]!=v for k,v in dict(filename=filename,media_type='image/png',sha256=row['sha256'],size=row['size']).items()):raise ConflictError()
                registered,registered_raw=self.content_store.read_asset(row['content_id'],head['revision'],asset['id'])
                if registered_raw!=raw:raise ConflictError()
                return self.store.transition(row['task_id'],'rendered',state='completed',reason_code=None,output_revision=head['revision'],asset_id=asset['id'])
            except ConflictError:
                return self.store.transition(row['task_id'],'rendered',state='content_changed',reason_code='content_changed')
            except Exception:return self.store.get(row['task_id'])
        return self.store.get(row['task_id'])
