"""ID 없는 started/unknown 음성 작업의 명시적 복구 연결 시험.

임시 ContentStore/SQLite + 가짜 client/transport만 쓴다. 별도 Python 프로세스는 잠금 시험에만 사용한다.
Env/FakeClient/FakeProbe는 기존 test_voice_tasks 모듈을 별칭으로 재사용한다(중복 수집 없음).
"""
import json
from pathlib import Path
import sqlite3
import select
import subprocess
import sys
import tempfile
import unittest

from common.operations.models import ContractError
from common.operations.voice_tasks import VoiceTaskStore
from common.operations.voicebox_client import LocalVoiceboxClient
from tests.operations import test_voice_tasks as base
from tests.operations import test_voicebox_client as client_base

GEN = 'gen-recovered-1'
UNVERIFIABLE = 'voice_recovery_unverifiable'
CLIENT_UNVERIFIABLE = 'voicebox_recovery_unverifiable'


class RecoveryClient(base.FakeClient):
    """FakeClient + inspect_generation. 기본은 작업 입력과 정확히 일치하는 history 한 건."""

    def __init__(self):
        super().__init__()
        self.inspect_calls, self.overrides, self.drop = [], {}, ()
        self.inspect_error = self.raw = self.hook = None

    def inspect_generation(self, generation_id):
        self.inspect_calls.append(generation_id)
        if self.hook is not None:
            self.hook(len(self.inspect_calls))
        if self.inspect_error is not None:
            raise self.inspect_error
        if self.raw is not None:
            return self.raw
        result = dict(id=generation_id, status='running', profile_id=base.PROFILE, text=base.SCRIPT, seed=14005,
                      language='ko', engine='qwen', model_size='0.6B')
        result.update(self.overrides)
        for key in self.drop:
            result.pop(key, None)
        return result


def started_task(env, item=None, script=base.SCRIPT, seed=14005):
    """native POST 없이 started(ID 없음) 행만 만든다."""
    item = item or env.item
    snap = env.content.get(item['id'], 1)
    row, created = env.store.claim(owner_account_id=snap['owner_account_id'], content_id=item['id'], input_revision=1,
                                   manifest_hash=snap['manifest_hash'], script=script, seed=seed,
                                   intent_hash=env.service._intent(snap, script, seed))
    assert created
    return row


