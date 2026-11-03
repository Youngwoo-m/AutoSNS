"""문맥별 동적 factory와 opt-in 전달 조립을 네트워크 없이 확인한다."""
from pathlib import Path
import tempfile
import unittest

from common.operations.media_leases import MediaLeaseStore
from common.operations.models import ContractError
from common.publishers.instagram_media_runtime import LeaseInstagramMediaFactory, assemble_media_delivery
from tests.publishers.test_instagram_media_sources import NOW, JPEG, context, prepared, metadata


class InstagramMediaRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'workspace'
        self.store = MediaLeaseStore(self.root / 'media-leases')
        self.loads = []
        self.binds = []
        self.allowed = {'write': True, 'review': True, 'serve': True}

    def loader(self, cid, revision, aid):
        self.loads.append((cid, revision, aid))
        return metadata(aid), JPEG

    def factory(self, **kwargs):
        args = dict(public_host='media.example.com', clock=lambda: NOW, write_guard=lambda *a: self.allowed['write'])
        args.update(kwargs)
        return LeaseInstagramMediaFactory(self.loader, self.store, **args)

    def assemble(self, **kwargs):
        owner = self
        class Content:
            read_asset = staticmethod(owner.loader)
        class Reviews:
            def authorize(self, ctx, p):
                return owner.allowed['review']
        class Server:
            closed = False
            def server_close(self):
                self.closed = True
        def bind(store, **options):
            self.binds.append((store, options))
            return Server()
        args = dict(workspace_root=self.root, content_store=Content(), reviews=Reviews(),
                    serving_allowed=lambda: self.allowed['serve'], write_guard=lambda *a: self.allowed['write'],
                    public_host='media.example.com', clock=lambda: NOW, server_factory=bind)
        args.update(kwargs)
        return assemble_media_delivery(**args)

    def test_default_inert_constructor_and_assembly_deny_without_callbacks(self):
        factory = self.factory(write_guard=None)
        with self.assertRaises(ContractError):
            factory.prepare(context(), prepared())
        assembly = self.assemble()
        self.assertIsNone(assembly.server)
        self.assertFalse(self.root.exists())
        self.assertEqual(self.binds, [])
        self.assertEqual(self.loads, [])
        with self.assertRaises(ContractError):
            assembly.factory.prepare(context(), prepared())
        self.assertFalse(assembly.authority({}))
        self.assertNotIn(str(self.root), repr(assembly))
        self.assertNotIn(str(self.root), repr(factory))

    def test_dynamic_contexts_cross_owner_remain_separate_and_preserve_order(self):
        self.store.initialize()
        factory = self.factory()
        first = context()
        second = context(content_id='another-content', owner_account_id='dept', destination_account_id='personal', connection_id='personal.instagram')
        receipts = []
        for ctx in (first, second):
            current = factory.prepare(ctx, prepared(ctx))
            receipts.append(current)
            self.assertEqual([r.position for r in current], [0, 1])
            self.assertEqual([r.asset_id for r in current], ['image-1', 'image-2'])
            for receipt in current:
                self.assertEqual(receipt.context_hash, ctx.context_hash)
                self.assertEqual(receipt.owner_account_id, ctx.owner_account_id)
                row = self.store.lookup(receipt.url.rsplit('/', 1)[-1], now=NOW)
                self.assertEqual(row['authority']['context']['content_id'], ctx.content_id)
                self.assertEqual(row['request']['asset_sha256'], metadata('image-1')['sha256'])
        self.assertNotEqual(receipts[0][0].url, receipts[1][0].url)
        self.assertEqual(factory.prepare(first, prepared(first)), receipts[0])
        self.assertEqual({r[0] for r in self.loads}, {'content-1', 'another-content'})

    def test_current_guard_rejects_before_loading_and_factory_never_initializes(self):
        self.allowed['write'] = False
        with self.assertRaises(ContractError):
            self.factory().prepare(context(), prepared())
        self.assertEqual(self.loads, [])
        self.assertFalse(self.root.exists())
        self.allowed['write'] = True
        with self.assertRaises(ContractError):
            self.factory().prepare(context(), prepared())
        self.assertFalse(self.root.exists())

    def test_enabled_assembly_composes_review_stop_and_write_guards(self):
        assembly = self.assemble(enabled=True, port=8123)
        self.assertTrue((self.root / 'media-leases').exists())
        self.assertEqual(len(self.binds), 1)
        options = self.binds[0][1]
        self.assertEqual(options['host'], '127.0.0.1')
        self.assertEqual(options['expected_host'], 'media.example.com')
        self.assertEqual(options['port'], 8123)
        ctx = context()
        receipts = assembly.factory.prepare(ctx, prepared(ctx))
        row = assembly.store.lookup(receipts[0].url.rsplit('/', 1)[-1], now=NOW)
        self.assertTrue(assembly.authority(row))
        for guard in self.allowed:
            self.allowed[guard] = False
            self.loads.clear()
            with self.assertRaises(ContractError):
                assembly.factory.prepare(ctx, prepared(ctx))
            self.assertEqual(self.loads, [])
            if guard == 'write':
                self.assertTrue(assembly.authority(row))
            if guard == 'review':
                self.assertFalse(assembly.authority(row))
            if guard == 'serve':
                self.assertFalse(options['serving_allowed']())
            self.allowed[guard] = True
        assembly.close()
        self.assertTrue(assembly.server.closed)

    def test_enabled_requires_all_guards_before_initializing_or_binding(self):
        for options in (dict(write_guard=None), dict(reviews=object()), dict(serving_allowed=None), dict(port=True)):
            with self.subTest(options=options):
                with self.assertRaises(ContractError):
                    self.assemble(enabled=True, **options)
                self.assertFalse(self.root.exists())
                self.assertEqual(self.binds, [])

    def test_bind_error_is_safe_and_never_starts_or_stages(self):
        def broken(*a, **k):
            raise OSError('private-root-or-config')
        with self.assertRaises(ContractError) as error:
            self.assemble(enabled=True, server_factory=broken)
        self.assertNotIn('private-root-or-config', str(error.exception))
        self.assertEqual(self.loads, [])
