"""콘텐츠 리비전별 미디어 제작 계획 저장소와 순수 검증기. 계획 저장은 제작·검토·실행이 아니다.

저장소는 별도 media-plans.sqlite3만 다룬다. 생성자와 get()은 파일이나 폴더를 만들지 않고,
명시 initialize()만 DB를 만든다. 원본 snapshot(owner/manifest/id/revision/assets)은 항상
content_store.get()으로 서버가 조회해 결속하며, 원본·자산·quota는 읽기만 한다.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import hashlib
import math
from pathlib import Path
import sqlite3

from .content_store import ConflictError, StoreError

DB_NAME = 'media-plans.sqlite3'
SCHEMA_VERSION = 1
PLAN_KEYS = {'exam', 'field', 'source', 'footer', 'disclosure', 'voice_asset_id', 'scenes'}
SCENE_KEYS = {'asset_id', 'kind', 'seconds', 'title', 'caption'}
SCENE_KINDS = ('diorama', 'diagram')
IMAGE_TYPES = ('image/png', 'image/jpeg', 'image/webp')
VOICE_TYPES = ('audio/wav',)
TEXT_LIMIT = 2000
TITLE_LIMIT = 300
CAPTION_LIMIT = 1000
MAX_SCENES = 30
MAX_SECONDS = 20
DEFAULT_DISCLOSURE = 'AI 합성 음성 · 검토 전'
DDL = (
    'CREATE TABLE IF NOT EXISTS media_plans(content_id TEXT NOT NULL, content_revision INTEGER NOT NULL, '
    'manifest_hash TEXT NOT NULL, owner_account_id TEXT NOT NULL, plan_revision INTEGER NOT NULL, '
    'plan TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(content_id,content_revision))',
)


def _invalid(): raise StoreError('invalid')
def _now(): return datetime.now(timezone.utc).isoformat()


def _text(value, limit):
    if type(value) is not str or len(value) > limit or '\x00' in value: _invalid()
    try: value.encode('utf-8')
    except UnicodeError: _invalid()
    return value


def _int(value, minimum):
    if type(value) is not int or value < minimum: _invalid()
    return value


def _assets(snapshot, media_types):
    """snapshot 자산 중 허용 media_type만 id 집합으로 돌려준다."""
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get('assets'), list): _invalid()
    ids = set()
    for asset in snapshot['assets']:
        if not isinstance(asset, dict) or type(asset.get('id')) is not str: _invalid()
        if asset.get('media_type') in media_types: ids.add(asset['id'])
    return ids


def default_media_plan(snapshot):
    """원고 snapshot에서 만든 빈 초안. 순수 함수이며 항상 새 dict를 돌려준다."""
    if not isinstance(snapshot, dict): _invalid()
    series, title = snapshot.get('series'), snapshot.get('title')
    exam = series if type(series) is str and series else '콘텐츠'
    return {'exam': _text(exam, TEXT_LIMIT), 'field': _text(title if title is not None else '', TEXT_LIMIT),
            'source': '', 'footer': '', 'disclosure': DEFAULT_DISCLOSURE, 'voice_asset_id': None, 'scenes': []}


def validate_media_plan(plan, snapshot):
    """계획을 snapshot 자산에 대해 검증하고 정규화한 새 dict를 돌려준다. 불완전해도 통과한다."""
    if not isinstance(plan, dict) or set(plan) != PLAN_KEYS: _invalid()
    images, voices = _assets(snapshot, IMAGE_TYPES), _assets(snapshot, VOICE_TYPES)
    result = {key: _text(plan[key], TEXT_LIMIT) for key in ('exam', 'field', 'source', 'footer', 'disclosure')}
    voice = plan['voice_asset_id']
    if voice is not None and (type(voice) is not str or voice not in voices): _invalid()
    result['voice_asset_id'] = voice
    scenes = plan['scenes']
    if not isinstance(scenes, list) or len(scenes) > MAX_SCENES: _invalid()
    normalized, total = [], []
    for scene in scenes:
        if not isinstance(scene, dict) or set(scene) != SCENE_KEYS: _invalid()
        asset_id, kind, seconds = scene['asset_id'], scene['kind'], scene['seconds']
        if type(asset_id) is not str or asset_id not in images: _invalid()
        if type(kind) is not str or kind not in SCENE_KINDS: _invalid()
        if type(seconds) not in (int, float) or not 0 < seconds <= MAX_SECONDS: _invalid()
        if type(seconds) is float and not math.isfinite(seconds): _invalid()
        total.append(seconds)
        normalized.append({'asset_id': asset_id, 'kind': kind, 'seconds': seconds,
                           'title': _text(scene['title'], TITLE_LIMIT), 'caption': _text(scene['caption'], CAPTION_LIMIT)})
    if math.fsum(total) > MAX_SECONDS: _invalid()
    result['scenes'] = normalized
    return result


def media_plan_readiness(plan):
    """제작 입력이 갖춰졌는지만 계산한다. 검토·완료·실행 증거는 판단하지 않는다.

    blockers 순서는 voice_required, scenes_required, diorama_required, distinct_diorama_required 고정이다.
    """
    if not isinstance(plan, dict) or not isinstance(plan.get('scenes'), list): _invalid()
    dioramas = [s.get('asset_id') for s in plan['scenes'] if isinstance(s, dict) and s.get('kind') == 'diorama']
    blockers = []
    if plan.get('voice_asset_id') is None: blockers.append('voice_required')
    if not plan['scenes']: blockers.append('scenes_required')
    if not 2 <= len(dioramas) <= 3: blockers.append('diorama_required')
    if not 2 <= len(set(dioramas)) <= 3: blockers.append('distinct_diorama_required')
    return {'inputs_ready': not blockers, 'blockers': blockers}


def _public(snapshot, plan_revision, plan):
    ready = media_plan_readiness(plan)
    return {'content_id': snapshot['id'], 'content_revision': snapshot['revision'],
            'manifest_hash': snapshot['manifest_hash'], 'owner_account_id': snapshot['owner_account_id'],
            'plan_revision': plan_revision, 'plan': plan, 'inputs_ready': ready['inputs_ready'],
            'blockers': ready['blockers'], 'execution_enabled': False, 'review_status': 'not_checked'}


def _dump(plan):
    return json.dumps(plan, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


class MediaPlanStore:
    def __init__(self, root, content_store):
        self.root = Path(root).absolute()
        self.content_store = content_store
        store_root = getattr(content_store, 'root', None)
        if not callable(getattr(content_store, 'get', None)) or store_root is None: _invalid()
        if self.root != Path(store_root).absolute(): _invalid()
        self._initialized = False

    def _path(self):
        path = self.root / DB_NAME
        if self.root.is_symlink() or path.is_symlink() or not path.resolve().is_relative_to(self.root.resolve()):
            raise StoreError('storage_error', 'Unsafe storage path')
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
            if conn.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION or not conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='media_plans'").fetchone():
                raise StoreError('storage_error', 'Unsupported media plan schema')
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
                has_tables = conn.execute("SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' LIMIT 1").fetchone()
                if version == 0 and has_tables:
                    raise StoreError('storage_error', 'Existing database is not a media plan store')
                if version not in (0, SCHEMA_VERSION):
                    raise StoreError('storage_error', 'Unsupported media plan schema version')
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

    def _snapshot(self, content_id, content_revision):
        """원본 snapshot을 content_store에서 읽는다. 호출자가 준 owner/manifest는 신뢰하지 않는다."""
        if type(content_id) is not str or not content_id: _invalid()
        _int(content_revision, 1)
        snapshot = self.content_store.get(content_id, content_revision)
        if snapshot is None: raise StoreError('not_found')
        if (not isinstance(snapshot, dict) or snapshot.get('id') != content_id or snapshot.get('revision') != content_revision
                or type(snapshot.get('manifest_hash')) is not str
                or snapshot.get('owner_account_id') not in ('personal', 'dept')):
            raise StoreError('storage_error', 'Invalid content snapshot')
        return snapshot

    @staticmethod
    def _stored(snapshot, row):
        """저장 행을 snapshot에 다시 결속·검증한다. 어긋나면 저장소 오류다."""
        revision = row['plan_revision']
        if (type(revision) is not int or revision < 1 or row['manifest_hash'] != snapshot['manifest_hash']
                or row['owner_account_id'] != snapshot['owner_account_id']):
            raise StoreError('storage_error', 'Invalid media plan row')
        try: return revision, validate_media_plan(json.loads(row['plan']), snapshot)
        except (StoreError, ValueError, TypeError) as exc:
            raise StoreError('storage_error', 'Invalid stored media plan') from exc

    def get(self, content_id, content_revision):
        snapshot = self._snapshot(content_id, content_revision)
        path = self._path()
        if not path.is_file(): return _public(snapshot, 0, default_media_plan(snapshot))
        with self._db() as conn:
            row = conn.execute('SELECT * FROM media_plans WHERE content_id=? AND content_revision=?',
                               (content_id, content_revision)).fetchone()
            if row is None: return _public(snapshot, 0, default_media_plan(snapshot))
            return _public(snapshot, *self._stored(snapshot, row))

    def save(self, content_id, content_revision, expected_revision, plan):
        if type(content_id) is not str or not content_id: _invalid()
        _int(content_revision, 1); _int(expected_revision, 0)
        if not self._initialized: raise StoreError('storage_error', 'initialize() required')
        snapshot = self._snapshot(content_id, content_revision)
        normalized = validate_media_plan(plan, snapshot)
        raw = _dump(normalized)
        with self._db(writable=True) as conn:
            conn.execute('BEGIN IMMEDIATE')
            try:
                row = conn.execute('SELECT * FROM media_plans WHERE content_id=? AND content_revision=?',
                                   (content_id, content_revision)).fetchone()
                current = 0 if row is None else self._stored(snapshot, row)[0]
                if current != expected_revision: raise ConflictError()
                conn.execute('INSERT INTO media_plans(content_id,content_revision,manifest_hash,owner_account_id,'
                             'plan_revision,plan,updated_at) VALUES(?,?,?,?,?,?,?) '
                             'ON CONFLICT(content_id,content_revision) DO UPDATE SET plan_revision=excluded.plan_revision, '
                             'plan=excluded.plan, updated_at=excluded.updated_at',
                             (content_id, content_revision, snapshot['manifest_hash'], snapshot['owner_account_id'],
                              current + 1, raw, _now()))
                conn.execute('COMMIT')
            except BaseException:
                conn.execute('ROLLBACK')
                raise
        return _public(snapshot, current + 1, normalized)

    def _import_asset(self, snapshot, asset_id, media_types):
        expected=next((a for a in snapshot['assets'] if a['id']==asset_id),None)
        if expected is None or expected.get('media_type') not in media_types: _invalid()
        asset,raw=self.content_store.read_asset(snapshot['id'],snapshot['revision'],asset_id)
        if (not isinstance(asset,dict) or not isinstance(raw,bytes)
                or any(asset.get(k)!=expected.get(k) for k in ('id','sha256','size','media_type'))
                or len(raw)!=expected.get('size') or hashlib.sha256(raw).hexdigest()!=expected.get('sha256')):
            raise StoreError('storage_error','Asset integrity failure')
        return asset,raw

    def import_plan(self, content_id, target_revision, expected_revision, source_revision,
                    source_plan_revision, voice_asset_id=None):
        """이전 계획만 명시 복사한다. 원본·자산·승인·검토를 생성하거나 변경하지 않는다."""
        _int(target_revision,1);_int(expected_revision,0)
        _int(source_revision,1);_int(source_plan_revision,1)
        if source_revision>=target_revision: _invalid()
        if voice_asset_id is not None and (type(voice_asset_id) is not str or not voice_asset_id): _invalid()
        if not self._initialized: raise StoreError('storage_error','initialize() required')
        with self._db(writable=True) as conn:
            conn.execute('BEGIN IMMEDIATE')
            try:
                source=self._snapshot(content_id,source_revision)
                target=self._snapshot(content_id,target_revision)
                if source['owner_account_id']!=target['owner_account_id']: _invalid()
                head=self.content_store.get(content_id)
                if not head or head['revision']!=target_revision or head['manifest_hash']!=target['manifest_hash']:
                    raise ConflictError()
                row=conn.execute('SELECT * FROM media_plans WHERE content_id=? AND content_revision=?',
                                 (content_id,source_revision)).fetchone()
                if row is None: raise StoreError('not_found')
                source_current,plan=self._stored(source,row)
                if source_current!=source_plan_revision: raise ConflictError()
                row=conn.execute('SELECT * FROM media_plans WHERE content_id=? AND content_revision=?',
                                 (content_id,target_revision)).fetchone()
                current=0 if row is None else self._stored(target,row)[0]
                if current!=expected_revision: raise ConflictError()
                images={scene['asset_id'] for scene in plan['scenes']}
                shared=[(asset_id,IMAGE_TYPES) for asset_id in images]
                if voice_asset_id is None and plan['voice_asset_id'] is not None:
                    shared.append((plan['voice_asset_id'],VOICE_TYPES))
                for asset_id,types in shared:
                    old,old_raw=self._import_asset(source,asset_id,types)
                    new,new_raw=self._import_asset(target,asset_id,types)
                    if (old_raw!=new_raw or any(old[k]!=new[k] for k in ('sha256','size','media_type'))):
                        _invalid()
                if voice_asset_id is not None:
                    self._import_asset(target,voice_asset_id,VOICE_TYPES)
                    plan['voice_asset_id']=voice_asset_id
                plan=validate_media_plan(plan,target)
                # 자산 검증 중 다른 콘텐츠 버전이 생겼으면 과거 버전에 저장하지 않는다.
                head=self.content_store.get(content_id)
                if not head or head['revision']!=target_revision or head['manifest_hash']!=target['manifest_hash']:
                    raise ConflictError()
                conn.execute('INSERT INTO media_plans(content_id,content_revision,manifest_hash,owner_account_id,'
                             'plan_revision,plan,updated_at) VALUES(?,?,?,?,?,?,?) '
                             'ON CONFLICT(content_id,content_revision) DO UPDATE SET plan_revision=excluded.plan_revision, '
                             'plan=excluded.plan, updated_at=excluded.updated_at',
                             (content_id,target_revision,target['manifest_hash'],target['owner_account_id'],
                              current+1,_dump(plan),_now()))
                conn.execute('COMMIT')
            except BaseException:
                conn.execute('ROLLBACK')
                raise
        return _public(target,current+1,plan)
