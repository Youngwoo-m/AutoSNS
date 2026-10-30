"""운영 HTTP 경계: 임시 루트만 사용한다."""
import http.client
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

APP=Path(__file__).resolve().parents[1]/'ax-console/app'
sys.path.insert(0,str(APP))

class Auth:
    KEYFILE=None
    def cookie_of(self,h):return h
    def check(self,t):return t=='fixture'
    def is_setup(self):return True

class OperationsHTTPTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('ops_server',APP/'web_server.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);self.source=root/'source';self.source.mkdir();self.workspace=root/'workspace'
        self.server=module.create_server(source_root=self.source,workspace_root=self.workspace,web_root=APP/'web',auth_backend=Auth())
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.stop)
    def stop(self):self.server.shutdown();self.server.server_close();self.thread.join()
    def request(self,path,method='GET',body=None,auth=True,origin=None):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        headers={'Content-Type':'application/json'}
        if auth:headers['Cookie']='fixture'
        if origin:headers['Origin']=origin
        try:
            c.request(method,path,json.dumps(body) if body is not None else None,headers)
            r=c.getresponse();return r.status,json.loads(r.read())
        finally:c.close()
    def test_get_no_writes_auth_and_queries(self):
        self.assertEqual(self.request('/api/v2/operations',auth=False)[0],401)
        self.assertEqual(self.request('/api/v2/operations',origin='http://evil.test')[0],403)
        status,data=self.request('/api/v2/operations?account=personal');self.assertEqual(status,200)
        self.assertEqual(set(data),{'items','summary','control','execution_enabled','blockers'})
        self.assertEqual(data['items'],[]);self.assertFalse(data['execution_enabled'])
        self.assertFalse(self.workspace.exists());self.assertEqual(list(self.source.iterdir()),[])
        for query in ('account=bad','account=all&account=dept','enabled=true'):
            self.assertEqual(self.request('/api/v2/operations?'+query)[0],400)
    def test_controls_idempotent_cas_no_enqueue_and_overrides(self):
        self.server.runtime_store.initialize()
        body=dict(scope='managed',id='all',action='pause',expected_version=0,request_key='pause-one',reason='확인')
        status,result=self.request('/api/v2/control','POST',body);self.assertEqual(status,200)
        self.assertEqual(self.request('/api/v2/control','POST',body),(200,result))
        self.assertEqual(self.request('/api/v2/control','POST',dict(body,request_key='stale'))[0],409)
        self.assertEqual(self.request('/api/v2/control','POST',dict(body,actor='admin'))[0],400)
        body.update(action='resume',expected_version=1,request_key='resume-one')
        self.assertEqual(self.request('/api/v2/control','POST',body)[0],200)
        self.assertEqual(self.server.runtime_store.list_runs(),[])
        self.assertEqual(list(self.source.iterdir()),[])
    def test_detail_redaction_and_default_blocks(self):
        id='delivery_'+'a'*32
        store=self.server.runtime_store
        row=dict(id=id,run_id='run_abc',state='unknown',version=2,context=dict(owner_account_id='personal',destination_account_id='dept',connection_id='dept.youtube',platform='youtube',options={'token':'SECRET'},profile='/SECRET'),remote_id='remote',remote_uncertain=True)
        store.get_delivery=lambda _:row
        store.list_operations=lambda account:[row] if account in ('all','personal','dept') else []
        store.attempts=lambda _:[dict(id='attempt_a',outcome='unknown',nonce_hash='SECRET',result={'evidence':{'path':'/SECRET'}})]
        store.events=lambda _:[dict(kind='lookup',evidence={'token':'SECRET','note':'/SECRET','url':'https://example.test/?token=SECRET'})]
        status,data=self.request('/api/v2/operations/'+id);self.assertEqual(status,200)
        self.assertNotIn('SECRET',json.dumps(data));self.assertIn('attempts',data);self.assertEqual(data['available_actions'],['resolve']);self.assertEqual(data['available_resolution_kinds'],['cancel_local'])
        for action,code in [('retry','execution_disabled'),('reconcile','adapter_unavailable'),('resolve','adapter_unavailable')]:
            body=dict(expected_version=2,request_key=action)
            if action=='resolve':body.update(kind='link_existing',evidence={'remote_id':'remote'},note='확인')
            status,data=self.request('/api/v2/operations/'+id+'/'+action,'POST',body)
            self.assertEqual(status,409);self.assertEqual(data['code'],code)
            self.assertEqual(self.request('/api/v2/operations/'+id+'/'+action,'POST',dict(body,enabled=True))[0],400)
        self.assertEqual(self.request('/api/v2/operations/'+id+'?account=all')[0],400)
        self.assertEqual(self.request('/api/v2/operations/invalid')[0],404)

    def test_actual_recovery_http_cancel_replay_and_forgery(self):
        fixture=RecoveryAPIIntegrationTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.server.runtime_store=fixture.store
        self.server.operations_clock=lambda:fixture.now
        url='/api/v2/operations/'+fixture.id
        body=fixture.decision()
        status,first=self.request(url+'/resolve','POST',body);self.assertEqual(status,200)
        self.assertTrue(first['remote_uncertain']);self.assertEqual(first['state'],'cancelled')
        self.assertEqual(self.request(url+'/resolve','POST',body),(200,first))
        self.assertEqual(self.request(url+'/resolve','POST',dict(body,note='changed'))[0],409)
        for field in ('actor','process_probe','lock_probe','adapter','executor','credential'):
            self.assertEqual(self.request(url+'/resolve','POST',dict(body,**{field:True}))[0],400)
        self.assertEqual(self.request(url+'/resolve','POST',body,auth=False)[0],401)
        self.assertEqual(self.request(url+'/resolve','POST',body,origin='http://evil.test')[0],403)
        self.assertEqual(self.request(url+'/resolve?account=all','POST',body)[0],400)
        self.assertEqual(self.request(url+'/retry','POST',{'expected_version':first['version'],'request_key':'retry'})[1]['code'],'execution_disabled')

    def test_actual_retry_http_uses_server_policy_and_same_run_target(self):
        from common.operations.runtime_models import ExecutionPolicy
        from tests.operations.test_dispatch import registry,request
        from datetime import timedelta
        import sqlite3
        fixture=RecoveryAPIIntegrationTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.server.runtime_store=fixture.store;self.server.ledger.registry=registry
        self.server.execution_policy=ExecutionPolicy(True,('x',),'cutover')
        self.server.process_probe=lambda i:dict(i,status='dead')
        self.server.lock_probe=lambda c:dict(status='free',connection_id=c['connection_id'])
        self.server.operations_clock=lambda:fixture.now+timedelta(minutes=2)
        url='/api/v2/operations/'+fixture.id
        # unknown을 그대로 재개하면 원격 조회/제출 없이 거부한다.
        decision=dict(expected_version=fixture.store.get_delivery(fixture.id)['version'],request_key='unknown-retry')
        db=sqlite3.connect(fixture.root/'operations.sqlite3')
        try:
            with db:db.execute('UPDATE runs SET payload=? WHERE id=?',(json.dumps(request()),'r'))
        finally:db.close()
        self.assertEqual(self.request(url+'/retry','POST',decision)[0],409)
        confirm=fixture.decision('confirmed_not_posted');confirm['evidence']={'confirmed_not_posted':True}
        status,resolved=self.request(url+'/resolve','POST',confirm);self.assertEqual(status,200)
        decision=dict(expected_version=resolved['version'],request_key='http-retry')
        status,result=self.request(url+'/retry','POST',decision);self.assertEqual(status,200)
        self.assertEqual(result['id'],fixture.id);self.assertEqual(result['run_id'],'r');self.assertEqual(result['state'],'queued')
        self.assertEqual(self.request(url+'/retry','POST',decision),(200,result))
        self.assertEqual(len(fixture.store.list_runs()),1)


