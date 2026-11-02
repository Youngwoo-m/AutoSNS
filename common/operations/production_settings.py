"""제작 설정 저장소와 순수 컴파일러. 설정 저장은 실제 기동이나 실행이 아니다.

저장소는 별도 production-settings.sqlite3만 다룬다. 생성자와 get()은 파일이나 폴더를
만들지 않고, 명시 initialize()만 DB를 만든다. 컴파일러는 I/O·provider·조회 없이
저장된 설정 행으로 다음 기동용 Registry/ExecutionCatalog/ExecutionPolicy를 계산한다.
"""
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from .content_store import ConflictError, StoreError
from .execution_catalog import ExecutionCatalog, ExecutorSpec
from .models import ContractError, Registry, _freeze_json
from .runtime_models import ExecutionPolicy

DB_NAME = 'production-settings.sqlite3'
SCHEMA_VERSION = 1
ACCOUNTS = ('personal', 'dept')
MAX_DAILY_LIMIT = 2147483647
PAYLOAD_KEYS = {'enabled_preference', 'daily_limit'}
ROW_KEYS = {'account_id', 'revision', 'enabled_preference', 'daily_limit', 'applies_to', 'execution_enabled'}
EXECUTOR_ID = 'managed-text-producer'
METRIC = 'managed_text_generations'
DDL = (
    'CREATE TABLE IF NOT EXISTS production_settings(account_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, '
    'enabled_preference INTEGER NOT NULL, daily_limit INTEGER, updated_at TEXT NOT NULL)',
)


def _invalid(): raise StoreError('invalid')
def _now(): return datetime.now(timezone.utc).isoformat()


def _account(account):
    if type(account) is not str or account not in ACCOUNTS: _invalid()
    return account


def _limit(value):
    return value is None or (type(value) is int and 1 <= value <= MAX_DAILY_LIMIT)


def _payload(payload):
    if not isinstance(payload, dict) or set(payload) != PAYLOAD_KEYS: _invalid()
    enabled, limit = payload['enabled_preference'], payload['daily_limit']
    if type(enabled) is not bool or not _limit(limit) or (enabled and limit is None): _invalid()
    return enabled, limit


def _default(account):
    return {'account_id': account, 'revision': 0, 'enabled_preference': False, 'daily_limit': None,
            'applies_to': 'next_startup', 'execution_enabled': False}


def _row(account, row):
    """DB 행을 공개 형태로 바꾼다. 형식이 틀린 행은 저장소 오류다."""
    revision, enabled, limit = row['revision'], row['enabled_preference'], row['daily_limit']
    if (type(revision) is not int or revision < 1 or enabled not in (0, 1) or type(enabled) is not int
            or not _limit(limit) or (enabled == 1 and limit is None)):
        raise StoreError('storage_error', 'Invalid settings row')
    return {**_default(account), 'revision': revision, 'enabled_preference': enabled == 1, 'daily_limit': limit}


class ProductionSettingsStore:
    def __init__(self, root):
        self.root = Path(root).absolute()
        self._initialized = False

    def _path(self):
        path = self.root / DB_NAME
        if self.root.is_symlink() or path.is_symlink() or not path.resolve().is_relative_to(self.root.resolve()):
            raise StoreError('storage_error', 'Unsafe storage path')
        # 상위 경로 중 root 아래의 심볼릭 링크도 거부한다. root 자체는 위에서 검사했다.
        return path

    @contextmanager
    def _db(self, writable=False):
        if writable and not self._initialized: raise StoreError('storage_error', 'initialize() required')
        conn = None
        try:
            path = self._path()
            conn = sqlite3.connect(path.as_uri() + ('?mode=rw' if writable else '?mode=ro'), uri=True,
                                   timeout=5, isolation_level=None)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA busy_timeout=5000')
            if conn.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION:
                raise StoreError('storage_error', 'Unsupported settings schema version')
            yield conn
        except StoreError: raise
        except (OSError, sqlite3.Error, ValueError, UnicodeError) as exc:
            raise StoreError('storage_error') from exc
        finally:
            if conn is not None: conn.close()

    def initialize(self):
        conn = None
        try:
            path = self._path()
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(path, timeout=5, isolation_level=None)
            conn.execute('PRAGMA busy_timeout=5000')
            conn.execute('BEGIN IMMEDIATE')
            try:
                version = conn.execute('PRAGMA user_version').fetchone()[0]
                if version == 0 and conn.execute("SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' LIMIT 1").fetchone():
                    raise StoreError('storage_error', 'Existing database is not a production settings store')
                if version not in (0, SCHEMA_VERSION):
                    raise StoreError('storage_error', 'Unsupported settings schema version')
                for statement in DDL: conn.execute(statement)
                conn.execute('PRAGMA user_version=%d' % SCHEMA_VERSION)
                conn.execute('COMMIT')
            except BaseException:
                conn.execute('ROLLBACK')
                raise
        except StoreError: raise
        except (OSError, sqlite3.Error) as exc:
            raise StoreError('storage_error') from exc
        finally:
            if conn is not None: conn.close()
        self._initialized = True

    def get(self, account):
        _account(account)
        path = self._path()
        if not path.is_file(): return _default(account)
        with self._db() as conn:
            row = conn.execute('SELECT * FROM production_settings WHERE account_id=?', (account,)).fetchone()
            return _default(account) if row is None else _row(account, row)

    def save(self, account, expected_revision, payload):
        _account(account)
        if type(expected_revision) is not int or expected_revision < 0: _invalid()
        enabled, limit = _payload(payload)
        with self._db(writable=True) as conn:
            conn.execute('BEGIN IMMEDIATE')
            try:
                row = conn.execute('SELECT * FROM production_settings WHERE account_id=?', (account,)).fetchone()
                current = 0 if row is None else _row(account, row)['revision']
                if current != expected_revision: raise ConflictError()
                conn.execute('INSERT INTO production_settings(account_id,revision,enabled_preference,daily_limit,updated_at) '
                             'VALUES(?,?,?,?,?) ON CONFLICT(account_id) DO UPDATE SET revision=excluded.revision, '
                             'enabled_preference=excluded.enabled_preference, daily_limit=excluded.daily_limit, '
                             'updated_at=excluded.updated_at',
                             (account, current + 1, int(enabled), limit, _now()))
                conn.execute('COMMIT')
            except BaseException:
                conn.execute('ROLLBACK')
                raise
            return {**_default(account), 'revision': current + 1, 'enabled_preference': enabled, 'daily_limit': limit}


