"""Explicit OAuth workspace owner initialization and read-only validation.

No constructor or ordinary load creates a marker. Writer/recovery locking is
implemented separately from this owner and key boundary.
"""
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
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
