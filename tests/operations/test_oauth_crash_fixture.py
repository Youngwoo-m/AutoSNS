"""Durable fake I/O and real process-death checks; no native credentials."""
import multiprocessing
import signal
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from common.operations.credential_backend import CredentialError
from tests.helpers.oauth_scoped_crash_fixture import (
    DurableScopedRawBackend, crash_checkpoint,
)


def _crash_worker(path, pipe, boundary):
    backend = DurableScopedRawBackend(Path(path))
    address = SimpleNamespace(service='fake.stage', account='fake.account')
    if boundary == 'before_add':
        crash_checkpoint(pipe, boundary)
    backend.add(address, b'fake-envelope-only')
    if boundary == 'after_add':
        crash_checkpoint(pipe, boundary)
    if boundary == 'before_delete':
        crash_checkpoint(pipe, boundary)
    backend.delete(address)
    crash_checkpoint(pipe, boundary)


def _ack_worker(pipe):
    crash_checkpoint(pipe, 'ready')
    pipe.send('continued')


class DurableScopedRawBackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='oauth-crash-fixture-')
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'fake-vault.sqlite3'
        self.backend = DurableScopedRawBackend(self.path)
        self.address = SimpleNamespace(service='fake.stage', account='fake.account')

    def assert_code(self, code, fn, *args):
        with self.assertRaises(CredentialError) as caught:
            fn(*args)
        self.assertEqual(caught.exception.code, code)

    def test_create_only_and_exact_address_survive_reopen(self):
        self.backend.add(self.address, b'fake-first')
        self.assert_code('credential_duplicate', self.backend.add, self.address, b'fake-second')
        reopened = DurableScopedRawBackend(self.path)
        self.assertEqual(reopened.copy(self.address), b'fake-first')
        other = SimpleNamespace(service='fake.other', account='fake.account')
        self.assert_code('credential_not_found', reopened.copy, other)
        self.assert_code('credential_not_found', reopened.delete, other)
        self.assertEqual(reopened.copy(self.address), b'fake-first')
        reopened.delete(self.address)
        self.assert_code('credential_not_found', self.backend.copy, self.address)
        self.assert_code('credential_not_found', self.backend.delete, self.address)

    def test_locked_denied_unavailable_preserve_bytes_across_reopen(self):
        self.backend.add(self.address, b'fake-preserved')
        for operation in ('add', 'copy', 'delete'):
            for code in ('credential_locked', 'credential_denied', 'credential_unavailable'):
                with self.subTest(operation=operation, code=code):
                    self.backend.set_fault(operation, code)
                    reopened = DurableScopedRawBackend(self.path)
                    args = (self.address, b'fake-replacement') if operation == 'add' else (self.address,)
                    self.assert_code(code, getattr(reopened, operation), *args)
                    self.backend.set_fault(operation, None)
                    self.assertEqual(reopened.copy(self.address), b'fake-preserved')

    def test_rejects_operational_path_and_symlink_without_touching_target(self):
        with self.assertRaises(ValueError):
            DurableScopedRawBackend(Path.cwd() / 'do-not-create.sqlite3')
        target = Path(self.tmp.name) / 'untouched'
        target.write_bytes(b'fake-sentinel')
        link = Path(self.tmp.name) / 'linked.sqlite3'
        link.symlink_to(target)
        with self.assertRaises(ValueError):
            DurableScopedRawBackend(link)
        self.assertEqual(target.read_bytes(), b'fake-sentinel')

    def test_rejects_bad_payload_and_unknown_fault(self):
        self.assert_code('credential_invalid_secret', self.backend.add, self.address, 'not-bytes')
        for operation, code in [('enumerate', 'credential_locked'), ('delete', 'invented')]:
            with self.assertRaises(ValueError):
                self.backend.set_fault(operation, code)

    def test_sigkill_at_committed_boundaries_then_reopen(self):
        ctx = multiprocessing.get_context('spawn')
        for boundary, present in [('before_add', False), ('after_add', True),
                                  ('before_delete', True), ('after_delete', False)]:
            with self.subTest(boundary=boundary):
                path = Path(self.tmp.name) / (boundary + '.sqlite3')
                DurableScopedRawBackend(path)
                parent, child = ctx.Pipe()
                process = ctx.Process(target=_crash_worker, args=(str(path), child, boundary))
                process.start()
                child.close()
                try:
                    self.assertTrue(parent.poll(15), 'child did not reach boundary')
                    self.assertEqual(parent.recv(), boundary)
                    process.kill()
                    process.join(15)
                    self.assertFalse(process.is_alive())
                    self.assertEqual(process.exitcode, -signal.SIGKILL)
                finally:
                    if process.is_alive():
                        process.kill()
                        process.join(15)
                    parent.close()
                    process.close()
                reopened = DurableScopedRawBackend(path)
                if present:
                    self.assertEqual(reopened.copy(self.address), b'fake-envelope-only')
                else:
                    self.assert_code('credential_not_found', reopened.copy, self.address)

    def test_checkpoint_can_continue_only_after_explicit_ack(self):
        ctx = multiprocessing.get_context('spawn')
        parent, child = ctx.Pipe()
        process = ctx.Process(target=_ack_worker, args=(child,))
        process.start()
        child.close()
        try:
            self.assertTrue(parent.poll(15))
            self.assertEqual(parent.recv(), 'ready')
            parent.send('ACK')
            self.assertTrue(parent.poll(15))
            self.assertEqual(parent.recv(), 'continued')
            process.join(15)
            self.assertEqual(process.exitcode, 0)
        finally:
            if process.is_alive():
                process.kill()
                process.join(15)
            parent.close()
            process.close()
