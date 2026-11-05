"""격리 SQLite·가짜 클라이언트만 사용하며 실제 업로드·SNS 요청은 없다."""
from dataclasses import replace
from datetime import datetime,timezone,timedelta
import hashlib
from pathlib import Path
import tempfile
import unittest
from common.publishers.instagram_services import InstagramJournal,InstagramServices
from common.publishers.instagram_media_sources import InstagramHostedMedia
from common.publishers.instagram_payloads import build_instagram_payload
from common.operations.runtime_models import PublicationContext
from common.operations.content_store import ConflictError,StoreError

NOW=datetime(2026,11,2,tzinfo=timezone.utc)
TARGET=dict(platform='instagram',target_id='123',connection_id='dept.instagram',expected_login_subject='subject')
def fixture(fmt='image'):
    ids=['one','two'] if fmt=='carousel' else ['one']
    ctx=PublicationContext(content_id='c1',content_revision=1,manifest_hash='manifest',owner_account_id='personal',destination_account_id='dept',connection_id='dept.instagram',target_id='123',publication_purpose='initial',schedule_slot='slot',options={'instagram':{'format':fmt,'asset_ids':ids}},schedule_condition={},registry_revision='r1',policy_revision='p1',auth_checked_at=NOW,auth_expires_at=NOW+timedelta(hours=1),review_report_hashes=('review',),platform='instagram')
    assets=[dict(id=x,sha256=hashlib.sha256(x.encode()).hexdigest(),size=12,media_type='video/mp4' if fmt=='reels' or x=='two' else 'image/jpeg') for x in ids]
    payload=build_instagram_payload(dict(id='c1',revision=1,manifest_hash='manifest',owner_account_id='personal',original='원문 캡션',assets=assets),ctx)
    return ctx,payload
class Client:
    def __init__(self):self.events=[];self.next=100;self.status='FINISHED';self.lost=False
    def inspect_account(self,identifier):self.events.append(('inspect',identifier));return dict(id=identifier,username='dept')
    def create(self,kind,*args,**kw):
        self.events.append((kind,args,kw));self.next+=1
        if self.lost:raise OSError('PRIVATE')
        return {'id':str(self.next)}
    def create_image(self,*a):return self.create('image',*a)
    def create_reels(self,*a):return self.create('reels',*a)
    def create_carousel_item(self,*a,**kw):return self.create('child',*a,**kw)
    def create_carousel(self,*a):return self.create('parent',*a)
    def container_status(self,cid):self.events.append(('status',cid));return {'id':cid,'status_code':self.status}
    def publish(self,*a):return self.create('publish',*a)
class InstagramServicesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.now=NOW;self.client=Client();self.stages=[]
        self.journal=InstagramJournal(Path(self.tmp.name)/'journal');self.journal.initialize()
    def authorizer(self,target,identity):return dict(target_id='123',login_subject='subject',professional=True,can_publish=True,checked_at=self.now,login_mode='facebook_login')
    def stage(self,ctx,prepared):
        self.stages.append(ctx.context_hash)
        return tuple(InstagramHostedMedia(ctx.context_hash,ctx.owner_account_id,ctx.destination_account_id,ctx.connection_id,ctx.target_id,ctx.content_id,ctx.content_revision,ctx.manifest_hash,i,a['id'],a['sha256'],a['size'],a['media_type'],'https://cdn.example.org/'+a['id'],self.now+timedelta(hours=1),'receipt_'+a['id']) for i,a in enumerate(prepared['assets']))
    def service(self,**kw):return InstagramServices(self.client,self.journal,lambda:self.now,**dict(dict(media_factory=self.stage,account_authorizer=self.authorizer,review_guard=lambda *a:True),**kw))
    def writes(self):return [x for x in self.client.events if x[0] in ('image','reels','child','parent','publish')]
    def test_defaults_are_inert_and_do_not_touch_client_or_stage(self):
        path=Path(self.tmp.name)/'inert';journal=InstagramJournal(path);self.assertFalse(path.exists())
        service=InstagramServices(self.client,journal,lambda:(_ for _ in ()).throw(AssertionError()))
        ctx,payload=fixture();self.assertEqual(service.submit(ctx,payload,TARGET)['outcome'],'failed');self.assertEqual(self.client.events,[])
        for missing in ('media_factory','account_authorizer','review_guard'):
            self.assertEqual(self.service(**{missing:None}).submit(ctx,payload,TARGET)['outcome'],'failed')
        self.assertEqual(self.client.events,[]);self.assertEqual(self.stages,[])
    def test_image_reels_and_mixed_carousel_explicit_flow_and_cached_id(self):
        for fmt,kinds in (('image',['image','publish']),('reels',['reels','publish']),('carousel',['child','child','parent','publish'])):
            with self.subTest(fmt=fmt):
                ctx,payload=fixture(fmt);ctx=replace(ctx,schedule_slot=fmt);payload['schedule_slot']=fmt
                before=len(self.writes());service=self.service();result=service.submit(ctx,payload,TARGET)
                self.assertEqual(result['outcome'],'submitted');self.assertIsNone(result['url']);self.assertEqual([x[0] for x in self.writes()[before:]],kinds)
                count=len(self.writes());self.assertEqual(service.submit(ctx,payload,TARGET),result);self.assertEqual(len(self.writes()),count)
                self.assertNotIn('https',str(result));self.assertNotIn('receipt_one',str(result));self.assertNotIn('cdn.example',str(result))
    def test_in_progress_reuses_existing_container_without_stage_or_create(self):
        ctx,payload=fixture();service=self.service();self.client.status='IN_PROGRESS'
        first=service.submit(ctx,payload,TARGET);self.assertEqual(first['outcome'],'failed');self.assertTrue(first['evidence']['confirmed_not_submitted'])
        self.client.status='FINISHED';self.assertEqual(service.submit(ctx,payload,TARGET)['outcome'],'submitted')
        self.assertEqual([x[0] for x in self.writes()],['image','publish']);self.assertEqual(len(self.stages),1)
    def test_lost_child_response_is_unknown_and_never_retries_post_or_stage(self):
        ctx,payload=fixture('carousel');service=self.service();self.client.lost=True
        self.assertEqual(service.submit(ctx,payload,TARGET)['outcome'],'unknown');self.client.lost=False
        self.assertEqual(service.submit(ctx,payload,TARGET)['outcome'],'unknown');self.assertEqual(len(self.writes()),1);self.assertEqual(len(self.stages),1)
    def test_stop_before_every_write_preserves_ready_for_explicit_resume(self):
        ctx,payload=fixture('carousel');service=self.service();checks=[]
        def stop():
            checks.append(1)
            if len(checks)==3:raise RuntimeError('STOP')
        service.before_write=stop
        self.assertEqual(service.submit(ctx,payload,TARGET)['outcome'],'failed');self.assertEqual([x[0] for x in self.writes()],['child'])
        service.before_write=lambda:None;self.assertEqual(service.submit(ctx,payload,TARGET)['outcome'],'submitted')
        self.assertEqual([x[0] for x in self.writes()],['child','child','parent','publish']);self.assertEqual(len(self.stages),1)
    def test_changed_auth_context_and_expired_lease_never_restage_or_post(self):
        ctx,payload=fixture();service=self.service();self.client.status='IN_PROGRESS';service.submit(ctx,payload,TARGET)
        changed=replace(ctx,auth_checked_at=NOW+timedelta(seconds=1));self.client.status='FINISHED'
        self.assertEqual(service.submit(changed,payload,TARGET)['outcome'],'failed');self.assertEqual(len(self.writes()),1)
        self.now=NOW+timedelta(hours=2);self.assertEqual(service.submit(ctx,payload,TARGET)['outcome'],'failed');self.assertEqual(len(self.writes()),1);self.assertEqual(len(self.stages),1)
    def test_authorizer_exact_fresh_professional_proof_required(self):
        for change in ({'professional':False},{'can_publish':1},{'login_mode':'instagram_login'},{'login_subject':'wrong'},{'checked_at':NOW-timedelta(seconds=61)},{'target_id':'999'},{'extra':True}):
            proof={**self.authorizer(None,None),**change};service=self.service(account_authorizer=lambda *a:proof)
            self.assertFalse(service.inspect(TARGET)['authenticated'])
        self.assertFalse(self.service().inspect({**TARGET,'expected_login_subject':None})['authenticated']);self.assertEqual(self.writes(),[])
    def test_invalid_receipt_and_staging_crash_cannot_be_repeated(self):
        ctx,payload=fixture();receipts=self.stage(ctx,payload)
        service=self.service(media_factory=lambda *a:(replace(receipts[0],asset_sha256='b'*64),))
        self.assertEqual(service.submit(ctx,payload,TARGET)['outcome'],'unknown');self.assertEqual(service.submit(ctx,payload,TARGET)['outcome'],'unknown');self.assertEqual(self.writes(),[])
    def test_publish_id_survives_journal_write_failure_and_old_started_is_never_reposted(self):
        ctx,payload=fixture();service=self.service();save=self.journal.save
        def fail(row,state,*a,**kw):
            if state=='submitted':raise StoreError('injected')
            return save(row,state,*a,**kw)
        self.journal.save=fail;result=service.submit(ctx,payload,TARGET)
        self.assertEqual(result['outcome'],'unknown');self.assertIsNotNone(result['remote_id']);count=len(self.writes())
        self.journal.save=save;self.assertEqual(service.submit(ctx,payload,TARGET)['outcome'],'unknown');self.assertEqual(len(self.writes()),count)
    def test_payload_conflict_and_wrong_target_are_rejected_without_new_writes(self):
        ctx,payload=fixture();service=self.service();service.submit(ctx,payload,TARGET);count=len(self.writes())
        changed={**payload,'caption':'변경','caption_sha256':hashlib.sha256('변경'.encode()).hexdigest()}
        self.assertEqual(service.submit(ctx,changed,TARGET)['outcome'],'failed');self.assertEqual(service.submit(ctx,payload,{**TARGET,'target_id':'999'})['outcome'],'failed');self.assertEqual(len(self.writes()),count)
    def test_journal_cas_and_explicit_initialization(self):
        journal=InstagramJournal(Path(self.tmp.name)/'new')
        with self.assertRaises(StoreError):
            with journal.hold('a'*64):pass
        row,new=self.journal.claim('a'*64,'b'*64,{},NOW.isoformat());self.assertTrue(new)
        self.journal.save(row,'ready',{},NOW.isoformat())
        with self.assertRaises(ConflictError):self.journal.save(row,'ready',{},NOW.isoformat())
    def test_staging_intent_is_durable_and_private_before_factory(self):
        ctx,payload=fixture();observed=[]
        def stage(c,p):
            import sqlite3
            from contextlib import closing
            with closing(sqlite3.connect(self.journal.root/'instagram-submissions.sqlite3')) as db:
                observed.append(db.execute('SELECT state FROM instagram_submissions').fetchone()[0])
            return self.stage(c,p)
        result=self.service(media_factory=stage).submit(ctx,payload,TARGET)
        self.assertEqual(result['outcome'],'submitted');self.assertEqual(observed,['staging_started'])
        import stat
        self.assertEqual(stat.S_IMODE((self.journal.root/'instagram-submissions.sqlite3').stat().st_mode),0o600)
    def test_expiry_during_stop_hook_blocks_post_and_revoked_review_preserves_ready(self):
        ctx,payload=fixture();service=self.service();self.client.status='IN_PROGRESS';service.submit(ctx,payload,TARGET)
        self.client.status='FINISHED';service.before_write=lambda:setattr(self,'now',NOW+timedelta(hours=2))
        self.assertEqual(service.submit(ctx,payload,TARGET)['outcome'],'failed');self.assertEqual([x[0] for x in self.writes()],['image'])
        self.now=NOW;service.before_write=lambda:None;service.review_guard=lambda *a:False
        self.assertEqual(service.submit(ctx,payload,TARGET)['outcome'],'failed');service.review_guard=lambda *a:True
        self.assertEqual(service.submit(ctx,payload,TARGET)['outcome'],'submitted');self.assertEqual(len(self.stages),1)
    def test_terminal_container_status_and_published_without_remote_id_never_publish(self):
        for status in ('ERROR','EXPIRED','PUBLISHED'):
            ctx,payload=fixture();ctx=replace(ctx,schedule_slot=status);payload['schedule_slot']=status
            self.client.status=status;result=self.service().submit(ctx,payload,TARGET)
            self.assertEqual(result['outcome'],'unknown' if status=='PUBLISHED' else 'failed')
            self.assertFalse(any(x[0]=='publish' for x in self.writes()))
    def test_old_staging_started_crash_never_stages_again(self):
        ctx,payload=fixture();calls=[]
        def crash(*a):calls.append(1);raise OSError('PRIVATE staging details')
        service=self.service(media_factory=crash);self.assertEqual(service.submit(ctx,payload,TARGET)['outcome'],'unknown')
        self.assertEqual(service.submit(ctx,payload,TARGET)['outcome'],'unknown');self.assertEqual(calls,[1]);self.assertEqual(self.writes(),[])
    def test_review_revocation_inside_stop_hook_blocks_write(self):
        ctx,payload=fixture();service=self.service();self.client.status='IN_PROGRESS';service.submit(ctx,payload,TARGET)
        self.client.status='FINISHED';approved=[True];service.review_guard=lambda *a:approved[0]
        service.before_write=lambda:approved.__setitem__(0,False)
        result=service.submit(ctx,payload,TARGET)
        self.assertEqual(result['outcome'],'failed');self.assertEqual([x[0] for x in self.writes()],['image'])
    def test_stop_before_factory_allows_only_explicit_same_context_restart(self):
        ctx,payload=fixture();service=self.service()
        service.before_write=lambda:(_ for _ in ()).throw(RuntimeError('STOP'))
        self.assertEqual(service.submit(ctx,payload,TARGET)['outcome'],'failed');self.assertEqual(self.stages,[]);self.assertEqual(self.writes(),[])
        service.before_write=lambda:None
        changed=replace(ctx,run_id='newrun')
        self.assertEqual(service.submit(changed,payload,TARGET)['outcome'],'failed');self.assertEqual(self.stages,[])
        self.assertEqual(service.submit(ctx,payload,TARGET)['outcome'],'submitted')
        self.assertEqual(len(self.stages),1);self.assertEqual([x[0] for x in self.writes()],['image','publish'])
    def test_upload_receipt_and_owned_observation_default_not_public(self):
        ctx,payload=fixture();service=self.service();result=service.submit(ctx,payload,TARGET)
        receipt=result['evidence']['upload_receipt']
        self.assertEqual(receipt['assets'],payload['assets']);self.assertEqual(receipt['context_hash'],ctx.context_hash)
        self.client.read_media=lambda rid:dict(id=rid,owner={'id':'123'},caption=payload['caption'],media_type='IMAGE',media_product_type='FEED',timestamp=NOW.isoformat(),permalink='https://www.instagram.com/p/AbC_1/')
        obs=service.observe(ctx,TARGET,result['remote_id'])
        self.assertEqual(obs['visibility'],'unknown');self.assertIsNone(obs['media_sha256']);self.assertEqual(obs['upload_receipt'],receipt)
        self.assertEqual(service.lookup(ctx,TARGET,{'remote_id':result['remote_id']}),[obs])

    def observation(self,payload,remote_id,**changes):
        fmt=payload['media_format']
        return dict(dict(id=remote_id,owner={'id':'123'},caption=payload['caption'],media_type={'image':'IMAGE','reels':'VIDEO','carousel':'CAROUSEL_ALBUM'}[fmt],media_product_type='REELS' if fmt=='reels' else 'FEED',timestamp=NOW.isoformat(),permalink='https://www.instagram.com/reel/ABC/' if fmt=='reels' else 'https://www.instagram.com/p/ABC/'),**changes)
    def test_carousel_first_read_pins_children_but_reorder_cannot_replace_pin(self):
        ctx,payload=fixture('carousel');service=self.service();result=service.submit(ctx,payload,TARGET)
        self.assertIsNone(result['evidence']['upload_receipt']['published_children'])
        self.client.read_media=lambda rid:self.observation(payload,rid)
        children=[{'id':'501','media_type':'IMAGE'},{'id':'502','media_type':'VIDEO'}]
        self.client.read_children=lambda rid:children
        first=service.observe(ctx,TARGET,result['remote_id']);self.assertEqual(first['upload_receipt']['published_children'],children)
        self.client.read_children=lambda rid:list(reversed(children))
        second=service.observe(ctx,TARGET,result['remote_id']);self.assertEqual(second['children'],list(reversed(children)))
        self.assertEqual(second['upload_receipt']['published_children'],children)
        self.assertEqual(service.submit(ctx,payload,TARGET)['evidence']['upload_receipt']['published_children'],children)
        self.assertEqual(len(self.writes()),4)
    def test_read_failure_then_success_and_source_context_binding(self):
        ctx,payload=fixture('carousel');service=self.service();result=service.submit(ctx,payload,TARGET)
        self.client.read_media=lambda rid:(_ for _ in ()).throw(OSError('PRIVATE'))
        self.assertIsNone(service.observe(ctx,TARGET,result['remote_id']))
        self.client.read_media=lambda rid:self.observation(payload,rid)
        self.client.read_children=lambda rid:[{'id':'501','media_type':'IMAGE'},{'id':'502','media_type':'VIDEO'}]
        self.assertIsNotNone(service.observe(ctx,TARGET,result['remote_id']))
        self.assertIsNone(service.observe(replace(ctx,run_id='different'),TARGET,result['remote_id']))
        self.assertIsNone(service.observe(ctx,TARGET,'999'))
        self.now=NOW+timedelta(hours=2)
        self.assertIsNotNone(service.observe(ctx,TARGET,result['remote_id']))
    def test_public_probe_exact_fresh_proof_only_and_invalid_observations(self):
        for fmt in ('image','reels','carousel'):
            ctx,payload=fixture(fmt);ctx=replace(ctx,schedule_slot=fmt);payload['schedule_slot']=fmt
            service=self.service();result=service.submit(ctx,payload,TARGET)
            self.client.read_media=lambda rid:self.observation(payload,rid)
            self.client.read_children=lambda rid:[{'id':'501','media_type':'IMAGE'},{'id':'502','media_type':'VIDEO'}]
            def proof(obs):return {**{k:obs[k] for k in ('remote_id','target_id','body_sha256','url','media_format','children')},'public':True,'checked_at':self.now}
            service.public_probe=proof
            self.assertEqual(service.observe(ctx,TARGET,result['remote_id'])['visibility'],'public')
            for change in ({'public':False},{'target_id':'999'},{'checked_at':NOW-timedelta(seconds=1)},{'url':'https://www.instagram.com/p/other/'},{'children':[] if fmt=='carousel' else [{'id':'9','media_type':'IMAGE'}]}):
                service.public_probe=lambda obs,change=change:{**proof(obs),**change}
                self.assertEqual(service.observe(ctx,TARGET,result['remote_id'])['visibility'],'unknown')
            for change in ({'owner':{'id':'999'}},{'permalink':'https://evil.example/p/ABC/'},{'timestamp':(NOW+timedelta(seconds=1)).isoformat()},{'media_product_type':'INVALID'}):
                self.client.read_media=lambda rid,change=change:self.observation(payload,rid,**change)
                self.assertIsNone(service.observe(ctx,TARGET,result['remote_id']))
    def test_unknown_known_id_retains_upload_receipt_and_lookup_never_posts(self):
        ctx,payload=fixture();service=self.service();save=self.journal.save
        def fail(row,state,*a,**kw):
            if state=='submitted':raise StoreError('failure')
            return save(row,state,*a,**kw)
        self.journal.save=fail;result=service.submit(ctx,payload,TARGET);self.journal.save=save
        self.assertEqual(result['outcome'],'unknown');self.assertEqual(result['evidence']['upload_receipt']['remote_id'],result['remote_id'])
        self.client.read_media=lambda rid:self.observation(payload,rid)
        count=len(self.writes());self.assertEqual(len(service.lookup(ctx,TARGET,result)),1);self.assertEqual(len(self.writes()),count)

    def test_receipt_original_context_survives_cached_replay_and_read_fields_are_exact(self):
        ctx,payload=fixture();service=self.service();result=service.submit(ctx,payload,TARGET)
        changed=replace(ctx,run_id='new-run')
        self.assertEqual(service.submit(changed,payload,TARGET)['evidence']['upload_receipt']['context_hash'],ctx.context_hash)
        self.client.read_media=lambda rid:self.observation(payload,rid)
        obs=service.observe(ctx,TARGET,result['remote_id'])
        self.assertEqual(set(obs),{'remote_id','target_id','created_at','text','body_sha256','media_sha256','media_format','media_type','media_product_type','media_status','children','visibility','url','upload_receipt'})
        self.assertEqual(obs['text'],payload['caption']);self.assertEqual(obs['media_type'],'IMAGE')
    def test_carousel_pin_write_failure_cannot_claim_observation(self):
        ctx,payload=fixture('carousel');service=self.service();result=service.submit(ctx,payload,TARGET)
        self.client.read_media=lambda rid:self.observation(payload,rid)
        self.client.read_children=lambda rid:[{'id':'501','media_type':'IMAGE'},{'id':'502','media_type':'VIDEO'}]
        save=self.journal.save;self.journal.save=lambda *a,**kw:(_ for _ in ()).throw(StoreError('PRIVATE'))
        self.assertIsNone(service.observe(ctx,TARGET,result['remote_id']))
        self.journal.save=save
        self.assertIsNotNone(service.observe(ctx,TARGET,result['remote_id']))
    def test_unknown_carousel_known_id_can_pin_readonly_without_repost(self):
        ctx,payload=fixture('carousel');service=self.service();save=self.journal.save
        def fail(row,state,*a,**kw):
            if state=='submitted':raise StoreError('injected')
            return save(row,state,*a,**kw)
        self.journal.save=fail;result=service.submit(ctx,payload,TARGET);self.journal.save=save
        self.assertEqual(result['outcome'],'unknown');self.assertIsNone(result['evidence']['upload_receipt']['published_children'])
        self.client.read_media=lambda rid:self.observation(payload,rid)
        children=[{'id':'501','media_type':'IMAGE'},{'id':'502','media_type':'VIDEO'}]
        self.client.read_children=lambda rid:children
        count=len(self.writes());obs=service.observe(ctx,TARGET,result['remote_id'])
        self.assertIsNotNone(obs);self.assertEqual(obs['upload_receipt']['published_children'],children)
        self.assertEqual(service.lookup(ctx,TARGET,result),[obs]);self.assertEqual(len(self.writes()),count)
        self.assertEqual(service.submit(ctx,payload,TARGET)['outcome'],'unknown');self.assertEqual(len(self.writes()),count)
        self.assertIsNone(service.observe(ctx,TARGET,'999'))
    def test_wrong_first_carousel_observation_does_not_poison_pin(self):
        for bad in ('count','type','caption'):
            ctx,payload=fixture('carousel');ctx=replace(ctx,schedule_slot=bad);payload['schedule_slot']=bad
            service=self.service();result=service.submit(ctx,payload,TARGET);count=len(self.writes())
            correct=[{'id':'501','media_type':'IMAGE'},{'id':'502','media_type':'VIDEO'}]
            children=correct+[{'id':'503','media_type':'IMAGE'}] if bad=='count' else [{'id':'501','media_type':'VIDEO'},{'id':'502','media_type':'IMAGE'}] if bad=='type' else correct
            self.client.read_children=lambda rid:children
            self.client.read_media=lambda rid:self.observation(payload,rid,**({'caption':'다른 캡션'} if bad=='caption' else {}))
            first=service.observe(ctx,TARGET,result['remote_id']);self.assertIsNotNone(first)
            self.assertIsNone(first['upload_receipt']['published_children'])
            self.client.read_children=lambda rid:correct;self.client.read_media=lambda rid:self.observation(payload,rid)
            self.assertEqual(service.observe(ctx,TARGET,result['remote_id'])['upload_receipt']['published_children'],correct)
            self.assertEqual(len(self.writes()),count)
    def test_raw_or_encoded_url_controls_rejected_before_probe_or_pin(self):
        ctx,payload=fixture('carousel');calls=[];service=self.service(public_probe=lambda obs:calls.append(obs));result=service.submit(ctx,payload,TARGET)
        self.client.read_children=lambda rid:[{'id':'501','media_type':'IMAGE'},{'id':'502','media_type':'VIDEO'}]
        for url in ('https://www.instagram.com/p/ABC/\n','https://www.instagram.com/p/ABC/%0a','https://www.instagram.com/\tp/ABC/'):
            self.client.read_media=lambda rid,url=url:self.observation(payload,rid,permalink=url)
            self.assertIsNone(service.observe(ctx,TARGET,result['remote_id']))
        self.assertEqual(calls,[])
        self.assertIsNone(service.submit(ctx,payload,TARGET)['evidence']['upload_receipt']['published_children'])
