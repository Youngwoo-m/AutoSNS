"""비공개 미디어 바이트 임대. 생성자는 저장소를 만들지 않는다."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3

from .models import ContractError

DB_NAME = 'media-leases.sqlite3'
APPLICATION_ID = 0x4D4C5345
SCHEMA_VERSION = 1
MAX_ASSET_BYTES = 100 * 1024 * 1024
REQUEST_KEYS = frozenset('context_hash owner_account_id destination_account_id connection_id target_id content_id content_revision manifest_hash position asset_id asset_sha256 asset_size media_type'.split())
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_DDL = "CREATE TABLE media_leases(lease_id TEXT PRIMARY KEY,identity TEXT NOT NULL UNIQUE,request TEXT NOT NULL,authority TEXT NOT NULL,token TEXT NOT NULL,token_hash TEXT NOT NULL UNIQUE,expires_at TEXT NOT NULL,revoked INTEGER NOT NULL DEFAULT 0,purged INTEGER NOT NULL DEFAULT 0,payload BLOB)"
_COLUMNS = ('lease_id','identity','request','authority','token','token_hash','expires_at','revoked','purged','payload')


def _fail(code='media_lease_invalid'):
    raise ContractError(code)


def _time(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        _fail()
    return value.astimezone(timezone.utc).isoformat(timespec='microseconds')


def _json(value):
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError, UnicodeError, RecursionError):
        _fail()


def _validate(request, raw, authority):
    if type(request) is not dict or set(request) != REQUEST_KEYS or type(authority) is not dict or not authority:
        _fail()
    for key in REQUEST_KEYS - {'position', 'asset_size', 'content_revision'}:
        value = request[key]
        if type(value) is not str or not value.strip() or len(value) > 2048 or '\x00' in value:
            _fail()
    for key in ('context_hash', 'manifest_hash', 'asset_sha256'):
        if not _SHA.fullmatch(request[key]):
            _fail()
    for key, minimum in (('position', 0), ('asset_size', 1), ('content_revision', 1)):
        if type(request[key]) is not int or request[key] < minimum:
            _fail()
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_ASSET_BYTES or len(raw) != request['asset_size']:
        _fail()
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), request['asset_sha256']):
        _fail()
    if request['position'] > 9:
        _fail()
    media_type = request['media_type']
    if not ((media_type == 'image/jpeg' and len(raw) >= 6 and raw.startswith(b'\xff\xd8\xff') and raw.endswith(b'\xff\xd9')) or
            (media_type == 'video/mp4' and len(raw) >= 16 and raw[4:8] == b'ftyp' and 16 <= int.from_bytes(raw[:4], 'big') <= len(raw) and int.from_bytes(raw[:4], 'big') % 4 == 0)):
        _fail()
    return _json(request), _json(authority)


class MediaLeaseStore:
    def __init__(self, root):
        self.root = Path(root).absolute()
        self._initialized = False

    def __repr__(self):
        return 'MediaLeaseStore(<비공개>)'

    def _path(self):
        path = self.root / DB_NAME
        # /tmp and /var may be operating-system aliases on macOS; root itself
        # and every existing component beneath a user-selected root are strict.
        if any(p.is_symlink() for p in (self.root, path)) or (path.exists() and not path.is_file()):
            _fail('media_lease_storage_error')
        for parent in self.root.parents:
            if parent.is_symlink() and str(parent) not in ('/tmp', '/var'):
                _fail('media_lease_storage_error')
        for suffix in ('-journal', '-wal', '-shm'):
            side = Path(str(path) + suffix)
            if side.is_symlink() or side.exists() and not side.is_file():
                _fail('media_lease_storage_error')
        return path

    @staticmethod
    def _verify(db):
        objects = db.execute("SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
        if (db.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID or
                db.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION or
                len(objects) != 1 or tuple(objects[0]) != ('table', 'media_leases', _DDL) or
                tuple(r[1] for r in db.execute('PRAGMA table_info(media_leases)')) != _COLUMNS):
            _fail('media_lease_storage_error')

    @contextmanager
    def _db(self, write=False):
        db = None
        try:
            path = self._path()
            if write and not self._initialized:
                _fail('media_lease_storage_error')
            if not path.exists():
                if write:
                    _fail('media_lease_storage_error')
                yield None
                return
            if path.stat().st_mode & 0o077:
                _fail('media_lease_storage_error')
            db = sqlite3.connect(path.as_uri() + ('?mode=rw' if write else '?mode=ro'), uri=True, timeout=5, isolation_level=None)
            db.row_factory = sqlite3.Row
            self._verify(db)
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield db
            if write:
                db.commit()
        except ContractError:
            raise
        except (OSError, sqlite3.Error, ValueError, UnicodeError):
            _fail('media_lease_storage_error')
        finally:
            if db is not None:
                db.close()

    def initialize(self):
        db = None
        try:
            path = self._path()
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600) if not path.exists() else None
            if fd is not None:
                os.close(fd)
            if path.stat().st_mode & 0o077:
                _fail('media_lease_storage_error')
            db = sqlite3.connect(path, timeout=5, isolation_level=None)
            db.execute('BEGIN IMMEDIATE')
            if (not db.execute('SELECT name FROM sqlite_master').fetchall() and
                    db.execute('PRAGMA application_id').fetchone()[0] == 0 and db.execute('PRAGMA user_version').fetchone()[0] == 0):
                db.execute(_DDL)
                db.execute(f'PRAGMA application_id={APPLICATION_ID}')
                db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
            self._verify(db)
            db.commit()
            db.execute('PRAGMA journal_mode=WAL')
            self._initialized = True
        except ContractError:
            raise
        except (OSError, sqlite3.Error):
            _fail('media_lease_storage_error')
        finally:
            if db is not None:
                db.close()

    @staticmethod
    def _active(row, now):
        return bool(row is not None and not row['revoked'] and not row['purged'] and row['expires_at'] > now)

    @staticmethod
    def _receipt(row):
        request = json.loads(row['request'])
        return dict(lease_id=row['lease_id'], token=row['token'], asset_sha256=request['asset_sha256'],
                    asset_size=request['asset_size'], media_type=request['media_type'], expires_at=row['expires_at'], receipt_id=row['lease_id'])

    def issue(self, *, request, raw, expires_at, now, authority):
        current, expiry = _time(now), _time(expires_at)
        if not timedelta(minutes=5) < expires_at - now <= timedelta(hours=24):
            _fail()
        request_json, authority_json = _validate(request, raw, authority)
        identity = hashlib.sha256(request_json.encode('utf-8')).hexdigest()
        with self._db(write=True) as db:
            row = db.execute('SELECT lease_id,request,authority,token,expires_at,revoked,purged FROM media_leases WHERE identity=?', (identity,)).fetchone()
            if row is not None:
                if row['request'] != request_json or row['authority'] != authority_json:
                    _fail('media_lease_binding_mismatch')
                if not self._active(row, current):
                    _fail('media_lease_inactive')
                return self._receipt(row)
            lease_id, token = secrets.token_hex(32), secrets.token_hex(32)
            db.execute('INSERT INTO media_leases(lease_id,identity,request,authority,token,token_hash,expires_at,payload) VALUES(?,?,?,?,?,?,?,?)',
                       (lease_id, identity, request_json, authority_json, token, hashlib.sha256(token.encode()).hexdigest(), expiry, raw))
            return self._receipt(dict(lease_id=lease_id,token=token,request=request_json,expires_at=expiry))

    def lookup(self, token, *, now):
        current = _time(now)
        if type(token) is not str or not _SHA.fullmatch(token):
            return None
        with self._db() as db:
            if db is None:
                return None
            row = db.execute('SELECT lease_id,request,authority,token_hash,expires_at,revoked,purged FROM media_leases WHERE token_hash=?',
                             (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
            if not self._active(row, current) or not hmac.compare_digest(row['token_hash'], hashlib.sha256(token.encode()).hexdigest()):
                return None
            request = json.loads(row['request'])
            return dict(lease_id=row['lease_id'], request=request, authority=json.loads(row['authority']), asset_size=request['asset_size'],
                        media_type=request['media_type'], expires_at=row['expires_at'])

    def is_active(self, lease_id, *, now):
        current = _time(now)
        with self._db() as db:
            return self._active(db.execute('SELECT expires_at,revoked,purged FROM media_leases WHERE lease_id=?', (lease_id,)).fetchone(), current) if db else False

    @contextmanager
    def open_payload(self, lease_id, *, now):
        current = _time(now)
        with self._db() as db:
            row = db.execute('SELECT rowid,request,expires_at,revoked,purged FROM media_leases WHERE lease_id=?', (lease_id,)).fetchone() if db else None
            if not self._active(row, current):
                _fail('media_lease_inactive')
            with db.blobopen('media_leases', 'payload', row['rowid'], readonly=True) as stream:
                request = json.loads(row['request'])
                digest = hashlib.sha256()
                if len(stream) != request['asset_size']:
                    _fail('media_lease_integrity_error')
                while chunk := stream.read(64 * 1024):
                    digest.update(chunk)
                if not hmac.compare_digest(digest.hexdigest(), request['asset_sha256']):
                    _fail('media_lease_integrity_error')
                stream.seek(0)
                yield stream

    def revoke(self, lease_id, *, now):
        _time(now)
        with self._db(write=True) as db:
            return db.execute('UPDATE media_leases SET revoked=1 WHERE lease_id=? AND revoked=0', (lease_id,)).rowcount == 1

    def purge(self, *, now):
        current = _time(now)
        with self._db(write=True) as db:
            return db.execute('UPDATE media_leases SET payload=NULL,purged=1 WHERE purged=0 AND (revoked=1 OR expires_at<=?)', (current,)).rowcount

    def list_status(self, *, destination_account_id, now):
        current = _time(now)
        with self._db() as db:
            if db is None:
                return []
            result = []
            for row in db.execute('SELECT lease_id,request,expires_at,revoked,purged FROM media_leases ORDER BY lease_id'):
                request = json.loads(row['request'])
                if request['destination_account_id'] != destination_account_id:
                    continue
                result.append(dict(lease_id=row['lease_id'], owner_account_id=request['owner_account_id'],
                                   destination_account_id=request['destination_account_id'], content_id=request['content_id'],
                                   content_revision=request['content_revision'], connection_id=request['connection_id'],
                                   asset_id=request['asset_id'], asset_sha256=request['asset_sha256'],
                                   asset_size=request['asset_size'], media_type=request['media_type'], expires_at=row['expires_at'],
                                   status='purged' if row['purged'] else 'revoked' if row['revoked'] else 'expired' if row['expires_at'] <= current else 'active'))
            return result
