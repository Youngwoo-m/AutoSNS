"""가짜 X leaf→adapter→영속 공개 검증을 연결하며 실제 전송은 하지 않는다."""
from dataclasses import replace
from datetime import timedelta
import tempfile
from pathlib import Path
import unittest
import sqlite3,json
from contextlib import closing
from common.operations.content_store import ContentStore
from common.operations.runtime_store import RuntimeStore
from common.operations.models import Registry,Connection,ContractError
from common.operations.runtime_models import PublicationContext
from common.operations.verification import verify_delivery
from common.publishers.x_services import XJournal,XServices
from common.publishers.x_runtime import build_x_handlers,build_x_catalog,bridge_bootstrap
from common.publishers.x import XAdapter
from common.operations.ledger import Ledger
from datetime import datetime,timezone
NOW=datetime(2026,11,4,tzinfo=timezone.utc)
LONG='https://example.org/?a=1&b=2'
SHORT='https://t.co/AbCdEf'

class Client:
    def __init__(self):self.calls=[];self.text='';self.changed=False;self.shortened=False;self.bad_entity=False
    def inspect_account(self):self.calls.append('me');return dict(id='123456',username='dept',protected=False)
    def create_post(self,text):self.calls.append('post');self.text=text;return dict(id='222',text=text)
    def read_post(self,id):
        self.calls.append('read')
        text=self.text if not self.changed else '다른 게시물'
        entities={}
        if self.shortened and LONG in text:
            prefix=text[:text.index(LONG)];start=len(prefix.encode('utf-16-le'))//2
            text=text.replace(LONG,SHORT)
            entities={'urls':[dict(start=start,end=start+len(SHORT),url=SHORT,expanded_url=LONG if not self.bad_entity else LONG.split('?')[0])]}
        return dict(id=id,author_id='123456',text=text,created_at=NOW.isoformat(),entities=entities)

class XRuntimeTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.content=ContentStore(self.root);self.content.initialize()
        snap=self.content.create('personal',dict(title='원문',kind='article',original='개인 원문',variants=[dict(destination_account_id='dept',platform='x',text='😀 학과 교차 게시 '+LONG)]))
        self.snap=self.content.add_asset(snap['id'],1,'image.png','image/png',b'\x89PNG\r\n\x1a\nfixture')
        self.ctx=PublicationContext(content_id=self.snap['id'],content_revision=self.snap['revision'],manifest_hash=self.snap['manifest_hash'],owner_account_id='personal',destination_account_id='dept',connection_id='dept.x',target_id='123456',publication_purpose='initial',schedule_slot='slot',options={'text_only':True},schedule_condition={},registry_revision='r',policy_revision='p',auth_checked_at=NOW,auth_expires_at=NOW+timedelta(hours=1),review_report_hashes=('review',),platform='x',run_id='r')
        self.registry=Registry('r',{'personal':{},'dept':{}},{'dept.x.credential':dict(account_id='dept',platform='x')},{'dept':dict(account_id='dept',lock_resource='profile:insta')},{'dept.x':Connection('dept.x','dept','x',target_id='123456',credential_ref='dept.x.credential',profile_ref='dept',enabled=True,capabilities=('text_only',))},{'x-job':dict(executor_id='x.dept',connection_id='dept.x',enabled=True,execution_owner='managed',managed_eligible=True)}, {},{})
        self.journal=XJournal(self.root);self.journal.initialize();self.client=Client()
    def adapter(self,public=True):
        def probe(obs):return dict(public=True,remote_id=obs['remote_id'],target_id=obs['target_id'],body_sha256=obs['body_sha256'],url=obs['url'],checked_at=NOW.isoformat())
        service=XServices(self.client,self.journal,lambda:NOW,cost_authorizer=lambda target:True,public_probe=probe if public else None)
        handlers=build_x_handlers(self.registry,services_factory=lambda key,credentials:service,clock=lambda:NOW)
        class Bridge:
            def read(self,executor,action,ctx,payload):return handlers[(executor,action)](ctx.to_dict(),payload,None)
            def submit(self,executor,ctx,prepared,permit):return handlers[(executor,'publish')](ctx.to_dict(),prepared,None)
        from types import SimpleNamespace
        bridge=Bridge();bridge.store=SimpleNamespace(content_store=self.content)
        return XAdapter(self.registry,bridge)
    def uploaded(self,adapter,outcome='submitted'):
        store=RuntimeStore(self.root,self.registry,self.content);store.initialize()
        with closing(sqlite3.connect(self.root/'operations.sqlite3')) as db:
            db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?)',('r','x-job',NOW.isoformat(),'prepare','fixture','{}'))
            db.execute('INSERT INTO deliveries VALUES(?,?,?,?,?,?,?,?)',('d',self.snap['id'],self.snap['revision'],'dept.x','initial','slot','fixture',json.dumps({'status':'ready','approval':{'subject_hash':'fixture'}})))
            db.commit()
        from common.shared.axlock import AxLock,LockPaths
        store.locks=AxLock(LockPaths.from_root(self.root/'source'),process_probe=lambda _:False)
        store.create_run('r');store.create_delivery('d','r',self.ctx)
        store.record_publication_approval('d',1,self.ctx.context_hash,'approval',self.ctx.review_report_hashes)
        lease=store.claim_run('r','worker',{'host_id':'host','pid':123,'started_at':NOW.isoformat()},NOW)
        attempt=store.create_attempt('d',store.get_delivery('d')['version'],lease,self.ctx.context_hash,'approval',now=NOW)
        permit=store.issue_permit(attempt['id'],lease,self.ctx.context_hash,'approval',NOW);store.consume_permit(permit,lease,NOW)
        result=adapter.submit(self.ctx,adapter.prepare(self.ctx,self.snap),permit)
        self.assertEqual(result.outcome,'submitted')
        store.finish_attempt(attempt['id'],outcome,remote_id=result.remote_id,url=result.url,evidence=result.evidence,now=NOW)
        return store
    def test_text_only_crosspost_reaches_verified_and_preserves_actual_public_url(self):
        adapter=self.adapter();store=self.uploaded(adapter)
        result=verify_delivery(store,'d',adapter,self.snap,now=NOW)
        self.assertEqual(result.outcome,'verified');self.assertEqual(store.get_run('r')['state'],'completed')
        self.assertEqual(store.get_delivery('d')['url'],'https://x.com/i/web/status/222')
        self.assertEqual(result.evidence['media_sha256'],())
        self.assertEqual(self.client.calls.count('post'),1)
        self.assertEqual(adapter.submit(self.ctx,adapter.prepare(self.ctx,self.snap),object()).remote_id,'222')
        self.assertEqual(self.client.calls.count('post'),1)
        self.assertEqual(self.content.get(self.snap['id']),self.snap)
    def test_owner_api_without_public_probe_never_completes_public_verification(self):
        adapter=self.adapter(public=False);store=self.uploaded(adapter)
        result=verify_delivery(store,'d',adapter,self.snap,now=NOW)
        self.assertEqual(result.outcome,'pending');self.assertNotEqual(store.get_delivery('d')['state'],'verified')
        self.assertIsNone(store.get_delivery('d')['url'])
    def test_default_catalog_and_child_bootstrap_are_not_enabled(self):
        self.assertEqual(dict(build_x_catalog(self.registry).executors),{})
        self.assertIn('x.dept',build_x_catalog(self.registry,configured=True).executors)
        with self.assertRaises(ContractError):bridge_bootstrap()
        disabled=replace(self.registry,connections={'dept.x':replace(self.registry.connections['dept.x'],enabled=False)})
        with self.assertRaises(ContractError):XAdapter(disabled,object()).prepare(self.ctx,self.snap)

    def test_x_text_only_plan_saves_without_modifying_original_assets(self):
        from common.operations.registry import load_registry
        registry=load_registry(Path(__file__).resolve().parents[2]/'ax-console/config/operations.json')
        item=self.content.create('dept',dict(title='계획 원고',kind='article',original='계획할 글'))
        ledger=Ledger(self.root,registry,self.content);ledger.initialize()
        row=ledger.create_or_get_delivery(dict(content_id=item['id'],revision=item['revision'],manifest_hash=item['manifest_hash'],connection_id='dept.x',publication_purpose='initial',schedule_slot='saved-x',scheduled_at='2026-11-04T10:00:00+09:00',timezone='Asia/Seoul',options={'text_only':True}))
        self.assertEqual(row['options'],{'text_only':True})
        self.assertFalse(row['execution_enabled'])
        self.assertEqual(self.content.get(self.snap['id']),self.snap)

    def test_changed_remote_text_cannot_complete_or_inherit_approved_hash(self):
        adapter=self.adapter();store=self.uploaded(adapter);self.client.changed=True
        result=verify_delivery(store,'d',adapter,self.snap,now=NOW)
        self.assertEqual(result.outcome,'pending')
        self.assertNotEqual(store.get_delivery('d')['state'],'verified')

    def test_invalid_runtime_payload_is_rejected_before_services_factory(self):
        calls=[]
        handlers=build_x_handlers(self.registry,services_factory=lambda *a:calls.append(a),clock=lambda:NOW)
        for action,payload in [('inspect_target',{'secret':'x'}),('verify',{'remote_id':'222','secret':'x'}),('lookup',{'attempt':{'remote_id':'222','secret':'x'}}),('publish',{'text':'외부 입력'})]:
            with self.subTest(action=action),self.assertRaises(ContractError):handlers[('x.dept',action)](self.ctx.to_dict(),payload,None)
        self.assertEqual(calls,[])

    def test_tco_utf16_entities_are_verified_without_claiming_same_remote_hash(self):
        self.client.shortened=True;adapter=self.adapter();store=self.uploaded(adapter)
        result=verify_delivery(store,'d',adapter,self.snap,now=NOW)
        self.assertEqual(result.outcome,'verified')
        self.assertNotEqual(result.evidence['remote_text_sha256'],result.evidence['body_sha256'])
        self.assertEqual(store.get_delivery('d')['url'],'https://x.com/i/web/status/222')
        self.assertEqual(self.client.calls.count('post'),1)

    def test_inexact_expansion_query_never_completes(self):
        self.client.shortened=True;self.client.bad_entity=True
        adapter=self.adapter();store=self.uploaded(adapter)
        self.assertEqual(verify_delivery(store,'d',adapter,self.snap,now=NOW).outcome,'pending')

    def test_known_uncertain_submission_reconciles_by_read_without_reposting(self):
        from common.operations.recovery import reconcile_delivery
        self.client.shortened=True;adapter=self.adapter();store=self.uploaded(adapter,outcome='unknown')
        delivery=store.get_delivery('d')
        result=reconcile_delivery(store,'d',adapter,NOW,expected_version=delivery['version'],request_key='x-reconcile')
        self.assertEqual(result['remote_id'],'222')
        self.assertEqual(self.client.calls.count('post'),1)
        self.assertEqual(verify_delivery(store,'d',adapter,self.snap,now=NOW).outcome,'verified')

    def test_returned_post_id_survives_local_commit_failure_for_read_only_lookup(self):
        from unittest.mock import patch
        actual=self.journal.transition
        def transition(row,state,at,**kwargs):
            if state=='submitted':raise OSError('fixture DB write failure')
            return actual(row,state,at,**kwargs)
        adapter=self.adapter()
        with patch.object(self.journal,'transition',side_effect=transition):
            result=adapter.submit(self.ctx,adapter.prepare(self.ctx,self.snap),object())
        self.assertEqual(result.outcome,'unknown');self.assertEqual(result.remote_id,'222')
        found=adapter.lookup(self.ctx,{'remote_id':'222','created_at':NOW.isoformat()})
        self.assertEqual(found.outcome,'matched')
        self.assertEqual(self.client.calls.count('post'),1)
