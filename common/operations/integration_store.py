"""Account-specific tool preferences. No credentials or external service state."""
import json
import re
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .database import initialize_database, connect_database
from .content_store import StoreError, ConflictError

PLATFORMS = {
    'metricool': ('instagram', 'threads', 'x', 'facebook', 'youtube', 'tiktok'),
    'vidiq': ('youtube', 'instagram', 'tiktok'),
    'local': ('youtube', 'tiktok', 'instagram', 'threads', 'x', 'facebook', 'tistory', 'naver_blog', 'blogger', 'homepage', 'kakao'),
}
PAYLOAD_FIELDS = frozenset(('platform', 'target_label', 'enabled_preference', 'notes'))


def validate_settings(account_id, provider_id, connection_id, expected_revision, payload):
    """Validate exact input schema without filesystem or network operations."""
    if not isinstance(account_id, str) or account_id not in ('dept', 'personal'):
        raise StoreError('invalid')
    if not isinstance(provider_id, str) or provider_id not in PLATFORMS:
        raise StoreError('invalid')
    if not isinstance(connection_id, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', connection_id):
        raise StoreError('invalid')
    if type(expected_revision) is not int or expected_revision < 0:
        raise StoreError('invalid')
    if not isinstance(payload, dict) or set(payload) != PAYLOAD_FIELDS:
        raise StoreError('invalid')
    if not isinstance(payload['platform'], str) or payload['platform'] not in PLATFORMS[provider_id]:
        raise StoreError('invalid')
    if type(payload['enabled_preference']) is not bool:
        raise StoreError('invalid')
    for field, limit in (('target_label', 300), ('notes', 2000)):
        if not isinstance(payload[field], str) or len(payload[field]) > limit:
            raise StoreError('invalid')
        try:
            payload[field].encode('utf-8')
        except UnicodeError as exc:
            raise StoreError('invalid') from exc
    return dict(payload)


def _serialize(row):
    result = dict(row)
    payload = json.loads(result.pop('payload'))
    return {**result, **payload, 'connection_status': 'unknown', 'execution_status': 'not_connected'}


class IntegrationStore:
    def __init__(self, root):
        self.root = Path(root)

    def initialize(self):
        initialize_database(self.root)

    def list(self, account='all'):
        if account not in ('all', 'dept', 'personal'):
            raise StoreError('invalid')
        try:
            connection = connect_database(self.root)
        except FileNotFoundError:
            return []
        with closing(connection) as db:
            query = 'SELECT * FROM integration_settings'
            args = ()
            if account != 'all':
                query += ' WHERE account_id=?'
                args = (account,)
            query += ' ORDER BY account_id,provider_id,connection_id'
            return [_serialize(row) for row in db.execute(query, args)]

    def put(self, account_id, provider_id, connection_id, expected_revision, payload):
        payload = validate_settings(account_id, provider_id, connection_id, expected_revision, payload)
        key = (account_id, provider_id, connection_id)
        now = datetime.now(timezone.utc).isoformat()
        try:
            with closing(connect_database(self.root, writable=True)) as db, db:
                db.execute('BEGIN IMMEDIATE')
                row = db.execute('SELECT * FROM integration_settings WHERE account_id=? AND provider_id=? AND connection_id=?', key).fetchone()
                if (row['revision'] if row else 0) != expected_revision:
                    raise ConflictError()
                revision = expected_revision + 1
                encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
                if row:
                    db.execute('UPDATE integration_settings SET revision=?,payload=?,updated_at=? WHERE account_id=? AND provider_id=? AND connection_id=? AND revision=?',
                               (revision, encoded, now, *key, expected_revision))
                else:
                    db.execute('INSERT INTO integration_settings(account_id,provider_id,connection_id,revision,payload,created_at,updated_at) VALUES(?,?,?,?,?,?,?)', (*key, revision, encoded, now, now))
                db.execute('INSERT INTO integration_events(account_id,provider_id,connection_id,revision,created_at) VALUES(?,?,?,?,?)', (*key, revision, now))
                saved = db.execute('SELECT * FROM integration_settings WHERE account_id=? AND provider_id=? AND connection_id=?', key).fetchone()
                return _serialize(saved)
        except (StoreError, ConflictError):
            raise
        except Exception as exc:
            raise StoreError('storage_error') from exc
