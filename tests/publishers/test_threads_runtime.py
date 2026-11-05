"""가짜 Threads leaf→adapter→영속 공개 검증을 연결하며 실제 전송은 하지 않는다."""
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
from common.publishers.threads_services import ThreadsJournal,ThreadsServices
from common.publishers.threads_runtime import build_threads_handlers,build_threads_catalog,bridge_bootstrap
from common.publishers.threads import ThreadsAdapter
from tests.publishers.test_threads import NOW

class Client:
    def __init__(self):self.calls=[];self.text=''
    def me(self):self.calls.append('me');return {'id':'123456'}
    def create_text(self,user,text):self.calls.append('create');self.text=text;return {'id':'111'}
    def container_status(self,id):self.calls.append('status');return {'id':id,'status':'FINISHED'}
    def publish(self,user,id):self.calls.append('publish');return {'id':'222'}
    def read_post(self,id):self.calls.append('read');return dict(id=id,owner={'id':'123456'},text=self.text,timestamp=NOW.isoformat(),media_type='TEXT_POST',permalink='https://www.threads.net/@dept/post/ABC')

class ThreadsRuntimeTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.content=ContentStore(self.root);self.content.initialize()
        snap=self.content.create('personal',dict(title='원문',kind='article',original='개인 원문',variants=[dict(destination_account_id='dept',platform='threads',text='학과 교차 게시')]))
        self.snap=self.content.add_asset(snap['id'],1,'image.png','image/png',b'\x89PNG\r\n\x1a\nfixture')
        self.ctx=PublicationContext(content_id=self.snap['id'],content_revision=self.snap['revision'],manifest_hash=self.snap['manifest_hash'],owner_account_id='personal',destination_account_id='dept',connection_id='dept.threads',target_id='123456',publication_purpose='initial',schedule_slot='slot',options={'text_only':True},schedule_condition={},registry_revision='r',policy_revision='p',auth_checked_at=NOW,auth_expires_at=NOW+timedelta(hours=1),review_report_hashes=('review',),platform='threads',run_id='r')
        self.registry=Registry('r',{'personal':{},'dept':{}},{'dept.threads.credential':dict(account_id='dept',platform='threads')},{'dept':dict(account_id='dept',lock_resource='profile:insta')},{'dept.threads':Connection('dept.threads','dept','threads',target_id='123456',credential_ref='dept.threads.credential',profile_ref='dept',enabled=True,capabilities=('text_only',))},{'threads-job':dict(executor_id='threads.dept',connection_id='dept.threads',enabled=True,execution_owner='managed',managed_eligible=True)}, {},{})
        self.journal=ThreadsJournal(self.root);self.journal.initialize();self.client=Client()
    def adapter(self,public=True):
        def probe(obs):return dict(public=True,remote_id=obs['remote_id'],target_id=obs['target_id'],body_sha256=obs['body_sha256'],url=obs['url'],checked_at=NOW.isoformat())
        service=ThreadsServices(self.client,self.journal,lambda:NOW,public_probe=probe if public else None)
        handlers=build_threads_handlers(self.registry,services_factory=lambda key,credentials:service,clock=lambda:NOW)
        class Bridge:
            def read(self,executor,action,ctx,payload):return handlers[(executor,action)](ctx.to_dict(),payload,None)
            def submit(self,executor,ctx,prepared,permit):return handlers[(executor,'publish')](ctx.to_dict(),prepared,None)
        return ThreadsAdapter(self.registry,Bridge())
    def uploaded(self,adapter):
        store=RuntimeStore(self.root,self.registry,self.content);store.initialize()
        with closing(sqlite3.connect(self.root/'operations.sqlite3')) as db:
            db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?)',('r','threads-job',NOW.isoformat(),'prepare','fixture','{}'))
            db.execute('INSERT INTO deliveries VALUES(?,?,?,?,?,?,?,?)',('d',self.snap['id'],self.snap['revision'],'dept.threads','initial','slot','fixture',json.dumps({'status':'ready','approval':{'subject_hash':'fixture'}})))
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
        store.finish_attempt(attempt['id'],'submitted',remote_id=result.remote_id,url=result.url,evidence=result.evidence,now=NOW)
        return store
    def test_text_only_crosspost_reaches_verified_and_preserves_actual_public_url(self):
        adapter=self.adapter();store=self.uploaded(adapter)
        result=verify_delivery(store,'d',adapter,self.snap,now=NOW)
        self.assertEqual(result.outcome,'verified');self.assertEqual(store.get_run('r')['state'],'completed')
        self.assertEqual(store.get_delivery('d')['url'],'https://www.threads.net/@dept/post/ABC')
        self.assertEqual(result.evidence['media_sha256'],())
        self.assertEqual(self.client.calls.count('create'),1);self.assertEqual(self.client.calls.count('publish'),1)
        self.assertEqual(adapter.submit(self.ctx,adapter.prepare(self.ctx,self.snap),object()).remote_id,'222')
        self.assertEqual(self.client.calls.count('publish'),1)
        self.assertEqual(self.content.get(self.snap['id']),self.snap)
    def test_owner_api_without_public_probe_never_completes_public_verification(self):
        adapter=self.adapter(public=False);store=self.uploaded(adapter)
        result=verify_delivery(store,'d',adapter,self.snap,now=NOW)
        self.assertEqual(result.outcome,'pending');self.assertNotEqual(store.get_delivery('d')['state'],'verified')
        self.assertIsNone(store.get_delivery('d')['url'])
    def test_default_catalog_and_child_bootstrap_are_not_enabled(self):
        self.assertEqual(dict(build_threads_catalog(self.registry).executors),{})
        self.assertIn('threads.dept',build_threads_catalog(self.registry,configured=True).executors)
        with self.assertRaises(ContractError):bridge_bootstrap()
