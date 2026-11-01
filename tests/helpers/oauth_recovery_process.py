"""격리 OAuth 프로세스 시험 도구. 실제 provider/native/network 호출은 없다.

부모는 공개 경계 이름만 Pipe로 받고 SIGKILL한다. 관찰자는 실제 메서드가
commit한 뒤 멈추며 제품 코드의 예외 정리나 테스트 전용 hook을 사용하지 않는다.
"""
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from common.operations.credential_backend import MemoryCredentialBackend
from common.operations.managed_connections import ManagedConnectionStore
from common.operations.models import Connection, Registry
from common.operations.oauth_models import OAuthClientRegistration, OAuthPolicy, TokenBundle
from common.operations.oauth_service import CallbackContext, OAuthConnectionService, SessionContext
from common.operations.oauth_stage_backend import OwnedStageBackend
from common.operations.oauth_stage_models import logical_ref
from common.operations.oauth_stage_store import OAuthStageStore, migrate_to_owned_schema
from common.operations.oauth_store import OAuthAttemptStore
from common.operations.oauth_workspace import (
    initialize_workspace_owner, load_workspace_owner, oauth_write_guard,
    require_oauth_write_guard,
)
from tests.helpers.oauth_scoped_crash_fixture import DurableScopedRawBackend, crash_checkpoint
from tests.operations.test_oauth_service import FakeProvider


class DurableCalls:
    """OAuth DB 외부에서 fake 호출을 먼저 commit한다. 값/주소는 기록하지 않는다."""
    def __init__(self, path):
        self.path = Path(path)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS calls (name TEXT NOT NULL)')

    def record(self, name):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('INSERT INTO calls VALUES (?)', (name,))

    def counts(self):
        with closing(sqlite3.connect(self.path)) as db:
            return dict(db.execute('SELECT name,count(*) FROM calls GROUP BY name'))


