"""저장한 숏츠 계획을 기존 Remotion renderer로 만드는 영속 작업 저장소와 서비스.

원본 콘텐츠와 계획은 신뢰된 ContentStore/MediaPlanStore가 소유하고, 이 모듈은 작업 상태만 별도
SQLite(video-tasks.sqlite3)에 보존한다. create는 대기열 등록만 하고 파일 복사/렌더/외부 호출을 하지 않는다.
렌더는 명시 호출한 run_next 한 건뿐이며 자동 재렌더, lease, 프로세스 시작, worker thread는 없다.
성공 결과는 검토 전 영상 자산 등록이고 review_status는 항상 not_checked다.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from uuid import UUID, uuid4

from .content_store import ConflictError, StoreError
from .media_plan_runtime import prepare_short_media, render_prepared_short
from .media_plans import media_plan_readiness
from .models import ContractError

DB_NAME = 'video-tasks.sqlite3'
LOCK_NAME = 'video-worker.lock'
SCHEMA_VERSION = 1
APPLICATION_ID = 0x56494445
ARTIFACT_DIR = 'media-artifacts'
OUTPUT_NAME = 'short.mp4'
OUTPUT_TYPE = 'video/mp4'
REVIEW_STATUS = 'not_checked'
MAX_JSON_CHARS = 1000000
STATES = ('queued', 'preparing', 'rendering', 'rendered', 'completed', 'blocked', 'failed', 'unknown',
          'content_changed')
NONTERMINAL = ('queued', 'preparing', 'rendering', 'rendered', 'unknown')
COLUMNS = ('task_id', 'intent_hash', 'owner_account_id', 'content_id', 'input_revision', 'manifest_hash',
           'plan_revision', 'plan_hash', 'state', 'reason_code', 'prepared', 'result', 'attempt',
           'output_revision', 'asset_id', 'version')
MUTABLE = frozenset({'state', 'reason_code', 'prepared', 'result', 'attempt', 'output_revision', 'asset_id'})
DDL = (
    'CREATE TABLE video_tasks(task_id TEXT PRIMARY KEY, intent_hash TEXT NOT NULL UNIQUE, '
    'owner_account_id TEXT NOT NULL, content_id TEXT NOT NULL, input_revision INTEGER NOT NULL, '
    'manifest_hash TEXT NOT NULL, plan_revision INTEGER NOT NULL, plan_hash TEXT NOT NULL, '
    'state TEXT NOT NULL CHECK(state IN (' + ','.join("'" + s + "'" for s in STATES) + ')), '
    'reason_code TEXT, prepared TEXT, result TEXT, attempt INTEGER NOT NULL DEFAULT 0, '
    'output_revision INTEGER, asset_id TEXT, version INTEGER NOT NULL DEFAULT 1)',
    'CREATE INDEX video_tasks_content ON video_tasks(content_id, input_revision)',
)
# 공개 reason_code 허용 목록. 이 밖의 값은 저장하지 않고 renderer reason은 media_render_blocked로 바꾼다.
SAFE_REASONS = frozenset({
    'content_changed', 'plan_changed', 'content_store_unavailable', 'media_inputs_required',
    'media_prepare_failed', 'media_render_blocked', 'render_outcome_unknown', 'render_result_invalid',
    'render_artifact_invalid', 'invalid_production_result', 'video_ingest_rejected',
    'renderer_unavailable', 'reuse_not_authorized', 'scene_asset_unregistered', 'scene_asset_mismatch',
    'scene_asset_changed', 'asset_changed', 'missing_required_media', 'media_too_large', 'unsafe_artifact_path',
    'unsupported_media', 'invalid_media_manifest', 'synthetic_disclosure_required', 'duration_exceeded',
    'audio_required', 'invalid_scene_registration', 'generation_not_authorized', 'media_probe_failed',
    'video_dimensions_or_audio', 'font_unchecked', 'video_unchecked', 'video_scenes_unchecked',
    'invalid_media_result', 'template_changed', 'artifact_already_exists', 'remotion_render_failed',
    'media_render_failed', 'media_validation_failed', 'invalid_remotion_registration',
})
RESULT_KEYS = {'filename', 'media_type', 'size', 'sha256', 'evidence'}
DIGEST = re.compile(r'[0-9a-f]{64}')


def _hash(data): return hashlib.sha256(data).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _task_id(value):
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise ContractError('invalid_task') from None
    if str(parsed) != value or parsed.version != 4:
        raise ContractError('invalid_task')
    return value


def _reason(value, default):
    return value if isinstance(value, str) and value in SAFE_REASONS else default


def _public(row):
    """내부 필드(owner/manifest/plan 해시/intent/result/prepared/attempt)를 뺀 안전 projection."""
    return dict(task_id=row['task_id'], state=row['state'], reason_code=row['reason_code'],
                content_id=row['content_id'], input_revision=row['input_revision'],
                plan_revision=row['plan_revision'], output_revision=row['output_revision'],
                asset_id=row['asset_id'], review_status=REVIEW_STATUS)


def _reject_constant(name):
    raise ValueError('non-finite JSON')


class VideoTaskStore:
    def __init__(self, root):
        self.root = Path(root).absolute()
        self._initialized = False

    # --- 연결 -------------------------------------------------------------
    def _db_path(self):
        path = self.root / DB_NAME
        if self.root.is_symlink() or path.is_symlink() or (path.exists() and not path.is_file()):
            raise ContractError('video_storage_unsafe')
        if path.exists() and not path.resolve().is_relative_to(self.root.resolve()):
            raise ContractError('video_storage_unsafe')
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
            raise ContractError('video_storage_foreign')
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
        columns = tuple(r[1] for r in conn.execute('PRAGMA table_info(video_tasks)'))
        if names != {'video_tasks', 'video_tasks_content'} or columns != COLUMNS:
            raise ContractError('video_storage_foreign')

    @contextmanager
    def _db(self, writable=False):
        if writable and not self._initialized:
            raise ContractError('video_storage_error', 'initialize() required')
        path = self._db_path()
        if not path.is_file():
            if writable:
                raise ContractError('video_storage_error')
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
            raise ContractError('video_storage_error') from exc
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
                    raise ContractError('video_storage_foreign')
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
            raise ContractError('video_storage_error') from exc
        finally:
            if conn is not None:
                conn.close()
        self._initialized = True

    # --- 전체 worker 잠금 -------------------------------------------------
    @contextmanager
    def worker_lock(self):
        """root/video-worker.lock에 비차단 flock. symlink/비정규 파일은 거부하고 이미 잡혀 있으면 busy."""
        if not self._initialized:
            raise ContractError('video_storage_error', 'initialize() required')
        if self.root.is_symlink():
            raise ContractError('video_storage_unsafe')
        try:
            fd = os.open(self.root / LOCK_NAME, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        except OSError as exc:
            raise ContractError('video_storage_unsafe') from exc
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ContractError('video_storage_unsafe')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ContractError('video_worker_busy') from None
            except OSError as exc:
                raise ContractError('video_storage_error') from exc
            yield
        finally:
            os.close(fd)  # 닫으면 잠금도 풀린다.

    # --- 작업 행 ----------------------------------------------------------
    def claim(self, *, owner_account_id, content_id, input_revision, manifest_hash, plan_revision, plan_hash,
              intent_hash):
        """BEGIN IMMEDIATE 아래에서 (row, created)를 돌려준다. 같은 intent는 상태와 무관하게 기존 행을 돌려준다."""
        with self._db(True) as conn:
            conn.execute('BEGIN IMMEDIATE')
            try:
                found = conn.execute('SELECT * FROM video_tasks WHERE intent_hash=?', (intent_hash,)).fetchone()
                if found is not None:
                    conn.commit()
                    return dict(found), False
                busy = conn.execute('SELECT 1 FROM video_tasks WHERE content_id=? AND state IN (%s) LIMIT 1'
                                    % ','.join('?' * len(NONTERMINAL)), (content_id, *NONTERMINAL)).fetchone()
                if busy is not None:
                    raise ContractError('video_task_conflict')
                task_id = str(uuid4())
                conn.execute('INSERT INTO video_tasks(task_id,intent_hash,owner_account_id,content_id,input_revision,'
                             'manifest_hash,plan_revision,plan_hash,state) VALUES(?,?,?,?,?,?,?,?,?)',
                             (task_id, intent_hash, owner_account_id, content_id, input_revision, manifest_hash,
                              plan_revision, plan_hash, 'queued'))
                row = conn.execute('SELECT * FROM video_tasks WHERE task_id=?', (task_id,)).fetchone()
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
            return dict(row), True

    def claim_next(self):
        """가장 오래된 queued 한 건을 preparing으로 원자 전이해 돌려준다. 없으면 None."""
        with self._db(True) as conn:
            conn.execute('BEGIN IMMEDIATE')
            try:
                found = conn.execute("SELECT task_id FROM video_tasks WHERE state='queued' "
                                     "ORDER BY rowid LIMIT 1").fetchone()
                if found is None:
                    conn.commit()
                    return None
                changed = conn.execute("UPDATE video_tasks SET state='preparing', attempt=attempt+1, "
                                       "version=version+1 WHERE task_id=? AND state='queued'",
                                       (found['task_id'],)).rowcount
                row = conn.execute('SELECT * FROM video_tasks WHERE task_id=?', (found['task_id'],)).fetchone()
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
            return dict(row) if changed == 1 else None

    def transition(self, task_id, from_states, **fields):
        """CAS: 현재 state가 from_states일 때만 갱신한다. 성공 여부를 돌려준다."""
        _task_id(task_id)
        reason = fields.get('reason_code')
        if (not fields or set(fields) - MUTABLE or fields.get('state') not in STATES or not from_states
                or set(from_states) - set(STATES) or (reason is not None and reason not in SAFE_REASONS)
                or any(fields.get(k) is not None and (not isinstance(fields[k], str) or len(fields[k]) > MAX_JSON_CHARS)
                       for k in ('prepared', 'result'))):
            raise ContractError('video_storage_error', 'invalid transition')
        columns = sorted(fields)
        sql = ('UPDATE video_tasks SET ' + ','.join(c + '=?' for c in columns) + ',version=version+1 '
               'WHERE task_id=? AND state IN (' + ','.join('?' * len(from_states)) + ')')
        with self._db(True) as conn:
            changed = conn.execute(sql, [fields[c] for c in columns] + [task_id, *from_states]).rowcount
        return changed == 1

    def get_row(self, task_id):
        _task_id(task_id)
        with self._db() as conn:
            if conn is None:
                return None
            found = conn.execute('SELECT * FROM video_tasks WHERE task_id=?', (task_id,)).fetchone()
            return dict(found) if found is not None else None

    def find_intent(self, intent_hash):
        with self._db() as conn:
            if conn is None:
                return None
            found = conn.execute('SELECT * FROM video_tasks WHERE intent_hash=?', (intent_hash,)).fetchone()
            return dict(found) if found is not None else None

    def get(self, task_id):
        row = self.get_row(task_id)
        return _public(row) if row is not None else None

    def list_for_content(self, content_id, revision=None):
        if not isinstance(content_id, str) or not content_id:
            raise ContractError('invalid_video_request')
        if revision is not None and (type(revision) is not int or revision < 1):
            raise ContractError('invalid_video_request')
        with self._db() as conn:
            if conn is None:
                return []
            if revision is None:
                rows = conn.execute('SELECT * FROM video_tasks WHERE content_id=? ORDER BY rowid', (content_id,))
            else:
                rows = conn.execute('SELECT * FROM video_tasks WHERE content_id=? AND input_revision=? '
                                    'ORDER BY rowid', (content_id, revision))
            return [_public(dict(r)) for r in rows.fetchall()]


def _content_id(value):
    if not isinstance(value, str) or not value or len(value) > 200 or '\x00' in value:
        raise ContractError('invalid_video_request')
    return value


def _revision(value):
    if type(value) is not int or value < 1:
        raise ContractError('invalid_video_request')
    return value


class VideoTaskService:
    def __init__(self, store, content_store, plan_store, *, enabled=False, runner_factory=None,
                 reuse_authorization=None, probe=None, inspect_video=None):
        self.store, self.content_store, self.plan_store = store, content_store, plan_store
        self.enabled, self.runner_factory = enabled is True, runner_factory
        self.reuse_authorization, self.probe, self.inspect_video = reuse_authorization, probe, inspect_video

    def get(self, task_id): return self.store.get(task_id)

    def list_for_content(self, content_id, revision=None): return self.store.list_for_content(content_id, revision)

    # --- create -----------------------------------------------------------
    def _load(self, content_id, revision):
        """(해당 버전 snapshot, 현재 head, 계획 record). 읽기만 한다."""
        try:
            snapshot = self.content_store.get(content_id, revision)
            head = self.content_store.get(content_id)
            record = self.plan_store.get(content_id, revision) if snapshot is not None else None
        except StoreError as exc:
            raise ContractError('content_not_found' if exc.code == 'not_found'
                                else 'content_store_unavailable') from None
        return snapshot, head, record

    @staticmethod
    def _plan_hash(record):
        return _hash(_canonical(record['plan']).encode('utf-8'))

    @staticmethod
    def _intent(snapshot, record, plan_hash):
        payload = _canonical({'owner': snapshot['owner_account_id'], 'content_id': snapshot['id'],
                              'revision': snapshot['revision'], 'manifest_hash': snapshot['manifest_hash'],
                              'plan_revision': record['plan_revision'], 'plan_hash': plan_hash})
        return _hash(payload.encode('utf-8'))

    def create(self, content_id, expected_revision, expected_plan_revision):
        content_id, revision = _content_id(content_id), _revision(expected_revision)
        plan_revision = _revision(expected_plan_revision)
        if not self.enabled or not callable(self.runner_factory):
            raise ContractError('video_renderer_unavailable')
        snapshot, head, record = self._load(content_id, revision)
        if snapshot is None:
            raise ContractError('content_not_found')
        if (record['plan_revision'] != plan_revision or record['owner_account_id'] != snapshot['owner_account_id']
                or record['manifest_hash'] != snapshot['manifest_hash']):
            raise ContractError('plan_revision_conflict')
        plan_hash = self._plan_hash(record)
        intent = self._intent(snapshot, record, plan_hash)
        existing = self.store.find_intent(intent)
        if existing is not None:
            return _public(existing)  # 완료/실패 작업도 재렌더 없이 반환
        if head is None or head['revision'] != revision or head['manifest_hash'] != snapshot['manifest_hash']:
            raise ContractError('content_revision_conflict')
        try:
            ready = media_plan_readiness(record['plan'])['inputs_ready']
        except StoreError:
            ready = False
        if not ready:
            raise ContractError('media_inputs_required')
        row, _ = self.store.claim(owner_account_id=snapshot['owner_account_id'], content_id=content_id,
                                  input_revision=revision, manifest_hash=snapshot['manifest_hash'],
                                  plan_revision=plan_revision, plan_hash=plan_hash, intent_hash=intent)
        return _public(row)

    # --- run_next ---------------------------------------------------------
    def _move(self, row, from_states, **fields):
        self.store.transition(row['task_id'], from_states, **fields)
        return self.store.get_row(row['task_id'])

    def run_next(self):
        """명시 호출 전용. queued 한 건만 처리하고 공개 projection 또는 None을 돌려준다."""
        if not self.enabled:
            raise ContractError('video_disabled')  # 어떤 I/O도 하기 전에 거부
        if not callable(self.runner_factory):
            raise ContractError('video_renderer_unavailable')
        with self.store.worker_lock():
            row = self.store.claim_next()
            if row is None:
                return None
            return _public(self._run(row))

    def _run(self, row):
        task_id = row['task_id']
        try:  # 시작 시점에 head와 계획을 다시 검사한다. 계획은 대기 중에 바뀔 수 있다.
            head = self.content_store.get(row['content_id'])
            record = self.plan_store.get(row['content_id'], row['input_revision']) if head is not None else None
        except StoreError:
            # 아직 아무것도 복사/렌더하지 않았으므로 queued로 되돌려 다음 명시 호출에 맡긴다.
            return self._move(row, ('preparing',), state='queued', reason_code='content_store_unavailable')
        if (head is None or head['owner_account_id'] != row['owner_account_id']
                or head['revision'] != row['input_revision'] or head['manifest_hash'] != row['manifest_hash']):
            return self._move(row, ('preparing',), state='content_changed', reason_code='content_changed')
        if (record['plan_revision'] != row['plan_revision'] or record['owner_account_id'] != row['owner_account_id']
                or record['manifest_hash'] != row['manifest_hash'] or self._plan_hash(record) != row['plan_hash']):
            return self._move(row, ('preparing',), state='content_changed', reason_code='plan_changed')
        try:
            ready = media_plan_readiness(record['plan'])['inputs_ready']
        except StoreError:
            ready = False
        if not ready:
            return self._move(row, ('preparing',), state='blocked', reason_code='media_inputs_required')
        try:
            prepared = prepare_short_media(record, content_store=self.content_store, attempt_id=task_id)
        except Exception as exc:
            code = getattr(exc, 'code', None)
            return self._move(row, ('preparing',), state='blocked' if code == 'media_inputs_required' else 'failed',
                              reason_code='media_inputs_required' if code == 'media_inputs_required'
                              else 'media_prepare_failed')
        prepared_json = json.dumps({'digest': prepared.plan_hash}, sort_keys=True)
        if not self.store.transition(task_id, ('preparing',), state='rendering', prepared=prepared_json):
            return self.store.get_row(task_id)
        row = self.store.get_row(task_id)
        try:  # 이 시점부터 렌더가 시작됐을 수 있다.
            result = render_prepared_short(prepared, runner_factory=self.runner_factory,
                                           reuse_authorization=self.reuse_authorization, probe=self.probe,
                                           inspect_video=self.inspect_video)
        except Exception:
            return self._move(row, ('rendering',), state='unknown', reason_code='render_outcome_unknown')
        row = self._settle(row, prepared.artifact_root, result)
        return self._ingest(row) if row['state'] == 'rendered' else row

    def _settle(self, row, root, result):
        status = result.get('status') if isinstance(result, dict) else None
        if status in ('blocked', 'error'):
            return self._move(row, ('rendering',), state='blocked',
                              reason_code=_reason(result.get('reason_code'), 'media_render_blocked'))
        if status != 'completed':
            return self._move(row, ('rendering',), state='unknown', reason_code='render_result_invalid')
        assets = result.get('assets')
        asset = None
        if isinstance(assets, (list, tuple)) and len(assets) == 1:
            asset = self._validated(root, assets[0])
        if asset is None:
            return self._move(row, ('rendering',), state='blocked', reason_code='invalid_production_result')
        try:  # 검증된 결과를 먼저 durable하게 남긴 뒤에만 등록한다.
            stored = json.dumps(dict(filename=OUTPUT_NAME, media_type=OUTPUT_TYPE, size=asset['size'],
                                     sha256=asset['sha256'], evidence=asset['evidence']),
                                sort_keys=True, allow_nan=False)
        except (TypeError, ValueError, RecursionError):
            return self._move(row, ('rendering',), state='failed', reason_code='render_result_invalid')
        return self._move(row, ('rendering',), state='rendered', result=stored)

    @staticmethod
    def _validated(root, item):
        """기존 production 검사기로 hash/MIME/검토 증거를 확인하고 예상 출력 경로만 허용한다."""
        from .production import validate_production_result
        try:
            checked = validate_production_result(dict(text='', assets=[item]), ('remotion_video',), root)
            if checked.get('status') != 'completed' or len(checked['assets']) != 1:
                return None
            asset = checked['assets'][0]
            if asset['media_type'] != OUTPUT_TYPE or Path(asset['path']) != root / OUTPUT_NAME:
                return None
            return asset
        except (KeyError, TypeError, ValueError, OSError):
            return None

    # --- resume -----------------------------------------------------------
    def resume(self, task_id):
        """rendered만 저장된 결과를 다시 검증해 CAS 등록한다. 그 밖의 상태는 렌더 없이 그대로 돌려준다."""
        if not self.enabled:
            raise ContractError('video_disabled')
        row = self.store.get_row(_task_id(task_id))
        if row is None:
            raise ContractError('task_not_found')
        if row['state'] == 'rendered':
            row = self._ingest(row)
        return _public(row)

    def _artifact_root(self, row):
        """DB의 digest와 task_id로만 artifact root를 다시 유도한다. 저장 경로는 믿지 않는다."""
        try:
            data = json.loads(row['prepared'], parse_constant=_reject_constant)
            digest = data['digest'] if isinstance(data, dict) and set(data) == {'digest'} else None
            if not isinstance(digest, str) or not DIGEST.fullmatch(digest):
                return None
            root = self.content_store._path(Path(ARTIFACT_DIR) / digest / row['task_id'])
            return root if root.is_dir() and not root.is_symlink() else None
        except (TypeError, ValueError, KeyError, OSError, StoreError):
            return None

    def _stored_asset(self, row, root):
        try:
            data = json.loads(row['result'], parse_constant=_reject_constant)
        except (TypeError, ValueError):
            return None
        if (not isinstance(data, dict) or set(data) != RESULT_KEYS or data['filename'] != OUTPUT_NAME
                or data['media_type'] != OUTPUT_TYPE):
            return None
        return self._validated(root, dict(path=str(root / OUTPUT_NAME), filename=OUTPUT_NAME, media_type=OUTPUT_TYPE,
                                          size=data['size'], sha256=data['sha256'], evidence=data['evidence']))

    def _ingest(self, row):
        root = self._artifact_root(row)
        asset = self._stored_asset(row, root) if root is not None else None
        if asset is None:
            return self._move(row, ('rendered',), state='failed', reason_code='render_artifact_invalid')
        try:
            raw = Path(asset['path']).read_bytes()
        except OSError:
            return self._move(row, ('rendered',), state='failed', reason_code='render_artifact_invalid')
        if len(raw) != asset['size'] or _hash(raw) != asset['sha256']:
            return self._move(row, ('rendered',), state='failed', reason_code='render_artifact_invalid')
        filename = f'video-{row["task_id"]}.mp4'
        for _ in range(3):  # add_asset 후 다음 반복이 읽기 복구 경로로 완료를 연결한다.
            try:
                head = self.content_store.get(row['content_id'])
                verdict = self._judge(row, head, filename, asset)
            except (ContractError, StoreError):
                return row  # 읽기 실패는 상태를 바꾸지 않고 다음 resume에 맡긴다.
            if verdict[0] == 'changed':
                return self._move(row, ('rendered',), state='content_changed', reason_code='content_changed')
            if verdict[0] == 'done':
                return self._move(row, ('rendered',), state='completed', reason_code=None,
                                  output_revision=verdict[1], asset_id=verdict[2])
            try:
                self.content_store.add_asset(row['content_id'], row['input_revision'], filename, OUTPUT_TYPE, raw)
            except ConflictError:
                continue  # 다른 resume이 먼저 등록했을 수 있다. 다시 읽어 판단한다.
            except StoreError as exc:
                if exc.code in ('too_large', 'unsupported_media', 'invalid'):
                    return self._move(row, ('rendered',), state='failed', reason_code='video_ingest_rejected')
                return row
        return self.store.get_row(row['task_id'])

    def _judge(self, row, head, filename, asset):
        """('ingest',) | ('done', revision, asset_id) | ('changed',). 불확실하면 changed."""
        changed = ('changed',)
        if head is None or head['owner_account_id'] != row['owner_account_id']:
            return changed
        if head['revision'] == row['input_revision']:
            return ('ingest',) if head['manifest_hash'] == row['manifest_hash'] else changed
        if head['revision'] != row['input_revision'] + 1:
            return changed
        base = self.content_store.get(row['content_id'], row['input_revision'])
        if (base is None or base['manifest_hash'] != row['manifest_hash']
                or base['owner_account_id'] != head['owner_account_id']):
            return changed
        for key in ('title', 'kind', 'series', 'status', 'original', 'variants', 'sources'):
            if head.get(key) != base.get(key):
                return changed
        if len(head['assets']) != len(base['assets']) + 1 or head['assets'][:-1] != base['assets']:
            return changed
        added = head['assets'][-1]
        if (added['filename'] != filename or added['media_type'] != OUTPUT_TYPE
                or added['sha256'] != asset['sha256'] or added['size'] != asset['size']):
            return changed
        try:
            _, data = self.content_store.read_asset(row['content_id'], head['revision'], added['id'])
        except StoreError as exc:
            if exc.code == 'storage_error':
                raise
            return changed
        if _hash(data) != asset['sha256']:
            return changed
        return ('done', head['revision'], added['id'])
