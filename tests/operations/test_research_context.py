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
                'observations':[{'id':i,'owner_account_id':'personal','destination_account_id':'dept','source_kind':'verified_delivery','status':'ok','content_id':'c','source':{'content_revision':1}} for i in ('a','b','c')], 'missing':[],'legacy_observation_ids':['legacy']}
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


    def test_incompatible_definition_is_unavailable_even_with_three_samples(self):
        context=self.context()
        other=copy.deepcopy(context['destination_metrics'][0])
        other.update(definition_id='unregistered',values={},
                     individual_values={'views':[{'observation_id':i,'value':3} for i in ('a','b','c')]},
                     aggregation={'views':{'method':'not_aggregated'}})
        context['destination_metrics'].append(other)
        result=self.preview(context)
        self.assertEqual(3,result['groups'][0]['sample_count'])
        self.assertEqual('available',result['groups'][0]['recommendation_status'])
        self.assertEqual(3,result['groups'][1]['sample_count'])
        self.assertEqual('unavailable',result['groups'][1]['recommendation_status'])
        self.assertEqual([],result['groups'][1]['recommendations'])
        self.assertIn('incompatible_metric_definition',result['missing'][-1]['uncertainties'])


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

    def test_real_record_metrics_references_bind_root_content_id_and_revision(self):
        first=self.record(self.result(values={'views':8},source={'content_id':'untrusted'}))
        initial=build_research_preview('dept',self.runtime.registry,self.store,Mock(),runtime_store=self.runtime)
        self.assertEqual('c',initial['evidence_refs'][0]['content_id'])
        self.assertEqual(2,initial['evidence_refs'][0]['content_revision'])
        self.runtime.rows[0]['context'].update(content_id='second-content',content_revision=7,manifest_hash='second-manifest')
        second=self.record(self.result(values={'views':9}),observation_key='second-content')
        self.assertEqual('c',first['content_id'])
        self.assertNotIn('content_id',first['source'])
        self.assertEqual('second-content',second['content_id'])
        self.assertEqual('personal',first['owner_account_id'])
        self.assertEqual('personal',second['owner_account_id'])
        preview=build_research_preview('dept',self.runtime.registry,self.store,Mock(),runtime_store=self.runtime)
        refs={ref['observation_id']:ref for ref in preview['evidence_refs']}
        # 동일 게시의 최신 검증 관측을 기존 projection이 선택해도 원고 ID/버전은 그 관측에 결속된다.
        self.assertNotIn(first['id'],refs)
        self.assertEqual('second-content',refs[second['id']]['content_id'])
        self.assertEqual(7,refs[second['id']]['content_revision'])
        self.assertEqual('personal',refs[second['id']]['owner_account_id'])
        self.assertEqual('dept',refs[second['id']]['destination_account_id'])
