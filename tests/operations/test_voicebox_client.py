import json
import unittest
from unittest import mock

from common.operations import voicebox_client
from common.operations.models import ContractError
from common.operations.voicebox_client import LocalVoiceboxClient, VoiceboxGenerationUnknown

PROFILE = 'profile_1'
SECRET = 'sk-SECRET-TOKEN-do-not-leak'
WAV = b'RIFF\x24\x00\x00\x00WAVEfmt ' + b'\x00' * 8
BODY = dict(profile_id=PROFILE, text='안녕하세요', language='ko', engine='qwen', model_size='0.6B',
            seed=14005, normalize=True, max_chunk_chars=250)


def js(value, status=200):
    return status, {}, json.dumps(value).encode()


class FakeTransport:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class FakeClock:
    def __init__(self):
        self.now, self.sleeps = 0.0, []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def make(*responses, **kwargs):
    transport = FakeTransport(*responses)
    return LocalVoiceboxClient(PROFILE, transport=transport, **kwargs), transport


def code_of(testcase, call, *args, **kwargs):
    with testcase.assertRaises(ContractError) as caught:
        call(*args, **kwargs)
    return caught.exception.code


class VoiceboxClientTests(unittest.TestCase):
    def test_poll_once_returns_active_and_failure_without_sleep_or_retry(self):
        for status in ('running', 'failed', 'cancelled', 'completed'):
            clock = FakeClock()
            client, transport = make(js({'id':'g1','status':status}), clock=clock, sleep=clock.sleep)
            self.assertEqual(client.poll_once('g1'), {'id':'g1','status':status})
            self.assertEqual(transport.calls, [('GET','/history/g1',None)])
            self.assertEqual(clock.sleeps, [])

    def test_constructor_does_no_io_and_validates_registration(self):
        with mock.patch('http.client.HTTPConnection') as connection, mock.patch('socket.socket') as sock:
            client = LocalVoiceboxClient(PROFILE)
        connection.assert_not_called()
        sock.assert_not_called()
        for bad in ('', 'a/b', 'a b', 'x' * 129, None, 5):
            self.assertEqual(code_of(self, LocalVoiceboxClient, bad), 'invalid_voicebox_registration')
        self.assertEqual(code_of(self, LocalVoiceboxClient, PROFILE, port=True), 'invalid_voicebox_registration')
        self.assertEqual(code_of(self, LocalVoiceboxClient, PROFILE, transport='http://x'), 'invalid_voicebox_registration')
        self.assertEqual(client.profile_id, PROFILE)

    def test_default_transport_is_fixed_literal_loopback(self):
        with mock.patch('http.client.HTTPConnection') as connection:
            response = connection.return_value.getresponse.return_value
            response.status, response.read.return_value = 200, b'[]'
            response.getheaders.return_value = []
            LocalVoiceboxClient(PROFILE, port=17493).ready()
        connection.assert_called_once_with('127.0.0.1', 17493, timeout=30)
        connection.return_value.close.assert_called_once_with()
        connection.return_value.request.assert_called_once()
        self.assertEqual(connection.return_value.request.call_args.args[:2], ('GET', '/profiles'))

    def test_ready_requires_registered_profile_and_never_raises(self):
        for payload in ([{'id': PROFILE}], {'profiles': [{'id': 'other'}, {'id': PROFILE, 'name': 'x'}]}):
            client, transport = make(js(payload))
            self.assertIs(client.ready(), True)
            self.assertEqual(transport.calls, [('GET', '/profiles', None)])
        for response in (js([{'id': 'other'}]), js({'profiles': 'nope'}), js({}), js([], 500), js([], 302),
                         (200, {}, b'not json'), (200, {}, b'[NaN]'), (200, {}, b'x' * (1024 * 1024 + 1)),
                         RuntimeError(SECRET), TimeoutError()):
            client, _ = make(response)
            self.assertIs(client.ready(), False)

    def test_generate_validates_exact_request_before_any_io(self):
        client, transport = make()
        bad_bodies = [{k: v for k, v in BODY.items() if k != 'seed'}, {**BODY, 'extra': 1},
                      {**BODY, 'profile_id': 'other'}, {**BODY, 'text': '  \n'}, {**BODY, 'text': 'a\x00b'},
                      {**BODY, 'text': 'a' * 2001}, {**BODY, 'text': 5}, {**BODY, 'language': 'en'},
                      {**BODY, 'engine': 'other'}, {**BODY, 'model_size': '1.7B'}, {**BODY, 'seed': -1},
                      {**BODY, 'seed': 2147483648}, {**BODY, 'seed': True}, {**BODY, 'seed': 1.0},
                      {**BODY, 'normalize': False}, {**BODY, 'normalize': 1}, {**BODY, 'max_chunk_chars': 500},
                      {**BODY, 'max_chunk_chars': 250.0}]
        for body in bad_bodies:
            with self.assertRaises(ContractError):
                client.generate(**body)
        self.assertEqual(transport.calls, [])

    def test_generate_posts_once_with_exact_body_and_safe_projection(self):
        reply = {'id': 'gen-1_A', 'status': 'queued', 'audio_path': '/etc/passwd', 'audio_url': 'http://evil.example/a.wav',
                 'path': '/tmp/x', 'token': SECRET}
        client, transport = make(js(reply), (302, {'Location': 'http://evil.example/'}, b''))
        result = client.generate(**{**BODY, 'text': ' 안녕하세요 '})
        self.assertEqual(result, {'id': 'gen-1_A', 'status': 'queued'})
        self.assertEqual(len(transport.calls), 1)
        method, path, raw = transport.calls[0]
        self.assertEqual((method, path), ('POST', '/generate'))
        self.assertEqual(json.loads(raw), {**BODY, 'text': '안녕하세요'})

    def test_generate_unknown_outcome_is_never_retried(self):
        failures = [TimeoutError(SECRET), (500, {}, b'oops'), (302, {}, b''), (200, {}, b'garbage'),
                    js({'id': 'a/../b', 'status': 'queued'}), js({'id': 'a', 'status': 'weird'}),
                    js(['id']), (200, {}, b'x' * (1024 * 1024 + 1))]
        for failure in failures:
            client, transport = make(failure)
            with self.assertRaises(VoiceboxGenerationUnknown) as caught:
                client.generate(**BODY)
            self.assertEqual(caught.exception.code, 'voicebox_generation_unknown')
            self.assertIsInstance(caught.exception, ContractError)
            self.assertEqual([call[0] for call in transport.calls], ['POST'])
            self.assertNotIn(SECRET, repr(caught.exception) + str(caught.exception))
        client, transport = make(js({'error': 'bad'}, 422))
        self.assertEqual(code_of(self, client.generate, **BODY), 'voicebox_invalid_response')
        self.assertEqual(len(transport.calls), 1)

    def test_wait_completed_polls_history_with_get_only(self):
        clock = FakeClock()
        client, transport = make(js({'id': 'g1', 'status': 'pending'}), js({'id': 'g1', 'status': 'running'}),
                                 js({'id': 'g1', 'status': 'completed', 'audio_path': '/etc/passwd'}),
                                 clock=clock, sleep=clock.sleep, poll_interval=3)
        self.assertEqual(client.wait_completed('g1'), {'id': 'g1', 'status': 'completed'})
        self.assertEqual(transport.calls, [('GET', '/history/g1', None)] * 3)
        self.assertEqual(clock.sleeps, [3, 3])

    def test_wait_completed_failure_timeout_and_mismatch_codes(self):
        for status in ('failed', 'cancelled'):
            client, _ = make(js({'id': 'g1', 'status': status}))
            self.assertEqual(code_of(self, client.wait_completed, 'g1'), 'voicebox_generation_failed')
        clock = FakeClock()
        client, transport = make(*[js({'id': 'g1', 'status': 'running'})] * 20, clock=clock, sleep=clock.sleep,
                                 poll_timeout=10, poll_interval=3)
        self.assertEqual(code_of(self, client.wait_completed, 'g1'), 'voicebox_poll_timeout')
        self.assertLessEqual(len(transport.calls), 5)
        self.assertTrue(all(call[0] == 'GET' for call in transport.calls))
        frozen = lambda: 0.0  # 시계가 멈춰도 반복 횟수 상한으로 끝난다
        client, transport = make(*[js({'id': 'g1', 'status': 'running'})] * 20, clock=frozen, sleep=lambda s: None,
                                 poll_timeout=10, poll_interval=3)
        self.assertEqual(code_of(self, client.wait_completed, 'g1'), 'voicebox_poll_timeout')
        for response, code in ((js({'id': 'other', 'status': 'completed'}), 'voicebox_invalid_response'),
                               (js({'id': 'g1', 'status': 'bogus'}), 'voicebox_invalid_response'),
                               ((200, {}, b'nope'), 'voicebox_invalid_response'),
                               (js({}, 404), 'voicebox_unavailable'), (OSError(SECRET), 'voicebox_unavailable'),
                               (js({}, 301), 'voicebox_invalid_response')):
            client, _ = make(response)
            self.assertEqual(code_of(self, client.wait_completed, 'g1'), code)

    def test_ids_with_path_or_query_injection_are_rejected_without_io(self):
        client, transport = make()
        for bad in ('', '../etc/passwd', 'a/b', 'a?x=1', 'a#b', 'a b', 'a\n', 'http://evil.example/x', 'é', 'x' * 129, None, 7):
            self.assertEqual(code_of(self, client.wait_completed, bad), 'voicebox_invalid_request')
            self.assertEqual(code_of(self, client.audio, bad), 'voicebox_invalid_request')
        self.assertEqual(transport.calls, [])

    def test_audio_checks_wav_header_status_and_size_limit(self):
        client, transport = make((200, {'Content-Type': 'audio/wav', 'Location': 'http://evil.example/'}, WAV))
        self.assertEqual(client.audio('g1'), WAV)
        self.assertEqual(transport.calls, [('GET', '/audio/g1', None)])
        cases = [((200, {}, b'ID3' + b'\x00' * 20), 'voicebox_audio_invalid'),
                 ((200, {}, b'RIFF\x00\x00\x00\x00AVI '), 'voicebox_audio_invalid'),
                 ((200, {}, b'RIFF'), 'voicebox_audio_invalid'), ((200, {}, b''), 'voicebox_audio_invalid'),
                 ((200, {}, bytearray(WAV)), None),
                 ((302, {'Location': '/audio/other'}, WAV), 'voicebox_unavailable'),
                 ((404, {}, WAV), 'voicebox_unavailable'), ((200, {}, 'RIFF'), 'voicebox_unavailable'),
                 (TimeoutError(SECRET), 'voicebox_unavailable')]
        for response, code in cases:
            client, _ = make(response)
            if code is None:
                self.assertEqual(client.audio('g1'), WAV)
            else:
                self.assertEqual(code_of(self, client.audio, 'g1'), code)
        with mock.patch.object(voicebox_client, 'MAX_WAV_BYTES', len(WAV)):
            client, _ = make((200, {}, WAV))
            self.assertEqual(client.audio('g1'), WAV)
            client, _ = make((200, {}, WAV + b'\x00'))
            self.assertEqual(code_of(self, client.audio, 'g1'), 'voicebox_audio_invalid')

    def test_errors_never_expose_raw_exception_or_response_text(self):
        leaks = (RuntimeError(SECRET), (200, {}, SECRET.encode()), (500, {}, SECRET.encode()),
                 js({'id': SECRET, 'status': 'queued'}))
        calls = (lambda c: c.ready(), lambda c: c.generate(**BODY), lambda c: c.wait_completed('g1'), lambda c: c.audio('g1'))
        for leak in leaks:
            for call in calls:
                client, _ = make(leak)
                try:
                    call(client)
                except ContractError as exc:
                    self.assertNotIn(SECRET, str(exc) + repr(exc) + repr(exc.args) + exc.code)
                    self.assertIsNone(exc.__cause__)

    def test_duck_types_with_voicebox_audio_runner(self):
        from tempfile import TemporaryDirectory
        from common.operations.production_media import VoiceboxAudioRunner
        client, transport = make(js([{'id': PROFILE}]), js({'id': 'g1', 'status': 'queued'}),
                                 js({'id': 'g1', 'status': 'completed'}), (200, {}, WAV),
                                 sleep=lambda s: None)
        with TemporaryDirectory() as root:
            try:
                result = VoiceboxAudioRunner(client, profile_id=PROFILE)(manifest=dict(text='안녕'), artifact_root=root)
            except ContractError as exc:  # 경로 규칙은 runner 소관. client 호출 순서만 확인한다.
                self.fail(exc.code)
        self.assertEqual(result['generation_id'], 'g1')
        self.assertEqual([(m, p) for m, p, _ in transport.calls],
                         [('GET', '/profiles'), ('POST', '/generate'), ('GET', '/history/g1'), ('GET', '/audio/g1')])


if __name__ == '__main__':
    unittest.main()
