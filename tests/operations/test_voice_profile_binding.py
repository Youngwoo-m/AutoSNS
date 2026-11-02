"""기존 음성 작업 재개는 최초 intent에 결속된 프로필에서만 허용한다. 네트워크·실합성 없음."""
from pathlib import Path
from contextlib import closing
import sqlite3
import tempfile
import unittest

from common.operations.models import ContractError
from tests.operations import test_voice_tasks as base


class VoiceProfileBindingTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.env=base.Env(Path(temp.name))

    def assert_rejected_without_changes(self,service,task_id,call=None):
        env=self.env;before=env.store.get_row(task_id)
        content_before=env.content.get(env.cid)
        native_before=(list(env.client.wait_calls),list(env.client.audio_calls),list(env.client.generate_calls))
        with self.assertRaises(ContractError) as caught:
            (call or (lambda:service.resume(task_id)))()
        self.assertEqual(caught.exception.code,'voice_recovery_mismatch')
        self.assertEqual(env.store.get_row(task_id),before)
        self.assertEqual(env.content.get(env.cid),content_before)
        self.assertEqual((env.client.wait_calls,env.client.audio_calls,env.client.generate_calls),native_before)

    def test_changed_profile_pending_refuses_before_poll_or_audio(self):
        row=self.env.create();self.assertEqual(row['state'],'pending')
        self.assert_rejected_without_changes(self.env.make_service(profile_id='another-profile'),row['task_id'])

    def test_changed_profile_audio_ready_refuses_before_asset_ingest(self):
        row=self.env.create();self.env.service._poll(self.env.store.get_row(row['task_id']))
        self.assertEqual(self.env.store.get_row(row['task_id'])['state'],'audio_ready')
        self.assert_rejected_without_changes(self.env.make_service(profile_id='another-profile'),row['task_id'])
        self.assertEqual(self.env.content.get(self.env.cid)['revision'],1)

    def test_original_profile_can_resume_and_completed_remains_read_only_on_profile_change(self):
        row=self.env.create();done=self.env.service.resume(row['task_id'])
        self.assertEqual(done['state'],'completed');self.assertEqual(done['output_revision'],2)
        service=self.env.make_service(profile_id='another-profile')
        before=self.env.store.get_row(row['task_id']);native_before=(list(self.env.client.wait_calls),list(self.env.client.audio_calls))
        self.assertEqual(service.resume(row['task_id']),done)
        self.assertEqual(service.confirm_recovery(row['task_id'],done['generation_id'],'a'*64),done)
        self.assertEqual(self.env.store.get_row(row['task_id']),before)
        self.assertEqual((self.env.client.wait_calls,self.env.client.audio_calls),native_before)

    def test_linked_pending_and_audio_ready_confirm_replay_require_original_profile(self):
        row=self.env.create();service=self.env.make_service(profile_id='another-profile')
        for state in ('pending','audio_ready'):
            if state=='audio_ready':self.env.service._poll(self.env.store.get_row(row['task_id']))
            self.assert_rejected_without_changes(service,row['task_id'],lambda:service.confirm_recovery(row['task_id'],row['generation_id'],'a'*64))
        unchanged=self.env.service.confirm_recovery(row['task_id'],row['generation_id'],'a'*64)
        self.assertEqual(unchanged['state'],'audio_ready')

    def test_tampered_owner_or_manifest_cannot_poll_even_with_same_profile(self):
        row=self.env.create()
        for key,value in [('owner_account_id','dept'),('manifest_hash','b'*64)]:
            original=self.env.store.get_row(row['task_id'])[key]
            with closing(sqlite3.connect(self.env.store.root/'voice-tasks.sqlite3')) as db, db:
                db.execute('UPDATE voice_tasks SET '+key+'=? WHERE task_id=?',(value,row['task_id']))
            self.assert_rejected_without_changes(self.env.service,row['task_id'])
            with closing(sqlite3.connect(self.env.store.root/'voice-tasks.sqlite3')) as db, db:
                db.execute('UPDATE voice_tasks SET '+key+'=? WHERE task_id=?',(original,row['task_id']))
