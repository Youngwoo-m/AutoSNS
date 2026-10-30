import multiprocessing
import unittest
from datetime import timedelta
from types import SimpleNamespace
from common.operations.runtime_store import RuntimeStore
from common.operations.content_store import StoreError
from tests.operations import test_runtime_store as fixtures
NOW, context = fixtures.NOW, fixtures.context
from common.operations.quota import reserve_quota,settle_quota,bucket_id,quota_window


def requirements(start=NOW):
    return [dict(scope_kind=kind,scope_id=scope,metric='posts',window_start=start.isoformat(),window_end=(start+timedelta(days=1)).isoformat(),limit=1,amount=1) for kind,scope in [('target','t'),('api','shared'),('owner','personal')]]

def observed(reqs,usage=0):
    return {bucket_id(r['scope_kind'],r['scope_id'],r['metric'],r['window_start'],r['window_end']):dict(observed_usage=usage,observed_at=r['window_start'],expires_at=r['window_end']) for r in reqs}

def quota_process(root,reqs,q):
    s=RuntimeStore(root,SimpleNamespace(policies={'p':{'quota_requirements':reqs}}));s.initialize()
    try:q.put(reserve_quota(s,{'delivery_id':'d','context':context()},observed(reqs),NOW))
    except StoreError:q.put(None)

