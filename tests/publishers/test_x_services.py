"""실제 API 없이 유료 호출 경계·단일 POST 원장·원문 및 공개 증명을 확인한다."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from common.operations.content_store import StoreError
from common.publishers.x_payloads import build_x_payload
from common.publishers.x_services import XJournal, XServices, DB_NAME, _validate
from tests.publishers.test_x_payloads import ctx, snapshot

NOW=datetime(2026,11,4,12,tzinfo=timezone.utc)
REMOTE='456'


def digest(text):return hashlib.sha256(text.encode()).hexdigest()


class Client:
    def __init__(self):
        self.calls=[];self.user={'id':'123','username':'account','protected':False}
        self.posted={'id':REMOTE,'text':'반환 원문'};self.row=None
        self.on_create=lambda:None;self.on_read=lambda:None
    def inspect_account(self):self.calls.append(('inspect',));return deepcopy(self.user)
    def create_post(self,text):
        self.calls.append(('create',text));self.on_create();return deepcopy(self.posted)
    def read_post(self,remote):
        self.calls.append(('read',remote));self.on_read();return deepcopy(self.row)


class XServicesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name)/'journal';self.journal=XJournal(self.folder)
        self.client=Client();self.current=ctx(target_id='123')
        self.prepared=build_x_payload(snapshot(self.current,'승인 원문'),self.current)
        self.target={'platform':'x','target_id':'123','connection_id':'dept.x','expected_login_subject':'123'}
        self.allowed=True;self.probes=[];self.time=NOW
        self.service=XServices(self.client,self.journal,lambda:self.time,cost_authorizer=lambda target:self.allowed)
        self.client.row=self.remote_row()
    def initialize(self):self.journal.initialize()
    def remote_row(self,**over):
        return dict(id=REMOTE,text=self.prepared['text'],author_id='123',created_at=NOW.isoformat(),entities={'urls':[]},**over)
    def submit(self):return self.service.submit(self.prepared,self.target)
    def counts(self,name):return sum(c[0]==name for c in self.client.calls)
    def stored(self):return self.journal.get(_validate(self.prepared,self.target)[1])
    def probe(self,observation):
        self.probes.append(deepcopy(observation))
        return {**{k:observation[k] for k in ('remote_id','target_id','body_sha256','url')},'public':True,'checked_at':self.time}
    def test_construction_and_default_cost_denial_are_inert(self):
        service=XServices(self.client,self.journal,lambda:NOW,public_probe=self.probe)
        self.assertFalse(self.folder.exists());self.assertFalse(service.inspect(self.target)['authenticated'])
        result=service.submit(self.prepared,self.target)
        self.assertEqual(result['evidence'],{'reason':'x_cost_confirmation_required','confirmed_not_submitted':True})
        self.assertIsNone(service.read_post(self.target,REMOTE));self.assertEqual(service.lookup(self.target,{'remote_id':REMOTE}),[])
        self.assertEqual(self.client.calls,[]);self.assertEqual(self.probes,[]);self.assertFalse(self.folder.exists())
    def test_uninitialized_journal_does_not_post_and_initialize_is_explicit(self):
        result=self.submit();self.assertNotEqual(result['outcome'],'submitted');self.assertEqual(self.counts('create'),0)
        self.assertFalse((self.folder/DB_NAME).exists())
        self.initialize();self.assertEqual((self.folder/DB_NAME).stat().st_mode&0o777,0o600)
        self.assertEqual(self.submit()['outcome'],'submitted')
    def test_single_post_durable_replay_is_offline_even_without_cost(self):
        self.initialize();first=self.submit();self.assertEqual(first['remote_id'],REMOTE)
        self.assertEqual(self.counts('create'),1);self.assertEqual(self.stored()['state'],'submitted')
        self.assertEqual(self.client.calls[-1],('create',self.prepared['text']))
        calls=list(self.client.calls)
        replay=XServices(self.client,XJournal(self.folder),lambda:NOW)
        self.assertEqual(replay.submit(self.prepared,self.target),first)
        self.assertEqual(self.client.calls,calls)
    def test_started_and_unknown_survive_restart_without_second_post(self):
        self.initialize()
        normalized,key,sha=_validate(self.prepared,self.target)
        self.journal.claim(key,sha,normalized,NOW.isoformat())
        self.assertEqual(self.submit()['outcome'],'unknown');self.assertEqual(self.client.calls,[])
        self.assertEqual(XServices(self.client,XJournal(self.folder),lambda:NOW,cost_authorizer=lambda _:True).submit(self.prepared,self.target)['outcome'],'unknown')
        self.assertEqual(self.counts('create'),0)
    def test_network_uncertainty_and_malformed_return_never_repeat(self):
        for malformed in (False,True):
            with self.subTest(malformed=malformed),tempfile.TemporaryDirectory() as folder:
                journal=XJournal(folder);journal.initialize();client=Client()
                if malformed:client.posted={'id':'invalid'}
                else:
                    def fail():raise OSError('private-provider-detail')
                    client.on_create=fail
                service=XServices(client,journal,lambda:NOW,cost_authorizer=lambda _:True)
                first=service.submit(self.prepared,self.target);second=service.submit(self.prepared,self.target)
                self.assertEqual((first['outcome'],second['outcome']),('unknown','unknown'))
                self.assertEqual(sum(c[0]=='create' for c in client.calls),1)
                self.assertNotIn('private-provider-detail',str(first))
                self.assertEqual(journal.get(_validate(self.prepared,self.target)[1])['state'],'unknown')
    def test_returned_id_survives_submission_commit_failure(self):
        self.initialize();original=self.journal.transition
        def transition(row,state,*args,**kwargs):
            if state=='submitted':raise StoreError('private-db-detail')
            return original(row,state,*args,**kwargs)
        with patch.object(self.journal,'transition',side_effect=transition):result=self.submit()
        self.assertEqual((result['outcome'],result['remote_id']),('unknown',REMOTE))
        self.assertEqual((self.stored()['state'],self.stored()['remote_id']),('unknown',REMOTE))
        self.assertEqual(self.submit()['outcome'],'unknown');self.assertEqual(self.counts('create'),1)
    def test_stop_before_write_is_known_not_posted_and_explicit_resume(self):
        self.initialize()
        def stop():raise RuntimeError('STOP')
        self.service.before_write=stop;result=self.submit()
        self.assertTrue(result['evidence']['confirmed_not_submitted']);self.assertEqual(self.stored()['state'],'known_not_posted');self.assertEqual(self.counts('create'),0)
        self.service.before_write=lambda:None
        self.assertEqual(self.submit()['outcome'],'submitted');self.assertEqual(self.counts('create'),1)
    def test_cost_revoked_at_write_and_owner_verification_blocks_post(self):
        self.initialize();self.service.before_write=lambda:setattr(self,'allowed',False)
        result=self.submit();self.assertEqual(result['evidence']['reason'],'x_cost_confirmation_required');self.assertEqual(self.counts('create'),0);self.assertEqual(self.stored()['state'],'known_not_posted')
        self.allowed=True;self.service.before_write=lambda:None;self.client.user['protected']=True
        self.assertEqual(self.submit()['evidence']['reason'],'target_unverified');self.assertEqual(self.counts('create'),0)
        self.client.user.update(protected=False,id='999');self.assertFalse(self.service.inspect(self.target)['authenticated'])
        self.client.user['id']='123';self.assertFalse(self.service.inspect({**self.target,'expected_login_subject':'999'})['authenticated'])
    def test_conflict_same_logical_submission_cannot_post_different_text(self):
        self.initialize();self.submit();changed={**self.prepared,'text':'달라진 원문','body_sha256':digest('달라진 원문')}
        result=self.service.submit(changed,self.target)
        self.assertEqual(result['evidence']['reason'],'x_payload_conflict');self.assertTrue(result['evidence']['confirmed_not_submitted']);self.assertEqual(self.counts('create'),1)
    def test_known_id_only_owner_and_withheld_checks_before_public_probe(self):
        self.initialize();self.service.public_probe=self.probe
        self.assertIsNone(self.service.read_post(self.target,REMOTE));self.assertEqual(self.client.calls,[])
        self.submit()
        for over in ({'author_id':'999'},{'id':'999'},{'withheld':{'country_codes':['US']}},{'text':'변경된 원문'}):
            self.client.row={**self.remote_row(),**over}
            self.assertIsNone(self.service.read_post(self.target,REMOTE));self.assertEqual(self.probes,[])
        self.client.row=self.remote_row();self.client.user['protected']=True
        before=self.counts('read');self.assertIsNone(self.service.read_post(self.target,REMOTE));self.assertEqual(self.counts('read'),before)
    def test_direct_identity_hash_is_separate_and_no_probe_is_unknown(self):
        self.initialize();self.submit();observation=self.service.read_post(self.target,REMOTE)
        self.assertEqual(observation['text'],self.prepared['text']);self.assertEqual(observation['body_sha256'],self.prepared['body_sha256'])
        self.assertEqual(observation['remote_text_sha256'],digest(self.client.row['text']));self.assertEqual(observation['visibility'],'unknown')
        self.assertEqual(observation['media_sha256'],[])
    def test_tco_after_emoji_reconstructs_exact_approved_body(self):
        source='😀 승인 https://example.com/long/path 끝'
        self.prepared=build_x_payload(snapshot(self.current,source),self.current)
        remote='😀 승인 https://t.co/abc 끝';short='https://t.co/abc'
        start=remote.index(short)
        # X v2 offsets are Unicode codepoint indices, not UTF-16 units.
        entity={'start':start,'end':start+len(short),'url':short,'expanded_url':'https://example.com/long/path'}
        self.client.row={**self.remote_row(),'text':remote,'entities':{'urls':[entity]}}
        self.initialize();self.submit();observed=self.service.read_post(self.target,REMOTE)
        self.assertIsNotNone(observed);self.assertEqual(observed['text'],source)
        self.assertEqual(observed['body_sha256'],digest(source));self.assertEqual(observed['remote_text_sha256'],digest(remote));self.assertNotEqual(observed['body_sha256'],observed['remote_text_sha256'])
        for urls in ([],[{**entity,'start':start+1}],[{**entity,'expanded_url':'https://evil.org/'}],[{**entity,'url':'https://t.co/wrong'}]):
            self.client.row['entities']={'urls':urls};self.assertIsNone(self.service.read_post(self.target,REMOTE))
    def test_public_proof_requires_exact_identity_keys_and_request_freshness(self):
        self.initialize();self.submit();self.service.public_probe=self.probe
        self.assertEqual(self.service.read_post(self.target,REMOTE)['visibility'],'public');self.assertEqual(len(self.probes),1)
        changes=[{'public':False},{'remote_id':'999'},{'target_id':'999'},{'body_sha256':'a'*64},{'url':'https://x.com/i/web/status/999'},{'checked_at':NOW-timedelta(seconds=1)},{'checked_at':NOW+timedelta(seconds=1)},{'extra':'private'}]
        for change in changes:
            def probe(observation):return {**self.probe(observation),**change}
            self.service.public_probe=probe
            self.assertEqual(self.service.read_post(self.target,REMOTE)['visibility'],'unknown')
        def stale(observation):
            proof=self.probe(observation);self.time=NOW+timedelta(seconds=61);return proof
        self.time=NOW;self.service.public_probe=stale
        self.assertEqual(self.service.read_post(self.target,REMOTE)['visibility'],'unknown')
    def test_cost_denial_blocks_remote_and_probe_after_submission(self):
        self.initialize();self.submit();self.service.public_probe=self.probe
        calls=list(self.client.calls);self.allowed=False
        self.assertIsNone(self.service.read_post(self.target,REMOTE));self.assertEqual(self.client.calls,calls);self.assertEqual(self.probes,[])
        self.allowed=True;self.client.on_read=lambda:setattr(self,'allowed',False)
        observed=self.service.read_post(self.target,REMOTE)
        self.assertEqual(observed['visibility'],'unknown');self.assertEqual(self.probes,[])


if __name__=='__main__':unittest.main()