class RecoveryTests(unittest.TestCase):
    def env(self, owner='personal', enabled=True):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = base.Env(Path(tmp.name), owner=owner, enabled=enabled)
        env.client = RecoveryClient()
        env.service = env.make_service()
        return env

    def unknown_task(self, env):
        env.client.generate_error = TimeoutError('timeout /secret')
        task = env.create()
        env.client.generate_error = None
        assert task['state'] == 'unknown' and task['generation_id'] is None
        return task['task_id']

    def code(self, call, *args):
        with self.assertRaises(ContractError) as caught:
            call(*args)
        return caught.exception.code

    # --- 미리보기 / 확정 ---------------------------------------------------
    def test_inspect_is_read_only_with_zero_post_for_started_and_unknown(self):
        for kind in ('unknown', 'started'):
            env = self.env()
            task_id = self.unknown_task(env) if kind == 'unknown' else started_task(env)['task_id']
            posts, before = len(env.client.generate_calls), env.store.get_row(task_id)
            env.client.overrides = {'text': '  ' + base.SCRIPT + '\n'}  # strip 비교
            preview = env.service.inspect_recovery(task_id, GEN)
            self.assertEqual(set(preview), {'task_id', 'generation_id', 'recovery_fingerprint', 'task_state',
                                            'can_confirm', 'review_status'})
            self.assertEqual((preview['task_id'], preview['generation_id'], preview['task_state']), (task_id, GEN, kind))
            self.assertIs(preview['can_confirm'], True)
            self.assertEqual(preview['review_status'], 'not_checked')
            self.assertRegex(preview['recovery_fingerprint'], r'^[0-9a-f]{64}$')
            self.assertEqual(env.client.inspect_calls, [GEN])
            self.assertEqual(len(env.client.generate_calls), posts)
            self.assertEqual(env.store.get_row(task_id), before)  # DB 전이 없음
            dump = json.dumps(preview, ensure_ascii=False)
            for secret in (base.PROFILE, base.SCRIPT, str(env.tmp)):
                self.assertNotIn(secret, dump)

    def test_confirm_links_pending_with_get_only_and_resume_is_separate(self):
        env = self.env()
        task_id = self.unknown_task(env)
        posts = len(env.client.generate_calls)
        before = env.store.get_row(task_id)
        fingerprint = env.service.inspect_recovery(task_id, GEN)['recovery_fingerprint']
        linked = env.service.confirm_recovery(task_id, GEN, fingerprint)
        self.assertEqual(set(linked), base.PUBLIC_KEYS)
        self.assertEqual((linked['state'], linked['generation_id'], linked['reason_code']), ('pending', GEN, None))
        row = env.store.get_row(task_id)
        self.assertEqual(row['version'], before['version'] + 1)
        self.assertEqual(env.client.inspect_calls, [GEN, GEN])  # 미리보기 + 확정 시 재조회
        self.assertEqual((len(env.client.generate_calls), env.client.audio_calls, env.client.wait_calls),
                         (posts, [], []))  # 다운로드/자동 resume 없음
        self.assertEqual(env.audio_assets(), [])
        done = env.service.resume(task_id)  # 다음 요청이 별도로 resume한다
        self.assertEqual(done['state'], 'completed')
        self.assertEqual((env.client.wait_calls, env.client.audio_calls, len(env.client.generate_calls)),
                         ([GEN], [GEN], posts))

    def test_confirm_replay_same_id_is_read_only_and_other_id_rejected(self):
        env = self.env()
        task_id = self.unknown_task(env)
        fingerprint = env.service.inspect_recovery(task_id, GEN)['recovery_fingerprint']
        first = env.service.confirm_recovery(task_id, GEN, fingerprint)
        calls, row = len(env.client.inspect_calls), env.store.get_row(task_id)
        for _ in range(2):
            self.assertEqual(env.service.confirm_recovery(task_id, GEN, fingerprint), first)
        self.assertEqual((len(env.client.inspect_calls), env.store.get_row(task_id)), (calls, row))
        self.assertEqual(env.service.confirm_recovery(task_id, GEN, 'f' * 64), first)  # 형식만 맞으면 replay
        self.assertEqual(self.code(env.service.confirm_recovery, task_id, GEN, 'F' * 64), 'invalid_voice_request')
        self.assertEqual(self.code(env.service.confirm_recovery, task_id, 'gen-other', fingerprint),
                         'voice_recovery_conflict')
        self.assertEqual(env.service.resume(task_id)['state'], 'completed')
        completed = env.service.confirm_recovery(task_id, GEN, fingerprint)
        self.assertEqual((completed['state'], completed['generation_id']), ('completed', GEN))
        self.assertEqual(env.store.get_row(task_id)['state'], 'completed')

    # --- 거부 --------------------------------------------------------------
    def test_mismatching_candidates_are_rejected_and_row_is_untouched(self):
        env = self.env()
        task_id = self.unknown_task(env)
        before = env.store.get_row(task_id)
        cases = ({'text': '다른 대본입니다.'}, {'profile_id': 'profile-other'}, {'seed': 1}, {'language': 'en'},
                 {'engine': 'other'}, {'model_size': '1.7B'}, {'status': 'failed'}, {'status': 'cancelled'},
                 {'id': 'gen-another'})
        for overrides in cases:
            env.client.overrides = overrides
            self.assertEqual(self.code(env.service.inspect_recovery, task_id, GEN), 'voice_recovery_mismatch', overrides)
            self.assertEqual(self.code(env.service.confirm_recovery, task_id, GEN, 'a' * 64),
                             'voice_recovery_mismatch', overrides)
        for status in ('pending', 'queued', 'running', 'completed'):
            env.client.overrides = {'status': status}
            self.assertTrue(env.service.inspect_recovery(task_id, GEN)['can_confirm'])
        self.assertEqual(env.store.get_row(task_id), before)

    def test_missing_malformed_or_failing_candidates_are_unverifiable(self):
        env = self.env()
        task_id = self.unknown_task(env)
        before = env.store.get_row(task_id)
        for field in ('id', 'status', 'profile_id', 'text', 'seed', 'language', 'engine', 'model_size'):
            env.client.drop = (field,)
            self.assertEqual(self.code(env.service.inspect_recovery, task_id, GEN), UNVERIFIABLE, field)
        env.client.drop = ()
        full = dict(id=GEN, status='running', profile_id=base.PROFILE, text=base.SCRIPT, seed=14005, language='ko',
                    engine='qwen', model_size='0.6B')
        for raw in ([], 'text', {'id': GEN}, dict(full, seed=True), dict(full, extra='/private/path')):
            env.client.raw = raw
            self.assertEqual(self.code(env.service.inspect_recovery, task_id, GEN), UNVERIFIABLE, raw)
        env.client.raw = None
        env.client.inspect_error = ContractError('voicebox_unavailable')
        self.assertEqual(self.code(env.service.inspect_recovery, task_id, GEN), UNVERIFIABLE)
        env.client.inspect_error = RuntimeError('boom /secret/path')
        self.assertEqual(self.code(env.service.confirm_recovery, task_id, GEN, 'b' * 64), UNVERIFIABLE)
        no_inspect = self.env()
        no_inspect.client = base.FakeClient()  # inspect_generation 없음
        no_inspect.service = no_inspect.make_service()
        other_id = self.unknown_task(no_inspect)
        self.assertEqual(self.code(no_inspect.service.inspect_recovery, other_id, GEN), UNVERIFIABLE)
        self.assertEqual(env.store.get_row(task_id), before)

    def test_changed_row_or_content_head_blocks_confirm_and_preview(self):
        env = self.env()
        task_id = self.unknown_task(env)
        fingerprint = env.service.inspect_recovery(task_id, GEN)['recovery_fingerprint']
        env.store.transition(task_id, ('unknown',), state='unknown', reason_code='voicebox_request_unknown')  # version+1
        self.assertEqual(self.code(env.service.confirm_recovery, task_id, GEN, fingerprint), 'voice_recovery_conflict')
        fresh = env.service.inspect_recovery(task_id, GEN)['recovery_fingerprint']
        self.assertNotEqual(fresh, fingerprint)
        env.content.update(env.cid, 1, {'title': '숏츠', 'kind': 'short', 'original': '작성자가 고친 대본'})
        self.assertEqual(self.code(env.service.inspect_recovery, task_id, GEN), 'content_revision_conflict')
        self.assertEqual(self.code(env.service.confirm_recovery, task_id, GEN, fresh), 'content_revision_conflict')
        row = env.store.get_row(task_id)
        self.assertEqual((row['state'], row['generation_id']), ('unknown', None))

    def test_ineligible_states_and_bad_arguments_are_rejected_before_native(self):
        env = self.env()
        task_id = self.unknown_task(env)
        for bad in ('not-a-uuid', '', None, '00000000-0000-1000-8000-000000000000'):
            self.assertEqual(self.code(env.service.inspect_recovery, bad, GEN), 'invalid_voice_request')
        for bad in ('', '../x', 'a.b', 'a:b', 'a/b', 'x' * 129, 5, None, 'a\n'):
            self.assertEqual(self.code(env.service.inspect_recovery, task_id, bad), 'invalid_voice_request', bad)
        for bad in ('', 'abc', 'A' * 64, 'g' * 64, 'a' * 63, 'a' * 65, None, 5):
            self.assertEqual(self.code(env.service.confirm_recovery, task_id, GEN, bad), 'invalid_voice_request', bad)
        self.assertEqual(self.code(env.service.inspect_recovery, '00000000-0000-4000-8000-000000000000', GEN),
                         'task_not_found')
        self.assertEqual(env.client.inspect_calls, [])
        env.store.transition(task_id, ('unknown',), state='failed', reason_code='voicebox_generation_failed')
        self.assertEqual(self.code(env.service.inspect_recovery, task_id, GEN), 'voice_recovery_conflict')
        self.assertEqual(env.client.inspect_calls, [])

    def test_generation_owned_elsewhere_or_owner_tampered_is_rejected(self):
        env = self.env(owner='dept')
        other = env.content.create('personal', {'title': '개인', 'kind': 'short', 'original': '원본 대본'})
        env.client.generate_result = {'id': 'gen-owned', 'status': 'pending'}
        theirs = env.service.create(other['id'], 1, base.SCRIPT)
        self.assertEqual(theirs['generation_id'], 'gen-owned')
        mine = self.unknown_task(env)
        self.assertEqual(self.code(env.service.inspect_recovery, mine, 'gen-owned'), 'voice_recovery_conflict')
        self.assertEqual(self.code(env.service.confirm_recovery, mine, 'gen-owned', 'c' * 64), 'voice_recovery_conflict')
        self.assertEqual(env.client.inspect_calls, [])  # native 조회 전에 거부
        self.assertEqual(env.store.link_generation(mine, 'gen-owned', env.store.get_row(mine)['version']), 'conflict')
        self.assertEqual(env.store.get_row(mine)['generation_id'], None)
        # 같은 생성 ID를 확정 직전에 다른 작업이 먼저 가져가는 경합: transaction 내 유일성 재검사.
        racer = started_task(env, other_item_for(env))
        env.client.hook = lambda n: env.store.link_generation(racer['task_id'], GEN, racer['version']) if n == 2 else None
        fingerprint = env.service.inspect_recovery(mine, GEN)['recovery_fingerprint']
        self.assertEqual(self.code(env.service.confirm_recovery, mine, GEN, fingerprint), 'voice_recovery_conflict')
        self.assertEqual(env.store.get_row(racer['task_id'])['generation_id'], GEN)
        self.assertEqual(env.store.get_row(mine)['generation_id'], None)
        # 행의 owner가 콘텐츠 소유자와 달라지면(다른 계정 연결) 거부한다.
        conn = sqlite3.connect(env.tmp / 'voice' / 'voice-tasks.sqlite3')
        try:
            conn.execute('UPDATE voice_tasks SET owner_account_id=? WHERE task_id=?', ('personal', mine))
            conn.commit()
        finally:
            conn.close()
        env.client.hook = None
        self.assertEqual(self.code(env.service.inspect_recovery, mine, 'gen-fresh'), 'voice_recovery_mismatch')

    # --- 잠금 / 경합 -------------------------------------------------------
    def test_separate_process_lock_prevents_recovery_and_is_released_on_exit(self):
        env=self.env();task_id=self.unknown_task(env)
        script="""import sys
sys.path.insert(0,sys.argv[3])
from common.operations.voice_tasks import VoiceTaskStore
store=VoiceTaskStore(sys.argv[1]);store.initialize()
with store.task_lock(sys.argv[2]):
 print('locked',flush=True)
 sys.stdin.read(1)
"""
        child=subprocess.Popen([sys.executable,'-c',script,str(env.store.root),task_id,str(Path(__file__).resolve().parents[2])],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        def cleanup():
            if child.poll() is None:child.kill()
            child.communicate(timeout=5)
        self.addCleanup(cleanup)
        self.assertTrue(select.select([child.stdout],[],[],5)[0],'잠금 확인 기한 초과')
        ready=child.stdout.readline().strip()
        self.assertEqual(ready,'locked',child.stderr.read() if not ready else '')
        before=len(env.client.generate_calls)
        self.assertEqual(self.code(env.service.inspect_recovery,task_id,GEN),'voice_task_busy')
        self.assertEqual(env.client.inspect_calls,[])
        child.stdin.write('x');child.stdin.flush();self.assertEqual(child.wait(timeout=5),0)
        self.assertTrue(env.service.inspect_recovery(task_id,GEN)['can_confirm'])
        self.assertEqual(len(env.client.generate_calls),before)

    def test_task_lock_contention_blocks_preview_and_confirm_and_releases(self):
        env = self.env()
        task_id = self.unknown_task(env)
        fingerprint = env.service.inspect_recovery(task_id, GEN)['recovery_fingerprint']
        env.client.inspect_calls.clear()
        with env.store.task_lock(task_id):
            self.assertEqual(self.code(env.service.inspect_recovery, task_id, GEN), 'voice_task_busy')
            self.assertEqual(self.code(env.service.confirm_recovery, task_id, GEN, fingerprint), 'voice_task_busy')
            peer = VoiceTaskStore(env.tmp / 'voice')  # 다른 프로세스를 흉내 낸 별도 store/fd
            peer._initialized = True
            with self.assertRaises(ContractError) as caught:
                with peer.task_lock(task_id):
                    pass
            self.assertEqual(caught.exception.code, 'voice_task_busy')
        self.assertEqual(env.client.inspect_calls, [])
        self.assertEqual(env.store.get_row(task_id)['state'], 'unknown')
        lock = env.tmp / 'voice' / 'voice-artifacts' / task_id / '.task.lock'
        self.assertTrue(lock.is_file() and not lock.is_symlink())
        with env.store.task_lock(task_id):  # 예외 후에도 잠금이 풀려 있다
            pass
        self.assertEqual(env.service.confirm_recovery(task_id, GEN, fingerprint)['state'], 'pending')
        # 잠금 파일이 symlink면 열지 않고 대상은 건드리지 않는다.
        victim = env.tmp / 'victim.txt'
        victim.write_text('victim')
        lock.unlink()
        lock.symlink_to(victim)
        with self.assertRaises(ContractError) as caught:
            with env.store.task_lock(task_id):
                pass
        self.assertEqual(caught.exception.code, 'voice_storage_unsafe')
        self.assertEqual(victim.read_text(), 'victim')

    def test_post_rereads_fresh_row_after_lock_and_never_generates_when_recovered_or_busy(self):
        env = self.env()
        stale = started_task(env)
        task_id = stale['task_id']
        fingerprint = env.service.inspect_recovery(task_id, GEN)['recovery_fingerprint']
        env.service.confirm_recovery(task_id, GEN, fingerprint)  # claim과 lock 사이에 복구가 먼저 연결
        result = env.service._post(stale)  # 낡은 started 행을 들고 있는 create 경로
        self.assertEqual((result['state'], result['generation_id']), ('pending', GEN))
        self.assertEqual(env.client.generate_calls, [])
        # lock이 busy면 합성 없이 오류, 행은 started 그대로. 같은 intent 재호출도 합성하지 않는다.
        env2 = self.env()
        row = started_task(env2)
        with env2.store.task_lock(row['task_id']):
            self.assertEqual(self.code(env2.service._post, row), 'voice_task_busy')
        self.assertEqual(env2.client.generate_calls, [])
        self.assertEqual(env2.store.get_row(row['task_id'])['state'], 'started')
        again = env2.service.create(env2.cid, 1, base.SCRIPT)  # 이미 있는 intent: native 없이 기존 행
        self.assertEqual((again['task_id'], again['state']), (row['task_id'], 'started'))
        self.assertEqual(env2.client.generate_calls, [])
        # 정상 경로 보존: 잠금이 비어 있으면 started 행은 정확히 한 번 POST한다.
        posted = env2.service._post(row)
        self.assertEqual((posted['state'], posted['generation_id']), ('pending', 'gen-1'))
        self.assertEqual(len(env2.client.generate_calls), 1)

    def test_unknown_without_id_is_preserved_when_recovery_fails(self):
        env = self.env()
        task_id = self.unknown_task(env)
        before = env.store.get_row(task_id)
        env.client.overrides = {'seed': 99}
        self.assertEqual(self.code(env.service.inspect_recovery, task_id, GEN), 'voice_recovery_mismatch')
        resumed = env.service.resume(task_id)  # ID가 없으므로 GET/POST 모두 없다
        self.assertEqual((resumed['state'], resumed['generation_id']), ('unknown', None))
        self.assertEqual(env.store.get_row(task_id), before)
        self.assertEqual((len(env.client.generate_calls), env.client.wait_calls, env.client.audio_calls),
                         (1, [], []))
        self.assertEqual(self.code(env.service.create, env.cid, 1, base.SCRIPT, 7), 'voice_task_conflict')

    def test_disabled_service_and_constructors_do_no_native_or_lock_work(self):
        env = self.env(enabled=False)
        task_id = started_task(env)['task_id']
        for call in (lambda: env.service.inspect_recovery(task_id, GEN),
                     lambda: env.service.confirm_recovery(task_id, GEN, 'a' * 64)):
            self.assertEqual(self.code(call), 'voicebox_disabled')
        self.assertEqual((env.client.inspect_calls, env.client.generate_calls, env.client.ready_calls), ([], [], 0))
        self.assertFalse((env.tmp / 'voice' / 'voice-artifacts').exists())  # 잠금 디렉터리도 만들지 않음
        transport = client_base.FakeTransport()
        LocalVoiceboxClient(client_base.PROFILE, transport=transport)
        VoiceTaskStore(env.tmp / 'never-created')
        self.assertEqual(transport.calls, [])
        self.assertFalse((env.tmp / 'never-created').exists())
        uninitialized = VoiceTaskStore(env.tmp / 'never-created')  # initialize() 없이는 잠금 디렉터리도 만들지 않는다
        with self.assertRaises(ContractError) as caught:
            with uninitialized.task_lock('00000000-0000-4000-8000-000000000000'):
                pass
        self.assertEqual(caught.exception.code, 'voice_storage_error')
        self.assertFalse((env.tmp / 'never-created').exists())


def other_item_for(env):
    return env.content.create('personal', {'title': '경합', 'kind': 'short', 'original': '원본 대본'})


class ClientInspectTests(unittest.TestCase):
    def good(self, **override):
        payload = dict(id='g1', status='running', profile_id=client_base.PROFILE, text='  안녕하세요 ', seed=14005,
                       language='ko', engine='qwen', model_size='0.6B')
        payload.update(override)
        return payload

    def test_projection_has_exactly_eight_fields_and_one_get(self):
        extra = dict(self.good(), audio_path='/Users/x/a.wav', url='http://evil/x', token=client_base.SECRET)
        client, transport = client_base.make(client_base.js(extra))
        result = client.inspect_generation('g1')
        self.assertEqual(set(result), {'id', 'status', 'profile_id', 'text', 'seed', 'language', 'engine', 'model_size'})
        self.assertEqual(result['profile_id'], client_base.PROFILE)
        self.assertNotIn(client_base.SECRET, json.dumps(result))
        self.assertEqual(transport.calls, [('GET', '/history/g1', None)])  # POST/auth/스캔/재시도 없음
        for status in ('pending', 'queued', 'running', 'completed', 'failed', 'cancelled'):
            client, _ = client_base.make(client_base.js(self.good(status=status)))
            self.assertEqual(client.inspect_generation('g1')['status'], status)

    def test_uncertain_responses_fail_closed_after_a_single_call_without_following_urls(self):
        bad = [self.good(id='other'), self.good(status='weird'), self.good(profile_id='someone-else'),
               self.good(text='   '), self.good(text='x' * 2001), self.good(text='a\x00b'), self.good(text='\ud800'),
               self.good(seed=-1), self.good(seed=2147483648), self.good(seed=True), self.good(seed='1'),
               self.good(seed=1.5), self.good(language='en'), self.good(engine='x'), self.good(model_size='1.7B'),
               [], 'text', None]
        for field in ('id', 'status', 'profile_id', 'text', 'seed', 'language', 'engine', 'model_size'):
            missing = self.good()
            del missing[field]
            bad.append(missing)
        for payload in bad:
            client, transport = client_base.make(client_base.js(payload))
            self.assertEqual(client_base.code_of(self, client.inspect_generation, 'g1'), CLIENT_UNVERIFIABLE, payload)
            self.assertEqual(len(transport.calls), 1)
        failures = [(302, {'Location': 'http://evil/x'}, b''), (404, {}, b'{}'), (200, {}, b'not json'),
                    (200, {}, b'{"id":NaN}'), ConnectionError('boom')]
        for response in failures:
            client, transport = client_base.make(response)
            self.assertEqual(client_base.code_of(self, client.inspect_generation, 'g1'), CLIENT_UNVERIFIABLE)
            self.assertEqual(transport.calls, [('GET', '/history/g1', None)])  # 리다이렉트 추적 없음
        client, transport = client_base.make()
        for bad_id in ('', '../x', 'a b', 'a.b', 'x' * 129, None, 5):
            self.assertEqual(client_base.code_of(self, client.inspect_generation, bad_id), 'voicebox_invalid_request')
        self.assertEqual(transport.calls, [])


if __name__ == '__main__':
    unittest.main()
