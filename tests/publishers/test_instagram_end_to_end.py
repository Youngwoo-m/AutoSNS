"""가짜 HTTP/공개전달→실제 Instagram 경계→실제 RuntimeStore 공개 검증.

InlineBridge는 BridgeHost child permit 자체를 검증하지 않는다. 실제 RuntimeStore의
승인·lease·permit 생성/소비·finish는 수행한다. 독립 원고/권리 검토는 fixture guard이며
실제 계정·로그인·공개 파일·API 전송은 없다. 변환 원격 해시는 만들어내지 않는다.
"""
from contextlib import closing
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs,urlsplit
from common.operations.content_store import ContentStore,StoreError
from common.operations.models import Registry,Connection
from common.operations.runtime_models import PublicationContext
from common.operations.runtime_store import RuntimeStore
from common.operations.verification import verify_delivery
from common.operations.recovery import reconcile_delivery
from common.publishers.instagram import InstagramAdapter
from common.publishers.instagram_client import InstagramApiClient
from common.publishers.instagram_runtime import build_instagram_handlers
from common.publishers.instagram_services import InstagramJournal,InstagramServices
from common.publishers.instagram_media_sources import InstagramMediaSourceFactory

NOW=datetime(2026,11,2,tzinfo=timezone.utc)
PAGE='123';REMOTE='900';URL='https://www.instagram.com/p/AbC123/'
JPEG=b'\xff\xd8\xfffixture-image\xff\xd9';VIDEO=b'\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isommp42'
class FakeHTTP:
    def __init__(self):self.calls=[];self.forms={};self.text=None;self.fmt='image';self.children_failure=False;self.reverse=False;self.caption_override=None
    def __call__(self,method,path,headers,body):
        self.calls.append((method,path));assert headers['Authorization']=='Bearer fake-instagram-token'
        route=urlsplit(path).path;node=route.rsplit('/',1)[-1]
        if method=='POST' and route=='/v26.0/'+PAGE+'/media':
            form={k:v[0] for k,v in parse_qs(body.decode(),keep_blank_values=True).items()};identifier=str(100+len(self.forms));self.forms[identifier]=form
            if 'caption' in form:
                self.text=form['caption'];self.fmt='carousel' if form.get('media_type')=='CAROUSEL' else 'reels' if form.get('media_type')=='REELS' else 'image'
            row={'id':identifier}
        elif method=='POST' and route=='/v26.0/'+PAGE+'/media_publish':row={'id':REMOTE}
        elif method=='GET' and route=='/v26.0/'+PAGE:row=dict(id=PAGE,username='fixture-dept')
        elif method=='GET' and route=='/v26.0/'+REMOTE+'/children':
            if self.children_failure:return 500,b'{"error":{"message":"fixture unavailable"}}'
            children=[dict(id='701',media_type='IMAGE'),dict(id='702',media_type='VIDEO')]
            row={'data':list(reversed(children)) if self.reverse else children}
        elif method=='GET' and route=='/v26.0/'+REMOTE:
            row=dict(id=REMOTE,owner={'id':PAGE},caption=self.caption_override if self.caption_override is not None else self.text,media_type={'image':'IMAGE','reels':'VIDEO','carousel':'CAROUSEL_ALBUM'}[self.fmt],media_product_type='REELS' if self.fmt=='reels' else 'FEED',timestamp=NOW.isoformat(),permalink=URL)
        elif method=='GET' and node in self.forms:row=dict(id=node,status_code='FINISHED')
        else:raise AssertionError('unexpected fixture route')
        return 200,json.dumps(row,ensure_ascii=False).encode()
    @property
    def posts(self):return [x for x in self.calls if x[0]=='POST']
