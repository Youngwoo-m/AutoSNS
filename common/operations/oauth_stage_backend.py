"""Exact scoped stage addresses and authenticated, create-only secret storage.

These are ownership primitives. Recovery must additionally prove journal origin,
unused operation outcome and absence from the complete protected reference graph.
No native bridge is constructed here; callers explicitly inject an adapter.
"""
from dataclasses import dataclass
import hashlib
import hmac
import json
import re
import threading
from typing import Protocol

from .credential_backend import CredentialError, validate_ref
from .keychain_backend import _check
from .oauth_stage_models import OwnedCredentialRef, logical_ref
from .oauth_workspace import validate_workspace_context


_SERVICE = 'autosns.oauth.stage.v1'
_MAGIC = b'AutoSNSOwnedStage\x00\x01'
_TAG_SIZE = hashlib.sha256().digest_size


@dataclass(frozen=True, repr=False)
class ScopedCredentialAddress:
    service: str
    account: str

    def __repr__(self):
        return 'ScopedCredentialAddress(<private>)'


def _validate_address(address):
    if (type(address) is not ScopedCredentialAddress or address.service != _SERVICE
            or type(address.account) is not str or not re.fullmatch(r'[0-9a-f]{64}', address.account)):
        raise CredentialError('credential_invalid_ref')


def _check_status(status):
    if type(status) is not int:
        raise CredentialError('credential_unavailable')
    _check(status)


def _identity(owned_ref):
    if type(owned_ref) is not OwnedCredentialRef:
        raise CredentialError('credential_invalid_ref')
    ref = logical_ref(owned_ref)
    parts = (owned_ref.workspace_id, owned_ref.root_binding, owned_ref.stage_id, *validate_ref(ref))
    return json.dumps(parts, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def scoped_address(owned_ref: OwnedCredentialRef) -> ScopedCredentialAddress:
    return ScopedCredentialAddress(_SERVICE, hashlib.sha256(_identity(owned_ref)).hexdigest())


class ScopedRawBackend(Protocol):
    def add(self, address: ScopedCredentialAddress, value: bytes) -> None: ...
    def copy(self, address: ScopedCredentialAddress) -> bytes: ...
    def delete(self, address: ScopedCredentialAddress) -> None: ...


class MemoryScopedRawBackend:
    def __init__(self):
        self._items = {}
        self._lock = threading.Lock()

    def add(self, address, value):
        _validate_address(address)
        if type(value) is not bytes:
            raise CredentialError('credential_invalid_secret')
        with self._lock:
            if address in self._items:
                raise CredentialError('credential_duplicate')
            self._items[address] = value

    def copy(self, address):
        _validate_address(address)
        with self._lock:
            if address not in self._items:
                raise CredentialError('credential_not_found')
            return self._items[address]

    def delete(self, address):
        _validate_address(address)
        with self._lock:
            if address not in self._items:
                raise CredentialError('credential_not_found')
            del self._items[address]


class KeychainScopedRawBackend:
    """Explicit bridge injection, with full service+account exact queries only."""
    def __init__(self, bridge):
        self._bridge = bridge

    def _call(self, method, address, *args):
        _validate_address(address)
        try:
            return getattr(self._bridge, method)(address.service, address.account, *args)
        except Exception:
            raise CredentialError('credential_unavailable') from None

    def add(self, address, value):
        if type(value) is not bytes:
            raise CredentialError('credential_invalid_secret')
        _check_status(self._call('add', address, value))

    def copy(self, address):
        result = self._call('copy', address)
        if type(result) is not tuple or len(result) != 2:
            raise CredentialError('credential_unavailable')
        status, value = result
        _check_status(status)
        if type(value) is not bytes:
            raise CredentialError('credential_unavailable')
        return value

    def delete(self, address):
        _check_status(self._call('delete', address))


class OwnedStageBackend:
    def __init__(self, context, raw_backend: ScopedRawBackend):
        self._context = context
        self._raw_backend = raw_backend

    @property
    def context(self):
        return self._context

    def _checked(self, owned_ref):
        identity = _identity(owned_ref)
        current = validate_workspace_context(self._context)
        if (owned_ref.workspace_id != current.owner.workspace_id
                or owned_ref.root_binding != current.owner.root_binding):
            raise CredentialError('credential_owner_mismatch')
        address = ScopedCredentialAddress(_SERVICE, hashlib.sha256(identity).hexdigest())
        # Include both exact address input and payload length in the authenticated data.
        prefix = _MAGIC + len(identity).to_bytes(4, 'big') + identity
        return address, prefix, current.key_provider.get_key()

    def put_owned(self, owned_ref, payload: bytes) -> None:
        if type(payload) is not bytes:
            raise CredentialError('credential_invalid_secret')
        address, prefix, key = self._checked(owned_ref)
        body = prefix + len(payload).to_bytes(8, 'big') + payload
        envelope = body + hmac.digest(key, body, 'sha256')
        # A duplicate is a failure: no read, overwrite, wrap, adoption or delete.
        self._raw_backend.add(address, envelope)

    def _read_checked(self, address, prefix, key):
        envelope = self._raw_backend.copy(address)
        minimum = len(prefix) + 8 + _TAG_SIZE
        if type(envelope) is not bytes or len(envelope) < minimum or not envelope.startswith(prefix):
            raise CredentialError('credential_ownership_unproven')
        body, tag = envelope[:-_TAG_SIZE], envelope[-_TAG_SIZE:]
        if not hmac.compare_digest(tag, hmac.digest(key, body, 'sha256')):
            raise CredentialError('credential_ownership_unproven')
        size = int.from_bytes(body[len(prefix):len(prefix) + 8], 'big')
        payload = body[len(prefix) + 8:]
        if len(payload) != size:
            raise CredentialError('credential_ownership_unproven')
        return payload

    def read_owned(self, owned_ref) -> bytes:
        return self._read_checked(*self._checked(owned_ref))

    def delete_owned(self, owned_ref) -> None:
        address, prefix, key = self._checked(owned_ref)
        self._read_checked(address, prefix, key)
        # Re-check disk identity immediately before deletion. The outer workspace
        # writer/recovery guard must serialize vault and reference-graph mutations.
        self._checked(owned_ref)
        self._raw_backend.delete(address)
