import csv
import io
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from common.operations.metrics_csv import build_csv_preview, import_csv
from common.operations.metrics_store import MetricsStore
from common.operations.models import Registry, Connection
from common.operations.content_store import StoreError, ConflictError

class CsvTests(unittest.TestCase):
    def setUp(self):
        self.registry = Registry('r1', {'personal': {}, 'dept': {}}, {}, {}, {'c': Connection('c', 'personal', 'youtube', target_id='channel')}, {}, {}, {})
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store = MetricsStore(self.tmp.name); self.store.initialize()
    def data(self, rows=None):
        stream = io.StringIO(); writer = csv.writer(stream)
        writer.writerow(['platform','target_id','remote_id','metric_name','value','observed_at','basis','title'])
        writer.writerows(rows or [['youtube','channel','v','views','0','2026-01-01T00:00:00Z','lifetime','제목\n다음']])
        return stream.getvalue().encode('utf-8-sig')
    def preview(self, data):
        return build_csv_preview(data, account_id='personal', registry=self.registry)
    def load(self, data, key='key', digest=None):
        return import_csv(self.store, data, account_id='personal', registry=self.registry, preview_digest=digest or self.preview(data)['preview_digest'], request_key=key)
    def test_bom_quoted_newline_duplicate_header_and_formula(self):
        self.assertTrue(self.preview(self.data())['can_import'])
        for data in (b'platform,platform\nyoutube,youtube\n', self.data([['youtube','channel','v','views','0','2026-01-01T00:00:00Z','lifetime',' \t=cmd']])):
            with self.assertRaises(StoreError): self.preview(data)
    def test_registry_scope_mismatch_and_unmapped_owner(self):
        self.load(self.data()); saved = self.store.list_observations()[0]
        self.assertEqual(saved['source_kind'], 'legacy_reported'); self.assertIsNone(saved['owner_account_id'])
        with self.assertRaises(StoreError): build_csv_preview(self.data(), account_id='dept', registry=self.registry)
        data = self.data().replace(b'channel', b'unknown')
        row = self.preview(data)['rows'][0]; self.assertIsNone(row['destination_account_id'])
    def test_duplicate_row_reorder_concurrent_receipt(self):
        a = ['youtube','channel','a','views','0','2026-01-01T00:00:00Z','lifetime','a']; b = a.copy(); b[2]='b'
        data = self.data([a,b,a]); self.assertEqual(self.load(data)['imported'], 2)
        self.assertEqual(self.load(self.data([b,a]), 'other')['imported'], 0)
        with ThreadPoolExecutor(2) as pool: results = list(pool.map(lambda _: self.load(data), range(2)))
        self.assertEqual(results[0], results[1]); self.assertEqual(len(self.store.list_observations()), 2)
    def test_changed_registry_or_payload_digest_is_conflict(self):
        data = self.data(); digest = self.preview(data)['preview_digest']; self.load(data)
        with self.assertRaises(ConflictError): self.load(data.replace(b',0,', b',1,'), digest=digest)
        other = Registry('r2', self.registry.accounts, {}, {}, self.registry.connections, {}, {}, {})
        with self.assertRaises(ConflictError): import_csv(self.store, data, account_id='personal', registry=other, preview_digest=digest, request_key='key')
        invalid = data.replace(b',0,', b',NaN,'); self.assertFalse(self.preview(invalid)['can_import'])
        with self.assertRaises(StoreError): self.load(invalid, 'invalid')
        self.assertEqual(len(self.store.list_observations()), 1)

    def test_limits_headers_encoding_and_atomic_invalid_row(self):
        for data in (b'\xff', b'x' * (256 * 1024 + 1), self.data().replace(b'title', b'owner_account_id'), self.data() + b'broken,row\n', b'platform,target_id,remote_id,metric_name,value,observed_at,basis\nyoutube,channel,v,views,1,2026-01-01T00:00:00Z,"lifetime\n'):
            with self.assertRaises(StoreError): self.preview(data)
        a = ['youtube','channel','a','views','0','2026-01-01T00:00:00Z','lifetime','a']
        with self.assertRaises(StoreError): self.preview(self.data([a] * 1001))
        bad = a.copy(); bad[4] = '-1'
        data = self.data([a, bad])
        with self.assertRaises(StoreError): self.load(data)
        self.assertEqual(self.store.list_observations(), [])

    def test_fresh_concurrent_import_and_revision_only_deduplication(self):
        data = self.data()
        with ThreadPoolExecutor(2) as pool: results = list(pool.map(lambda _: self.load(data), range(2)))
        self.assertEqual(results[0], results[1]); self.assertEqual(results[0]['imported'], 1)
        self.registry = Registry('r2', self.registry.accounts, {}, {}, self.registry.connections, {}, {}, {})
        self.assertEqual(self.load(data, 'new')['imported'], 0)
        with self.assertRaises(ConflictError): self.load(data)

    def test_mapping_change_is_distinct_immutable_observation(self):
        data = self.data().replace(b'channel', b'unknown'); self.load(data)
        self.registry = Registry('r2', self.registry.accounts, {}, {}, {'new': Connection('new','personal','youtube',target_id='unknown')}, {}, {}, {})
        self.assertEqual(self.load(data, 'mapped')['imported'], 1)
        rows = self.store.list_observations()
        self.assertIsNone(rows[0]['destination_account_id'])
        self.assertEqual(rows[1]['destination_account_id'], 'personal')
        self.assertTrue(all(r['source_kind'] == 'legacy_reported' and r['content_id'] is None and r['delivery_id'] is None for r in rows))
