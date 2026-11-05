"""관리 콘텐츠 이미지의 재사용 승인 기록 저장소·서비스·권한 검사기.

승인은 사람이 직접 남긴 append-only 기록(review_method=manual)이다. AI 검사나 자동 승인은 없다.
기록 키는 owner_account_id+content_id+asset_id+sha256이며 원고 리비전은 키에 포함하지 않는다.
따라서 새 원고 버전에서도 같은 owner/content/id/sha 이미지는 기존 기록을 이어받고,
바이트가 달라진 이미지·다른 계정·다른 콘텐츠는 승인 전이로 돌아간다.

저장소는 별도 reuse-approvals.sqlite3만 다룬다. 생성자와 읽기는 파일이나 폴더를 만들지 않고,
명시 initialize()만 DB를 만든다. 원고·자산·계획은 읽기만 하며 모델 호출, 파일 복사, 렌더는 없다.
"""
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3

from .content_store import StoreError
from .models import ContractError

DB_NAME = 'reuse-approvals.sqlite3'
SCHEMA_VERSION = 1
APPLICATION_ID = 0x52455553  # 'REUS'
OWNERS = ('personal', 'dept')
IMAGE_TYPES = ('image/png', 'image/jpeg', 'image/webp')
NOTES_LIMIT = 2000
ACTOR_LIMIT = 200
ID_LIMIT = 200
REVIEW_METHOD = 'manual'
DEFAULT_ACTOR = 'console_user'
DENIED = 'reuse_not_authorized'
PUBLIC_KEYS = ('content_id', 'content_revision', 'manifest_hash', 'owner_account_id', 'asset_id', 'sha256',
               'approval_revision', 'approved_revision', 'rights_confirmed', 'visual_checked', 'notes',
               'status', 'review_method')
COLUMNS = ('owner_account_id', 'content_id', 'asset_id', 'sha256', 'approval_revision', 'approved_revision',
           'approved_manifest_hash', 'actor', 'rights_confirmed', 'visual_checked', 'notes', 'created_at')
DDL = (
    "CREATE TABLE reuse_approvals(owner_account_id TEXT NOT NULL CHECK(owner_account_id IN ('personal','dept')), "
    'content_id TEXT NOT NULL, asset_id TEXT NOT NULL, sha256 TEXT NOT NULL CHECK(length(sha256)=64), '
    'approval_revision INTEGER NOT NULL CHECK(approval_revision>=1), '
    'approved_revision INTEGER NOT NULL CHECK(approved_revision>=1), '
    'approved_manifest_hash TEXT NOT NULL CHECK(length(approved_manifest_hash)=64), actor TEXT NOT NULL, '
    'rights_confirmed INTEGER NOT NULL CHECK(rights_confirmed IN (0,1)), '
    'visual_checked INTEGER NOT NULL CHECK(visual_checked IN (0,1)), notes TEXT NOT NULL, created_at TEXT NOT NULL, '
    'PRIMARY KEY(owner_account_id, content_id, asset_id, sha256, approval_revision))',
    "CREATE TRIGGER reuse_approvals_no_update BEFORE UPDATE ON reuse_approvals "
    "BEGIN SELECT RAISE(ABORT, 'reuse approvals are append-only'); END",
    "CREATE TRIGGER reuse_approvals_no_delete BEFORE DELETE ON reuse_approvals "
    "BEGIN SELECT RAISE(ABORT, 'reuse approvals are append-only'); END",
)
SCHEMA_NAMES = frozenset(('reuse_approvals', 'reuse_approvals_no_update', 'reuse_approvals_no_delete'))
SHA256 = re.compile(r'[0-9a-f]{64}')
SOURCE = re.compile(r'managed-content:([A-Za-z0-9_-]{1,128}):r([1-9][0-9]{0,8}):([A-Za-z0-9_-]{1,128})')
REQUEST = re.compile(r'media-plan:([0-9a-f]{64})')


def _invalid():
    raise ContractError('invalid_reuse_request')


def _now():
    return datetime.now(timezone.utc).isoformat()


def _text(value, limit, *, allow_empty):
    if type(value) is not str or len(value) > limit or '\x00' in value or (not value and not allow_empty):
        _invalid()
    try:
        value.encode('utf-8')
    except UnicodeError:
        _invalid()
    return value


