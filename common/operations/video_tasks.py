"""저장한 숏츠 계획을 기존 Remotion renderer로 만드는 영속 작업 저장소와 서비스.

원본 콘텐츠와 계획은 신뢰된 ContentStore/MediaPlanStore가 소유하고, 이 모듈은 작업 상태만 별도
SQLite(video-tasks.sqlite3)에 보존한다. create는 대기열 등록만 하고 파일 복사/렌더/외부 호출을 하지 않는다.
렌더는 명시 호출한 run_next 한 건뿐이며 자동 재렌더, lease, 프로세스 시작, worker thread는 없다.
성공 결과는 검토 전 영상 자산 등록이고 review_status는 항상 not_checked다.

defer_video_review=True로 구성한 서비스는 기술 조건을 모두 통과했지만 사람 검토가 비어 있는 영상을
awaiting_review로 보존한다(재렌더/재시도 없음, ContentStore 등록 없음). confirm_review의 pass는 사람이
수동으로 남긴 확인 기록(manual_review)이며 독립적인 AI 검증이 아니다. 콘텐츠의 최종 review_status는
어떤 경우에도 not_checked로 남는다.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
from uuid import UUID, uuid4

from .content_store import ConflictError, StoreError
from .media_plan_runtime import prepare_short_media, render_prepared_short
from .media_plans import media_plan_readiness
from .models import ContractError, thaw
from .production_media import MAX_ASSET_BYTES

DB_NAME = 'video-tasks.sqlite3'
LOCK_NAME = 'video-worker.lock'
SCHEMA_VERSION = 2
LEGACY_SCHEMA_VERSION = 1
APPLICATION_ID = 0x56494445
ARTIFACT_DIR = 'media-artifacts'
OUTPUT_NAME = 'short.mp4'
OUTPUT_TYPE = 'video/mp4'
REVIEW_STATUS = 'not_checked'
MAX_JSON_CHARS = 1000000
STATES = ('queued', 'preparing', 'rendering', 'rendered', 'awaiting_review', 'completed', 'blocked', 'failed',
          'unknown', 'content_changed')
LEGACY_STATES = tuple(s for s in STATES if s != 'awaiting_review')
NONTERMINAL = ('queued', 'preparing', 'rendering', 'rendered', 'awaiting_review', 'unknown')
COLUMNS = ('task_id', 'intent_hash', 'owner_account_id', 'content_id', 'input_revision', 'manifest_hash',
           'plan_revision', 'plan_hash', 'state', 'reason_code', 'prepared', 'result', 'attempt',
           'output_revision', 'asset_id', 'version')
MUTABLE = frozenset({'state', 'reason_code', 'prepared', 'result', 'attempt', 'output_revision', 'asset_id'})


def _ddl(states):
    return (
        'CREATE TABLE video_tasks(task_id TEXT PRIMARY KEY, intent_hash TEXT NOT NULL UNIQUE, '
        'owner_account_id TEXT NOT NULL, content_id TEXT NOT NULL, input_revision INTEGER NOT NULL, '
        'manifest_hash TEXT NOT NULL, plan_revision INTEGER NOT NULL, plan_hash TEXT NOT NULL, '
        'state TEXT NOT NULL CHECK(state IN (' + ','.join("'" + s + "'" for s in states) + ')), '
        'reason_code TEXT, prepared TEXT, result TEXT, attempt INTEGER NOT NULL DEFAULT 0, '
        'output_revision INTEGER, asset_id TEXT, version INTEGER NOT NULL DEFAULT 1)',
        'CREATE INDEX video_tasks_content ON video_tasks(content_id, input_revision)',
    )


DDL = _ddl(STATES)
LEGACY_DDL = _ddl(LEGACY_STATES)
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
    'video_review_required', 'video_review_changes_requested',
})
RESULT_KEYS = {'filename', 'media_type', 'size', 'sha256', 'evidence'}
CANDIDATE_KEYS = {'candidate', 'manifest'}
EVIDENCE_KEYS = {'kind', 'probe', 'font_sha256', 'inputs', 'disclosure'}
INPUT_KEYS = {'asset_id', 'path', 'sha256', 'source', 'origin', 'provenance', 'provenance_hash', 'reuse_request_id'}
CHECK_KEYS = {'audio_checked', 'font_checked', 'disclosure_checked', 'scenes_checked'}
DECISIONS = ('pass', 'changes_requested')
MAX_NOTES_CHARS = 2000
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
    def _verify(conn, legacy=False):
        """application_id/버전/테이블·인덱스 DDL/컬럼이 정확히 알려진 스키마일 때만 통과한다. 버전을 돌려준다."""
        version = conn.execute('PRAGMA user_version').fetchone()[0]
        if (conn.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID
                or version not in ((SCHEMA_VERSION, LEGACY_SCHEMA_VERSION) if legacy else (SCHEMA_VERSION,))):
            raise ContractError('video_storage_foreign')
        expected = DDL if version == SCHEMA_VERSION else LEGACY_DDL
        objects = {r[0]: r[1] for r in conn.execute("SELECT name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
        columns = tuple(r[1] for r in conn.execute('PRAGMA table_info(video_tasks)'))
        if objects != {'video_tasks': expected[0], 'video_tasks_content': expected[1]} or columns != COLUMNS:
            raise ContractError('video_storage_foreign')
        return version

    @contextmanager
    def _db(self, writable=False):
        """읽기 전용은 schema 1도 허용하지만 자동 migration은 하지 않는다. 쓰기는 schema 2만 허용한다."""
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
            self._verify(conn, legacy=not writable)
            yield conn
        except ContractError:
            raise
        except (OSError, sqlite3.Error, ValueError) as exc:
            raise ContractError('video_storage_error') from exc
        finally:
            if conn is not None:
                conn.close()

    def initialize(self):
        """유일한 생성/migration 지점. 외부/foreign DB와 symlink는 건드리지 않고 거부한다."""
        path = self._db_path()
        conn = None
        migrate = False
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            if path.exists():
                probe = self._connect(path, 'ro')
                try:
                    if self._is_empty(probe):
                        mode = 'rw'
                    else:
                        migrate = self._verify(probe, legacy=True) == LEGACY_SCHEMA_VERSION
                        mode = 'rw' if migrate else None
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
                if migrate:
                    self._migrate(conn)
                else:
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

    def _migrate(self, conn):
        """schema 1 -> 2. 호출자의 BEGIN IMMEDIATE 안에서 table/index를 재생성하고 모든 row를 그대로 옮긴다."""
        if self._verify(conn, legacy=True) != LEGACY_SCHEMA_VERSION:
            raise ContractError('video_storage_foreign')
        columns = ','.join(COLUMNS)
        conn.execute('DROP INDEX video_tasks_content')
        conn.execute('ALTER TABLE video_tasks RENAME TO video_tasks_v1')
        conn.execute(DDL[0])
        conn.execute('INSERT INTO video_tasks(rowid,%s) SELECT rowid,%s FROM video_tasks_v1 ORDER BY rowid'
                     % (columns, columns))
        self._verify_migrated(conn)
        conn.execute('DROP TABLE video_tasks_v1')
        conn.execute(DDL[1])
        conn.execute('PRAGMA user_version=%d' % SCHEMA_VERSION)
        self._verify(conn)

    @staticmethod
    def _verify_migrated(conn):
        columns = ','.join(COLUMNS)
        old = conn.execute('SELECT COUNT(*) FROM video_tasks_v1').fetchone()[0]
        new = conn.execute('SELECT COUNT(*) FROM video_tasks').fetchone()[0]
        lost = conn.execute('SELECT COUNT(*) FROM (SELECT %s FROM video_tasks_v1 EXCEPT SELECT %s FROM video_tasks)'
                            % (columns, columns)).fetchone()[0]
        if old != new or lost:
            raise ContractError('video_storage_error', 'migration verification failed')

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

    def transition(self, task_id, from_states, *, expected_version=None, **fields):
        """CAS: 현재 state가 from_states(그리고 주어지면 version이 expected_version)일 때만 갱신한다."""
        _task_id(task_id)
        reason = fields.get('reason_code')
        if (not fields or set(fields) - MUTABLE or fields.get('state') not in STATES or not from_states
                or set(from_states) - set(STATES) or (reason is not None and reason not in SAFE_REASONS)
                or (expected_version is not None and (type(expected_version) is not int or expected_version < 1))
                or any(fields.get(k) is not None and (not isinstance(fields[k], str) or len(fields[k]) > MAX_JSON_CHARS)
                       for k in ('prepared', 'result'))):
            raise ContractError('video_storage_error', 'invalid transition')
        columns = sorted(fields)
        sql = ('UPDATE video_tasks SET ' + ','.join(c + '=?' for c in columns) + ',version=version+1 '
               'WHERE task_id=? AND state IN (' + ','.join('?' * len(from_states)) + ')')
        args = [fields[c] for c in columns] + [task_id, *from_states]
        if expected_version is not None:
            sql += ' AND version=?'
            args.append(expected_version)
        with self._db(True) as conn:
            changed = conn.execute(sql, args).rowcount
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
                 reuse_authorization=None, probe=None, inspect_video=None, defer_video_review=False):
        self.store, self.content_store, self.plan_store = store, content_store, plan_store
        self.enabled, self.runner_factory = enabled is True, runner_factory
        self.reuse_authorization, self.probe, self.inspect_video = reuse_authorization, probe, inspect_video
        self.defer_video_review = defer_video_review is True

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
        preflight=getattr(self.reuse_authorization,'check_plan',None)
        if callable(preflight):preflight(content_id,revision)
        # 새 버전/계획의 명시 제작 요청은 더는 승인할 수 없는 옛 검토 대기를
        # 보관 상태로 옮긴다. 파일·검토 입력은 보존하고, 같은 입력의 재시도는 위에서 반환한다.
        for waiting in self.store.list_for_content(content_id):
            if waiting['state']!='awaiting_review':
                continue
            old=self.store.get_row(waiting['task_id'])
            if old is None or old['owner_account_id']!=snapshot['owner_account_id']:
                continue
            stale_content=old['input_revision']!=revision or old['manifest_hash']!=snapshot['manifest_hash']
            stale_plan=old['plan_revision']!=plan_revision or old['plan_hash']!=plan_hash
            if stale_content or stale_plan:
                self.store.transition(old['task_id'],('awaiting_review',),expected_version=old['version'],
                    state='content_changed',reason_code='content_changed' if stale_content else 'plan_changed')
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
        # defer 옵션이 꺼져 있으면 기존과 완전히 같은 호출이다.
        options = {'defer_video_review': True} if self.defer_video_review else {}
        try:  # 이 시점부터 렌더가 시작됐을 수 있다.
            result = render_prepared_short(prepared, runner_factory=self.runner_factory,
                                           reuse_authorization=self.reuse_authorization, probe=self.probe,
                                           inspect_video=self.inspect_video, **options)
        except Exception:
            return self._move(row, ('rendering',), state='unknown', reason_code='render_outcome_unknown')
        row = self._settle(row, prepared.artifact_root, result, prepared.manifest)
        return self._ingest(row) if row['state'] == 'rendered' else row

    def _settle(self, row, root, result, manifest=None):
        status = result.get('status') if isinstance(result, dict) else None
        if status in ('blocked', 'error'):
            return self._move(row, ('rendering',), state='blocked',
                              reason_code=_reason(result.get('reason_code'), 'media_render_blocked'))
        if status == 'awaiting_review' and self.defer_video_review and manifest is not None:
            return self._settle_awaiting(row, root, result, manifest)
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

    def _settle_awaiting(self, row, root, result, manifest):
        """leaf 보고를 믿지 않고 기술 조건을 독립 검증한 뒤 candidate+manifest를 durable하게 보존한다."""
        candidate = None
        try:
            review = self._review_manifest(manifest)
            assets = result.get('assets')
            item = assets[0] if isinstance(assets, (list, tuple)) and len(assets) == 1 else None
            if (isinstance(item, dict) and Path(item['path']) == root / OUTPUT_NAME
                    and item.get('media_type') == OUTPUT_TYPE):
                candidate = dict(filename=OUTPUT_NAME, media_type=OUTPUT_TYPE, size=item['size'],
                                 sha256=item['sha256'], evidence=thaw(item['evidence']))
            if candidate is not None and self._candidate_raw(root, candidate, review) is None:
                candidate = None
            stored = json.dumps(dict(candidate=candidate, manifest=review), sort_keys=True, allow_nan=False)
        except (KeyError, TypeError, ValueError, RecursionError, OSError):
            candidate = stored = None
        if candidate is None:
            return self._move(row, ('rendering',), state='blocked', reason_code='invalid_production_result')
        if len(stored) > MAX_JSON_CHARS:
            return self._move(row, ('rendering',), state='failed', reason_code='render_result_invalid')
        return self._move(row, ('rendering',), state='awaiting_review', reason_code='video_review_required',
                          result=stored)

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
        """rendered만 저장된 결과를 다시 검증해 CAS 등록한다. 그 밖의 상태(awaiting_review 포함)는 렌더 없이 그대로 돌려준다."""
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
        try:
            self._reauthorize_inputs(asset['evidence'])
        except ContractError:
            return self._move(row,('rendered',),state='rendered',reason_code='reuse_not_authorized')
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

    def _reauthorize_inputs(self,evidence):
        """렌더 중 철회된 이미지 확인을 완료 증거로 재사용하지 않는다."""
        inputs=evidence.get('inputs') if isinstance(evidence,dict) else None
        if not isinstance(inputs,list) or not inputs or not callable(self.reuse_authorization):
            raise ContractError('reuse_not_authorized')
        for item in inputs:
            if not isinstance(item,dict) or item.get('origin')!='reuse':
                raise ContractError('reuse_not_authorized')
            try:
                manifest={key:item[key] for key in ('path','sha256','source','reuse_request_id')}
                answer=self.reuse_authorization(manifest=manifest,asset=dict(path=item['path'],sha256=item['sha256']))
                if (not isinstance(answer,dict) or answer.get('authorized') is not True or answer.get('reviewed') is not True
                    or any(answer.get(key)!=manifest[key] for key in ('sha256','source','reuse_request_id'))):
                    raise ContractError('reuse_not_authorized')
            except Exception:
                raise ContractError('reuse_not_authorized') from None

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

    # --- 사람 검토 --------------------------------------------------------
    @staticmethod
    def _review_manifest(plan):
        """검토자에게 보이는 원고/장면 정보. 경로·음성·provenance는 포함하지 않는다."""
        plan = thaw(plan)
        scenes = [dict(index=i, kind=s['kind'], seconds=s['seconds'], title=s['title'], caption=s['caption'])
                  for i, s in enumerate(plan['scenes'], 1)]
        return dict(exam=plan['exam'], field=plan['field'], source=plan['source'], footer=plan['footer'],
                    disclosure=plan['disclosure'], scenes=scenes)

    @staticmethod
    def _read_file(path):
        """symlink가 아닌 일반 파일의 bytes. 아니면 None."""
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ASSET_BYTES:
            return None
        return path.read_bytes()

    def _candidate_raw(self, root, candidate, review):
        """저장/보고된 candidate를 실제 파일과 독립적으로 대조한다. 통과하면 영상 bytes, 아니면 None.

        leaf 보고(evidence)를 그대로 믿지 않고 bytes hash/size/MP4 header, 규격(1080x1920, 소리, 0<초<=20),
        font hash, 합성 고지, 입력 이미지 hash를 다시 확인한다. 검토 완료 flag가 섞인 evidence는 거부한다.
        """
        try:
            root = Path(root)
            if (root.is_symlink() or not isinstance(candidate, dict) or set(candidate) != RESULT_KEYS
                    or candidate['filename'] != OUTPUT_NAME or candidate['media_type'] != OUTPUT_TYPE
                    or type(candidate['size']) is not int or not isinstance(candidate['sha256'], str)
                    or not DIGEST.fullmatch(candidate['sha256'])):
                return None
            raw = self._read_file(root / OUTPUT_NAME)
            if (raw is None or len(raw) < 12 or raw[4:8] != b'ftyp' or len(raw) != candidate['size']
                    or _hash(raw) != candidate['sha256']):
                return None
            evidence = candidate['evidence']
            if not isinstance(evidence, dict) or set(evidence) != EVIDENCE_KEYS or evidence['kind'] != 'remotion_video':
                return None
            probe = evidence['probe']
            seconds = probe['seconds']
            if (not isinstance(probe, dict) or type(seconds) not in (int, float) or not math.isfinite(seconds)
                    or not 0 < seconds <= 20 or (probe['width'], probe['height']) != (1080, 1920)
                    or probe['has_audio'] is not True):
                return None
            disclosure = evidence['disclosure']
            if (not isinstance(evidence['font_sha256'], str) or not DIGEST.fullmatch(evidence['font_sha256'])
                    or not isinstance(disclosure, str) or 'AI 합성 음성' not in disclosure
                    or disclosure != review['disclosure']):
                return None
            inputs = evidence['inputs']
            if not isinstance(inputs, list) or len(inputs) != len(review['scenes']):
                return None
            for item in inputs:
                if (not isinstance(item, dict) or set(item) != INPUT_KEYS or not isinstance(item['sha256'], str)
                        or not DIGEST.fullmatch(item['sha256']) or not isinstance(item['path'], str)):
                    return None
                path = Path(item['path'])
                if not path.is_absolute() or path.parent != root:
                    return None
                data = self._read_file(path)
                if data is None or _hash(data) != item['sha256']:
                    return None
            return raw
        except (KeyError, TypeError, ValueError, OSError, RecursionError):
            return None

    def _load_result(self, row):
        try:
            data = json.loads(row['result'], parse_constant=_reject_constant)
        except (TypeError, ValueError):
            return None
        if not isinstance(data, dict) or set(data) not in (CANDIDATE_KEYS, CANDIDATE_KEYS | {'changes_requested'}):
            return None
        return data

    def _verify_review(self, row):
        """awaiting_review 행을 저장물·실제 파일·현재 원고/계획과 모두 대조한다. (root, data, raw, fingerprint)."""
        try:
            root = self._artifact_root(row)
            data = self._load_result(row)
            if root is None or data is None or set(data) != CANDIDATE_KEYS:
                raise ContractError('video_review_invalid')
            try:
                head = self.content_store.get(row['content_id'])
                record = self.plan_store.get(row['content_id'], row['input_revision']) if head is not None else None
            except StoreError:
                raise ContractError('content_store_unavailable') from None
            if (head is None or head['owner_account_id'] != row['owner_account_id']
                    or head['revision'] != row['input_revision'] or head['manifest_hash'] != row['manifest_hash']):
                raise ContractError('content_changed')
            if (record is None or record['plan_revision'] != row['plan_revision']
                    or record['owner_account_id'] != row['owner_account_id']
                    or record['manifest_hash'] != row['manifest_hash'] or self._plan_hash(record) != row['plan_hash']):
                raise ContractError('plan_changed')
            review = self._review_manifest(record['plan'])
            if data['manifest'] != review:
                raise ContractError('video_review_invalid')
            candidate = data['candidate']
            raw = self._candidate_raw(root, candidate, review)
            if raw is None:
                raise ContractError('video_review_invalid')
            self._reauthorize_inputs(candidate['evidence'])
            fingerprint = _hash(_canonical(dict(
                version=row['version'], task_id=row['task_id'], owner=row['owner_account_id'],
                input=dict(content_id=row['content_id'], input_revision=row['input_revision'],
                           manifest_hash=row['manifest_hash']),
                plan=dict(plan_revision=row['plan_revision'], plan_hash=row['plan_hash']),
                output=dict(sha256=candidate['sha256'], size=candidate['size']),
                manifest=data['manifest'], evidence=candidate['evidence'])).encode('utf-8'))
            return root, data, raw, fingerprint
        except ContractError:
            raise
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            raise ContractError('video_review_invalid') from None

    def _review_row(self, task_id):
        if not self.enabled:
            raise ContractError('video_disabled')  # 어떤 I/O도 하기 전에 거부
        row = self.store.get_row(_task_id(task_id))
        if row is None:
            raise ContractError('task_not_found')
        if row['state'] != 'awaiting_review':
            raise ContractError('video_review_unavailable')
        return row

    def review_context(self, task_id):
        """검토 화면용 읽기 전용 context. 경로/음성/provenance/actor는 노출하지 않는다."""
        row = self._review_row(task_id)
        _, data, _, fingerprint = self._verify_review(row)
        candidate = data['candidate']
        probe = candidate['evidence']['probe']
        media = dict(filename=OUTPUT_NAME, media_type=OUTPUT_TYPE, size=candidate['size'], sha256=candidate['sha256'],
                     seconds=probe['seconds'], width=probe['width'], height=probe['height'],
                     has_audio=probe['has_audio'])
        return dict(task_id=row['task_id'], state=row['state'], content_id=row['content_id'],
                    input_revision=row['input_revision'], plan_revision=row['plan_revision'],
                    context_fingerprint=fingerprint, scene_count=len(data['manifest']['scenes']), media=media,
                    manifest=data['manifest'], review_status=REVIEW_STATUS)

    def review_video(self, task_id):
        """(metadata, bytes). review_context와 같은 검증을 거치며 렌더/파일 쓰기/상태 전이가 없다."""
        row = self._review_row(task_id)
        _, data, raw, _ = self._verify_review(row)
        candidate = data['candidate']
        return (dict(filename=OUTPUT_NAME, media_type=OUTPUT_TYPE, size=candidate['size'], sha256=candidate['sha256']),
                raw)

    def confirm_review(self, task_id, context_fingerprint, decision, checks, notes, *, actor='console_user'):
        """사람이 직접 남기는 수동 검토 기록. 독립적인 AI 검증이 아니며 actor는 서버가 정한 값만 쓴다.

        pass: 모든 확인 항목이 True여야 하며 manual_review를 evidence에 남겨 기존 production 검증을 통과해야
        rendered로 저장하고 _ingest를 한 번 호출한다. changes_requested: blocked로 보존하고 등록/재렌더는 없다.
        """
        if not self.enabled:
            raise ContractError('video_disabled')
        task_id = _task_id(task_id)
        try:
            valid_notes=isinstance(notes,str) and len(notes)<=MAX_NOTES_CHARS and '\x00' not in notes
            if valid_notes:notes.encode('utf-8')
        except UnicodeError:
            valid_notes=False
        if (not isinstance(context_fingerprint, str) or not DIGEST.fullmatch(context_fingerprint)
                or not isinstance(decision, str) or decision not in DECISIONS
                or not isinstance(checks, dict) or set(checks) != CHECK_KEYS
                or any(type(v) is not bool for v in checks.values())
                or not valid_notes
                or not isinstance(actor, str) or not actor.strip() or len(actor) > 100 or '\x00' in actor):
            raise ContractError('invalid_video_review')
        if (decision == 'pass' and not all(checks.values())) or (decision == 'changes_requested' and not notes.strip()):
            raise ContractError('invalid_video_review')
        record = dict(actor=actor, notes=notes, fingerprint=context_fingerprint, checks=dict(checks))
        with self.store.worker_lock():
            row = self.store.get_row(task_id)
            if row is None:
                raise ContractError('task_not_found')
            if row['state'] != 'awaiting_review':
                return self._replay_review(row, decision, record)
            root, data, _, fingerprint = self._verify_review(row)
            if fingerprint != context_fingerprint:
                raise ContractError('video_review_stale')
            candidate = data['candidate']
            if decision == 'changes_requested':
                stored = json.dumps(dict(data, changes_requested=record), sort_keys=True, allow_nan=False)
                fields = dict(state='blocked', reason_code='video_review_changes_requested', result=stored)
            else:
                evidence = dict(candidate['evidence'], audio_checked=True, font_checked=True,
                                scenes=[dict(index=i, checked=True) for i in range(1, len(data['manifest']['scenes']) + 1)],
                                manual_review=dict(record))
                item = dict(path=str(root / OUTPUT_NAME), filename=OUTPUT_NAME, media_type=OUTPUT_TYPE,
                            size=candidate['size'], sha256=candidate['sha256'], evidence=evidence)
                if self._validated(root, item) is None:
                    raise ContractError('video_review_invalid')
                stored = json.dumps(dict(filename=OUTPUT_NAME, media_type=OUTPUT_TYPE, size=candidate['size'],
                                         sha256=candidate['sha256'], evidence=evidence), sort_keys=True, allow_nan=False)
                fields = dict(state='rendered', reason_code=None, result=stored)
            if not self.store.transition(task_id, ('awaiting_review',), expected_version=row['version'], **fields):
                raise ContractError('video_review_stale')
            row = self.store.get_row(task_id)
            if decision == 'pass':
                row = self._ingest(row)  # 한 번만. 실패/중단은 rendered로 남아 resume이 읽기 복구한다.
            return _public(row)

    def _replay_review(self, row, decision, record):
        """응답을 잃은 같은 요청의 재시도. 저장된 수동 기록과 정확히 같을 때만 읽기만으로 같은 공개 상태를 돌려준다."""
        conflict = ContractError('video_review_conflict')
        try:
            data = json.loads(row['result'], parse_constant=_reject_constant) if row['result'] else None
            root = self._artifact_root(row)
            if decision == 'pass' and row['state'] in ('rendered', 'completed'):
                saved = data['evidence']['manual_review'] if set(data) == RESULT_KEYS else None
                stored = data
            elif (decision == 'changes_requested' and row['state'] == 'blocked'
                  and row['reason_code'] == 'video_review_changes_requested' and set(data) == CANDIDATE_KEYS | {'changes_requested'}):
                saved, stored = data['changes_requested'], data['candidate']
            else:
                raise conflict
            raw = self._read_file(root / OUTPUT_NAME) if root is not None else None
        except (KeyError, TypeError, ValueError, OSError):
            raise conflict from None
        if saved != record or raw is None or len(raw) != stored['size'] or _hash(raw) != stored['sha256']:
            raise conflict
        return _public(row)
