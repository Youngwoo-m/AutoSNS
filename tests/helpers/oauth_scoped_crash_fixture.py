"""Test-only durable ScopedRawBackend and Pipe crash checkpoints.

Use fake bytes inside a TemporaryDirectory(prefix='oauth-crash-fixture-').
This raw I/O double proves no ownership, reads no journal, and grants no
recovery/delete authority. Never wire it into production CLI or native I/O.
Each call closes its SQLite connection before returning, so callers may kill
an independent process immediately after a committed boundary and reopen.
"""
import os
import sqlite3
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol

from common.operations.credential_backend import CredentialError


class _Address(Protocol):
    service: str
    account: str


class DurableScopedRawBackend:
    """Create-only fake bytes; an explicit caller-owned temp fixture is required."""

    def __init__(self, path: Path):
        path = Path(path)
        temporary_root = Path(tempfile.gettempdir()).resolve()
        parent = path.parent.resolve(strict=True)
        if (not parent.is_relative_to(temporary_root)
                or not any(part.startswith('oauth-crash-fixture-')
                           for part in parent.relative_to(temporary_root).parts)
                or path.is_symlink()):
            raise ValueError('temporary_fixture_path_required')
        self._path = parent / path.name
        fd = os.open(self._path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError('temporary_fixture_regular_file_required')
        finally:
            os.close(fd)
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS fake_items ('
                       'service TEXT NOT NULL, account TEXT NOT NULL, payload BLOB NOT NULL, '
                       'PRIMARY KEY(service, account))')
            db.execute('CREATE TABLE IF NOT EXISTS fake_faults ('
                       'operation TEXT PRIMARY KEY, code TEXT NOT NULL)')

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self._path, timeout=5)
        try:
            db.execute('PRAGMA synchronous=FULL')
            with db:
                yield db
        except sqlite3.Error:
            raise CredentialError('credential_unavailable') from None
        finally:
            db.close()

    @staticmethod
    def _key(address: _Address):
        service, account = address.service, address.account
        if not isinstance(service, str) or not service or not isinstance(account, str) or not account:
            raise CredentialError('credential_invalid_ref')
        return service, account

    @staticmethod
    def _check_fault(db, operation):
        row = db.execute('SELECT code FROM fake_faults WHERE operation=?', (operation,)).fetchone()
        if row:
            raise CredentialError(row[0])

    def set_fault(self, operation: str, code: str | None):
        """Persist deterministic failures so spawned/reopened callers see them."""
        if operation not in ('add', 'copy', 'delete') or code not in (
                None, 'credential_locked', 'credential_denied', 'credential_unavailable'):
            raise ValueError('unsupported_fixture_fault')
        with self._db() as db:
            if code is None:
                db.execute('DELETE FROM fake_faults WHERE operation=?', (operation,))
            else:
                db.execute('INSERT OR REPLACE INTO fake_faults VALUES (?, ?)', (operation, code))

    def add(self, address: _Address, payload: bytes) -> None:
        key = self._key(address)
        if not isinstance(payload, bytes):
            raise CredentialError('credential_invalid_secret')
        with self._db() as db:
            self._check_fault(db, 'add')
            try:
                db.execute('INSERT INTO fake_items VALUES (?, ?, ?)', (*key, payload))
            except sqlite3.IntegrityError:
                raise CredentialError('credential_duplicate') from None

    def copy(self, address: _Address) -> bytes:
        key = self._key(address)
        with self._db() as db:
            self._check_fault(db, 'copy')
            row = db.execute('SELECT payload FROM fake_items WHERE service=? AND account=?', key).fetchone()
            if row is None:
                raise CredentialError('credential_not_found')
            return bytes(row[0])

    def delete(self, address: _Address) -> None:
        key = self._key(address)
        with self._db() as db:
            self._check_fault(db, 'delete')
            result = db.execute('DELETE FROM fake_items WHERE service=? AND account=?', key)
            if result.rowcount != 1:
                raise CredentialError('credential_not_found')


def crash_checkpoint(pipe, name: str, *, timeout: float = 15) -> None:
    """Send only a public boundary label, then await ACK or external SIGKILL.

    The caller closes/terminates and joins its own child in a finally block.
    No sleep, exception cleanup, journal mutation or automatic recovery occurs.
    """
    if not isinstance(name, str) or not name or len(name) > 80 or not all(
            ch.isascii() and (ch.isalnum() or ch in '_-') for ch in name):
        raise ValueError('invalid_fixture_checkpoint')
    pipe.send(name)
    if not pipe.poll(timeout):
        raise TimeoutError('fixture_checkpoint_ack_timeout')
    if pipe.recv() != 'ACK':
        raise ValueError('invalid_fixture_checkpoint_ack')
