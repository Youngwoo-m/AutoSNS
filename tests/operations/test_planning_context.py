"""계정별 기획 근거의 정의·기간·결측·비용 귀속 시험."""
from unittest.mock import Mock
from tests.operations import test_metrics as fixtures
from tests.operations.test_metrics import NOW
from common.operations.metrics_models import MetricObservation
from common.operations.metrics import build_metrics_context, collect_delivery_metrics
from common.operations.planning_context import build_planning_context

class PlanningContextTests(fixtures.MetricsFixture):
    def setUp(self):super().setUp()
    def context(self,account):
        return build_planning_context(account,self.runtime.registry,self.store,runtime_store=self.runtime)
    def legacy(self):
        row=MetricObservation('legacy_reported',None,'personal','naver_blog','personal.naver','safeworking',None,None,None,'안전 작업 이력','legacy_reported',{'views':100},None,None,None,'legacy.views',source={'kind':'blog'},uncertainties=('owner_unknown',))
        return self.store.append_observation(row,'legacy')
    def test_lifetime_never_becomes_monthly_and_destination_counts_once(self):
        self.record(self.result(values={'views':20}),observation_key='first')
        self.record(self.result(values={'views':20}),observation_key='duplicate-source')
        dept=self.context('dept');personal=self.context('personal')
        self.assertEqual([],dept['interval_metrics']);self.assertEqual(20,dept['destination_metrics'][0]['values']['views'])
        self.assertEqual([],personal['destination_metrics']);self.assertEqual(2,len(personal['observation_ids']))
    def test_failure_keeps_previous_success_and_legacy_excluded(self):
        self.record(self.result(values={'views':8}))
        self.record(self.result(status='error',values={},observed_at=None))
        self.legacy();ctx=self.context('all')
        self.assertEqual(8,ctx['destination_metrics'][0]['values']['views'])
        self.assertEqual('error',ctx['metric_evidence'][0]['latest_status'])
        self.assertEqual(1,len(ctx['legacy_observation_ids']));self.assertTrue(ctx['missing'])
    def test_production_budget_deduplicated_owner_once_and_actual_money_unknown(self):
        self.runtime.rows.append(dict(self.runtime.rows[0],id='d2'))
        self.runtime.productions=[dict(id='production',state='settled',requirements=[{'bucket_id':'quota','amount':3}],created_at=NOW,settled_at=NOW)]
        personal=self.context('personal');dept=self.context('dept')
        self.assertEqual(1,len(personal['production_budget_evidence']));self.assertEqual([],dept['production_budget_evidence'])
        budget=personal['production_budget_evidence'][0]
        self.assertIsNone(budget['actual_cost']);self.assertIsNone(budget['currency']);self.assertEqual('unknown',budget['monetary_status'])
    def test_safeworking_history_registered_sites_and_no_virtual_accounts(self):
        row=self.legacy();ctx=self.context('personal')
        self.assertIn(row['id'],ctx['observation_ids']);self.assertEqual('safeworking',ctx['registered_sites'][0]['target_id'])
        self.assertEqual(['personal.naver'],[s['connection_id'] for s in ctx['registered_sites']])
        self.assertIn('definitions',ctx);self.assertIn('periods',ctx);self.assertIn('proposals',ctx)
    def test_dept_request_never_resolves_personal_tokens(self):
        forbidden=Mock(side_effect=AssertionError('token access'))
        object.__setattr__(self.runtime.registry,'credentials',forbidden)
        self.context('dept');forbidden.assert_not_called()

    def test_same_remote_via_two_deliveries_is_not_double_counted(self):
        self.record(self.result(values={'views':12}))
        self.runtime.rows.append(dict(self.runtime.rows[0],id='copy-delivery'))
        from common.operations.metrics import record_metrics
        record_metrics(self.store,'copy-delivery',self.result(values={'views':12}),runtime_store=self.runtime,registry=self.runtime.registry)
        self.assertEqual(12,self.context('dept')['destination_metrics'][0]['values']['views'])

    def test_actual_collector_exception_links_previous_success_to_latest_failure(self):
        self._assert_actual_collection_failure_linked(lambda *_: 1/0, 'error')

    def test_actual_missing_collector_links_previous_success_to_unsupported(self):
        self._assert_actual_collection_failure_linked(None, 'unsupported')

    def _assert_actual_collection_failure_linked(self, collector, status):
        fixed=build_metrics_context(self.runtime,'d',self.runtime.registry)
        success=self.record(collect_delivery_metrics(fixed,'video',lambda *_:self.result(values={'views':8})))
        failure=self.record(collect_delivery_metrics(fixed,'video',collector))
        context=self.context('dept')
        metric=next(row for row in context['metric_evidence'] if row['definition_id']=='youtube.views')
        self.assertEqual(status,metric['latest_status'])
        self.assertEqual(failure['id'],metric['latest_observation_id'])
        self.assertEqual('physical_post',metric['latest_scope'])
        self.assertEqual(success['id'],metric['latest_metric_observation_id'])
        self.assertEqual(success['id'],metric['previous_success_observation_id'])
        self.assertEqual('lifetime',metric['basis']);self.assertIsNone(metric['period'])
        self.assertIn(failure['id'],metric['observation_ids'])
        self.assertEqual(8,context['destination_metrics'][0]['values']['views'])
        self.assertEqual([],context['interval_metrics'])
        self.assertTrue(any(row['observation_id']==failure['id'] and row['status']==status for row in context['missing']))

    def test_success_after_physical_collection_failure_is_current_again(self):
        fixed=build_metrics_context(self.runtime,'d',self.runtime.registry)
        self.record(collect_delivery_metrics(fixed,'video',None))
        success=self.record(collect_delivery_metrics(fixed,'video',lambda *_:self.result(values={'views':9})))
        metric=next(row for row in self.context('dept')['metric_evidence'] if row['definition_id']=='youtube.views')
        self.assertEqual('ok',metric['latest_status']);self.assertEqual(success['id'],metric['latest_observation_id'])
        self.assertEqual('metric',metric['latest_scope'])

    def test_physical_failure_does_not_change_another_posts_success(self):
        self.record(self.result(values={'views':8}))
        self.runtime.rows[0]['remote_id']='other-video'
        self.runtime.events=lambda _:[dict(kind='verification',evidence=dict(outcome='verified',checked_at=NOW,evidence=dict(remote_id='other-video',target_id='channel',destination_account_id='dept',visibility='public')))]
        fixed=build_metrics_context(self.runtime,'d',self.runtime.registry)
        self.record(collect_delivery_metrics(fixed,'other-video',None))
        metric=next(row for row in self.context('dept')['metric_evidence'] if row['definition_id']=='youtube.views')
        self.assertEqual('ok',metric['latest_status'])
        self.assertEqual('metric',metric['latest_scope'])
