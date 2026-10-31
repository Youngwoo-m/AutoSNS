"""저장 근거의 소유자·대상·정의 경계 시험."""
import copy
import unittest
from unittest.mock import Mock, patch
from common.operations.research_context import build_research_preview


class ResearchContextTests(unittest.TestCase):
    def preview(self,context,account='dept'):
        with patch('common.operations.research_context.build_planning_context',return_value=context), patch('urllib.request.urlopen',side_effect=AssertionError('fetch')):
            return build_research_preview(account,Mock(),Mock(),Mock())
    def context(self):
        return {'destination_metrics':[{'destination_account_id':'dept','platform':'youtube','target_id':'channel','definition_id':'youtube.views','basis':'lifetime','period':None,'values':{'views':9},'individual_values':{},'aggregation':{'views':{'method':'sum'}},'observation_ids':['a','b','c']}],
                'observations':[{'id':i,'owner_account_id':'personal','destination_account_id':'dept','source_kind':'verified_delivery','status':'ok','source':{'content_id':'c','content_revision':1}} for i in ('a','b','c')], 'missing':[],'legacy_observation_ids':['legacy']}
    def test_owner_destination_evidence_is_not_crossed(self):
        context=self.context();before=copy.deepcopy(context)
        result=self.preview(context)
        self.assertEqual(context,before)
        self.assertEqual('dept',result['groups'][0]['destination_account_id'])
        self.assertEqual(['personal'],result['groups'][0]['owner_account_ids'])
        self.assertEqual(['a','b','c'],result['groups'][0]['observation_ids'])
        self.assertNotIn('legacy',str(result['groups']))
        self.assertEqual([],self.preview(context,'personal')['groups'])
        self.assertNotIn('ctr',result)
        self.assertIn('search_volume',result['unavailable_fields'])
    def test_incompatible_definitions_and_small_samples_are_unavailable(self):
        context=self.context();context['destination_metrics'][0]['observation_ids']=['a','b']
        other=copy.deepcopy(context['destination_metrics'][0]);other.update(definition_id='unregistered',basis='interval',period={'start':'a','end':'b'},values={},individual_values={'views':[{'observation_id':'c','value':2}]},aggregation={'views':{'method':'not_aggregated'}},observation_ids=['c'])
        context['destination_metrics'].append(other)
        result=self.preview(context)
        self.assertEqual(2,len(result['groups']))
        for group in result['groups']:
            self.assertEqual('unavailable',group['recommendation_status'])
            self.assertEqual([],group['recommendations'])
        self.assertTrue(result['missing'])


from tests.operations import test_planning_context as planning_tests
from tests.operations import test_metrics as fixtures


class ResearchStoredEvidenceTests(fixtures.MetricsFixture):
    def test_real_projection_retains_legacy_outside_verified_groups(self):
        self.record(self.result(values={'views':8}))
        legacy=planning_tests.PlanningContextTests.legacy(self)
        content_store=Mock()
        with patch('urllib.request.urlopen',side_effect=AssertionError('fetch')), patch('subprocess.run',side_effect=AssertionError('process')):
            dept=build_research_preview('dept',self.runtime.registry,self.store,content_store,runtime_store=self.runtime)
            personal=build_research_preview('personal',self.runtime.registry,self.store,content_store,runtime_store=self.runtime)
        self.assertEqual(8,dept['groups'][0]['values']['views'])
        self.assertEqual('unavailable',dept['groups'][0]['recommendation_status'])
        self.assertEqual(['personal'],dept['groups'][0]['owner_account_ids'])
        self.assertEqual([],personal['groups'])
        self.assertNotIn(legacy['id'],str(dept['groups']))
        self.assertNotIn('SECRET',str(dept))
        content_store.assert_not_called()
        self.assertEqual([],content_store.mock_calls)
