"""변환된 원격 영상의 공개 확인은 실제 업로드 영수증과 원격 메타데이터를 결속한다."""
import copy
from datetime import timedelta
import hashlib
import unittest
from tests.publishers import test_youtube as fixture
from common.publishers.youtube_payloads import build_youtube_payload
from common.operations.youtube_evidence import youtube_upload_identity

class YoutubeEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.context=fixture.context(run_id='run');self.snapshot={**fixture.snapshot(),'owner_account_id':'personal'}
        self.prepared=build_youtube_payload(self.snapshot,self.context,self.context.options.get('youtube_config',{}))
        self.now=fixture.NOW+timedelta(minutes=2)
        self.candidate=dict(remote_id='remote',target_id=self.context.target_id,destination_account_id='dept',created_at=(fixture.NOW+timedelta(minutes=1)).isoformat(),visibility='public',upload_status='processed',processing_status='succeeded',title=self.prepared['body']['snippet']['title'],description=self.prepared['body']['snippet']['description'],media_sha256=None)
        self.receipt=dict(kind='youtube_upload_receipt_v1',connection_id=self.context.connection_id,target_id=self.context.target_id,remote_id='remote',owner_account_id='personal',destination_account_id='dept',content_id=self.context.content_id,content_revision=1,manifest_hash=self.context.manifest_hash,asset_id='asset-video',asset_sha256='a'*64,asset_size=5,title_sha256=hashlib.sha256(self.candidate['title'].encode()).hexdigest(),description_sha256=hashlib.sha256(self.candidate['description'].encode()).hexdigest())
        self.attempt=dict(id='attempt',context_hash=self.context.context_hash,created_at=fixture.NOW.isoformat(),request_started=1,outcome='submitted',result=dict(outcome='submitted',remote_id='remote',evidence=dict(upload_receipt=self.receipt)))
    def valid(self,**changes):
        values=dict(context=self.context,snapshot=self.snapshot,candidate=self.candidate,attempt=self.attempt,now=self.now,remote_id='remote');values.update(changes)
        return youtube_upload_identity(**values)
    def test_server_receipt_and_fresh_remote_publication_match_without_remote_media_hash(self):
        self.assertTrue(self.valid());self.assertTrue(self.valid(context=self.context.to_dict()))
        self.assertIsNone(self.candidate['media_sha256']);self.assertNotIn('body_sha256',self.candidate)
        self.attempt.update(outcome='scheduled');self.attempt['result']['outcome']='scheduled';self.assertTrue(self.valid())
    def test_remote_id_channel_visibility_processing_and_edits_cannot_match(self):
        for patch in ({'remote_id':'other'},{'target_id':'other'},{'destination_account_id':'personal'},{'visibility':'private'},{'upload_status':'uploaded'},{'processing_status':'processing'},{'title':'edited'},{'description':'edited'},{'title':None}):
            with self.subTest(patch=patch):self.assertFalse(self.valid(candidate={**self.candidate,**patch}))
        self.assertFalse(self.valid(remote_id='other'))
    def test_missing_forged_replayed_and_extra_receipt_fields_are_rejected(self):
        self.attempt['result']['evidence']={};self.assertFalse(self.valid())
        for field in self.receipt:
            receipt={**self.receipt,field:'other'}
            self.attempt['result']['evidence']={'upload_receipt':receipt};self.assertFalse(self.valid(),field)
        for patch in ({'content_revision':True},{'asset_size':True},{'extra':'yes'}):
            self.attempt['result']['evidence']={'upload_receipt':{**self.receipt,**patch}};self.assertFalse(self.valid())
    def test_unknown_unstarted_or_other_context_attempt_is_not_upload_proof(self):
        for patch in ({'outcome':'unknown'},{'request_started':False},{'request_started':'1'},{'context_hash':'different'},{'result':None},{'result':{**self.attempt['result'],'outcome':'failed'}},{'result':{**self.attempt['result'],'remote_id':'other'}}):
            self.assertFalse(self.valid(attempt={**self.attempt,**patch}))
    def test_snapshot_asset_version_owner_and_approval_payload_changes_fail(self):
        for patch in ({'revision':2},{'manifest_hash':'changed'},{'owner_account_id':'dept'},{'id':'other'},{'title':'changed'},{'assets':[{**self.snapshot['assets'][0],'sha256':'b'*64}]},{'assets':[{**self.snapshot['assets'][0],'size':6}]}):
            self.assertFalse(self.valid(snapshot={**self.snapshot,**patch}),repr(patch))
        # 선택된 채널 변환본의 내용이 바뀌어도 실제 description 결속이 깨진다.
        changed=copy.deepcopy(self.snapshot);changed['variants'][0]['text']='새 배포원고'
        self.assertFalse(self.valid(snapshot=changed))
    def test_publication_time_must_be_within_attempt_and_observation_window(self):
        for created in ((fixture.NOW-timedelta(seconds=1)).isoformat(),(self.now+timedelta(seconds=1)).isoformat(),'invalid',None):
            self.assertFalse(self.valid(candidate={**self.candidate,'created_at':created}))
