"""SDK 응답 ID와 서버가 검증한 입력에만 업로드 영수증을 결속한다. 가짜 Google 전송만 사용."""
import copy
from dataclasses import FrozenInstanceError
import hashlib
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from common.publishers.youtube_services import GoogleYoutubeServices,VerifiedYoutubeMedia,create_youtube_services
from tests.publishers import test_youtube as base

FIELDS={'kind','connection_id','target_id','remote_id','owner_account_id','destination_account_id','content_id','content_revision','manifest_hash','asset_id','asset_sha256','asset_size','title_sha256','description_sha256'}


def prepared(account='dept'):
    return dict(connection_id=account+'.youtube',target_id='UC-'+account,owner_account_id='personal',destination_account_id=account,
        content_id='content',content_revision=1,manifest_hash='manifest',asset=dict(id='asset-video',sha256='a'*64,size=5,media_type='video/mp4'),
        body=dict(snippet=dict(title='안전한 제목',description='정확한 본문\n출처'),status=dict(privacyStatus='public')))


class YoutubeReceiptTests(unittest.TestCase):
    def service(self,account='dept',factory=None):
        fake=base.FakeGoogle(account)
        service=GoogleYoutubeServices(base.Client(fake),media_factory=factory or (lambda asset,payload:VerifiedYoutubeMedia('media-object',asset['sha256'],asset['size'])),clock=lambda:base.NOW)
        return fake,service

    def test_typed_verified_media_produces_exact_receipt_after_sdk_id_for_crosspost(self):
        fake,service=self.service();payload=prepared();result=service.submit(payload,dict(target_id='UC-dept'))
        self.assertEqual(result['outcome'],'submitted');receipt=result['evidence']['upload_receipt']
        self.assertEqual(set(receipt),FIELDS);self.assertEqual(receipt['kind'],'youtube_upload_receipt_v1')
        self.assertEqual(receipt['owner_account_id'],'personal');self.assertEqual(receipt['destination_account_id'],'dept')
        self.assertEqual(receipt['target_id'],'UC-dept');self.assertEqual(receipt['remote_id'],'remote')
        self.assertEqual(receipt['asset_sha256'],payload['asset']['sha256']);self.assertEqual(receipt['asset_size'],5)
        self.assertEqual(receipt['title_sha256'],hashlib.sha256(payload['body']['snippet']['title'].encode('utf-8')).hexdigest())
        self.assertEqual(receipt['description_sha256'],hashlib.sha256(payload['body']['snippet']['description'].encode('utf-8')).hexdigest())
        insert=next(v for n,v in fake.calls if n=='videos.insert');self.assertEqual(insert['media_body'],'media-object')
        self.assertNotIn('media_sha256',result['evidence'])
        with self.assertRaises(FrozenInstanceError):VerifiedYoutubeMedia('upload','a'*64,5).size=6

    def test_typed_digest_or_size_mismatch_never_inserts(self):
        for digest,size in [('b'*64,5),('a'*64,6)]:
            fake,service=self.service(factory=lambda *_:VerifiedYoutubeMedia('upload',digest,size))
            result=service.submit(prepared(),dict(target_id='UC-dept'))
            self.assertEqual(result['outcome'],'failed');self.assertTrue(result['evidence']['confirmed_not_submitted'])
            self.assertFalse(any(n=='videos.insert' for n,_ in fake.calls));self.assertNotIn('upload_receipt',result['evidence'])

    def test_missing_or_inconsistent_prepared_identity_is_rejected_before_media_factory(self):
        for mutate in [lambda p:p.pop('content_id'),lambda p:p.update(connection_id='personal.youtube'),lambda p:p.update(target_id='other'),lambda p:p.update(content_revision=True),lambda p:p['asset'].update(sha256='invalid'),lambda p:p['body']['snippet'].update(title='\ud800')]:
            payload=prepared();mutate(payload);calls=[];fake,service=self.service(factory=lambda *_:calls.append(1))
            result=service.submit(payload,dict(target_id='UC-dept'))
            self.assertEqual(result['outcome'],'failed');self.assertTrue(result['evidence']['confirmed_not_submitted'])
            self.assertEqual(calls,[]);self.assertFalse(any(n=='videos.insert' for n,_ in fake.calls))

    def test_sdk_unknown_missing_id_and_legacy_media_never_receive_receipt(self):
        for mode in ('lost','missing','legacy'):
            fake,service=self.service(factory=(lambda *_:object()) if mode=='legacy' else None)
            if mode=='lost':fake.lost=True
            if mode=='missing':fake.response.pop('id')
            result=service.submit(prepared(),dict(target_id='UC-dept'))
            self.assertNotIn('upload_receipt',result['evidence'])
            self.assertEqual(result['outcome'],'submitted' if mode=='legacy' else 'unknown')
            self.assertEqual(sum(n=='videos.insert' for n,_ in fake.calls),1)

    def test_scheduled_id_receipt_does_not_claim_public_verification(self):
        fake,service=self.service('personal');payload=prepared('personal');at='2026-11-05T01:00:00+00:00'
        payload['body']['status']=dict(privacyStatus='private',publishAt=at)
        fake.response['status']=dict(privacyStatus='private',publishAt=at,uploadStatus='uploaded')
        result=service.submit(payload,dict(target_id='UC-personal'))
        self.assertEqual(result['outcome'],'scheduled');self.assertEqual(result['evidence']['visibility'],'scheduled')
        self.assertEqual(result['evidence']['upload_receipt']['connection_id'],'personal.youtube')
        self.assertNotIn('verified',result['evidence']);self.assertNotIn('media_sha256',result['evidence'])

    def test_installed_factory_returns_verified_media_only_after_raw_byte_checks(self):
        raw=b'video';payload=prepared();payload['asset']['sha256']=hashlib.sha256(raw).hexdigest();fake=base.FakeGoogle('dept');reads=[]
        def loader(*args):reads.append(args);return dict(payload['asset']),raw
        with patch.dict(sys.modules,{'googleapiclient':SimpleNamespace(),'googleapiclient.discovery':SimpleNamespace(build=lambda *a,**k:base.Client(fake)),'googleapiclient.http':SimpleNamespace(MediaIoBaseUpload=lambda stream,**kw:('sdk-media',stream.read()))}):
            service=create_youtube_services('dept.youtube',object(),media_loader=loader)
            media=service.media_factory(payload['asset'],payload)
            self.assertIsInstance(media,VerifiedYoutubeMedia);self.assertEqual(media.sha256,payload['asset']['sha256']);self.assertEqual(media.size,len(raw))
            self.assertEqual(media.upload,('sdk-media',raw))
            payload['asset']['sha256']='0'*64
            with self.assertRaises(ValueError):service.media_factory(payload['asset'],payload)
        self.assertEqual(reads,[('content',1,'asset-video')]*2)
