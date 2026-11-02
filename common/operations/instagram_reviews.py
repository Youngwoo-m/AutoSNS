"""Instagram 최종 배포 구성의 수동 검토. 승인된 15필드 준비물 전체를 fingerprint로 묶는다.

이미지/영상·캡션·순서·대상에 대한 사람의 확인이며 독립 원고 검토나 실제 기술 규격
검증을 대신하지 않는다. authorize는 이 확인만 검사한다. STOP·계정 권한·현재 계획
승인·독립 검토·publication permit·실제 발행 승인은 기존 공통 관문이 계속 담당한다.
생성자와 store 읽기는 저장소를 만들지 않고 명시 initialize만 DB를 만든다.
"""
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .content_store import StoreError
from .models import ContractError,Registry,thaw
from .runtime_models import PublicationContext,utc
from common.publishers.instagram_payloads import InstagramPreparationContext,PREPARED_KEYS,NUMERIC_ID,build_instagram_payload

DB_NAME='instagram-reviews.sqlite3'
APPLICATION_ID=0x49475256
SCHEMA_VERSION=1
CHECK_KEYS=('rights_confirmed','visual_checked','caption_checked','composition_checked','audio_checked')
PUBLIC_KEYS=('plan_id','content_id','content_revision','manifest_hash','owner_account_id','destination_account_id',
    'connection_id','target_id','media_format','caption','assets','subject_hash','review_revision','decision',
    'checks','notes','review_method','status','audio_required')
COLUMNS=('subject_hash','review_revision','decision','checks','notes','actor','recorded_at')
_SCHEMA_NAMES={'instagram_reviews','instagram_reviews_no_update','instagram_reviews_no_delete'}
_SHA=re.compile(r'[0-9a-f]{64}')
_DDL=(
    "CREATE TABLE instagram_reviews(subject_hash TEXT NOT NULL,review_revision INTEGER NOT NULL CHECK(review_revision>=1),decision TEXT NOT NULL CHECK(decision IN ('approved','revoked')),checks TEXT NOT NULL,notes TEXT NOT NULL,actor TEXT NOT NULL,recorded_at TEXT NOT NULL,PRIMARY KEY(subject_hash,review_revision))",
    "CREATE TRIGGER instagram_reviews_no_update BEFORE UPDATE ON instagram_reviews BEGIN SELECT RAISE(ABORT,'append_only'); END",
    "CREATE TRIGGER instagram_reviews_no_delete BEFORE DELETE ON instagram_reviews BEGIN SELECT RAISE(ABORT,'append_only'); END",
)


def _invalid():raise ContractError('instagram_review_invalid')
def _text(value,limit,required=False):
    if type(value) is not str or len(value)>limit or '\x00' in value or required and not value.strip():_invalid()
    try:value.encode('utf-8')
    except UnicodeError:_invalid()
    return value

def _hash(value):
    if type(value) is not str or _SHA.fullmatch(value) is None:_invalid()
    return value

def _checks(value):
    if not isinstance(value,Mapping) or set(value)!=set(CHECK_KEYS) or any(type(v) is not bool for v in value.values()):_invalid()
    return {key:value[key] for key in CHECK_KEYS}

def _json(value):return json.dumps(thaw(value),sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)

def _unique(pairs):
    value={}
    for key,item in pairs:
        if key in value:raise ValueError()
        value[key]=item
    return value

def instagram_subject_hash(prepared):
    if not isinstance(prepared,Mapping) or set(prepared)!=set(PREPARED_KEYS):_invalid()
    try:return hashlib.sha256(_json(prepared).encode('utf-8')).hexdigest()
    except (ValueError,TypeError,UnicodeError,RecursionError):_invalid()

def _approved(record,audio_required):
    return bool(record and record['decision']=='approved' and all(record['checks'][key] is True for key in CHECK_KEYS[:4])
                and (not audio_required or record['checks']['audio_checked'] is True))