def _int(value, minimum):
    if type(value) is not int or value < minimum:
        _invalid()
    return value


def _hash(value):
    if type(value) is not str or not SHA256.fullmatch(value):
        _invalid()
    return value


def _flag(value):
    if type(value) is not bool:
        _invalid()
    return value


def _key(owner_account_id, content_id, asset_id, sha256):
    if owner_account_id not in OWNERS:
        _invalid()
    return (owner_account_id, _text(content_id, ID_LIMIT, allow_empty=False),
            _text(asset_id, ID_LIMIT, allow_empty=False), _hash(sha256))


def _translate(exc, missing):
    """ContentStore 오류를 고정 코드로 바꾼다. 원문과 경로는 전달하지 않는다."""
    code = getattr(exc, 'code', None)
    if code == 'invalid':
        return ContractError('invalid_reuse_request')
    if code == 'not_found':
        return ContractError(missing)
    return ContractError('reuse_storage_error')


class ReuseApprovalStore:
    def __init__(self, root):
        self.root = Path(root).absolute()
        self._initialized = False

    # --- 연결 -------------------------------------------------------------
    def _db_path(self):
        path = self.root / DB_NAME
        if self.root.is_symlink() or path.is_symlink() or (path.exists() and not path.is_file()):
            raise ContractError('reuse_storage_error')
        return path

    @staticmethod
    def _connect(path, mode):
        conn = sqlite3.connect(path.as_uri() + '?mode=' + mode, uri=True, timeout=5, isolation_level=None)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA busy_timeout=5000')
            return conn
        except BaseException:
            conn.close()
            raise

    @staticmethod
    def _is_empty(conn):
        return (conn.execute('PRAGMA user_version').fetchone()[0] == 0
                and conn.execute('PRAGMA application_id').fetchone()[0] == 0
                and conn.execute('SELECT COUNT(*) FROM sqlite_master').fetchone()[0] == 0)

    @staticmethod
    def _verify(conn):
        if (conn.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID
                or conn.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION):
            raise ContractError('reuse_storage_error')
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
        columns = tuple(r[1] for r in conn.execute('PRAGMA table_info(reuse_approvals)'))
        if names != SCHEMA_NAMES or columns != COLUMNS:
            raise ContractError('reuse_storage_error')

    @contextmanager
    def _db(self, writable=False):
        """읽기에서 DB가 없으면 None을 내보내며 아무것도 만들지 않는다."""
        if writable and not self._initialized:
            raise ContractError('reuse_storage_error')
        path = self._db_path()
        if not path.is_file():
            if writable:
                raise ContractError('reuse_storage_error')
            yield None
            return
        conn = None
        try:
            conn = self._connect(path, 'rw' if writable else 'ro')
            self._verify(conn)
            yield conn
        except ContractError:
            raise
        except (OSError, sqlite3.Error, ValueError, UnicodeError) as exc:
            raise ContractError('reuse_storage_error') from exc
        finally:
            if conn is not None:
                conn.close()

    def initialize(self):
        """유일한 생성 지점. foreign DB와 symlink는 건드리지 않고 거부한다."""
        path = self._db_path()
        conn = None
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            if path.exists():
                probe = self._connect(path, 'ro')
                try:
                    if self._is_empty(probe):
                        mode = 'rw'
                    else:
                        self._verify(probe)
                        mode = None
                finally:
                    probe.close()
                if mode is None:
                    self._initialized = True
                    return
            else:
                mode = 'rwc'
            conn = self._connect(path, mode)
            conn.execute('BEGIN IMMEDIATE')
            try:
                if not self._is_empty(conn):
                    raise ContractError('reuse_storage_error')
                for statement in DDL:
                    conn.execute(statement)
                conn.execute('PRAGMA application_id=%d' % APPLICATION_ID)
                conn.execute('PRAGMA user_version=%d' % SCHEMA_VERSION)
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        except ContractError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise ContractError('reuse_storage_error') from exc
        finally:
            if conn is not None:
                conn.close()
        self._initialized = True

    # --- 기록 -------------------------------------------------------------
    @staticmethod
    def _record(row):
        """저장 행을 검증해 dict로 만든다. 형식이 어긋나면 저장소 오류다."""
        try:
            record = {name: row[name] for name in COLUMNS}
            if (record['owner_account_id'] not in OWNERS or type(record['approval_revision']) is not int
                    or record['approval_revision'] < 1 or type(record['approved_revision']) is not int
                    or record['approved_revision'] < 1 or record['rights_confirmed'] not in (0, 1)
                    or record['visual_checked'] not in (0, 1) or type(record['notes']) is not str
                    or type(record['actor']) is not str or not SHA256.fullmatch(record['sha256'])
                    or not SHA256.fullmatch(record['approved_manifest_hash'])):
                raise ValueError
        except (ValueError, TypeError, IndexError, KeyError) as exc:
            raise ContractError('reuse_storage_error') from exc
        record['rights_confirmed'] = bool(record['rights_confirmed'])
        record['visual_checked'] = bool(record['visual_checked'])
        return record

    def latest(self, owner_account_id, content_id, asset_id, sha256):
        """키의 최신 기록. DB가 없거나 기록이 없으면 None이고, 읽기는 아무것도 만들지 않는다."""
        key = _key(owner_account_id, content_id, asset_id, sha256)
        with self._db() as conn:
            if conn is None:
                return None
            row = conn.execute('SELECT * FROM reuse_approvals WHERE owner_account_id=? AND content_id=? '
                               'AND asset_id=? AND sha256=? ORDER BY approval_revision DESC LIMIT 1', key).fetchone()
            return None if row is None else self._record(row)

    def history(self, owner_account_id, content_id, asset_id, sha256):
        key = _key(owner_account_id, content_id, asset_id, sha256)
        with self._db() as conn:
            if conn is None:
                return []
            return [self._record(r) for r in conn.execute(
                'SELECT * FROM reuse_approvals WHERE owner_account_id=? AND content_id=? AND asset_id=? '
                'AND sha256=? ORDER BY approval_revision', key)]

    def save(self, *, owner_account_id, content_id, asset_id, sha256, expected_revision, approved_revision,
             approved_manifest_hash, actor, rights_confirmed, visual_checked, notes):
        """현재 최대 revision==expected_revision일 때만 새 revision 행을 INSERT한다. 기존 행은 보존한다."""
        key = _key(owner_account_id, content_id, asset_id, sha256)
        _int(expected_revision, 0)
        _int(approved_revision, 1)
        _hash(approved_manifest_hash)
        _text(actor, ACTOR_LIMIT, allow_empty=False)
        _flag(rights_confirmed)
        _flag(visual_checked)
        _text(notes, NOTES_LIMIT, allow_empty=True)
        with self._db(True) as conn:
            conn.execute('BEGIN IMMEDIATE')
            try:
                current = conn.execute('SELECT MAX(approval_revision) FROM reuse_approvals WHERE owner_account_id=? '
                                       'AND content_id=? AND asset_id=? AND sha256=?', key).fetchone()[0]
                if current is None:
                    current = 0
                if type(current) is not int:
                    raise ContractError('reuse_storage_error')
                if current != expected_revision:
                    raise ContractError('reuse_approval_conflict')
                values = key + (current + 1, approved_revision, approved_manifest_hash, actor,
                                int(rights_confirmed), int(visual_checked), notes, _now())
                conn.execute('INSERT INTO reuse_approvals(%s) VALUES(%s)' % (','.join(COLUMNS), ','.join('?' * len(COLUMNS))),
                             values)
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        return {**dict(zip(COLUMNS, values)), 'rights_confirmed': rights_confirmed, 'visual_checked': visual_checked}


