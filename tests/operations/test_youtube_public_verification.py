"""서버에 저장된 업로드 영수증과 새 공개 관측을 영속 원장에서 결속한다."""
import copy,hashlib
from unittest.mock import Mock
import unittest
from tests.operations import test_runtime_store as base
from tests.publishers.test_youtube import context,snapshot,NOW
from common.operations.runtime_models import VerificationResult
from common.operations.verification import verify_delivery
from common.publishers.youtube_payloads import build_youtube_payload


class YoutubePublicVerificationTests(unittest.TestCase):
    setUp=base.RuntimeStoreTests.setUp
    fixture=base.RuntimeStoreTests.fixture
    store=base.RuntimeStoreTests.store
    def prepare(self,receipt=True):
        self.fixture();store=self.store();store.initialize();store.create_run('r')
        ctx=context('personal.youtube');store.create_delivery('d','r',ctx)
        store.record_publication_approval('d',1,ctx.context_hash,'approval',ctx.review_report_hashes)
        lease=store.claim_run('r','worker',{'host_id':'host','pid':123,'started_at':NOW.isoformat()},NOW)
        attempt=store.create_attempt('d',store.get_delivery('d')['version'],lease,ctx.context_hash,'approval',now=NOW)
        permit=store.issue_permit(attempt['id'],lease,ctx.context_hash,'approval',NOW);store.consume_permit(permit,lease,NOW)
        snap=dict(snapshot(),owner_account_id='personal');prepared=build_youtube_payload(snap,ctx,{})
        digest=lambda text:hashlib.sha256(text.encode()).hexdigest()
        binding={key:prepared[key] for key in ('connection_id','target_id','owner_account_id','destination_account_id','content_id','content_revision','manifest_hash')}
        self.receipt=dict(binding,kind='youtube_upload_receipt_v1',remote_id='remote',asset_id=prepared['asset']['id'],asset_sha256=prepared['asset']['sha256'],asset_size=prepared['asset']['size'],title_sha256=digest(prepared['body']['snippet']['title']),description_sha256=digest(prepared['body']['snippet']['description']))
        store.finish_attempt(attempt['id'],'submitted',remote_id='remote',evidence={'upload_receipt':self.receipt} if receipt else {},now=NOW)
        candidate=dict(remote_id='remote',target_id=ctx.target_id,destination_account_id=ctx.destination_account_id,created_at=NOW.isoformat(),visibility='public',upload_status='processed',processing_status='succeeded',title=prepared['body']['snippet']['title'],description=prepared['body']['snippet']['description'],media_sha256=None)
        return store,snap,candidate
    def verify(self,store,snap,candidate):
        adapter=Mock();adapter.verify.return_value=VerificationResult('verified',NOW,candidate)
        return verify_delivery(store,'d',adapter,snap,now=NOW)
    def test_persisted_receipt_and_fresh_public_observation_verify_transcoded_video(self):
        store,snap,candidate=self.prepare()
        result=self.verify(store,snap,candidate)
        self.assertEqual(result.outcome,'verified');self.assertEqual(store.get_delivery('d')['state'],'verified')
        self.assertIsNone(result.evidence.get('media_sha256'))
        self.assertEqual(result.evidence.get('verification_method'),'youtube_upload_receipt_and_public_observation')
        self.assertNotIn('upload_receipt',result.evidence)
    def test_candidate_cannot_supply_missing_server_receipt(self):
        store,snap,candidate=self.prepare(receipt=False);candidate['upload_receipt']=self.receipt
        self.assertEqual(self.verify(store,snap,candidate).outcome,'pending')
        self.assertNotEqual(store.get_delivery('d')['state'],'verified')
    def test_edited_description_does_not_verify(self):
        store,snap,candidate=self.prepare();candidate['description']+='changed'
        self.assertEqual(self.verify(store,snap,candidate).outcome,'pending')

    def test_actual_service_receipt_is_persisted_and_public_view_verified(self):
        from common.publishers.youtube_services import GoogleYoutubeServices,VerifiedYoutubeMedia,observation
        from tests.publishers.test_youtube import FakeGoogle,Client
        from common.publishers.youtube import YoutubeAdapter
        from tests.publishers.test_youtube import registry
        self.fixture();store=self.store();store.initialize();store.create_run('r')
        ctx=context('personal.youtube');snap=dict(snapshot(),owner_account_id='personal')
        prepared=build_youtube_payload(snap,ctx,{})
        google=FakeGoogle('personal')
        google.videos[0]['snippet'].update(title=prepared['body']['snippet']['title'],description=prepared['body']['snippet']['description'])
        service=GoogleYoutubeServices(Client(google),media_factory=lambda asset,payload:VerifiedYoutubeMedia(object(),asset['sha256'],asset['size']),clock=lambda:NOW)
        target=dict(platform='youtube',target_id=ctx.target_id,expected_login_subject=ctx.target_id)
        store.create_delivery('d','r',ctx);store.record_publication_approval('d',1,ctx.context_hash,'approval',ctx.review_report_hashes)
        lease=store.claim_run('r','worker',{'host_id':'host','pid':123,'started_at':NOW.isoformat()},NOW)
        attempt=store.create_attempt('d',store.get_delivery('d')['version'],lease,ctx.context_hash,'approval',now=NOW)
        permit=store.issue_permit(attempt['id'],lease,ctx.context_hash,'approval',NOW);store.consume_permit(permit,lease,NOW)
        result=service.submit(prepared,target)
        store.finish_attempt(attempt['id'],result['outcome'],remote_id=result['remote_id'],evidence=result['evidence'],now=NOW)
        class Bridge:
            def read(self,executor,action,context,payload):
                raw=service.read_video(target,payload['remote_id'])
                return dict(checked_at=NOW.isoformat(),observation=observation(raw,context.to_dict()))
        verified=verify_delivery(store,'d',YoutubeAdapter(registry(),Bridge()),snap,now=NOW)
        self.assertEqual(verified.outcome,'verified')
        self.assertEqual(store.get_run('r')['state'],'completed')
        self.assertEqual(sum(name=='videos.insert' for name,_ in google.calls),1)
        self.assertIsNone(verified.evidence.get('media_sha256'))

    def test_real_observation_can_finish_after_request_start_but_not_after_completion(self):
        from datetime import timedelta
        store,snap,candidate=self.prepare()
        adapter=Mock();adapter.verify.return_value=VerificationResult('verified',NOW+timedelta(seconds=1),candidate)
        result=verify_delivery(store,'d',adapter,snap,now=NOW,clock=lambda:NOW+timedelta(seconds=2))
        self.assertEqual(result.outcome,'verified')

    def test_future_checked_at_is_still_rejected_after_observation_finishes(self):
        from datetime import timedelta
        store,snap,candidate=self.prepare()
        adapter=Mock();adapter.verify.return_value=VerificationResult('verified',NOW+timedelta(seconds=3),candidate)
        result=verify_delivery(store,'d',adapter,snap,now=NOW,clock=lambda:NOW+timedelta(seconds=2))
        self.assertEqual(result.outcome,'pending')
