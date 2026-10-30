"""성과 전용 append-only 저장소. 운영 원장·콘텐츠·승인 상태에는 접근하지 않는다."""
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .content_store import ConflictError, StoreError
from .metrics_models import _text, normalize_observation


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _account(value, *, all_allowed=False):
    if value not in (('all', 'personal', 'dept') if all_allowed else ('personal', 'dept')):
        raise StoreError('invalid')


_SCHEMA = '''
CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY, observation_key TEXT NOT NULL UNIQUE,
    owner_account_id TEXT, destination_account_id TEXT, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS proposals (
    id TEXT PRIMARY KEY, request_key TEXT NOT NULL UNIQUE, account_id TEXT NOT NULL,
    request_payload TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS observations_no_update BEFORE UPDATE ON observations
BEGIN SELECT RAISE(ABORT, 'append_only'); END;
CREATE TRIGGER IF NOT EXISTS observations_no_delete BEFORE DELETE ON observations
BEGIN SELECT RAISE(ABORT, 'append_only'); END;
CREATE TRIGGER IF NOT EXISTS proposals_no_update BEFORE UPDATE ON proposals
BEGIN SELECT RAISE(ABORT, 'append_only'); END;
CREATE TRIGGER IF NOT EXISTS proposals_no_delete BEFORE DELETE ON proposals
BEGIN SELECT RAISE(ABORT, 'append_only'); END;
PRAGMA user_version=1;
'''


class MetricsStore:
    def __init__(self, root):
        self.root = Path(root).absolute()
        self._initialized = False

    @property
    def path(self):
        path = self.root / 'metrics.sqlite3'
        if self.root.is_symlink() or path.is_symlink():
            raise StoreError('storage_error')
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise StoreError('storage_error')
        return path

    def initialize(self):
        path = self.path
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(path)) as conn:
                if conn.execute('PRAGMA user_version').fetchone()[0] not in (0, 1):
                    raise StoreError('storage_error')
                conn.executescript(_SCHEMA)
            self._initialized = True
        except (OSError, sqlite3.Error) as exc:
            raise StoreError('storage_error') from exc

    @contextmanager
    def _db(self, write=False):
        conn = None
        try:
            path = self.path
            if write and not self._initialized:
                raise StoreError('storage_error', 'initialize() required')
            if not path.is_file():
                if write:
                    raise StoreError('storage_error')
                yield None
                return
            conn = sqlite3.connect(path.as_uri() + '?mode=' + ('rw' if write else 'ro'), uri=True)
            conn.row_factory = sqlite3.Row
            if write:
                conn.execute('BEGIN IMMEDIATE')
            yield conn
            if write:
                conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ConflictError() from exc
        except (OSError, sqlite3.Error) as exc:
            raise StoreError('storage_error') from exc
        finally:
            if conn is not None:
                # Closing an uncommitted write rolls back the whole import.
                conn.close()

    def _append(self, conn, row, observation_key):
        _text(observation_key, limit=1000)
        payload = _json(row)
        found = conn.execute('SELECT id,payload FROM observations WHERE observation_key=?', (observation_key,)).fetchone()
        if found:
            if found['payload'] != payload:
                raise ConflictError()
            return dict(json.loads(found['payload']), id=found['id']), False
        ident = 'metric_' + uuid4().hex
        conn.execute('INSERT INTO observations VALUES(?,?,?,?,?)',
                     (ident, observation_key, row['owner_account_id'], row['destination_account_id'], payload))
        return dict(row, id=ident), True

    def append_observation(self, observation, observation_key):
        row = normalize_observation(observation)
        with self._db(True) as conn:
            saved, _ = self._append(conn, row, observation_key)
            return saved

    def list_observations(self, account_id='all'):
        _account(account_id, all_allowed=True)
        with self._db() as conn:
            if conn is None:
                return []
            query = 'SELECT id,payload FROM observations'
            args = ()
            if account_id != 'all':
                query += ' WHERE owner_account_id=? OR destination_account_id=?'
                args = (account_id, account_id)
            return [dict(json.loads(r['payload']), id=r['id']) for r in conn.execute(query + ' ORDER BY rowid', args)]

    def import_rows(self, plan):
        """{preview_digest, observations:[{observation_key, observation:{...}}]} 원자 저장.

        원본 재검증 및 preview_digest 일치 확인은 import 호출자가 담당한다.
        """
        if not isinstance(plan, dict) or not isinstance(plan.get('observations'), list):
            raise StoreError('invalid')
        _text(plan.get('preview_digest'), limit=1000)
        imported = unchanged = 0
        with self._db(True) as conn:
            for entry in plan['observations']:
                if not isinstance(entry, dict) or set(entry) != {'observation_key', 'observation'}:
                    raise StoreError('invalid')
                row = normalize_observation(entry['observation'])
                _, created = self._append(conn, row, entry['observation_key'])
                imported += int(created)
                unchanged += int(not created)
        return dict(imported=imported, unchanged=unchanged, preview_digest=plan['preview_digest'])

    def save_proposal(self, account_id, observation_ids, title, note, request_key):
        _account(account_id)
        _text(title, limit=300)
        _text(note, empty=True, limit=20000)
        _text(request_key, limit=1000)
        if (not isinstance(observation_ids, (list, tuple)) or not observation_ids or len(observation_ids) > 100
                or any(not isinstance(i, str) or not i for i in observation_ids)
                or len(set(observation_ids)) != len(observation_ids)):
            raise StoreError('invalid')
        request = dict(account_id=account_id, observation_ids=list(observation_ids), title=title, note=note)
        with self._db(True) as conn:
            found = conn.execute('SELECT request_payload,payload FROM proposals WHERE request_key=?', (request_key,)).fetchone()
            if found:
                if found['request_payload'] != _json(request):
                    raise ConflictError()
                return json.loads(found['payload'])
            for ident in observation_ids:
                row = conn.execute('SELECT owner_account_id,destination_account_id FROM observations WHERE id=?', (ident,)).fetchone()
                if row is None or account_id not in (row['owner_account_id'], row['destination_account_id']):
                    raise StoreError('invalid')
            result = dict(request, id='proposal_' + uuid4().hex, status='draft',
                          created_at=datetime.now(timezone.utc).isoformat())
            conn.execute('INSERT INTO proposals VALUES(?,?,?,?,?)',
                         (result['id'], request_key, account_id, _json(request), _json(result)))
            return result

    def list_proposals(self, account_id='all'):
        _account(account_id, all_allowed=True)
        with self._db() as conn:
            if conn is None:
                return []
            query = 'SELECT payload FROM proposals'
            args = ()
            if account_id != 'all':
                query += ' WHERE account_id=?'
                args = (account_id,)
            return [json.loads(r['payload']) for r in conn.execute(query + ' ORDER BY rowid', args)]
