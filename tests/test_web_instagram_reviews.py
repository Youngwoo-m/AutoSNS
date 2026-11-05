"""가짜 쿠키·임시 저장소·localhost만 사용하는 구성 검토 HTTP 시험."""
from dataclasses import replace
import http.client
import json
from pathlib import Path
import unittest
from tests import test_web_deliveries as fixture

class InstagramReviewHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.DeliveryHTTPTests.setUpClass.__func__(cls)
    setUp=fixture.DeliveryHTTPTests.setUp
    stop=fixture.DeliveryHTTPTests.stop
    request=fixture.DeliveryHTTPTests.request

    def plan(self,target='123'):
        store=self.server.content_store;store.initialize();self.server.ledger.initialize()
        base=self.server.ledger.registry()
        connection=replace(base.connections['personal.youtube'],id='personal.instagram',platform='instagram',
            target_id=target,capabilities=('plan','visibility:public'),enabled=False)
        self.server.ledger.registry_source=replace(base,connections={**base.connections,connection.id:connection})
        content=store.create('personal',{'title':'최종 구성','kind':'article','original':'사람이 검토할 캡션'})
        content=store.add_asset(content['id'],content['revision'],'image.jpg','image/jpeg',b'\xff\xd8\xfffixture\xff\xd9')
        body=dict(content_id=content['id'],revision=content['revision'],manifest_hash=content['manifest_hash'],
            connection_id=connection.id,publication_purpose='initial',schedule_slot='review-test',
            scheduled_at='2026-11-02T10:00:00+09:00',timezone='Asia/Seoul',
            options={'instagram':{'format':'image','asset_ids':[content['assets'][0]['id']]}})
        status,plan=self.request('/api/v2/deliveries','POST',body);self.assertEqual(status,200,plan)
        self.assertEqual(plan['target_id'],target);self.assertFalse(plan['execution_enabled'])
        return content,plan,'/api/v2/deliveries/'+plan['id']+'/instagram-review'

    def test_auth_readonly_no_initialization_and_strict_http_boundary(self):
        path='/api/v2/deliveries/delivery_'+'a'*32+'/instagram-review'
        self.assertEqual(self.request(path,authed=False)[0],401)
        self.assertEqual(self.request(path)[0],404);self.assertFalse(self.workspace.exists())
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        try:
            connection.request('GET','/web/instagram_review_panel.js',headers={'Cookie':'fixture'})
            response=connection.getresponse();self.assertEqual(response.status,200)
            self.assertIn('javascript',response.getheader('Content-Type'));self.assertIn(b'createInstagramReviewPanel',response.read())
        finally:connection.close()
        self.assertFalse(self.workspace.exists())
        content,plan,path=self.plan()
        status,row=self.request(path);self.assertEqual(status,200,row)
        self.assertEqual(row['status'],'not_reviewed')
        self.assertFalse((self.workspace/'instagram-reviews.sqlite3').exists())
        self.assertEqual(self.request(path+'?actor=other')[0],400)
        self.assertEqual(self.request(path,'PUT',{})[0],405)
        body=dict(expected_review_revision=0,subject_hash=row['subject_hash'],decision='approved',
            checks={key:key!='audio_checked' for key in row['checks']},notes='원고와 순서를 직접 확인')
        self.assertEqual(self.request(path,'POST',body)[0],503)
        self.server.instagram_review_store.initialize()
        self.assertEqual(self.request(path,'POST',{**body,'owner_account_id':'dept'})[0],400)
        self.assertEqual(self.request(path,'POST',body,extra_headers={'Origin':'https://evil.example'})[0],403)
        status,saved=self.request(path,'POST',body);self.assertEqual(status,200,saved)
        self.assertEqual(saved['status'],'approved');self.assertNotIn('actor',saved)
        self.assertEqual(self.request(path,'POST',body)[0],409)
        self.assertEqual(self.server.content_store.get(content['id']),content)
        revoked={**body,'expected_review_revision':saved['review_revision'],'decision':'revoked'}
        self.assertEqual(self.request(path,'POST',revoked)[1]['status'],'revoked')

    def test_unverified_target_and_changed_content_never_reuse_old_review(self):
        content,plan,path=self.plan(target=None)
        self.assertEqual(self.request(path)[0],409)
        base=self.server.ledger.registry();old=base.connections['personal.instagram']
        self.server.ledger.registry_source=replace(base,connections={**base.connections,old.id:replace(old,target_id='123')})
        status,row=self.request(path);self.assertEqual(status,200,row)
        self.server.instagram_review_store.initialize()
        body=dict(expected_review_revision=0,subject_hash=row['subject_hash'],decision='approved',
            checks={key:key!='audio_checked' for key in row['checks']},notes='확인')
        self.server.content_store.update(content['id'],content['revision'],{'title':content['title'],'kind':content['kind'],'original':'검토 후 변경된 원고'})
        self.assertEqual(self.request(path,'POST',body)[0],409)
