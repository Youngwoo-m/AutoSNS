import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest.mock import patch

from common.operations.credential_backend import CredentialError


class OAuthWorkspaceTests(unittest.TestCase):
    def setUp(self):
        try:
            self.workspace = importlib.import_module('common.operations.oauth_workspace')
        except ModuleNotFoundError:
            self.fail('OAuth workspace foundation is not implemented')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'oauth'

    def marker(self, root=None):
        return (root or self.root) / self.workspace.OWNER_MARKER_NAME

    def test_constructor_and_owner_load_never_create_marker(self):
        with self.assertRaises(CredentialError):
            self.workspace.load_workspace_owner(self.root)
        self.assertFalse(self.root.exists())
        self.root.mkdir(mode=0o700)
        with self.assertRaises(CredentialError):
            self.workspace.load_workspace_owner(self.root)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_explicit_initialization_is_private_durable_and_idempotent(self):
        with patch('ctypes.CDLL', side_effect=AssertionError('native access forbidden')):
            context = self.workspace.initialize_workspace_owner(self.root)
            before = self.marker().read_bytes()
            again = self.workspace.initialize_workspace_owner(self.root)
        self.assertEqual(context.owner, again.owner)
        self.assertEqual(before, self.marker().read_bytes())
        self.assertEqual(context.root, self.root.resolve())
        self.assertEqual(context.owner.root_binding,
                         hashlib.sha256(os.fsencode(self.root.resolve())).hexdigest())
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.marker().stat().st_mode), 0o600)
        self.assertEqual(len(context.key_provider.get_key()), 32)
        for value in (context, context.owner, context.key_provider):
            self.assertNotIn(context.key_provider.get_key().hex(), repr(value))
            self.assertNotIn(before.decode(), repr(value))
        self.assertEqual(set(p.name for p in self.root.iterdir()),
                         {self.workspace.OWNER_MARKER_NAME})

    def test_copied_marker_root_binding_is_rejected(self):
        self.workspace.initialize_workspace_owner(self.root)
        other = Path(self.temp.name) / 'copied'
        other.mkdir(mode=0o700)
        shutil.copyfile(self.marker(), self.marker(other))
        self.marker(other).chmod(0o600)
        before = self.marker(other).read_bytes()
        for load in (self.workspace.load_workspace_owner,
                     self.workspace.initialize_workspace_owner):
            with self.assertRaises(CredentialError):
                load(other)
        self.assertEqual(self.marker(other).read_bytes(), before)

    def test_invalid_marker_formats_permissions_and_symlinks_are_preserved(self):
        self.workspace.initialize_workspace_owner(self.root)
        original = self.marker().read_bytes()
        document = json.loads(original)
        malformed = [b'{', b'{}', original[:-1], b'\xff', b'[' * 1500 + b']' * 1500]
        for field, value in (('format_version', True), ('format_version', 2),
                             ('workspace_id', 'a' * 32), ('root_binding', 'f' * 64),
                             ('key', '00'), ('extra', 'private-error-sentinel')):
            changed = dict(document)
            changed[field] = value
            malformed.append(json.dumps(changed).encode())
        # Duplicate fields must not be silently normalized by the JSON parser.
        malformed.append(original[:-1] + b',"format_version":1}')
        for value in malformed:
            with self.subTest(case_length=len(value)):
                self.marker().write_bytes(value)
                with self.assertRaises(CredentialError) as caught:
                    self.workspace.load_workspace_owner(self.root)
                self.assertNotIn('private-error-sentinel', repr(caught.exception))
                self.assertEqual(self.marker().read_bytes(), value)
        self.marker().write_bytes(original)
        for path, bad, good in ((self.root, 0o755, 0o700),
                                 (self.marker(), 0o644, 0o600)):
            path.chmod(bad)
            with self.assertRaises(CredentialError):
                self.workspace.initialize_workspace_owner(self.root)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), bad)
            path.chmod(good)
        target = self.root / 'saved-marker'
        self.marker().rename(target)
        self.marker().symlink_to(target)
        with self.assertRaises(CredentialError):
            self.workspace.load_workspace_owner(self.root)
        self.assertTrue(self.marker().is_symlink())
        self.marker().unlink()
        target.rename(self.marker())
        alias = Path(self.temp.name) / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(CredentialError):
            self.workspace.load_workspace_owner(alias)

    def test_context_validation_rejects_replaced_key_and_missing_marker(self):
        context = self.workspace.initialize_workspace_owner(self.root)
        document = json.loads(self.marker().read_bytes())
        document['key'] = 'ab' * 32
        self.marker().write_text(json.dumps(document))
        with self.assertRaises(CredentialError):
            self.workspace.validate_workspace_context(context)
        self.marker().unlink()
        with self.assertRaises(CredentialError):
            self.workspace.validate_workspace_context(context)
        self.assertFalse(self.marker().exists())


if __name__ == '__main__':
    unittest.main()
