"""Instagram factory는 고정된 명시 활성 연결만 조립하며 기본은 비어 있다."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from common.operations.models import Connection
from common.publishers import build_adapters

class InstagramRegistrationTests(unittest.TestCase):
    def test_enabled_fixed_owner_binding_only_and_constructor_is_inert(self):
        personal=Connection('personal.instagram','personal','instagram',target_id='123',enabled=True)
        dept=Connection('dept.instagram','dept','instagram',target_id='456',enabled=True)
        other=Connection('other.instagram','personal','instagram',target_id='789',enabled=True)
        registry=SimpleNamespace(connections={row.id:row for row in (personal,dept,other)})
        with patch('socket.socket',side_effect=AssertionError('network forbidden')):
            adapters=build_adapters(registry=registry,bridge=object())
        self.assertEqual(set(adapters),{'personal.instagram','dept.instagram'})
        self.assertTrue(all(adapter.platform=='instagram' for adapter in adapters.values()))
        for row in (replace(personal,enabled=False),replace(personal,target_id=None),replace(personal,platform='facebook')):
            registry.connections={personal.id:row};self.assertEqual(build_adapters(registry=registry,bridge=object()),{})

    def test_default_factory_remains_empty(self):self.assertEqual(build_adapters(),{})
