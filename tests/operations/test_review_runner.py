"""실제 SQLite의 불변 증거와 서버 권한/실행 신원을 시험한다."""
import importlib
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from common.operations.content_store import ContentStore
from common.operations.runtime_store import RuntimeStore
from common.operations.publication_gate import report_hash, validate_reviews
from types import SimpleNamespace

NOW=datetime(2026,10,31,tzinfo=timezone.utc)

def api(name):
    try:module=importlib.import_module('common.operations.review_runner')
    except ModuleNotFoundError:module=None
    value=getattr(module,name,None)
    if value is None:raise AssertionError(f'독립 검토 계약 구현 누락: {name}')
    return value


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.content=ContentStore(Path(self.tmp.name));self.content.initialize()
        self.snapshot=self.content.create('personal',{'title':'답안','kind':'article','original':'1+2=3'})
        self.runtime=RuntimeStore(Path(self.tmp.name),content_store=self.content);self.runtime.initialize()
        self.producer={'principal_id':'author','execution_id':'generation'}
        self.authorities={'review_authorities':{'calc-principal':['calc'],'source-principal':['source']},'require_calc_review':True}
        self.calls=[]

    def runner(self, verdict='pass', **extra):
        def provider(**kwargs):
            self.calls.append(kwargs)
            return {'verdict':verdict,**extra}
        return api('RegisteredReviewRunner')({'calc-principal':provider,'source-principal':provider},source_checker=lambda snapshot:{'available':True,'checked':True,'sources':['https://example.org/original']},calculation_runner=lambda snapshot:{'available':True,'checked':True,'results':[{'actual':3,'expected':3}]})

    def run_reviews(self, runner=None, authorities=None):
        return api('run_reviews')(self.snapshot,producer=self.producer,authorities=authorities or self.authorities,runner=runner or self.runner(),runtime_store=self.runtime,now=NOW)

    def test_review_identity_and_hash_are_server_owned(self):
        result=self.run_reviews()
        self.assertEqual(result['status'],'completed');self.assertEqual([c['role'] for c in self.calls],['calc','source'])
        reports=result['reports'];self.assertEqual(len(reports),2)
        self.assertEqual({r['reviewer_id'] for r in reports},{'calc-principal','source-principal'})
        self.assertEqual(len({self.producer['execution_id'],*[r['execution_id'] for r in reports]}),3)
        rows=self.runtime.read_content_evidence(self.snapshot['id'],1,self.snapshot['manifest_hash'])
        self.assertEqual(len(rows),3)
        ctx=SimpleNamespace(content_id=self.snapshot['id'],content_revision=1,manifest_hash=self.snapshot['manifest_hash'])
        hashes=validate_reviews(result,self.authorities,ctx,[{'kind':r['kind'],'evidence':r['report']} for r in rows],NOW)
        self.assertEqual(set(hashes),{r['report_hash'] for r in reports})
        for r in reports:self.assertEqual(r['report_hash'],report_hash(r))

    def test_provider_cannot_assert_identity_or_hash(self):
        for key in ('principal_id','reviewer_id','execution_id','report_hash','content_revision','checked_at'):
            with self.subTest(key=key):
                result=self.run_reviews(self.runner(**{key:'forged'}))
                self.assertEqual(result['status'],'blocked')
                self.assertFalse(any(r['verdict']=='pass' for r in result['reports']))

    def test_same_principal_cannot_produce_or_review_both_roles(self):
        for authority in ({'review_authorities':{'author':['source']}},{'review_authorities':{'same':['calc','source']},'require_calc_review':True}):
            self.assertEqual(self.run_reviews(authorities=authority)['status'],'blocked')
        self.assertEqual(self.calls,[])

    def test_missing_source_and_calc_evidence_remains_unclear(self):
        for role in ('source','calc'):
            runner=self.runner()
            if role=='source':runner.source_checker=None
            else:runner.calculation_runner=None
            result=self.run_reviews(runner)
            self.assertEqual(result['status'],'blocked');self.assertEqual(result['outcomes'][role],'unclear')
            self.assertFalse(any(r['role']==role and r['verdict']=='pass' for r in result['reports']))

    def test_fix_and_unclear_never_become_pass(self):
        for verdict in ('fix','unclear'):
            result=self.run_reviews(self.runner(verdict))
            self.assertEqual(result['status'],'blocked')
            self.assertEqual({r['verdict'] for r in result['reports']},{verdict})

    def test_two_fix_cycles_stay_blocked(self):
        result=self.run_reviews(authorities=dict(self.authorities,fix_cycles=2))
        self.assertEqual(result['reason_code'],'fix_cycle_limit');self.assertEqual(self.calls,[])

    def test_asset_change_invalidates_reviews(self):
        result=self.run_reviews()
        changed=self.content.update(self.snapshot['id'],1,{'title':'변경','kind':'article','original':'다른 원고'})
        self.assertEqual(self.runtime.read_content_evidence(changed['id'],2,changed['manifest_hash']),[])
        ctx=SimpleNamespace(content_id=changed['id'],content_revision=2,manifest_hash=changed['manifest_hash'])
        old=self.runtime.read_content_evidence(self.snapshot['id'],1,self.snapshot['manifest_hash'])
        with self.assertRaises(Exception):validate_reviews(result,self.authorities,ctx,[{'kind':r['kind'],'evidence':r['report']} for r in old],NOW)
        self.assertEqual(self.run_reviews()['reason_code'],'content_changed')

    def test_production_and_review_never_receive_publication_capability(self):
        self.snapshot=dict(self.snapshot,connection_id='secret-target',permit='secret-permit',credential_ref='secret-ref',asset_bytes={'a':b'private'})
        result=self.run_reviews();self.assertEqual(result['status'],'completed')
        for call in self.calls:
            self.assertEqual(set(call),{'role','snapshot','evidence','execution_id'})
            for key in ('permit','connection_id','credential_ref','asset_bytes'):self.assertNotIn(key,call['snapshot'])

    def test_unregistered_reviewer_is_unclear_and_is_not_recorded_as_executed(self):
        runner=api('RegisteredReviewRunner')({},source_checker=lambda snapshot:{'available':True,'checked':True},calculation_runner=lambda snapshot:{'available':True,'checked':True})
        result=self.run_reviews(runner)
        self.assertEqual(result['status'],'blocked');self.assertEqual(result['reports'],[])

    def test_fixed_calculator_accepts_only_schema_and_never_executes_code(self):
        calc=api('calculate_registered_inputs')
        self.assertEqual(calc([{'operation':'add','operands':['1','2'],'expected':'3','tolerance':'0','unit':'m'}])['results'][0]['actual'],'3')
        result=calc([{'operation':'python','code':'raise AssertionError()'}])
        self.assertFalse(result['available'])

    def test_snapshot_payload_cannot_impersonate_server_manifest(self):
        self.snapshot=dict(self.snapshot,original='이 manifest와 다른 위조 원고')
        result=self.run_reviews()
        self.assertEqual(result['status'],'blocked');self.assertEqual(result['reason_code'],'content_changed')
        self.assertEqual(self.calls,[])

    def test_actual_provider_execution_identity_is_retained_and_duplicates_rejected(self):
        class Provider:
            def generate(inner,request,prompt,policy):
                import json
                payload=json.loads(prompt.split('\n',1)[1])
                self.calls.append(payload)
                return {'status':'completed','execution_id':'server-provider-'+payload['role'], 'text':'{"verdict":"pass"}'}
        adapter=api('SubscriptionReviewProvider')(Provider(),request='server-request',policy='server-policy')
        runner=api('RegisteredReviewRunner')({'calc-principal':adapter,'source-principal':adapter},source_checker=lambda snapshot:{'available':True,'checked':True},calculation_runner=lambda snapshot:{'available':True,'checked':True})
        result=self.run_reviews(runner)
        self.assertEqual(result['status'],'completed')
        self.assertEqual([r['execution_id'] for r in result['reports']],['server-provider-calc','server-provider-source'])
        class ReusedProvider:
            def generate(inner,*args):return {'status':'completed','execution_id':'generation','text':'{"verdict":"pass"}'}
        repeated=api('SubscriptionReviewProvider')(ReusedProvider(),request='server-request',policy='server-policy')
        runner.providers={'calc-principal':repeated,'source-principal':repeated}
        result=self.run_reviews(runner)
        self.assertEqual(result['status'],'blocked')
        self.assertEqual(result['reports'],[])

    def test_provider_text_identity_claim_is_rejected_by_actual_adapter(self):
        class Provider:
            def generate(inner,*args):return {'status':'completed','execution_id':'fresh-server-execution','text':'{"verdict":"pass","reviewer_id":"forged"}'}
        adapter=api('SubscriptionReviewProvider')(Provider(),request='server-request',policy='server-policy')
        runner=self.runner();runner.providers={'calc-principal':adapter,'source-principal':adapter}
        result=self.run_reviews(runner)
        self.assertEqual(result['status'],'blocked')
        self.assertFalse(any(r['verdict']=='pass' for r in result['reports']))
