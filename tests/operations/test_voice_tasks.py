import unittest
import tempfile
from unittest.mock import patch

class _MonkeyPatch:

    def __init__(self, owner):
        self.owner = owner

    def setattr(self, target, name, value):
        item = patch.object(target, name, value)
        item.start()
        self.owner.addCleanup(item.stop)
'voice_tasks 시험. 실제 임시 ContentStore + 가짜 client/probe만 쓴다(네트워크/음성/프로세스 없음).'
import io
import json
from pathlib import Path
import sqlite3
import threading
import time
import wave
from common.operations.content_store import ContentStore
from common.operations.models import ContractError
from common.operations.voice_tasks import VoiceTaskService, VoiceTaskStore, VOICE_LABEL
PROFILE = 'profile-secret-7731'
SCRIPT = '안녕하세요. 재난안전 숏츠 대본입니다.'
PUBLIC_KEYS = {'task_id', 'state', 'reason_code', 'content_id', 'input_revision', 'output_revision', 'asset_id', 'seconds', 'review_status', 'voice_label', 'generation_id'}

def make_wav(frames=2400):
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(24000)
        out.writeframes(b'\x00\x00' * frames)
    return buffer.getvalue()

class FakeClient:

    def __init__(self):
        self.is_ready = True
        self.generate_calls, self.wait_calls, self.audio_calls, self.ready_calls = ([], [], [], 0)
        self.generate_error = None
        self.generate_result = {'id': 'gen-1', 'status': 'pending'}
        self.wait_error = None
        self.wait_status = 'completed'
        self.wav = make_wav()
        self.delay = 0.0
        self._lock = threading.Lock()

    def ready(self):
        self.ready_calls += 1
        return self.is_ready

    def generate(self, **body):
        with self._lock:
            self.generate_calls.append(body)
        time.sleep(self.delay)
        if self.generate_error is not None:
            raise self.generate_error
        return dict(self.generate_result)

    def wait_completed(self, generation_id):
        self.wait_calls.append(generation_id)
        if self.wait_error is not None:
            raise self.wait_error
        return {'id': generation_id, 'status': self.wait_status}

    def audio(self, generation_id):
        self.audio_calls.append(generation_id)
        return self.wav

class FakeProbe:

    def __init__(self, seconds=3.5):
        self.seconds, self.paths = (seconds, [])

    def __call__(self, path):
        assert Path(path).read_bytes()[:4] == b'RIFF'
        self.paths.append(Path(path))
        return {'seconds': self.seconds, 'width': None, 'height': None, 'has_audio': True}

class Env:

    def __init__(self, tmp_path, enabled=True, owner='personal'):
        self.tmp = tmp_path
        self.content = ContentStore(tmp_path / 'content')
        self.content.initialize()
        self.item = self.content.create(owner, {'title': '숏츠', 'kind': 'short', 'original': '원본 대본', 'variants': [], 'sources': []})
        self.store = VoiceTaskStore(tmp_path / 'voice')
        self.client, self.probe = (FakeClient(), FakeProbe())
        self.enabled = enabled
        self.store.initialize()
        self.service = self.make_service()

    def make_service(self, **override):
        options = dict(profile_id=PROFILE, enabled=self.enabled, probe=self.probe)
        options.update(override)
        return VoiceTaskService(self.store, self.content, self.client, **options)

    @property
    def cid(self):
        return self.item['id']

    def create(self, **kw):
        return self.service.create(self.cid, kw.pop('revision', 1), kw.pop('script', SCRIPT), **kw)

    def audio_assets(self, revision=None):
        return [a for a in self.content.get(self.cid, revision)['assets'] if a['media_type'] == 'audio/wav']

