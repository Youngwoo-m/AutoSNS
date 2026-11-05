import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import unittest
from pathlib import Path
from common.operations.integration_store import IntegrationStore
from common.operations.database import connect_database
from common.operations.content_store import StoreError, ConflictError


class IntegrationStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'workspace'
        self.store = IntegrationStore(self.root)
        self.payload = dict(platform='youtube', target_label='채널', enabled_preference=True, notes='사용 선호')

    def test_reads_do_not_create_and_restart_persistence(self):
        self.assertEqual(self.store.list(), [])
        self.assertFalse(self.root.exists())
        self.store.initialize()
        item = self.store.put('personal', 'vidiq', 'main', 0, self.payload)
        self.assertEqual(item['revision'], 1)
        self.assertEqual(IntegrationStore(self.root).list()[0], item)
        self.assertEqual(item['connection_status'], 'unknown')
        self.assertEqual(item['execution_status'], 'not_connected')

    def test_account_independence_and_cas(self):
        self.store.initialize()
        for account in ('personal', 'dept'):
            self.store.put(account, 'vidiq', 'main', 0, self.payload)
        self.assertEqual(len(self.store.list()), 2)
        self.assertEqual(len(self.store.list('dept')), 1)
        other = IntegrationStore(self.root)
        changed = dict(self.payload, notes='수정')
        self.assertEqual(other.put('dept', 'vidiq', 'main', 1, changed)['revision'], 2)
        with self.assertRaises(ConflictError):
            self.store.put('dept', 'vidiq', 'main', 1, self.payload)
        with self.assertRaises(ConflictError):
            self.store.put('dept', 'vidiq', 'main', 0, self.payload)

    def test_validation(self):
        self.store.initialize()
        invalid = [dict(self.payload, token='secret'), dict(self.payload, platform='naver_blog'),
                   dict(self.payload, enabled_preference=1), dict(self.payload, notes='x'*2001)]
        for payload in invalid:
            with self.subTest(payload=payload):
                with self.assertRaises(StoreError):
                    self.store.put('personal', 'vidiq', 'main', 0, payload)
        for account, provider, connection, revision in [('all','vidiq','main',0), ('dept','bad','main',0), ('dept','local','../x',0), ('dept','local','main',True)]:
            with self.assertRaises(StoreError):
                self.store.put(account, provider, connection, revision, self.payload)
        self.assertEqual(self.store.list(), [])

    def test_simultaneous_create_has_one_winner_and_atomic_events(self):
        self.store.initialize()
        def attempt(index):
            try:
                return IntegrationStore(self.root).put('dept', 'local', 'main', 0, dict(self.payload, notes=str(index)))
            except ConflictError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, range(2)))
        self.assertEqual(sum(result is not None for result in results), 1)
        with closing(connect_database(self.root)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM integration_events').fetchone()[0], 1)
        self.assertEqual(self.store.list()[0]['revision'], 1)

    def test_invalid_utf8_and_missing_fields_rejected_before_writing(self):
        self.store.initialize()
        for payload in [dict(self.payload, notes='\ud800'), {'platform': 'youtube'}]:
            with self.assertRaises(StoreError) as error:
                self.store.put('dept', 'local', 'main', 0, payload)
            self.assertEqual(error.exception.code, 'invalid')
        with closing(connect_database(self.root)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM integration_events').fetchone()[0], 0)
