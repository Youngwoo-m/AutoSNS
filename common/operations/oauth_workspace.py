"""Explicit OAuth workspace owner initialization and read-only validation.

No constructor or ordinary load creates a marker. Writer/recovery locking is
implemented separately from this owner and key boundary.
"""
from contextlib import contextmanager
from dataclasses import dataclass, field
import errno
import fcntl
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import threading
import time
from typing import Protocol
import uuid

from .credential_backend import CredentialError
from .oauth_stage_models import WorkspaceOwner


OWNER_MARKER_NAME = '.oauth-workspace-owner.json'
_MARKER_FIELDS = {'format_version', 'workspace_id', 'root_binding', 'key'}
_MARKER_LIMIT = 4096


class WorkspaceError(CredentialError):
    """Only fixed public codes, never paths or marker content."""


class WorkspaceKeyProvider(Protocol):
    def get_key(self) -> bytes: ...


@dataclass(frozen=True, repr=False)
class _MarkerKeyProvider:
    _key: bytes

    def get_key(self) -> bytes:
        return self._key

    def __repr__(self):
        return 'WorkspaceKeyProvider(<private>)'


@dataclass(frozen=True, repr=False)
class OAuthWorkspaceContext:
    root: Path
    owner: WorkspaceOwner
    key_provider: WorkspaceKeyProvider
    _created_pid: int = field(default_factory=os.getpid, init=False, compare=False)

    def __repr__(self):
        return 'OAuthWorkspaceContext(<private>)'


