"""Voicebox 음성 합성 작업 저장소와 서비스.

원본 콘텐츠는 신뢰된 ContentStore가 소유하고, 이 모듈은 합성 작업 상태만 별도
SQLite(voice-tasks.sqlite3)에 보존한다. 자동 재합성, lease, 프로세스 시작은 없다.
작업별 OS 파일 잠금(.task.lock)은 native POST와 명시적 복구 연결이 서로 경합하지 않게 할 때만 쓴다.
결과는 검토를 거치지 않은 AI 합성 음성 원자료이며 review_status는 항상 not_checked다.
"""
from contextlib import contextmanager
import errno
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
from uuid import UUID, uuid4

from . import production_media
from .content_store import ConflictError, StoreError, MAX_ASSET_BYTES
from .models import ContractError

DB_NAME = 'voice-tasks.sqlite3'
SCHEMA_VERSION = 1
APPLICATION_ID = 0x564F4943
ARTIFACT_DIR = 'voice-artifacts'
ARTIFACT_NAME = 'voice.wav'
LOCK_NAME = '.task.lock'
MAX_SECONDS = 20
MAX_SCRIPT_CHARS = 2000
MAX_SEED = 2147483647
VOICE_LABEL = production_media.VOICE_LABEL
REVIEW_STATUS = 'not_checked'
STATES = ('started', 'pending', 'audio_ready', 'completed', 'failed', 'unknown', 'content_changed')
COLUMNS = ('task_id', 'intent_hash', 'owner_account_id', 'content_id', 'input_revision', 'manifest_hash', 'script',
           'seed', 'state', 'reason_code', 'generation_id', 'audio_sha256', 'audio_size', 'audio_path', 'seconds',
           'output_revision', 'asset_id', 'version')
MUTABLE = frozenset({'state', 'reason_code', 'generation_id', 'audio_sha256', 'audio_size', 'audio_path', 'seconds',
                     'output_revision', 'asset_id'})
DDL = (
    'CREATE TABLE voice_tasks(task_id TEXT PRIMARY KEY, intent_hash TEXT NOT NULL UNIQUE, owner_account_id TEXT NOT NULL, '
    'content_id TEXT NOT NULL, input_revision INTEGER NOT NULL, manifest_hash TEXT NOT NULL, script TEXT NOT NULL, '
    'seed INTEGER NOT NULL, state TEXT NOT NULL CHECK(state IN (' + ','.join("'" + s + "'" for s in STATES) + ')), '
    'reason_code TEXT, generation_id TEXT, audio_sha256 TEXT, audio_size INTEGER, audio_path TEXT, seconds REAL, '
    'output_revision INTEGER, asset_id TEXT, version INTEGER NOT NULL DEFAULT 1)',
    'CREATE INDEX voice_tasks_content ON voice_tasks(content_id, input_revision)',
)
GENERATION_ID = re.compile(r'[A-Za-z0-9._:-]{1,200}')
FAILED_STATUSES = ('failed', 'error', 'cancelled')
# 복구 연결에 쓰는 ID는 client와 같은 엄격한 형식만 허용한다(경로/URL 문자 차단).
RECOVERY_ID = re.compile(r'[A-Za-z0-9_-]{1,128}')
FINGERPRINT = re.compile(r'[0-9a-f]{64}')
RECOVERABLE_STATES = ('started', 'unknown')
LINKED_STATES = ('pending', 'audio_ready', 'completed')
RECOVERY_STATUSES = ('pending', 'queued', 'running', 'completed')
CANDIDATE_FIELDS = frozenset(('id', 'status', 'profile_id', 'text', 'seed', 'language', 'engine', 'model_size'))


def _hash(data): return hashlib.sha256(data).hexdigest()


def _task_id(value):
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise ContractError('invalid_task') from None
    if str(parsed) != value or parsed.version != 4:
        raise ContractError('invalid_task')
    return value


def _public(row):
    """내부 필드(script, profile, 경로, intent 해시)를 뺀 안전 projection."""
    return dict(task_id=row['task_id'], state=row['state'], reason_code=row['reason_code'],
                content_id=row['content_id'], input_revision=row['input_revision'],
                output_revision=row['output_revision'], asset_id=row['asset_id'], seconds=row['seconds'],
                review_status=REVIEW_STATUS, voice_label=VOICE_LABEL, generation_id=row['generation_id'])


