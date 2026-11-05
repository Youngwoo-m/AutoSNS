import json,tempfile,threading
from pathlib import Path
import unittest
from tests.test_web_execution_server import server_module,APP
from tests import test_web_server as fixture
from tests.operations.test_voice_tasks import FakeClient,FakeProbe,SCRIPT
from common.operations.voice_tasks import VoiceTaskService
from common.operations.account_voice_service import AccountVoiceTaskService

class AccountVoiceHTTPTests(unittest.TestCase):
    request=fixture.WebServerTests.request
    login=fixture.WebServerTests.login
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.server=server_module.create_server(source_root=self.root/'source',workspace_root=self.root/'managed',web_root=APP/'web',auth_backend=fixture.FakeAuth())
        self.server.content_store.initialize();self.server.voice_task_store.initialize()
        self.server.voice_settings_store.initialize()
        self.contents={a:self.server.content_store.create(a,dict(title=a,kind='short')) for a in ('personal','dept')}
        self.clients={a:FakeClient() for a in self.contents}
        services={a:VoiceTaskService(self.server.voice_task_store,self.server.content_store,self.clients[a],profile_id='profile-'+a,enabled=True,probe=FakeProbe()) for a in self.contents}
        self.server.voice_task_service=AccountVoiceTaskService(self.server.voice_task_store,self.server.content_store,services)
        thread=threading.Thread(target=self.server.serve_forever,daemon=True);thread.start()
        self.addCleanup(lambda:(self.server.shutdown(),self.server.server_close(),thread.join()))
    def test_settings_cas_do_not_call_service_and_cannot_set_runtime_or_owner(self):
        path='/api/v2/accounts/personal/voice-settings'
        self.assertEqual(self.request(path)[0],401);cookie=self.login()
        status,_,raw=self.request(path,headers=cookie);self.assertEqual(status,200)
        self.assertEqual(json.loads(raw)['revision'],0)
        body=dict(expected_revision=0,settings=dict(enabled_preference=True,profile_id='next-profile'))
        self.assertEqual(self.request(path,'POST',body,dict(cookie,Origin='https://evil.example'))[0],403)
        status,_,raw=self.request(path,'POST',body,cookie);self.assertEqual(status,200)
        self.assertFalse(json.loads(raw)['execution_enabled'])
        self.assertEqual(self.request(path,'POST',body,cookie)[0],409)
        for injected in (dict(body,account_id='dept'),dict(body,run=True),dict(body,settings=dict(body['settings'],host='elsewhere'))):
            self.assertEqual(self.request(path,'POST',injected,cookie)[0],400)
        self.assertEqual(self.server.voice_settings_store.get('dept')['revision'],0)
        self.assertTrue(all(not c.generate_calls and c.ready_calls==0 for c in self.clients.values()))
    def test_server_owner_selects_profile_and_account_capabilities_are_bounded(self):
        cookie=self.login()
        for account,item in self.contents.items():
            path='/api/v2/contents/'+item['id']+'/voice-tasks'
            code,_,raw=self.request(path,'POST',dict(expected_revision=1,script=SCRIPT,seed=14005),cookie)
            self.assertEqual(code,200);self.assertEqual(json.loads(raw)['state'],'pending')
            self.assertEqual(self.clients[account].generate_calls[0]['profile_id'],'profile-'+account)
            cap='/api/v2/voicebox/capabilities?account='+account
            code,_,raw=self.request(cap,headers=cookie);self.assertEqual(code,200)
            self.assertTrue(json.loads(raw)['execution_enabled']);self.assertNotIn(b'profile-',raw)
        self.server.voice_task_service=AccountVoiceTaskService(self.server.voice_task_store,self.server.content_store,{'personal':self.server.voice_task_service.services['personal']})
        code,_,raw=self.request('/api/v2/voicebox/capabilities?account=dept',headers=cookie)
        self.assertFalse(json.loads(raw)['execution_enabled'])
        for query in ('?account=else','?account=personal&account=dept','?account=personal&profile_id=x'):
            self.assertEqual(self.request('/api/v2/voicebox/capabilities'+query,headers=cookie)[0],400)
