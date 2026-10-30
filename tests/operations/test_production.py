"""제작은 fixture 공급자/임시 DB만 사용한다."""
import hashlib
import json
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from common.operations.content_store import ContentStore, StoreError, ConflictError
from common.operations.production_models import ProductionRequest, ProviderPolicy

NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)

class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.content = ContentStore(self.root); self.content.initialize()
        self.snapshot = self.content.create('personal', {'title':'측량', 'kind':'article', 'original':'원고'})
        self.job = dict(id='produce', kind='production', owner_account_id='personal', policy_revision='p1',
                        required_outputs=['text'], brief={'topic':'측량'}, execution_owner='managed',enabled=True,provider_policy_id='subscription')
        self.policy = ProviderPolicy('subscription', 'personal', ('produce',), True, ('claude-subscription',), ('text',), ())

    def store(self):
        from common.operations.production_store import ProductionStore
        store = ProductionStore(self.root,registry=SimpleNamespace(revision='registry1',jobs={'produce':self.job},policies={'p1':{}})); store.initialize(); return store

    def bind(self, store):
        return store.bind_input('produce', self.snapshot, self.job, 'registry1', create=True)

    def request(self):
        binding=self.store().bind_input('produce',self.snapshot,self.job,'registry1',create=False)
        return ProductionRequest('produce','personal',binding['binding_id']+':occurrence1',self.snapshot['id'],1,{'topic':'측량'},('text',))

    def test_binding_is_immutable_and_survives_reopen(self):
        store=self.store(); one=self.bind(store)
        self.assertEqual(one,self.bind(store))
        self.assertEqual([one], self.store().list_bindings())
        fake=dict(self.snapshot, original='위조')
        with self.assertRaises(StoreError): store.bind_input('produce',fake,self.job,'registry1',create=True)
        updated=self.content.update(self.snapshot['id'],1,{'title':'수정','kind':'article'})
        self.assertNotEqual(one['binding_id'],store.bind_input('produce',updated,self.job,'registry1',create=True)['binding_id'])
        with self.assertRaises(StoreError): store.start(self.request(),self.policy,NOW)

    def test_same_unit_reuses_result_without_second_charge(self):
        store=self.store(); self.bind(store); request=self.request()
        first=store.start(request,self.policy,NOW)
        self.assertTrue(first['claimed'])
        second=store.start(request,self.policy,NOW)
        self.assertFalse(second['claimed']); self.assertEqual(first['version'],second['version'])
        result=dict(status='blocked',reason_code='provider_unavailable',observed_usage=None)
        done=store.finish(request.production_unit_id,first['version'],result)
        self.assertEqual('blocked',done['state'])
        self.assertEqual(done['result'],store.start(request,self.policy,NOW)['result'])
        with self.assertRaises(ConflictError): store.finish(request.production_unit_id,first['version'],result)

    def test_unknown_cost_is_not_zero(self):
        from common.operations.production import validate_production_result
        result=validate_production_result({'text':'본문','assets':[]},('text',),self.root)
        self.assertIsNone(result['observed_usage'])
        self.assertEqual('completed',result['status'])

    def test_validate_all_outputs_and_assets(self):
        from common.operations.production import validate_production_result
        result=validate_production_result({'text':'본문','assets':[]},('text','pdf_document'),self.root)
        self.assertEqual('blocked',result['status'])
        path=self.root/'a.png'; path.write_bytes(b'\x89PNG\r\n\x1a\nfixture')
        asset=dict(path=str(path),filename='a.png',media_type='image/png',size=path.stat().st_size,
                   sha256=hashlib.sha256(path.read_bytes()).hexdigest(),evidence={'kind':'reuse_image','reviewed':True})
        result=validate_production_result({'text':'본문','assets':[asset]},('text','image'),self.root)
        self.assertEqual('completed',result['status'])
        path.write_bytes(b'changed')
        self.assertEqual('blocked',validate_production_result({'text':'본문','assets':[asset]},('text','image'),self.root)['status'])

    def runtime(self):
        from common.operations.runtime_store import RuntimeStore
        from common.operations.quota import bucket_id, quota_window
        rows=[dict(scope_kind=kind,scope_id=scope,metric='posts',window_kind='day',timezone='UTC',amount=1,limit=limit)
              for kind,scope,limit in [('target','t',10),('api','shared',10),('owner','personal',1)]]
        registry=SimpleNamespace(policies={'p1':{'quota_requirements':rows}})
        runtime=RuntimeStore(self.root,registry=registry,content_store=self.content);runtime.initialize()
        owner=rows[-1];start,end=quota_window(owner,NOW)
        runtime.observe_bucket(bucket_id('owner','personal','posts',start,end),1,0,NOW,end)
        return runtime

    def provider(self, callback=None):
        calls=[]
        class Provider:
            def generate(inner, request, prompt, policy):
                calls.append((request,prompt,policy))
                text=callback(request) if callback else '완성 원고'
                return dict(status='completed',text=text,provider_id='claude-subscription',execution_id='fixture-generation',observed_usage=None)
        value=Provider();value.calls=calls;return value

    def produce(self, store, runtime, provider, media=None, request=None):
        from common.operations.production import produce_content
        return produce_content(request or self.request(),provider=provider,media_runner=media or {},content_store=self.content,
                               production_store=store,runtime_store=runtime,policy=self.policy,now=NOW)

    def plan_delivery(self,runtime,snapshot,id='d',target='t',policy='p1'):
        from tests.operations.test_runtime_store import context
        ctx=replace(context(),content_id=snapshot['id'],content_revision=snapshot['revision'],manifest_hash=snapshot['manifest_hash'],
                    target_id=target,connection_id='connection-'+id,policy_revision=policy,schedule_slot=id)
        with runtime._db(True) as conn:
            conn.execute('INSERT OR IGNORE INTO runs VALUES(?,?,?,?,?,?)',('r','produce',NOW.isoformat(),'submit','fixture','{}'))
            conn.execute('INSERT INTO deliveries VALUES(?,?,?,?,?,?,?,?)',(id,snapshot['id'],snapshot['revision'],ctx.connection_id,'initial',id,'fixture','{}'))
        if runtime.get_run('r') is None: runtime.create_run('r')
        runtime.create_delivery(id,'r',ctx)
        return {'delivery_id':id,'context':ctx}

    def observations(self,rows,now):
        from common.operations.quota import bucket_id,quota_window
        observations={}
        for row in rows:
            if row['scope_kind']=='owner': continue
            start,end=quota_window(row,now)
            observations[bucket_id(row['scope_kind'],row['scope_id'],row['metric'],start,end)]={
                'observed_usage':0,'observed_at':now,'expires_at':end}
        return observations

    def test_production_and_review_never_receive_publication_capability(self):
        store=self.store(); self.bind(store);runtime=self.runtime();provider=self.provider()
        result=self.produce(store,runtime,provider)
        self.assertEqual('completed',result['status'])
        self.assertIsNone(result['observed_usage'])
        received=provider.calls[0][0]
        self.assertEqual(('text',),received.required_outputs)
        self.assertFalse(any(hasattr(received,k) for k in ('connection_id','credential','profile','permit','adapter','runtime_store')))
        again=self.produce(store,runtime,provider)
        self.assertEqual(result,again);self.assertEqual(len(provider.calls),1)
        self.assertEqual(len(runtime.list_productions()),1)
        self.assertEqual(runtime.list_productions()[0]['state'],'settled')

    def test_production_hold_is_reused_across_two_deliveries_and_next_day(self):
        from common.operations.quota import reserve_quota,bucket_id,quota_window
        store=self.store();self.bind(store);runtime=self.runtime();provider=self.provider()
        made=self.produce(store,runtime,provider);self.assertEqual('completed',made['status'])
        snapshot=self.content.get(made['content_id'])
        one=self.plan_delivery(runtime,snapshot)
        rows=runtime.registry.policies['p1']['quota_requirements']
        first=reserve_quota(runtime,one,self.observations(rows,NOW),NOW)
        rows2=json.loads(json.dumps(rows));rows2[0]['scope_id']='t2';runtime.registry.policies['p2']={'quota_requirements':rows2}
        two=self.plan_delivery(runtime,snapshot,'d2','t2','p2')
        second=reserve_quota(runtime,two,self.observations(rows2,NOW),NOW)
        later=NOW+timedelta(days=1)
        three=self.plan_delivery(runtime,snapshot,'d3','t','p1')
        third=reserve_quota(runtime,three,self.observations(rows,later),later)
        unit=self.request().production_unit_id
        for reservation in (first,second,third):self.assertEqual(runtime.get_reservation(reservation)['production_ids'],[unit])
        self.assertEqual(len(runtime.list_productions()),1)
        owner=rows[-1];start,end=quota_window(owner,NOW)
        owner_bucket=bucket_id('owner','personal','posts',start,end)
        self.assertEqual(next(b for b in runtime.quota_buckets() if b['id']==owner_bucket)['reserved'],1)
        self.assertEqual(len(runtime.get_production(unit)['requirements']),1)
        self.assertEqual(sum(b['reserved'] for b in runtime.quota_buckets()),7)

    def test_wrong_manifest_or_foreign_unit_cannot_reuse_production_hold(self):
        store=self.store();self.bind(store);runtime=self.runtime();made=self.produce(store,runtime,self.provider())
        unit=self.request().production_unit_id
        with self.assertRaises(StoreError):runtime.get_production_for_output(made['content_id'],made['revision'],'0'*64)
        with self.assertRaises(StoreError):runtime.bind_production_output('foreign',made['content_id'],made['revision'],made['manifest_hash'],expected_production_version=2)
        with self.assertRaises(StoreError):runtime.bind_production_output(unit,made['content_id'],made['revision'],made['manifest_hash'],expected_production_version=1)
        changed=self.content.update(made['content_id'],made['revision'],{'title':'수정','kind':'article','original':'변경'})
        with self.assertRaises(StoreError):runtime.get_production_for_output(changed['id'],changed['revision'],changed['manifest_hash'])
        with self.assertRaises(StoreError):runtime.get_production_for_output(made['content_id'],made['revision'],made['manifest_hash'])

    def test_unlinked_managed_evidence_never_falls_back_to_legacy_hold(self):
        from common.operations.quota import reserve_quota
        store=self.store();self.bind(store);runtime=self.runtime();made=self.produce(store,runtime,self.provider())
        snapshot=self.content.get(made['content_id']);delivery=self.plan_delivery(runtime,snapshot)
        with runtime._db(True) as conn:conn.execute('DELETE FROM production_output_links')
        before=len(runtime.list_productions())
        with self.assertRaises(StoreError):reserve_quota(runtime,delivery,self.observations(runtime.registry.policies['p1']['quota_requirements'],NOW),NOW)
        self.assertEqual(len(runtime.list_productions()),before)
        self.assertIsNone(runtime.get_reservation('unlinked'))

    def test_completed_link_crash_recovery_does_not_generate_again(self):
        store=self.store();self.bind(store);runtime=self.runtime();provider=self.provider();made=self.produce(store,runtime,provider)
        with runtime._db(True) as conn:conn.execute('DELETE FROM production_output_links')
        self.assertEqual(made,self.produce(store,runtime,provider));self.assertEqual(len(provider.calls),1)
        self.assertEqual(runtime.get_production_for_output(made['content_id'],made['revision'],made['manifest_hash'])['production_id'],self.request().production_unit_id)

    def test_cas_conflict_retains_unattached_artifacts(self):
        store=self.store();self.bind(store);runtime=self.runtime()
        artifact=self.root/'production-artifacts'/self.request().production_unit_id/'made.png'
        def generate(request):
            artifact.write_bytes(b'\x89PNG\r\n\x1a\nfixture')
            self.content.update(self.snapshot['id'],1,{'title':'사람이 수정','kind':'article'})
            return json.dumps({'text':'생성 원고','media':[{'kind':'reuse_image','manifest':{'path':str(artifact),'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest(),'source':'fixture','reuse_request_id':'user-1'}}]})
        media={'reuse_authorization':lambda **kw:dict(authorized=True,reviewed=True,**{k:kw['manifest'][k] for k in ('sha256','source','reuse_request_id')})}
        provider=self.provider(generate);result=self.produce(store,runtime,provider,media)
        self.assertEqual('conflict',result['reason_code']);self.assertTrue(artifact.is_file())
        self.assertEqual(self.content.get(self.snapshot['id'])['title'],'사람이 수정')
        self.assertEqual(self.content.get(self.snapshot['id'])['assets'],[])
        self.assertEqual(len(provider.calls),1)
        self.assertEqual(runtime.get_production(self.request().production_unit_id)['state'],'held')

    def test_media_required_outputs_use_actual_a4_fixture_provider(self):
        from common.operations.production_providers import ClaudeSubscriptionProvider
        self.job['required_outputs']=['text','image'];store=self.store();self.bind(store);runtime=self.runtime()
        request=replace(self.request(),required_outputs=('text','image'),production_unit_id='')
        artifact=self.root/'production-artifacts'/request.production_unit_id/'made.png'
        calls=[]
        def spawn(args,**kwargs):
            calls.append((args,kwargs));artifact.write_bytes(b'\x89PNG\r\n\x1a\nfixture')
            media={'kind':'reuse_image','manifest':{'path':str(artifact),'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest(),'source':'fixture','reuse_request_id':'user-1'}}
            payload={'text':'원고','media':[media]}
            return SimpleNamespace(returncode=0,stdout=json.dumps({'type':'result','is_error':False,'result':json.dumps(payload)}))
        from common.operations.production_providers import _REQUIRED_FLAGS
        spawn.capability_evidence=dict(executable='/fixture/claude',version='fixture-only',text_only_verified=True,supported_flags=list(_REQUIRED_FLAGS))
        provider=ClaudeSubscriptionProvider(Path('/fixture/claude'),'fixture-model',spawn=spawn)
        media={'reuse_authorization':lambda **kw:dict(authorized=True,reviewed=True,**{k:kw['manifest'][k] for k in ('sha256','source','reuse_request_id')})}
        result=self.produce(store,runtime,provider,media,request)
        self.assertEqual('completed',result['status']);self.assertEqual(len(calls),1)
        self.assertEqual(len(self.content.get(result['content_id'])['assets']),1)
        self.assertEqual(runtime.get_production_for_output(result['content_id'],result['revision'],result['manifest_hash'])['production_id'],request.production_unit_id)

    def test_binding_payload_tamper_is_detected_before_provider(self):
        store=self.store();binding=self.bind(store)
        with store._db(True) as conn:
            payload=dict(binding['input_payload'],brief={'topic':'위조'})
            conn.execute('UPDATE production_bindings SET input_payload=? WHERE binding_id=?',(json.dumps(payload),binding['binding_id']))
        with self.assertRaises(StoreError):store.list_bindings()

    def test_publication_cannot_select_a_foreign_completed_unit(self):
        store=self.store();self.bind(store);runtime=self.runtime();made=self.produce(store,runtime,self.provider())
        other=self.content.create('personal',{'title':'다른 콘텐츠','kind':'article','original':'원문'})
        delivery=self.plan_delivery(runtime,other)
        unit=self.request().production_unit_id
        rows=runtime.registry.policies['p1']['quota_requirements']
        runtime.observe_bucket('target-fixture',10,0,NOW,NOW+timedelta(hours=1))
        with self.assertRaises(StoreError):
            runtime.reserve_quota(delivery['delivery_id'],[{'bucket_id':'target-fixture','amount':1}],NOW,
                production_requirements=[{'production_id':unit,'requirements':runtime.get_production(unit)['requirements']}])

    def test_missing_budget_and_unknown_provider_do_not_execute_twice(self):
        store=self.store();self.bind(store);runtime=self.runtime();provider=self.provider()
        runtime.registry.policies['p1']['quota_requirements']=[]
        result=self.produce(store,runtime,provider)
        self.assertEqual(result['reason_code'],'quota_policy_required');self.assertEqual(provider.calls,[])
        self.assertEqual(result,self.produce(store,runtime,provider))

    def test_pdf_requires_all_pages_checked(self):
        from common.operations.production import validate_production_result
        path=self.root/'answer.pdf';path.write_bytes(b'%PDF-1.4\nfixture\n%%EOF\n')
        asset=dict(path=str(path),filename=path.name,media_type='application/pdf',size=path.stat().st_size,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),evidence={'kind':'pdf_document',
                'parser':{'safe_parser':True,'encrypted':False,'page_count':2},
                'pages':[{'page_number':1,'checked':True,'rendered_sha256':'a'*64}]})
        self.assertEqual('blocked',validate_production_result({'text':'본문','assets':[asset]},('text','pdf'),self.root)['status'])
        asset['evidence']['pages'].append({'page_number':2,'checked':True,'rendered_sha256':'b'*64})
        self.assertEqual('completed',validate_production_result({'text':'본문','assets':[asset]},('text','pdf'),self.root)['status'])
        # ContentStore는 위 self-claim을 받지 않고 서버 고정 parser로 다시 검증한다.
        with self.assertRaises(StoreError):self.content.add_asset(self.snapshot['id'],1,path.name,'application/pdf',path.read_bytes())

    def test_start_requires_current_server_registry_and_exact_binding_occurrence(self):
        from common.operations.production_store import ProductionStore
        store=self.store();self.bind(store);request=self.request()
        before=(self.root/'operations.sqlite3').read_bytes()
        with self.assertRaises(StoreError):ProductionStore(self.root).start(request,self.policy,NOW)
        self.assertEqual(before,(self.root/'operations.sqlite3').read_bytes())
        for field,value in [('revision','changed')]:
            original=getattr(store.registry,field);setattr(store.registry,field,value)
            with self.assertRaises(StoreError):store.start(request,self.policy,NOW)
            setattr(store.registry,field,original)
        for field,value in [('enabled',False),('policy_revision','new'),('owner_account_id','dept')]:
            original=self.job[field];self.job[field]=value
            with self.assertRaises(StoreError):store.start(request,self.policy,NOW)
            self.job[field]=original
        with self.assertRaises(StoreError):store.start(replace(request,occurrence_id='arbitrary',production_unit_id=''),self.policy,NOW)
        self.assertEqual(before,(self.root/'operations.sqlite3').read_bytes())

    def test_produced_manifest_gets_separate_calc_and_source_execution_evidence(self):
        from common.operations.review_runner import RegisteredReviewRunner,SubscriptionReviewProvider,run_reviews
        store=self.store();self.bind(store);runtime=self.runtime();made=self.produce(store,runtime,self.provider())
        calls=[]
        class Reviewer:
            def __init__(inner, role):inner.role=role
            def generate(inner,request,prompt,policy):
                calls.append((inner.role,request,prompt))
                return dict(status='completed',text='{"verdict":"pass","findings":[]}',execution_id='fixture-review-'+inner.role)
        registered={role:SubscriptionReviewProvider(Reviewer(role),request=self.request(),policy=self.policy,principal_id=role) for role in ('calc','source')}
        runner=RegisteredReviewRunner(registered,source_checker=lambda snapshot:dict(available=True,checked=True),
            calculation_runner=lambda snapshot:dict(available=True,checked=True,results=[{'matches':True}]))
        snapshot=self.content.get(made['content_id'])
        result=run_reviews(snapshot,producer=made['producer'],authorities={'review_authorities':{'calc':['calc'],'source':['source']},'require_calc_review':True},
                           runner=runner,runtime_store=runtime,now=NOW)
        self.assertEqual('completed',result['status']);self.assertEqual([c[0] for c in calls],['calc','source'])
        self.assertEqual(len({made['producer']['execution_id'],*[r['execution_id'] for r in result['reports']]}),3)
        self.assertEqual(len({made['producer']['principal_id'],*[r['reviewer_id'] for r in result['reports']]}),3)
        evidence=runtime.read_content_evidence(snapshot['id'],snapshot['revision'],snapshot['manifest_hash'])
        self.assertEqual(len(evidence),3)
        self.assertFalse(any(word in calls[0][2] for word in ('credential_ref','profile_ref','permit_nonce')))

if __name__ == '__main__': unittest.main()
