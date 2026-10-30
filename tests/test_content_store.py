"""관리 저장소 시험: 모든 I/O는 임시 루트에 한정한다."""
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from common.operations.content_store import ContentStore, StoreError, ConflictError
from common.operations.database import initialize_database, connect_database, SCHEMA_VERSION

PAYLOAD = {'title': '원고', 'kind': 'article', 'original': '초안'}
PNG = b'\x89PNG\r\n\x1a\n' + b'fixture'

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'workspace'
        self.store = ContentStore(self.root)

    def init(self):
        self.store.initialize()
        return self.store.create('personal', PAYLOAD)

    def error(self, code, fn, *args):
        with self.assertRaises(StoreError) as ctx:
            fn(*args)
        self.assertEqual(ctx.exception.code, code)

    def test_reads_never_create_root_or_database(self):
        self.assertEqual(self.store.list(), [])
        self.assertIsNone(self.store.get('managed_missing'))
        self.assertEqual(self.store.list_revisions('managed_missing'), [])
        self.error('not_found', self.store.read_asset, 'managed_missing', 1, 'asset_missing')
        self.assertFalse(self.root.exists())
        with self.assertRaises(FileNotFoundError):
            connect_database(self.root)
        self.error('storage_error', self.store.create, 'personal', PAYLOAD)
        self.assertFalse(self.root.exists())

    def test_database_initialization_is_atomic_idempotent_and_shared(self):
        errors = []
        def init():
            try: initialize_database(self.root)
            except Exception as exc: errors.append(exc)
        threads = [threading.Thread(target=init) for _ in range(3)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(errors, [])
        with connect_database(self.root) as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({'contents', 'revisions', 'reviews', 'events', 'integration_settings', 'integration_events'} <= tables)
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)
            self.assertEqual(conn.execute('PRAGMA foreign_keys').fetchone()[0], 1)
            self.assertEqual(conn.execute('PRAGMA busy_timeout').fetchone()[0], 5000)
        conn.close()
        conn = sqlite3.connect(self.root / 'operations.sqlite3')
        conn.execute('PRAGMA user_version=99'); conn.close()
        with self.assertRaises(Exception): initialize_database(self.root)
        with self.assertRaises(Exception): connect_database(self.root, writable=True)

    def test_revisions_are_persistent_immutable_and_manifest_is_canonical(self):
        one = self.init()
        self.assertTrue(one['id'].startswith('managed_'))
        self.assertEqual(one['revision'], 1)
        fields = ['owner_account_id','title','kind','series','status','original','variants','sources','assets']
        raw = json.dumps({k:one[k] for k in fields},sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
        self.assertEqual(one['manifest_hash'], hashlib.sha256(raw).hexdigest())
        two = self.store.update(one['id'], 1, {**PAYLOAD, 'original': '수정', 'status': 'production'})
        self.assertEqual(two['revision'], 2)
        reopened = ContentStore(self.root)
        self.assertEqual(reopened.get(one['id'], 1)['original'], '초안')
        self.assertEqual(reopened.get(one['id'])['original'], '수정')
        self.assertEqual([r['revision'] for r in reopened.list_revisions(one['id'])], [1,2])
        files = list(self.root.rglob('manifest.json'))
        self.assertEqual(len(files), 2)

    def test_two_simultaneous_connections_have_exactly_one_cas_winner(self):
        one = self.init(); barrier = threading.Barrier(2); results = []
        def update(title):
            store = ContentStore(self.root); store.initialize(); barrier.wait()
            try: results.append(store.update(one['id'], 1, {**PAYLOAD,'title':title})['title'])
            except ConflictError: results.append('conflict')
        ts = [threading.Thread(target=update,args=(s,)) for s in ['A','B']]
        for t in ts: t.start()
        for t in ts: t.join()
        self.assertEqual(results.count('conflict'), 1)
        self.assertEqual(self.store.get(one['id'])['revision'], 2)
        self.assertEqual(len(self.store.list_revisions(one['id'])), 2)

    def test_payload_owner_and_nested_fields_are_strict(self):
        one=self.init()
        for payload in [{**PAYLOAD,'owner_account_id':'dept'}, {**PAYLOAD,'credential_ref':'x'}, {**PAYLOAD,'status':'approved'}, {**PAYLOAD,'title':'x'*301}, {**PAYLOAD,'variants':[{'destination_account_id':'dept','platform':'evil','text':''}]}, {**PAYLOAD,'sources':[{'url':'file:///tmp/x','note':''}]}]:
            self.error('invalid',self.store.update,one['id'],1,payload)
        self.error('invalid',self.store.create,'all',PAYLOAD)
        self.error('invalid',self.store.update,one['id'],True,PAYLOAD)
        variant={'destination_account_id':'dept','platform':'youtube','text':'변환'}
        self.error('invalid',self.store.update,one['id'],1,{**PAYLOAD,'variants':[variant,variant]})
        saved=self.store.update(one['id'],1,{**PAYLOAD,'variants':[variant]})
        self.assertEqual(self.store.list('dept')[0]['id'],saved['id'])

    def test_reviews_are_manual_bound_to_revision_hash_and_never_inherited(self):
        one=self.init()
        review=self.store.record_review(one['id'],1,one['manifest_hash'],'source','pass','확인')
        self.assertEqual(review['method'],'manual')
        self.assertEqual(self.store.get(one['id'])['reviews'][0]['id'],review['id'])
        self.error('conflict', self.store.record_review,one['id'],1,'0'*64,'source','pass','')
        two=self.store.update(one['id'],1,PAYLOAD)
        self.assertEqual(two['reviews'],[])
        self.assertEqual(len(self.store.get(one['id'],1)['reviews']),1)
        self.error('invalid',self.store.record_review,one['id'],2,two['manifest_hash'],'source','pass','x'*10001)

    def test_assets_keep_ids_validate_bytes_and_detect_tampering(self):
        one=self.init()
        two=self.store.add_asset(one['id'],1,'그림.png','image/png',PNG)
        asset=two['assets'][0]
        self.assertNotIn('url',asset)
        self.assertEqual(self.store.read_asset(one['id'],2,asset['id']),(asset,PNG))
        three=self.store.update(one['id'],2,PAYLOAD)
        self.assertEqual(three['assets'],two['assets'])
        self.assertEqual(self.store.read_asset(one['id'],3,asset['id'])[1],PNG)
        self.error('not_found',self.store.read_asset,one['id'],1,asset['id'])
        asset_path=next(p for p in self.root.rglob(asset['id']) if p.is_file() and '3' in p.relative_to(self.root).parts)
        asset_path.write_bytes(b'corrupt')
        self.error('storage_error',self.store.read_asset,one['id'],3,asset['id'])
        self.error('storage_error',self.store.update,one['id'],3,PAYLOAD)

    def test_asset_validation_and_limits(self):
        one=self.init()
        for filename in ['../a.png','a\\b.png','a\n.png','a\x00.png','a'*201+'.png']:
            self.error('invalid',self.store.add_asset,one['id'],1,filename,'image/png',PNG)
        for name,mime,data in [('a.svg','image/svg+xml',b'<svg/>'),('a.png','image/png',b'evil'),('a.jpg','image/png',PNG)]:
            self.error('unsupported_media',self.store.add_asset,one['id'],1,name,mime,data)
        with patch('common.operations.content_store.MAX_ASSET_BYTES', 3):
            self.error('too_large',self.store.add_asset,one['id'],1,'a.png','image/png',PNG)
        with patch('common.operations.content_store.MAX_CONTENT_ASSET_BYTES',len(PNG)):
            two=self.store.add_asset(one['id'],1,'a.png','image/png',PNG)
            self.store.update(one['id'],2,PAYLOAD)
            self.error('too_large',self.store.add_asset,one['id'],3,'b.png','image/png',PNG)

    def test_database_wrong_version_does_not_change_journal_mode(self):
        self.root.mkdir()
        conn=sqlite3.connect(self.root/'operations.sqlite3')
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA user_version=99')
        conn.close()
        for action in [lambda: initialize_database(self.root), lambda: connect_database(self.root,writable=True)]:
            with self.assertRaises(sqlite3.DatabaseError): action()
            conn=sqlite3.connect(self.root/'operations.sqlite3')
            self.assertEqual(conn.execute('PRAGMA journal_mode').fetchone()[0],'wal')
            conn.close()

    def test_missing_records_and_json_limit_have_stable_codes(self):
        one=self.init()
        self.error('not_found',self.store.update,'managed_missing',1,PAYLOAD)
        self.error('not_found',self.store.add_asset,'managed_missing',1,'a.png','image/png',PNG)
        self.error('not_found',self.store.record_review,'managed_missing',1,'0'*64,'general','pass','')
        self.error('not_found',self.store.read_asset,one['id'],99,'asset_missing')
        with patch('common.operations.content_store.MAX_JSON_BYTES',10):
            self.error('too_large',self.store.update,one['id'],1,PAYLOAD)
        for key in ['kind','status']:
            self.error('invalid',self.store.update,one['id'],1,{**PAYLOAD,key:[]})
        self.error('invalid',self.store.update,one['id'],1,{**PAYLOAD,'variants':[{'destination_account_id':[], 'platform':[], 'text':''}]})

    def test_fsync_failure_leaves_previous_version_visible(self):
        one=self.init()
        with patch('common.operations.content_store.os.fsync',side_effect=OSError('sync failure')):
            self.error('storage_error',self.store.update,one['id'],1,PAYLOAD)
        self.assertEqual(self.store.get(one['id'])['revision'],1)
        self.assertEqual(self.store.list_revisions(one['id'])[0]['revision'],1)

    def test_all_supported_asset_signatures_and_cross_type_rejection(self):
        item=self.init()
        fixtures=[('a.jpg','image/jpeg',b'\xff\xd8\xfffixture'),
                  ('a.webp','image/webp',b'RIFFxxxxWEBPfixture'),
                  ('a.mp4','video/mp4',b'\x00\x00\x00\x18ftypisomfixture'),
                  ('a.mp3','audio/mpeg',b'ID3fixture'),
                  ('a.wav','audio/wav',b'RIFFxxxxWAVEfixture')]
        for filename,media_type,data in fixtures:
            item=self.store.add_asset(item['id'],item['revision'],filename,media_type,data)
            self.assertEqual(self.store.read_asset(item['id'],item['revision'],item['assets'][-1]['id'])[1],data)
        self.error('unsupported_media',self.store.add_asset,item['id'],item['revision'],'bad.webp','image/webp',b'RIFFxxxxWAVEfixture')

    def test_file_failure_does_not_publish_partial_revision(self):
        one=self.init()
        with patch('pathlib.Path.write_bytes',side_effect=OSError('disk failure')):
            self.error('storage_error',self.store.update,one['id'],1,PAYLOAD)
        self.assertEqual(self.store.get(one['id'])['revision'],1)
        self.assertEqual(self.store.update(one['id'],1,PAYLOAD)['revision'],2)

    def test_commit_failure_after_move_preserves_previous_revision_and_retry(self):
        one=self.init()
        with connect_database(self.root,writable=True) as conn:
            conn.execute('CREATE TABLE commit_failure(value TEXT REFERENCES contents(id) DEFERRABLE INITIALLY DEFERRED)')
            conn.execute("CREATE TRIGGER fail_revision AFTER INSERT ON revisions WHEN NEW.revision=2 BEGIN INSERT INTO commit_failure VALUES('missing'); END")
        conn.close()
        self.error('storage_error',self.store.update,one['id'],1,PAYLOAD)
        self.assertEqual(self.store.get(one['id'])['revision'],1)
        with connect_database(self.root,writable=True) as conn: conn.execute('DROP TRIGGER fail_revision')
        conn.close()
        self.assertEqual(self.store.update(one['id'],1,PAYLOAD)['revision'],2)

    def test_symlink_path_escape_never_reads_or_writes_outside_root(self):
        one=self.init(); outside=Path(self.tmp.name)/'outside'; outside.mkdir()
        revisions=self.root/'personal'/'content'/one['id']/'revisions'
        moved=revisions.with_name('retained'); revisions.rename(moved); revisions.symlink_to(outside,target_is_directory=True)
        self.error('storage_error',self.store.get,one['id'])
        self.error('storage_error',self.store.update,one['id'],1,PAYLOAD)
        self.assertEqual(list(outside.iterdir()),[])

if __name__ == '__main__': unittest.main()
