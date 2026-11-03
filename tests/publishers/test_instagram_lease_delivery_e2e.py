"""고정 바이트 임대부터 명시 loopback 전달까지의 격리 시험."""
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import timedelta
import http.client
import io
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlsplit

from common.operations.media_leases import MediaLeaseStore
from common.operations.media_lease_http import build_media_server
from common.publishers.instagram_media_leases import BoundInstagramMediaStager, InstagramLeaseAuthorityGuard
from common.publishers.instagram_media_sources import InstagramMediaSourceFactory
from tests.publishers.test_instagram_media_sources import NOW, JPEG, VIDEO, context, metadata, prepared

HOST = 'media.example.com'


class InstagramLeaseDeliveryE2ETests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = MediaLeaseStore(Path(temporary.name) / 'private')
        self.store.initialize()
        self.review = True
        self.serving = True
        self.logs = io.StringIO()
        self.output = redirect_stdout(self.logs)
        self.errors = redirect_stderr(self.logs)
        self.output.__enter__()
        self.errors.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)
        self.addCleanup(self.errors.__exit__, None, None, None)
        self.server = build_media_server(self.store, enabled=True, host='127.0.0.1', port=0,
            expected_host=HOST, clock=lambda: NOW,
            authority_guard=InstagramLeaseAuthorityGuard(lambda ctx, payload: self.review),
            serving_allowed=lambda: self.serving)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def stage(self, raw=JPEG, mime='image/jpeg', *, issued_at=NOW):
        fmt = 'reels' if mime == 'video/mp4' else 'image'
        ctx = replace(context(options={'instagram': {'format': fmt, 'asset_ids': ['asset']}}),
            auth_checked_at=issued_at, auth_expires_at=issued_at + timedelta(hours=4))
        asset = metadata('asset', raw, mime)
        payload = prepared(ctx, [asset])
        guard = lambda context, value: self.review
        stager = BoundInstagramMediaStager(ctx, payload, self.store,
            public_host=HOST, clock=lambda: issued_at, write_guard=guard)
        factory = InstagramMediaSourceFactory(lambda *args: (asset, raw),
            stager=stager, approval_guard=guard, allowed_hosts=(HOST,), clock=lambda: issued_at)
        return factory.prepare(ctx, payload)[0]

    def request(self, receipt, method='GET', headers=None):
        url = urlsplit(receipt.url)
        self.assertEqual(url.hostname, HOST)
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            connection.request(method, url.path, headers={'Host': HOST, **(headers or {})})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def assert_private_logs(self, receipt):
        token = urlsplit(receipt.url).path.rsplit('/', 1)[-1]
        self.assertNotIn(token, self.logs.getvalue())
        self.assertNotIn(receipt.url, self.logs.getvalue())

    def test_factory_receipt_serves_exact_jpeg_and_head_without_token_logs(self):
        receipt = self.stage()
        status, headers, body = self.request(receipt)
        self.assertEqual((status, body), (200, JPEG))
        self.assertEqual(headers['Content-Type'], 'image/jpeg')
        self.assertEqual(headers['Content-Length'], str(len(JPEG)))
        status, head_headers, body = self.request(receipt, 'HEAD')
        self.assertEqual((status, body), (200, b''))
        self.assertEqual(head_headers, headers)
        self.assert_private_logs(receipt)

    def test_factory_mp4_receipt_serves_exact_byte_range(self):
        receipt = self.stage(VIDEO, 'video/mp4')
        status, headers, body = self.request(receipt, headers={'Range': 'bytes=4-15'})
        self.assertEqual((status, body), (206, VIDEO[4:16]))
        self.assertEqual(headers['Content-Range'], f'bytes 4-15/{len(VIDEO)}')
        self.assertEqual(headers['Content-Length'], '12')
        self.assertEqual(headers['Content-Type'], 'video/mp4')
        self.assert_private_logs(receipt)

    def test_current_review_and_serving_stop_fail_closed(self):
        receipt = self.stage()
        self.review = False
        self.assertEqual(self.request(receipt)[::2], (404, b''))
        self.review = True
        self.serving = False
        self.assertEqual(self.request(receipt)[::2], (404, b''))
        self.assert_private_logs(receipt)

    def test_revoked_lease_is_unavailable(self):
        receipt = self.stage()
        token = urlsplit(receipt.url).path.rsplit('/', 1)[-1]
        metadata = self.store.lookup(token, now=NOW)
        self.assertTrue(self.store.revoke(metadata['lease_id'], now=NOW))
        self.assertEqual(self.request(receipt)[::2], (404, b''))
        self.assert_private_logs(receipt)

    def test_expired_lease_is_unavailable_at_fixed_server_time(self):
        receipt = self.stage(issued_at=NOW - timedelta(hours=2))
        self.assertEqual(self.request(receipt)[::2], (404, b''))
        self.assert_private_logs(receipt)
