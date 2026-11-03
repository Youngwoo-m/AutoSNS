"""실제 저장된 X 계획의 비활성 경계. 임시 원장·가짜 세션만 사용한다."""
import unittest
from tests import test_web_deliveries as fixture


class XPlansHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.DeliveryHTTPTests.setUpClass.__func__(cls)
    setUp=fixture.DeliveryHTTPTests.setUp
    stop=fixture.DeliveryHTTPTests.stop
    request=fixture.DeliveryHTTPTests.request

    def content_body(self):
        store=self.server.content_store;store.initialize();self.server.ledger.initialize()
        content=store.create('dept',dict(title='X 계획 원고',kind='card',original='원본 캡션 그대로',
            variants=[dict(destination_account_id='dept',platform='x',text='X 전용 원문 https://source.example.com/?keep=1')]))
        content=store.add_asset(content['id'],content['revision'],'card.png','image/png',b'\x89PNG\r\n\x1a\nfixture')
        body=dict(content_id=content['id'],revision=content['revision'],manifest_hash=content['manifest_hash'],
            connection_id='dept.x',publication_purpose='initial',schedule_slot='x-plan',
            scheduled_at='2026-11-04T10:00:00+09:00',timezone='Asia/Seoul',options={'text_only':True})
        return content,body

    def test_registered_dept_x_capability_stays_unverified_and_disabled(self):
        status,response=self.request('/api/v2/connections')
        self.assertEqual(status,200)
        connections={item['id']:item for item in response['items']}
        self.assertIn('dept.x',connections)
        self.assertNotIn('personal.x',connections)
        row=connections['dept.x']
        self.assertIn('text_only',row['capabilities'])
        self.assertEqual(row['target_status'],'unverified')
        self.assertFalse(row['execution_enabled'])
        registered=self.server.ledger.registry().connections['dept.x']
        self.assertIsNone(registered.target_id)
        self.assertFalse(registered.enabled)

    def test_saved_text_only_plan_preserves_source_and_cannot_approve_unknown_target(self):
        content,body=self.content_body()
        status,plan=self.request('/api/v2/deliveries','POST',body)
        self.assertEqual(status,200,plan)
        self.assertEqual(plan['options'],{'text_only':True})
        self.assertEqual(plan['target_status'],'unverified')
        self.assertFalse(plan['execution_enabled'])
        self.assertEqual(plan['owner_account_id'],'dept')
        self.assertEqual(plan['destination_account_id'],'dept')
        self.assertEqual(self.server.content_store.get(content['id']),content)
        url='/api/v2/deliveries/'+plan['id']
        self.assertEqual(self.request(url)[1],plan)
        approval=dict(expected_version=plan['version'],subject_hash=plan['subject_hash'],decision='approved',notes='계획 검토')
        self.assertEqual(self.request(url+'/approvals','POST',approval)[0],409)
        self.assertEqual(self.request(url)[1]['status'],'pending')
        self.assertEqual(self.request('/api/v2/deliveries?account=dept')[1]['items'][0]['id'],plan['id'])
        self.assertEqual(self.request('/api/v2/deliveries?account=personal')[1]['items'],[])

    def test_explicit_option_types_impersonation_and_http_auth_boundaries(self):
        content,body=self.content_body()
        for option in (False,0,1,'true',None):
            with self.subTest(option=option):
                self.assertEqual(self.request('/api/v2/deliveries','POST',{**body,'options':{'text_only':option}})[0],400)
        for field,value in (('owner_account_id','personal'),('destination_account_id','personal'),
                ('execution_enabled',True),('actor','admin')):
            self.assertEqual(self.request('/api/v2/deliveries','POST',{**body,field:value})[0],400)
        self.assertEqual(self.request('/api/v2/deliveries','POST',body,authed=False)[0],401)
        self.assertEqual(self.request('/api/v2/connections',authed=False)[0],401)
        self.assertEqual(self.request('/api/v2/deliveries','POST',body,
            extra_headers={'Origin':'https://evil.example.com'})[0],403)
        self.assertEqual(self.request('/api/v2/deliveries')[1]['items'],[])
        self.assertEqual(self.server.content_store.get(content['id']),content)

    def test_missing_text_only_option_is_not_automatically_selected(self):
        content,body=self.content_body()
        status,plan=self.request('/api/v2/deliveries','POST',{**body,'options':{}})
        self.assertEqual(status,200,plan)
        self.assertEqual(plan['options'],{})
        self.assertFalse(plan['execution_enabled'])
        self.assertEqual(self.server.content_store.get(content['id']),content)
