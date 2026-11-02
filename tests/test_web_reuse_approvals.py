"""실제 승인 저장소·인증 HTTP·영상 계약 연결. 영상 leaf만 가짜다."""
import json
import unittest
from tests import test_web_video_review as fixture
from tests.operations import test_video_tasks as media
from common.operations.reuse_approvals import ManagedReuseAuthorizer


class ReuseHTTPTests(unittest.TestCase):
    request=fixture.VideoReviewHTTPTests.request
    login=fixture.VideoReviewHTTPTests.login
    make_content=fixture.VideoReviewHTTPTests.make_content
    ready_plan=fixture.VideoReviewHTTPTests.ready_plan
    factory=fixture.VideoReviewHTTPTests.factory
    runner=fixture.VideoReviewHTTPTests.runner
    review_body=fixture.VideoReviewHTTPTests.review_body
    waiting=fixture.VideoReviewHTTPTests.waiting

    def setUp(self):
        fixture.VideoReviewHTTPTests.setUp(self)
        self.server.reuse_approval_store.initialize()
        self.approvals=self.server.reuse_approval_service
        self.service.reuse_authorization=ManagedReuseAuthorizer(self.approvals)
        self.approval_route='/api/v2/contents/'+self.item['id']+'/reuse-approvals?revision='+str(self.item['revision'])

    def rows(self,cookie):
        status,_,raw=self.request(self.approval_route,headers=cookie);self.assertEqual(status,200)
        return json.loads(raw)['items']

    def save(self,cookie,row,approved=True):
        body=dict(asset_id=row['asset_id'],expected_revision=row['approval_revision'],rights_confirmed=approved,visual_checked=approved,notes='사람이 이미지 사용과 내용을 확인한 시험 기록')
        status,_,raw=self.request(self.approval_route,'POST',body,cookie);self.assertEqual(status,200)
        return json.loads(raw)

    def approve_images(self,cookie):return [self.save(cookie,row) for row in self.rows(cookie)]

    def test_auth_schema_and_cas_do_not_accept_client_owner_hash_or_actor(self):
        self.assertEqual(self.request(self.approval_route)[0],401);cookie=self.login();rows=self.rows(cookie)
        self.assertEqual(len(rows),3);self.assertTrue(all(row['status']=='not_approved' for row in rows))
        body=dict(asset_id=rows[0]['asset_id'],expected_revision=0,rights_confirmed=True,visual_checked=True,notes='확인')
        for field in ('owner_account_id','sha256','actor','status','path'):
            self.assertEqual(self.request(self.approval_route,'POST',{**body,field:'injected'},cookie)[0],400)
        self.assertEqual(self.request(self.approval_route,'POST',body,{**cookie,'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request(self.approval_route,'POST',body,cookie)[0],200)
        self.assertEqual(self.request(self.approval_route,'POST',body,cookie)[0],409)
        self.assertEqual(self.contents.get(self.item['id']),self.item)

    def test_unapproved_images_block_leaf_then_review_rechecks_revocation(self):
        cookie=self.login()
        status,_,raw=self.request(self.route,'POST',self.body,cookie);self.assertEqual(status,409)
        self.assertIsNone(self.service.run_next());self.assertEqual(self.runs,0)
        approved=self.approve_images(cookie)
        changed={**self.record['plan'],'footer':'명시 재계획'}
        new=self.plans.save(self.item['id'],self.item['revision'],1,changed);self.body['expected_plan_revision']=new['plan_revision']
        cookie,path=self.waiting();context=json.loads(self.request(path+'/review',headers=cookie)[2])
        revoked=self.save(cookie,approved[0],False)
        self.assertEqual(self.request(path+'/review','POST',self.review_body(context),cookie)[0],409)
        self.assertEqual(self.contents.get(self.item['id']),self.item)
        self.save(cookie,revoked,True)
        status,_,raw=self.request(path+'/review','POST',self.review_body(context),cookie)
        self.assertEqual(status,200);self.assertEqual(json.loads(raw)['state'],'completed');self.assertEqual(self.runs,1)

    def test_approval_revoked_during_leaf_stops_ingest_until_explicit_resume(self):
        cookie=self.login();approved=self.approve_images(cookie);original=self.service.runner_factory
        self.service.inspect_video=media.VideoTaskTests.inspect
        def factory(**kwargs):
            leaf=original(**kwargs)
            def render(**inputs):
                value=leaf(**inputs)
                self.approvals.save(self.item['id'],self.item['revision'],approved[0]['asset_id'],1,False,False,'명시 철회',actor='console_user')
                return value
            return render
        self.service.runner_factory=factory
        status,_,raw=self.request(self.route,'POST',self.body,cookie);self.assertEqual(status,200);task=json.loads(raw)
        result=self.service.run_next();self.assertEqual(result['state'],'rendered');self.assertEqual(result['reason_code'],'reuse_not_authorized')
        self.assertEqual(self.contents.get(self.item['id']),self.item)
        revoked=next(row for row in self.rows(cookie) if row['asset_id']==approved[0]['asset_id']);self.save(cookie,revoked,True)
        status,_,raw=self.request('/api/v2/video-tasks/'+task['task_id']+'/resume','POST',{},cookie)
        self.assertEqual(status,200);self.assertEqual(json.loads(raw)['state'],'completed');self.assertEqual(self.runs,1)
