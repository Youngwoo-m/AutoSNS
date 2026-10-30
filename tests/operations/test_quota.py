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
    def second_delivery(self,s,original):
        from dataclasses import replace
        import sqlite3,json
        other=replace(original,target_id='t2',connection_id='y',policy_revision='p2')
        c=sqlite3.connect(s.root/'operations.sqlite3')
        c.execute('INSERT INTO deliveries VALUES(?,?,?,?,?,?,?,?)',('d2','c',1,'y','initial','s','hash',json.dumps({'status':'ready'})))
        c.commit();c.close();s.create_delivery('d2','r',other)
        reqs=requirements()
        for r in reqs:
            if r['scope_kind']=='target':r['scope_id']='t2';r['limit']=10
            elif r['scope_kind']=='api':r['limit']=10
        s.registry.policies['p2']={'quota_requirements':reqs}
        return {'delivery_id':'d2','context':other},reqs
    def test_same_original_two_channels_charge_owner_once(self):
        s,ctx,reqs=self.setup_quota()
        for r in reqs:
            if r['scope_kind']!='owner':r['limit']=10
        two,other=self.second_delivery(s,ctx['context'])
        one_id=reserve_quota(s,ctx,observed(reqs),NOW)
        two_id=reserve_quota(s,two,observed(other),NOW)
        self.assertNotEqual(one_id,two_id)
        owner=bucket_id('owner','personal','posts',NOW,NOW+timedelta(days=1))
        self.assertEqual(next(b for b in s.quota_buckets() if b['id']==owner)['reserved'],1)
        self.assertEqual(s.get_reservation(one_id)['production_ids'],s.get_reservation(two_id)['production_ids'])
        api=bucket_id('api','shared','posts',NOW,NOW+timedelta(days=1))
        self.assertEqual(next(b for b in s.quota_buckets() if b['id']==api)['reserved'],2)
        self.assertEqual(sum(b['reserved'] for b in s.quota_buckets() if b['id'] not in (owner,api)),2)
    def test_separate_production_needs_additional_owner_budget(self):
        s,ctx,reqs=self.setup_quota()
        for r in reqs:
            if r['scope_kind']!='owner':r['limit']=10
        two,other=self.second_delivery(s,ctx['context'])
        other[-1]['production_id']='separate-render'
        reserve_quota(s,ctx,observed(reqs),NOW)
        with self.assertRaises(StoreError):reserve_quota(s,two,observed(other),NOW)
        self.assertEqual(s.list_productions().__len__(),1)
        other[-1]['limit']=2
        reserve_quota(s,two,observed(other),NOW)
        self.assertEqual(len(s.list_productions()),2)
    def test_production_lifecycle_separate_from_delivery_release(self):
        s,ctx,reqs=self.setup_quota();rid=reserve_quota(s,ctx,observed(reqs),NOW)
        production=s.get_reservation(rid)['production_ids'][0]
        settle_quota(s,rid,'confirmed_not_submitted')
        self.assertEqual(s.get_production(production)['state'],'held')
        s.settle_production(production,now=NOW)
        self.assertEqual(s.get_production(production)['state'],'settled')
        self.assertEqual(s.get_reservation(rid)['state'],'released')
    def test_production_unknown_shared_hold_cannot_be_released(self):
        s,ctx,reqs=self.setup_quota()
        for r in reqs:
            if r['scope_kind']!='owner':r['limit']=10
        two,other=self.second_delivery(s,ctx['context'])
        one=reserve_quota(s,ctx,observed(reqs),NOW)
        second=reserve_quota(s,two,observed(other),NOW)
        production=s.get_reservation(one)['production_ids'][0]
        settle_quota(s,one,'confirmed_not_submitted');settle_quota(s,second,'unknown')
        with self.assertRaises(StoreError):s.settle_production(production,release=True,now=NOW)
        self.assertEqual(s.get_production(production)['state'],'held')
        settle_quota(s,second,'submitted')
        self.assertEqual(s.get_production(production)['state'],'settled')
    def test_repost_next_period_keeps_original_production_charge(self):
        s,ctx,reqs=self.setup_quota();one=reserve_quota(s,ctx,observed(reqs),NOW)
        settle_quota(s,one,'submitted')
        later=NOW+timedelta(days=1);new=requirements(later)
        s.registry.policies['p']['quota_requirements']=new
        owner=bucket_id('owner','personal','posts',later,later+timedelta(days=1))
        obs=observed(new);obs.pop(owner)
        two=reserve_quota(s,ctx,obs,later)
        self.assertEqual(s.get_reservation(one)['production_ids'],s.get_reservation(two)['production_ids'])
        self.assertEqual(len(s.list_productions()),1)
        self.assertFalse(any(b['id']==owner for b in s.quota_buckets()))
    def test_started_unknown_keeps_all_usage_then_real_result_settles(self):
        s,ctx,reqs=self.setup_quota();rid=reserve_quota(s,ctx,observed(reqs),NOW)
        from common.operations.runtime_models import RunLease
        run=s.get_run('r')
        lease=RunLease('r',run['worker_id'],run['generation'],run['lease_expires_at'])
        attempt=s.create_attempt('d',s.get_delivery('d')['version'],lease,ctx['context'].context_hash,'approval',reservation_id=rid,now=NOW)
        permit=s.issue_permit(attempt['id'],lease,ctx['context'].context_hash,'approval',NOW)
        s.consume_permit(permit,lease,NOW)
        with self.assertRaises(StoreError):settle_quota(s,rid,'confirmed_not_posted')
        self.assertEqual(s.get_production(s.get_reservation(rid)['production_ids'][0])['state'],'held')
        s.finish_attempt(attempt['id'],'submitted',remote_id='remote-exact',now=NOW)
        settle_quota(s,rid,'submitted')
        self.assertEqual(s.get_reservation(rid)['state'],'settled')
        self.assertEqual(s.get_production(s.get_reservation(rid)['production_ids'][0])['state'],'settled')
    def test_owner_daily_and_long_period_share_one_production(self):
        s,ctx,reqs=self.setup_quota()
        for r in reqs:
            if r['scope_kind']!='owner':r['limit']=10
        long=dict(reqs[-1],window_end=(NOW+timedelta(days=30)).isoformat(),limit=30)
        reqs.append(long)
        two,other=self.second_delivery(s,ctx['context']);other.append(dict(long))
        first=reserve_quota(s,ctx,observed(reqs),NOW)
        second=reserve_quota(s,two,observed(other),NOW)
        self.assertEqual(len(s.list_productions()),1)
        production=s.get_production(s.get_reservation(first)['production_ids'][0])
        self.assertEqual(len(production['requirements']),2)
        self.assertEqual(s.get_reservation(first)['production_ids'],s.get_reservation(second)['production_ids'])
        for r in (reqs[-2],long):
            id=bucket_id('owner','personal','posts',r['window_start'],r['window_end'])
            self.assertEqual(next(b for b in s.quota_buckets() if b['id']==id)['reserved'],1)
        s.settle_production(production['id'],now=NOW)
        self.assertEqual(s.get_production(production['id'])['state'],'settled')
        later=NOW+timedelta(days=1);new=requirements(later)
        new[0]['limit']=10;new[1]['limit']=10;new.append(dict(long))
        s.registry.policies['p']['quota_requirements']=new
        obs=observed(new)
        for r in new:
            id=bucket_id(r['scope_kind'],r['scope_id'],r['metric'],r['window_start'],r['window_end'])
            if r['scope_kind']=='owner':obs.pop(id)
        reserve_quota(s,ctx,obs,later)
        self.assertEqual(len(s.list_productions()),1)
        self.assertEqual(s.get_production(production['id'])['requirements'],production['requirements'])
    def test_owner_any_period_insufficient_rolls_back_all_reservations(self):
        s,ctx,reqs=self.setup_quota()
        reqs.append(dict(reqs[-1],window_end=(NOW+timedelta(days=30)).isoformat(),limit=30))
        for blocked in (reqs[-1],reqs[-2]):
            with self.subTest(period=blocked['window_end']):
                obs=observed(reqs)
                id=bucket_id('owner','personal','posts',blocked['window_start'],blocked['window_end'])
                obs[id]['observed_usage']=blocked['limit']
                with self.assertRaises(StoreError):reserve_quota(s,ctx,obs,NOW)
                self.assertEqual(s.list_productions(),[])
                self.assertTrue(all(b['reserved']==0 for b in s.quota_buckets()))
