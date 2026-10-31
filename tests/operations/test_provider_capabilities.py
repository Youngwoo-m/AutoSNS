import unittest
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import patch
from common.operations.provider_capabilities import DEFAULT_CAPABILITIES, ToolCapability, capabilities_snapshot
from common.operations.tool_cost_policy import ToolkitPolicy
from common.operations.models import Connection


class CapabilityTests(unittest.TestCase):
    def test_catalog_is_not_authenticated_runtime(self):
        snapshot = capabilities_snapshot('personal', SimpleNamespace(connections={}), policy=ToolkitPolicy(True))
        self.assertFalse(snapshot['external_execution_supported'])
        self.assertEqual(snapshot['connections'], [])
        self.assertTrue(all(x['runtime_kind'] == 'local' for x in snapshot['items'] if x['action_id'].startswith('local.')))
        self.assertEqual(len([x for x in snapshot['items'] if x['action_id'].startswith('local.')]), 7)

    def test_default_disabled_has_no_io(self):
        with patch('socket.socket') as socket, patch('subprocess.Popen') as process:
            snapshot = capabilities_snapshot('personal', SimpleNamespace(connections={}), policy=ToolkitPolicy())
        self.assertFalse(snapshot['toolkit_enabled'])
        socket.assert_not_called()
        process.assert_not_called()

    def test_stored_auth_observation_does_not_grant_scopes_or_expose_secrets(self):
        connection = Connection(account_id='personal', id='saved', platform='youtube',
            target_id='target', target_label='저장된 개인 채널',
            auth_status='authenticated', auth_checked_at='2026-10-30T00:00:00+00:00',
            credential_ref='secret-ref')
        snapshot = capabilities_snapshot('personal', SimpleNamespace(connections={'saved': connection}), policy=ToolkitPolicy())
        row = snapshot['connections'][0]
        self.assertEqual(row['auth_status'], 'authenticated')
        self.assertEqual(row['platform'], 'youtube')
        self.assertEqual(row['target_label'], '저장된 개인 채널')
        self.assertEqual(row['read_scope_status'], 'unknown')
        self.assertEqual(row['write_scope_status'], 'unknown')
        self.assertNotIn('credential_ref', row)
        self.assertEqual(capabilities_snapshot('dept', SimpleNamespace(connections={'saved': connection}), policy=ToolkitPolicy())['connections'], [])

    def test_catalog_is_deeply_immutable(self):
        with self.assertRaises(TypeError):
            DEFAULT_CAPABILITIES['fake'] = None
        item = DEFAULT_CAPABILITIES['local.packaging.preview']
        with self.assertRaises(FrozenInstanceError):
            item.effect = 'external_write'
        with self.assertRaises(ValueError):
            ToolCapability('a', 'b', [], 'read', 'implemented', 'local', 'no_additional_cost', ())
