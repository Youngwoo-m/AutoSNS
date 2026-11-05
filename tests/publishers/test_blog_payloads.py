"""순수 블로그 변환과 원격 근거 경계: 외부 서비스 없이 검사한다."""
import copy
import hashlib
import importlib
import os
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from common.operations.runtime_models import PublicationContext


NOW = datetime(2026, 10, 31, tzinfo=timezone.utc)


def context(platform='blogger', **changes):
    values = dict(content_id='content', content_revision=1, manifest_hash='manifest',
                  owner_account_id='personal', destination_account_id='dept',
                  connection_id='dept.' + platform, target_id='target',
                  publication_purpose='initial', schedule_slot='initial', options={},
                  schedule_condition={}, registry_revision='registry', policy_revision='policy',
                  auth_checked_at=NOW, auth_expires_at='2026-11-01T00:00:00Z',
                  review_report_hashes=('review',), platform=platform)
    values.update(changes)
    return PublicationContext(**values)


def snapshot():
    return dict(id='content', revision=1, manifest_hash='manifest', title='안전 <확인>',
                original='원본', variants=[dict(destination_account_id='dept', platform='blogger', text='배포 본문')],
                sources=[dict(url='https://example.org/근거?q=1&v=2', note='기사 <근거>')],
                assets=[dict(id='asset', sha256='a' * 64, path='unopened.png')])


