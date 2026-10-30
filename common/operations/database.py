"""콘텐츠와 연동 선호가 공유하는 명시적 SQLite 수명 주기."""
from pathlib import Path
import sqlite3

SCHEMA_VERSION = 2
DB_NAME = 'operations.sqlite3'
DDL = (
    'CREATE TABLE IF NOT EXISTS contents(id TEXT PRIMARY KEY, owner_account_id TEXT NOT NULL, current_revision INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS revisions(content_id TEXT NOT NULL REFERENCES contents(id), revision INTEGER NOT NULL, manifest_hash TEXT NOT NULL, snapshot TEXT NOT NULL, file_path TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(content_id,revision))',
    'CREATE TABLE IF NOT EXISTS reviews(id TEXT PRIMARY KEY, content_id TEXT NOT NULL, revision INTEGER NOT NULL, manifest_hash TEXT NOT NULL, kind TEXT NOT NULL, decision TEXT NOT NULL, notes TEXT NOT NULL, method TEXT NOT NULL, created_at TEXT NOT NULL, FOREIGN KEY(content_id,revision) REFERENCES revisions(content_id,revision))',
    'CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, content_id TEXT NOT NULL REFERENCES contents(id), revision INTEGER NOT NULL, kind TEXT NOT NULL, created_at TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS integration_settings(account_id TEXT, provider_id TEXT, connection_id TEXT, revision INTEGER, payload TEXT, created_at TEXT, updated_at TEXT, PRIMARY KEY(account_id,provider_id,connection_id))',
    'CREATE TABLE IF NOT EXISTS integration_events(id INTEGER PRIMARY KEY, account_id TEXT, provider_id TEXT, connection_id TEXT, revision INTEGER, created_at TEXT)',
)

def _path(root):
    root = Path(root).absolute()
    path = root / DB_NAME
    if root.is_symlink() or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise OSError('Unsafe database path')
    return path

def _open(path, writable):
    conn = sqlite3.connect(path.as_uri() + ('?mode=rw' if writable else '?mode=ro'), uri=True, timeout=5)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA busy_timeout=5000')
        if conn.execute('PRAGMA user_version').fetchone()[0] not in ((SCHEMA_VERSION,) if writable else (1, SCHEMA_VERSION)):
            raise sqlite3.DatabaseError('Unsupported operations schema version')
        if writable:
            conn.execute('PRAGMA journal_mode=DELETE')
        return conn
    except BaseException:
        conn.close()
        raise

def connect_database(root: Path, *, writable: bool = False) -> sqlite3.Connection:
    path = _path(root)
    if not path.is_file():
        raise FileNotFoundError(path)
    conn = _open(path,writable)
    if conn.execute('PRAGMA user_version').fetchone()[0] not in ((SCHEMA_VERSION,) if writable else (1, SCHEMA_VERSION)):
        conn.close()
        raise sqlite3.DatabaseError('Unsupported operations schema version')
    return conn

def initialize_database(root: Path) -> None:
    path = _path(root)
    path.parent.mkdir(parents=True,exist_ok=True)
    # Opening in create mode is confined to this explicit initialization entry point.
    conn = sqlite3.connect(path,timeout=5)
    try:
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA busy_timeout=5000')
        if conn.execute('PRAGMA user_version').fetchone()[0] not in (0,1,SCHEMA_VERSION):
            raise sqlite3.DatabaseError('Unsupported operations schema version')
        conn.execute('PRAGMA journal_mode=DELETE')
        conn.execute('BEGIN IMMEDIATE')
        version=conn.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0,1,SCHEMA_VERSION):
            raise sqlite3.DatabaseError('Unsupported operations schema version')
        for statement in DDL: conn.execute(statement)
        for statement in OPERATIONS_DDL: conn.execute(statement)
        conn.execute('PRAGMA user_version=2')
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()

# 이행은 initialize_database의 단일 트랜잭션에서만 실행한다.
OPERATIONS_DDL = (
    'CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, payload TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS triggers(id TEXT PRIMARY KEY, job_id TEXT NOT NULL, payload TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, job_id TEXT NOT NULL, scheduled_at_utc TEXT NOT NULL, phase TEXT NOT NULL, request_hash TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE(job_id,scheduled_at_utc,phase))',
    'CREATE TABLE IF NOT EXISTS deliveries(id TEXT PRIMARY KEY, content_id TEXT NOT NULL, revision INTEGER NOT NULL, connection_id TEXT NOT NULL, publication_purpose TEXT NOT NULL, schedule_slot TEXT NOT NULL, request_hash TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE(content_id,revision,connection_id,publication_purpose,schedule_slot))',
    'CREATE TABLE IF NOT EXISTS approvals(id TEXT PRIMARY KEY, delivery_id TEXT NOT NULL REFERENCES deliveries(id), payload TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS delivery_events(id INTEGER PRIMARY KEY, delivery_id TEXT NOT NULL REFERENCES deliveries(id), version INTEGER NOT NULL, kind TEXT NOT NULL, summary TEXT NOT NULL, created_at TEXT NOT NULL)',
)
