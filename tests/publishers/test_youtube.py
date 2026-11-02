"""실 managed adapter/service/legacy leaf를 fake Google 전송 경계까지 실행한다."""
import ast
import copy
import importlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from common.operations.models import Registry, Connection, ContractError
from common.operations.runtime_models import PublicationContext

NOW = datetime(2026, 10, 31, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[2]
KEYS = ('dept.youtube', 'personal.youtube')


def context(key='dept.youtube', **changes):
    account = key.split('.')[0]
    values = dict(content_id='content', content_revision=1, manifest_hash='manifest',
                  owner_account_id='personal', destination_account_id=account,
                  connection_id=key, target_id='UC-' + account, publication_purpose='initial',
                  schedule_slot='initial', options={'visibility': 'public'}, schedule_condition={},
                  registry_revision='registry', policy_revision='policy', auth_checked_at=NOW,
                  auth_expires_at=NOW + timedelta(hours=1), review_report_hashes=('review',), platform='youtube')
    return PublicationContext(**dict(values, **changes))


def snapshot():
    return dict(id='content', revision=1, manifest_hash='manifest', title='안전 <확인>', original='원본',
                variants=[dict(destination_account_id='dept', platform='youtube', text='배포 본문')],
                sources=[dict(url='https://example.org/source', note='공식 근거')],
                assets=[dict(id='asset-video', filename='short.mp4', media_type='video/mp4', size=5, sha256='a' * 64)])


def registry():
    return Registry('registry', {'dept': {}, 'personal': {}},
        {key + '.credential': dict(account_id=key.split('.')[0], platform='youtube') for key in KEYS},
        {'dept': dict(account_id='dept', lock_resource='profile:youtube-dept'),
         'personal': dict(account_id='personal', lock_resource='profile:youtube-personal')},
        {key: Connection(key, key.split('.')[0], 'youtube', target_id='UC-' + key.split('.')[0],
                         credential_ref=key + '.credential', profile_ref=key.split('.')[0], enabled=True) for key in KEYS},
        {'job-' + key: dict(executor_id={'dept.youtube': 'youtube.dept', 'personal.youtube': 'youtube.personal'}[key], connection_id=key, owner_account_id=key.split('.')[0],
                           enabled=True, execution_owner='managed', managed_eligible=True, policy_revision='policy', schedule_owner='console') for key in KEYS},
        {'policy': {}}, {})


class Request:
    def __init__(self, value): self.value = value
    def execute(self): return copy.deepcopy(self.value)


class UploadRequest:
    def __init__(self, owner): self.owner = owner
    def next_chunk(self, **kwargs):
        self.owner.calls.append(('next_chunk', kwargs))
        if self.owner.lost: raise OSError('secret-credential-value')
        return None, copy.deepcopy(self.owner.response)


class Resource:
    def __init__(self, owner, name): self.owner, self.name = owner, name
    def list(self, **kwargs):
        self.owner.calls.append((self.name + '.list', kwargs))
        if self.name == 'channels':
            return Request({'items': [dict(id=self.owner.channel, contentDetails={'relatedPlaylists': {'uploads': 'UU-fixture'}})]})
        if self.name == 'videos': return Request({'items': self.owner.videos})
        if self.name == 'playlistItems':
            return Request({'items': [{'contentDetails': {'videoId': 'remote'}}]})
        return Request({'items': []})
    def insert(self, **kwargs):
        self.owner.calls.append((self.name + '.insert', kwargs))
        if self.name == 'videos': return UploadRequest(self.owner)
        return Request({'id': 'followup'})
    def set(self, **kwargs):
        self.owner.calls.append((self.name + '.set', kwargs)); return Request({})
    def update(self, **kwargs):
        self.owner.calls.append((self.name + '.update', kwargs)); return Request({})


class FakeGoogle:
    def __init__(self, account):
        self.channel, self.calls, self.lost = 'UC-' + account, [], False
        self.response = {'id': 'remote', 'status': {'privacyStatus': 'public', 'uploadStatus': 'uploaded'}}
        self.videos = [dict(id='remote', snippet=dict(channelId=self.channel, title='안전 〈확인〉', description='배포 본문',
                          publishedAt=NOW.isoformat()), status=dict(privacyStatus='public', uploadStatus='processed'),
                          contentDetails=dict(duration='PT20S'), processingDetails=dict(processingStatus='succeeded'))]
    def channels(self): return Resource(self, 'channels')
    def videos_resource(self): return Resource(self, 'videos')
    def playlistItems(self): return Resource(self, 'playlistItems')
    def thumbnails(self): return Resource(self, 'thumbnails')
    def commentThreads(self): return Resource(self, 'commentThreads')
    def captions(self): return Resource(self, 'captions')


# videos()는 응답 fixture와 충돌하지 않게 별도 client facade로 노출한다.
class Client:
    def __init__(self, fake): self.fake = fake
    def videos(self): return self.fake.videos_resource()
    def __getattr__(self, name): return getattr(self.fake, name)


class InlineBridge:
    def __init__(self, handlers, credentials): self.handlers, self.credentials = handlers, credentials
    def read(self, executor, action, ctx, payload):
        return self.handlers[(executor, action)](ctx.to_dict(), payload, self.credentials[ctx.connection_id])
    def submit(self, executor, ctx, prepared, permit):
        return self.handlers[(executor, 'publish')](ctx.to_dict(), prepared, self.credentials[ctx.connection_id])


def isolated_functions(relative, names, namespace=None):
    """legacy 모듈 전체 import/환경 변경 없이 실제 함수 본문만 실행한다."""
    tree = ast.parse((ROOT / relative).read_text())
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    scope = {} if namespace is None else namespace
    exec(compile(ast.Module(body=nodes, type_ignores=[]), relative, 'exec'), scope)
    return SimpleNamespace(**{name: scope[name] for name in names})


class YoutubeTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('common.publishers.youtube'), 'YouTube managed adapter가 필요합니다')
        self.module = importlib.import_module('common.publishers.youtube')
        self.runtime = importlib.import_module('common.publishers.youtube_runtime')
        self.services_module = importlib.import_module('common.publishers.youtube_services')
        self.reg = registry()
        self.google = {key: FakeGoogle(key.split('.')[0]) for key in KEYS}
        self.credentials = {key: object() for key in KEYS}
        self.resolutions = []
        def factory(key, credentials):
            self.assertIs(credentials, self.credentials[key])
            self.resolutions.append(key)
            return self.services_module.GoogleYoutubeServices(Client(self.google[key]),
                media_factory=lambda asset, prepared: ('sealed-media', asset['id']), clock=lambda: NOW)
        self.handlers = self.runtime.build_youtube_handlers(self.reg, services_factory=factory, clock=lambda: NOW)
        self.adapter = self.module.build_adapter(self.reg, InlineBridge(self.handlers, self.credentials))

    def prepare(self, ctx=None, data=None): return self.adapter.prepare(ctx or context(), data or snapshot())

    def test_two_channels_use_exact_registered_target(self):
        for key in KEYS:
            ctx = context(key)
            observed = self.adapter.inspect_target(ctx)
            self.assertEqual(observed['target_id'], ctx.target_id)
            self.assertEqual(observed['login_subject'], ctx.target_id)
            result = self.adapter.submit(ctx, self.prepare(ctx), object())
            self.assertEqual(result.outcome, 'submitted')
            self.assertEqual(result.remote_id, 'remote')
            self.assertEqual(self.google[key].calls[0], ('channels.list', {'part': 'id,contentDetails', 'mine': True}))
        self.google['personal.youtube'].channel = 'UC-dept'
        ctx = context('personal.youtube')
        failed = self.adapter.submit(ctx, self.prepare(ctx), object())
        self.assertEqual(failed.outcome, 'failed')
        self.assertEqual(sum(n == 'videos.insert' for n, _ in self.google['personal.youtube'].calls), 1)

    def test_scheduled_is_not_verified(self):
        ctx = context(options={'visibility': 'private'}, schedule_condition={'kind': 'fixed', 'at': '2026-11-01T00:00:00Z'})
        prepared = self.prepare(ctx)
        self.google['dept.youtube'].response['status'] = dict(privacyStatus='private', publishAt='2026-11-01T00:00:00Z', uploadStatus='uploaded')
        result = self.adapter.submit(ctx, prepared, object())
        self.assertEqual(result.outcome, 'scheduled')
        self.assertEqual(result.scheduled_at, datetime(2026, 11, 1, tzinfo=timezone.utc))
        self.google['dept.youtube'].videos[0]['status'] = self.google['dept.youtube'].response['status']
        checked = self.adapter.verify(ctx, 'remote', snapshot())
        self.assertEqual(checked.outcome, 'pending')
        self.assertEqual(checked.evidence['visibility'], 'scheduled')

    def test_private_fallback_is_not_scheduled(self):
        ctx = context(options={'visibility': 'private'}, schedule_condition={'kind': 'fixed', 'at': '2026-11-01T00:00:00Z'})
        self.google['dept.youtube'].response['status'] = dict(privacyStatus='private', uploadStatus='uploaded')
        result = self.adapter.submit(ctx, self.prepare(ctx), object())
        self.assertEqual(result.outcome, 'submitted')
        self.assertIsNone(result.scheduled_at)
        self.assertEqual(result.evidence['visibility'], 'private')
        self.assertFalse(result.evidence['schedule_confirmed'])

    def test_upload_leaf_has_no_hidden_mutations_and_returns_id_first(self):
        ctx = context(options={'visibility': 'public', 'followup_intents': ['thumbnail', 'playlist', 'comment', 'caption', 'public_switch', 'tiktok']})
        result = self.adapter.submit(ctx, self.prepare(ctx), object())
        self.assertEqual(result.remote_id, 'remote')
        calls = self.google['dept.youtube'].calls
        self.assertEqual([name for name, _ in calls], ['channels.list', 'videos.insert', 'next_chunk'])
        self.assertEqual(calls[-1][1], {'num_retries': 0})
        self.assertEqual([item['action'] for item in result.evidence['followup_intents']],
                         ['thumbnail', 'playlist', 'comment', 'caption', 'public_switch', 'tiktok'])
        self.assertTrue(all(item['state'] == 'not_started' for item in result.evidence['followup_intents']))

    def test_lost_upload_response_does_not_insert_again(self):
        self.google['dept.youtube'].lost = True
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = self.adapter.submit(context(), self.prepare(), object())
            lookup = self.adapter.lookup(context(), {'created_at': NOW.isoformat()})
        self.assertEqual(result.outcome, 'unknown')
        self.assertEqual(lookup.outcome, 'unsupported')
        self.assertEqual(sum(n == 'videos.insert' for n, _ in self.google['dept.youtube'].calls), 1)
        self.assertTrue(any(n == 'playlistItems.list' for n, _ in self.google['dept.youtube'].calls))
        self.assertTrue(any(n == 'videos.list' for n, _ in self.google['dept.youtube'].calls))
        self.assertEqual(stdout.getvalue() + stderr.getvalue(), '')
        self.assertNotIn('secret-credential-value', str(result.to_dict()))

    def test_youtube_public_observation_is_only_candidate_without_local_hash_claim(self):
        result = self.adapter.verify(context(), 'remote', snapshot())
        self.assertEqual(result.outcome, 'verified')
        self.assertEqual(result.evidence['verification_method'], 'youtube_public_observation')
        self.assertIsNone(result.evidence.get('media_sha256'))
        self.assertEqual(result.evidence['description'], '배포 본문')
        self.assertEqual(result.evidence['target_id'], 'UC-dept')

    def test_lookup_exact_id_reads_video_but_does_not_claim_strong_match(self):
        result = self.adapter.lookup(context(), {'remote_id': 'remote', 'created_at': NOW.isoformat()})
        self.assertEqual(result.outcome, 'unsupported')
        self.assertEqual(result.candidates[0]['remote_id'], 'remote')
        self.assertEqual(result.evidence['reason'], 'media_evidence_required')
        self.assertEqual(sum(n == 'videos.insert' for n, _ in self.google['dept.youtube'].calls), 0)

    def test_mismatched_remote_channel_is_failed(self):
        self.google['dept.youtube'].videos[0]['snippet']['channelId'] = 'UC-other'
        self.assertEqual(self.adapter.verify(context(), 'remote', snapshot()).outcome, 'failed')

    def test_past_schedule_rejected_before_upload_without_public_fallback(self):
        ctx = context(schedule_condition={'kind': 'fixed', 'at': '2026-10-01T00:00:00Z'})
        result = self.adapter.submit(ctx, self.prepare(ctx), object())
        self.assertEqual(result.outcome, 'failed')
        self.assertEqual(sum(n == 'videos.insert' for n, _ in self.google['dept.youtube'].calls), 0)

    def test_prepared_and_context_cannot_select_another_account(self):
        prepared = self.prepare()
        prepared['target_id'] = 'UC-personal'
        with self.assertRaises(ContractError): self.adapter.submit(context(), prepared, object())
        with self.assertRaises(ContractError): self.adapter.inspect_target(context(target_id='UC-personal'))

    def test_prepare_is_pure_uses_approved_variant_and_asset_reference(self):
        before, env, paths = copy.deepcopy(snapshot()), dict(os.environ), list(sys.path)
        with patch('builtins.open', side_effect=AssertionError('open forbidden')), patch('socket.socket', side_effect=AssertionError('socket forbidden')):
            payload = self.prepare()
        self.assertEqual(payload['body']['snippet']['title'], '안전 〈확인〉')
        self.assertIn('배포 본문', payload['body']['snippet']['description'])
        self.assertIn('https://example.org/source', payload['body']['snippet']['description'])
        self.assertIn('#Shorts', payload['body']['snippet']['description'])
        self.assertEqual(payload['asset']['id'], 'asset-video')
        self.assertNotIn('path', payload['asset'])
        self.assertEqual(before, snapshot())
        self.assertEqual(env, dict(os.environ)); self.assertEqual(paths, sys.path)

    def test_missing_video_changed_snapshot_and_ambiguous_variant_rejected(self):
        for change in ({'revision': 2}, {'assets': []}, {'variants': snapshot()['variants'] * 2}):
            with self.subTest(change=change), self.assertRaises(ValueError): self.prepare(data=dict(snapshot(), **change))

    def test_resolver_account_platform_scope_exact_no_personal_fallback(self):
        from common.publishers.bridge_host import resolve_registered_credentials
        calls = []
        def resolve(ref, **kw): calls.append((ref, kw)); return object()
        resolve_registered_credentials('dept.youtube', registry=self.reg,
            credential_catalog=self.runtime.CREDENTIAL_CATALOG, resolver=resolve, scope='publication')
        self.assertEqual(calls, [('dept.youtube.credential', dict(account_id='dept', platform='youtube', scope='publication'))])
        with self.assertRaises(ContractError):
            self.runtime.resolve_youtube_credentials('dept.youtube.credential', account_id='personal', platform='youtube', scope='publication')
        with self.assertRaises(ContractError):
            self.runtime.resolve_youtube_credentials('personal.youtube.credential', account_id='personal', platform='blogger', scope='read')

    def test_default_factory_and_current_registry_remain_disabled(self):
        from common.publishers import build_adapters
        from common.operations.registry import load_registry
        self.assertEqual(build_adapters(), {})
        live = load_registry(ROOT / 'ax-console/config/operations.json')
        self.assertEqual(dict(self.runtime.build_youtube_catalog(live).executors), {})
        with patch.object(self.runtime, 'resolve_youtube_credentials', side_effect=AssertionError('credentials forbidden')):
            with self.assertRaises(ContractError): self.module.bridge_bootstrap()

    def test_approved_executor_ids_register_both_channels_and_reach_upload_leaf(self):
        catalog = self.runtime.build_youtube_catalog(self.reg)
        self.assertEqual({key: spec.job_ids for key, spec in catalog.executors.items()},
                         {'youtube.dept': ('job-dept.youtube',), 'youtube.personal': ('job-personal.youtube',)})
        for connection, executor in (('dept.youtube', 'youtube.dept'), ('personal.youtube', 'youtube.personal')):
            with self.subTest(connection=connection):
                self.assertIn((executor, 'inspect_target'), self.handlers)
                self.assertIn((executor, 'publish'), self.handlers)
                ctx = context(connection)
                self.assertEqual(self.adapter.inspect_target(ctx)['target_id'], ctx.target_id)
                result = self.adapter.submit(ctx, self.prepare(ctx), object())
                self.assertEqual(result.remote_id, 'remote')
                self.assertEqual(sum(name == 'videos.insert' for name, _ in self.google[connection].calls), 1)

    def test_static_catalog_uses_fixed_module_and_independent_host(self):
        catalog = self.runtime.build_youtube_catalog(self.reg)
        self.assertEqual(set(catalog.executors), {'youtube.dept', 'youtube.personal'})
        self.assertTrue(all(spec.module == 'common.publishers.youtube' for spec in catalog.executors.values()))
        from common.publishers.bridge_host import BridgeHost
        store = SimpleNamespace(locks=None)
        locks = object()
        host = self.runtime.build_youtube_host(self.reg, catalog, store, locks,
             services_factory=lambda key, credentials: None, credential_resolver=lambda *a, **k: None)
        self.assertIsInstance(host, BridgeHost)
        self.assertIs(store.locks, locks)

    def test_approved_required_followups_remain_pending_not_completed(self):
        ctx = context(options={'visibility': 'public', 'youtube_config': {'youtube': {
            'thumbnail': True, 'playlist_default': 'playlist', 'auto_comment': {'enabled': True}}}})
        result = self.adapter.submit(ctx, self.prepare(ctx), object())
        intents = result.evidence['followup_intents']
        self.assertEqual([item['action'] for item in intents], ['thumbnail', 'playlist', 'comment'])
        self.assertEqual(result.evidence['followup_completion'], 'pending')
        self.assertTrue(all(item['required'] and item['state'] == 'not_started' for item in intents))
        self.assertEqual([name for name, _ in self.google['dept.youtube'].calls],
                         ['channels.list', 'videos.insert', 'next_chunk'])

    def test_resolver_reads_exact_existing_encrypted_key_and_preserves_scopes(self):
        keys, parsed = [], []
        credential = SimpleNamespace(valid=True)
        class Credentials:
            @staticmethod
            def from_authorized_user_info(info): parsed.append(info); return credential
        secrets = {'YOUTUBE_TOKEN_DEPT': '{"token":"dept-fixture"}',
                   'YOUTUBE_TOKEN_GEOAI': '{"token":"personal-fixture"}'}
        class Secrets:
            @staticmethod
            def read(): return secrets
        with patch.dict(sys.modules, {
            'common.shared.secret_env': Secrets,
            'google.oauth2.credentials': SimpleNamespace(Credentials=Credentials),
            'google.auth.transport.requests': SimpleNamespace(Request=lambda: None)}):
            self.assertIs(self.runtime.resolve_youtube_credentials('dept.youtube.credential',
                account_id='dept', platform='youtube', scope='publication'), credential)
            self.assertEqual(parsed, [{'token': 'dept-fixture'}])
            secrets.pop('YOUTUBE_TOKEN_DEPT')
            with self.assertRaises(ContractError):
                self.runtime.resolve_youtube_credentials('dept.youtube.credential', account_id='dept', platform='youtube', scope='read')
        self.assertEqual(len(parsed), 1)

    def test_private_and_unlisted_requests_and_observations_are_separate(self):
        for privacy in ('private', 'unlisted', 'public'):
            with self.subTest(privacy=privacy):
                ctx = context(options={'visibility': privacy})
                payload = self.prepare(ctx)
                self.assertEqual(payload['body']['status']['privacyStatus'], privacy)
                self.assertNotIn('publishAt', payload['body']['status'])
                self.google['dept.youtube'].response['status'] = dict(privacyStatus=privacy, uploadStatus='uploaded')
                result = self.adapter.submit(ctx, payload, object())
                self.assertEqual(result.evidence['visibility'], privacy)
                self.assertEqual(result.outcome, 'submitted')
                self.assertFalse(result.evidence['schedule_confirmed'])

    def test_managed_ineligible_job_does_not_register_even_when_enabled(self):
        from dataclasses import replace
        jobs = {key: dict(job, managed_eligible=False) for key, job in self.reg.jobs.items()}
        self.assertEqual(dict(self.runtime.build_youtube_catalog(replace(self.reg, jobs=jobs)).executors), {})

    def test_processing_failure_is_not_verification_pending_or_success(self):
        self.google['dept.youtube'].videos[0]['status']['uploadStatus'] = 'rejected'
        result = self.adapter.verify(context(), 'remote', snapshot())
        self.assertEqual(result.outcome, 'failed')
        self.assertEqual(result.evidence['reason'], 'remote_processing_failed')

    def test_enabled_launcher_without_registered_venv_is_environment_unavailable(self):
        with patch('common.operations.registry.load_registry', return_value=self.reg), \
             patch('pathlib.Path.is_file', return_value=False):
            with self.assertRaisesRegex(ContractError, 'environment_unavailable'):
                self.module.bridge_bootstrap()

    def test_schedule_expiring_during_media_preparation_is_not_inserted(self):
        current = [NOW]
        def media(asset, prepared):
            current[0] = NOW + timedelta(seconds=2)
            return 'media'
        service = self.services_module.GoogleYoutubeServices(Client(self.google['dept.youtube']),
                    media_factory=media, clock=lambda: current[0])
        ctx = context(schedule_condition={'kind': 'fixed', 'at': (NOW + timedelta(seconds=1)).isoformat()})
        result = service.submit(self.prepare(ctx), dict(target_id='UC-dept'))
        self.assertEqual(result['outcome'], 'failed')
        self.assertEqual(sum(name == 'videos.insert' for name, _ in self.google['dept.youtube'].calls), 0)

    def test_malformed_remote_schedule_preserves_id_without_scheduled_claim(self):
        self.google['dept.youtube'].response['status'] = dict(privacyStatus='private', publishAt='invalid-date')
        result = self.adapter.submit(context(), self.prepare(), object())
        self.assertEqual(result.remote_id, 'remote')
        self.assertEqual(result.outcome, 'submitted')
        self.assertEqual(result.evidence['visibility'], 'private')
        self.assertFalse(result.evidence['schedule_confirmed'])

    def test_registered_project_environment_never_falls_back_to_server_python(self):
        from common.operations.bootstrap_config import default_bootstrap_config
        source_root=default_bootstrap_config().source_root
        catalog = self.runtime.build_youtube_catalog(self.reg)
        for spec in catalog.executors.values():
            self.assertEqual(spec.cwd, source_root / 'dept/youtube-shorts-auto')
            self.assertEqual(spec.interpreter, str(source_root / 'dept/youtube-shorts-auto/.venv/bin/python'))

    def test_remote_id_survives_malformed_status_without_further_io(self):
        self.google['dept.youtube'].response = {'id': 'remote', 'status': 'malformed'}
        result = self.adapter.submit(context(), self.prepare(), object())
        self.assertEqual(result.remote_id, 'remote')
        self.assertEqual(result.outcome, 'submitted')
        self.assertEqual([name for name, _ in self.google['dept.youtube'].calls],
                         ['channels.list', 'videos.insert', 'next_chunk'])

    def test_google_media_transport_reads_only_sealed_asset_and_checks_bytes(self):
        import hashlib
        fake = self.google['dept.youtube']
        calls, credentials = [], object()
        def build(api, version, **kw):
            self.assertEqual((api, version), ('youtube', 'v3'))
            self.assertIs(kw['credentials'], credentials)
            self.assertFalse(kw['cache_discovery'])
            return Client(fake)
        def upload(stream, **kw):
            calls.append((stream.read(), kw)); return 'resumable-media'
        raw = b'video'
        prepared = self.prepare()
        prepared['asset']['sha256'] = hashlib.sha256(raw).hexdigest()
        def loader(content_id, revision, asset_id):
            self.assertEqual((content_id, revision, asset_id), ('content', 1, 'asset-video'))
            return dict(prepared['asset']), raw
        with patch.dict(sys.modules, {
            'googleapiclient': SimpleNamespace(),
            'googleapiclient.discovery': SimpleNamespace(build=build),
            'googleapiclient.http': SimpleNamespace(MediaIoBaseUpload=upload)}):
            service = self.services_module.create_youtube_services('dept.youtube', credentials, media_loader=loader)
            result = service.submit(prepared, dict(target_id='UC-dept'))
            self.assertEqual(result['remote_id'], 'remote')
            self.assertEqual(calls, [(b'video', dict(mimetype='video/mp4', chunksize=-1, resumable=True))])
            prepared['asset']['sha256'] = '0' * 64
            blocked = service.submit(prepared, dict(target_id='UC-dept'))
        self.assertEqual(blocked['outcome'], 'failed')
        self.assertEqual(sum(n == 'videos.insert' for n, _ in fake.calls), 1)

    def test_import_and_prepare_do_not_load_legacy_tokens_or_processes(self):
        environment, paths = dict(os.environ), list(sys.path)
        with patch('builtins.open', side_effect=AssertionError('open forbidden')), \
             patch('socket.socket', side_effect=AssertionError('socket forbidden')), \
             patch('subprocess.Popen', side_effect=AssertionError('process forbidden')), \
             patch('os.makedirs', side_effect=AssertionError('mkdir forbidden')):
            for name in ('youtube_payloads', 'youtube_services', 'youtube_runtime', 'youtube'):
                # Fresh imports must not replace canonical classes used by other tests.
                existing=importlib.import_module('common.publishers.'+name)
                alias='common.publishers._import_check_'+name
                spec=importlib.util.spec_from_file_location(alias,existing.__file__)
                fresh=importlib.util.module_from_spec(spec)
                with patch.dict(sys.modules,{alias:fresh}):spec.loader.exec_module(fresh)
            self.prepare()
        self.assertEqual(environment, dict(os.environ)); self.assertEqual(paths, sys.path)
        self.assertNotIn('youtube_upload', sys.modules)
        self.assertNotIn('geoai_short_post', sys.modules)

    def test_actual_child_uses_trusted_launcher_root_with_legacy_common_bomb(self):
        from dataclasses import replace
        from common.operations.execution_catalog import ExecutionCatalog
        from common.publishers.legacy_bridge import LegacyBridge
        from common.shared.axlock import AxLock, LockPaths
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            launcher_root, cwd = root / 'launchers', root / 'legacy'
            launcher_root.mkdir(); cwd.mkdir()
            bomb = root / 'legacy-imported'
            (cwd / 'common.py').write_text('from pathlib import Path\nPath(' + repr(str(bomb)) + ').write_text("bad")\nraise RuntimeError("legacy common imported")\n')
            specs = self.runtime.build_youtube_catalog(self.reg, interpreter=sys.executable, cwd=cwd).executors
            catalog = ExecutionCatalog({key: replace(spec, module='fixture_youtube_child') for key, spec in specs.items()})
            code = """from pathlib import Path
import sys
from types import SimpleNamespace
from dataclasses import replace
from tests.publishers.test_youtube import registry, NOW, FakeGoogle, Client
from common.operations.execution_catalog import ExecutionCatalog
from common.publishers.youtube_runtime import build_youtube_catalog, build_youtube_host
from common.publishers.youtube_services import GoogleYoutubeServices
from common.publishers.bridge_host import main
from common.shared.axlock import AxLock, LockPaths
LAUNCHERS=Path(LAUNCHER_ROOT_LITERAL)
CWD=Path(CWD_LITERAL)
SOURCE=Path(SOURCE_LITERAL)
def bootstrap():
    reg=registry()
    specs=build_youtube_catalog(reg,interpreter=sys.executable,cwd=CWD).executors
    catalog=ExecutionCatalog({key:replace(spec,module='fixture_youtube_child') for key,spec in specs.items()})
    store=SimpleNamespace(locks=None,get_run=lambda run: {'occurrence':dict(job_id='job-dept.youtube',phase='submit',mode='live')})
    locks=AxLock(LockPaths.from_root(SOURCE),process_probe=lambda _:False)
    def resolver(reference,*,account_id,platform,scope):
        assert (reference,account_id,platform,scope)==('dept.youtube.credential','dept','youtube','read')
        return 'fixture-credential'
    def factory(key,credential):
        assert (key,credential)==('dept.youtube','fixture-credential')
        return GoogleYoutubeServices(Client(FakeGoogle('dept')),media_factory=lambda *args:None,clock=lambda:NOW)
    return build_youtube_host(reg,catalog,store,locks,services_factory=factory,
        credential_resolver=resolver,clock=lambda:NOW,module_root=LAUNCHERS)
if __name__=='__main__':
    raise SystemExit(main(bootstrap=bootstrap,bootstrap_module=__spec__.name))
"""
            code = code.replace('LAUNCHER_ROOT_LITERAL', repr(str(launcher_root))).replace('CWD_LITERAL', repr(str(cwd))).replace('SOURCE_LITERAL', repr(str(root / 'source')))
            (launcher_root / 'fixture_youtube_child.py').write_text(code)
            locks = AxLock(LockPaths.from_root(root / 'source'), process_probe=lambda _: False)
            store = SimpleNamespace(get_run=lambda run: {'occurrence': dict(job_id='job-dept.youtube', phase='submit', mode='live')})
            bridge = LegacyBridge(self.reg, catalog, store, locks, module_root=launcher_root)
            ctx = context(owner_account_id='dept', run_id='fixture-run')
            with locks.hold(['profile:youtube-dept'], job='youtube-child', wait=.1):
                observed = self.module.build_adapter(self.reg, bridge).inspect_target(ctx)
            self.assertEqual(observed['target_id'], 'UC-dept')
            self.assertTrue(observed['authenticated'])
            self.assertFalse(bomb.exists())

    def test_both_actual_legacy_managed_leaves_share_real_service(self):
        service = self.services_module.GoogleYoutubeServices(Client(self.google['dept.youtube']),
            media_factory=lambda asset, prepared: ('sealed', asset['id']), clock=lambda: NOW)
        target = dict(target_id='UC-dept', platform='youtube', expected_login_subject=None)
        for relative in ('dept/youtube-shorts-auto/youtube_upload.py', 'dept/youtube-shorts-auto/geoai_short_post.py'):
            leaf = isolated_functions(relative, ('managed_upload', 'managed_read_target', 'managed_read_video'))
            self.assertTrue(leaf.managed_read_target(target, service)['authenticated'])
            self.assertEqual(leaf.managed_upload(self.prepare(), target, service)['remote_id'], 'remote')
            self.assertEqual(leaf.managed_read_video(target, 'remote', service)['id'], 'remote')
        self.assertEqual(sum(n == 'videos.insert' for n, _ in self.google['dept.youtube'].calls), 2)
        self.assertEqual(sum(n == 'next_chunk' for n, _ in self.google['dept.youtube'].calls), 2)

    def test_legacy_upload_keeps_existing_followups(self):
        events = []
        fake = self.google['dept.youtube']
        cfg = {'youtube': {'privacy': 'public', 'thumbnail': True, 'playlist_default': 'playlist'}}
        scope = dict(load_config=lambda: cfg, os=os, _build_title=lambda data, cfg: '제목',
                     _build_description=lambda data, cfg: '설명', _detected_keywords=lambda data: [],
                     DEFAULT_SEO_KEYWORDS=[], _preflight=lambda *args: None, _creds=lambda path: object(),
                     build=lambda *args, **kw: Client(fake), MediaFileUpload=lambda *a, **kw: 'media',
                     log=lambda msg: None, pick_playlist=lambda *a: 'playlist',
                     put_in_playlist=lambda *a: events.append('playlist'), TOKEN_PATH='/fixture/token.json', json=__import__('json'))
        leaf = isolated_functions('dept/youtube-shorts-auto/youtube_upload.py', ('upload',), scope)
        with patch('os.path.exists', return_value=True), patch.dict(sys.modules, {
            'make_thumbnail': SimpleNamespace(make_thumbnail=lambda *a, **kw: 'thumbnail'),
            'tiktok_queue': SimpleNamespace(add=lambda *a, **kw: events.append('tiktok'))}):
            result = leaf.upload({'video': 'fixture.mp4', 'description': '설명', 'title': '제목'}, dry_run=False)
        self.assertEqual(result['video_id'], 'remote')
        self.assertEqual(events, ['playlist', 'tiktok'])
        self.assertEqual(sum(n == 'thumbnails.set' for n, _ in fake.calls), 1)


if __name__ == '__main__': unittest.main()
