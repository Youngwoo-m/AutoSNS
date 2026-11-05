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
        # 서버 adapter 아래 generate 경계의 비모델 fixture. 운영 registry에는 등록하지 않는다.
        class Provider:
            def generate(inner, request, prompt, policy):
                import json
                from uuid import uuid4
                self.calls.append(json.loads(prompt.split('\n',1)[1]))
                return {'status':'completed','execution_id':'fixture-provider-'+uuid4().hex,
                        'text':json.dumps({'verdict':verdict,**extra})}
        providers={principal:api('SubscriptionReviewProvider')(Provider(),request='server-request',policy='server-policy',principal_id=principal)
                   for principal in ('calc-principal','source-principal')}
        return api('RegisteredReviewRunner')(providers,source_checker=lambda snapshot:{'available':True,'checked':True,'sources':['https://example.org/original']},calculation_runner=lambda snapshot:{'available':True,'checked':True,'results':[{'actual':3,'expected':3}]})

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
            self.assertEqual(set(call),{'role','snapshot','evidence'})
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
        adapters={p:api('SubscriptionReviewProvider')(Provider(),request='server-request',policy='server-policy',principal_id=p) for p in ('calc-principal','source-principal')}
        runner=api('RegisteredReviewRunner')(adapters,source_checker=lambda snapshot:{'available':True,'checked':True},calculation_runner=lambda snapshot:{'available':True,'checked':True})
        result=self.run_reviews(runner)
        self.assertEqual(result['status'],'completed')
        self.assertEqual([r['execution_id'] for r in result['reports']],['server-provider-calc','server-provider-source'])
        class ReusedProvider:
            def generate(inner,*args):return {'status':'completed','execution_id':'generation','text':'{"verdict":"pass"}'}
        runner.providers={p:api('SubscriptionReviewProvider')(ReusedProvider(),request='server-request',policy='server-policy',principal_id=p) for p in ('calc-principal','source-principal')}
        result=self.run_reviews(runner)
        self.assertEqual(result['status'],'blocked')
        self.assertEqual(result['reports'],[])

    def test_provider_text_identity_claim_is_rejected_by_actual_adapter(self):
        class Provider:
            def generate(inner,*args):return {'status':'completed','execution_id':'fresh-server-execution','text':'{"verdict":"pass","reviewer_id":"forged"}'}
        runner=self.runner();runner.providers={p:api('SubscriptionReviewProvider')(Provider(),request='server-request',policy='server-policy',principal_id=p) for p in ('calc-principal','source-principal')}
        result=self.run_reviews(runner)
        self.assertEqual(result['status'],'blocked')
        self.assertFalse(any(r['verdict']=='pass' for r in result['reports']))

    def test_bare_pass_callbacks_do_not_become_actual_provider_executions(self):
        def callback(**kwargs):
            self.calls.append(kwargs)
            return {'verdict':'pass'}
        runner=api('RegisteredReviewRunner')({'calc-principal':callback,'source-principal':callback},
                source_checker=lambda snapshot:{'available':True,'checked':True},calculation_runner=lambda snapshot:{'available':True,'checked':True})
        result=self.run_reviews(runner)
        self.assertEqual(result['status'],'blocked')
        self.assertEqual(result['reports'],[])
        rows=self.runtime.read_content_evidence(self.snapshot['id'],1,self.snapshot['manifest_hash'])
        self.assertFalse(any(row['kind']=='independent_review' for row in rows))

    def test_custom_runner_mapping_cannot_assert_actual_execution(self):
        class Runner:
            def execute(inner,**kwargs):return {'executed':True,'verdict':'pass','execution_id':'invented-'+kwargs['role']}
        result=self.run_reviews(Runner())
        self.assertEqual(result['status'],'blocked');self.assertEqual(result['reports'],[])

    def test_adapter_principal_registration_must_match_server_authority(self):
        runner=self.runner()
        runner.providers['calc-principal']=runner.providers['source-principal']
        result=self.run_reviews(runner)
        self.assertEqual(result['outcomes']['calc'],'unclear')
        self.assertFalse(any(r['role']=='calc' for r in result['reports']))

    def test_registered_a4_provider_executes_two_local_fixture_children(self):
        # A4 실제 .generate 코드/ID 생성과 자식 프로세스를 연결한다. 모델 CLI는 실행하지 않는다.
        import json
        import subprocess
        import sys
        from common.operations.production_providers import ClaudeSubscriptionProvider
        from common.operations.production_models import ProductionRequest, ProviderPolicy
        observations=Path(self.tmp.name)/'child-observations';observations.mkdir()
        script='''import json,os,pathlib,sys
prompt=sys.stdin.read()
payload=json.loads(prompt.split('\\n',1)[1])
args=sys.argv[2:]
assert args[args.index('--tools')+1] == ''
assert args[args.index('--model')+1] == 'fixture-explicit-model'
assert args[args.index('--mcp-config')+1] == '{"mcpServers":{}}'
assert '--no-session-persistence' in args
record={'pid':os.getpid(),'role':payload['role'],'cwd':os.getcwd(),'snapshot':payload['snapshot']}
pathlib.Path(sys.argv[1],str(os.getpid())+'.json').write_text(json.dumps(record))
print(json.dumps({'type':'result','is_error':False,'result':json.dumps({'verdict':'pass','findings':[]})}))
'''
        def spawn(args,**kwargs):
            return subprocess.run([sys.executable,'-c',script,str(observations),*args[1:]],**kwargs)
        executable=Path('/usr/local/bin/fixture-claude-never-invoked')
        spawn.capability_evidence={'executable':str(executable),'version':'fixture-only', 'text_only_verified':True,
                'supported_flags':['-p','--model','--tools','--setting-sources','--strict-mcp-config','--mcp-config','--disable-slash-commands','--no-session-persistence','--output-format','--verbose']}
        provider=ClaudeSubscriptionProvider(executable,'fixture-explicit-model',spawn=spawn)
        request=ProductionRequest('review-fixture','personal','review-occurrence',self.snapshot['id'],1,{'task':'review'},('text',))
        policy=ProviderPolicy('fixture','personal',('review-fixture',),True,('claude-subscription',),('text',),())
        adapters={p:api('SubscriptionReviewProvider')(provider,request=request,policy=policy,principal_id=p) for p in ('calc-principal','source-principal')}
        runner=api('RegisteredReviewRunner')(adapters,source_checker=lambda snapshot:{'available':True,'checked':True},
                calculation_runner=lambda snapshot:api('calculate_registered_inputs')([{'operation':'add','operands':['1','2'],'expected':'3','tolerance':'0','unit':'m'}]))
        result=self.run_reviews(runner)
        self.assertEqual(result['status'],'completed')
        observed=[json.loads(path.read_text()) for path in observations.glob('*.json')]
        self.assertEqual({o['role'] for o in observed},{'calc','source'})
        self.assertEqual(len({o['pid'] for o in observed}),2)
        self.assertEqual(len({r['execution_id'] for r in result['reports']}),2)
        self.assertTrue(all(r['execution_id'].startswith('production-execution-') for r in result['reports']))
        for child in observed:
            self.assertEqual(child['snapshot']['manifest_hash'],self.snapshot['manifest_hash'])
            self.assertFalse(Path(child['cwd']).exists())
