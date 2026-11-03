"""임대 저장소의 비공개 바이트와 수명 계약."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3

import unittest
import tempfile

from common.operations.media_leases import DB_NAME, MediaLeaseStore
from common.operations.models import ContractError

NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)
RAW = b'\xff\xd8\xff' + b'private-image' * 200 + b'\xff\xd9'


def request(raw=RAW):
    return dict(context_hash='a'*64, owner_account_id='owner', destination_account_id='destination', connection_id='connection',
                target_id='target', content_id='content', content_revision=1, manifest_hash='b'*64, position=0,
                asset_id='asset', asset_sha256=hashlib.sha256(raw).hexdigest(), asset_size=len(raw), media_type='image/jpeg')



def issue(store, **kwargs):
    args = dict(request=request(), raw=RAW, expires_at=NOW + timedelta(hours=1), now=NOW, authority={'context': {'private': 'secret'}, 'prepared': {'caption': '비공개'}})
    args.update(kwargs)
    return store.issue(**args)


class MediaLeaseStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        from pathlib import Path
        self.tmp_path = Path(self.temp.name)
        self.store = MediaLeaseStore(self.tmp_path / 'leases')
        self.store.initialize()

    def test_inert_private_and_exact_receipt(self):
        tmp_path = self.tmp_path
        root = tmp_path / 'private'
        store = MediaLeaseStore(root)
        assert not root.exists()
        assert store.lookup('c'*64, now=NOW) is None
        assert not root.exists()
        assert str(root) not in repr(store)
        store.initialize()
        receipt = issue(store)
        assert set(receipt) == {'lease_id', 'token', 'asset_sha256', 'asset_size', 'media_type', 'expires_at', 'receipt_id'}
        assert len(receipt['token']) == 64
        assert (root / DB_NAME).stat().st_mode & 0o777 == 0o600
        metadata = store.lookup(receipt['token'], now=NOW)
        assert metadata['authority']['prepared']['caption'] == '비공개'
        assert 'token' not in metadata
        safe = json.dumps(store.list_status(destination_account_id='destination', now=NOW))
        for secret in (receipt['token'], 'secret', 'caption', 'context', 'authority', 'receipt_id', str(root)):
            assert secret not in safe
        assert store.list_status(destination_account_id='other', now=NOW) == []


    def case_ttl_rejected(self, delta):
        store = self.store
        with self.assertRaises(ContractError):
            issue(store, expires_at=NOW + delta)


    def test_utc_and_boundary(self):
        store = self.store
        with self.assertRaises(ContractError):
            issue(store, now=NOW.replace(tzinfo=None))
        assert issue(store, expires_at=NOW + timedelta(hours=24))


    def test_retry_keeps_token_and_expiry_and_authority(self):
        store = self.store
        first = issue(store)
        assert issue(store, expires_at=NOW + timedelta(hours=2), now=NOW + timedelta(minutes=1)) == first
        with self.assertRaises(ContractError):
            issue(store, authority={'different': True})
        assert store.lookup('0'*64, now=NOW) is None
        assert store.lookup('../invalid', now=NOW) is None


    def case_tombstone_never_reissued(self, mode):
        store = MediaLeaseStore(self.tmp_path / mode)
        store.initialize()
        receipt = issue(store)
        current = NOW + timedelta(hours=2) if mode == 'expired' else NOW
        if mode != 'expired':
            assert store.revoke(receipt['lease_id'], now=current)
            assert not store.revoke(receipt['lease_id'], now=current)
        if mode == 'purged':
            assert store.purge(now=current) == 1
            assert store.purge(now=current) == 0
        assert not store.is_active(receipt['lease_id'], now=current)
        assert store.lookup(receipt['token'], now=current) is None
        with self.assertRaises(ContractError):
            issue(store, now=current, expires_at=current + timedelta(hours=1))
        with self.assertRaises(ContractError):
            with store.open_payload(receipt['lease_id'], now=current):
                self.fail('비활성 payload 열림')


    def test_chunk_stream_and_concurrent_revoke(self):
        store = self.store
        receipt = issue(store)
        with store.open_payload(receipt['lease_id'], now=NOW) as stream:
            assert not isinstance(stream, bytes)
            assert stream.read(3) == RAW[:3]
            stream.seek(0)
            digest = hashlib.sha256()
            while chunk := stream.read(17):
                digest.update(chunk)
            assert digest.hexdigest() == receipt['asset_sha256']
            assert store.revoke(receipt['lease_id'], now=NOW)
            assert not store.is_active(receipt['lease_id'], now=NOW)
        assert store.purge(now=NOW) == 1
        with sqlite3.connect(store.root / DB_NAME) as db:
            assert db.execute('SELECT payload,purged FROM media_leases').fetchone() == (None, 1)


    def case_bindings(self, change):
        store = self.store
        altered = request()
        altered.update(change)
        with self.assertRaises(ContractError):
            issue(store, request=altered)


    def test_mp4(self):
        store = self.store
        raw = b'\x00\x00\x00\x10ftypisom0000' + b'payload'
        req = request(raw)
        req['media_type'] = 'video/mp4'
        assert issue(store, raw=raw, request=req)['media_type'] == 'video/mp4'


    def test_symlinks_and_foreign_db(self):
        tmp_path = self.tmp_path
        actual = tmp_path / 'actual'
        actual.mkdir()
        link = tmp_path / 'link'
        link.symlink_to(actual, target_is_directory=True)
        with self.assertRaises(ContractError):
            MediaLeaseStore(link).initialize()
        db = actual / DB_NAME
        db.symlink_to(tmp_path / 'missing')
        with self.assertRaises(ContractError):
            MediaLeaseStore(actual).initialize()
        db.unlink()
        with sqlite3.connect(db) as conn:
            conn.execute('CREATE TABLE foreign_data(secret TEXT)')
        db.chmod(0o600)
        with self.assertRaises(ContractError):
            MediaLeaseStore(actual).initialize()
        with sqlite3.connect(db) as conn:
            assert conn.execute("SELECT name FROM sqlite_master WHERE name='foreign_data'").fetchone()


    def test_payload_tampering_rejected_before_yield(self):
        store = self.store
        receipt = issue(store)
        with sqlite3.connect(store.root / DB_NAME) as db:
            db.execute('UPDATE media_leases SET payload=?', (b'x' * len(RAW),))
        with self.assertRaises(ContractError):
            with store.open_payload(receipt['lease_id'], now=NOW):
                self.fail('변조 바이트가 노출됨')


    def test_sidecar_symlink_rejected(self):
        store = self.store
        tmp_path = self.tmp_path
        side = store.root / (DB_NAME + '-wal')
        if side.exists():
            side.unlink()
        side.symlink_to(tmp_path / 'outside')
        with self.assertRaises(ContractError):
            store.is_active('anything', now=NOW)

    def test_ttl_rejected(self):
        for value in [timedelta(minutes=5), timedelta(seconds=-1), timedelta(hours=24, seconds=1)]:
            with self.subTest(value=value):
                self.case_ttl_rejected(value)

    def test_tombstone_never_reissued(self):
        for value in ['expired', 'revoked', 'purged']:
            with self.subTest(value=value):
                self.case_tombstone_never_reissued(value)

    def test_bindings(self):
        for value in [{'asset_sha256': '0'*64}, {'asset_size': 1}, {'media_type': 'image/png'}, {'position': True}, {'position': 10}, {'extra': 1}]:
            with self.subTest(value=value):
                self.case_bindings(value)

    def test_magic_binding_rejects_truncated_formats(self):
        for raw, media_type in [(b'\xff\xd8\xffbad', 'image/jpeg'),
                                (b'\x00\x00\x00\x20ftypisom0000', 'video/mp4'),
                                (b'\x00\x00\x00\x11ftypisom00000', 'video/mp4')]:
            with self.subTest(media_type=media_type):
                req = request(raw)
                req['media_type'] = media_type
                with self.assertRaises(ContractError):
                    issue(self.store, raw=raw, request=req)
