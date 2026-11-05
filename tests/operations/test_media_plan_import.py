"""이전 제작 계획을 새 원고 버전에 명시적으로 가져오는 계약."""
import copy
import hashlib
import unittest
from unittest.mock import patch
from tests.operations import test_media_plans as fixture
WAV=fixture.WAV
from common.operations.content_store import ConflictError, StoreError


class MediaPlanImportTests(unittest.TestCase):
    setUp=fixture.MediaPlanTests.setUp
    make_content=fixture.MediaPlanTests.make_content
    ready_plan=fixture.MediaPlanTests.ready_plan
    def prepared(self, voice=True):
        source, images, old_voice=self.make_content(voice=voice)
        self.plans.initialize()
        plan=self.ready_plan(images, old_voice)
        saved=self.plans.save(source['id'],source['revision'],0,plan)
        target=self.contents.add_asset(source['id'],source['revision'],'new.wav','audio/wav',WAV+b'new voice')
        return source,target,saved,target['assets'][-1]['id']

    def run_import(self, source,target,saved,**kw):
        return self.plans.import_plan(source['id'],target['revision'],0,source['revision'],saved['plan_revision'],**kw)

    def test_import_preserves_plan_and_source_without_copying_review(self):
        source,target,saved,voice=self.prepared()
        before=self.contents.get(source['id'])
        result=self.run_import(source,target,saved,voice_asset_id=voice)
        expected=copy.deepcopy(saved['plan']);expected['voice_asset_id']=voice
        self.assertEqual(result['plan'],expected)
        self.assertEqual(result['plan_revision'],1)
        self.assertEqual(result['content_revision'],target['revision'])
        self.assertEqual(result['review_status'],'not_checked')
        self.assertIs(result['execution_enabled'],False)
        self.assertEqual(self.plans.get(source['id'],source['revision']),saved)
        self.assertEqual(self.contents.get(source['id']),before)
        with self.assertRaises(ConflictError):self.run_import(source,target,saved,voice_asset_id=voice)

    def test_import_keeps_existing_voice_unless_explicitly_replaced(self):
        source,target,saved,_=self.prepared()
        self.assertEqual(self.run_import(source,target,saved)['plan'],saved['plan'])

    def test_no_voice_plan_can_select_new_voice(self):
        source,target,saved,voice=self.prepared(voice=False)
        self.assertEqual(self.run_import(source,target,saved,voice_asset_id=voice)['plan']['voice_asset_id'],voice)

    def test_source_and_target_cas_and_latest_head_are_required(self):
        source,target,saved,_=self.prepared()
        changed=self.plans.save(source['id'],source['revision'],1,{**saved['plan'],'footer':'new'})
        with self.assertRaises(ConflictError):self.run_import(source,target,saved)
        self.assertEqual(self.plans.get(source['id'],target['revision'])['plan_revision'],0)
        self.contents.add_asset(target['id'],target['revision'],'other.wav','audio/wav',WAV+b'other')
        with self.assertRaises(ConflictError):self.run_import(source,target,changed)

    def test_invalid_revisions_voice_and_missing_source_are_rejected(self):
        source,target,saved,_=self.prepared()
        for args in ((target['revision'],0,target['revision'],1),(target['revision'],0,True,1),(target['revision'],0,source['revision'],0)):
            with self.assertRaises(StoreError):self.plans.import_plan(source['id'],*args)
        for voice in ('notfound',source['assets'][0]['id'],True):
            with self.assertRaises(StoreError):self.run_import(source,target,saved,voice_asset_id=voice)
        with self.assertRaises(StoreError):self.plans.import_plan(source['id'],target['revision'],0,1,1)
        self.assertEqual(self.plans.get(source['id'],target['revision'])['plan_revision'],0)

    def test_source_or_target_tampered_bytes_cannot_be_imported(self):
        source,target,saved,_=self.prepared()
        original=self.contents.read_asset
        for revision in (source['revision'],target['revision']):
            def tampered(cid,rev,aid):
                asset,raw=original(cid,rev,aid)
                return (asset,raw+b'x') if rev==revision else (asset,raw)
            with patch.object(self.contents,'read_asset',side_effect=tampered):
                with self.assertRaises(StoreError):self.run_import(source,target,saved)
        self.assertEqual(self.plans.get(source['id'],target['revision'])['plan_revision'],0)

    def test_changed_asset_identity_and_other_owner_are_rejected(self):
        source,target,saved,_=self.prepared()
        original=self.contents.read_asset
        def changed(cid,rev,aid):
            asset,raw=original(cid,rev,aid)
            if rev==target['revision']:
                raw=raw+b'different';asset={**asset,'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
            return asset,raw
        with patch.object(self.contents,'read_asset',side_effect=changed):
            with self.assertRaises(StoreError):self.run_import(source,target,saved)
        original_get=self.contents.get
        def owner(cid,rev=None):
            result=original_get(cid,rev)
            return {**result,'owner_account_id':'dept'} if rev==target['revision'] else result
        with patch.object(self.contents,'get',side_effect=owner):
            with self.assertRaises(StoreError):self.run_import(source,target,saved)

    def test_new_voice_bytes_are_verified_and_head_moving_during_import_conflicts(self):
        source,target,saved,voice=self.prepared()
        original=self.contents.read_asset
        def bad_voice(cid,rev,aid):
            asset,raw=original(cid,rev,aid)
            return (asset,raw+b'bad') if aid==voice else (asset,raw)
        with patch.object(self.contents,'read_asset',side_effect=bad_voice):
            with self.assertRaises(StoreError):self.run_import(source,target,saved,voice_asset_id=voice)
        moved=[]
        def move_head(cid,rev,aid):
            result=original(cid,rev,aid)
            if not moved:
                moved.append(True)
                self.contents.add_asset(cid,target['revision'],'concurrent.wav','audio/wav',WAV+b'concurrent')
            return result
        with patch.object(self.contents,'read_asset',side_effect=move_head):
            with self.assertRaises(ConflictError):self.run_import(source,target,saved,voice_asset_id=voice)
        self.assertEqual(self.plans.get(source['id'],target['revision'])['plan_revision'],0)