class VoiceTaskTests(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp_path = Path(tmp.name)

    def test_disabled_service_is_inert(self):
        tmp_path = self.tmp_path
        env = Env(tmp_path, enabled=False)
        voice_root = tmp_path / 'untouched'
        inert = VoiceTaskService(VoiceTaskStore(voice_root), env.content, env.client, profile_id=PROFILE)
        for call in (lambda: inert.create(env.cid, 1, SCRIPT), lambda: inert.resume('00000000-0000-4000-8000-000000000000'), lambda: env.service.create(env.cid, 1, SCRIPT)):
            with self.assertRaises(ContractError) as caught:
                call()
            assert caught.exception.code == 'voicebox_disabled'
        assert not voice_root.exists()
        assert env.client.ready_calls == 0 and env.client.generate_calls == [] and (env.client.wait_calls == [])
        assert env.store.list_for_content(env.cid) == []

    def test_expected_revision_mismatch_rejected_before_generation(self):
        env = Env(self.tmp_path / 'fixture')
        env.content.update(env.cid, 1, {'title': '숏츠', 'kind': 'short', 'original': '수정본'})
        with self.assertRaises(ContractError) as caught:
            env.create(revision=1)
        assert caught.exception.code == 'content_revision_conflict'
        for bad in ((env.cid, 0, SCRIPT), (env.cid, 2, ''), (env.cid, 2, 'a\x00b'), (env.cid, 2, 'x' * 2001), (env.cid, True, SCRIPT)):
            with self.assertRaises(ContractError):
                env.service.create(*bad)
        for seed in (-1, 2147483648, 1.5, True):
            with self.assertRaises(ContractError):
                env.service.create(env.cid, 2, SCRIPT, seed)
        assert env.client.generate_calls == [] and env.store.list_for_content(env.cid) == []

    def test_concurrent_same_intent_posts_once_and_returns_same_task(self):
        env = Env(self.tmp_path / 'fixture')
        env.client.delay = 0.15
        results, errors = ([], [])

        def run():
            try:
                results.append(env.create())
            except ContractError as exc:
                errors.append(exc.code)
        threads = [threading.Thread(target=run) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert len(env.client.generate_calls) == 1
        assert len({r['task_id'] for r in results}) == 1
        assert len(env.store.list_for_content(env.cid)) == 1

    def test_generate_body_is_exact_and_other_intent_blocked_while_started_or_unknown(self):
        env = Env(self.tmp_path / 'fixture')
        env.client.generate_error = TimeoutError('read timed out at /secret/path')
        first = env.create()
        assert env.client.generate_calls == [dict(profile_id=PROFILE, text=SCRIPT, language='ko', engine='qwen', model_size='0.6B', seed=14005, normalize=True, max_chunk_chars=250)]
        assert first['state'] == 'unknown' and first['generation_id'] is None
        with self.assertRaises(ContractError) as caught:
            env.create(seed=7)
        assert caught.exception.code == 'voice_task_conflict'
        with self.assertRaises(ContractError):
            env.create(script='다른 대본')
        assert len(env.client.generate_calls) == 1

    def test_post_timeout_unknown_never_reposts(self):
        env = Env(self.tmp_path / 'fixture')
        env.client.generate_error = TimeoutError('timeout')
        task = env.create()
        again = env.create()
        resumed = env.service.resume(task['task_id'])
        other_service = env.make_service()
        resumed_again = other_service.resume(task['task_id'])
        assert again['task_id'] == task['task_id'] == resumed['task_id']
        assert resumed['state'] == resumed_again['state'] == 'unknown'
        assert len(env.client.generate_calls) == 1 and env.client.wait_calls == [] and (env.client.audio_calls == [])
        env.client.generate_error = None
        env.client.generate_result = {'status': 'pending'}
        with self.assertRaises(ContractError):
            env.create(seed=1)
        assert len(env.client.generate_calls) == 1

    def test_malformed_post_response_becomes_unknown(self):
        env = Env(self.tmp_path / 'fixture')
        env.client.generate_result = {'id': '../escape', 'status': 'pending'}
        assert env.create()['state'] == 'unknown'

    def test_known_id_resume_uses_get_only_and_survives_client_errors(self):
        env = Env(self.tmp_path / 'fixture')
        task = env.create()
        assert task['state'] == 'pending' and task['generation_id'] == 'gen-1'
        env.client.wait_error = ConnectionError('boom /private/tmp/x')
        still = env.service.resume(task['task_id'])
        assert still['state'] == 'pending' and still['reason_code'] is None
        env.client.wait_error = None
        env.client.wait_status = 'generating'
        assert env.service.resume(task['task_id'])['state'] == 'pending'
        assert len(env.client.generate_calls) == 1 and env.client.audio_calls == []
        env.client.wait_status = 'completed'
        assert env.service.resume(task['task_id'])['state'] == 'completed'
        assert len(env.client.generate_calls) == 1

    def test_completed_registers_asset_with_cas_and_is_reused_without_native(self):
        env = Env(self.tmp_path / 'fixture')
        task = env.create()
        done = env.service.resume(task['task_id'])
        assert done['state'] == 'completed' and done['input_revision'] == 1 and (done['output_revision'] == 2)
        assert done['review_status'] == 'not_checked' and done['voice_label'] == VOICE_LABEL == 'AI 합성 음성(본인 목소리 복제)'
        assert done['seconds'] == 3.5
        head = env.content.get(env.cid)
        assert head['revision'] == 2 and len(env.audio_assets()) == 1
        asset = env.audio_assets()[0]
        assert asset['filename'] == f"voicebox-{task['task_id']}.wav" and asset['id'] == done['asset_id']
        assert env.content.read_asset(env.cid, 2, asset['id'])[1] == env.client.wav
        assert (env.tmp / 'voice' / 'voice-artifacts' / task['task_id'] / 'voice.wav').read_bytes() == env.client.wav
        assert not list((env.tmp / 'voice' / 'voice-artifacts' / task['task_id']).glob('*.tmp-*'))
        assert env.content.get(env.cid)['reviews'] == []
        env.client.is_ready = False
        assert env.create()['state'] == 'completed'
        assert env.service.resume(task['task_id'])['state'] == 'completed'
        assert len(env.client.generate_calls) == 1 and len(env.audio_assets()) == 1

    def test_content_change_preserves_audio_and_never_overwrites(self):
        env = Env(self.tmp_path / 'fixture')
        task = env.create()
        env.content.update(env.cid, 1, {'title': '숏츠', 'kind': 'short', 'original': '작성자가 고친 대본'})
        changed = env.service.resume(task['task_id'])
        assert changed['state'] == 'content_changed' and changed['reason_code'] == 'content_changed'
        assert (env.tmp / 'voice' / 'voice-artifacts' / task['task_id'] / 'voice.wav').exists()
        assert env.content.get(env.cid)['revision'] == 2 and env.audio_assets() == []
        assert env.service.resume(task['task_id'])['state'] == 'content_changed'
        assert len(env.client.generate_calls) == 1

    def test_invalid_wav_or_overlong_audio_fails_with_fixed_reason_1(self):
        env = Env(self.tmp_path / 'fixture')
        wav, seconds, reason = (b'not a wav file at all, but long enough to pass the size floor......', 3.0, 'voicebox_audio_invalid')
        env.client.wav, env.probe.seconds = (wav, seconds)
        task = env.create()
        failed = env.service.resume(task['task_id'])
        assert failed['state'] == 'failed' and failed['reason_code'] == reason
        assert env.audio_assets() == [] and env.content.get(env.cid)['revision'] == 1
        assert not (env.tmp / 'voice' / 'voice-artifacts' / task['task_id'] / 'voice.wav').exists()

    def test_invalid_wav_or_overlong_audio_fails_with_fixed_reason_2(self):
        env = Env(self.tmp_path / 'fixture')
        wav, seconds, reason = (make_wav(), 20.01, 'voicebox_duration_invalid')
        env.client.wav, env.probe.seconds = (wav, seconds)
        task = env.create()
        failed = env.service.resume(task['task_id'])
        assert failed['state'] == 'failed' and failed['reason_code'] == reason
        assert env.audio_assets() == [] and env.content.get(env.cid)['revision'] == 1
        assert not (env.tmp / 'voice' / 'voice-artifacts' / task['task_id'] / 'voice.wav').exists()

    def test_invalid_wav_or_overlong_audio_fails_with_fixed_reason_3(self):
        env = Env(self.tmp_path / 'fixture')
        wav, seconds, reason = (make_wav(), float('nan'), 'voicebox_duration_invalid')
        env.client.wav, env.probe.seconds = (wav, seconds)
        task = env.create()
        failed = env.service.resume(task['task_id'])
        assert failed['state'] == 'failed' and failed['reason_code'] == reason
        assert env.audio_assets() == [] and env.content.get(env.cid)['revision'] == 1
        assert not (env.tmp / 'voice' / 'voice-artifacts' / task['task_id'] / 'voice.wav').exists()

    def test_invalid_wav_or_overlong_audio_fails_with_fixed_reason_4(self):
        env = Env(self.tmp_path / 'fixture')
        wav, seconds, reason = (make_wav(), 0, 'voicebox_duration_invalid')
        env.client.wav, env.probe.seconds = (wav, seconds)
        task = env.create()
        failed = env.service.resume(task['task_id'])
        assert failed['state'] == 'failed' and failed['reason_code'] == reason
        assert env.audio_assets() == [] and env.content.get(env.cid)['revision'] == 1
        assert not (env.tmp / 'voice' / 'voice-artifacts' / task['task_id'] / 'voice.wav').exists()

    def test_twenty_seconds_exactly_is_accepted(self):
        env = Env(self.tmp_path / 'fixture')
        env.probe.seconds = 20
        assert env.service.resume(env.create()['task_id'])['state'] == 'completed'

    def test_crash_after_ingest_before_finish_recovers_by_read_only(self):
        env = Env(self.tmp_path / 'fixture')
        monkeypatch = _MonkeyPatch(self)
        task = env.create()
        real = env.store.transition
        crashed = []

        def flaky(task_id, from_states, **fields):
            if fields.get('state') == 'completed' and (not crashed):
                crashed.append(True)
                raise ContractError('voice_storage_error')
            return real(task_id, from_states, **fields)
        monkeypatch.setattr(env.store, 'transition', flaky)
        with self.assertRaises(ContractError):
            env.service.resume(task['task_id'])
        assert env.store.get(task['task_id'])['state'] == 'audio_ready'
        assert env.content.get(env.cid)['revision'] == 2 and len(env.audio_assets()) == 1
        recovered = env.make_service().resume(task['task_id'])
        assert recovered['state'] == 'completed' and recovered['output_revision'] == 2
        assert len(env.audio_assets()) == 1 and env.content.get(env.cid)['revision'] == 2
        assert len(env.client.generate_calls) == 1 and env.client.audio_calls == ['gen-1']

    def test_recovery_fails_closed_when_head_is_not_exact_ingest_result(self):
        env = Env(self.tmp_path / 'fixture')
        monkeypatch = _MonkeyPatch(self)
        task = env.create()
        real = env.store.transition

        def crash(task_id, from_states, **fields):
            if fields.get('state') == 'completed':
                raise ContractError('voice_storage_error')
            return real(task_id, from_states, **fields)
        monkeypatch.setattr(env.store, 'transition', crash)
        with self.assertRaises(ContractError):
            env.service.resume(task['task_id'])
        monkeypatch.setattr(env.store, 'transition', real)
        env.content.update(env.cid, 2, {'title': '숏츠', 'kind': 'short', 'original': '원본 대본'})
        assert env.service.resume(task['task_id'])['state'] == 'content_changed'
        assert len(env.audio_assets()) == 1 and len(env.client.generate_calls) == 1

    def test_account_binding_and_task_isolation(self):
        tmp_path = self.tmp_path
        env = Env(tmp_path, owner='dept')
        other = env.content.create('personal', {'title': '개인', 'kind': 'short', 'original': '원본 대본'})
        mine, theirs = (env.create(), env.service.create(other['id'], 1, SCRIPT))
        assert mine['task_id'] != theirs['task_id'] and len(env.client.generate_calls) == 2
        assert [t['task_id'] for t in env.store.list_for_content(env.cid)] == [mine['task_id']]
        row = env.store.get_row(mine['task_id'])
        assert row['owner_account_id'] == 'dept' and row['manifest_hash'] == env.item['manifest_hash']
        assert env.store.list_for_content(env.cid, 2) == [] and len(env.store.list_for_content(env.cid, 1)) == 1
        with self.assertRaises(ContractError):
            env.service.resume('not-a-uuid')
        with self.assertRaises(ContractError) as caught:
            env.service.resume('00000000-0000-4000-8000-000000000000')
        assert caught.exception.code == 'task_not_found'

    def test_public_projection_and_failures_are_redacted(self):
        env = Env(self.tmp_path / 'fixture')
        env.client.wav = b'x' * 64
        task = env.create()
        failed = env.service.resume(task['task_id'])
        done_env_dump = json.dumps([task, failed, env.store.get(task['task_id']), env.store.list_for_content(env.cid)], ensure_ascii=False)
        for item in (task, failed, env.store.get(task['task_id'])):
            assert set(item) == PUBLIC_KEYS and item['review_status'] == 'not_checked' and (item['voice_label'] == VOICE_LABEL)
        for secret in (PROFILE, SCRIPT, str(env.tmp), 'voice.wav', 'voice-artifacts'):
            assert secret not in done_env_dump
        assert failed['reason_code'] == 'voicebox_audio_invalid'

    def test_store_rejects_symlink_root_foreign_db_and_leaves_other_files_untouched(self):
        tmp_path = self.tmp_path
        real = tmp_path / 'real'
        real.mkdir()
        link = tmp_path / 'link'
        link.symlink_to(real)
        with self.assertRaises(ContractError):
            VoiceTaskStore(link).initialize()
        assert list(real.iterdir()) == []
        foreign_root = tmp_path / 'foreign'
        foreign_root.mkdir()
        foreign = foreign_root / 'voice-tasks.sqlite3'
        conn = sqlite3.connect(foreign)
        conn.execute('CREATE TABLE other(x)')
        conn.commit()
        conn.close()
        before = foreign.read_bytes()
        with self.assertRaises(ContractError):
            VoiceTaskStore(foreign_root).initialize()
        assert foreign.read_bytes() == before
        garbage_root = tmp_path / 'garbage'
        garbage_root.mkdir()
        (garbage_root / 'voice-tasks.sqlite3').write_text('not sqlite')
        with self.assertRaises(ContractError):
            VoiceTaskStore(garbage_root).initialize()
        assert (garbage_root / 'voice-tasks.sqlite3').read_text() == 'not sqlite'
        victim = tmp_path / 'victim.sqlite3'
        victim.write_text('victim')
        link_db_root = tmp_path / 'linkdb'
        link_db_root.mkdir()
        (link_db_root / 'voice-tasks.sqlite3').symlink_to(victim)
        with self.assertRaises(ContractError):
            VoiceTaskStore(link_db_root).initialize()
        assert victim.read_text() == 'victim'

    def test_constructor_and_get_do_no_io_until_initialize(self):
        tmp_path = self.tmp_path
        store = VoiceTaskStore(tmp_path / 'never')
        assert store.get('00000000-0000-4000-8000-000000000000') is None and store.list_for_content('c') == []
        assert not (tmp_path / 'never').exists()
        store.initialize()
        assert (tmp_path / 'never' / 'voice-tasks.sqlite3').is_file()
        again = VoiceTaskStore(tmp_path / 'never')
        again.initialize()
