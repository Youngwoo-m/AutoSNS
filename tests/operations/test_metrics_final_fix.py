"""최종 I1/I2/I4 반례: 임시 원장·합성 importer→GET 외에는 IO하지 않는다."""
import copy
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
from unittest.mock import patch
from tests.operations.test_metrics import MetricsFixture, NOW, registry
from common.operations.metrics import build_metrics_context, collect_delivery_metrics
from common.operations.metrics_models import MetricResult, MetricObservation
from common.operations.metrics_store import MetricsStore
from common.operations.content_store import ConflictError, StoreError
from common.operations.planning_context import build_planning_context, _projection
from common.operations.legacy_metrics import load_legacy_metrics, build_import_plan


class CollectionAttemptTests(MetricsFixture):
    def test_error_success_same_error_records_new_latest_attempt(self):
        error=self.result(status='error',values={},observed_at=None,definition_id='collection.error',basis='unknown')
        first=self.record(error); success=self.record(self.result(values={'views':8})); last=self.record(error)
        self.assertNotEqual(first['id'],last['id'])
        self.assertEqual(3,len(self.store.list_observations()))
        evidence=build_planning_context('dept',self.runtime.registry,self.store,runtime_store=self.runtime)['metric_evidence']
        metric=next(r for r in evidence if r['definition_id']=='youtube.views')
        self.assertEqual(last['id'],metric['latest_observation_id']);self.assertEqual('error',metric['latest_status'])
        self.assertEqual(success['id'],metric['previous_success_observation_id'])
        self.assertGreater(last['collected_at'],first['collected_at'])

    def test_success_unsupported_same_success_is_recovery(self):
        success=self.result(values={'views':8});first=self.record(success)
        self.record(self.result(status='unsupported',values={},observed_at=None,definition_id='collection.unsupported',basis='unknown'))
        last=self.record(success)
        self.assertNotEqual(first['id'],last['id']);self.assertEqual(3,len(self.store.list_observations()))
        metric=next(r for r in build_planning_context('dept',self.runtime.registry,self.store,runtime_store=self.runtime)['metric_evidence'] if r['definition_id']=='youtube.views')
        self.assertEqual('ok',metric['latest_status']);self.assertEqual(last['id'],metric['latest_observation_id'])

    def test_explicit_replay_survives_reopen_conflicts_and_concurrency(self):
        first=self.record(self.result(),observation_key='attempt-one')
        self.store=MetricsStore(self.store.root);self.store.initialize()
        self.assertEqual(first,self.record(self.result(),observation_key='attempt-one'))
        with self.assertRaises(ConflictError):self.record(self.result(values={'views':1}),observation_key='attempt-one')
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.record(self.result(),observation_key='parallel'),range(2)))
        self.assertEqual(results[0],results[1]);self.assertEqual(2,len(self.store.list_observations()))

    def test_result_requires_server_identity_and_completion_as_a_pair(self):
        for fields in ({'collection_id':'one'}, {'collected_at':NOW}, {'collection_id':'','collected_at':NOW}, {'collection_id':'one','collected_at':'2026-10-30'}):
            with self.assertRaises(StoreError):self.result(**fields)
        result=self.result(collection_id='one',collected_at=NOW)
        saved=self.record(result)
        with self.assertRaises(ConflictError):self.record(self.result(collection_id='one',collected_at='2026-10-30T01:00:00Z'))
        self.assertEqual(saved,self.record(result))

    def test_collector_cannot_choose_attempt_identity_and_each_completion_is_new(self):
        ctx=build_metrics_context(self.runtime,'d',self.runtime.registry)
        supplied=self.result(collection_id='provider-supplied',collected_at='2000-01-01T00:00:00Z')
        first=collect_delivery_metrics(ctx,'video',lambda *_:supplied)
        second=collect_delivery_metrics(ctx,'video',lambda *_:supplied)
        self.assertNotEqual('provider-supplied',first.collection_id);self.assertNotEqual(first.collection_id,second.collection_id)
        self.assertNotEqual(supplied.collected_at,first.collected_at)
        self.assertNotEqual(self.record(first)['id'],self.record(second)['id'])

    def test_collection_issues_identity_and_completion_time_for_all_statuses(self):
        ctx=build_metrics_context(self.runtime,'d',self.runtime.registry)
        for collector in (None,lambda *_:1/0,lambda *_:self.result()):
            with patch('common.operations.metrics.datetime') as clock:
                clock.now.return_value.isoformat.return_value='2026-10-30T04:00:00+00:00'
                result=collect_delivery_metrics(ctx,'video',collector)
            self.assertTrue(getattr(result,'collection_id',None))
            self.assertEqual('2026-10-30T04:00:00+00:00',result.collected_at)
            first=self.record(result);self.assertEqual(first,self.record(result))
            self.assertEqual(result.collected_at,first['collected_at'])
        self.assertEqual(3,len(self.store.list_observations()))


