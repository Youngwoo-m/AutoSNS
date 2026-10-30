"""새 조회 조합의 출처·범위·무쓰기 계약."""
from pathlib import Path
import sys
import tempfile
import unittest

APP = Path(__file__).resolve().parents[1] / 'ax-console/app'
sys.path.insert(0, str(APP))
from common.operations.content_store import ContentStore, StoreError


class WebContentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_serialization_assets_are_revision_urls_without_paths(self):
        from web_content import serialize_content
        item = {'id': 'managed_abc', 'revision': 3, 'assets': [
            {'id': 'asset_abc', 'filename': '그림.png', 'media_type': 'image/png', 'size': 8, 'sha256': 'x'}]}
        result = serialize_content(item)
        self.assertEqual(result['assets'][0]['url'], '/api/v2/contents/managed_abc/revisions/3/assets/asset_abc')
        self.assertNotIn('url', item['assets'][0])

    def test_snapshot_related_target_and_legacy_source_without_deliveries(self):
        from workspace_snapshot import build_workspace_snapshot
        store = ContentStore(self.root / 'workspace')
        store.initialize()
        item = store.create('personal', {'title': '원본', 'kind': 'article', 'original': '가' * 350,
            'variants': [{'destination_account_id': 'dept', 'platform': 'youtube', 'text': '학과 변환'}]})
        snapshot = build_workspace_snapshot(self.root / 'source', store.root, 'dept', launchagents_dir=self.root / 'agents')
        managed = next(c for c in snapshot['contents'] if c['id'] == item['id'])
        self.assertEqual(managed['target_accounts'], ['dept'])
        self.assertEqual(managed['summary'], '가' * 300)
        self.assertEqual(managed['channels'], ['youtube'])
        self.assertTrue(snapshot['workspace_writable'])
        self.assertTrue(snapshot['read_only'])
        self.assertEqual(snapshot['deliveries'], [])
        self.assertEqual(snapshot['schedule'], [])

    def test_compose_preserves_legacy_input_and_marks_colliding_sources(self):
        from workspace_snapshot import compose_workspace_snapshot
        store = ContentStore(self.root / 'workspace')
        store.initialize()
        item = store.create('dept', {'title': '관리', 'kind': 'article'})
        legacy = {'contents': [{'id': item['id'], 'title': '기존'}], 'warnings': [], 'read_only': True}
        snapshot = compose_workspace_snapshot(legacy, store.root)
        self.assertEqual([c['source'] for c in snapshot['contents']], ['legacy', 'managed'])
        self.assertNotIn('source', legacy['contents'][0])
        self.assertEqual(legacy['warnings'], [])

    def test_missing_workspace_read_does_not_initialize_and_corrupt_is_not_empty(self):
        from workspace_snapshot import build_workspace_snapshot
        missing = self.root / 'missing'
        snapshot = build_workspace_snapshot(self.root / 'source', missing, launchagents_dir=self.root / 'agents')
        self.assertFalse(snapshot['workspace_writable'])
        self.assertTrue(snapshot['warnings'])
        self.assertFalse(missing.exists())
        missing.mkdir()
        (missing / 'operations.sqlite3').write_bytes(b'broken database')
        snapshot = build_workspace_snapshot(self.root / 'source', missing, launchagents_dir=self.root / 'agents')
        self.assertFalse(snapshot['workspace_writable'])
        self.assertTrue(any('읽지 못' in warning for warning in snapshot['warnings']))


if __name__ == '__main__':
    unittest.main()