class OperationsBoundaryTests(unittest.TestCase):
    def test_operations_module_provides_strict_handler(self):
        spec=importlib.util.find_spec('web_operations')
        self.assertIsNotNone(spec,'독립 운영 API 경계가 필요합니다')

    def test_pure_read_and_strict_control_with_real_store(self):
        from web_operations import handle
        from common.operations.runtime_store import RuntimeStore
        from common.operations.content_store import ConflictError,StoreError
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'source';source.mkdir();workspace=Path(temp)/'workspace'
            store=RuntimeStore(workspace)
            response=handle(store,'GET','/api/v2/operations',{},lambda:{},source_root=source)
            self.assertFalse(workspace.exists());self.assertEqual(response['control']['global']['state'],'clear')
            self.assertEqual({(r['scope'],r['id']) for r in response['control']['managed']},{('managed','all'),('account','personal'),('account','dept')})
            store.initialize()
            body=dict(scope='managed',id='all',action='pause',expected_version=0,request_key='one',reason='검토')
            send=lambda b:handle(store,'POST','/api/v2/control',{},lambda:b,source_root=source)
            result=send(body);self.assertEqual(result['version'],1);self.assertEqual(send(body),result)
            with self.assertRaises(ConflictError):send(dict(body,request_key='two'))
            with self.assertRaises(StoreError):send(dict(body,actor='override'))
            self.assertEqual(store.list_runs(),[]);self.assertEqual(list(source.iterdir()),[])

    def test_list_filters_and_evidence_allowlist(self):
        from web_operations import list_response,item
        from common.operations.runtime_models import ExecutionPolicy
        from types import SimpleNamespace
        row=dict(id='delivery_'+'a'*32,run_id='run_one',state='unknown',version=1,context=dict(owner_account_id='personal',destination_account_id='personal',options={'secret':'SECRET'}))
        store=SimpleNamespace(list_operations=lambda a:[row],control_state=lambda:[],attempts=lambda id:[{'id':'attempt_a','nonce_hash':'SECRET','request_started':True}],events=lambda id:[{'kind':'lookup','evidence':{'token':'SECRET','path':'/SECRET'}}])
        with tempfile.TemporaryDirectory() as source:
            self.assertEqual(list_response(store,Path(source),'dept',ExecutionPolicy())['items'],[])
            self.assertEqual(list_response(store,Path(source),'personal',ExecutionPolicy())['summary']['waiting'],1)
            data=item(row,detail=True,store=store)
            self.assertNotIn('SECRET',json.dumps(data));self.assertEqual(data['evidence'],[{'kind':'lookup'}])