class QuotaTests(unittest.TestCase):
    setUp = fixtures.RuntimeStoreTests.setUp
    store = fixtures.RuntimeStoreTests.store
    fixture = fixtures.RuntimeStoreTests.fixture
    ready = fixtures.RuntimeStoreTests.ready
    def setup_quota(self):
        s,ctx,_=self.ready();reqs=requirements();s.registry=SimpleNamespace(policies={'p':{'quota_requirements':reqs}})
        return s,{'delivery_id':'d','context':ctx},reqs
    def test_manual_usage_and_atomic_failure(self):
        s,ctx,reqs=self.setup_quota();obs=observed(reqs);obs[next(iter(obs))]['observed_usage']=1
        with self.assertRaises(StoreError):reserve_quota(s,ctx,obs,NOW)
        self.assertTrue(all(b['reserved']==0 for b in s.quota_buckets()))
    def test_unknown_retained_and_failed_not_released(self):
        s,ctx,reqs=self.setup_quota();rid=reserve_quota(s,ctx,observed(reqs),NOW)
        settle_quota(s,rid,'unknown');settle_quota(s,rid,'failed')
        self.assertEqual(s.get_reservation(rid)['state'],'held')
        with self.assertRaises(StoreError):reserve_quota(s,ctx,{},NOW)
        settle_quota(s,rid,'confirmed_not_submitted');self.assertEqual(s.get_reservation(rid)['state'],'released')
    def test_expiration_and_windows(self):
        s,ctx,reqs=self.setup_quota();rid=reserve_quota(s,ctx,observed(reqs),NOW)
        with self.assertRaises(StoreError):reserve_quota(s,ctx,{},NOW+timedelta(days=1))
        new=requirements(NOW+timedelta(days=1));s.registry.policies['p']['quota_requirements']=new
        next_id=reserve_quota(s,ctx,observed(new),NOW+timedelta(days=1))
        self.assertNotEqual(rid,next_id);self.assertEqual(s.get_reservation(rid)['state'],'held')
    def test_managed_settlement_in_new_total_not_double_counted(self):
        s,ctx,reqs=self.setup_quota();rid=reserve_quota(s,ctx,observed(reqs),NOW)
        s.settle_reservation(rid,now=NOW+timedelta(seconds=1))
        for r in reqs:r['limit']=2
        obs=observed(reqs,1)
        for row in obs.values():row['observed_at']=(NOW+timedelta(seconds=2)).isoformat()
        reserve_quota(s,ctx,obs,NOW+timedelta(seconds=2))
        self.assertTrue(all(b['reserved']==1 for b in s.quota_buckets()))
    def test_two_processes_only_one_reservation(self):
        s,_,reqs=self.setup_quota();mp=multiprocessing.get_context('spawn');q=mp.Queue()
        ps=[mp.Process(target=quota_process,args=(str(s.root),reqs,q)) for _ in range(2)]
        for p in ps:p.start()
        for p in ps:p.join(15);self.assertEqual(p.exitcode,0)
        self.assertEqual(sum(q.get(timeout=2) is not None for _ in ps),1)
    def test_bucket_dimensions_and_utc(self):
        args=('target','t','posts',NOW,NOW+timedelta(days=1))
        one=bucket_id(*args)
        self.assertEqual(one,bucket_id('target','t','posts','2026-10-30T09:00:00+09:00',NOW+timedelta(days=1)))
        for index,value in [(0,'owner'),(1,'other'),(2,'cost'),(3,NOW-timedelta(days=1)),(4,NOW+timedelta(days=2))]:
            changed=list(args);changed[index]=value;self.assertNotEqual(one,bucket_id(*changed))

    def test_daily_window_rollover_and_dst(self):
        daily={'window_kind':'day','timezone':'America/New_York'}
        from datetime import datetime,timezone
        for date,hours in [('2026-03-08T12:00:00+00:00',23),('2026-11-01T12:00:00+00:00',25)]:
            start,end=quota_window(daily,datetime.fromisoformat(date))
            self.assertEqual((end-start).total_seconds()/3600,hours)
        seoul={'window_kind':'day','timezone':'Asia/Seoul'}
        start,end=quota_window(seoul,NOW)
        self.assertEqual(start.isoformat(),'2026-10-29T15:00:00+00:00')
        self.assertNotEqual(quota_window(seoul,NOW+timedelta(days=1))[0],start)
    def test_daily_policy_rollover_without_registry_edit(self):
        s,ctx,reqs=self.setup_quota()
        for r in reqs:
            r.pop('window_start');r.pop('window_end');r.update(window_kind='day',timezone='Asia/Seoul')
        def observations(now):
            result={}
            for r in reqs:
                start,end=quota_window(r,now)
                result[bucket_id(r['scope_kind'],r['scope_id'],r['metric'],start,end)]=dict(observed_usage=0,observed_at=now,expires_at=end)
            return result
        one=reserve_quota(s,ctx,observations(NOW),NOW)
        later=NOW+timedelta(days=1)
        two=reserve_quota(s,ctx,observations(later),later)
        self.assertNotEqual(one,two)
    def test_missing_policy_scope_override_and_stale_observation(self):
        s,ctx,reqs=self.setup_quota()
        reqs[0]['scope_id']='wrong'
        with self.assertRaises(StoreError):reserve_quota(s,ctx,observed(reqs),NOW)
        self.assertEqual(s.quota_buckets(),[])
        reqs[0]['scope_id']='t'
        obs=observed(reqs)
        for row in obs.values():row['expires_at']=(NOW+timedelta(seconds=1)).isoformat()
        with self.assertRaises(StoreError):reserve_quota(s,ctx,obs,NOW+timedelta(seconds=2))
        s.registry=None
        with self.assertRaises(StoreError):reserve_quota(s,ctx,{},NOW)
    def test_fresh_observation_keeps_unknown_hold(self):
        s,ctx,reqs=self.setup_quota();rid=reserve_quota(s,ctx,observed(reqs),NOW)
        settle_quota(s,rid,'unknown')
        fresh=observed(reqs)
        for row in fresh.values():row['observed_at']=(NOW+timedelta(seconds=1)).isoformat()
        with self.assertRaises(StoreError):reserve_quota(s,ctx,fresh,NOW+timedelta(seconds=1))
        self.assertTrue(all(b['reserved']==1 for b in s.quota_buckets()))
    def test_settled_after_observation_still_debits(self):
        s,ctx,reqs=self.setup_quota();rid=reserve_quota(s,ctx,observed(reqs),NOW)
        s.settle_reservation(rid,now=NOW+timedelta(seconds=1))
        with self.assertRaises(StoreError):reserve_quota(s,ctx,{},NOW+timedelta(seconds=2))
        self.assertTrue(all(b['reserved']==1 for b in s.quota_buckets()))
    def test_policy_amount_cannot_be_injected_in_observation(self):
        s,ctx,reqs=self.setup_quota();obs=observed(reqs)
        obs[next(iter(obs))]['amount']=0
        with self.assertRaises(StoreError):reserve_quota(s,ctx,obs,NOW)
        self.assertEqual(s.quota_buckets(),[])
