"""가짜 로그인·임시 비공개 저장소를 이용한 임대 관리 HTTP 시험."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import unittest

from tests import test_web_deliveries as fixture


class MediaLeaseHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.DeliveryHTTPTests.setUpClass.__func__(cls)

    setUp = fixture.DeliveryHTTPTests.setUp
    stop = fixture.DeliveryHTTPTests.stop
    request = fixture.DeliveryHTTPTests.request

    def issue(self, *, destination='dept', owner='personal', position=0, expired=False):
        store = self.server.media_lease_store
        store.initialize()
        raw = b'\xff\xd8\xfffixture-private-image\xff\xd9'
        now = datetime.now(timezone.utc)
        if expired:
            now -= timedelta(hours=2)
        request = dict(context_hash='a'*64, owner_account_id=owner, destination_account_id=destination,
                       connection_id=destination+'.instagram', target_id='12345', content_id='content-fixture',
                       content_revision=1, manifest_hash='b'*64, position=position, asset_id='asset-fixture',
                       asset_sha256=hashlib.sha256(raw).hexdigest(), asset_size=len(raw), media_type='image/jpeg')
        return store.issue(request=request, raw=raw, now=now, expires_at=now+timedelta(hours=1),
                           authority={'context': {'secret': 'private-authority'}, 'prepared': {'caption': '숨겨진 캡션'}})

    def assert_safe(self, response, *receipts):
        serialized = json.dumps(response, ensure_ascii=False)
        for receipt in receipts:
            self.assertNotIn(receipt['token'], serialized)
        for secret in ('https://', 'http://', 'token', 'receipt_id', 'authority', 'context_hash', 'private-authority',
                       '숨겨진 캡션', str(self.workspace)):
            self.assertNotIn(secret, serialized)

    def test_auth_readonly_and_query_contract(self):
        path = '/api/v2/media-leases'
        self.assertEqual(self.request(path+'?account=personal', authed=False)[0], 401)
        self.assertFalse(self.workspace.exists())
        self.assertEqual(self.request(path+'?account=personal'), (200, {'account_id':'personal', 'items':[]}))
        self.assertFalse(self.workspace.exists())
        for query in ('', '?account=other', '?account=personal&account=dept', '?account=personal&token=secret', '?account='):
            with self.subTest(query=query):
                self.assertEqual(self.request(path+query)[0], 400)
        self.assertFalse(self.workspace.exists())
        self.assertEqual(self.request(path+'?account=personal', 'POST', {})[0], 405)
        self.assertEqual(self.request(path+'/'+'a'*64+'/revoke')[0], 405)

    def test_revoke_origin_body_scope_and_status(self):
        receipt = self.issue()
        path = '/api/v2/media-leases/'+receipt['lease_id']+'/revoke'
        body = {'account_id':'dept'}
        self.assertEqual(self.request(path, 'POST', body, authed=False)[0], 401)
        self.assertEqual(self.request(path, 'POST', body, extra_headers={'Origin':'https://evil.example'})[0], 403)
        self.assertEqual(self.request(path, 'POST', {'account_id':'personal'})[0], 404)
        for invalid in ({}, {'account_id':'dept', 'token':receipt['token']}, {'account_id':'other'}, []):
            with self.subTest(body=invalid):
                self.assertEqual(self.request(path, 'POST', invalid)[0], 400)
        self.assertEqual(self.request(path+'?account=dept', 'POST', body)[0], 400)
        self.assertEqual(self.request('/api/v2/media-leases/'+'0'*64+'/revoke', 'POST', body)[0], 404)
        self.assertEqual(self.request(path, 'PUT', body)[0], 405)
        status, response = self.request('/api/v2/media-leases?account=dept')
        self.assertEqual(status, 200)
        self.assertEqual(response['items'][0]['status'], 'active')
        self.assertEqual(response['items'][0]['owner_account_id'], 'personal')
        self.assertEqual(response['items'][0]['destination_account_id'], 'dept')
        self.assert_safe(response, receipt)
        status, response = self.request(path, 'POST', body)
        self.assertEqual(status, 200)
        self.assertEqual(response['items'][0]['status'], 'revoked')
        self.assert_safe(response, receipt)
        self.assertIsNone(self.server.media_lease_store.lookup(receipt['token'], now=datetime.now(timezone.utc)))
        self.assertEqual(self.request('/api/v2/media-leases?account=personal')[1]['items'], [])

    def test_expired_and_purged_statuses_retain_safe_tombstones(self):
        expired = self.issue(expired=True)
        active = self.issue(position=1)
        status, response = self.request('/api/v2/media-leases?account=dept')
        self.assertEqual(status, 200)
        self.assertEqual({row['status'] for row in response['items']}, {'active', 'expired'})
        self.assert_safe(response, expired, active)
        self.server.media_lease_store.purge(now=datetime.now(timezone.utc))
        status, response = self.request('/api/v2/media-leases?account=dept')
        self.assertEqual(status, 200)
        self.assertEqual({row['status'] for row in response['items']}, {'active', 'purged'})
        self.assert_safe(response, expired, active)
