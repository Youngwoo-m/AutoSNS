"""Instagram 다단계 전송의 명시 재개 원장. 기본 권한·매체·검토 공급자는 없다.

SQLite/OS 잠금과 CAS로 원격 쓰기 직전 상태를 영속한다. 응답 불명확 단계는 자동
재전송하지 않는다. 전달 영수증은 private DB에만 보관하며 실제 공개 검증·원격 해시
증명은 구현하지 않는다. 이 경계는 독립 원고 검토·발행 permit·런타임 STOP을 대신하지
않는다. before_write는 신뢰된 런타임이 STOP/permit 검사를 주입할 별도 경계다.
"""
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import asdict
from datetime import timedelta
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from common.operations.content_store import StoreError,ConflictError
from common.operations.models import thaw,freeze
from common.operations.runtime_models import PublicationContext,utc
from .instagram_payloads import NUMERIC_ID
from .instagram_media_sources import InstagramHostedMedia,_binding
from .instagram_client import _url

DB_NAME='instagram-submissions.sqlite3'
APPLICATION_ID=0x4947534a
SCHEMA_VERSION=1
COLUMNS=('logical_key','payload_hash','prepared','state','remote_id','reason_code','version','created_at','updated_at','data','context_hash')
DDL='CREATE TABLE instagram_submissions(logical_key TEXT PRIMARY KEY,payload_hash TEXT NOT NULL,prepared TEXT NOT NULL,state TEXT NOT NULL,remote_id TEXT,reason_code TEXT,version INTEGER NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,data TEXT NOT NULL,context_hash TEXT NOT NULL)'
def _json(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def _hash(value):return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()
def _id(value):return type(value) is str and NUMERIC_ID.fullmatch(value) is not None
class InstagramJournal:
    def __init__(self,root):self.root=Path(root).absolute();self._initialized=False
    def _path(self):
        path=self.root/DB_NAME
        if self.root.is_symlink() or path.is_symlink() or (path.exists() and not path.is_file()) or not path.resolve().is_relative_to(self.root.resolve()):
            raise StoreError('instagram_storage_error')
        return path
    @staticmethod
    def _verify(db):
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if (db.execute('PRAGMA application_id').fetchone()[0]!=APPLICATION_ID or db.execute('PRAGMA user_version').fetchone()[0]!=SCHEMA_VERSION
                or tables!={'instagram_submissions'} or tuple(r[1] for r in db.execute('PRAGMA table_info(instagram_submissions)'))!=COLUMNS):
            raise StoreError('instagram_storage_error')
    @contextmanager
    def _db(self,write=False):
        if write and not self._initialized:raise StoreError('instagram_storage_error')
        db=None
        try:
            db=sqlite3.connect(self._path().as_uri()+('?mode=rw' if write else '?mode=ro'),uri=True,timeout=5,isolation_level=None)
            db.row_factory=sqlite3.Row;self._verify(db);yield db
        except StoreError:raise
        except (sqlite3.Error,OSError,ValueError,UnicodeError):raise StoreError('instagram_storage_error') from None
        finally:
            if db is not None:db.close()
    def initialize(self):
        db=None
        try:
            path=self._path();path.parent.mkdir(parents=True,exist_ok=True,mode=0o700);db=sqlite3.connect(path,isolation_level=None,timeout=5)
            db.execute('BEGIN IMMEDIATE')
            objects=db.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
            if not objects and db.execute('PRAGMA application_id').fetchone()[0]==0 and db.execute('PRAGMA user_version').fetchone()[0]==0:
                db.execute(DDL);db.execute(f'PRAGMA application_id={APPLICATION_ID}');db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
            self._verify(db);db.execute('COMMIT');os.chmod(path,0o600)
        except StoreError:
            if db is not None:db.rollback()
            raise
        except (sqlite3.Error,OSError):
            if db is not None:db.rollback()
            raise StoreError('instagram_storage_error') from None
        finally:
            if db is not None:db.close()
        self._initialized=True
    @contextmanager
    def hold(self,key):
        if not self._initialized or not re.fullmatch(r'[a-f0-9]{64}',key):raise StoreError('instagram_storage_error')
        self._path();folder=self.root/'instagram-submission-locks'
        if folder.is_symlink():raise StoreError('instagram_storage_error')
        folder.mkdir(exist_ok=True,mode=0o700);fd=os.open(folder/key,os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
        try:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise StoreError('instagram_submission_busy') from None
            yield
        finally:os.close(fd)
    def get(self,key):
        if not self._path().is_file():return None
        with self._db() as db:
            row=db.execute('SELECT * FROM instagram_submissions WHERE logical_key=?',(key,)).fetchone()
            return dict(row) if row else None
    def claim(self,key,payload_hash,prepared,at,context_hash=''):
        with self._db(True) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row=db.execute('SELECT * FROM instagram_submissions WHERE logical_key=?',(key,)).fetchone()
                if row is not None:
                    if row['payload_hash']!=payload_hash or row['prepared']!=_json(prepared):raise StoreError('instagram_payload_conflict')
                    db.execute('COMMIT');return dict(row),False
                db.execute('INSERT INTO instagram_submissions(logical_key,payload_hash,prepared,state,version,created_at,updated_at,data,context_hash) VALUES(?,?,?,?,?,?,?,?,?)',
                    (key,payload_hash,_json(prepared),'staging_started',1,at,at,'{}',context_hash))
                row=dict(db.execute('SELECT * FROM instagram_submissions WHERE logical_key=?',(key,)).fetchone());db.execute('COMMIT');return row,True
            except BaseException:db.rollback();raise
    def save(self,row,state,data,at,*,remote_id=None):
        allowed={'staging_blocked':{'staging_started'},'staging_started':{'ready','unknown','staging_blocked'},'ready':{'ready','publish_started','unknown','failed'},
                 'publish_started':{'submitted','unknown'}}
        if state not in allowed.get(row['state'],set()):raise ConflictError()
        with self._db(True) as db:
            cursor=db.execute('UPDATE instagram_submissions SET state=?,data=?,remote_id=?,version=version+1,updated_at=? WHERE logical_key=? AND version=? AND state=?',
                (state,_json(data),remote_id if remote_id is not None else row['remote_id'],at,row['logical_key'],row['version'],row['state']))
            if cursor.rowcount!=1:raise ConflictError()
        return self.get(row['logical_key'])

def _failed(reason):return dict(outcome='failed',url=None,evidence=dict(reason=reason,confirmed_not_submitted=True))
def _unknown(reason='instagram_submission_uncertain',remote_id=None):
    result=dict(outcome='unknown',url=None,evidence=dict(reason=reason))
    if remote_id is not None:result['remote_id']=remote_id
    return result
def _submitted(identifier):return dict(outcome='submitted',remote_id=identifier,url=None,evidence={})

class _Blocked(Exception):pass
class _Uncertain(Exception):pass
class _Pending(Exception):pass
class _Terminal(Exception):pass

class InstagramServices:
    def __init__(self,client,journal,clock,*,media_factory=None,account_authorizer=None,review_guard=None):
        factory=media_factory if callable(media_factory) else getattr(media_factory,'prepare',None)
        if (not callable(clock) or media_factory is not None and not callable(factory)
                or any(value is not None and not callable(value) for value in (account_authorizer,review_guard))):
            raise StoreError('invalid_instagram_service_registration')
        self.client=client;self.journal=journal;self.clock=clock;self.media_factory=factory
        self.account_authorizer=account_authorizer;self.review_guard=review_guard;self.before_write=lambda:None
    def _at(self):return utc(self.clock()).isoformat()
    def inspect(self,target):
        base=dict(platform='instagram',target_id=None,login_subject=None,authenticated=False,
                  verification_method='immutable_instagram_id_and_professional_permission',status='needs_review')
        if (self.account_authorizer is None or not isinstance(target,Mapping) or not _id(target.get('target_id'))
                or target.get('platform','instagram')!='instagram' or type(target.get('expected_login_subject')) is not str
                or not target['expected_login_subject'].strip()):return base
        try:
            started=utc(self.clock());identity=self.client.inspect_account(target['target_id'])
            if not isinstance(identity,Mapping) or identity.get('id')!=target['target_id']:return base
            proof=self.account_authorizer(dict(target),dict(identity));finished=utc(self.clock())
            if (not isinstance(proof,Mapping) or set(proof)!={'target_id','login_subject','professional','can_publish','checked_at','login_mode'}
                    or proof['target_id']!=target['target_id'] or proof['login_subject']!=target['expected_login_subject']
                    or proof['professional'] is not True or proof['can_publish'] is not True or proof['login_mode']!='facebook_login'
                    or not started<=utc(proof['checked_at'])<=finished or finished-started>timedelta(seconds=60)):
                return base
            return {**base,'authenticated':True,'target_id':target['target_id'],'login_subject':proof['login_subject'],'status':'ready'}
        except Exception:return base
    def _guard(self,ctx,prepared,receipts=()):
        try:
            now=utc(self.clock())
            if not ctx.auth_checked_at<=now<ctx.auth_expires_at or self.review_guard(ctx,freeze(prepared)) is not True:raise _Blocked()
            if any(utc(r['expires_at'])<=now+timedelta(minutes=5) for r in receipts):raise _Blocked()
            self.before_write()
            # STOP/permit hook 실행 중 시계가 진행되어도 만료된 lease로 전송하지 않는다.
            now=utc(self.clock())
            if (not ctx.auth_checked_at<=now<ctx.auth_expires_at or self.review_guard(ctx,freeze(prepared)) is not True
                    or any(utc(r['expires_at'])<=now+timedelta(minutes=5) for r in receipts)):raise _Blocked()
        except Exception:raise _Blocked() from None
    def _receipts(self,ctx,prepared,values):
        if type(values) is not tuple or len(values)!=len(prepared['assets']):raise ValueError()
        rows=[];now=utc(self.clock())
        for i,(receipt,asset) in enumerate(zip(values,prepared['assets'])):
            if not isinstance(receipt,InstagramHostedMedia):raise ValueError()
            expected=dict(context_hash=ctx.context_hash,owner_account_id=ctx.owner_account_id,destination_account_id=ctx.destination_account_id,
                connection_id=ctx.connection_id,target_id=ctx.target_id,content_id=ctx.content_id,content_revision=ctx.content_revision,
                manifest_hash=ctx.manifest_hash,position=i,asset_id=asset['id'],asset_sha256=asset['sha256'],asset_size=asset['size'],media_type=asset['media_type'])
            if (any(getattr(receipt,k)!=v for k,v in expected.items()) or type(receipt.position) is not int
                    or type(receipt.asset_size) is not int or type(receipt.content_revision) is not int
                    or type(receipt.receipt_id) is not str or re.fullmatch(r'[A-Za-z0-9_-]{1,128}',receipt.receipt_id) is None
                    or not now+timedelta(minutes=5)<utc(receipt.expires_at)<=now+timedelta(hours=24)):
                raise ValueError()
            _url(receipt.url)
            row=asdict(receipt);row['expires_at']=utc(receipt.expires_at).isoformat();rows.append(row)
        return rows
    def _mark(self,row,state,data,remote_id=None):
        return self.journal.save(row,state,data,self._at(),remote_id=remote_id)
    def _uncertain(self,row,data,remote_id=None):
        try:self._mark(row,'unknown',data,remote_id)
        except Exception:pass
        return _unknown(remote_id=remote_id)
    def submit(self,ctx,prepared,target):
        if self.media_factory is None or self.account_authorizer is None or self.review_guard is None:return _failed('instagram_service_unconfigured')
        try:
            if not isinstance(ctx,PublicationContext):raise ValueError()
            prepared=thaw(_binding(ctx,prepared))
            if (not isinstance(target,Mapping) or target.get('platform','instagram')!='instagram'
                    or target.get('target_id')!=ctx.target_id or ctx.connection_id!=ctx.destination_account_id+'.instagram'
                    or target.get('connection_id',ctx.connection_id)!=ctx.connection_id):raise ValueError()
            # 검토·인증 만료는 전송 시작 전에 확인하되 STOP hook은 각 실제 쓰기 직전에 별도로 호출한다.
            if self.review_guard(ctx,freeze(prepared)) is not True or not ctx.auth_checked_at<=utc(self.clock())<ctx.auth_expires_at:
                return _failed('instagram_write_blocked')
            key=_hash({name:prepared[name] for name in ('owner_account_id','destination_account_id','connection_id','target_id','content_id','content_revision','publication_purpose','schedule_slot')})
            payload_hash=_hash(prepared)
        except Exception:return _failed('instagram_invalid_payload')
        if not self.inspect(target)['authenticated']:return _failed('target_unverified')
        try:
            with self.journal.hold(key):
                try:row,new=self.journal.claim(key,payload_hash,prepared,self._at(),ctx.context_hash)
                except Exception:return _failed('instagram_journal_unavailable_or_conflict')
                if row['state']=='submitted':return _submitted(row['remote_id']) if _id(row['remote_id']) else _unknown()
                if row['context_hash']!=ctx.context_hash:return _failed('instagram_context_reauthorization_required')
                if row['state']=='staging_blocked':
                    # 외부 공급자를 호출하기 전 차단된 확정 기록만 명시 재개한다.
                    try:row=self._mark(row,'staging_started',{});new=True
                    except Exception:return _failed('instagram_journal_unavailable')
                if row['state'] in ('unknown','publish_started') or row['state']=='staging_started' and not new:
                    return _unknown(remote_id=row['remote_id'])
                if row['state']=='failed':return _failed('instagram_container_failed')
                try:data=json.loads(row['data'])
                except Exception:return _unknown()
                if new:
                    try:self._guard(ctx,prepared)
                    except _Blocked:
                        try:self._mark(row,'staging_blocked',data)
                        except Exception:return self._uncertain(row,data)
                        return _failed('instagram_write_blocked')
                    # 공급자 진입 이후에는 어떤 예외도 재stage 가능한 차단으로 취급하지 않는다.
                    try:
                        values=self.media_factory(ctx,freeze(prepared))
                        receipts=self._receipts(ctx,prepared,values)
                        data={'receipts':receipts,'steps':{}}
                        row=self._mark(row,'ready',data)
                    except Exception:return self._uncertain(row,data)
                # 중단 기록에 이미 started가 있으면 원격 수락 여부를 추측하거나 재시도하지 않는다.
                if (type(data) is not dict or set(data)!={'receipts','steps'} or type(data['steps']) is not dict
                        or any(type(step) is not dict or step.get('state')!='ready' for step in data['steps'].values())):
                    return self._uncertain(row,data)
                receipts=data['receipts']
                # private DB receipt도 최초 문맥과 자산 순서에 다시 결속한다.
                try:
                    loaded=tuple(InstagramHostedMedia(**{**r,'expires_at':utc(r['expires_at'])}) for r in receipts)
                    self._receipts(ctx,prepared,loaded)
                except Exception:return _failed('instagram_media_lease_invalid')
                def container(name,create):
                    nonlocal row
                    step=data['steps'].get(name)
                    if step is None:
                        self._guard(ctx,prepared,receipts)
                        data['steps'][name]={'state':'started'}
                        try:row=self._mark(row,'ready',data)
                        except Exception:raise _Uncertain() from None
                        try:
                            response=create();identifier=response.get('id') if isinstance(response,Mapping) else None
                            if not _id(identifier):raise ValueError()
                        except Exception:raise _Uncertain() from None
                        data['steps'][name]={'state':'ready','id':identifier}
                        try:row=self._mark(row,'ready',data)
                        except Exception:raise _Uncertain() from None
                    identifier=data['steps'][name].get('id')
                    if not _id(identifier):raise _Uncertain()
                    try:status=self.client.container_status(identifier)
                    except Exception:raise _Pending() from None
                    if not isinstance(status,Mapping) or status.get('id')!=identifier:raise _Uncertain()
                    code=status.get('status_code')
                    if code=='IN_PROGRESS':raise _Pending()
                    if code in ('ERROR','EXPIRED'):raise _Terminal()
                    if code!='FINISHED':raise _Uncertain()
                    return identifier
                try:
                    if prepared['media_format']=='image':
                        cid=container('parent',lambda:self.client.create_image(ctx.target_id,receipts[0]['url'],prepared['caption']))
                    elif prepared['media_format']=='reels':
                        cid=container('parent',lambda:self.client.create_reels(ctx.target_id,receipts[0]['url'],prepared['caption']))
                    else:
                        children=[]
                        for i,r in enumerate(receipts):
                            option={'image_url' if r['media_type']=='image/jpeg' else 'video_url':r['url']}
                            children.append(container('child_'+str(i),lambda option=option:self.client.create_carousel_item(ctx.target_id,**option)))
                        cid=container('parent',lambda:self.client.create_carousel(ctx.target_id,children,prepared['caption']))
                    self._guard(ctx,prepared,receipts)
                    row=self._mark(row,'publish_started',data)
                except _Blocked:return _failed('instagram_write_blocked')
                except _Pending:return _failed('instagram_container_pending')
                except _Terminal:
                    try:self._mark(row,'failed',data)
                    except Exception:return self._uncertain(row,data)
                    return _failed('instagram_container_failed')
                except Exception:return self._uncertain(row,data)
                identifier=None
                try:
                    response=self.client.publish(ctx.target_id,cid)
                    identifier=response.get('id') if isinstance(response,Mapping) else None
                    if not _id(identifier):identifier=None;raise ValueError()
                    self._mark(row,'submitted',data,identifier)
                    return _submitted(identifier)
                except Exception:return self._uncertain(row,data,identifier)
        except Exception:return _failed('instagram_journal_unavailable')
