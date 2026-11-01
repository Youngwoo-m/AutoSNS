import unittest
from unittest.mock import patch
from common.operations.oauth_models import CredentialRef
from common.operations.credential_backend import MemoryCredentialBackend, CredentialError
from common.operations.keychain_backend import MacKeychainBackend, SecurityFrameworkBridge


def ref(account='personal', generation=1):
    return CredentialRef('autosns.oauth', account, 'instagram', 'connection-1', generation, 'token')


class FakeBridge:
    def __init__(self):
        self.items = {}; self.status = 0; self.calls = []
    def add(self, service, account, secret):
        self.calls.append('add')
        if self.status: return self.status
        if (service, account) in self.items: return -25299
        self.items[service, account] = secret
        return 0
    def copy(self, service, account):
        self.calls.append('copy')
        return (self.status, None) if self.status else (0, self.items[service, account]) if (service, account) in self.items else (-25300, None)
    def delete(self, service, account):
        self.calls.append('delete')
        if self.status: return self.status
        return 0 if self.items.pop((service, account), None) is not None else -25300


class CredentialBackendTests(unittest.TestCase):
    def backends(self):
        return [MemoryCredentialBackend(account_id='personal'), MacKeychainBackend(FakeBridge(), account_id='personal')]
    def test_roundtrip_duplicate_generation_and_delete(self):
        for backend in self.backends():
            backend.put(ref(), b'synthetic-secret')
            self.assertEqual(backend.get(ref()), b'synthetic-secret')
            with self.assertRaises(CredentialError) as ctx: backend.put(ref(), b'replacement')
            self.assertEqual(ctx.exception.code, 'credential_duplicate')
            backend.put(ref(generation=2), b'new')
            backend.delete(ref()); self.assertEqual(backend.get(ref(generation=2)), b'new')
            with self.assertRaises(CredentialError): backend.get(ref())
    def test_namespace_and_owner_rejected_before_bridge(self):
        bridge = FakeBridge(); backend = MacKeychainBackend(bridge, account_id='personal')
        invalid = []
        for field,value in [('namespace','other'),('connection_id','../x'),('connection_id','a/b'),('connection_id','a\\b'),('connection_id','a..b'),('platform','a.b'),('generation',True)]:
            item=ref(); object.__setattr__(item,field,value); invalid.append(item)
        for item in invalid + [ref('dept')]:
            with self.assertRaises(CredentialError): backend.get(item)
        self.assertEqual(bridge.calls, [])
    def test_existing_dotted_connection_ids_preserve_exact_identity(self):
        for backend in self.backends():
            for identifier in ('personal.youtube','dept.naver_blog','youtube.personal'):
                item = CredentialRef('autosns.oauth','personal','youtube',identifier,1,'token')
                backend.put(item, b'dotted-fixture')
                self.assertEqual(backend.get(item), b'dotted-fixture')
                other = CredentialRef('autosns.oauth','dept','youtube',identifier,1,'token')
                with self.assertRaises(CredentialError) as ctx: backend.get(other)
                self.assertEqual(ctx.exception.code, 'credential_owner_mismatch')
                lookalike = CredentialRef('autosns.oauth','personal','youtube',identifier.replace('.', '_'),1,'token')
                with self.assertRaises(CredentialError): backend.get(lookalike)
                backend.delete(item)
                with self.assertRaises(CredentialError): backend.get(item)

    def test_account_isolation_unbound(self):
        backend = MemoryCredentialBackend(); backend.put(ref(), b'private')
        with self.assertRaises(CredentialError): backend.get(ref('dept'))
    def test_errors_sanitized_and_delete_failure_preserves_value(self):
        bridge = FakeBridge(); backend = MacKeychainBackend(bridge)
        backend.put(ref(), b'synthetic-secret')
        for status, code in [(-25300,'credential_not_found'),(-25308,'credential_locked'),(-25293,'credential_denied'),(-999,'credential_unavailable')]:
            bridge.status = status
            for action in [lambda: backend.get(ref()), lambda: backend.delete(ref())]:
                with self.assertRaises(CredentialError) as ctx: action()
                self.assertEqual(ctx.exception.code, code)
                self.assertNotIn('synthetic-secret', repr(ctx.exception))
        bridge.status = 0; self.assertEqual(backend.get(ref()), b'synthetic-secret')
        self.assertNotIn('synthetic-secret', repr(backend))
    def test_lazy_bridge_and_unexpected_exception_sanitized(self):
        with patch('ctypes.CDLL', side_effect=AssertionError('native load')):
            SecurityFrameworkBridge()
        bridge = FakeBridge()
        def fail(*args): raise RuntimeError('synthetic-secret')
        bridge.copy = fail
        with self.assertRaises(CredentialError) as ctx: MacKeychainBackend(bridge).get(ref())
        self.assertNotIn('synthetic-secret', repr(ctx.exception))
        self.assertIsNone(ctx.exception.__cause__)


class NativeOwnershipTests(unittest.TestCase):
    def bridge(self, status=0, wrong_type=False):
        import ctypes
        class CF:
            def __init__(self): self.next=100; self.created=[]; self.released=[]; self.buffer=ctypes.create_string_buffer(b'fixture')
            def make(self,*args):
                self.next+=1; self.created.append(self.next); return self.next
            CFStringCreateWithCString=make
            CFDataCreate=make
            CFDictionaryCreate=make
            def CFRelease(self,obj): self.released.append(obj.value if hasattr(obj,'value') else obj)
            def CFGetTypeID(self,obj): return 9 if wrong_type else 8
            def CFDataGetTypeID(self): return 8
            def CFDataGetLength(self,obj): return 7
            def CFDataGetBytePtr(self,obj): return ctypes.addressof(self.buffer)
        class Security:
            def SecItemCopyMatching(self,query,out):
                ctypes.cast(out,ctypes.POINTER(ctypes.c_void_p))[0]=500
                return status
            def SecItemAdd(self,query,out): return status
            def SecItemDelete(self,query): return status
        bridge=SecurityFrameworkBridge(); bridge._cf=CF(); bridge._security=Security()
        bridge._constant=lambda name: 1
        return bridge
    def test_copy_releases_retained_result_and_all_owned_objects(self):
        for status in (0,-25300):
            bridge=self.bridge(status)
            self.assertEqual(bridge.copy('service','account'), (0,b'fixture') if status==0 else (status,None))
            self.assertCountEqual(bridge._cf.released, bridge._cf.created+[500])
    def test_wrong_result_type_releases_everything(self):
        bridge=self.bridge(wrong_type=True)
        with self.assertRaises(CredentialError): bridge.copy('service','account')
        self.assertCountEqual(bridge._cf.released,bridge._cf.created+[500])
    def test_add_and_delete_release_query_and_values(self):
        for method,args in [('add',('service','account',b'fixture')),('delete',('service','account'))]:
            bridge=self.bridge(); self.assertEqual(getattr(bridge,method)(*args),0)
            self.assertCountEqual(bridge._cf.released,bridge._cf.created)
