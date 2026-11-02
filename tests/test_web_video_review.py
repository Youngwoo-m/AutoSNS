"""가짜 제작 leaf + 실제 임시 HTTP로 영상 검토/범위 미리보기/등록을 확인한다."""
import json
import unittest
from tests import test_web_video_tasks as fixture
from tests.operations import test_video_tasks as media


class VideoReviewHTTPTests(unittest.TestCase):
    request=fixture.VideoHTTPTests.request
    login=fixture.VideoHTTPTests.login
    make_content=fixture.VideoHTTPTests.make_content
    ready_plan=fixture.VideoHTTPTests.ready_plan
    factory=media.VideoTaskTests.factory
    runner=media.VideoTaskTests.runner

    def setUp(self):
        fixture.VideoHTTPTests.setUp(self)
        self.mode='ok';self.runs=self.factory_calls=0
        self.service.runner_factory=self.factory
        self.service.reuse_authorization=media.VideoTaskTests.authorize
        self.service.probe=media.VideoTaskTests.probe
        self.service.inspect_video=lambda **kwargs:{}
        self.service.defer_video_review=True

    def waiting(self):
        cookie=self.login()
        status,_,raw=self.request(self.route,'POST',self.body,cookie);self.assertEqual(status,200)
        task=json.loads(raw);self.service.run_next()
        path='/api/v2/video-tasks/'+task['task_id']
        status,_,raw=self.request(path,headers=cookie);self.assertEqual(status,200)
        self.assertEqual(json.loads(raw)['state'],'awaiting_review')
        self.assertEqual(self.runs,1)
        return cookie,path

    def review_body(self,context,decision='pass'):
        return dict(context_fingerprint=context['context_fingerprint'],decision=decision,
            checks=dict(audio_checked=True,font_checked=True,disclosure_checked=True,scenes_checked=True),
            notes='사람이 확인한 시험 기록')

    def test_review_context_and_range_preview_do_not_mutate_or_rerender(self):
        cookie,path=self.waiting();before=self.contents.get(self.item['id'])
        self.assertEqual(self.request(path+'/review')[0],401)
        status,_,raw=self.request(path+'/review',headers=cookie);self.assertEqual(status,200)
        context=json.loads(raw);self.assertEqual(context['scene_count'],3)
        self.assertEqual(context['review_status'],'not_checked')
        self.assertNotIn(str(self.root).encode(),raw);self.assertNotIn(b'image_asset_id',raw)
        status,headers,full=self.request(path+'/preview',headers=cookie)
        self.assertEqual(status,200);self.assertEqual(headers['Content-Type'],'video/mp4')
        self.assertEqual(self.request(path+'/preview',headers={**cookie,'Range':'bytes=4-7'})[2],b'ftyp')
        status,headers,part=self.request(path+'/preview',headers={**cookie,'Range':'bytes=-4'})
        self.assertEqual(status,206);self.assertEqual(part,full[-4:]);self.assertIn('Content-Range',headers)
        for header in ('bytes=999999-','bytes=0-1,4-7','bytes=-0','invalid'):
            self.assertEqual(self.request(path+'/preview',headers={**cookie,'Range':header})[0],416)
        self.assertEqual(self.contents.get(self.item['id']),before);self.assertEqual(self.runs,1)

    def test_manual_review_registration_is_explicit_and_idempotent(self):
        cookie,path=self.waiting();context=json.loads(self.request(path+'/review',headers=cookie)[2])
        body=self.review_body(context)
        self.assertEqual(self.request(path+'/review','POST',{**body,'actor':'producer'},cookie)[0],400)
        self.assertEqual(self.request(path+'/review','POST',{**body,'checks':{**body['checks'],'audio_checked':False}},cookie)[0],400)
        self.assertEqual(self.request(path+'/review','POST',{**body,'context_fingerprint':'0'*64},cookie)[0],409)
        status,_,raw=self.request(path+'/review','POST',body,cookie);self.assertEqual(status,200)
        result=json.loads(raw);self.assertEqual(result['state'],'completed');self.assertEqual(result['review_status'],'not_checked')
        self.assertEqual(result['output_revision'],self.item['revision']+1)
        self.assertEqual(self.request(path+'/review','POST',body,cookie)[2],raw)
        self.assertEqual(self.runs,1);self.assertEqual(len(self.contents.get(self.item['id'])['assets']),len(self.item['assets'])+1)

    def test_changes_request_preserves_original_and_never_registers_candidate(self):
        cookie,path=self.waiting();context=json.loads(self.request(path+'/review',headers=cookie)[2])
        body=self.review_body(context,'changes_requested');body['checks']={key:False for key in body['checks']}
        status,_,raw=self.request(path+'/review','POST',body,cookie);self.assertEqual(status,200)
        self.assertEqual(json.loads(raw)['state'],'blocked')
        self.assertEqual(self.contents.get(self.item['id']),self.item);self.assertEqual(self.runs,1)
