"""형식별 입력을 제작기로 전달하고 원본·출처·변환본을 보존한다."""
import json
import unittest
from common.operations.worker_service import WorkerService
from tests.integration import test_worker_service as fixture
from tests.operations.test_runtime_store import NOW

class PromptPipelineTests(unittest.TestCase):
    setUp=fixture.ServiceTests.setUp
    service=fixture.ServiceTests.service
    request=fixture.ServiceTests.request
    submit=fixture.ServiceTests.submit
    def test_card_prompt_uses_current_snapshot_and_keeps_crosspost_metadata(self):
        variants=[dict(destination_account_id='dept',platform='instagram',text='보존할 학과 변환')]
        sources=[dict(url='https://example.org/provided',note='제공 자료')]
        content=self.content.create('personal',dict(title='학습 카드',kind='card',series='학습',original='카드에 쓸 요점',variants=variants,sources=sources))
        prompts=[]
        class Provider:
            def generate(self,request,prompt,policy):
                prompts.append(prompt)
                return dict(status='completed',text=json.dumps(dict(text='카드 1: 학습 요점',media=[])),provider_id='claude-subscription',execution_id='prompt-fixture',observed_usage=None)
        self.producers={'produce':{'provider':Provider(),'media_runner':{}}}
        service=self.service();self.submit(service,content)
        self.assertEqual(WorkerService(service,clock=lambda:NOW).tick()['state'],'completed')
        self.assertEqual(len(prompts),1)
        self.assertIn('카드',prompts[0]);self.assertIn('카드에 쓸 요점',prompts[0])
        self.assertIn('https://example.org/provided',prompts[0])
        current=self.content.get(content['id'])
        self.assertEqual(current['kind'],'card');self.assertEqual(current['variants'],variants);self.assertEqual(current['sources'],sources)
        self.assertEqual(current['original'],'카드 1: 학습 요점');self.assertEqual(current['status'],'review')
        self.assertEqual(self.content.get(content['id'],1)['original'],'카드에 쓸 요점')