class BlogPayloadTests(unittest.TestCase):
    def build(self, platform, data, ctx):
        self.assertIsNotNone(importlib.util.find_spec('common.publishers.blog_payloads'), '순수 payload 모듈이 필요합니다')
        module = importlib.import_module('common.publishers.blog_payloads')
        return module.build_blog_payload(platform, data, ctx)

    def observe(self, platform, raw, **ctx):
        self.assertIsNotNone(importlib.util.find_spec('common.publishers.blog_observations'), '원격 관측 모듈이 필요합니다')
        module = importlib.import_module('common.publishers.blog_observations')
        return module.normalize_blog_observation(platform, raw, context=ctx, checked_at=NOW)

    def test_transform_preserves_approved_variant_sources_category_and_ai_notice(self):
        data = snapshot()
        before = copy.deepcopy(data)
        for platform in ('blogger', 'naver', 'tistory'):
            with self.subTest(platform=platform):
                ctx = context(platform, options={'category': '필수분류', 'ai_notice': 'AI 활용 고지', 'tags': ['안전']})
                result = self.build(platform, data, ctx)
                self.assertEqual(result['body_text'], '배포 본문' if platform == 'blogger' else '원본')
                self.assertEqual(result['sources'], data['sources'])
                self.assertEqual(result['category'], '필수분류')
                self.assertEqual(result['ai_notice'], 'AI 활용 고지')
                self.assertIn('https://example.org/%EA%B7%BC%EA%B1%B0?q=1&amp;v=2', result['body_html'])
                self.assertIn('기사 &lt;근거&gt;', result['body_html'])
                self.assertIn('AI 활용 고지', result['body_html'])
                self.assertEqual(result['owner_account_id'], 'personal')
                self.assertEqual(result['destination_account_id'], 'dept')
                self.assertEqual(result['target_id'], 'target')
                result['assets'][0]['id'] = 'changed'
        self.assertEqual(data, before)

    def test_pure_module_import_has_no_filesystem_network_or_environment_effect(self):
        modules = [importlib.import_module('common.publishers.' + name)
                   for name in ('blog_payloads', 'blog_observations')]
        environment, path = dict(os.environ), list(sys.path)
        with patch('builtins.open', side_effect=AssertionError('파일 접근 금지')), \
             patch('os.makedirs', side_effect=AssertionError('디렉터리 생성 금지')), \
             patch('socket.socket', side_effect=AssertionError('네트워크 금지')):
            for module in modules:
                importlib.reload(module)
        self.assertEqual(dict(os.environ), environment)
        self.assertEqual(sys.path, path)

    def test_blogger_category_survives_label_count_and_utf8_limits(self):
        result = self.build('blogger', snapshot(), context(options={
            'category': '필수분류', 'tags': ['긴태그' * 15 + str(i) for i in range(30)],
            'local_tags': ['제천']}))
        self.assertIn('필수분류', result['labels'])
        self.assertIn('제천', result['labels'])
        self.assertLessEqual(len(result['labels']), 15)
        self.assertLessEqual(len(','.join(result['labels']).encode()), 200)
        with self.assertRaises(ValueError):
            self.build('blogger', snapshot(), context(options={'category': '필수분류' * 30}))

    def test_dept_blogger_keeps_existing_six_label_default(self):
        result = self.build('blogger', snapshot(), context(options={'category': '분류', 'tags': ['tag' + str(i) for i in range(20)]}))
        self.assertLessEqual(len(result['labels']), 6)

    def test_prepare_does_not_read_assets_or_load_legacy_or_external_services(self):
        with patch('builtins.open', side_effect=AssertionError('파일 읽기 금지')), \
             patch('socket.socket', side_effect=AssertionError('네트워크 금지')):
            result = self.build('blogger', snapshot(), context())
        self.assertEqual(result['assets'][0]['path'], 'unopened.png')
        self.assertEqual(result['body_sha256'], hashlib.sha256('배포 본문'.encode()).hexdigest())

    def test_changed_snapshot_ambiguous_variant_and_platform_are_rejected(self):
        for change in ({'revision': 2}, {'manifest_hash': 'changed'},
                       {'variants': snapshot()['variants'] * 2}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.build('blogger', {**snapshot(), **change}, context())
        with self.assertRaises(ValueError):
            self.build('blogger', snapshot(), context('naver'))
        with self.assertRaises(ValueError):
            self.build('unknown', snapshot(), context('unknown'))

    def test_html_is_escaped_unless_approved_format_is_explicit(self):
        data = {**snapshot(), 'original': '<p>검토 본문</p>', 'variants': []}
        self.assertIn('&lt;p&gt;', self.build('blogger', data, context())['body_html'])
        result = self.build('blogger', data, context(options={'body_format': 'html'}))
        self.assertTrue(result['body_html'].startswith('<p>검토 본문</p>'))
        self.assertEqual(result['body_text'], '<p>검토 본문</p>')

    def test_absent_remote_body_media_and_target_cannot_borrow_local_evidence(self):
        raw = {'id': 'post', 'title': '같은 제목', 'body_sha256': 'pretend', 'media_sha256': ['pretend']}
        result = self.observe('blogger', raw, target_id='local-target',
                              destination_account_id='dept', body_sha256='local', assets=[])
        self.assertIsNone(result['target_id'])
        self.assertIsNone(result['body_sha256'])
        self.assertIsNone(result['media_sha256'])
        self.assertEqual(result['visibility'], 'unknown')
        self.assertEqual(result['remote_id'], 'post')

    def test_remote_body_change_changes_observation_hash(self):
        raw = dict(id='post', blog={'id': 'remote-target'}, content='<p>원격 본문</p>',
                   published='2026-10-31T00:00:00Z', status='LIVE', publicly_readable=True, images=[])
        original = self.observe('blogger', raw, destination_account_id='dept')
        changed = self.observe('blogger', {**raw, 'content': '<p>변경 본문</p>'}, destination_account_id='dept')
        self.assertEqual(original['body_sha256'], hashlib.sha256('<p>원격 본문</p>'.encode()).hexdigest())
        self.assertNotEqual(original['body_sha256'], changed['body_sha256'])
        self.assertEqual(original['body_format'], 'html')
        self.assertEqual(original['target_id'], 'remote-target')
        self.assertEqual(original['visibility'], 'public')
        self.assertEqual(original['media_sha256'], [])
        self.assertEqual(original['checked_at'], NOW.isoformat())

    def test_remote_media_require_downloaded_bytes_and_never_hash_urls(self):
        for raw in ({'content': '<p><img src="https://example.org/a.png"></p>', 'images': []},
                    {'body_text': '본문', 'media': [{'url': 'https://example.org/a.png', 'sha256': 'local'}]}):
            with self.subTest(raw=raw):
                self.assertIsNone(self.observe('blogger', raw)['media_sha256'])
        result = self.observe('naver', {'remote_id': 'post', 'target_id': 'remote',
                                      'body_text': '본문', 'media': [{'content_bytes': b'remote-image'}],
                                      'visibility': 'private'})
        self.assertEqual(result['media_sha256'], [hashlib.sha256(b'remote-image').hexdigest()])
        self.assertEqual(result['visibility'], 'private')

    def test_live_status_of_private_blog_does_not_prove_public_access(self):
        result = self.observe('blogger', {'id': 'post', 'status': 'LIVE'})
        self.assertEqual(result['visibility'], 'unknown')

    def test_title_url_or_timestamp_never_establish_public_visibility(self):
        for platform in ('blogger', 'naver', 'tistory'):
            with self.subTest(platform=platform):
                result = self.observe(platform, {'id': 'post', 'url': 'https://example.org/post',
                                                'published': NOW.isoformat()})
                self.assertEqual(result['visibility'], 'unknown')


if __name__ == '__main__':
    unittest.main()