class InstagramReviewStore:
    def __init__(self,root):self.root=Path(root).absolute();self._initialized=False
    def _path(self):
        path=self.root/DB_NAME
        if self.root.is_symlink() or path.is_symlink() or path.exists() and not path.is_file() or not path.resolve().is_relative_to(self.root.resolve()):
            raise ContractError('instagram_review_storage_error')
        return path
    @staticmethod
    def _verify(db):
        objects={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
        if (db.execute('PRAGMA application_id').fetchone()[0]!=APPLICATION_ID or db.execute('PRAGMA user_version').fetchone()[0]!=SCHEMA_VERSION
                or objects!=_SCHEMA_NAMES or tuple(row[1] for row in db.execute('PRAGMA table_info(instagram_reviews)'))!=COLUMNS):
            raise ContractError('instagram_review_storage_error')
    @contextmanager
    def _db(self,write=False):
        if write and not self._initialized:raise ContractError('instagram_review_storage_error')
        db=None
        try:
            path=self._path()
            if not path.is_file():
                if write:raise ContractError('instagram_review_storage_error')
                yield None;return
            db=sqlite3.connect(path.as_uri()+('?mode=rw' if write else '?mode=ro'),uri=True,timeout=5,isolation_level=None)
            db.row_factory=sqlite3.Row;self._verify(db);yield db
        except ContractError:raise
        except (OSError,sqlite3.Error,ValueError,UnicodeError):raise ContractError('instagram_review_storage_error') from None
        finally:
            if db is not None:db.close()
    def initialize(self):
        db=None
        try:
            path=self._path();path.parent.mkdir(parents=True,exist_ok=True);db=sqlite3.connect(path,isolation_level=None,timeout=5)
            db.execute('BEGIN IMMEDIATE')
            objects=db.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
            if not objects and db.execute('PRAGMA application_id').fetchone()[0]==0 and db.execute('PRAGMA user_version').fetchone()[0]==0:
                for statement in _DDL:db.execute(statement)
                db.execute(f'PRAGMA application_id={APPLICATION_ID}');db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
            self._verify(db);db.execute('COMMIT')
        except ContractError:
            if db is not None:db.rollback()
            raise
        except (OSError,sqlite3.Error):
            if db is not None:db.rollback()
            raise ContractError('instagram_review_storage_error') from None
        finally:
            if db is not None:db.close()
        self._initialized=True
    @staticmethod
    def _row(row):
        try:
            result=dict(row);_hash(result['subject_hash'])
            if type(result['review_revision']) is not int or result['review_revision']<1 or result['decision'] not in ('approved','revoked'):_invalid()
            result['checks']=_checks(json.loads(result['checks'],object_pairs_hook=_unique))
            _text(result['notes'],2000);_text(result['actor'],200,True);utc(result['recorded_at'])
            return result
        except Exception:raise ContractError('instagram_review_storage_error') from None
    def latest(self,subject_hash):
        _hash(subject_hash)
        with self._db() as db:
            if db is None:return None
            row=db.execute('SELECT * FROM instagram_reviews WHERE subject_hash=? ORDER BY review_revision DESC LIMIT 1',(subject_hash,)).fetchone()
            return self._row(row) if row is not None else None
    def append(self,subject_hash,expected_revision,decision,checks,notes,*,actor,recorded_at):
        _hash(subject_hash)
        if type(expected_revision) is not int or expected_revision<0 or decision not in ('approved','revoked'):_invalid()
        checks=_checks(checks);_text(notes,2000);_text(actor,200,True)
        try:recorded_at=utc(recorded_at).isoformat()
        except Exception:_invalid()
        with self._db(True) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                latest=db.execute('SELECT * FROM instagram_reviews WHERE subject_hash=? ORDER BY review_revision DESC LIMIT 1',(subject_hash,)).fetchone()
                current=0 if latest is None else self._row(latest)['review_revision']
                if current!=expected_revision:raise ContractError('instagram_review_conflict')
                db.execute('INSERT INTO instagram_reviews VALUES(?,?,?,?,?,?,?)',(subject_hash,current+1,decision,_json(checks),notes,actor,recorded_at))
                db.execute('COMMIT')
            except BaseException:db.rollback();raise
        return dict(subject_hash=subject_hash,review_revision=current+1,decision=decision,checks=checks,notes=notes,actor=actor,recorded_at=recorded_at)


class InstagramReviewService:
    def __init__(self,review_store,content_store,plan_supplier,registry_supplier,clock=None):
        if (not isinstance(review_store,InstagramReviewStore) or not all(callable(getattr(content_store,name,None)) for name in ('get','read_asset'))
                or not callable(plan_supplier) or not callable(registry_supplier) or clock is not None and not callable(clock)):_invalid()
        try:
            if review_store.root.resolve()!=Path(content_store.root).resolve():_invalid()
        except (AttributeError,TypeError,OSError,RuntimeError):_invalid()
        self.store=self.review_store=review_store;self.content_store=content_store
        self.plan_supplier=plan_supplier;self.registry_supplier=registry_supplier;self.clock=clock or (lambda:datetime.now(timezone.utc))
    def _registry(self):
        registry=self.registry_supplier()
        if not isinstance(registry,Registry):_invalid()
        return registry
    @staticmethod
    def _connection(registry,connection_id,owner,destination,target_id=None):
        connection=registry.connections.get(connection_id)
        if (connection is None or connection.platform!='instagram' or type(connection.target_id) is not str
                or NUMERIC_ID.fullmatch(connection.target_id) is None):raise ContractError('instagram_target_unverified')
        if (owner not in ('personal','dept') or destination not in ('personal','dept') or owner not in registry.accounts
                or destination not in registry.accounts or connection.account_id!=destination
                or target_id is not None and connection.target_id!=target_id):_invalid()
        return connection
    def _snapshot(self,content_id,revision,manifest_hash,owner):
        try:
            snapshot=self.content_store.get(content_id,revision);head=self.content_store.get(content_id)
        except StoreError:raise ContractError('instagram_review_stale') from None
        if (not isinstance(snapshot,Mapping) or not isinstance(head,Mapping) or snapshot.get('id')!=content_id
                or snapshot.get('revision')!=revision or snapshot.get('manifest_hash')!=manifest_hash or snapshot.get('owner_account_id')!=owner
                or head.get('revision')!=revision or head.get('manifest_hash')!=manifest_hash or head.get('owner_account_id')!=owner):
            raise ContractError('instagram_review_stale')
        return snapshot
    def _bytes(self,prepared):
        try:
            for expected in prepared['assets']:
                metadata,raw=self.content_store.read_asset(prepared['content_id'],prepared['content_revision'],expected['id'])
                if (not isinstance(metadata,Mapping) or type(raw) is not bytes or type(metadata.get('size')) is not int
                        or any(metadata.get(key)!=expected[key] for key in ('id','sha256','size','media_type'))
                        or len(raw)!=expected['size'] or hashlib.sha256(raw).hexdigest()!=expected['sha256']):
                    raise ContractError('instagram_asset_changed')
        except Exception:raise ContractError('instagram_asset_changed') from None
        self._snapshot(prepared['content_id'],prepared['content_revision'],prepared['manifest_hash'],prepared['owner_account_id'])
    def _derive(self,plan_id):
        _text(plan_id,300,True)
        try:plan=self.plan_supplier(plan_id)
        except StoreError:raise ContractError('instagram_plan_unavailable') from None
        if (not isinstance(plan,Mapping) or plan.get('id')!=plan_id or plan.get('status')=='cancelled'
                or plan.get('source')!='managed' or plan.get('platform')!='instagram'):
            raise ContractError('instagram_plan_unavailable')
        registry=self._registry()
        connection=self._connection(registry,plan.get('connection_id'),plan.get('owner_account_id'),plan.get('destination_account_id'))
        fields=dict(platform='instagram',connection_id=connection.id,target_id=connection.target_id,
            owner_account_id=plan.get('owner_account_id'),destination_account_id=plan.get('destination_account_id'),
            content_id=plan.get('content_id'),content_revision=plan.get('revision'),manifest_hash=plan.get('manifest_hash'),
            publication_purpose=plan.get('publication_purpose'),schedule_slot=plan.get('schedule_slot'),options=plan.get('options'))
        ctx=InstagramPreparationContext(**fields)
        snapshot=self._snapshot(ctx.content_id,ctx.content_revision,ctx.manifest_hash,ctx.owner_account_id)
        prepared=build_instagram_payload(snapshot,ctx);self._bytes(prepared)
        fresh=self._registry()
        self._connection(fresh,ctx.connection_id,ctx.owner_account_id,ctx.destination_account_id,ctx.target_id)
        return prepared
    @staticmethod
    def _public(plan_id,prepared,record):
        audio_required=any(asset['media_type']=='video/mp4' for asset in prepared['assets'])
        status='approved' if _approved(record,audio_required) else 'revoked' if record and record['decision']=='revoked' else 'not_reviewed'
        return dict(plan_id=plan_id,**{key:prepared[key] for key in ('content_id','content_revision','manifest_hash','owner_account_id',
            'destination_account_id','connection_id','target_id','media_format','caption')},assets=[dict(asset) for asset in prepared['assets']],
            subject_hash=instagram_subject_hash(prepared),review_revision=record['review_revision'] if record else 0,
            decision=record['decision'] if record else None,checks=dict(record['checks']) if record else dict.fromkeys(CHECK_KEYS,False),
            notes=record['notes'] if record else '',review_method='manual',status=status,audio_required=audio_required)
    def get(self,plan_id):
        prepared=self._derive(plan_id)
        return self._public(plan_id,prepared,self.store.latest(instagram_subject_hash(prepared)))
    def record(self,plan_id,body,actor='console_user'):
        if not isinstance(body,Mapping) or set(body)!={'expected_review_revision','subject_hash','decision','checks','notes'}:_invalid()
        expected=body['expected_review_revision']
        if type(expected) is not int or expected<0 or body['decision'] not in ('approved','revoked'):_invalid()
        _hash(body['subject_hash']);checks=_checks(body['checks']);_text(body['notes'],2000);_text(actor,200,True)
        prepared=self._derive(plan_id);subject=instagram_subject_hash(prepared)
        if body['subject_hash']!=subject:raise ContractError('instagram_review_stale')
        audio_required=any(asset['media_type']=='video/mp4' for asset in prepared['assets'])
        if body['decision']=='approved' and not _approved(dict(decision='approved',checks=checks),audio_required):_invalid()
        saved=self.store.append(subject,expected,body['decision'],checks,body['notes'],actor=actor,recorded_at=self.clock())
        # 원장 추가와 원본 저장소는 별개다. 중간에 바뀐 구성의 승인을 현재 구성에 이식하지 않는다.
        if instagram_subject_hash(self._derive(plan_id))!=subject:raise ContractError('instagram_review_stale')
        return self._public(plan_id,prepared,saved)
    def authorize(self,ctx,prepared):
        """실제 실행 문맥의 최종 수동 검토만 확인한다. 발행 permit/계획 승인을 대체하지 않는다."""
        try:
            if not isinstance(ctx,PublicationContext) or ctx.platform!='instagram':return False
            registry=self._registry()
            if ctx.registry_revision!=registry.revision:return False
            self._connection(registry,ctx.connection_id,ctx.owner_account_id,ctx.destination_account_id,ctx.target_id)
            snapshot=self._snapshot(ctx.content_id,ctx.content_revision,ctx.manifest_hash,ctx.owner_account_id)
            actual=build_instagram_payload(snapshot,ctx)
            if instagram_subject_hash(actual)!=instagram_subject_hash(prepared):return False
            self._bytes(actual)
            fresh=self._registry()
            if fresh.revision!=ctx.registry_revision:return False
            self._connection(fresh,ctx.connection_id,ctx.owner_account_id,ctx.destination_account_id,ctx.target_id)
            record=self.store.latest(instagram_subject_hash(actual))
            audio_required=any(asset['media_type']=='video/mp4' for asset in actual['assets'])
            return _approved(record,audio_required)
        except Exception:return False
