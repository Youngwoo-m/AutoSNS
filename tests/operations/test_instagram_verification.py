"""Instagram 영수증 기반 공개 검증의 실제 원장 결속. 원격 I/O는 없다."""
import copy
from dataclasses import replace
from unittest.mock import Mock
import unittest
from tests.operations import test_runtime_store as runtime_fixture
from tests.operations import test_instagram_evidence as evidence_fixture
from common.operations.runtime_models import VerificationResult,LookupResult
from common.operations.models import thaw
from common.operations.verification import verify_delivery,snapshot_fingerprints

NOW=evidence_fixture.NOW

class InstagramVerificationTests(unittest.TestCase):
    setUp=runtime_fixture.RuntimeStoreTests.setUp
    fixture=runtime_fixture.RuntimeStoreTests.fixture
    store=runtime_fixture.RuntimeStoreTests.store

    def prepared(self,fmt='image',provisional=False,outcome='submitted'):
        self.fixture();store=self.store();store.initialize();store.create_run('r')
        old,snapshot,candidate,prior=evidence_fixture.fixture(fmt,provisional)
        candidate={**candidate,'created_at':candidate['created_at'].isoformat()}
        ctx=replace(old,content_id='c',run_id='r');snapshot={**snapshot,'id':'c'}
        receipt={**prior['result']['evidence']['upload_receipt'],'content_id':'c','context_hash':ctx.context_hash}
        store.create_delivery('d','r',ctx);store.record_publication_approval('d',1,ctx.context_hash,'approval',ctx.review_report_hashes)
        lease=store.claim_run('r','worker',{'host_id':'host','pid':123,'started_at':NOW.isoformat()},NOW)
        attempt=store.create_attempt('d',store.get_delivery('d')['version'],lease,ctx.context_hash,'approval',now=NOW)
        permit=store.issue_permit(attempt['id'],lease,ctx.context_hash,'approval',NOW);store.consume_permit(permit,lease,NOW)
        store.finish_attempt(attempt['id'],outcome,remote_id='999',evidence={'upload_receipt':receipt},now=NOW)
        store.content_store=Mock();store.content_store.get.return_value=snapshot
        return store,ctx,snapshot,candidate,receipt

    def test_local_fingerprint_selects_only_approved_instagram_assets_in_order(self):
        store,ctx,snapshot,candidate,receipt=self.prepared('carousel')
        snapshot={**snapshot,'assets':snapshot['assets']+[dict(id='not-selected',sha256='f'*64,size=12,media_type='image/jpeg')]}
        body,media=snapshot_fingerprints(ctx.to_dict(),snapshot)
        self.assertEqual(body,receipt['caption_sha256']);self.assertEqual(media,[a['sha256'] for a in receipt['assets']])

    def test_receipt_and_public_observation_complete_without_fabricated_remote_media_hash(self):
        store,ctx,snapshot,candidate,receipt=self.prepared();adapter=Mock()
        adapter.verify.return_value=VerificationResult('verified',NOW,candidate)
        result=verify_delivery(store,'d',adapter,snapshot,now=NOW)
        self.assertEqual(result.outcome,'verified');self.assertEqual(store.get_delivery('d')['url'],candidate['url'])
        self.assertIsNone(result.evidence['media_sha256'])
        self.assertEqual(result.evidence['verification_method'],'instagram_upload_receipt_and_public_observation')

    def test_carousel_provisional_requires_private_final_pin_and_keeps_it_as_evidence(self):
        store,ctx,snapshot,candidate,receipt=self.prepared('carousel',True);adapter=Mock()
        adapter.verify.return_value=VerificationResult('verified',NOW,candidate)
        self.assertEqual(verify_delivery(store,'d',adapter,snapshot,now=NOW).outcome,'pending')
        candidate['upload_receipt']={**receipt,'published_children':copy.deepcopy(candidate['children'])}
        adapter.verify.return_value=VerificationResult('verified',NOW,candidate)
        result=verify_delivery(store,'d',adapter,snapshot,now=NOW)
        self.assertEqual(result.outcome,'verified');self.assertEqual(thaw(result.evidence['upload_receipt']['published_children']),candidate['children'])

    def test_receipt_missing_caption_replaced_wrong_order_or_private_stays_pending(self):
        store,ctx,snapshot,candidate,receipt=self.prepared('carousel');adapter=Mock()
        for patch in ({'text':'changed'},{'visibility':'unknown'},{'children':list(reversed(candidate['children']))},
                      {'media_sha256':['a'*64]},{'url':'https://instagram.com/accounts/login/'}):
            with self.subTest(patch=patch):
                adapter.verify.return_value=VerificationResult('verified',NOW,{**candidate,**patch})
                self.assertEqual(verify_delivery(store,'d',adapter,snapshot,now=NOW).outcome,'pending')
                self.assertNotEqual(store.get_delivery('d')['state'],'verified')

    def test_unknown_known_id_reconciles_by_receipt_and_then_verifies_without_new_submission(self):
        from common.operations.recovery import reconcile_delivery
        store,ctx,snapshot,candidate,receipt=self.prepared('carousel',True,'unknown');adapter=Mock()
        candidate['upload_receipt']={**receipt,'published_children':copy.deepcopy(candidate['children'])}
        adapter.lookup.return_value=LookupResult('matched',[candidate])
        resolved=reconcile_delivery(store,'d',adapter,NOW,expected_version=store.get_delivery('d')['version'],request_key='instagram-receipt-link')
        self.assertEqual(resolved['state'],'uploaded');self.assertEqual(len(store.attempts('d')),1)
        proof=store.attempts('d')[0]['result']['resolution']['evidence']['upload_receipt']
        self.assertEqual(proof['published_children'],candidate['children'])
        adapter.verify.return_value=VerificationResult('verified',NOW,candidate)
        self.assertEqual(verify_delivery(store,'d',adapter,snapshot,now=NOW).outcome,'verified')
        adapter.submit.assert_not_called()
