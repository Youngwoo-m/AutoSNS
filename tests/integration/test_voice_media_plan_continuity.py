"""음성 생성이 만든 새 원고 버전에 기존 장면 구성을 명시적으로 이어 쓴다."""
from pathlib import Path
import tempfile
import unittest
from tests.operations.test_voice_tasks import Env
from tests.operations.test_media_plans import scene
from common.operations.media_plans import MediaPlanStore,default_media_plan


class VoiceMediaPlanContinuityTests(unittest.TestCase):
    def test_voice_output_can_replace_audio_without_rewriting_saved_scenes(self):
        with tempfile.TemporaryDirectory() as tmp:
            env=Env(Path(tmp))
            content=env.content.get(env.cid)
            for index in range(2):
                content=env.content.add_asset(env.cid,content['revision'],f'scene{index}.png','image/png',
                    b'\x89PNG\r\n\x1a\n'+bytes([index])*16)
            images=[asset['id'] for asset in content['assets']]
            plans=MediaPlanStore(env.content.root,env.content);plans.initialize()
            plan=default_media_plan(content)
            plan.update(source='원문 출처',scenes=[scene(images[0]),scene(images[1])])
            original=plans.save(env.cid,content['revision'],0,plan)
            task=env.create(revision=content['revision'])
            task=env.service.resume(task['task_id'])
            self.assertEqual(task['state'],'completed')
            self.assertEqual(len(env.client.generate_calls),1)
            self.assertGreater(task['output_revision'],content['revision'])
            target=plans.get(env.cid,task['output_revision'])
            self.assertEqual(target['plan']['scenes'],[])
            imported=plans.import_plan(env.cid,task['output_revision'],0,content['revision'],1,task['asset_id'])
            self.assertEqual(imported['plan']['scenes'],original['plan']['scenes'])
            self.assertEqual(imported['plan']['source'],'원문 출처')
            self.assertEqual(imported['plan']['voice_asset_id'],task['asset_id'])
            self.assertTrue(imported['inputs_ready'])
            self.assertEqual(imported['review_status'],'not_checked')
            self.assertFalse(imported['execution_enabled'])
            self.assertEqual(plans.get(env.cid,content['revision']),original)
            self.assertEqual(len(env.client.generate_calls),1)
