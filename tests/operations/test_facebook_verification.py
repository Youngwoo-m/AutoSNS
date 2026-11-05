"""Facebook 텍스트 배포의 실제 원장 공개 검증. 원격 I/O는 없다."""
from dataclasses import replace
import hashlib
import unittest
from unittest.mock import Mock
from tests.operations import test_runtime_store as fixture_module
NOW=fixture_module.NOW
from common.operations.runtime_models import VerificationResult
from common.operations.content_store import StoreError
from common.operations.verification import snapshot_fingerprints,verify_delivery

class FacebookVerificationTests(unittest.TestCase):
    setUp=fixture_module.RuntimeStoreTests.setUp
    fixture=fixture_module.RuntimeStoreTests.fixture
    store=fixture_module.RuntimeStoreTests.store

    def prepared(self):
        self.fixture();store=self.store();store.initialize();store.create_run('r')
        ctx=replace(fixture_module.context(),platform='facebook',connection_id='dept.facebook',target_id='123',destination_account_id='dept',options={'text_only':True})
        snapshot=dict(id='c',revision=1,manifest_hash='m',owner_account_id='personal',original='개인 원문',variants=[dict(platform='facebook',destination_account_id='dept',text='학과 교차 게시')],assets=[dict(sha256='a'*64)])
        store.create_delivery('d','r',ctx);store.record_publication_approval('d',1,ctx.context_hash,'approval',('a','b'))
        lease=store.claim_run('r','worker',{'host_id':'host','pid':123,'started_at':NOW.isoformat()},NOW)
        attempt=store.create_attempt('d',store.get_delivery('d')['version'],lease,ctx.context_hash,'approval',now=NOW)
        permit=store.issue_permit(attempt['id'],lease,ctx.context_hash,'approval',NOW);store.consume_permit(permit,lease,NOW)
        store.finish_attempt(attempt['id'],'submitted',remote_id='123_456',now=NOW)
        evidence=dict(remote_id='123_456',target_id='123',destination_account_id='dept',created_at=NOW.isoformat(),body_sha256=hashlib.sha256('학과 교차 게시'.encode()).hexdigest(),media_sha256=[],visibility='public',url='https://www.facebook.com/123/posts/456')
        return store,ctx,snapshot,evidence

    def test_only_explicit_facebook_text_only_excludes_source_assets(self):
        _,ctx,snapshot,_=self.prepared()
        self.assertEqual(snapshot_fingerprints(ctx.to_dict(),snapshot)[1],[])
        for change in (dict(options={}),dict(platform='youtube')):
            altered=replace(ctx,**change)
            self.assertEqual(snapshot_fingerprints(altered.to_dict(),snapshot)[1],['a'*64])
        # Instagram은 별도 명시 자산 선택을 요구한다. Facebook 옵션을 묵시적으로 재사용하지 않는다.
        with self.assertRaises(StoreError):snapshot_fingerprints(replace(ctx,platform='instagram').to_dict(),snapshot)

    def test_public_evidence_persists_exact_url_and_crosspost_body(self):
        store,ctx,snapshot,evidence=self.prepared();adapter=Mock()
        adapter.verify.return_value=VerificationResult('verified',NOW,evidence)
        result=verify_delivery(store,'d',adapter,snapshot,now=NOW)
        self.assertEqual(result.outcome,'verified');self.assertEqual(store.get_delivery('d')['url'],evidence['url'])
        self.assertEqual(store.get_delivery('d')['state'],'verified')

    def test_missing_or_unsafe_url_cannot_complete_public_verification(self):
        store,ctx,snapshot,evidence=self.prepared();adapter=Mock()
        for url in (None,'https://evil.example/post','https://facebook.com/123/posts/456?access_token=SECRET','https://facebook.com:443/123/posts/456','https://user@facebook.com/123/posts/456','https://facebook.com/123/posts/456#fragment','https://facebook.com/123/posts/\n456','https://facebook.com/'):
            with self.subTest(url=url):
                adapter.verify.return_value=VerificationResult('verified',NOW,{**evidence,'url':url})
                result=verify_delivery(store,'d',adapter,snapshot,now=NOW)
                self.assertEqual(result.outcome,'pending');self.assertNotEqual(store.get_delivery('d')['state'],'verified')
                self.assertIsNone(store.get_delivery('d')['url'])
