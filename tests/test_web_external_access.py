"""외부 출처·쿠키 정책의 순수 검증. 실제 외부 서버를 열지 않는다."""
from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ax-console' / 'app'))
from web_external_access import ExternalAccessPolicy


class ExternalAccessPolicyTests(unittest.TestCase):
    def test_inert_immutable_exact_configuration(self):
        with patch('socket.getaddrinfo', side_effect=AssertionError('DNS 금지')):
            policy = ExternalAccessPolicy.from_mapping({'public_origin': 'https://console.example.com'})
        self.assertEqual((policy.host, policy.origin), ('console.example.com', 'https://console.example.com'))
        self.assertEqual(policy.public(), {'origin': policy.origin, 'enabled': True})
        self.assertFalse(policy.allow_internal_key)
        with self.assertRaises(FrozenInstanceError):
            policy.public_origin = 'https://other.example.com'
        for value in (None, {}, {'origin': policy.origin}, {'public_origin': policy.origin, 'enabled': True}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ExternalAccessPolicy.from_mapping(value)

    def test_rejects_ambiguous_or_nonpublic_origins(self):
        values = (None, True, '', 'http://console.example.com', 'HTTPS://console.example.com',
            'https://Console.example.com', 'https://console.example.com.', 'https://localhost',
            'https://127.0.0.1', 'https://[::1]', 'https://console.localhost', 'https://console.local',
            'https://console.internal', 'https://console.test', 'https://console.invalid',
            'https://console.example', 'https://console.onion', 'https://console.123',
            'https://console.example.com:443', 'https://console.example.com:8443',
            'https://user@console.example.com', 'https://console.example.com/',
            'https://console.example.com/path', 'https://console.example.com?x=1',
            'https://console.example.com#x', 'https://콘솔.example.com',
            'https://console.example.com\r\nX: y', 'https://console.example.com\x00',
            ' https://console.example.com', 'https://console.example.com%2f',
            'https://console.example.com\\evil', 'https://-console.example.com',
            'https://console..example.com', 'https://' + 'x' * 64 + '.com')
        for value in values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                ExternalAccessPolicy(value)

    def test_exact_host_and_same_https_origin(self):
        policy = ExternalAccessPolicy('https://console.example.com')
        self.assertTrue(policy.accepts_host(policy.host))
        self.assertTrue(policy.accepts_origin(None))
        self.assertTrue(policy.accepts_origin(policy.origin))
        for host in (None, policy.host + ':443', policy.host.upper(), 'localhost', policy.host + '.evil'):
            self.assertFalse(policy.accepts_host(host))
        for origin in ('null', '', 'http://' + policy.host, policy.origin + '/', policy.origin + ':443',
                policy.origin.upper(), 'https://other.example.com', policy.origin + '\r\n'):
            self.assertFalse(policy.accepts_origin(origin))

    def test_cookie_preserves_token_attributes_and_logout(self):
        policy = ExternalAccessPolicy('https://console.example.com')
        for value in ('ax_web_session=opaque-token; Path=/; HttpOnly; SameSite=Strict; Max-Age=2592000',
                'ax_web_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0'):
            self.assertEqual(policy.cookie(value), value + '; Secure')
            self.assertEqual(policy.cookie(value + '; Secure'), value + '; Secure')

    def test_cookie_injection_domain_and_duplicate_attributes_rejected(self):
        policy = ExternalAccessPolicy('https://console.example.com')
        for value in (None, '', 'not-cookie', 'name=secret\r\nInjected: value',
                'name=secret; Domain=example.com', 'name=secret; domain=example.com',
                'name=secret; Path=/; path=/', 'name=secret; Secure; secure',
                'name=secret; HttpOnly=yes', 'name=secret; SameSite=None',
                'name=secret; Path=/other', 'name=secret; Max-Age=x',
                'name=secret', 'name=secret; Path=/; SameSite=Strict; Max-Age=0',
                'name=secret; Path=/; HttpOnly; Max-Age=0',
                'name=secret; Path=/; HttpOnly; SameSite=Strict',
                'name=secret; Unknown=value', 'name=secret,other=value', 'name=토큰'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                policy.cookie(value)