def _read_file(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as handle:
        return handle.read(MAX_ASSET_BYTES + 1)


class VoiceTaskStore:
    def __init__(self, root):
        self.root = Path(root).absolute()
        self._initialized = False

    # --- 연결 -------------------------------------------------------------
    def _db_path(self):
        path = self.root / DB_NAME
        if self.root.is_symlink() or path.is_symlink() or (path.exists() and not path.is_file()):
            raise ContractError('voice_storage_unsafe')
        if path.exists() and not path.resolve().is_relative_to(self.root.resolve()):
            raise ContractError('voice_storage_unsafe')
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
                and conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0] == 0)

    @staticmethod
    def _verify(conn):
        if (conn.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID
                or conn.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION):
            raise ContractError('voice_storage_foreign')
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
        columns = tuple(r[1] for r in conn.execute('PRAGMA table_info(voice_tasks)'))
        if names != {'voice_tasks', 'voice_tasks_content'} or columns != COLUMNS:
            raise ContractError('voice_storage_foreign')

    @contextmanager
    def _db(self, writable=False):
        if writable and not self._initialized:
            raise ContractError('voice_storage_error', 'initialize() required')
        path = self._db_path()
        if not path.is_file():
            if writable:
                raise ContractError('voice_storage_error')
            yield None
            return
        conn = None
        try:
            conn = self._connect(path, 'rw' if writable else 'ro')
            self._verify(conn)
            yield conn
        except ContractError:
            raise
        except (OSError, sqlite3.Error, ValueError) as exc:
            raise ContractError('voice_storage_error') from exc
        finally:
            if conn is not None:
                conn.close()

    def initialize(self):
        """유일한 생성 지점. 외부/foreign DB와 symlink는 건드리지 않고 거부한다."""
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
                    raise ContractError('voice_storage_foreign')
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
            raise ContractError('voice_storage_error') from exc
        finally:
            if conn is not None:
                conn.close()
        self._initialized = True

    # --- 작업 행 ----------------------------------------------------------
    def claim(self, *, owner_account_id, content_id, input_revision, manifest_hash, script, seed, intent_hash):
        """BEGIN IMMEDIATE 아래에서 (row, created)를 돌려준다. created인 호출자만 native POST를 한다."""
        with self._db(True) as conn:
            conn.execute('BEGIN IMMEDIATE')
            try:
                found = conn.execute('SELECT * FROM voice_tasks WHERE intent_hash=?', (intent_hash,)).fetchone()
                if found is not None:
                    conn.commit()
                    return dict(found), False
                busy = conn.execute("SELECT 1 FROM voice_tasks WHERE content_id=? AND state IN ('started','unknown') "
                                    "AND generation_id IS NULL LIMIT 1", (content_id,)).fetchone()
                if busy is not None:
                    raise ContractError('voice_task_conflict')
                task_id = str(uuid4())
                conn.execute('INSERT INTO voice_tasks(task_id,intent_hash,owner_account_id,content_id,input_revision,'
                             'manifest_hash,script,seed,state) VALUES(?,?,?,?,?,?,?,?,?)',
                             (task_id, intent_hash, owner_account_id, content_id, input_revision, manifest_hash,
                              script, seed, 'started'))
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
            return dict(conn.execute('SELECT * FROM voice_tasks WHERE task_id=?', (task_id,)).fetchone()), True

    def transition(self, task_id, from_states, **fields):
        """CAS: 현재 state가 from_states일 때만 갱신한다. 성공 여부를 돌려준다."""
        _task_id(task_id)
        if not fields or set(fields) - MUTABLE or fields.get('state') not in STATES or not from_states:
            raise ContractError('voice_storage_error', 'invalid transition')
        columns = sorted(fields)
        sql = ('UPDATE voice_tasks SET ' + ','.join(c + '=?' for c in columns) + ',version=version+1 '
               'WHERE task_id=? AND state IN (' + ','.join('?' * len(from_states)) + ')')
        with self._db(True) as conn:
            changed = conn.execute(sql, [fields[c] for c in columns] + [task_id, *from_states]).rowcount
        return changed == 1

    def link_generation(self, task_id, generation_id, expected_version):
        """복구 연결 CAS. started/unknown + generation_id NULL + 예상 version일 때만 pending으로 연결한다.

        generation_id 유일성은 스키마 변경 없이 같은 BEGIN IMMEDIATE transaction 안에서 다시 확인한다.
        'linked' | 'conflict'(이미 다른 작업에 연결됨) | 'stale'(행이 바뀜)을 돌려준다.
        """
        _task_id(task_id)
        with self._db(True) as conn:
            conn.execute('BEGIN IMMEDIATE')
            try:
                if conn.execute('SELECT 1 FROM voice_tasks WHERE generation_id=? LIMIT 1',
                                (generation_id,)).fetchone() is not None:
                    conn.rollback()
                    return 'conflict'
                changed = conn.execute(
                    "UPDATE voice_tasks SET state='pending', generation_id=?, reason_code=NULL, version=version+1 "
                    "WHERE task_id=? AND state IN ('started','unknown') AND generation_id IS NULL AND version=?",
                    (generation_id, task_id, expected_version)).rowcount
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        return 'linked' if changed == 1 else 'stale'

    def generation_task(self, generation_id):
        """generation_id가 이미 붙은 작업의 task_id(없으면 None). 읽기 전용."""
        with self._db() as conn:
            if conn is None:
                return None
            found = conn.execute('SELECT task_id FROM voice_tasks WHERE generation_id=? LIMIT 1',
                                 (generation_id,)).fetchone()
            return found['task_id'] if found is not None else None

    def get_row(self, task_id):
        _task_id(task_id)
        with self._db() as conn:
            if conn is None:
                return None
            found = conn.execute('SELECT * FROM voice_tasks WHERE task_id=?', (task_id,)).fetchone()
            return dict(found) if found is not None else None

    def find_intent(self, intent_hash):
        with self._db() as conn:
            if conn is None:
                return None
            found = conn.execute('SELECT * FROM voice_tasks WHERE intent_hash=?', (intent_hash,)).fetchone()
            return dict(found) if found is not None else None

    def get(self, task_id):
        row = self.get_row(task_id)
        return _public(row) if row is not None else None

    def list_for_content(self, content_id, revision=None):
        if not isinstance(content_id, str) or not content_id:
            raise ContractError('invalid_voice_request')
        if revision is not None and (type(revision) is not int or revision < 1):
            raise ContractError('invalid_voice_request')
        with self._db() as conn:
            if conn is None:
                return []
            if revision is None:
                rows = conn.execute('SELECT * FROM voice_tasks WHERE content_id=? ORDER BY rowid', (content_id,))
            else:
                rows = conn.execute('SELECT * FROM voice_tasks WHERE content_id=? AND input_revision=? ORDER BY rowid',
                                    (content_id, revision))
            return [_public(dict(r)) for r in rows.fetchall()]

    # --- 작업별 잠금 ------------------------------------------------------
    @contextmanager
    def task_lock(self, task_id):
        """voice-artifacts/{task_id}/.task.lock에 대한 비차단 flock. 이미 잡혀 있으면 voice_task_busy.

        OS 잠금이므로 프로세스가 죽으면 자동으로 풀리고 DB 행은 그대로 남는다. 다른 프로세스도 같은 파일을 쓴다.
        """
        try:
            import fcntl
        except ImportError:
            raise ContractError('voice_storage_error') from None
        directory = self._artifact_dir(task_id, True)
        fd = None
        try:
            fd = os.open(directory / LOCK_NAME, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ContractError('voice_storage_unsafe')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ContractError('voice_task_busy') from None
        except BaseException as exc:
            if fd is not None:
                os.close(fd)
            if not isinstance(exc, OSError) or isinstance(exc, ContractError):
                raise
            code = 'voice_storage_unsafe' if exc.errno == errno.ELOOP else 'voice_storage_error'
            raise ContractError(code) from exc
        try:
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(fd)

    # --- WAV 산출물 -------------------------------------------------------
    def _artifact_dir(self, task_id, create):
        _task_id(task_id)
        base = self.root / ARTIFACT_DIR
        target = base / task_id
        if create:
            if not self._initialized:
                raise ContractError('voice_storage_error', 'initialize() required')
            if self.root.is_symlink() or base.is_symlink():
                raise ContractError('voice_storage_unsafe')
            target.mkdir(parents=True, exist_ok=True)
        if any(p.is_symlink() for p in (self.root, base, target)) or (create and not target.is_dir()):
            raise ContractError('voice_storage_unsafe')
        return target

    def stage_artifact(self, task_id, raw):
        """O_EXCL 임시 파일에 쓴다. 호출자가 probe한 뒤 publish_artifact로 확정한다."""
        try:
            tmp = self._artifact_dir(task_id, True) / (ARTIFACT_NAME + '.tmp-' + uuid4().hex)
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            try:
                with os.fdopen(fd, 'wb') as handle:
                    handle.write(raw)
                    handle.flush()
                    os.fsync(handle.fileno())
            except BaseException:
                self.discard_artifact(tmp)
                raise
            return tmp
        except OSError as exc:
            raise ContractError('voice_storage_error') from exc

    def publish_artifact(self, task_id, tmp, raw):
        """os.link로 덮어쓰기 없이 확정한다. 다른 내용이 이미 있으면 None."""
        final = self._artifact_dir(task_id, False) / ARTIFACT_NAME
        try:
            os.link(tmp, final)
        except FileExistsError:
            try:
                if _read_file(final) != raw:
                    return None
            except OSError as exc:
                raise ContractError('voice_storage_error') from exc
        except OSError as exc:
            raise ContractError('voice_storage_error') from exc
        return f'{ARTIFACT_DIR}/{task_id}/{ARTIFACT_NAME}'

    @staticmethod
    def discard_artifact(tmp):
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def read_artifact(self, row):
        """DB 경로를 믿지 않고 task id에서 경로를 다시 유도한다. 불일치/손상은 None."""
        expected = f'{ARTIFACT_DIR}/{row["task_id"]}/{ARTIFACT_NAME}'
        try:
            if row['audio_path'] != expected:
                return None
            raw = _read_file(self._artifact_dir(row['task_id'], False) / ARTIFACT_NAME)
        except (OSError, ContractError):
            return None
        if len(raw) != row['audio_size'] or _hash(raw) != row['audio_sha256']:
            return None
        return raw


def _content_id(value):
    if not isinstance(value, str) or not value or len(value) > 200 or '\x00' in value:
        raise ContractError('invalid_voice_request')
    return value


def _revision(value):
    if type(value) is not int or value < 1:
        raise ContractError('invalid_voice_request')
    return value


def _script(value):
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_SCRIPT_CHARS or '\x00' in value:
        raise ContractError('invalid_voice_request')
    try:
        value.encode('utf-8')
    except UnicodeError:
        raise ContractError('invalid_voice_request') from None
    return value


def _seed(value):
    if type(value) is not int or not 0 <= value <= MAX_SEED:
        raise ContractError('invalid_voice_request')
    return value


def _is_wav(raw):
    return isinstance(raw, bytes) and 44 <= len(raw) <= MAX_ASSET_BYTES and raw[:4] == b'RIFF' and raw[8:12] == b'WAVE'


def _measured_seconds(info):
    """probe가 실측한 seconds만 쓴다. 명목상 duration은 읽지 않는다."""
    if not isinstance(info, dict) or info.get('has_audio') is False:
        return None
    value = info.get('seconds')
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0 or value > MAX_SECONDS:
        return None
    return float(value)


def _generation_id(generated):
    if not isinstance(generated, dict) or not isinstance(generated.get('status'), str):
        return None
    value = generated.get('id')
    return value if isinstance(value, str) and GENERATION_ID.fullmatch(value) else None


class VoiceTaskService:
    def __init__(self, store, content_store, client, *, profile_id, enabled=False, probe=production_media.probe_media):
        if not isinstance(profile_id, str) or not profile_id:
            raise ContractError('invalid_voicebox_registration')
        self.store, self.content_store, self.client = store, content_store, client
        self.profile_id, self.enabled, self.probe = profile_id, enabled is True, probe

    def _require_enabled(self):
        if not self.enabled:
            raise ContractError('voicebox_disabled')

    def _snapshot(self, content_id, revision=None):
        try:
            return self.content_store.get(content_id, revision)
        except StoreError as exc:
            raise ContractError('content_store_unavailable') from exc

    def _intent(self, snapshot, script, seed):
        payload = json.dumps({'owner': snapshot['owner_account_id'], 'content_id': snapshot['id'],
                              'revision': snapshot['revision'], 'manifest_hash': snapshot['manifest_hash'],
                              'script': script, 'seed': seed, 'profile_id': self.profile_id},
                             sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        return _hash(payload.encode('utf-8'))

    # --- create -----------------------------------------------------------
    def create(self, content_id, expected_revision, script, seed=14005):
        self._require_enabled()
        content_id, revision = _content_id(content_id), _revision(expected_revision)
        script, seed = _script(script), _seed(seed)
        snapshot = self._snapshot(content_id, revision)
        if snapshot is None:
            raise ContractError('content_not_found')
        intent = self._intent(snapshot, script, seed)
        existing = self.store.find_intent(intent)
        if existing is not None:
            return _public(existing)  # 완료된 작업도 native 호출 없이 반환
        head = self._snapshot(content_id)
        if head is None or head['revision'] != revision or head['manifest_hash'] != snapshot['manifest_hash']:
            raise ContractError('content_revision_conflict')
        try:
            ready = self.client.ready() is True
        except Exception:
            ready = False
        if not ready:
            raise ContractError('voicebox_unavailable')
        row, created = self.store.claim(owner_account_id=snapshot['owner_account_id'], content_id=content_id,
                                        input_revision=revision, manifest_hash=snapshot['manifest_hash'],
                                        script=script, seed=seed, intent_hash=intent)
        if not created:
            return _public(row)
        return self._post(row)

    def _post(self, row):
        # 작업 잠금을 잡은 뒤 행을 다시 읽는다. claim 이후 복구가 먼저 연결했거나 상태가 바뀌었으면 합성하지 않는다.
        # 잠금이 busy면 예외가 나고 native POST는 없다(행은 started로 남는다).
        with self.store.task_lock(row['task_id']):
            fresh = self.store.get_row(row['task_id'])
            if fresh is None:
                raise ContractError('task_not_found')
            if fresh['state'] != 'started' or fresh['generation_id'] is not None:
                return _public(fresh)
            body = dict(profile_id=self.profile_id, text=fresh['script'], language='ko', engine='qwen',
                        model_size='0.6B', seed=fresh['seed'], normalize=True, max_chunk_chars=250)
            try:
                generation_id = _generation_id(self.client.generate(**body))
            except Exception:
                generation_id = None
            if generation_id is None:
                # 요청이 도달했는지 알 수 없다. 자동 재합성 금지이므로 unknown으로 남긴다.
                self.store.transition(fresh['task_id'], ('started',), state='unknown',
                                      reason_code='voicebox_request_unknown')
            else:
                self.store.transition(fresh['task_id'], ('started',), state='pending', generation_id=generation_id)
            return self.store.get(fresh['task_id'])

    # --- 명시적 복구 연결 -------------------------------------------------
    @staticmethod
    def _recovery_args(task_id, generation_id):
        try:
            _task_id(task_id)
        except ContractError:
            raise ContractError('invalid_voice_request') from None
        if not isinstance(generation_id, str) or RECOVERY_ID.fullmatch(generation_id) is None:
            raise ContractError('invalid_voice_request')

    def _candidate(self, row, generation_id):
        """native history 한 건을 GET으로 조회해 작업 입력과 정확히 일치하는지 확인한다. 원문은 노출하지 않는다."""
        inspect = getattr(self.client, 'inspect_generation', None)
        if not callable(inspect):
            raise ContractError('voice_recovery_unverifiable')
        try:
            found = inspect(generation_id)
        except Exception:
            raise ContractError('voice_recovery_unverifiable') from None
        if not isinstance(found, dict) or set(found) != CANDIDATE_FIELDS:
            raise ContractError('voice_recovery_unverifiable')
        texts = ('id', 'status', 'profile_id', 'text', 'language', 'engine', 'model_size')
        if not all(isinstance(found[k], str) for k in texts) or type(found['seed']) is not int:
            raise ContractError('voice_recovery_unverifiable')
        if (found['id'] != generation_id or found['status'] not in RECOVERY_STATUSES
                or found['profile_id'] != self.profile_id or found['text'].strip() != row['script'].strip()
                or found['seed'] != row['seed'] or found['language'] != 'ko' or found['engine'] != 'qwen'
                or found['model_size'] != '0.6B'):
            raise ContractError('voice_recovery_mismatch')

    def _fingerprint(self, row, generation_id):
        payload = {'task_id': row['task_id'], 'version': row['version'], 'state': row['state'],
                   'input': {'owner': row['owner_account_id'], 'content_id': row['content_id'],
                             'revision': row['input_revision'], 'manifest_hash': row['manifest_hash'],
                             'intent_hash': row['intent_hash']},
                   'candidate': {'id': generation_id, 'text_sha256': _hash(row['script'].strip().encode('utf-8')),
                                 'seed': row['seed'], 'language': 'ko', 'engine': 'qwen', 'model_size': '0.6B'}}
        return _hash(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))

    def _recovery_check(self, task_id, generation_id):
        """작업 잠금 안에서 호출한다. 모두 통과하면 (fresh row, fingerprint). native는 GET 한 번뿐이다."""
        row = self.store.get_row(task_id)
        if row is None:
            raise ContractError('task_not_found')
        if row['state'] not in RECOVERABLE_STATES or row['generation_id'] is not None:
            raise ContractError('voice_recovery_conflict')
        snapshot = self._snapshot(row['content_id'], row['input_revision'])
        if snapshot is None:
            raise ContractError('content_not_found')
        if (snapshot['revision'] != row['input_revision'] or snapshot['owner_account_id'] != row['owner_account_id']
                or snapshot['manifest_hash'] != row['manifest_hash']
                or self._intent(snapshot, row['script'], row['seed']) != row['intent_hash']):
            raise ContractError('voice_recovery_mismatch')
        head = self._snapshot(row['content_id'])
        if (head is None or head['revision'] != row['input_revision'] or head['manifest_hash'] != row['manifest_hash']
                or head['owner_account_id'] != row['owner_account_id']):
            raise ContractError('content_revision_conflict')
        if self.store.generation_task(generation_id) is not None:
            raise ContractError('voice_recovery_conflict')
        self._candidate(row, generation_id)
        return row, self._fingerprint(row, generation_id)

    def inspect_recovery(self, task_id, generation_id):
        """ID 없는 started/unknown 작업과 기존 생성 ID가 같은 입력인지 미리 본다. DB 전이도 POST도 없다."""
        self._require_enabled()
        self._recovery_args(task_id, generation_id)
        with self.store.task_lock(task_id):
            row, fingerprint = self._recovery_check(task_id, generation_id)
            return dict(task_id=task_id, generation_id=generation_id, recovery_fingerprint=fingerprint,
                        task_state=row['state'], can_confirm=True, review_status=REVIEW_STATUS)

    def confirm_recovery(self, task_id, generation_id, recovery_fingerprint):
        """검증을 다시 수행하고 DB CAS로 generation_id만 연결한다(pending). 오디오 다운로드/resume은 하지 않는다."""
        self._require_enabled()
        self._recovery_args(task_id, generation_id)
        if not isinstance(recovery_fingerprint, str) or FINGERPRINT.fullmatch(recovery_fingerprint) is None:
            raise ContractError('invalid_voice_request')
        with self.store.task_lock(task_id):
            current = self.store.get_row(task_id)
            if current is None:
                raise ContractError('task_not_found')
            if current['generation_id'] is not None:
                if current['generation_id'] == generation_id and current['state'] in LINKED_STATES:
                    return _public(current)  # 읽기 전용 replay
                raise ContractError('voice_recovery_conflict')
            row, expected = self._recovery_check(task_id, generation_id)
            if not hmac.compare_digest(expected, recovery_fingerprint):
                raise ContractError('voice_recovery_conflict')
            if self.store.link_generation(task_id, generation_id, row['version']) != 'linked':
                raise ContractError('voice_recovery_conflict')
            return self.store.get(task_id)

    # --- resume -----------------------------------------------------------
    def resume(self, task_id):
        self._require_enabled()
        row = self.store.get_row(_task_id(task_id))
        if row is None:
            raise ContractError('task_not_found')
        for _ in range(3):  # pending -> audio_ready -> completed
            state = row['state']
            if state == 'pending':
                row = self._poll(row)
            elif state == 'audio_ready':
                row = self._ingest(row)
            else:
                break  # started/unknown/종결 상태는 그대로 둔다. POST는 하지 않는다.
            if row['state'] == state:
                break
        return _public(row)

    def _move(self, row, from_states, **fields):
        self.store.transition(row['task_id'], from_states, **fields)
        return self.store.get_row(row['task_id'])

    def _fail(self, row, from_states, reason):
        return self._move(row, from_states, state='failed', reason_code=reason)

    def _poll(self, row):
        generation_id = row['generation_id']
        if not generation_id:
            return row
        try:  # GET만 사용한다.
            # 웹 요청은 합성이 끝날 때까지 수분간 대기하지 않는다.
            poll = getattr(self.client, 'poll_once', None)
            result = poll(generation_id) if callable(poll) else self.client.wait_completed(generation_id)
        except Exception:
            return row  # pending 유지, 다음 resume이 다시 GET
        if not isinstance(result, dict) or result.get('id') != generation_id:
            return row
        if result.get('status') in FAILED_STATUSES:
            return self._fail(row, ('pending',), 'voicebox_generation_failed')
        if result.get('status') != 'completed':
            return row
        try:
            raw = self.client.audio(generation_id)
        except Exception:
            return row
        return self._store_audio(row, raw)

    def _store_audio(self, row, raw):
        if not _is_wav(raw):
            return self._fail(row, ('pending',), 'voicebox_audio_invalid')
        tmp = None
        try:
            tmp = self.store.stage_artifact(row['task_id'], raw)
            try:
                info = self.probe(tmp)
            except Exception:
                return self._fail(row, ('pending',), 'voicebox_probe_failed')
            seconds = _measured_seconds(info)
            if seconds is None:
                return self._fail(row, ('pending',), 'voicebox_duration_invalid')
            relative = self.store.publish_artifact(row['task_id'], tmp, raw)
            if relative is None:
                return self._fail(row, ('pending',), 'voicebox_artifact_conflict')
        finally:
            self.store.discard_artifact(tmp)
        return self._move(row, ('pending',), state='audio_ready', audio_sha256=_hash(raw), audio_size=len(raw),
                          audio_path=relative, seconds=seconds)

    # --- CAS ingest / 복구 -----------------------------------------------
    def _ingest(self, row):
        raw = self.store.read_artifact(row)
        if raw is None:
            return self._fail(row, ('audio_ready',), 'voicebox_artifact_invalid')
        filename = f'voicebox-{row["task_id"]}.wav'
        for _ in range(3):  # add_asset 후 다음 반복이 읽기 복구 경로로 완료를 연결한다.
            try:
                head = self._snapshot(row['content_id'])
                verdict = self._judge(row, head, filename)
            except (ContractError, StoreError):
                return row  # 읽기 실패는 상태를 바꾸지 않고 다음 resume에 맡긴다.
            if verdict[0] == 'changed':
                return self._move(row, ('audio_ready',), state='content_changed', reason_code='content_changed')
            if verdict[0] == 'done':
                return self._move(row, ('audio_ready',), state='completed', reason_code=None,
                                  output_revision=verdict[1], asset_id=verdict[2])
            try:
                self.content_store.add_asset(row['content_id'], row['input_revision'], filename, 'audio/wav', raw)
            except ConflictError:
                continue  # 다른 resume이 먼저 등록했을 수 있다. 다시 읽어 판단한다.
            except StoreError as exc:
                if exc.code in ('too_large', 'unsupported_media', 'invalid'):
                    return self._fail(row, ('audio_ready',), 'voicebox_ingest_rejected')
                return row
        return self.store.get_row(row['task_id'])

    def _judge(self, row, head, filename):
        """('ingest',) | ('done', revision, asset_id) | ('changed',). 불확실하면 changed."""
        changed = ('changed',)
        if head is None or head['owner_account_id'] != row['owner_account_id']:
            return changed
        if head['revision'] == row['input_revision']:
            return ('ingest',) if head['manifest_hash'] == row['manifest_hash'] else changed
        if head['revision'] != row['input_revision'] + 1:
            return changed
        base = self._snapshot(row['content_id'], row['input_revision'])
        if base is None or base['manifest_hash'] != row['manifest_hash'] or base['owner_account_id'] != head['owner_account_id']:
            return changed
        for key in ('title', 'kind', 'series', 'status', 'original', 'variants', 'sources'):
            if head.get(key) != base.get(key):
                return changed
        if len(head['assets']) != len(base['assets']) + 1 or head['assets'][:-1] != base['assets']:
            return changed
        added = head['assets'][-1]
        if (added['filename'] != filename or added['media_type'] != 'audio/wav'
                or added['sha256'] != row['audio_sha256'] or added['size'] != row['audio_size']):
            return changed
        try:
            _, data = self.content_store.read_asset(row['content_id'], head['revision'], added['id'])
        except StoreError as exc:
            if exc.code == 'storage_error':
                raise
            return changed
        if _hash(data) != row['audio_sha256']:
            return changed
        return ('done', head['revision'], added['id'])
