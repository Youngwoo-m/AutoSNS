from datetime import timedelta
from unittest.mock import Mock
from tests.operations.test_recovery import RecoveryFixture, NOW
from common.operations.runtime_models import VerificationResult

class VerificationTests(RecoveryFixture):
    def adapter(self, **changes):
        adapter=Mock();evidence=self.candidate();evidence.update(visibility='public');evidence.update(changes)
        adapter.verify.return_value=VerificationResult('verified',NOW,evidence)
        return adapter

    def test_strong_publication_verified_and_aggregate_completed(self):
        from common.operations.verification import verify_delivery
        s,ctx,lease,a=self.started('submitted');adapter=self.adapter()
        result=verify_delivery(s,'d',adapter,s.content_store.get(),now=NOW)
        self.assertEqual(result.outcome,'verified');self.assertEqual(s.get_delivery('d')['state'],'verified');self.assertEqual(s.get_run('r')['state'],'completed')

    def test_changed_body_media_private_future_observation_fail_closed(self):
        from common.operations.verification import verify_delivery
        for changes in [{'body_sha256':'wrong'},{'media_sha256':['changed']},{'visibility':'private'},{'created_at':(NOW+timedelta(days=1)).isoformat()}]:
            s,ctx,lease,a=self.started('submitted')
            result=verify_delivery(s,'d',self.adapter(**changes),s.content_store.get(),now=NOW)
            self.assertNotEqual(result.outcome,'verified');self.assertNotEqual(s.get_delivery('d')['state'],'verified')
            self.tmp.cleanup();self.setUp()

    def test_schedule_not_public_before_due(self):
        from common.operations.verification import verify_delivery
        s,ctx,lease,a=self.started(None)
        s.finish_attempt(a['id'],'scheduled',remote_id='remote',scheduled_at=NOW+timedelta(hours=1),now=NOW)
        adapter=self.adapter();result=verify_delivery(s,'d',adapter,s.content_store.get(),now=NOW)
        self.assertEqual(result.outcome,'pending');self.assertEqual(s.get_delivery('d')['state'],'scheduled');adapter.verify.assert_not_called()

    def test_unknown_is_not_verified_without_reconciliation(self):
        from common.operations.verification import verify_delivery
        s,ctx,lease,a=self.started();adapter=self.adapter()
        result=verify_delivery(s,'d',adapter,s.content_store.get(),now=NOW)
        self.assertEqual(result.outcome,'pending');adapter.verify.assert_not_called()

    def test_snapshot_fixed_schedule_still_blocks_after_response_loss(self):
        from common.operations.verification import verify_delivery
        s,ctx,lease,a=self.started('submitted')
        # 정상 서버 context가 미래 fixed schedule을 가지는 사례를 독립 fake store로 표현한다.
        delivery=s.get_delivery('d');delivery['context']['schedule_condition']['at']=(NOW+timedelta(hours=1)).isoformat()
        s.get_delivery=Mock(return_value=delivery);adapter=self.adapter()
        result=verify_delivery(s,'d',adapter,s.content_store.get(),now=NOW)
        self.assertEqual(result.outcome,'pending');adapter.verify.assert_not_called()
