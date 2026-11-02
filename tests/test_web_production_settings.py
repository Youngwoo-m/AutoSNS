import json
from pathlib import Path
import tempfile
import threading
import unittest
from tests import test_web_execution_server as web_fixture
from tests import test_web_server as http_fixture
from common.operations.content_store import ContentStore

class ProductionSettingsHTTPTests(unittest.TestCase):
    request=http_fixture.WebServerTests.request
    login=http_fixture.WebServerTests.login
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.server=web_fixture.server_module.create_server(source_root=self.root/'source',
            workspace_root=self.root/'managed',web_root=web_fixture.APP/'web',auth_backend=http_fixture.FakeAuth())
        thread=threading.Thread(target=self.server.serve_forever,daemon=True);thread.start()
        def close():self.server.shutdown();self.server.server_close();thread.join()
        self.addCleanup(close)
    def test_auth_read_is_inert_and_explicit_save_preserves_operational_quota(self):
        path='/api/v2/production/settings?account=personal'
        self.assertEqual(self.request(path)[0],401)
        cookie=self.login()
        status,_,data=self.request(path,headers=cookie)
        self.assertEqual(status,200);self.assertEqual(json.loads(data)['revision'],0)
        self.assertFalse((self.root/'managed').exists())
        content=ContentStore(self.root/'managed');content.initialize()
        before=(self.root/'managed/operations.sqlite3').read_bytes()
        self.server.production_settings_store.initialize()
        body=dict(expected_revision=0,enabled_preference=True,daily_limit=4)
        self.assertEqual(self.request(path,'POST',body,dict(cookie,Origin='https://evil.example'))[0],403)
        status,_,data=self.request(path,'POST',body,cookie)
        self.assertEqual(status,200);row=json.loads(data)
        self.assertEqual(row['revision'],1);self.assertFalse(row['execution_enabled'])
        self.assertEqual(self.request(path,'POST',body,cookie)[0],409)
        status,_,data=self.request('/api/v2/production/settings?account=dept',headers=cookie)
        self.assertEqual(json.loads(data)['revision'],0)
        self.assertEqual(before,(self.root/'managed/operations.sqlite3').read_bytes())
        self.assertIsNone(self.server.execution_service)
    def test_schema_and_initialization_boundaries(self):
        cookie=self.login();path='/api/v2/production/settings?account=personal'
        body=dict(expected_revision=0,enabled_preference=False,daily_limit=None)
        self.assertEqual(self.request(path,'POST',body,cookie)[0],503)
        for query in ('','?account=all','?account=personal&account=dept','?account=dept&run=1'):
            self.assertEqual(self.request('/api/v2/production/settings'+query,headers=cookie)[0],400)
        self.server.production_settings_store.initialize()
        for change in (dict(run_enabled=True),dict(expected_revision=True),dict(daily_limit=True),dict(enabled_preference=True)):
            self.assertEqual(self.request(path,'POST',dict(body,**change),cookie)[0],400)
        self.assertFalse(self.server.production_settings_store.get('personal')['enabled_preference'])
