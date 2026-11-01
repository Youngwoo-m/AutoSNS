import dataclasses
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from common.operations.credential_backend import CredentialError
from common.operations.keychain_backend import MacKeychainBackend
from common.operations.oauth_models import CredentialRef
from tests.operations.test_credential_backend import FakeBridge


class OAuthStageBackendTests(unittest.TestCase):
    def setUp(self):
        try:
            self.models = importlib.import_module('common.operations.oauth_stage_models')
            self.workspace = importlib.import_module('common.operations.oauth_workspace')
            self.backend = importlib.import_module('common.operations.oauth_stage_backend')
        except ModuleNotFoundError:
            self.fail('OAuth owned-stage foundation is not implemented')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'first'
        self.context = self.workspace.initialize_workspace_owner(self.root)
        self.ref = CredentialRef('autosns.oauth', 'personal', 'youtube', 'personal.youtube', 1, 'token')
        self.owned = self.models.OwnedCredentialRef(self.ref, self.context.owner.workspace_id,
                                                   self.context.owner.root_binding, 'stage-1')

    def adapters(self):
        return (self.backend.MemoryScopedRawBackend(),
                self.backend.KeychainScopedRawBackend(FakeBridge()))

    def test_constructor_and_owner_load_never_create_marker(self):
        bridge = FakeBridge()
        marker = self.root / self.workspace.OWNER_MARKER_NAME
        marker.unlink()
        with patch('ctypes.CDLL', side_effect=AssertionError('native forbidden')):
            raw = self.backend.KeychainScopedRawBackend(bridge)
            scoped = self.backend.OwnedStageBackend(self.context, raw)
        self.assertEqual(bridge.calls, [])
        self.assertFalse(marker.exists())
        with self.assertRaises(CredentialError):
            scoped.put_owned(self.owned, b'private-payload-sentinel')
        self.assertEqual(bridge.calls, [])
        self.assertFalse(marker.exists())

    def test_same_legacy_ref_different_workspaces_have_distinct_scoped_identity(self):
        other = self.workspace.initialize_workspace_owner(Path(self.temp.name) / 'second')
        second = self.models.OwnedCredentialRef(self.ref, other.owner.workspace_id,
                                                other.owner.root_binding, 'stage-1')
        for raw in self.adapters():
            first_backend = self.backend.OwnedStageBackend(self.context, raw)
            second_backend = self.backend.OwnedStageBackend(other, raw)
            first_backend.put_owned(self.owned, b'first-payload')
            second_backend.put_owned(second, b'second-payload')
            self.assertNotEqual(self.backend.scoped_address(self.owned), self.backend.scoped_address(second))
            first_backend.delete_owned(self.owned)
            self.assertEqual(second_backend.read_owned(second), b'second-payload')
            with self.assertRaises(CredentialError):
                first_backend.read_owned(second)

    def test_exact_address_binds_full_ref_owner_root_and_stage(self):
        address = self.backend.scoped_address(self.owned)
        parts = [self.owned.workspace_id, self.owned.root_binding, 'stage-1',
                 'autosns.oauth', 'personal', 'youtube', 'personal.youtube', 1, 'token']
        expected = hashlib.sha256(json.dumps(parts, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        self.assertEqual((address.service, address.account), ('autosns.oauth.stage.v1', expected))
        for field, value in (('stage_id', 'stage-2'), ('root_binding', 'ab' * 32)):
            changed = dataclasses.replace(self.owned, **{field: value})
            self.assertNotEqual(address, self.backend.scoped_address(changed))
        changed_ref = CredentialRef('autosns.oauth', 'personal', 'youtube', 'personal.youtube', 2, 'token')
        self.assertNotEqual(address, self.backend.scoped_address(dataclasses.replace(self.owned, ref=changed_ref)))

    def test_missing_marker_or_invalid_tag_never_deletes(self):
        for raw in self.adapters():
            scoped = self.backend.OwnedStageBackend(self.context, raw)
            scoped.put_owned(self.owned, b'private-payload-sentinel')
            address = self.backend.scoped_address(self.owned)
            envelope = raw.copy(address)
            marker = self.root / self.workspace.OWNER_MARKER_NAME
            marker_bytes = marker.read_bytes()
            marker.unlink()
            with self.assertRaises(CredentialError):
                scoped.delete_owned(self.owned)
            self.assertEqual(raw.copy(address), envelope)
            marker.write_bytes(marker_bytes)
            marker.chmod(0o600)
            raw.delete(address)
            corrupted = envelope[:-1] + bytes([envelope[-1] ^ 1])
            raw.add(address, corrupted)
            for operation in (scoped.read_owned, scoped.delete_owned):
                with self.assertRaises(CredentialError) as caught:
                    operation(self.owned)
                self.assertNotIn('private-payload-sentinel', repr(caught.exception))
            self.assertEqual(raw.copy(address), corrupted)

    def test_duplicate_put_does_not_adopt_or_delete_existing_item(self):
        for raw in self.adapters():
            scoped = self.backend.OwnedStageBackend(self.context, raw)
            address = self.backend.scoped_address(self.owned)
            raw.add(address, b'foreign-item-sentinel')
            with self.assertRaises(CredentialError) as caught:
                scoped.put_owned(self.owned, b'replacement-payload')
            self.assertEqual(caught.exception.code, 'credential_duplicate')
            self.assertEqual(raw.copy(address), b'foreign-item-sentinel')
            with self.assertRaises(CredentialError):
                scoped.delete_owned(self.owned)
            self.assertEqual(raw.copy(address), b'foreign-item-sentinel')

    def test_legacy_item_is_never_auto_wrapped(self):
        bridge = FakeBridge()
        legacy = MacKeychainBackend(bridge)
        legacy.put(self.ref, b'legacy-item-sentinel')
        scoped = self.backend.OwnedStageBackend(self.context, self.backend.KeychainScopedRawBackend(bridge))
        for operation in (scoped.read_owned, scoped.delete_owned):
            with self.assertRaises(CredentialError):
                operation(self.ref)
            with self.assertRaises(CredentialError):
                operation(self.owned)
        self.assertEqual(legacy.get(self.ref), b'legacy-item-sentinel')
        self.assertEqual(len(bridge.items), 1)

    def test_envelope_cannot_be_replayed_under_another_address(self):
        for raw in self.adapters():
            scoped = self.backend.OwnedStageBackend(self.context, raw)
            scoped.put_owned(self.owned, b'private-payload-sentinel')
            other = dataclasses.replace(self.owned, stage_id='another-stage')
            raw.add(self.backend.scoped_address(other), raw.copy(self.backend.scoped_address(self.owned)))
            with self.assertRaises(CredentialError):
                scoped.delete_owned(other)
            self.assertEqual(scoped.read_owned(self.owned), b'private-payload-sentinel')

    def test_replaced_marker_key_rejects_existing_context_before_raw_access(self):
        bridge = FakeBridge()
        raw = self.backend.KeychainScopedRawBackend(bridge)
        scoped = self.backend.OwnedStageBackend(self.context, raw)
        scoped.put_owned(self.owned, b'private-payload-sentinel')
        before = dict(bridge.items)
        marker = self.root / self.workspace.OWNER_MARKER_NAME
        document = json.loads(marker.read_bytes())
        document['key'] = 'ab' * 32
        marker.write_text(json.dumps(document))
        bridge.calls.clear()
        for operation in (scoped.read_owned, scoped.delete_owned):
            with self.assertRaises(CredentialError):
                operation(self.owned)
        self.assertEqual(bridge.calls, [])
        self.assertEqual(bridge.items, before)

    def test_private_reprs_and_errors_never_include_secret_material(self):
        raw = self.backend.MemoryScopedRawBackend()
        scoped = self.backend.OwnedStageBackend(self.context, raw)
        scoped.put_owned(self.owned, b'private-payload-sentinel')
        envelope = raw.copy(self.backend.scoped_address(self.owned))
        for value in (self.owned, raw, scoped, self.backend.scoped_address(self.owned)):
            self.assertNotIn('private-payload-sentinel', repr(value))
            self.assertNotIn(self.owned.stage_id, repr(value))
            self.assertNotIn(envelope.hex(), repr(value))
        self.assertEqual(self.owned.to_dict(public=True), {})
        bridge = FakeBridge()
        def failed_copy(*args):
            raise RuntimeError('private-payload-sentinel')
        bridge.copy = failed_copy
        with self.assertRaises(CredentialError) as caught:
            self.backend.KeychainScopedRawBackend(bridge).copy(self.backend.scoped_address(self.owned))
        self.assertNotIn('private-payload-sentinel', repr(caught.exception))
        self.assertIsNone(caught.exception.__cause__)

    def test_native_error_codes_and_malformed_replies_are_sanitized(self):
        address = self.backend.scoped_address(self.owned)
        bridge = FakeBridge()
        raw = self.backend.KeychainScopedRawBackend(bridge)
        raw.add(address, b'original-value')
        for status, code in ((-25300, 'credential_not_found'), (-25308, 'credential_locked'),
                             (-25293, 'credential_denied'), (-128, 'credential_denied'),
                             (-999, 'credential_unavailable')):
            bridge.status = status
            for operation in (lambda: raw.add(address, b'replacement'),
                              lambda: raw.copy(address), lambda: raw.delete(address)):
                with self.assertRaises(CredentialError) as caught:
                    operation()
                self.assertEqual(caught.exception.code, code)
        bridge.status = 0
        self.assertEqual(raw.copy(address), b'original-value')
        for malformed in (None, False, {'private-payload-sentinel': True}, 'private-payload-sentinel'):
            bridge.add = lambda *args: malformed
            bridge.copy = lambda *args: (malformed, b'private-payload-sentinel')
            bridge.delete = lambda *args: malformed
            for operation in (lambda: raw.add(address, b'replacement'),
                              lambda: raw.copy(address), lambda: raw.delete(address)):
                with self.assertRaises(CredentialError) as caught:
                    operation()
                self.assertEqual(caught.exception.code, 'credential_unavailable')
                self.assertNotIn('private-payload-sentinel', repr(caught.exception))

    def test_owned_operations_emit_no_secret_logs(self):
        raw = self.backend.MemoryScopedRawBackend()
        scoped = self.backend.OwnedStageBackend(self.context, raw)
        with self.assertNoLogs(level='DEBUG'):
            scoped.put_owned(self.owned, b'private-payload-sentinel')
            self.assertEqual(scoped.read_owned(self.owned), b'private-payload-sentinel')
            with self.assertRaises(CredentialError):
                scoped.put_owned(self.owned, b'private-payload-sentinel')
            scoped.delete_owned(self.owned)
            with self.assertRaises(CredentialError):
                scoped.read_owned(self.owned)

    def test_strict_codec_preserves_owned_identity_and_legacy_namespace(self):
        legacy = dict(namespace='autosns.oauth', account_id='personal', platform='youtube',
                      connection_id='personal.youtube', generation=1, kind='token')
        self.assertEqual(self.models.encode_stored_ref(self.ref), legacy)
        self.assertEqual(self.models.decode_stored_ref(legacy), self.ref)
        encoded = self.models.encode_stored_ref(self.owned)
        self.assertEqual(set(encoded), {'format', 'ref', 'workspace_id', 'root_binding', 'stage_id'})
        decoded = self.models.decode_stored_ref(encoded)
        self.assertEqual(decoded, self.owned)
        self.assertEqual(hash(decoded), hash(self.owned))
        self.assertNotEqual(decoded, self.ref)
        self.assertEqual(self.models.logical_ref(decoded), self.ref)
        self.assertEqual(self.models.logical_ref(self.ref), self.ref)
        invalid = [None, [], True, {}, {**legacy, 'extra': 'private-payload-sentinel'},
                   {**legacy, 'namespace': 'autosns.oauth.stage.v1'},
                   {**legacy, 'generation': True}, {**legacy, 'platform': 'a.b'},
                   {**encoded, 'format': 'owned_v2'}, {**encoded, 'extra': 1},
                   {**encoded, 'stage_id': ''}, {**encoded, 'root_binding': 'short'},
                   {**encoded, 'workspace_id': 'a' * 32}, {**encoded, 'ref': encoded}]
        for item in invalid:
            with self.assertRaises(CredentialError):
                self.models.decode_stored_ref(item)


if __name__ == '__main__':
    unittest.main()
