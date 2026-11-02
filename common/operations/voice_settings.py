"""개인·학과 음성 설정. 저장은 다음 명시 기동용이며 앱 실행·합성을 하지 않는다."""
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
import re
import sqlite3
from .content_store import ConflictError,StoreError
from .models import ContractError

DB_NAME='voice-settings.sqlite3'
SCHEMA_VERSION=1
APPLICATION_ID=0x56534554
ACCOUNTS=('personal','dept')
ROW_KEYS={'account_id','revision','enabled_preference','profile_id','applies_to','execution_enabled'}
COLUMNS=('account_id','revision','enabled_preference','profile_id','updated_at')
PROFILE=re.compile(r'[A-Za-z0-9_-]{1,128}')
DDL='CREATE TABLE voice_settings(account_id TEXT PRIMARY KEY,revision INTEGER NOT NULL,enabled_preference INTEGER NOT NULL,profile_id TEXT,updated_at TEXT NOT NULL)'

def _invalid():raise StoreError('invalid')
def _account(value):
    if type(value) is not str or value not in ACCOUNTS:_invalid()
    return value

def _profile(value):return value is None or (type(value) is str and PROFILE.fullmatch(value) is not None)
def _payload(value):
    if not isinstance(value,dict) or set(value)!={'enabled_preference','profile_id'}:_invalid()
    enabled,profile=value['enabled_preference'],value['profile_id']
    if type(enabled) is not bool or not _profile(profile) or (enabled and profile is None):_invalid()
    return enabled,profile

def _default(account):return dict(account_id=account,revision=0,enabled_preference=False,profile_id=None,applies_to='next_startup',execution_enabled=False)
def _row(account,row):
    revision,enabled,profile=row['revision'],row['enabled_preference'],row['profile_id']
    if (row['account_id']!=account or type(revision) is not int or revision<1 or type(enabled) is not int or enabled not in (0,1)
            or not _profile(profile) or (enabled==1 and profile is None)):
        raise StoreError('storage_error','Invalid voice settings row')
    return {**_default(account),'revision':revision,'enabled_preference':enabled==1,'profile_id':profile}

class VoiceSettingsStore:
    def __init__(self,root):self.root=Path(root).absolute();self._initialized=False
    def _path(self):
        path=self.root/DB_NAME
        if self.root.is_symlink() or path.is_symlink() or (path.exists() and not path.is_file()) or not path.resolve().is_relative_to(self.root.resolve()):
            raise StoreError('storage_error','Unsafe voice settings path')
        return path
    @staticmethod
    def _verify(db):
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if (db.execute('PRAGMA user_version').fetchone()[0]!=SCHEMA_VERSION
                or db.execute('PRAGMA application_id').fetchone()[0]!=APPLICATION_ID or tables!={'voice_settings'}
                or tuple(r[1] for r in db.execute('PRAGMA table_info(voice_settings)'))!=COLUMNS):
            raise StoreError('storage_error','Unsupported voice settings schema')
    @contextmanager
    def _db(self,writable=False):
        if writable and not self._initialized:raise StoreError('storage_error','initialize() required')
        db=None
        try:
            db=sqlite3.connect(self._path().as_uri()+('?mode=rw' if writable else '?mode=ro'),uri=True,timeout=5,isolation_level=None)
            db.row_factory=sqlite3.Row;db.execute('PRAGMA busy_timeout=5000');self._verify(db);yield db
        except StoreError:raise
        except (OSError,sqlite3.Error,ValueError,UnicodeError) as exc:raise StoreError('storage_error') from exc
        finally:
            if db is not None:db.close()
    def initialize(self):
        db=None
        try:
            path=self._path();path.parent.mkdir(parents=True,exist_ok=True)
            db=sqlite3.connect(path,timeout=5,isolation_level=None);db.execute('PRAGMA busy_timeout=5000');db.execute('BEGIN IMMEDIATE')
            try:
                objects=db.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
                if not objects and db.execute('PRAGMA user_version').fetchone()[0]==0 and db.execute('PRAGMA application_id').fetchone()[0]==0:
                    db.execute(DDL);db.execute(f'PRAGMA application_id={APPLICATION_ID}');db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
                self._verify(db);db.execute('COMMIT')
            except BaseException:db.rollback();raise
        except StoreError:raise
        except (OSError,sqlite3.Error) as exc:raise StoreError('storage_error') from exc
        finally:
            if db is not None:db.close()
        self._initialized=True
    def get(self,account):
        _account(account)
        if not self._path().is_file():return _default(account)
        with self._db() as db:
            row=db.execute('SELECT * FROM voice_settings WHERE account_id=?',(account,)).fetchone()
            return _default(account) if row is None else _row(account,row)
    def save(self,account,expected_revision,payload):
        _account(account)
        if type(expected_revision) is not int or expected_revision<0:_invalid()
        enabled,profile=_payload(payload)
        with self._db(True) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row=db.execute('SELECT * FROM voice_settings WHERE account_id=?',(account,)).fetchone()
                current=0 if row is None else _row(account,row)['revision']
                if current!=expected_revision:raise ConflictError()
                db.execute('INSERT INTO voice_settings(account_id,revision,enabled_preference,profile_id,updated_at) VALUES(?,?,?,?,?) '
                           'ON CONFLICT(account_id) DO UPDATE SET revision=excluded.revision,enabled_preference=excluded.enabled_preference,profile_id=excluded.profile_id,updated_at=excluded.updated_at',
                           (account,current+1,int(enabled),profile,datetime.now(timezone.utc).isoformat()))
                db.execute('COMMIT')
            except BaseException:db.rollback();raise
        return {**_default(account),'revision':current+1,'enabled_preference':enabled,'profile_id':profile}

def compile_voice_settings(rows):
    """두 계정 설정으로 다음 기동용 account->local profile 매핑만 순수 계산한다."""
    if not isinstance(rows,(list,tuple)):raise ContractError('invalid_voice_settings')
    seen=set();result={}
    for row in rows:
        if not isinstance(row,Mapping) or set(row)!=ROW_KEYS:raise ContractError('invalid_voice_settings')
        account=row['account_id']
        if type(account) is not str or account not in ACCOUNTS:raise ContractError('unknown_account')
        if account in seen:raise ContractError('invalid_voice_settings')
        seen.add(account)
        revision,enabled,profile=row['revision'],row['enabled_preference'],row['profile_id']
        if (type(revision) is not int or revision<0 or type(enabled) is not bool or not _profile(profile)
                or (enabled and profile is None) or row['applies_to']!='next_startup' or row['execution_enabled'] is not False
                or (revision==0 and (enabled or profile is not None))):
            raise ContractError('invalid_voice_settings')
        if enabled:result[account]=profile
    if seen!=set(ACCOUNTS):raise ContractError('invalid_voice_settings')
    return result