class RecoveryAPIIntegrationTests(unittest.TestCase):
    def setUp(self):
        from tests.operations.test_runtime_store import RuntimeStoreTests,context,NOW
        from common.operations.runtime_store import RuntimeStore
        from types import SimpleNamespace
        import sqlite3
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'managed';self.source=Path(self.tmp.name)/'source';self.source.mkdir()
        RuntimeStoreTests.fixture(self)
        self.id='delivery_'+'b'*32
        db=sqlite3.connect(self.root/'operations.sqlite3')
        try:
            with db:db.execute('UPDATE deliveries SET id=? WHERE id=?',(self.id,'d'))
        finally:db.close()
        self.snapshot={'title':'한글 원본 제목','manifest_hash':'m','revision':1,'original':'body','assets':[],'variants':[]}
        self.store=RuntimeStore(self.root,content_store=SimpleNamespace(get=lambda *a:self.snapshot));self.store.initialize()
        self.store.create_run('r');self.ctx=context();self.store.create_delivery(self.id,'r',self.ctx)
        self.store.record_publication_approval(self.id,1,self.ctx.context_hash,'approval',('a','b'))
        lease=self.store.claim_run('r','worker',{'host_id':'host','pid':123,'started_at':NOW.isoformat()},NOW)
        a=self.store.create_attempt(self.id,self.store.get_delivery(self.id)['version'],lease,self.ctx.context_hash,'approval',now=NOW)
        permit=self.store.issue_permit(a['id'],lease,self.ctx.context_hash,'approval',NOW);self.store.consume_permit(permit,lease,NOW);self.store.finish_attempt(a['id'],'unknown',now=NOW)
        self.now=NOW;self.lookups=0
    def request(self,action,body,**kwargs):
        from web_operations import handle
        return handle(self.store,'POST','/api/v2/operations/'+self.id+'/'+action,{},lambda:body,source_root=self.source,now=self.now,**kwargs)
    def decision(self,kind='cancel_local',**extra):
        return dict(expected_version=self.store.get_delivery(self.id)['version'],request_key='command',kind=kind,evidence={'local_only':True},note='작업자 검토',**extra)
    def test_cancel_replay_preserves_uncertainty_same_identity_and_forgery_rejected(self):
        from common.operations.content_store import StoreError,ConflictError
        decision=self.decision();first=self.request('resolve',decision)
        self.assertEqual(first['state'],'cancelled');self.assertTrue(first['remote_uncertain']);self.assertEqual(first['id'],self.id)
        self.assertEqual(self.request('resolve',decision),first)
        with self.assertRaises(ConflictError):self.request('resolve',dict(decision,note='다른 판단'))
        for field in ('actor','process_probe','lock_probe','executor','credential','adapter'):
            with self.assertRaises(StoreError):self.request('resolve',dict(decision,**{field:'forged'}))
    def test_probe_claims_do_not_replace_server_probe(self):
        from web_operations import OperationsBlocked
        decision=self.decision('confirmed_not_posted');decision['evidence']={'confirmed_not_posted':True,'old_process_terminated':True,'profile_lock_released':True}
        with self.assertRaises(OperationsBlocked) as blocked:self.request('resolve',decision)
        self.assertEqual(blocked.exception.code,'probe_unavailable');self.assertEqual(self.store.get_delivery(self.id)['state'],'unknown')
    def test_reconcile_response_loss_replay_calls_lookup_once_and_never_submits(self):
        import hashlib
        from common.operations.runtime_models import LookupResult
        fixture=self
        class Adapter:
            def lookup(self,ctx,attempt):
                fixture.lookups+=1
                return LookupResult('matched',[dict(remote_id='remote_one',target_id='t',destination_account_id='personal',created_at=fixture.now.isoformat(),body_sha256=hashlib.sha256(b'body').hexdigest(),media_sha256=[])])
            def submit(self,*a):raise AssertionError('복구에서 제출 금지')
        body=dict(expected_version=self.store.get_delivery(self.id)['version'],request_key='reconcile')
        first=self.request('reconcile',body,adapters={'x':Adapter()});self.assertEqual(first['state'],'uploaded')
        self.assertEqual(self.request('reconcile',body,adapters={'x':Adapter()}),first);self.assertEqual(self.lookups,1)
    def test_display_types_safe_public_url_and_registry_controls(self):
        from web_operations import item,list_response
        from common.operations.runtime_models import ExecutionPolicy
        row=self.store.get_delivery(self.id)
        self.store.record_evidence(self.id,'remote_lookup',{'remote_id':'remote_one','checked_at':self.now.isoformat(),'outcome':'matched','url':'https://www.youtube.com/watch?v=remote_one','process':{'status':'dead','pid':123},'token':'SECRET','path':'/SECRET'})
        data=item(row,detail=True,store=self.store)
        self.assertEqual(data['title'],'한글 원본 제목');self.assertEqual(data['evidence'][-1]['checked_at'],self.now.isoformat())
        self.assertEqual(data['evidence'][-1]['process_status'],'dead');self.assertIn('youtube.com',data['evidence'][-1]['url']);self.assertNotIn('SECRET',json.dumps(data))
        self.store.record_evidence(self.id,'unsafe',{'url':'https://www.youtube.com/watch?v=ok&token=SECRET'})
        self.assertNotIn('url',item(row,detail=True,store=self.store)['evidence'][-1])
        response=list_response(self.store,self.source,'dept',ExecutionPolicy(),connections=[{'id':'dept.youtube','account_id':'dept','target_label':'학과 채널'}])
        self.assertIn('dept.youtube',[r['id'] for r in response['control']['managed']])

    def test_partial_retry_same_ids_replay_and_unknown_remote_zero(self):
        import sqlite3
        from datetime import timedelta
        from tests.operations.test_dispatch import registry,request
        from common.operations.runtime_models import ExecutionPolicy
        from common.operations.content_store import ConflictError
        policy=ExecutionPolicy(True,('x',),'cutover');reg=registry()
        dead=lambda identity:dict(identity,status='dead')
        free=lambda context:dict(status='free',connection_id=context['connection_id'])
        decision=self.decision('confirmed_not_posted');decision['evidence']={'confirmed_not_posted':True}
        self.request('resolve',decision,process_probe=dead,lock_probe=free)
        db=sqlite3.connect(self.root/'operations.sqlite3')
        try:
            with db:
                db.execute('UPDATE runs SET payload=? WHERE id=?',(json.dumps(request()),'r'))
                for id in ('success','other'):
                    db.execute('INSERT INTO deliveries VALUES(?,?,?,?,?,?,?,?)',(id,'c',1,'x',id,id,'hash','{}'))
        finally:db.close()
        for id in ('success','other'):self.store.create_delivery(id,'r',self.ctx)
        # 별도 성공/대기 대상은 재개 명령의 선택 범위 밖이다.
        self.store.transition_delivery('other',1,'running');self.store.transition_delivery('other',self.store.get_delivery('other')['version'],'retry_wait')
        # 검증된 형제 대상 fixture를 명시적으로 기록한다(외부 제출 없음).
        db=sqlite3.connect(self.root/'operations.sqlite3')
        try:
            with db:db.execute("UPDATE runtime_deliveries SET state='verified',version=2 WHERE id='success'")
        finally:db.close()
        success=self.store.get_delivery('success');other=self.store.get_delivery('other')
        self.now+=timedelta(minutes=2)
        body=dict(expected_version=self.store.get_delivery(self.id)['version'],request_key='retry-selected')
        before=self.store.get_delivery(self.id);approval=self.store.get_publication_approval(self.id)
        result=self.request('retry',body,policy=policy,registry=reg,process_probe=dead,lock_probe=free)
        self.assertEqual(result['state'],'queued');self.assertEqual(result['id'],self.id);self.assertEqual(result['run_id'],'r')
        self.assertEqual(self.request('retry',body,policy=policy,registry=reg),result)
        self.assertEqual(self.store.get_delivery('success'),success);self.assertEqual(self.store.get_delivery('other'),other)
        self.assertEqual(self.store.get_delivery(self.id)['context'],before['context']);self.assertEqual(self.store.get_publication_approval(self.id),approval)

    def test_unknown_retry_never_calls_remote_and_get_is_byte_identical(self):
        from common.operations.runtime_models import ExecutionPolicy
        from tests.operations.test_dispatch import registry,request
        from common.operations.content_store import ConflictError
        import sqlite3
        from datetime import timedelta
        db=sqlite3.connect(self.root/'operations.sqlite3')
        try:
            with db:db.execute('UPDATE runs SET payload=? WHERE id=?',(json.dumps(request()),'r'))
        finally:db.close()
        from web_operations import handle
        class Adapter:
            def lookup(self,*a):raise AssertionError('unknown retry remote0')
            def submit(self,*a):raise AssertionError('unknown retry remote0')
        before=(self.root/'operations.sqlite3').read_bytes()
        handle(self.store,'GET','/api/v2/operations',{},lambda:{},source_root=self.source,adapters={'x':Adapter()})
        self.assertEqual((self.root/'operations.sqlite3').read_bytes(),before)
        self.now+=timedelta(minutes=2)
        with self.assertRaises(ConflictError):self.request('retry',{'expected_version':self.store.get_delivery(self.id)['version'],'request_key':'never'},policy=ExecutionPolicy(True,('x',),'cutover'),registry=registry(),process_probe=lambda i:dict(i,status='dead'),lock_probe=lambda c:dict(status='free',connection_id='x'),adapters={'x':Adapter()})
        self.assertEqual((self.root/'operations.sqlite3').read_bytes(),before)