class InstagramEndToEndTests(unittest.TestCase):
    def setUp(self):
        network_guard=patch('socket.socket',side_effect=AssertionError('real network forbidden'));network_guard.start();self.addCleanup(network_guard.stop)
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.content=ContentStore(self.root);self.content.initialize()
        snap=self.content.create('personal',dict(title='개인 원본',kind='card',original='개인 원고',variants=[dict(destination_account_id='dept',platform='instagram',text=' 학과 교차 게시\n그대로 ')]))
        for name,mime,raw in (('original.png','image/png',b'\x89PNG\r\n\x1a\nnot-selected'),('selected.jpg','image/jpeg',JPEG),('selected.mp4','video/mp4',VIDEO)):
            snap=self.content.add_asset(snap['id'],snap['revision'],name,mime,raw)
        self.snap=snap;self.ids=[a['id'] for a in snap['assets']]
        self.registry=Registry('r',{'personal':{},'dept':{}},{'dept.instagram.credential':dict(account_id='dept',platform='instagram')},{'dept':dict(account_id='dept',lock_resource='profile:insta')},{'dept.instagram':Connection('dept.instagram','dept','instagram',target_id=PAGE,credential_ref='dept.instagram.credential',profile_ref='dept',enabled=True,capabilities=('plan','visibility:public'),expected_login_subject='fixture-user')},{'instagram-job':dict(executor_id='instagram.dept',connection_id='dept.instagram',enabled=True,execution_owner='managed',managed_eligible=True)}, {},{})
        self.http=FakeHTTP();self.stages=[];self.client=InstagramApiClient('fake-instagram-token',api_version='v26.0',transport=self.http)
        self.journal=InstagramJournal(self.root);self.journal.initialize()
    def context(self,fmt='image'):
        ids=self.ids[1:2] if fmt=='image' else self.ids[2:] if fmt=='reels' else self.ids[1:]
        return PublicationContext(content_id=self.snap['id'],content_revision=self.snap['revision'],manifest_hash=self.snap['manifest_hash'],owner_account_id='personal',destination_account_id='dept',connection_id='dept.instagram',target_id=PAGE,publication_purpose='initial',schedule_slot='slot',options={'instagram':{'format':fmt,'asset_ids':ids}},schedule_condition={},registry_revision='r',policy_revision='p',auth_checked_at=NOW,auth_expires_at=NOW+timedelta(hours=1),review_report_hashes=('source-review','numbers-review'),platform='instagram',run_id='r')
    def adapter(self,ctx,*,public=True,unknown=False,tamper=None):
        def stage(request,raw):
            self.stages.append((dict(request),raw));return dict(url='https://cdn.example.org/'+request['asset_id'],asset_sha256=hashlib.sha256(raw).hexdigest(),asset_size=len(raw),expires_at=NOW+timedelta(hours=1),receipt_id='receipt_'+str(len(self.stages)))
        factory=InstagramMediaSourceFactory(self.content.read_asset,stager=stage,approval_guard=lambda *a:True,allowed_hosts=('cdn.example.org',),clock=lambda:NOW)
        def authorize(target,identity):return dict(target_id=PAGE,login_subject='fixture-user',professional=True,can_publish=True,checked_at=NOW,login_mode='facebook_login')
        def probe(observation):
            return dict(public=True,remote_id=observation['remote_id'],target_id=observation['target_id'],body_sha256=observation['body_sha256'],url=observation['url'],media_format=observation['media_format'],children=observation['children'],checked_at=NOW)
        service=InstagramServices(self.client,self.journal,lambda:NOW,media_factory=factory,account_authorizer=authorize,review_guard=lambda *a:True,public_probe=probe if public else None)
        if unknown:
            save=self.journal.save;failed=[False]
            def fail_submitted_once(row,state,*args,**kwargs):
                if state=='submitted' and not failed[0]:failed[0]=True;raise StoreError('fixture_save_failed')
                return save(row,state,*args,**kwargs)
            self.journal.save=fail_submitted_once
        handlers=build_instagram_handlers(self.registry,services_factory=lambda *a:service,clock=lambda:NOW)
        content=self.content
        class InlineBridge:
            def __init__(self):self.store=type('StoreView',(),{'content_store':content})()
            def read(self,executor,action,context,payload):return handlers[(executor,action)](context.to_dict(),payload,None)
            def submit(self,executor,context,prepared,permit):
                result=handlers[(executor,'publish')](context.to_dict(),prepared,None)
                if tamper:tamper(result)
                return result
        return InstagramAdapter(self.registry,InlineBridge())
    def started(self,ctx):
        store=RuntimeStore(self.root,self.registry,self.content);store.initialize()
        with closing(sqlite3.connect(self.root/'operations.sqlite3')) as db:
            db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?)',('r','instagram-job',NOW.isoformat(),'prepare','fixture','{}'))
            db.execute('INSERT INTO deliveries VALUES(?,?,?,?,?,?,?,?)',('d',self.snap['id'],self.snap['revision'],'dept.instagram','initial','slot','fixture',json.dumps({'status':'ready','approval':{'subject_hash':'fixture'}})));db.commit()
        from common.shared.axlock import AxLock,LockPaths
        store.locks=AxLock(LockPaths.from_root(self.root/'source'),process_probe=lambda _:False)
        store.create_run('r');store.create_delivery('d','r',ctx);store.record_publication_approval('d',1,ctx.context_hash,'approval',ctx.review_report_hashes)
        lease=store.claim_run('r','worker',{'host_id':'fixture','pid':123,'started_at':NOW.isoformat()},NOW)
        attempt=store.create_attempt('d',store.get_delivery('d')['version'],lease,ctx.context_hash,'approval',now=NOW)
        permit=store.issue_permit(attempt['id'],lease,ctx.context_hash,'approval',NOW);store.consume_permit(permit,lease,NOW)
        return store,attempt,permit
    def submitted(self,ctx,adapter,outcome='submitted'):
        store,attempt,permit=self.started(ctx);result=adapter.submit(ctx,adapter.prepare(ctx,self.snap),permit)
        self.assertEqual(result.outcome,outcome);store.finish_attempt(attempt['id'],outcome,remote_id=result.remote_id,url=result.url,evidence=result.evidence,now=NOW)
        return store
    def test_image_reels_and_carousel_selected_assets_crosspost_verify_without_remote_hash(self):
        # 각 형식은 독립된 임시 저장소에서 검증한다.
        for fmt,count in (('image',2),('reels',2),('carousel',4)):
            with self.subTest(fmt=fmt):
                if fmt!='image':self.setUp()
                ctx=self.context(fmt);adapter=self.adapter(ctx);store=self.submitted(ctx,adapter)
                result=verify_delivery(store,'d',adapter,self.snap,now=NOW)
                self.assertEqual(result.outcome,'verified');self.assertEqual(store.get_delivery('d')['url'],URL)
                self.assertIsNone(result.evidence['media_sha256']);self.assertIn('instagram',result.evidence['verification_method']);self.assertNotIn('cdn.example.org',str(result.evidence))
                self.assertEqual(len(self.http.posts),count);self.assertEqual(self.http.text,' 학과 교차 게시\n그대로 ')
                self.assertEqual(self.content.get(self.snap['id']),self.snap);self.assertEqual(len(self.snap['assets']),3)
                self.assertEqual([a['id'] for a in result.evidence['upload_receipt']['assets']],list(ctx.options['instagram']['asset_ids']))
                self.assertNotIn(self.ids[0],[a['id'] for a in result.evidence['upload_receipt']['assets']])
    def test_owned_read_without_public_probe_stays_pending_and_url_unpersisted(self):
        ctx=self.context();adapter=self.adapter(ctx,public=False);store=self.submitted(ctx,adapter)
        self.assertEqual(verify_delivery(store,'d',adapter,self.snap,now=NOW).outcome,'pending')
        self.assertIsNone(store.get_delivery('d')['url']);self.assertEqual(len(self.http.posts),2)
    def test_provisional_carousel_children_pin_finishes_on_read_only_observation(self):
        ctx=self.context('carousel');self.http.children_failure=True;adapter=self.adapter(ctx);store=self.submitted(ctx,adapter)
        self.assertEqual(verify_delivery(store,'d',adapter,self.snap,now=NOW).outcome,'pending')
        count=len(self.http.posts);self.http.children_failure=False
        self.assertEqual(verify_delivery(store,'d',adapter,self.snap,now=NOW).outcome,'verified');self.assertEqual(len(self.http.posts),count)
    def test_reordered_remote_children_or_changed_caption_never_verify(self):
        ctx=self.context('carousel');adapter=self.adapter(ctx);store=self.submitted(ctx,adapter);self.http.reverse=True
        self.assertEqual(verify_delivery(store,'d',adapter,self.snap,now=NOW).outcome,'pending');self.http.reverse=False;self.http.caption_override='교체된 캡션'
        self.assertEqual(verify_delivery(store,'d',adapter,self.snap,now=NOW).outcome,'failed');self.assertIsNone(store.get_delivery('d')['url'])
    def test_missing_or_tampered_source_receipt_stays_pending(self):
        for action in ('missing','tampered'):
            with self.subTest(action=action):
                if action=='tampered':self.setUp()
                ctx=self.context()
                def tamper(result):
                    if action=='missing':result['evidence'].pop('upload_receipt',None)
                    else:result['evidence']['upload_receipt']['caption_sha256']='0'*64
                adapter=self.adapter(ctx,tamper=tamper);store=self.submitted(ctx,adapter)
                self.assertEqual(verify_delivery(store,'d',adapter,self.snap,now=NOW).outcome,'pending');self.assertEqual(len(self.http.posts),2)
    def test_known_remote_unknown_reconciles_read_only_then_verifies_preserving_receipt(self):
        ctx=self.context('carousel');adapter=self.adapter(ctx,unknown=True);store=self.submitted(ctx,adapter,'unknown');before=len(self.http.posts)
        result=reconcile_delivery(store,'d',adapter,NOW,expected_version=store.get_delivery('d')['version'],request_key='reconcile-instagram')
        self.assertEqual(store.get_delivery('d')['remote_id'],REMOTE);self.assertEqual(len(self.http.posts),before)
        self.assertEqual(verify_delivery(store,'d',adapter,self.snap,now=NOW).outcome,'verified')
        self.assertEqual(store.get_delivery('d')['url'],URL);self.assertEqual(len(self.http.posts),before)
        final=store.attempts('d')[-1]['result']['resolution']['evidence']['upload_receipt']
        self.assertEqual(final['context_hash'],ctx.context_hash);self.assertEqual(final['remote_id'],REMOTE)
        self.assertEqual([c['id'] for c in final['published_children']],['701','702'])
