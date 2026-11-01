"""Explicitly scoped credential storage; never serializes secret values."""
import re
import threading
from typing import Protocol
from .oauth_models import CredentialRef


class CredentialError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class CredentialBackend(Protocol):
    def put(self, ref: CredentialRef, secret: bytes) -> None: ...
    def get(self, ref: CredentialRef) -> bytes: ...
    def delete(self, ref: CredentialRef) -> None: ...


def validate_ref(ref, account_id=None):
    if not isinstance(ref, CredentialRef) or ref.namespace != 'autosns.oauth':
        raise CredentialError('credential_invalid_ref')
    if ref.account_id not in ('personal', 'dept') or (account_id is not None and ref.account_id != account_id):
        raise CredentialError('credential_owner_mismatch')
    if any(not isinstance(x, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', x) for x in (ref.platform, ref.connection_id)):
        raise CredentialError('credential_invalid_ref')
    if type(ref.generation) is not int or ref.generation <= 0 or ref.kind not in ('client','code','verifier','ticket','token'):
        raise CredentialError('credential_invalid_ref')
    return (ref.namespace, ref.account_id, ref.platform, ref.connection_id, ref.generation, ref.kind)


class MemoryCredentialBackend:
    def __init__(self, *, account_id=None):
        self._account_id = account_id
        self._items = {}
        self._lock = threading.Lock()
    def put(self, ref, secret):
        key = validate_ref(ref, self._account_id)
        if not isinstance(secret, bytes): raise CredentialError('credential_invalid_secret')
        with self._lock:
            if key in self._items: raise CredentialError('credential_duplicate')
            self._items[key] = secret
    def get(self, ref):
        key = validate_ref(ref, self._account_id)
        with self._lock:
            if key not in self._items: raise CredentialError('credential_not_found')
            return self._items[key]
    def delete(self, ref):
        key = validate_ref(ref, self._account_id)
        with self._lock:
            if key not in self._items: raise CredentialError('credential_not_found')
            del self._items[key]