class OperationsFactoryContractTests(unittest.TestCase):
    def test_server_owned_dependencies_are_explicit_factory_arguments(self):
        import inspect
        spec=importlib.util.spec_from_file_location('ops_factory',APP/'web_server.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        parameters=inspect.signature(module.create_server).parameters
        self.assertTrue({'recovery_adapters','process_probe','lock_probe','operations_clock'}<=set(parameters))

    def test_direct_handler_rejects_query_overrides_without_http_wrapper(self):
        from web_operations import handle
        from common.operations.content_store import StoreError
        with tempfile.TemporaryDirectory() as source:
            for query in ({'account':['bad']},{'account':['all','dept']},{'enabled':['true']}):
                with self.assertRaises(StoreError):handle(None,'GET','/api/v2/operations',query,lambda:{},source_root=Path(source))
            with self.assertRaises(StoreError):handle(None,'POST','/api/v2/control',{'account':['all']},lambda:{},source_root=Path(source))

class OperationsSummaryTests(unittest.TestCase):
    def test_partial_run_is_counted_once_and_success_is_not_new_completion(self):
        from types import SimpleNamespace
        from web_operations import list_response
        from common.operations.runtime_models import ExecutionPolicy
        rows=[dict(id='a',run_id='run_one',state='verified',context={}),dict(id='b',run_id='run_one',state='retry_wait',context={})]
        store=SimpleNamespace(list_operations=lambda a:rows,list_runs=lambda:[{'id':'run_one','state':'partial'}],control_state=lambda:[])
        with tempfile.TemporaryDirectory() as source:
            summary=list_response(store,Path(source),'all',ExecutionPolicy())['summary']
        self.assertEqual(summary,{'active':0,'completed':0,'partial':1,'waiting':0})

if __name__=='__main__':unittest.main()