class ProcessFixture:
    connection_id = 'personal.youtube'
    now = datetime(2026, 11, 1, tzinfo=timezone.utc)

    def __init__(self, root, vault_path, calls_path, *, initialize=False,
                 pipe=None, boundary=None, stage_kind=None):
        self.root = Path(root)
        self.vault_path = Path(vault_path)
        self.calls = DurableCalls(calls_path)
        self.context = (initialize_workspace_owner(self.root) if initialize
                        else load_workspace_owner(self.root))
        self.attempts = OAuthAttemptStore(self.root, self.clock)
        if initialize:
            self.attempts.initialize()
            with oauth_write_guard(self.context):
                migrate_to_owned_schema(self.context)
        self.connections = ManagedConnectionStore(self.root, self.clock)
        self.journal = OAuthStageStore(self.context, self.clock)
        self.raw = DurableScopedRawBackend(self.vault_path)
        self.owned = OwnedStageBackend(self.context, self.raw)
        self.provider = FakeProvider()
        self.scope = self.provider.definition.read_scopes[0]
        self.registration = OAuthClientRegistration('youtube', 'fake-client', None,
            'https://console.test/oauth/callback/youtube', 1, (self.scope,),
            self.provider.definition.operations[0].evidence_revision, None)
        self.session = SessionContext('console_user', 'fake-process-binding')
        self.callback = CallbackContext('youtube', self.registration.redirect_uri)
        self.registry = Registry('base', {'personal': {}, 'dept': {}}, {}, {},
            {self.connection_id: Connection(self.connection_id, 'personal', 'youtube', target_id='target')}, {}, {}, {})
        self.pipe, self.boundary, self.stage_kind = pipe, boundary, stage_kind
        self._observe()
        self.service = self.make_service()

    def clock(self):
        return self.now

    def make_service(self):
        return OAuthConnectionService(lambda: self.registry, {'youtube': self.registration},
            self.attempts, self.connections, MemoryCredentialBackend(), {'youtube': self.provider},
            OAuthPolicy(True), self.clock, cost_guard=lambda *args: None,
            workspace_context=self.context, stage_store=self.journal, owned_backend=self.owned)

    def probe(self):
        require_oauth_write_guard(self.root, self.context.owner)
        with closing(sqlite3.connect(self.root/'oauth.sqlite3', timeout=0)) as db:
            db.execute('BEGIN IMMEDIATE')
            db.rollback()

    def checkpoint(self, name, ref=None):
        if (self.boundary == name and
                (self.stage_kind is None or (ref is not None and logical_ref(ref).kind == self.stage_kind))):
            crash_checkpoint(self.pipe, name)

    def _after(self, target, method, callback):
        original = getattr(target, method)
        def wrapped(*args, **kwargs):
            result = original(*args, **kwargs)
            callback(args, kwargs, result)
            return result
        setattr(target, method, wrapped)

    def _before_commit(self, target, method, boundary, ref_from_args=None):
        """관찰 대상 메서드의 실제 transaction body와 commit 사이만 멈춘다."""
        if self.boundary != boundary:
            return
        original_method = getattr(target, method)
        original_db = target._db
        def wrapped(*args, **kwargs):
            @contextmanager
            def observed_db(write=False):
                with original_db(write) as db:
                    yield db
                    if write:
                        # The real INSERT/CAS ran, but OAuthDatabase._db has
                        # not validated pointers/committed its transaction yet.
                        assert db.in_transaction, 'fixture_expected_uncommitted_write'
                        self.checkpoint(boundary, ref_from_args(args) if ref_from_args else None)
            with patch.object(target, '_db', observed_db):
                return original_method(*args, **kwargs)
        setattr(target, method, wrapped)

    def _observe(self):
        for name in ('add', 'copy', 'delete'):
            original = getattr(self.raw, name)
            def raw_call(*args, _name=name, _original=original, **kwargs):
                self.probe()
                self.calls.record('raw_' + _name)
                result = _original(*args, **kwargs)
                if _name == 'delete': self.checkpoint('after_exact_delete')
                return result
            setattr(self.raw, name, raw_call)
        # A new process has no in-memory authorize challenge. This fake performs
        # no transport; exchange gets its verifier from the real service path.
        self.provider.exchange = lambda attempt, code, secret, verifier=None: TokenBundle(
            'fake-access', 'fake-refresh', 'Bearer', None, attempt['context'].requested_scopes)
        for name in ('authorize', 'exchange', 'inspect', 'refresh', 'revoke'):
            original = getattr(self.provider, name)
            def provider_call(*args, _name=name, _original=original, **kwargs):
                self.probe()
                self.calls.record('provider_' + _name)
                result = _original(*args, **kwargs)
                if _name == 'refresh': self.checkpoint('after_refresh_response')
                return result
            setattr(self.provider, name, provider_call)
        self._before_commit(self.journal, 'begin_stage', 'before_intent', lambda args: args[1])
        self._after(self.journal, 'begin_stage', lambda a, k, r: self.checkpoint('after_intent', r.owned_ref))
        self._after(self.owned, 'put_owned', lambda a, k, r: self.checkpoint('after_put', a[0]))
        self._after(self.journal, 'mark_stored', lambda a, k, r: self.checkpoint('after_stored', r.owned_ref))
        self._after(self.attempts, 'update_attempt', lambda a, k, r:
            self.checkpoint('after_token_pointer') if a[3] == 'token_exchanged' else None)
        self._before_commit(self.connections, 'create_target_proposal', 'before_proposal_commit')
        self._after(self.connections, 'create_target_proposal',
                    lambda a, k, r: self.checkpoint('after_proposal_commit'))
        self._after(self.connections, 'confirm_target', lambda a, k, r: self.checkpoint('after_confirm_pointer'))
        self._after(self.journal, 'mark_deleted', lambda a, k, r: self.checkpoint('after_mark_deleted'))
        original_finish = self.connections.finish_connection_operation
        def finish(*args, **kwargs):
            self.checkpoint('before_refresh_pointer')
            result = original_finish(*args, **kwargs)
            self.checkpoint('after_refresh_pointer')
            return result
        self.connections.finish_connection_operation = finish

    def start_body(self, key='new-start', revision=0):
        return dict(request_key=key, account_id='personal', provider_id='youtube',
            connection_id=self.connection_id, expected_base_revision='base',
            expected_connection_revision=revision, requested_scopes=[self.scope])

    def start(self, key='start', revision=0):
        item = self.service.start(self.session, self.start_body(key, revision))
        return item, parse_qs(urlsplit(item['authorize_url']).query)['state'][0]

    def staged(self, prefix='initial', revision=0):
        item, state = self.start(prefix+'-start', revision)
        self.service.receive_callback('youtube', dict(state=state, code='fake-code'), self.callback)
        return self.service.read_attempt(self.session, item['attempt_id'])

    def exchanged(self, prefix='initial', revision=0):
        item = self.staged(prefix, revision)
        return self.service.resume_exchange(self.session, item['attempt_id'],
            dict(request_key=prefix+'-continue', expected_revision=item['revision']))

    def proposal(self, prefix='initial', revision=0):
        item = self.exchanged(prefix, revision)
        return self.service.inspect(self.session, item['attempt_id'],
            dict(request_key=prefix+'-inspect', expected_revision=item['revision']))

    def connected(self):
        item = self.proposal()
        return self.service.confirm_target(self.session, item['target_proposal']['proposal_id'],
            dict(request_key='initial-confirm', expected_base_revision='base', expected_connection_revision=0))

    def snapshot(self):
        return self.journal.recovery_snapshot(self.context.owner)

    def read(self, ref):
        with oauth_write_guard(self.context):
            return self.owned.read_owned(ref)

    def cleanup(self):
        from common.operations.oauth_recovery import cleanup_recovery
        snap = self.snapshot()
        return cleanup_recovery(self.context, self.journal, self.owned,
            expected_workspace_id=self.context.owner.workspace_id,
            expected_journal_revision=snap.journal_revision,
            expected_graph_revision=snap.graph_revision)


def recovery_worker(root, vault_path, calls_path, pipe, action, boundary, stage_kind, inputs):
    """spawn target: no payload/ref/key/result is sent or printed."""
    try:
        fixture = ProcessFixture(root, vault_path, calls_path, pipe=pipe,
                                 boundary=boundary, stage_kind=stage_kind)
        if action == 'start': fixture.service.start(fixture.session, inputs['body'])
        elif action == 'callback':
            fixture.service.receive_callback('youtube', inputs, fixture.callback)
        elif action == 'continue':
            fixture.service.resume_exchange(fixture.session, inputs['attempt_id'], inputs['body'])
        elif action == 'confirm':
            fixture.service.confirm_target(fixture.session, inputs['proposal_id'], inputs['body'])
        elif action == 'inspect':
            fixture.service.inspect(fixture.session, inputs['attempt_id'], inputs['body'])
        elif action == 'refresh':
            fixture.service.refresh(fixture.session, fixture.connection_id, inputs['body'])
        elif action == 'cleanup': fixture.cleanup()
        else: raise ValueError('invalid_fixture_action')
        pipe.send('worker_completed')
    except BaseException:
        pipe.send('worker_failed')
    finally:
        pipe.close()