def _public(snapshot, sha256, asset_id, record):
    """actor/경로/증거 원문 없이 13개 고정 키만 내보낸다. 기록이 없으면 0/None/false 기본 행이다."""
    approved = record is not None and record['rights_confirmed'] is True and record['visual_checked'] is True
    return {'content_id': snapshot['id'], 'content_revision': snapshot['revision'],
            'manifest_hash': snapshot['manifest_hash'], 'owner_account_id': snapshot['owner_account_id'],
            'asset_id': asset_id, 'sha256': sha256,
            'approval_revision': record['approval_revision'] if record else 0,
            'approved_revision': record['approved_revision'] if record else None,
            'rights_confirmed': record['rights_confirmed'] if record else False,
            'visual_checked': record['visual_checked'] if record else False,
            'notes': record['notes'] if record else '',
            'status': 'approved' if approved else 'not_approved', 'review_method': REVIEW_METHOD}


class ReuseApprovalService:
    def __init__(self, store, content_store, plan_store):
        if (not callable(getattr(store, 'latest', None)) or not callable(getattr(store, 'save', None))
                or not callable(getattr(content_store, 'get', None))
                or not callable(getattr(content_store, 'read_asset', None))
                or not callable(getattr(plan_store, 'get', None))):
            _invalid()
        roots = [getattr(obj, 'root', None) for obj in (store, content_store, plan_store)]
        if any(root is None for root in roots):
            _invalid()
        if len({os.path.realpath(os.fspath(Path(root).absolute())) for root in roots}) != 1:
            _invalid()
        self.store, self.content_store, self.plan_store = store, content_store, plan_store

    # --- 원본 조회(읽기 전용) -----------------------------------------------
    def _snapshot(self, content_id, revision=None):
        """revision이 None이면 현재 head. 호출자가 준 owner/hash는 쓰지 않고 항상 서버가 조회한다."""
        try:
            snapshot = self.content_store.get(content_id, revision)
        except StoreError as exc:
            raise _translate(exc, 'content_not_found') from None
        if snapshot is None:
            raise ContractError('content_not_found')
        if (not isinstance(snapshot, Mapping) or snapshot.get('id') != content_id
                or type(snapshot.get('revision')) is not int or (revision is not None and snapshot['revision'] != revision)
                or type(snapshot.get('manifest_hash')) is not str
                or snapshot.get('owner_account_id') not in OWNERS or not isinstance(snapshot.get('assets'), list)):
            raise ContractError('reuse_storage_error')
        return snapshot

    def _verified_image(self, snapshot, asset_id):
        """이미지 자산의 실제 바이트 sha/size를 ContentStore에서 확인하고 검증된 sha256을 돌려준다."""
        asset = next((a for a in snapshot['assets'] if isinstance(a, Mapping) and a.get('id') == asset_id
                      and a.get('media_type') in IMAGE_TYPES), None)
        if asset is None:
            raise ContractError('asset_not_found')
        try:
            _, raw = self.content_store.read_asset(snapshot['id'], snapshot['revision'], asset_id)
        except StoreError as exc:
            raise _translate(exc, 'reuse_storage_error') from None
        sha256 = hashlib.sha256(raw).hexdigest()
        if len(raw) != asset.get('size') or sha256 != asset.get('sha256'):
            raise ContractError('reuse_storage_error')
        return sha256

    @staticmethod
    def _images(snapshot):
        return [a['id'] for a in snapshot['assets']
                if isinstance(a, Mapping) and type(a.get('id')) is str and a.get('media_type') in IMAGE_TYPES]

    # --- 공개 API -----------------------------------------------------------
    def get_for_content(self, content_id, revision):
        _text(content_id, ID_LIMIT, allow_empty=False)
        _int(revision, 1)
        snapshot = self._snapshot(content_id, revision)
        items = []
        for asset_id in self._images(snapshot):
            sha256 = self._verified_image(snapshot, asset_id)
            record = self.store.latest(snapshot['owner_account_id'], snapshot['id'], asset_id, sha256)
            items.append(_public(snapshot, sha256, asset_id, record))
        return {'items': items}

    def save(self, content_id, content_revision, asset_id, expected_revision, rights_confirmed, visual_checked,
             notes, *, actor=DEFAULT_ACTOR):
        _text(content_id, ID_LIMIT, allow_empty=False)
        _int(content_revision, 1)
        _text(asset_id, ID_LIMIT, allow_empty=False)
        _int(expected_revision, 0)
        _flag(rights_confirmed)
        _flag(visual_checked)
        _text(notes, NOTES_LIMIT, allow_empty=True)
        _text(actor, ACTOR_LIMIT, allow_empty=False)
        head = self._snapshot(content_id)
        if head['revision'] != content_revision:
            raise ContractError('content_revision_conflict')
        sha256 = self._verified_image(head, asset_id)
        record = self.store.save(
            owner_account_id=head['owner_account_id'], content_id=head['id'], asset_id=asset_id, sha256=sha256,
            expected_revision=expected_revision, approved_revision=head['revision'],
            approved_manifest_hash=head['manifest_hash'], actor=actor, rights_confirmed=rights_confirmed,
            visual_checked=visual_checked, notes=notes)
        return _public(head, sha256, asset_id, record)