class AggregationTests(MetricsFixture):
    def rows(self,definition='searchconsole.performance.v1',basis='interval',values=None):
        period={'start':'2026-10-01T00:00:00Z','end':'2026-10-02T00:00:00Z','timezone':'UTC'} if basis=='interval' else None
        base=self.record(self.result(definition_id=definition,basis=basis,period=period,values=values or {'clicks':3,'impressions':4,'ctr':.75,'position':2,'reach':7,'subscribers':9,'mystery':11}))
        return [base,dict(copy.deepcopy(base),id='second',remote_id='second')]
    def test_validated_count_and_weighted_ratio_preserve_individual_nonadditive_values(self):
        rows=self.rows();aggregate=_projection(rows,'dept')[1][0]
        self.assertEqual({'clicks':6,'impressions':8,'ctr':.75,'position':2},aggregate['values'])
        self.assertEqual(2,len(aggregate['individual_values']['reach']))
        self.assertEqual([7,7],[r['value'] for r in aggregate['individual_values']['reach']])
        self.assertEqual('not_aggregated',aggregate['aggregation']['subscribers']['method'])
    def test_unknown_definition_and_unknown_basis_never_default_to_sum(self):
        for definition,basis in [('custom.rate','interval'),('searchconsole.performance.v1','unknown')]:
            aggregate=_projection(self.rows(definition,basis),'dept')[1][0]
            self.assertEqual({},aggregate['values'])
            self.assertIn('ctr',aggregate['individual_values'])
    def test_mismatched_ratio_missing_denominator_and_different_targets_are_not_combined(self):
        rows=self.rows();rows[1]['values']['ctr']=75
        aggregate=_projection(rows,'dept')[1][0]
        self.assertNotIn('ctr',aggregate['values']);self.assertIn('ctr',aggregate['individual_values'])
        rows=self.rows();del rows[1]['values']['impressions']
        aggregate=_projection(rows,'dept')[1][0]
        self.assertNotIn('position',aggregate['values']);self.assertNotIn('ctr',aggregate['values'])
        rows=self.rows();rows[1]['target_id']='another-property'
        aggregates=_projection(rows,'dept')[1]
        self.assertEqual(2,len(aggregates));self.assertEqual([.75,.75],[r['values']['ctr'] for r in aggregates])
    def test_zero_negative_fractional_counts_and_lifetime_search_are_not_misrepresented(self):
        for values in ({'clicks':0,'impressions':0,'ctr':0,'position':0}, {'clicks':-1,'impressions':4,'ctr':-.25}, {'clicks':1.5,'impressions':4,'ctr':.375}):
            aggregate=_projection(self.rows(values=values),'dept')[1][0]
            self.assertNotIn('ctr',aggregate['values'])
            if values['clicks']!=0:self.assertNotIn('clicks',aggregate['values'])
        aggregate=_projection(self.rows(basis='lifetime'),'dept')[1][0]
        self.assertEqual({},aggregate['values'])

    def test_valid_large_counts_do_not_crash_projection_or_lose_individual_values(self):
        large=10**400
        aggregate=_projection(self.rows(values={'clicks':large,'impressions':large,'ctr':1,'position':1.5}),'dept')[1][0]
        self.assertEqual(2*large,aggregate['values']['clicks'])
        self.assertIn('position',aggregate['individual_values'])

    def test_weighted_position_uses_impressions_and_unknown_metric_keeps_each_source(self):
        rows=self.rows();rows[1]['values'].update(clicks=1,impressions=2,ctr=.5,position=8)
        aggregate=_projection(rows,'dept')[1][0]
        self.assertAlmostEqual(4/6,aggregate['values']['ctr']);self.assertEqual(4,aggregate['values']['position'])
        self.assertEqual({rows[0]['id'],'second'},{r['observation_id'] for r in aggregate['individual_values']['mystery']})


def importer_http_fixture():
    """Node에서 같은 실제 importer/store/GET 결과를 렌더한다. socket 불필요."""
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'ax-console/app'))
    from web_metrics import handle
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp);parts=root/'source/common/analytics/snapshots/parts';parts.mkdir(parents=True)
        reports={
            'indexing':{'per_site':[{'검사':15,'색인확인':12,'미색인':3}],'indexed_total':321},
            'instagram':{'items':[{'saves':7}],'profile':{'followers':123,'posts':4,'token':'SECRET'}},
            'youtube':{'items':[],'channel':{'subscribers':55,'total_views':678}},
            'searchconsole':{'items':[{'clicks':3,'impressions':4,'ctr':.75,'position':2.5,'queries':9}]},
        }
        for kind,data in reports.items():(parts/f'{kind}.json').write_text(json.dumps(data))
        store=MetricsStore(root/'managed');store.initialize()
        store.import_rows(build_import_plan(load_legacy_metrics(root/'source',registry()),registry()))
        return handle(store,'GET','/api/v2/metrics',{},lambda:None,source_root=root/'source',registry=registry())

if __name__=='__main__':
    if '--emit-fixture' in sys.argv:print(json.dumps(importer_http_fixture(),ensure_ascii=False))
