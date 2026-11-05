"""Threads 생성/게시 원장은 가짜 API만 사용하며 불명확한 POST를 재시도하지 않는다."""
from contextlib import contextmanager
from datetime import datetime,timezone
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from common.publishers.threads_services import ThreadsJournal,ThreadsServices
from common.operations.content_store import StoreError

NOW=datetime(2026,11,2,tzinfo=timezone.utc)
TARGET=dict(platform='threads',connection_id='dept.threads',target_id='10001',expected_login_subject='10001')
def prepared(**kw):
    value=dict(platform='threads',connection_id='dept.threads',target_id='10001',owner_account_id='personal',destination_account_id='dept',content_id='content1',content_revision=1,manifest_hash='manifest1',publication_purpose='initial',schedule_slot='slot1',text='원고',body_sha256=hashlib.sha256('원고'.encode()).hexdigest(),media_sha256=[]);value.update(kw);return value
class Client:
    def __init__(self):self.calls=[];self.user='10001';self.status='FINISHED';self.fail=None;self.after_create=None
    def me(self):self.calls.append(('me',));return {'id':self.user}
    def create_text(self,user,text):
        self.calls.append(('create',user,text))
        if self.after_create:self.after_create()
        if self.fail=='create':raise RuntimeError('TOKEN_PRIVATE')
        return {'id':'30003'}
    def container_status(self,cid):
        self.calls.append(('status',cid))
        if self.fail=='status':raise RuntimeError('TOKEN_PRIVATE')
        return {'id':cid,'status':self.status}
    def publish(self,user,cid):
        self.calls.append(('publish',user,cid))
        if self.fail=='publish':raise RuntimeError('TOKEN_PRIVATE')
        return {'id':'40004'}
    def read_post(self,pid):
        self.calls.append(('read',pid));return dict(id=pid,owner={'id':self.user},media_type='TEXT_POST',text='원고',timestamp=NOW.isoformat(),permalink='https://www.threads.net/@public/post/test')
class ThreadsServiceTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)/'managed'
        self.journal=ThreadsJournal(self.root);self.client=Client();self.service=ThreadsServices(self.client,self.journal,lambda:NOW)
    def ready(self):self.journal.initialize()
    def mutations(self):return [c[0] for c in self.client.calls if c[0] in ('create','publish')]
    def test_inert_explicit_journal_and_owner_inspection(self):
        self.assertFalse(self.root.exists());self.assertEqual(self.client.calls,[])
        result=self.service.inspect(TARGET);self.assertTrue(result['authenticated']);self.assertEqual(result['target_id'],'10001')
        self.assertFalse(self.root.exists());self.client.user='20002';self.assertFalse(self.service.inspect(TARGET)['authenticated'])
        self.assertEqual(self.mutations(),[])
    def test_success_receipt_cached_after_owner_check_and_no_extra_posts(self):
        self.ready();result=self.service.submit(prepared(),TARGET)
        self.assertEqual(result['outcome'],'submitted');self.assertEqual(result['remote_id'],'40004')
        self.assertEqual(self.mutations(),['create','publish'])
        self.assertEqual(self.service.submit(prepared(),TARGET),result);self.assertEqual(self.mutations(),['create','publish'])
        self.client.user='20002';self.assertEqual(self.service.submit(prepared(),TARGET)['outcome'],'failed');self.assertEqual(self.mutations(),['create','publish'])
    def test_pending_or_status_read_failure_keeps_container_and_only_status_resumes(self):
        self.ready();self.client.status='IN_PROGRESS';first=self.service.submit(prepared(),TARGET)
        self.assertEqual(first['outcome'],'failed');self.assertTrue(first['evidence']['confirmed_not_submitted'])
        self.assertEqual(self.mutations(),['create']);self.client.fail='status'
        second=self.service.submit(prepared(),TARGET);self.assertEqual(second['outcome'],'failed');self.assertEqual(self.mutations(),['create'])
        self.client.fail=None;self.client.status='FINISHED';self.assertEqual(self.service.submit(prepared(),TARGET)['outcome'],'submitted')
        self.assertEqual(self.mutations(),['create','publish'])
    def test_unknown_create_or_publish_is_never_retried_and_has_no_secret(self):
        self.ready()
        for stage in ('create','publish'):
            self.client.fail=stage;item=prepared(schedule_slot=stage)
            first=self.service.submit(item,TARGET);self.assertEqual(first['outcome'],'unknown');self.assertNotIn('TOKEN_PRIVATE',str(first))
            before=list(self.mutations());self.client.fail=None
            self.assertEqual(self.service.submit(item,TARGET)['outcome'],'unknown');self.assertEqual(self.mutations(),before)
    def test_terminal_container_failure_or_already_published_never_recreates(self):
        self.ready()
        for status in ('ERROR','EXPIRED','PUBLISHED'):
            self.client.status=status;item=prepared(schedule_slot=status)
            result=self.service.submit(item,TARGET);self.assertEqual(result['outcome'],'unknown' if status=='PUBLISHED' else 'failed')
            before=list(self.mutations());self.client.status='FINISHED';self.service.submit(item,TARGET);self.assertEqual(self.mutations(),before)
    def test_same_logical_key_changed_payload_is_rejected_before_native(self):
        self.ready();self.service.submit(prepared(),TARGET);before=list(self.mutations())
        result=self.service.submit(prepared(manifest_hash='different'),TARGET)
        self.assertEqual(result['outcome'],'failed');self.assertTrue(result['evidence']['confirmed_not_submitted']);self.assertEqual(self.mutations(),before)
    def test_journal_is_durable_before_each_post_and_thread_replay_does_not_duplicate(self):
        self.ready();entered=threading.Event();release=threading.Event();results=[]
        def hold():
            db=sqlite3.connect(self.root/'threads-submissions.sqlite3')
            try:self.assertEqual(db.execute('SELECT state FROM threads_submissions').fetchone()[0],'create_started')
            finally:db.close()
            entered.set();release.wait(3)
        self.client.after_create=hold
        publish=self.client.publish
        def checked_publish(*args):
            db=sqlite3.connect(self.root/'threads-submissions.sqlite3')
            try:self.assertEqual(db.execute('SELECT state FROM threads_submissions').fetchone()[0],'publish_started')
            finally:db.close()
            return publish(*args)
        self.client.publish=checked_publish
        thread=threading.Thread(target=lambda:results.append(self.service.submit(prepared(),TARGET)));thread.start();self.assertTrue(entered.wait(3))
        try:
            replay=self.service.submit(prepared(),TARGET);self.assertEqual(replay['outcome'],'unknown');self.assertEqual(self.mutations(),['create'])
        finally:release.set();thread.join(3)
        self.assertFalse(thread.is_alive());self.assertEqual(results[0]['outcome'],'submitted');self.assertEqual(self.mutations(),['create','publish'])
        db=sqlite3.connect(self.root/'threads-submissions.sqlite3')
        try:self.assertEqual(db.execute('SELECT state FROM threads_submissions').fetchone()[0],'submitted')
        finally:db.close()
    def test_remote_read_only_normalizes_actual_text_and_validated_public_permalink(self):
        result=self.service.read_post(TARGET,'40004')
        self.assertEqual(result['visibility'],'unknown');self.assertEqual(result['body_sha256'],hashlib.sha256('원고'.encode()).hexdigest());self.assertEqual(result['media_sha256'],[])
        self.assertEqual(self.service.lookup(TARGET,{'result':{'remote_id':'40004'}}),[result]);self.assertEqual(self.service.lookup(TARGET,{}),[])
        self.assertEqual(self.mutations(),[])
    def test_read_different_owner_media_or_permalink_never_claims_public(self):
        original=self.client.read_post
        for patch in ({'owner':{'id':'20002'}},{'media_type':'IMAGE'},{'permalink':'https://evil.example/post'},{'permalink':'https://www.threads.net/privacy'},{'permalink':'https://threads.net/post?access_token=PRIVATE'},{'timestamp':'invalid'},{'text':'x'*501}):
            self.client.read_post=lambda pid,p=patch:{**original(pid),**p}
            self.assertIsNone(self.service.read_post(TARGET,'40004'))
        self.assertEqual(self.mutations(),[])
    def test_invalid_payload_or_target_mismatch_does_not_mutate(self):
        self.ready()
        for change in ({'media_sha256':['sha']},{'text':'x'*501},{'body_sha256':'wrong'},{'target_id':'20002'},{'extra':'unknown'}):
            result=self.service.submit(prepared(**change),TARGET);self.assertEqual(result['outcome'],'failed');self.assertTrue(result['evidence']['confirmed_not_submitted'])
        self.assertEqual(self.mutations(),[])
    def test_foreign_database_and_symlink_rejected_without_adoption(self):
        self.root.mkdir();db=sqlite3.connect(self.root/'threads-submissions.sqlite3');db.execute('CREATE TABLE keep(value)');db.commit();db.close()
        with self.assertRaises(StoreError):self.journal.initialize()
        (self.root/'threads-submissions.sqlite3').unlink();target=self.root.parent/'foreign';(self.root/'threads-submissions.sqlite3').symlink_to(target)
        with self.assertRaises(StoreError):self.journal.initialize()
        self.assertFalse(target.exists())

    def test_interrupted_native_call_preserves_started_journal_and_cannot_replay(self):
        self.ready()
        for stage in ('create_text','publish'):
            original=getattr(self.client,stage)
            def interrupted(*args):raise KeyboardInterrupt()
            setattr(self.client,stage,interrupted)
            item=prepared(schedule_slot=stage)
            with self.assertRaises(KeyboardInterrupt):self.service.submit(item,TARGET)
            setattr(self.client,stage,original);before=list(self.mutations())
            result=self.service.submit(item,TARGET);self.assertEqual(result['outcome'],'unknown')
            self.assertEqual(self.mutations(),before)

    def test_stop_before_create_records_terminal_known_not_posted(self):
        self.ready()
        def stop():raise RuntimeError('PRIVATE_STOP_CONTEXT')
        self.service.before_write=stop
        result=self.service.submit(prepared(),TARGET)
        self.assertEqual(result['outcome'],'failed');self.assertTrue(result['evidence']['confirmed_not_submitted'])
        self.assertEqual(self.mutations(),[]);self.assertNotIn('PRIVATE_STOP_CONTEXT',str(result))
        self.service.before_write=lambda:None;self.assertEqual(self.service.submit(prepared(),TARGET)['outcome'],'failed')
        self.assertEqual(self.mutations(),[])

    def test_stop_between_create_and_publish_preserves_container_for_next_approval(self):
        self.ready();writes=[]
        def stop():
            writes.append('check')
            if len(writes)==2:raise RuntimeError('STOP')
        self.service.before_write=stop
        result=self.service.submit(prepared(),TARGET)
        self.assertEqual(result['outcome'],'failed');self.assertTrue(result['evidence']['confirmed_not_submitted'])
        self.assertEqual(self.mutations(),['create'])
        self.service.before_write=lambda:None
        self.assertEqual(self.service.submit(prepared(),TARGET)['outcome'],'submitted');self.assertEqual(self.mutations(),['create','publish'])

    def test_explicit_public_probe_requires_fresh_exact_bound_proof(self):
        def proof(obs):return dict(public=True,remote_id=obs['remote_id'],target_id=obs['target_id'],body_sha256=obs['body_sha256'],url=obs['url'],checked_at=NOW.isoformat())
        service=ThreadsServices(self.client,self.journal,lambda:NOW,public_probe=proof)
        result=service.read_post(TARGET,'40004');self.assertEqual(result['visibility'],'public')
        self.assertEqual(self.mutations(),[]);self.assertFalse(self.root.exists())
        with self.assertRaises(StoreError):ThreadsServices(self.client,self.journal,lambda:NOW,public_probe=True)

    def test_private_mismatched_stale_incomplete_or_failed_probe_is_unknown(self):
        from datetime import timedelta
        def proof(obs):return dict(public=True,remote_id=obs['remote_id'],target_id=obs['target_id'],body_sha256=obs['body_sha256'],url=obs['url'],checked_at=NOW.isoformat())
        probes=[lambda obs:True,lambda obs:{**proof(obs),'public':False},lambda obs:{**proof(obs),'public':1},
            lambda obs:{**proof(obs),'remote_id':'999'},lambda obs:{**proof(obs),'target_id':'999'},
            lambda obs:{**proof(obs),'body_sha256':'0'*64},lambda obs:{**proof(obs),'url':'https://www.threads.net/@other/post/different'},lambda obs:{**proof(obs),'checked_at':(NOW-timedelta(seconds=1)).isoformat()},
            lambda obs:{**proof(obs),'checked_at':(NOW+timedelta(seconds=1)).isoformat()},lambda obs:{**proof(obs),'extra':'PRIVATE'}]
        def failed(obs):raise RuntimeError('PRIVATE_TOKEN')
        probes.append(failed)
        for probe in probes:
            service=ThreadsServices(self.client,self.journal,lambda:NOW,public_probe=probe)
            result=service.read_post(TARGET,'40004');self.assertEqual(result['visibility'],'unknown');self.assertNotIn('PRIVATE_TOKEN',str(result))
        self.assertEqual(self.mutations(),[])

    def test_probe_cannot_mutate_api_observation_into_public(self):
        def forged(obs):
            obs['remote_id']='999';obs['text']='changed';obs['media_sha256'].append('fake')
            return dict(public=True,remote_id='999',target_id=obs['target_id'],body_sha256=obs['body_sha256'],url=obs['url'],checked_at=NOW.isoformat())
        service=ThreadsServices(self.client,self.journal,lambda:NOW,public_probe=forged)
        result=service.read_post(TARGET,'40004');self.assertEqual(result['remote_id'],'40004');self.assertEqual(result['text'],'원고')
        self.assertEqual(result['media_sha256'],[]);self.assertEqual(result['visibility'],'unknown')

    def test_owner_api_public_flag_is_not_anonymous_public_proof(self):
        read=self.client.read_post
        self.client.read_post=lambda remote:{**read(remote),'public':True,'is_public':True,'visibility':'public'}
        result=self.service.read_post(TARGET,'40004')
        self.assertEqual(result['visibility'],'unknown');self.assertEqual(self.mutations(),[])
