"""실제 수동 검토와 비공개 임대의 결속. 외부 인증·발행·네트워크는 없다."""
from dataclasses import replace
from urllib.parse import urlsplit
import unittest
from unittest.mock import patch

from common.operations.media_leases import MediaLeaseStore
from common.operations.models import ContractError
from common.publishers.instagram_media_leases import BoundInstagramMediaStager, InstagramLeaseAuthorityGuard
from common.publishers.instagram_media_sources import InstagramMediaSourceFactory
from tests.publishers import test_instagram_review_integration as review_fixture


class InstagramLeaseReviewIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = review_fixture.InstagramReviewIntegrationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.network = patch('socket.socket', side_effect=AssertionError('외부 네트워크 금지'))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.store = MediaLeaseStore(self.fixture.root / 'private-media')
        self.store.initialize()
        self.plan, self.ctx, self.prepared = self.fixture.plan_context('carousel')
        self.permit = True
        self.write_stop = False
        self.serving_stop = False
        self.authority = InstagramLeaseAuthorityGuard(self.fixture.reviews.authorize)
        stager = BoundInstagramMediaStager(self.ctx, self.prepared, self.store,
            public_host='cdn.example.org', clock=lambda: self.fixture.now, write_guard=self.write_guard)
        self.factory = InstagramMediaSourceFactory(self.fixture.contents.read_asset,
            stager=stager, approval_guard=self.write_guard,
            allowed_hosts=('cdn.example.org',), clock=lambda: self.fixture.now)

    def write_guard(self, ctx, prepared):
        return self.permit and not self.write_stop and self.fixture.reviews.authorize(ctx, prepared)

    def stage(self):
        return self.factory.prepare(self.ctx, self.prepared)

    def fetch(self, receipt):
        metadata = self.store.lookup(urlsplit(receipt.url).path.rsplit('/', 1)[-1], now=self.fixture.now)
        # HTTP 경계의 별도 STOP과 현재 수동 검토를 합성한다. 소비된 permit은 재요구하지 않는다.
        if self.serving_stop or metadata is None or not self.authority(metadata):
            return None
        with self.store.open_payload(metadata['lease_id'], now=self.fixture.now) as payload:
            return payload.read()

    def test_approved_saved_plan_stages_exact_bytes_and_caption_without_consumed_permit(self):
        self.fixture.record(self.plan)
        before = self.fixture.contents.get(self.fixture.item['id'])
        receipts = self.stage()
        self.permit = False
        for receipt, asset in zip(receipts, self.prepared['assets']):
            expected = self.fixture.contents.read_asset(self.ctx.content_id, self.ctx.content_revision, asset['id'])[1]
            self.assertEqual(self.fetch(receipt), expected)
            metadata = self.store.lookup(urlsplit(receipt.url).path.rsplit('/', 1)[-1], now=self.fixture.now)
            self.assertEqual(metadata['authority']['context'], self.ctx.to_dict())
            self.assertEqual(metadata['authority']['prepared']['caption'], self.prepared['caption'])
        self.assertEqual([r.asset_id for r in receipts], self.fixture.ids)
        self.assertEqual(self.fixture.contents.get(self.fixture.item['id']), before)
        self.assertEqual(self.fixture.http, [])

    def test_real_review_revocation_blocks_existing_bytes(self):
        self.fixture.record(self.plan)
        receipts = self.stage()
        self.fixture.record(self.plan, 'revoked')
        for receipt in receipts:
            self.assertIsNone(self.fetch(receipt))

    def test_changed_head_revision_blocks_existing_bytes(self):
        self.fixture.record(self.plan)
        receipts = self.stage()
        self.fixture.contents.update(self.ctx.content_id, self.ctx.content_revision,
            dict(title='새 원고', kind='card', original='새 캡션'))
        for receipt in receipts:
            self.assertIsNone(self.fetch(receipt))

    def test_registry_revision_or_target_change_blocks_existing_bytes(self):
        self.fixture.record(self.plan)
        receipts = self.stage()
        original = self.fixture.registry
        for changed in (replace(original, revision='changed-registry'),
                replace(original, connections={**original.connections,
                    self.ctx.connection_id: replace(original.connections[self.ctx.connection_id], target_id='456')})):
            with self.subTest(registry=changed.revision):
                self.fixture.registry = changed
                for receipt in receipts:
                    self.assertIsNone(self.fetch(receipt))
        self.fixture.registry = original
        self.assertIsNotNone(self.fetch(receipts[0]))

    def test_unapproved_plan_creates_no_leases(self):
        with self.assertRaises(ContractError):
            self.stage()
        self.assertEqual(self.store.list_status(destination_account_id='dept', now=self.fixture.now), [])

    def test_write_permit_stop_and_separate_serving_stop(self):
        self.fixture.record(self.plan)
        self.permit = False
        with self.assertRaises(ContractError):
            self.stage()
        self.permit = True
        self.write_stop = True
        with self.assertRaises(ContractError):
            self.stage()
        self.assertEqual(self.store.list_status(destination_account_id='dept', now=self.fixture.now), [])
        self.write_stop = False
        receipts = self.stage()
        self.permit = False
        self.serving_stop = True
        self.assertIsNone(self.fetch(receipts[0]))
        self.serving_stop = False
        self.assertIsNotNone(self.fetch(receipts[0]))
