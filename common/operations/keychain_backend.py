"""Lazy public Security.framework binding. Construction/import performs no native I/O."""
import ctypes as C
import json
import sys
from .credential_backend import CredentialError, validate_ref


def _check(status):
    if status:
        raise CredentialError({-25300:'credential_not_found', -25299:'credential_duplicate',
                               -25308:'credential_locked', -25293:'credential_denied',
                               -128:'credential_denied'}.get(status, 'credential_unavailable'))


class MacKeychainBackend:
    def __init__(self, bridge, *, account_id=None):
        self._bridge = bridge
        self._account_id = account_id
    def _identity(self, ref):
        parts = validate_ref(ref, self._account_id)
        return parts[0], json.dumps(parts[1:], separators=(',', ':'))
    def _call(self, method, *args):
        failed = False
        try: result = getattr(self._bridge, method)(*args)
        except Exception: failed = True
        if failed: raise CredentialError('credential_unavailable') from None
        return result
    def put(self, ref, secret):
        service, account = self._identity(ref)
        if not isinstance(secret, bytes): raise CredentialError('credential_invalid_secret')
        _check(self._call('add', service, account, secret))
    def get(self, ref):
        status, value = self._call('copy', *self._identity(ref))
        _check(status)
        if not isinstance(value, bytes): raise CredentialError('credential_unavailable')
        return value
    def delete(self, ref):
        _check(self._call('delete', *self._identity(ref)))


class SecurityFrameworkBridge:
    """Uses SecItem generic-password exact queries and disables authentication UI.

    ABI source: macOS SDK Security/SecItem.h and CoreFoundation headers.
    No library loads until an explicitly invoked add/copy/delete operation.
    """
    def __init__(self):
        self._security = self._cf = None
    def _load(self):
        if self._security is not None: return
        if sys.platform != 'darwin': raise CredentialError('credential_unavailable')
        security = C.CDLL('/System/Library/Frameworks/Security.framework/Security')
        cf = C.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        for name, restype, args in [
            ('CFStringCreateWithCString', C.c_void_p, [C.c_void_p,C.c_char_p,C.c_uint32]),
            ('CFDataCreate', C.c_void_p, [C.c_void_p,C.c_void_p,C.c_long]),
            ('CFDictionaryCreate', C.c_void_p,[C.c_void_p,C.POINTER(C.c_void_p),C.POINTER(C.c_void_p),C.c_long,C.c_void_p,C.c_void_p]),
            ('CFDataGetLength', C.c_long,[C.c_void_p]),
            ('CFDataGetBytePtr', C.c_void_p,[C.c_void_p]),
            ('CFGetTypeID', C.c_ulong,[C.c_void_p]), ('CFDataGetTypeID', C.c_ulong,[]),
            ('CFRelease', None,[C.c_void_p])]:
            fn = getattr(cf,name); fn.restype = restype; fn.argtypes = args
        for name, args in [('SecItemAdd',[C.c_void_p,C.POINTER(C.c_void_p)]),('SecItemCopyMatching',[C.c_void_p,C.POINTER(C.c_void_p)]),('SecItemDelete',[C.c_void_p])]:
            fn = getattr(security,name); fn.restype = C.c_int32; fn.argtypes = args
        self._security, self._cf = security, cf
    def _constant(self, name):
        library = self._cf if name == 'kCFBooleanTrue' else self._security
        return C.c_void_p.in_dll(library, name).value
    def _execute(self, operation, service, account, secret=None):
        self._load()
        owned = []; result = C.c_void_p()
        try:
            def string(value):
                obj = self._cf.CFStringCreateWithCString(None, value.encode('utf-8'), 0x08000100)
                if not obj: raise CredentialError('credential_unavailable')
                owned.append(obj); return obj
            pairs = [('kSecClass',self._constant('kSecClassGenericPassword')),
                     ('kSecAttrService',string(service)),('kSecAttrAccount',string(account)),
                     ('kSecUseAuthenticationUI',self._constant('kSecUseAuthenticationUIFail'))]
            if operation == 'add':
                data = self._cf.CFDataCreate(None, secret, len(secret))
                if not data: raise CredentialError('credential_unavailable')
                owned.append(data); pairs.append(('kSecValueData', data))
            if operation == 'copy':
                pairs.extend([('kSecReturnData',self._constant('kCFBooleanTrue')),('kSecMatchLimit',self._constant('kSecMatchLimitOne'))])
            keys = (C.c_void_p * len(pairs))(*(self._constant(k) for k,v in pairs))
            values = (C.c_void_p * len(pairs))(*(v for k,v in pairs))
            # NULL callbacks: keys are immortal constants; owned values outlive dictionary.
            query = self._cf.CFDictionaryCreate(None, keys, values, len(pairs), None, None)
            if not query: raise CredentialError('credential_unavailable')
            owned.append(query)
            if operation == 'delete': return self._security.SecItemDelete(query)
            if operation == 'add': return self._security.SecItemAdd(query, None)
            status = self._security.SecItemCopyMatching(query, C.byref(result))
            if status: return status, None
            if not result.value or self._cf.CFGetTypeID(result) != self._cf.CFDataGetTypeID():
                raise CredentialError('credential_unavailable')
            size = self._cf.CFDataGetLength(result)
            if size < 0 or size > 16 * 1024 * 1024: raise CredentialError('credential_unavailable')
            return 0, C.string_at(self._cf.CFDataGetBytePtr(result), size)
        finally:
            if result.value: self._cf.CFRelease(result)
            for obj in reversed(owned): self._cf.CFRelease(obj)
    def add(self, service, account, secret): return self._execute('add',service,account,secret)
    def copy(self, service, account): return self._execute('copy',service,account)
    def delete(self, service, account): return self._execute('delete',service,account)
