"""가짜 HTTP→실제 client/service/journal/handler/adapter→RuntimeStore 공개 검증.

InlineBridge를 사용하므로 BridgeHost의 child permit 관문 자체를 검증하지 않는다.
RuntimeStore의 실제 승인·lease·permit을 생성/소비하고 결과·공개 URL을 영속화한다.
모든 자격·페이지 권한 증명·공개 probe는 시험용이며 실제 API·로그인은 없다.
"""
from contextlib import closing
from datetime import timedelta
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from urllib.parse import parse_qs,urlsplit

from common.operations.content_store import ContentStore
from common.operations.models import Registry,Connection
from common.operations.runtime_models import PublicationContext
from common.operations.runtime_store import RuntimeStore
from common.operations.verification import verify_delivery
from common.publishers.facebook import FacebookAdapter
from common.publishers.facebook_client import FacebookApiClient
from common.publishers.facebook_runtime import build_facebook_handlers
from common.publishers.facebook_services import FacebookJournal,FacebookServices
from tests.publishers.test_facebook_payloads import NOW

PAGE='123456';POST=PAGE+'_777';URL='https://www.facebook.com/123456/posts/777'

class FakeHTTP:
    def __init__(self):self.calls=[];self.text=None;self.attachments=[]
    def __call__(self,method,path,headers,body):
        self.calls.append((method,path));assert headers['Authorization']=='Bearer fixture-facebook-token'
        route=urlsplit(path).path
        if method=='GET' and route=='/v26.0/me':row=dict(id=PAGE,name='시험 페이지')
        elif method=='POST' and route=='/v26.0/'+PAGE+'/feed':
            form=parse_qs(body.decode('ascii'));assert set(form)=={'message','published'};assert form['published']==['true']
            self.text=form['message'][0];row={'id':POST}
        elif method=='GET' and route=='/v26.0/'+POST+'/attachments':row={'data':self.attachments}
        elif method=='GET' and route=='/v26.0/'+POST:
            row=dict(id=POST,**{'from':{'id':PAGE}},message=self.text,created_time=NOW.isoformat(),permalink_url=URL,is_published=True,is_hidden=False)
        else:raise AssertionError('unexpected fixture endpoint')
        return 200,json.dumps(row,ensure_ascii=False).encode('utf-8')
    @property
    def posts(self):return [call for call in self.calls if call[0]=='POST']

class FacebookEndToEndTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.content=ContentStore(self.root);self.content.initialize()
        first=self.content.create('personal',dict(title='개인 원본',kind='article',original='개인 원고',variants=[dict(destination_account_id='dept',platform='facebook',text=' 학과 페이지 교차 게시\n그대로 ')]))
        self.snap=self.content.add_asset(first['id'],1,'original.png','image/png',b'\x89PNG\r\n\x1a\nfixture')
        self.ctx=PublicationContext(content_id=self.snap['id'],content_revision=self.snap['revision'],manifest_hash=self.snap['manifest_hash'],owner_account_id='personal',destination_account_id='dept',connection_id='dept.facebook',target_id=PAGE,publication_purpose='initial',schedule_slot='slot',options={'text_only':True},schedule_condition={},registry_revision='r',policy_revision='p',auth_checked_at=NOW,auth_expires_at=NOW+timedelta(hours=1),review_report_hashes=('review',),platform='facebook',run_id='r')
        self.registry=Registry('r',{'personal':{},'dept':{}},{'dept.facebook.credential':dict(account_id='dept',platform='facebook')},{'dept':dict(account_id='dept',lock_resource='profile:insta')},{'dept.facebook':Connection('dept.facebook','dept','facebook',target_id=PAGE,credential_ref='dept.facebook.credential',profile_ref='dept',enabled=True,capabilities=('text_only','visibility:public'),expected_login_subject='admin-user')},{'facebook-job':dict(executor_id='facebook.dept',connection_id='dept.facebook',enabled=True,execution_owner='managed',managed_eligible=True)}, {},{})
        self.http=FakeHTTP();self.client=FacebookApiClient('fixture-facebook-token',api_version='v26.0',transport=self.http)
        self.journal=FacebookJournal(self.root);self.journal.initialize()
    def adapter(self,public=True,lose_response=False,authorized=True):
        def authorize(target,identity):
            return dict(page_id=target['target_id'],token_subject=identity['id'],login_subject='admin-user',can_publish=True,tasks_checked=True,checked_at=NOW.isoformat(),page_type='page')
        def probe(observation):
            return dict(public=True,remote_id=observation['remote_id'],target_id=observation['target_id'],body_sha256=observation['body_sha256'],url=observation['url'],checked_at=NOW.isoformat())
        service=FacebookServices(self.client,self.journal,lambda:NOW,page_authorizer=authorize if authorized else None,public_probe=probe if public else None)
        handlers=build_facebook_handlers(self.registry,services_factory=lambda _key,_credentials:service,clock=lambda:NOW)
        content=self.content
        class InlineBridge:
            def __init__(self):self.store=type('StoreView',(),{'content_store':content})();self.lose=lose_response
            def read(self,executor,action,ctx,payload):return handlers[(executor,action)](ctx.to_dict(),payload,None)
            def submit(self,executor,ctx,prepared,permit):
                result=handlers[(executor,'publish')](ctx.to_dict(),prepared,None)
                if self.lose:self.lose=False;raise OSError('fixture lost child response')
                return result
        return FacebookAdapter(self.registry,InlineBridge())
    def started(self):
        store=RuntimeStore(self.root,self.registry,self.content);store.initialize()
        with closing(sqlite3.connect(self.root/'operations.sqlite3')) as db:
            db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?)',('r','facebook-job',NOW.isoformat(),'prepare','fixture','{}'))
            db.execute('INSERT INTO deliveries VALUES(?,?,?,?,?,?,?,?)',('d',self.snap['id'],self.snap['revision'],'dept.facebook','initial','slot','fixture',json.dumps({'status':'ready','approval':{'subject_hash':'fixture'}})));db.commit()
        from common.shared.axlock import AxLock,LockPaths
        store.locks=AxLock(LockPaths.from_root(self.root/'source'),process_probe=lambda _:False)
        store.create_run('r');store.create_delivery('d','r',self.ctx)
        store.record_publication_approval('d',1,self.ctx.context_hash,'approval',self.ctx.review_report_hashes)
        lease=store.claim_run('r','worker',{'host_id':'fixture','pid':123,'started_at':NOW.isoformat()},NOW)
        attempt=store.create_attempt('d',store.get_delivery('d')['version'],lease,self.ctx.context_hash,'approval',now=NOW)
        permit=store.issue_permit(attempt['id'],lease,self.ctx.context_hash,'approval',NOW);store.consume_permit(permit,lease,NOW)
        return store,attempt,permit
    def submitted(self,adapter):
        store,attempt,permit=self.started();result=adapter.submit(self.ctx,adapter.prepare(self.ctx,self.snap),permit)
        self.assertEqual(result.outcome,'submitted');store.finish_attempt(attempt['id'],'submitted',remote_id=result.remote_id,url=result.url,evidence=result.evidence,now=NOW)
        return store
    def test_actual_client_and_journal_crosspost_verifies_public_url_without_mutating_original_asset(self):
        adapter=self.adapter();store=self.submitted(adapter);result=verify_delivery(store,'d',adapter,self.snap,now=NOW)
        self.assertEqual(result.outcome,'verified');self.assertEqual(store.get_delivery('d')['url'],URL);self.assertEqual(store.get_run('r')['state'],'completed')
        self.assertEqual(list(result.evidence['media_sha256']),[]);self.assertEqual(self.http.text,' 학과 페이지 교차 게시\n그대로 ');self.assertEqual(len(self.http.posts),1)
        self.assertEqual(self.content.get(self.snap['id']),self.snap);self.assertEqual(len(self.snap['assets']),1)
        self.assertTrue(any('/'+POST+'/attachments' in path for method,path in self.http.calls if method=='GET'))
        replay=adapter.submit(self.ctx,adapter.prepare(self.ctx,self.snap),object());self.assertEqual(replay.remote_id,POST);self.assertEqual(len(self.http.posts),1)
    def test_owner_api_and_published_flag_without_public_probe_stay_pending(self):
        adapter=self.adapter(public=False);store=self.submitted(adapter);result=verify_delivery(store,'d',adapter,self.snap,now=NOW)
        self.assertEqual(result.outcome,'pending');self.assertNotEqual(store.get_delivery('d')['state'],'verified');self.assertIsNone(store.get_delivery('d')['url']);self.assertEqual(len(self.http.posts),1)
    def test_response_lost_after_journal_commit_replays_no_post_and_known_id_lookup_is_read_only(self):
        adapter=self.adapter(lose_response=True);store,attempt,permit=self.started()
        result=adapter.submit(self.ctx,adapter.prepare(self.ctx,self.snap),permit);self.assertEqual(result.outcome,'unknown')
        store.finish_attempt(attempt['id'],'unknown',evidence=result.evidence,now=NOW);self.assertEqual(store.get_delivery('d')['state'],'unknown');self.assertEqual(len(self.http.posts),1)
        replay=adapter.submit(self.ctx,adapter.prepare(self.ctx,self.snap),object());self.assertEqual(replay.outcome,'submitted');self.assertEqual(replay.remote_id,POST);self.assertEqual(len(self.http.posts),1)
        unknown=store.attempts('d')[-1];self.assertEqual(adapter.lookup(self.ctx,unknown).outcome,'unsupported')
        # 이미 영속된 Page post ID를 별도 서버 확인으로 얻은 경우만 명시 조회한다. 목록 검색은 없다.
        with closing(sqlite3.connect(self.root/'facebook-submissions.sqlite3')) as db:
            known=db.execute('SELECT remote_id FROM facebook_submissions').fetchone()[0]
        lookup=adapter.lookup(self.ctx,{**unknown,'remote_id':known});self.assertEqual(lookup.outcome,'matched');self.assertEqual(lookup.candidates[0]['remote_id'],POST);self.assertEqual(len(self.http.posts),1);self.assertEqual(store.get_delivery('d')['state'],'unknown')
    def test_missing_page_type_tasks_authorizer_does_not_make_a_post(self):
        adapter=self.adapter(authorized=False);result=adapter.submit(self.ctx,adapter.prepare(self.ctx,self.snap),object())
        self.assertEqual(result.outcome,'failed');self.assertTrue(result.evidence['confirmed_not_submitted']);self.assertEqual(self.http.posts,[])

    def test_remote_attachment_cannot_be_treated_as_an_empty_media_text_post(self):
        adapter=self.adapter();store=self.submitted(adapter);self.http.attachments=[{'media_type':'photo'}]
        result=verify_delivery(store,'d',adapter,self.snap,now=NOW)
        self.assertEqual(result.outcome,'pending');self.assertNotEqual(store.get_delivery('d')['state'],'verified');self.assertEqual(len(self.http.posts),1)
