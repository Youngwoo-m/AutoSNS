import unittest
from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import patch
from common.operations.tool_cost_policy import CostEvidence, ToolActionContext, ToolkitPolicy, LOCAL_COST_EVIDENCE, evaluate_tool_action
from common.operations.provider_capabilities import DEFAULT_CAPABILITIES


class CostPolicyTests(unittest.TestCase):
    def context(self, **kwargs):
        return replace(ToolActionContext('personal', 'personal', None, None, ToolkitPolicy(True), 'local', LOCAL_COST_EVIDENCE, datetime(2026, 10, 31, tzinfo=timezone.utc)), **kwargs)

    def test_paid_credit_unknown_and_forged_zero_never_run(self):
        evidence = [CostEvidence('credits', 150, True, 'cost=0', None), CostEvidence('paid', 0, True, 'cost=0', None), CostEvidence('unknown', 0, None, '', None), CostEvidence('no_additional_cost', 0, True, 'cost=0', None)]
        with patch('socket.socket') as socket, patch('subprocess.Popen') as process:
            for item in evidence:
                self.assertFalse(evaluate_tool_action('local.packaging.preview', self.context(cost_evidence=item))['allowed'])
        socket.assert_not_called()
        process.assert_not_called()

    def test_expired_evidence_and_read_does_not_grant_write(self):
        expired = replace(LOCAL_COST_EVIDENCE, valid_until='2020-01-01T00:00:00+00:00')
        self.assertFalse(evaluate_tool_action('local.packaging.preview', self.context(cost_evidence=expired))['allowed'])
        self.assertFalse(evaluate_tool_action('metricool.publish', self.context(runtime_kind='unavailable', read_scope_status='granted', write_scope_status='unknown'))['allowed'])

    def test_only_fixed_local_evidence_and_explicit_policy_allow(self):
        for action in DEFAULT_CAPABILITIES:
            decision = evaluate_tool_action(action, self.context())
            self.assertEqual(decision['allowed'], action.startswith('local.'))
        self.assertFalse(evaluate_tool_action('local.packaging.preview', self.context(policy=ToolkitPolicy()))['allowed'])
        self.assertFalse(evaluate_tool_action('local.packaging.preview', self.context(), catalog={})['allowed'])

    def test_missing_identity_unknown_cost_and_runtime_are_denied(self):
        for changes in ({'owner_account_id': None}, {'destination_account_id': 'dept'},
                        {'runtime_kind': 'codex_assisted'},
                        {'cost_evidence': replace(LOCAL_COST_EVIDENCE, additional_cost_zero=None)}):
            self.assertFalse(evaluate_tool_action('local.thumbnail.render', self.context(**changes))['allowed'])
        self.assertFalse(evaluate_tool_action('unknown', self.context())['allowed'])

    def test_cross_local_evidence_cannot_grant_external_execution(self):
        context=self.context(destination_account_id='dept',cross_account_local_authorized=True)
        self.assertTrue(evaluate_tool_action('local.packaging.preview',context)['allowed'])
        self.assertFalse(evaluate_tool_action('metricool.publish',context)['allowed'])
        with self.assertRaises(ValueError):self.context(cross_account_local_authorized=1)

    def test_strict_constructors(self):
        for value in (1, 'true', None):
            with self.assertRaises(ValueError):
                ToolkitPolicy(value)
        with self.assertRaises(ValueError):
            CostEvidence('credits', True, True, 'x', None)
        with self.assertRaises(ValueError):
            CostEvidence('free', 0, True, 'x', None)
        with self.assertRaises(ValueError):
            self.context(now=datetime(2026, 1, 1))
        with self.assertRaises(ValueError):
            self.context(write_scope_status='yes')
        with self.assertRaises(ValueError):
            self.context(policy={'enabled': True})
        with self.assertRaises(ValueError):
            CostEvidence('no_additional_cost', 0, True, 'x', '2026-01-01')
        with self.assertRaises(ValueError):
            CostEvidence('no_additional_cost', 0, 1, 'x', None)