@dataclass(frozen=True)
class CompiledProduction:
    registry: Registry
    catalog: ExecutionCatalog
    policy: ExecutionPolicy


def _contract(code, detail=''):
    return ContractError(code, detail)


def _setting_rows(settings):
    if not isinstance(settings, (list, tuple)): raise _contract('invalid_production_settings')
    rows = {}
    for row in settings:
        if not isinstance(row, Mapping) or set(row) != ROW_KEYS: raise _contract('invalid_production_settings')
        account = row['account_id']
        if type(account) is not str or account not in ACCOUNTS: raise _contract('unknown_account')
        if account in rows: raise _contract('invalid_production_settings', 'duplicate account')
        revision, enabled, limit = row['revision'], row['enabled_preference'], row['daily_limit']
        if (type(revision) is not int or revision < 0 or type(enabled) is not bool or not _limit(limit)
                or (enabled and limit is None) or row['applies_to'] != 'next_startup'
                or row['execution_enabled'] is not False):
            raise _contract('invalid_production_settings', account)
        rows[account] = dict(account_id=account, revision=revision, enabled_preference=enabled, daily_limit=limit)
    if set(rows) != set(ACCOUNTS): raise _contract('invalid_production_settings', 'missing account')
    return rows


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def _absolute(value):
    if not isinstance(value, (str, Path)) or not Path(value).is_absolute(): raise _contract('invalid_catalog')
    return str(value)


def compile_production_settings(settings, *, accounts, code_root, interpreter, activate=False):
    """저장된 두 계정 설정을 다음 기동용 제작 구성으로 계산한다. I/O와 provider 호출은 없다."""
    if type(activate) is not bool: raise _contract('invalid_runtime', 'activate')
    rows = _setting_rows(settings)
    if not isinstance(accounts, Mapping) or not set(ACCOUNTS) <= set(accounts): raise _contract('unknown_account')
    safe_accounts = _freeze_json(accounts)  # 문자열 키·JSON 값만 허용한다.
    root, python = _absolute(code_root), _absolute(interpreter)
    meaning = {account: [row['revision'], row['enabled_preference'], row['daily_limit']] for account, row in rows.items()}
    config_sha = _sha({'settings': meaning, 'accounts': sorted(safe_accounts)})
    jobs, policies = {}, {}
    for account in ACCOUNTS:
        row = rows[account]
        # 비활성 또는 한도 없음이면 enabled=false, quota_requirements=[]로 어떤 경로로도 실행되지 않는다.
        live = row['enabled_preference'] and row['daily_limit'] is not None
        policy_revision = 'managed-text-policy-%s-r%d' % (account, row['revision'])
        jobs['managed-text-' + account] = dict(
            id='managed-text-' + account, kind='production', owner_account_id=account, executor_id=EXECUTOR_ID, execution_owner='managed',
            schedule_owner='console', enabled=row['enabled_preference'], subscription_only=True,
            required_outputs=['text'], policy_revision=policy_revision)
        policies[policy_revision] = dict(
            subscription_only=True,
            quota_requirements=[dict(scope_kind='owner', scope_id=account, metric=METRIC, window_kind='day',
                                     timezone='Asia/Seoul', amount=1, limit=row['daily_limit'])] if live else [])
    registry = Registry(revision='production-settings-' + config_sha, accounts=safe_accounts, credentials={},
                        profiles={}, connections={}, jobs=jobs, policies=policies, crossposts={})
    job_ids = tuple(jobs)
    catalog = ExecutionCatalog(
        executors={EXECUTOR_ID: ExecutorSpec(EXECUTOR_ID, job_ids, ('prepare',), python, root,
                                             'common.operations.production_startup', (), ())},
        callers={'console': dict(job_ids=job_ids, source='console', legacy_allowed=False)},
        production_jobs={job_id: dict(owner_account_id=job['owner_account_id'], required_outputs=['text'])
                         for job_id, job in jobs.items()})
    policy = ExecutionPolicy(enabled=activate and any(job['enabled'] for job in jobs.values()),
                             allowed_connection_ids=(), cutover_revision=config_sha,
                             provider_policy={'subscription_only': True})
    return CompiledProduction(registry, catalog, policy)
