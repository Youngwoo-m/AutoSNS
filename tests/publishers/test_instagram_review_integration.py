"""실제 저장소·최종 검토·매체 공급자·전송 원장을 잇는 격리 통합 시험.

최종 수동 검토 guard를 검증한다. 실제 원고 독립 검토·publication permit·런타임 STOP
추가 정책의 대체 시험이 아니다. 공개 stager와 HTTP 모두 가짜이며 외부 I/O는 없다.
"""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
from common.operations.content_store import ContentStore
from common.operations.ledger import Ledger
from common.operations.registry import load_registry
from common.operations.runtime_models import PublicationContext
from common.operations.instagram_reviews import InstagramReviewStore,InstagramReviewService
from common.publishers.instagram_payloads import build_instagram_payload
from common.publishers.instagram_client import InstagramApiClient
from common.publishers.instagram_media_sources import InstagramMediaSourceFactory
from common.publishers.instagram_services import InstagramJournal,InstagramServices

NOW=datetime(2026,11,2,tzinfo=timezone.utc)
CHECKS=dict(rights_confirmed=True,visual_checked=True,caption_checked=True,composition_checked=True,audio_checked=False)
class InstagramReviewIntegrationTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)/'isolated'
        self.now=NOW;self.http=[];self.staged=[];self.status='FINISHED';self.identity_authorized=True
        self.contents=ContentStore(self.root);self.contents.initialize()
        self.item=self.contents.create('dept',dict(title='검토할 카드',kind='card',original='승인할 캡션 그대로'))
        for name,raw in (('one.jpg',b'\xff\xd8\xfffixture-one\xff\xd9'),('two.jpg',b'\xff\xd8\xfffixture-two\xff\xd9')):
            self.item=self.contents.add_asset(self.item['id'],self.item['revision'],name,'image/jpeg',raw)
        self.ids=[a['id'] for a in self.item['assets']]
        base=load_registry(Path(__file__).resolve().parents[2]/'ax-console/config/operations.json')
        connection=replace(base.connections['dept.instagram'],target_id='123',expected_login_subject='fixture-subject')
        self.registry=replace(base,connections={**base.connections,connection.id:connection})
        self.ledger=Ledger(self.root,lambda:self.registry,self.contents);self.ledger.initialize()
        self.review_store=InstagramReviewStore(self.root);self.review_store.initialize()
        self.reviews=InstagramReviewService(self.review_store,self.contents,self.ledger.get_delivery,lambda:self.registry,lambda:self.now)
        factory=InstagramMediaSourceFactory(self.contents.read_asset,stager=self.stage,approval_guard=self.reviews.authorize,allowed_hosts=('cdn.example.org',),clock=lambda:self.now)
        # 임의 명시 버전은 시험 경로이며 현재 앱 지원 버전임을 주장하지 않는다.
        client=InstagramApiClient('fake-fixture-token',api_version='v26.0',transport=self.transport)
        journal=InstagramJournal(self.root);journal.initialize()
        self.service=InstagramServices(client,journal,lambda:self.now,media_factory=factory,account_authorizer=self.authorize_account,review_guard=self.reviews.authorize)
        self.target=dict(platform='instagram',target_id='123',connection_id='dept.instagram',expected_login_subject='fixture-subject')
    def transport(self,method,path,headers,body):
        self.http.append((method,path,headers,body));node=urlsplit(path).path
        if method=='GET' and node=='/v26.0/123':row=dict(id='123',username='fixture-dept')
        elif method=='GET':row=dict(id=node.rsplit('/',1)[-1],status_code=self.status)
        else:row=dict(id=str(1000+len(self.http)))
        return 200,json.dumps(row).encode()
    def stage(self,request,raw):
        self.staged.append((dict(request),raw))
        return dict(url='https://cdn.example.org/'+request['asset_id']+'.jpg',asset_sha256=hashlib.sha256(raw).hexdigest(),asset_size=len(raw),expires_at=self.now+timedelta(hours=1),receipt_id='fixture_'+str(len(self.staged)))
    def authorize_account(self,target,identity):
        return dict(target_id='123',login_subject='fixture-subject',professional=True,can_publish=self.identity_authorized,checked_at=self.now,login_mode='facebook_login')
    def plan_context(self,fmt='image',slot='main'):
        options=dict(instagram=dict(format=fmt,asset_ids=self.ids if fmt=='carousel' else self.ids[:1]))
        plan=self.ledger.create_or_get_delivery(dict(content_id=self.item['id'],revision=self.item['revision'],manifest_hash=self.item['manifest_hash'],connection_id='dept.instagram',publication_purpose='initial',schedule_slot=slot,scheduled_at='2026-11-02T01:00:00+00:00',timezone='UTC',schedule_condition={'kind':'fixed','at':'2026-11-02T01:00:00+00:00'},options=options))
        ctx=PublicationContext(content_id=self.item['id'],content_revision=self.item['revision'],manifest_hash=self.item['manifest_hash'],owner_account_id='dept',destination_account_id='dept',connection_id='dept.instagram',target_id='123',publication_purpose='initial',schedule_slot=slot,options=options,schedule_condition=plan['schedule_condition'],registry_revision=self.registry.revision,policy_revision='fixture-policy',auth_checked_at=NOW,auth_expires_at=NOW+timedelta(hours=2),review_report_hashes=('independent-source-review','independent-numbers-review'),run_id='fixture-run',platform='instagram')
        return plan,ctx,build_instagram_payload(self.item,ctx)
    def record(self,plan,decision='approved'):
        current=self.reviews.get(plan['id'])
        return self.reviews.record(plan['id'],dict(expected_review_revision=current['review_revision'],subject_hash=current['subject_hash'],decision=decision,checks=dict(CHECKS) if decision=='approved' else dict.fromkeys(CHECKS,False),notes='격리 수동 검토 시험'))
    def posts(self):return [row for row in self.http if row[0]=='POST']
    def test_unreviewed_blocks_then_manual_record_allows_full_chain_without_source_mutation(self):
        plan,ctx,payload=self.plan_context();before=self.contents.get(self.item['id'])
        with patch('socket.socket',side_effect=AssertionError('external HTTP forbidden')):
            self.assertFalse(self.reviews.authorize(ctx,payload))
            self.assertEqual(self.service.submit(ctx,payload,self.target)['outcome'],'failed')
            self.assertEqual(self.staged,[]);self.assertEqual(self.posts(),[])
            self.record(plan);self.assertTrue(self.reviews.authorize(ctx,payload))
            result=self.service.submit(ctx,payload,self.target)
        self.assertEqual(result['outcome'],'submitted');self.assertEqual(len(self.staged),1)
        self.assertEqual([urlsplit(row[1]).path for row in self.posts()],['/v26.0/123/media','/v26.0/123/media_publish'])
        self.assertEqual(self.contents.get(self.item['id']),before);self.assertNotIn('https',str(result))
        self.assertEqual(self.staged[0][0]['asset_sha256'],payload['assets'][0]['sha256'])
    def test_review_revoked_inside_write_hook_blocks_stage_and_posts_until_new_manual_approval(self):
        plan,ctx,payload=self.plan_context();self.record(plan)
        self.service.before_write=lambda:self.record(plan,'revoked')
        result=self.service.submit(ctx,payload,self.target)
        self.assertEqual(result['outcome'],'failed');self.assertEqual(self.staged,[]);self.assertEqual(self.posts(),[])
        self.service.before_write=lambda:None
        self.assertEqual(self.service.submit(ctx,payload,self.target)['outcome'],'failed');self.assertEqual(self.posts(),[])
        self.record(plan);self.assertEqual(self.service.submit(ctx,payload,self.target)['outcome'],'submitted')
        self.assertEqual(len(self.staged),1);self.assertEqual(len(self.posts()),2)
    def test_changed_carousel_order_and_professional_permission_do_not_inherit_approval(self):
        plan,ctx,payload=self.plan_context('carousel');self.record(plan)
        reversed_ctx=replace(ctx,options=dict(instagram=dict(format='carousel',asset_ids=list(reversed(self.ids)))))
        reordered=build_instagram_payload(self.item,reversed_ctx)
        self.assertFalse(self.reviews.authorize(reversed_ctx,reordered));self.assertEqual(self.service.submit(reversed_ctx,reordered,self.target)['outcome'],'failed')
        self.identity_authorized=False
        self.assertEqual(self.service.submit(ctx,payload,self.target)['outcome'],'failed');self.assertEqual(self.staged,[]);self.assertEqual(self.posts(),[])
    def test_expired_hosted_receipt_cannot_restage_or_publish_even_with_manual_review(self):
        plan,ctx,payload=self.plan_context();self.record(plan);self.status='IN_PROGRESS'
        result=self.service.submit(ctx,payload,self.target);self.assertEqual(result['outcome'],'failed')
        self.assertEqual(len(self.staged),1);self.assertEqual(len(self.posts()),1)
        self.now=NOW+timedelta(minutes=56);self.status='FINISHED'
        self.assertTrue(self.reviews.authorize(ctx,payload))
        self.assertEqual(self.service.submit(ctx,payload,self.target)['outcome'],'failed')
        self.assertEqual(len(self.staged),1);self.assertEqual(len(self.posts()),1)
