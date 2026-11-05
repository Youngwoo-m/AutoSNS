import copy
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch
from common.operations.content_store import StoreError
from common.operations.media_plan_runtime import prepare_short_media,render_prepared_short,ingest_short_output
from tests.operations import test_media_plans as fixture

class MediaRuntimeTests(unittest.TestCase):
    setUp=fixture.MediaPlanTests.setUp
    make_content=fixture.MediaPlanTests.make_content
    ready_plan=fixture.MediaPlanTests.ready_plan
    def record(self):
        snapshot,images,voice=self.make_content();self.plans.initialize()
        return self.plans.save(snapshot['id'],snapshot['revision'],0,self.ready_plan(images,voice))
    def test_prepare_pins_registered_assets_without_mutating_originals(self):
        record=self.record();before=(self.root/'operations.sqlite3').read_bytes()
        prepared=prepare_short_media(record,content_store=self.contents,attempt_id='attempt-1')
        self.assertTrue(prepared.artifact_root.is_relative_to(self.root/'media-artifacts'))
        self.assertEqual(len(prepared.scene_assets),3)
        for asset_id,registered in prepared.scene_assets.items():
            _,raw=self.contents.read_asset(record['content_id'],record['content_revision'],asset_id)
            self.assertEqual(Path(registered.path).read_bytes(),raw)
        self.assertTrue(Path(prepared.manifest['voice']).is_file())
        self.assertEqual(before,(self.root/'operations.sqlite3').read_bytes())
        with self.assertRaises(FileExistsError):prepare_short_media(record,content_store=self.contents,attempt_id='attempt-1')
    def test_plan_version_owner_and_path_injection_rejected_before_staging(self):
        record=self.record()
        for changed in (dict(owner_account_id='dept'),dict(manifest_hash='bad'),dict(plan_revision=0)):
            with self.assertRaises(StoreError):prepare_short_media(dict(record,**changed),content_store=self.contents,attempt_id='test')
        for attempt in ('../../outside','/tmp/other','a/b',''):
            with self.assertRaises(StoreError):prepare_short_media(record,content_store=self.contents,attempt_id=attempt)
        self.assertFalse((self.root/'media-artifacts').exists())
    def test_incomplete_plan_and_missing_renderer_never_render(self):
        record=self.record();bad=copy.deepcopy(record);bad['plan']['voice_asset_id']=None
        with self.assertRaises(StoreError):prepare_short_media(bad,content_store=self.contents,attempt_id='bad')
        prepared=prepare_short_media(record,content_store=self.contents,attempt_id='good')
        result=render_prepared_short(prepared)
        self.assertEqual(result['status'],'blocked');self.assertFalse((prepared.artifact_root/'short.mp4').exists())
    def test_registered_renderer_receives_pinned_assets_without_fabricating_reviews(self):
        prepared=prepare_short_media(self.record(),content_store=self.contents,attempt_id='registered')
        factories=[]
        def factory(**kwargs):
            factories.append(kwargs)
            return lambda **kwargs:dict(status='blocked',reason_code='reuse_not_authorized')
        result=render_prepared_short(prepared,runner_factory=factory)
        self.assertEqual(result['status'],'blocked');self.assertEqual(result['reason_code'],'reuse_not_authorized')
        self.assertIs(factories[0]['scene_assets'],prepared.scene_assets)
        self.assertFalse((prepared.artifact_root/'short.mp4').exists())

    def test_checked_output_is_cas_ingested_and_cannot_duplicate_or_overwrite(self):
        record=self.record();prepared=prepare_short_media(record,content_store=self.contents,attempt_id='ingest')
        raw=b'0000ftypisomfixture';path=prepared.artifact_root/'short.mp4';path.write_bytes(raw)
        evidence=dict(kind='remotion_video',probe=dict(seconds=10,width=1080,height=1920,has_audio=True),
            audio_checked=True,font_checked=True,disclosure='AI 합성 음성',scenes=[dict(checked=True)])
        asset=dict(path=str(path),filename=path.name,media_type='video/mp4',size=len(raw),sha256=hashlib.sha256(raw).hexdigest(),evidence=evidence)
        result=dict(status='completed',assets=[asset])
        output=ingest_short_output(prepared,result,content_store=self.contents)
        self.assertEqual(output['content']['revision'],record['content_revision']+1)
        self.assertEqual(output['content']['owner_account_id'],record['owner_account_id'])
        self.assertEqual(output['review_status'],'not_checked')
        with self.assertRaises(StoreError):ingest_short_output(prepared,result,content_store=self.contents)
        self.assertEqual(self.contents.get(record['content_id'])['revision'],output['content']['revision'])

    def test_unchecked_output_cannot_enter_content_store(self):
        prepared=prepare_short_media(self.record(),content_store=self.contents,attempt_id='unchecked')
        with self.assertRaises(StoreError):ingest_short_output(prepared,dict(status='blocked',assets=[]),content_store=self.contents)
