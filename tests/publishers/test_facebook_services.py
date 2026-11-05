"""Facebook 페이지 권한·발행 원장은 가짜 client/증명자만 사용한다."""
from datetime import datetime,timedelta,timezone
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from common.operations.content_store import StoreError
from common.publishers.facebook_services import FacebookJournal,FacebookServices

NOW=datetime(2026,11,2,tzinfo=timezone.utc)
TARGET=dict(platform='facebook',connection_id='dept.facebook',target_id='123',expected_login_subject='admin-user')
def prepared(**changes):
    value=dict(platform='facebook',connection_id='dept.facebook',target_id='123',owner_account_id='personal',destination_account_id='dept',content_id='content',content_revision=1,manifest_hash='manifest',publication_purpose='initial',schedule_slot='main',text='안전 원고',body_sha256=hashlib.sha256('안전 원고'.encode()).hexdigest(),media_sha256=[])
    value.update(changes);return value

def authorize(target,identity):
    return dict(page_id=target['target_id'],token_subject=identity['id'],login_subject='admin-user',can_publish=True,tasks_checked=True,checked_at=NOW.isoformat(),page_type='page')
def public(obs):return dict(public=True,remote_id=obs['remote_id'],target_id=obs['target_id'],body_sha256=obs['body_sha256'],url=obs['url'],checked_at=NOW.isoformat())
class Client:
    def __init__(self):self.calls=[];self.subject='123';self.fail=None;self.on_post=None
    def me(self):self.calls.append(('me',));return {'id':self.subject,'name':'Page'}
    def create_text(self,page,text):
        self.calls.append(('post',page,text))
        if self.on_post:self.on_post()
        if self.fail=='post':raise RuntimeError('PRIVATE-TOKEN')
        return {'id':page+'_456'}
    def read_post(self,post):
        self.calls.append(('read',post));return {'id':post,'from':{'id':'123'},'message':'안전 원고','created_time':NOW.isoformat(),'permalink_url':'https://www.facebook.com/123/posts/456','is_published':True,'is_hidden':False,'attachments':[]}

class FacebookServicesTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)/'managed'
        self.journal=FacebookJournal(self.root);self.client=Client()
        self.service=FacebookServices(self.client,self.journal,lambda:NOW,page_authorizer=authorize)
    def ready(self):self.journal.initialize()
    def posts(self):return [call for call in self.client.calls if call[0]=='post']
    def test_constructor_and_missing_page_authorizer_are_inert_and_not_authenticated(self):
        service=FacebookServices(self.client,self.journal,lambda:NOW)
        self.assertEqual(self.client.calls,[]);self.assertFalse(self.root.exists())
        self.assertFalse(service.inspect(TARGET)['authenticated']);self.assertEqual(service.inspect(TARGET)['status'],'needs_review')
        self.assertEqual(self.client.calls,[])
        with self.assertRaises(StoreError):FacebookServices(self.client,self.journal,lambda:NOW,page_authorizer=True)
        with self.assertRaises(StoreError):FacebookServices(self.client,self.journal,lambda:NOW,public_probe=True)
    def test_inspect_requires_explicit_page_tasks_subject_and_fresh_attestation(self):
        observed=self.service.inspect(TARGET);self.assertTrue(observed['authenticated']);self.assertEqual(observed['login_subject'],'admin-user');self.assertEqual(observed['target_id'],'123')
        for patch in ({'page_id':'999'},{'token_subject':'999'},{'login_subject':'other'},{'can_publish':False},{'tasks_checked':1},{'page_type':'user'},{'checked_at':(NOW-timedelta(seconds=1)).isoformat()},{'checked_at':(NOW+timedelta(seconds=1)).isoformat()},{'extra':'PRIVATE'}):
            service=FacebookServices(self.client,self.journal,lambda:NOW,page_authorizer=lambda target,identity,p=patch:{**authorize(target,identity),**p})
            self.assertFalse(service.inspect(TARGET)['authenticated'])
        self.client.subject='999';self.assertFalse(self.service.inspect(TARGET)['authenticated']);self.assertEqual(self.posts(),[])
    def test_submitted_id_persisted_before_return_and_replay_does_not_post(self):
        self.ready();result=self.service.submit(prepared(),TARGET);self.assertEqual(result['outcome'],'submitted');self.assertEqual(result['remote_id'],'123_456')
        self.assertEqual(self.service.submit(prepared(),TARGET),result);self.assertEqual(len(self.posts()),1)
        db=sqlite3.connect(self.root/'facebook-submissions.sqlite3')
        try:self.assertEqual(db.execute('SELECT state,remote_id FROM facebook_submissions').fetchone(),('submitted','123_456'))
        finally:db.close()
        self.client.subject='999';self.assertEqual(self.service.submit(prepared(),TARGET)['outcome'],'failed');self.assertEqual(len(self.posts()),1)
    def test_post_exception_and_interrupted_started_never_repost_even_new_instance(self):
        self.ready();self.client.fail='post';result=self.service.submit(prepared(),TARGET)
        self.assertEqual(result['outcome'],'unknown');self.assertNotIn('PRIVATE-TOKEN',str(result));self.client.fail=None
        reopened=FacebookJournal(self.root);reopened.initialize();service=FacebookServices(self.client,reopened,lambda:NOW,page_authorizer=authorize)
        self.assertEqual(service.submit(prepared(),TARGET)['outcome'],'unknown');self.assertEqual(len(self.posts()),1)
        def interrupt(*args):raise KeyboardInterrupt()
        original=self.client.create_text;self.client.create_text=interrupt
        with self.assertRaises(KeyboardInterrupt):service.submit(prepared(schedule_slot='interrupted'),TARGET)
        self.client.create_text=original
        self.assertEqual(service.submit(prepared(schedule_slot='interrupted'),TARGET)['outcome'],'unknown');self.assertEqual(len(self.posts()),1)
    def test_known_prepost_stop_can_reenter_only_on_next_explicit_submit(self):
        self.ready()
        def stop():raise RuntimeError('PRIVATE-STOP')
        self.service.before_write=stop;result=self.service.submit(prepared(),TARGET)
        self.assertEqual(result['outcome'],'failed');self.assertTrue(result['evidence']['confirmed_not_submitted']);self.assertEqual(self.posts(),[])
        self.service.before_write=lambda:None
        self.assertEqual(self.service.submit(prepared(),TARGET)['outcome'],'submitted');self.assertEqual(len(self.posts()),1)
    def test_changed_payload_same_logical_intent_cannot_get_a_new_post(self):
        self.ready();self.service.submit(prepared(),TARGET)
        changed=self.service.submit(prepared(manifest_hash='changed'),TARGET)
        self.assertEqual(changed['outcome'],'failed');self.assertTrue(changed['evidence']['confirmed_not_submitted']);self.assertEqual(len(self.posts()),1)
    def test_concurrent_same_intent_claims_once_and_started_commit_precedes_post(self):
        self.ready();entered=threading.Event();release=threading.Event();results=[]
        def hold():
            db=sqlite3.connect(self.root/'facebook-submissions.sqlite3')
            try:self.assertEqual(db.execute('SELECT state FROM facebook_submissions').fetchone()[0],'started')
            finally:db.close()
            entered.set();release.wait(3)
        self.client.on_post=hold
        thread=threading.Thread(target=lambda:results.append(self.service.submit(prepared(),TARGET)));thread.start();self.assertTrue(entered.wait(3))
        try:self.assertEqual(self.service.submit(prepared(),TARGET)['outcome'],'unknown');self.assertEqual(len(self.posts()),1)
        finally:release.set();thread.join(3)
        self.assertFalse(thread.is_alive());self.assertEqual(results[0]['outcome'],'submitted');self.assertEqual(len(self.posts()),1)
    def test_wrong_or_missing_composite_response_is_unknown_not_retryable(self):
        self.ready()
        for index,response in enumerate(({'id':'999_456'},{'id':'456'},{'id':None},{})):
            self.client.create_text=lambda *args,r=response:r
            result=self.service.submit(prepared(schedule_slot=str(index)),TARGET)
            self.assertEqual(result['outcome'],'unknown')
    def test_owner_api_flags_do_not_prove_public_and_private_flags_prevent_probe(self):
        observation=self.service.read_post(TARGET,'123_456');self.assertEqual(observation['visibility'],'unknown');self.assertEqual(observation['body_sha256'],prepared()['body_sha256'])
        read=self.client.read_post;calls=[]
        self.service.public_probe=lambda obs:(calls.append(obs),public(obs))[1]
        for patch in ({'is_published':False},{'is_hidden':True}):
            self.client.read_post=lambda post,p=patch:{**read(post),**p}
            self.assertEqual(self.service.read_post(TARGET,'123_456')['visibility'],'private')
        self.assertEqual(calls,[]);self.assertEqual(self.posts(),[])
    def test_public_probe_requires_exact_fresh_identity_text_and_url_proof(self):
        service=FacebookServices(self.client,self.journal,lambda:NOW,page_authorizer=authorize,public_probe=public)
        self.assertEqual(service.read_post(TARGET,'123_456')['visibility'],'public')
        for patch in ({'public':1},{'remote_id':'123_999'},{'target_id':'999'},{'body_sha256':'0'*64},{'url':'https://www.facebook.com/other'},{'checked_at':(NOW-timedelta(seconds=1)).isoformat()},{'extra':'PRIVATE'}):
            service.public_probe=lambda obs,p=patch:{**public(obs),**p}
            self.assertEqual(service.read_post(TARGET,'123_456')['visibility'],'unknown')
        self.assertEqual(self.posts(),[])
    def test_remote_read_exact_owner_post_text_time_and_url_required(self):
        read=self.client.read_post
        for patch in ({'id':'123_999'},{'from':{'id':'999'}},{'created_time':'invalid'},{'message':''},{'permalink_url':'https://evil.example/post'},{'is_published':1},{'is_hidden':None}):
            self.client.read_post=lambda post,p=patch:{**read(post),**p}
            self.assertIsNone(self.service.read_post(TARGET,'123_456'))
        self.client.read_post=read
        self.assertEqual(len(self.service.lookup(TARGET,{'result':{'remote_id':'123_456'}})),1)
        count=len(self.client.calls);self.assertEqual(self.service.lookup(TARGET,{}),[]);self.assertEqual(len(self.client.calls),count)
    def test_payload_mismatch_or_no_page_proof_prevents_any_post(self):
        self.ready()
        for patch in ({'target_id':'999'},{'connection_id':'personal.facebook'},{'media_sha256':['image']},{'body_sha256':'wrong'},{'extra':'PRIVATE'}):
            self.assertEqual(self.service.submit(prepared(**patch),TARGET)['outcome'],'failed')
        service=FacebookServices(self.client,self.journal,lambda:NOW)
        self.assertEqual(service.submit(prepared(),TARGET)['outcome'],'failed');self.assertEqual(self.posts(),[])
    def test_journal_foreign_schema_symlink_and_uninitialized_never_start_post(self):
        self.assertEqual(self.service.submit(prepared(),TARGET)['outcome'],'unknown');self.assertFalse(self.root.exists());self.assertEqual(self.posts(),[])
        self.root.mkdir();db=sqlite3.connect(self.root/'facebook-submissions.sqlite3');db.execute('CREATE TABLE keep(value)');db.commit();db.close()
        with self.assertRaises(StoreError):self.journal.initialize()
        (self.root/'facebook-submissions.sqlite3').unlink();target=self.root.parent/'other';(self.root/'facebook-submissions.sqlite3').symlink_to(target)
        with self.assertRaises(StoreError):self.journal.initialize()
        self.assertFalse(target.exists())

    def test_known_post_id_survives_journal_result_write_failure_without_second_post(self):
        self.ready();transition=self.journal.transition
        def failed(row,state,*args,**kwargs):
            if state=='submitted':raise OSError('PRIVATE-DISK-CONTEXT')
            return transition(row,state,*args,**kwargs)
        self.journal.transition=failed
        result=self.service.submit(prepared(),TARGET)
        self.assertEqual(result['outcome'],'unknown');self.assertEqual(result['remote_id'],'123_456')
        self.assertNotIn('PRIVATE-DISK-CONTEXT',str(result));self.assertEqual(len(self.posts()),1)
        self.journal.transition=transition
        self.assertEqual(self.service.submit(prepared(),TARGET)['outcome'],'unknown');self.assertEqual(len(self.posts()),1)
        self.assertEqual(self.service.lookup(TARGET,{'result':result})[0]['remote_id'],'123_456')

    def test_probes_cannot_mutate_identity_and_raw_api_flags_cannot_create_proof(self):
        def mutate(target,identity):
            identity['id']='999';target['target_id']='999'
            return authorize(target,identity)
        service=FacebookServices(self.client,self.journal,lambda:NOW,page_authorizer=mutate)
        self.assertFalse(service.inspect(TARGET)['authenticated']);self.assertEqual(TARGET['target_id'],'123')
        def mutate_public(obs):
            obs['remote_id']='123_999';obs['media_sha256'].append('fake')
            return public(obs)
        service=FacebookServices(self.client,self.journal,lambda:NOW,page_authorizer=authorize,public_probe=mutate_public)
        observation=service.read_post(TARGET,'123_456');self.assertEqual(observation['remote_id'],'123_456')
        self.assertEqual(observation['media_sha256'],[]);self.assertEqual(observation['visibility'],'unknown')
        self.assertEqual(self.posts(),[])

    def test_authorizer_and_public_probe_errors_are_sanitized_without_journal_mutation(self):
        def fail(*args):raise RuntimeError('PRIVATE-PROBE-TOKEN')
        service=FacebookServices(self.client,self.journal,lambda:NOW,page_authorizer=fail)
        result=service.inspect(TARGET);self.assertFalse(result['authenticated']);self.assertNotIn('PRIVATE-PROBE-TOKEN',str(result))
        service=FacebookServices(self.client,self.journal,lambda:NOW,page_authorizer=authorize,public_probe=fail)
        result=service.read_post(TARGET,'123_456');self.assertEqual(result['visibility'],'unknown');self.assertNotIn('PRIVATE-PROBE-TOKEN',str(result))
        self.assertFalse(self.root.exists());self.assertEqual(self.posts(),[])

    def test_missing_or_nonempty_remote_attachments_cannot_claim_text_only_public(self):
        read=self.client.read_post
        service=FacebookServices(self.client,self.journal,lambda:NOW,page_authorizer=authorize,public_probe=public)
        for attachments in (None,{},'',False,[{'id':'media'}],({'media_type':'photo'},)):
            self.client.read_post=lambda post,a=attachments:{**read(post),'attachments':a}
            self.assertIsNone(service.read_post(TARGET,'123_456'))
        def missing(post):
            row=read(post);del row['attachments'];return row
        self.client.read_post=missing;self.assertIsNone(service.read_post(TARGET,'123_456'))
        self.assertEqual(self.posts(),[])