class ManagedReuseAuthorizer:
    """저장된 사람 확인과 계획 결속이 맞을 때만 재사용을 승인한다."""
    def check_plan(self,content_id,revision):
        """대기열 등록 전 선택 이미지의 현재 확인 상태를 읽기만 한다."""
        try:
            snapshot=self.service._snapshot(content_id,revision)
            record=self.service.plan_store.get(content_id,revision)
            plan=record['plan']
            if not plan['scenes'] or record['plan_revision']<1:self._deny()
            identity=dict(content_id=content_id,revision=revision,manifest_hash=snapshot['manifest_hash'],
                plan_revision=record['plan_revision'],plan=plan)
            digest=hashlib.sha256(json.dumps(identity,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
            for asset_id in dict.fromkeys(scene['asset_id'] for scene in plan['scenes']):
                sha=self.service._verified_image(snapshot,asset_id)
                self(manifest=dict(path='managed-source',sha256=sha,
                    source=f'managed-content:{content_id}:r{revision}:{asset_id}',reuse_request_id='media-plan:'+digest),asset=dict(sha256=sha))
        except Exception:
            raise ContractError(DENIED) from None

    def __init__(self, service):
        if not isinstance(service, ReuseApprovalService):
            _invalid()
        self.service = service

    def __call__(self, *, manifest, asset):
        try:
            return self._authorize(manifest, asset)
        except Exception:
            # 실패 원인(소유자, 경로, 해시, id)은 응답에 싣지 않는다.
            raise ContractError(DENIED) from None

    @staticmethod
    def _deny():
        raise ContractError(DENIED)

    def _authorize(self, manifest, asset):
        service = self.service
        if (not isinstance(manifest, Mapping) or not isinstance(asset, Mapping)
                or set(manifest) != {'path', 'sha256', 'source', 'reuse_request_id'}):
            self._deny()
        sha256, source, request = manifest['sha256'], manifest['source'], manifest['reuse_request_id']
        if not all(type(v) is str for v in (sha256, source, request)) or not SHA256.fullmatch(sha256):
            self._deny()
        parsed, bound = SOURCE.fullmatch(source), REQUEST.fullmatch(request)
        if parsed is None or bound is None or asset.get('sha256') != sha256:
            self._deny()
        content_id, revision, asset_id = parsed.group(1), int(parsed.group(2)), parsed.group(3)
        # manifest['path']는 읽지 않는다. 바이트는 불변 원고에서만 읽는다.
        snapshot = service._snapshot(content_id, revision)
        if not hmac.compare_digest(service._verified_image(snapshot, asset_id), sha256):
            self._deny()
        record = service.store.latest(snapshot['owner_account_id'], content_id, asset_id, sha256)
        if record is None or record['rights_confirmed'] is not True or record['visual_checked'] is not True:
            self._deny()
        plan = service.plan_store.get(content_id, revision)
        if (not isinstance(plan, Mapping) or plan.get('content_id') != content_id
                or plan.get('content_revision') != revision or plan.get('manifest_hash') != snapshot['manifest_hash']
                or plan.get('owner_account_id') != snapshot['owner_account_id']
                or type(plan.get('plan_revision')) is not int or plan['plan_revision'] < 1
                or not isinstance(plan.get('plan'), Mapping) or not isinstance(plan['plan'].get('scenes'), list)
                or not any(isinstance(s, Mapping) and s.get('asset_id') == asset_id for s in plan['plan']['scenes'])):
            self._deny()
        # prepare_short_media의 digest와 같은 정체성·직렬화(기본 구분자, sort_keys, ensure_ascii=False)다.
        identity = dict(content_id=snapshot['id'], revision=revision, manifest_hash=snapshot['manifest_hash'],
                        plan_revision=plan['plan_revision'], plan=plan['plan'])
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False,
                                           allow_nan=False).encode()).hexdigest()
        if not hmac.compare_digest(digest, bound.group(1)):
            self._deny()
        return {'authorized': True, 'reviewed': True, 'sha256': sha256, 'source': source, 'reuse_request_id': request}
