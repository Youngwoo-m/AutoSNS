"""고정 Facebook 연결만 명시 adapter factory에 등록한다."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from common.operations.models import Connection
from common.publishers import build_adapters

class FacebookRegistrationTests(unittest.TestCase):
    def test_only_enabled_fixed_page_bindings_with_target_are_registered(self):
        personal=Connection('personal.facebook','personal','facebook',enabled=True,target_id='123')
        dept=Connection('dept.facebook','dept','facebook',enabled=True,target_id='456')
        other=Connection('other.facebook','personal','facebook',enabled=True,target_id='789')
        registry=SimpleNamespace(connections={c.id:c for c in (personal,dept,other)})
        with patch('socket.socket',side_effect=AssertionError('no network')):
            result=build_adapters(registry=registry,bridge=object())
        self.assertEqual(set(result),{'personal.facebook','dept.facebook'})
        self.assertTrue(all(adapter.platform=='facebook' for adapter in result.values()))
        registry.connections={personal.id:replace(personal,enabled=False),dept.id:replace(dept,target_id=None)}
        self.assertEqual(build_adapters(registry=registry,bridge=object()),{})
        registry.connections={personal.id:replace(personal,platform='threads')}
        self.assertEqual(build_adapters(registry=registry,bridge=object()),{})

    def test_default_factory_remains_empty(self):
        self.assertEqual(build_adapters(),{})
