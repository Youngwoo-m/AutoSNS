"""임시 저장소·가짜 Voicebox 전송으로 HTTP 전체 경계를 검증한다."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from tests.test_web_execution_server import server_module, APP, NoSocketServer
from tests import test_web_server as server_fixture
from tests.operations.test_voice_tasks import FakeClient, FakeProbe, PROFILE, SCRIPT, make_wav
from common.operations.content_store import ContentStore
from common.operations.voice_tasks import VoiceTaskStore, VoiceTaskService
from common.operations.voicebox_client import LocalVoiceboxClient


class VoiceHTTPTests(unittest.TestCase):
    request = server_fixture.WebServerTests.request
    login = server_fixture.WebServerTests.login

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'workspace'
        self.content = ContentStore(self.root)
        self.content.initialize()
        self.item = self.content.create('personal', dict(title='음성 시험', kind='short', original='원본', variants=[], sources=[]))
        self.store = VoiceTaskStore(self.root)
        self.store.initialize()
        self.client = FakeClient()
        self.service = VoiceTaskService(self.store, self.content, self.client, profile_id=PROFILE, enabled=True, probe=FakeProbe())
        self.server = server_module.create_server(source_root=Path(self.tmp.name)/'source', workspace_root=self.root,
            web_root=APP/'web', auth_backend=server_fixture.FakeAuth(), voice_task_service=self.service)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join()))
        self.route = '/api/v2/contents/' + self.item['id'] + '/voice-tasks'
        self.body = dict(expected_revision=1, script=SCRIPT, seed=14005)

    def test_auth_origin_schema_and_disabled_are_before_native_calls(self):
        self.assertEqual(self.request(self.route, 'POST', self.body)[0], 401)
        cookie = self.login()
        self.assertEqual(self.request(self.route, 'POST', self.body, {**cookie, 'Origin':'https://evil.example'})[0], 403)
        for field in ('profile_id', 'host', 'output_path'):
            self.assertEqual(self.request(self.route, 'POST', {**self.body, field:'untrusted'}, cookie)[0], 400)
        self.server.voice_task_service = None
        self.assertEqual(self.request(self.route, 'POST', self.body, cookie)[0], 503)
        self.assertEqual(self.client.ready_calls, 0)
        self.assertEqual(self.client.generate_calls, [])

    def test_create_resume_replay_and_private_projection(self):
        cookie = self.login()
        status, _, raw = self.request('/api/v2/voicebox/capabilities', headers=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)['readiness'], 'not_checked')
        self.assertEqual(self.client.ready_calls, 0)
        status, _, raw = self.request(self.route, 'POST', self.body, cookie)
        self.assertEqual(status, 200)
        pending = json.loads(raw)
        self.assertEqual(pending['state'], 'pending')
        route = '/api/v2/voice-tasks/' + pending['task_id']
        status, _, raw = self.request(route + '/resume', 'POST', {}, cookie)
        self.assertEqual(status, 200)
        completed = json.loads(raw)
        self.assertEqual(completed['state'], 'completed')
        self.assertEqual(completed['review_status'], 'not_checked')
        self.assertEqual(completed['output_revision'], 2)
        self.assertEqual(self.content.get(self.item['id'], 1)['original'], '원본')
        self.assertEqual(len(self.content.get(self.item['id'])['assets']), 1)
        self.assertEqual(json.loads(self.request(self.route, 'POST', self.body, cookie)[2]), completed)
        self.assertEqual(json.loads(self.request(route, headers=cookie)[2]), completed)
        listed = self.request(self.route + '?revision=1', headers=cookie)
        self.assertEqual(listed[0], 200)
        self.assertEqual(json.loads(listed[2])['items'], [completed])
        self.assertNotIn(PROFILE.encode(), listed[2])
        self.assertNotIn(SCRIPT.encode(), listed[2])
        self.assertNotIn(str(self.root).encode(), listed[2])
        self.assertEqual(len(self.client.generate_calls), 1)

    def test_mismatched_store_rejected_before_socket(self):
        other = VoiceTaskService(VoiceTaskStore(Path(self.tmp.name)/'other'), self.content,
            self.client, profile_id=PROFILE, enabled=True, probe=FakeProbe())
        with patch.object(server_module, '_WebServer', NoSocketServer), self.assertRaises(ValueError):
            server_module.create_server(source_root=Path(self.tmp.name)/'source', workspace_root=self.root,
                web_root=APP/'web', auth_backend=server_fixture.FakeAuth(), voice_task_service=other)

    def test_real_client_protocol_with_durable_service(self):
        calls = []
        def transport(method, path, body=None):
            calls.append((method, path, body))
            data = {'/profiles':[{'id':PROFILE}], '/generate':{'id':'generation1','status':'pending'},
                    '/history/generation1':{'id':'generation1','status':'completed'}}
            return (200, {}, make_wav() if path == '/audio/generation1' else json.dumps(data[path]).encode())
        self.service.client = LocalVoiceboxClient(PROFILE, transport=transport)
        first = self.service.create(self.item['id'], 1, SCRIPT)
        final = self.service.resume(first['task_id'])
        self.assertEqual(final['state'], 'completed')
        self.assertEqual(self.service.create(self.item['id'], 1, SCRIPT), final)
        posts = [call for call in calls if call[0] == 'POST']
        self.assertEqual(len(posts), 1)
        payload = json.loads(posts[0][2])
        self.assertEqual(payload['profile_id'], PROFILE)
        self.assertEqual(payload['engine'], 'qwen')
        self.assertEqual(payload['text'], SCRIPT)

    def test_real_client_resume_checks_once_and_persists_terminal_failure(self):
        calls = []
        status = ['running']
        def transport(method, path, body=None):
            calls.append((method, path))
            payload = ([{'id':PROFILE}] if path == '/profiles' else
                       {'id':'generation2','status':'pending' if path == '/generate' else status[0]})
            return 200, {}, json.dumps(payload).encode()
        self.service.client = LocalVoiceboxClient(PROFILE, transport=transport,
            sleep=lambda _: self.fail('웹 상태 확인에서 대기하지 않아야 함'))
        row = self.service.create(self.item['id'], 1, SCRIPT)
        self.assertEqual(self.service.resume(row['task_id'])['state'], 'pending')
        self.assertEqual(calls.count(('GET','/history/generation2')), 1)
        status[0] = 'failed'
        failed = self.service.resume(row['task_id'])
        self.assertEqual(failed['state'], 'failed')
        before = list(calls)
        self.assertEqual(self.service.resume(row['task_id']), failed)
        self.assertEqual(calls, before)