def _root_fd(root, *, initialize=False):
    try:
        supplied = Path(root)
        if supplied.is_symlink():
            raise WorkspaceError('oauth_workspace_invalid_root')
        if initialize:
            try:
                supplied.mkdir(mode=0o700)
            except FileExistsError:
                pass
        canonical = supplied.resolve(strict=True)
        fd = os.open(canonical, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except WorkspaceError:
        raise
    except (OSError, ValueError, TypeError, RuntimeError):
        raise WorkspaceError('oauth_workspace_unavailable') from None
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700:
        os.close(fd)
        raise WorkspaceError('oauth_workspace_invalid_permissions')
    return canonical, fd


def _unique_fields(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate_field')
        value[key] = item
    return value


def _binding(root):
    return hashlib.sha256(os.fsencode(root)).hexdigest()


def _load_marker(root, root_fd):
    try:
        fd = os.open(OWNER_MARKER_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root_fd)
    except FileNotFoundError:
        raise WorkspaceError('oauth_workspace_owner_missing') from None
    except OSError:
        raise WorkspaceError('oauth_workspace_owner_unavailable') from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
            raise WorkspaceError('oauth_workspace_invalid_permissions')
        with os.fdopen(fd, 'rb', closefd=False) as source:
            data = source.read(_MARKER_LIMIT + 1)
        if len(data) > _MARKER_LIMIT:
            raise WorkspaceError('oauth_workspace_invalid_marker')
        try:
            value = json.loads(data, object_pairs_hook=_unique_fields)
            if type(value) is not dict or set(value) != _MARKER_FIELDS:
                raise ValueError('invalid_fields')
            owner = WorkspaceOwner(value['workspace_id'], value['root_binding'], value['format_version'])
            if type(value['key']) is not str or not re.fullmatch(r'[0-9a-f]{64}', value['key']):
                raise ValueError('invalid_key')
            key = bytes.fromhex(value['key'])
        except (ValueError, TypeError, CredentialError):
            raise WorkspaceError('oauth_workspace_invalid_marker') from None
        if owner.root_binding != _binding(root):
            raise WorkspaceError('oauth_workspace_root_mismatch')
        return OAuthWorkspaceContext(root, owner, _MarkerKeyProvider(key))
    except OSError:
        raise WorkspaceError('oauth_workspace_owner_unavailable') from None
    finally:
        os.close(fd)


def load_workspace_owner(root) -> OAuthWorkspaceContext:
    canonical, root_fd = _root_fd(root)
    try:
        return _load_marker(canonical, root_fd)
    finally:
        os.close(root_fd)


def initialize_workspace_owner(root) -> OAuthWorkspaceContext:
    canonical, root_fd = _root_fd(root, initialize=True)
    try:
        try:
            fd = os.open(OWNER_MARKER_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=root_fd)
        except FileExistsError:
            return _load_marker(canonical, root_fd)
        except OSError:
            raise WorkspaceError('oauth_workspace_owner_unavailable') from None
        try:
            value = dict(format_version=1, workspace_id=uuid.uuid4().hex,
                         root_binding=_binding(canonical), key=secrets.token_bytes(32).hex())
            data = json.dumps(value, separators=(',', ':'), allow_nan=False).encode('utf-8')
            with os.fdopen(fd, 'wb', closefd=False) as target:
                target.write(data)
                target.flush()
                os.fsync(fd)
            os.fsync(root_fd)
        except OSError:
            # Partial initialization remains visible and invalid; never overwrite it.
            raise WorkspaceError('oauth_workspace_owner_unavailable') from None
        finally:
            os.close(fd)
        return _load_marker(canonical, root_fd)
    finally:
        os.close(root_fd)


def validate_workspace_context(context: OAuthWorkspaceContext) -> OAuthWorkspaceContext:
    """Revalidate current disk ownership and key before any owned vault access."""
    if type(context) is not OAuthWorkspaceContext or type(context.owner) is not WorkspaceOwner:
        raise WorkspaceError('oauth_workspace_invalid_context')
    current = load_workspace_owner(context.root)
    try:
        key = context.key_provider.get_key()
        valid = (context.root == current.root and context.owner == current.owner
                 and type(key) is bytes and len(key) == 32
                 and hmac.compare_digest(key, current.key_provider.get_key()))
    except Exception:
        raise WorkspaceError('oauth_workspace_invalid_context') from None
    if not valid:
        raise WorkspaceError('oauth_workspace_owner_mismatch')
    return current


# Every writer in a canonical root shares both levels of exclusion. Registry
# entries intentionally survive individual context/service lifetimes.
_GUARD_LOCK_NAME = '.oauth-workspace.lock'
_guard_registry_lock = threading.Lock()
_guard_locks = {}
_guard_tokens = {}
_guard_local = threading.local()
_guard_fds = set()
_guard_fd_lock = threading.Lock()


@dataclass(repr=False)
class _HeldWriteGuard:
    context: OAuthWorkspaceContext
    pid: int
    thread_id: int
    token: object


def _prepare_guards_for_fork():
    # Only the fd-lifetime lock is acquired here: never wait for a workspace
    # RLock or the registry while forking. Writers hold it only across open +
    # registration or unregister + close, never while waiting for flock.
    _guard_fd_lock.acquire()


def _resume_guards_after_fork():
    _guard_fd_lock.release()


def _reset_guards_after_fork():
    global _guard_registry_lock, _guard_locks, _guard_tokens, _guard_local, _guard_fds, _guard_fd_lock
    # A fork inherits open-file descriptions, so never LOCK_UN here: that would
    # unlock the parent's flock. Closing only the child's fd leaves it intact.
    for fd in _guard_fds:
        try:
            os.close(fd)
        except OSError:
            pass
    _guard_registry_lock = threading.Lock()
    _guard_locks = {}
    _guard_tokens = {}
    _guard_local = threading.local()
    _guard_fds = set()
    _guard_fd_lock = threading.Lock()


os.register_at_fork(before=_prepare_guards_for_fork,
                    after_in_parent=_resume_guards_after_fork,
                    after_in_child=_reset_guards_after_fork)


def _held_write_guard():
    held = getattr(_guard_local, 'held', None)
    if (held is None or held.pid != os.getpid()
            or held.thread_id != threading.get_ident()
            or _guard_tokens.get(held.token) is not held):
        return None
    return held


def _validate_guard_context(context):
    if (type(context) is not OAuthWorkspaceContext
            or context._created_pid != os.getpid()):
        raise WorkspaceError('oauth_workspace_invalid_context')
    return validate_workspace_context(context)


def require_oauth_write_guard(root, owner) -> OAuthWorkspaceContext:
    """Return this thread's live guard, revalidating ownership before a write.

    This read-only check never creates the lock or marker. The guard must wrap
    the complete writer operation, with database transactions kept inside it.
    """
    held = _held_write_guard()
    if held is None:
        raise WorkspaceError('oauth_guard_required')
    try:
        canonical = Path(root).resolve(strict=True)
    except (OSError, ValueError, TypeError, RuntimeError):
        raise WorkspaceError('oauth_guard_required') from None
    if canonical != held.context.root or owner != held.context.owner:
        raise WorkspaceError('oauth_guard_required')
    _validate_guard_context(held.context)
    return held.context


def _open_guard_file(root_fd):
    try:
        fd = os.open(_GUARD_LOCK_NAME, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                     0o600, dir_fd=root_fd)
    except OSError:
        raise WorkspaceError('oauth_workspace_lock_unavailable') from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
            raise WorkspaceError('oauth_workspace_invalid_permissions')
        return fd
    except BaseException:
        os.close(fd)
        raise


@contextmanager
def oauth_write_guard(context: OAuthWorkspaceContext, timeout: float = 10):
    """Serialize explicit writers by root with one monotonic timeout budget.

    Equivalent contexts may reenter on the owning thread without opening a
    second flock descriptor. Forked children must explicitly reload context.
    """
    if type(timeout) not in (int, float):
        raise WorkspaceError('oauth_workspace_invalid_timeout')
    try:
        timeout = float(timeout)
    except (OverflowError, ValueError):
        raise WorkspaceError('oauth_workspace_invalid_timeout') from None
    if not math.isfinite(timeout) or timeout < 0:
        raise WorkspaceError('oauth_workspace_invalid_timeout')
    deadline = time.monotonic() + timeout
    current = _validate_guard_context(context)
    held = _held_write_guard()
    if held is not None:
        prior = _validate_guard_context(held.context)
        if (prior.root != current.root or prior.owner != current.owner
                or not hmac.compare_digest(prior.key_provider.get_key(),
                                           current.key_provider.get_key())):
            raise WorkspaceError('oauth_workspace_invalid_context')
        yield context
        return

    with _guard_registry_lock:
        local_lock = _guard_locks.setdefault(current.root, threading.RLock())
    remaining = max(0.0, deadline - time.monotonic())
    if not local_lock.acquire(timeout=min(remaining, threading.TIMEOUT_MAX)):
        raise WorkspaceError('oauth_workspace_busy')
    fd = None
    token = None
    pid = os.getpid()
    try:
        _validate_guard_context(context)
        _, root_fd = _root_fd(current.root)
        try:
            with _guard_fd_lock:
                fd = _open_guard_file(root_fd)
                _guard_fds.add(fd)
        finally:
            os.close(root_fd)
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as error:
                if error.errno not in (errno.EAGAIN, errno.EACCES, errno.EINTR):
                    raise WorkspaceError('oauth_workspace_lock_unavailable') from None
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise WorkspaceError('oauth_workspace_busy') from None
                threading.Event().wait(min(remaining, 0.05))
        _validate_guard_context(context)
        token = object()
        held = _HeldWriteGuard(context, pid, threading.get_ident(), token)
        _guard_tokens[token] = held
        _guard_local.held = held
        yield context
    finally:
        # A child's inherited generator must not release the parent's lock or
        # a recycled descriptor. Its at-fork callback already closed child fds.
        if os.getpid() == pid:
            if token is not None:
                _guard_tokens.pop(token, None)
                _guard_local.held = None
            if fd is not None:
                with _guard_fd_lock:
                    _guard_fds.discard(fd)
                    os.close(fd)
            local_lock.release()
