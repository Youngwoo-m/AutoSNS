"""읽기 전용 원본과 명시적인 성과 가져오기 경계 회귀시험."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from common.operations.legacy_metrics import load_legacy_metrics, build_import_plan, import_snapshot
from common.operations.metrics_store import MetricsStore
from common.operations.content_store import StoreError, ConflictError
from common.operations.models import Connection, Registry


class LegacyMetricsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'source'
        self.parts = self.root / 'common/analytics/snapshots/parts'
        self.parts.mkdir(parents=True)
        self.registry = Registry('r1', {'personal': {}, 'dept': {}}, {}, {}, {
            'personal-tistory': Connection('personal-tistory', 'personal', 'tistory', target_id='https://mine.tistory.com'),
            'dept-instagram': Connection('dept-instagram', 'dept', 'instagram', target_id='178900'),
            'dept-youtube': Connection('dept-youtube', 'dept', 'youtube', target_id='@dept'),
        }, {}, {}, {})
        self.fixtures = {
            'blog': {'items': [{'title': '옛 글', 'url': 'https://mine.tistory.com/7?token=SECRET', 'views': 0, 'likes': 2, 'status': 'done'}], 'views_at': '2020-01-01T09:00:00+09:00'},
            'blogger': {'blog': {'title': '학과', 'url': 'https://other.blogspot.com/'}, 'items': [{'title': '이름으로 추정 금지', 'url': 'https://other.blogspot.com/2020/post.html'}]},
            'instagram': {'profile': {'username': 'dept', 'uid': '178900', 'followers': 100, 'posts': 4, 'token': 'SECRET'}, 'items': [{'url': 'https://instagram.com/p/ABC', 'views': 0}]},
            'threads': {'profile': {'username': 'dept', 'url': 'https://threads.net/@dept'}, 'items': [{'url': 'https://threads.net/@dept/post/xyz', 'views': 9}]},
            'x': {'account': {'username': 'personal'}, 'items': [{'url': 'https://x.com/unknown/status/12', 'state': 'running'}]},
            'youtube': {'channel': {'title': '채널', 'handle': '@dept', 'subscribers': 20, 'total_views': 300}, 'items': [{'id': 'v7', 'url': 'https://youtube.com/watch?v=v7', 'views': 3}]},
            'smds': {'items': [{'title': '관리실적 아님', 'url': 'https://unregistered.example/a', 'pages': 3}]},
            'searchconsole': {'sites': ['https://mine.tistory.com'], 'period': {'start': '2020-01-01', 'end': '2020-01-30'}, 'items': [{'site': 'https://mine.tistory.com', 'query': '질문', 'clicks': 0, 'impressions': 2}], 'pages': [{'site': 'https://mine.tistory.com', 'page': 'https://mine.tistory.com/7', 'clicks': 2}], 'per_site': [{'site': 'https://mine.tistory.com', 'clicks': 2}], 'totals': {'clicks': 2}},
            'indexing': {'per_site': [{'site': 'https://mine.tistory.com', '검사': 5, '색인확인': 2, '미색인': 3}], 'pending': [{'site': 'https://mine.tistory.com', 'url': 'https://mine.tistory.com/8', 'verdict': 'unknown'}], 'indexed_total': 2},
        }
        for kind, data in self.fixtures.items():
            self.write(kind, data)

    def write(self, kind, data):
        (self.parts / (kind + '.json')).write_text(json.dumps(data, ensure_ascii=True))

    def plan(self):
        return build_import_plan(load_legacy_metrics(self.root, self.registry), self.registry)

    def test_nine_formats_keep_zero_provenance_and_nullable_times(self):
        plan = self.plan()
        self.assertEqual(9, len(plan['files']))
        self.assertEqual(set(self.fixtures), {f['kind'] for f in plan['files']})
        rows = [e['observation'] for e in plan['observations']]
        self.assertGreater(len(rows), 9)
        blog = next(r for r in rows if r['title'] == '옛 글')
        self.assertEqual(0, blog['values']['views'])
        self.assertEqual('2020-01-01T00:00:00+00:00', blog['observed_at'])
        self.assertIsNone(blog['collected_at'])
        self.assertEqual('legacy_reported', blog['status'])
        self.assertEqual('personal', blog['destination_account_id'])
        self.assertIsNone(blog['owner_account_id'])
        self.assertIn('owner_unknown', blog['uncertainties'])
        self.assertTrue(all(r['delivery_id'] is None and r['content_id'] is None for r in rows))
        self.assertTrue(all(r['basis'] == 'unknown' and r['period'] is None for r in rows))
        public = json.dumps(plan, ensure_ascii=False)
        self.assertNotIn('SECRET', public)
        self.assertNotIn('?token', public)
        self.assertNotIn(str(self.root), public)
        self.assertTrue(all(set(r['source']) <= {'path', 'kind', 'label', 'note', 'section', 'row_key'} for r in rows))

    def test_mtime_is_not_observed_or_collection_time(self):
        f = self.parts / 'youtube.json'
        os.utime(f, (1900000000, 1900000000))
        row = next(e['observation'] for e in self.plan()['observations'] if e['observation']['remote_id'] == 'v7')
        self.assertIsNone(row['observed_at'])
        self.assertIsNone(row['collected_at'])
        self.assertIsNotNone(row['file_mtime'])

    def test_unregistered_host_title_and_account_cannot_assign_owner(self):
        data = {'items': [{'title': '개인 mine', 'date': '2020-01-01', 'account_id': 'personal', 'target_id': 'https://mine.tistory.com', 'url': 'https://mine.tistory.com.evil.example/7', 'views': 3}, {'title': '개인', 'views': 2}]}
        self.write('blog', data)
        rows = [e['observation'] for e in self.plan()['observations'] if e['observation']['source']['kind'] == 'blog']
        self.assertEqual(2, len(rows))
        self.assertTrue(all(r['owner_account_id'] is None and r['destination_account_id'] is None for r in rows))

    def test_naver_blog_canonical_and_legacy_alias_match_registered_blog_ids(self):
        for registered_platform in ('naver_blog', 'naver'):
            with self.subTest(platform=registered_platform):
                registry = Registry('naver-fixture', {'personal': {}, 'dept': {}}, {}, {}, {
                    'dept-naver': Connection('dept-naver', 'dept', registered_platform, target_id='studs23'),
                    'personal-naver': Connection('personal-naver', 'personal', registered_platform, target_id='safeworking'),
                }, {}, {}, {})
                data = {'items': [
                    {'url': 'https://blog.naver.com/studs23/123', 'views': 0},
                    {'url': 'https://m.blog.naver.com/safeworking/456', 'views': 3}]}
                plan = self.synthetic_plan('blog', data, registry)
                rows = [e['observation'] for e in plan['observations']]
                self.assertEqual(['dept', 'personal'], [r['destination_account_id'] for r in rows])
                self.assertEqual(['dept-naver', 'personal-naver'], [r['connection_id'] for r in rows])
                self.assertEqual(['studs23', 'safeworking'], [r['target_id'] for r in rows])
                self.assertTrue(all(r['platform'] == 'naver_blog' for r in rows))
                self.assertTrue(all(r['owner_account_id'] is None for r in rows))
                self.assertEqual(0, plan['counts']['unassigned'])

    def test_naver_blog_wrong_account_target_and_lookalike_host_stay_unassigned(self):
        registry = Registry('naver-fixture', {'personal': {}, 'dept': {}}, {}, {}, {
            'dept-naver': Connection('dept-naver', 'dept', 'naver_blog', target_id='studs23'),
            'personal-naver': Connection('personal-naver', 'personal', 'naver_blog', target_id='safeworking'),
        }, {}, {}, {})
        data = {'items': [
            {'url': 'https://blog.naver.com/studs23/1', 'connection_id': 'personal-naver', 'target_id': 'safeworking', 'views': 1},
            {'url': 'https://blog.naver.com/safeworking/2', 'connection_id': 'dept-naver', 'target_id': 'studs23', 'views': 1},
            {'url': 'https://blog.naver.com/unregistered/3', 'account_id': 'personal', 'views': 1},
            {'url': 'https://blog.naver.com.evil.example/studs23/4', 'target_id': 'studs23', 'views': 1}]}
        rows = [e['observation'] for e in self.synthetic_plan('blog', data, registry)['observations']]
        self.assertEqual(4, len(rows))
        self.assertTrue(all(r['destination_account_id'] is None and r['connection_id'] is None for r in rows))
        self.assertTrue(all(r['owner_account_id'] is None for r in rows))

    def test_running_is_recovery_pending_and_done_never_verified(self):
        rows = [e['observation'] for e in self.plan()['observations']]
        self.assertTrue(all(r['source_kind'] == 'legacy_reported' for r in rows))
        running = next(r for r in rows if r['source']['kind'] == 'x')
        self.assertIn('recovery_pending', running['uncertainties'])

    def test_missing_corrupt_oversized_and_symlink_files_are_isolated(self):
        (self.parts / 'blog.json').unlink()
        (self.parts / 'blogger.json').write_text('{bad')
        (self.parts / 'threads.json').write_bytes(b' ' * 10000)
        (self.parts / 'x.json').unlink()
        (self.parts / 'x.json').symlink_to(self.parts / 'youtube.json')
        snapshot = load_legacy_metrics(self.root, self.registry, max_file_bytes=9000)
        states = {f['kind']: f['status'] for f in snapshot['files']}
        self.assertEqual('missing', states['blog'])
        self.assertEqual('corrupt', states['blogger'])
        self.assertEqual('too_large', states['threads'])
        self.assertEqual('unsafe', states['x'])
        self.assertGreaterEqual(build_import_plan(snapshot, self.registry)['counts']['errors'], 3)

    def test_all_nine_malformed_shapes_and_error_unsupported_preserved(self):
        for kind in self.fixtures:
            with self.subTest(kind=kind):
                original = copy.deepcopy(self.fixtures[kind])
                self.write(kind, {'items': 'bad'} if kind not in ('indexing',) else {'per_site': 'bad'})
                snap = load_legacy_metrics(self.root, self.registry)
                self.assertEqual('invalid_shape', next(f for f in snap['files'] if f['kind'] == kind)['status'])
                self.write(kind, original)
        self.write('youtube', {'status': 'unsupported', 'items': []})
        self.write('blog', {'error': 'SECRET', 'items': []})
        rows = [e['observation'] for e in self.plan()['observations']]
        self.assertEqual({'error', 'unsupported'}, {r['status'] for r in rows if r['source']['kind'] in ('youtube', 'blog')})
        self.assertTrue(all(r['values'] == {} for r in rows if r['status'] in ('error', 'unsupported')))
        self.assertNotIn('SECRET', json.dumps(self.plan()))

    def test_duplicate_rows_and_repeated_import_keep_ids_and_account_isolation(self):
        self.fixtures['blog']['items'] *= 2
        self.write('blog', self.fixtures['blog'])
        plan = self.plan()
        self.assertEqual(plan, self.plan())
        store = MetricsStore(Path(self.tmp.name) / 'managed')
        store.initialize()
        first = import_snapshot(store, plan)
        rows = store.list_observations()
        second = import_snapshot(store, self.plan())
        self.assertEqual(first['imported'], len(rows))
        self.assertEqual(0, second['imported'])
        self.assertEqual(len(rows), second['unchanged'])
        self.assertEqual(rows, store.list_observations())
        self.assertTrue(all('personal' in (r['owner_account_id'], r['destination_account_id']) for r in store.list_observations('personal')))
        self.assertTrue(all('dept' in (r['owner_account_id'], r['destination_account_id']) for r in store.list_observations('dept')))
        self.assertFalse((Path(self.tmp.name) / 'managed' / 'runtime.sqlite3').exists())

    def test_conflicting_container_identity_cannot_override_post_host_or_handle(self):
        registry = Registry('r2', {'personal': {}, 'dept': {}}, {}, {}, {
            'x-personal': Connection('x-personal', 'personal', 'x', target_id='personal'),
            'blogger-personal': Connection('blogger-personal', 'personal', 'blogger', target_id='https://mine.blogspot.com'),
        }, {}, {}, {})
        self.write('x', {'account': {'username': 'personal'}, 'items': [{'url': 'https://x.com/other/status/3', 'views': 2}]})
        self.write('blogger', {'blog': {'url': 'https://mine.blogspot.com'}, 'items': [{'url': 'https://other.blogspot.com/a.html'}]})
        plan = build_import_plan(load_legacy_metrics(self.root, registry), registry)
        rows = [e['observation'] for e in plan['observations'] if e['observation']['platform'] in ('x', 'blogger')]
        self.assertTrue(rows)
        self.assertTrue(all(r['destination_account_id'] is None for r in rows))

    def test_identical_titles_metrics_on_distinct_urls_are_distinct_observations(self):
        self.write('blogger', {'blog': {'url': 'https://other.blogspot.com'}, 'items': [
            {'title': '동일 제목', 'url': 'https://other.blogspot.com/a.html'},
            {'title': '동일 제목', 'url': 'https://other.blogspot.com/b.html'}]})
        rows = [e for e in self.plan()['observations'] if e['observation']['source']['kind'] == 'blogger']
        self.assertEqual(2, len(rows))
        self.assertNotEqual(rows[0]['observation_key'], rows[1]['observation_key'])

    def synthetic_plan(self, kind, data, registry=None):
        snapshot = {'files': [{'path': f'common/analytics/snapshots/parts/{kind}.json',
            'kind': kind, 'label': kind, 'status': 'ok', 'digest': 'synthetic',
            'file_mtime': None, 'row_count': len(data.get('items', [])),
            'missing_rows': 0, 'unsupported': False, 'note': '합성 시험'}],
            'parts': {kind: data}}
        return build_import_plan(snapshot, registry)

    def test_search_query_dimensions_survive_normalization_and_true_duplicates_collapse(self):
        first = {'site': 'https://site.example', 'query': '측량', 'clicks': 1, 'impressions': 5}
        second = dict(first, query='토목')
        data = {'items': [first, second, dict(first)]}
        plan = self.synthetic_plan('searchconsole', data)
        self.assertEqual(2, len(plan['observations']))
        self.assertEqual(2, len({e['observation_key'] for e in plan['observations']}))
        self.assertEqual(2, len({e['observation']['source']['row_key'] for e in plan['observations']}))
        self.assertEqual(plan, self.synthetic_plan('searchconsole', copy.deepcopy(data)))
        public = json.dumps(plan, ensure_ascii=False)
        self.assertNotIn('측량', public)
        self.assertNotIn('토목', public)

    def test_search_site_page_dimensions_keep_equal_metric_rows_separate(self):
        data = {'pages': [
            {'site': 'https://one.example', 'page': 'https://one.example/a', 'clicks': 1},
            {'site': 'https://one.example', 'page': 'https://one.example/b', 'clicks': 1},
            {'site': 'https://two.example', 'page': 'https://one.example/a', 'clicks': 1}]}
        plan = self.synthetic_plan('searchconsole', data)
        self.assertEqual(3, len(plan['observations']))
        self.assertEqual(3, len({e['observation_key'] for e in plan['observations']}))

    def test_query_based_search_pages_keep_positions_while_identical_static_rows_deduplicate(self):
        data = {'pages': [
            {'site': 'https://site.example', 'page': 'https://site.example/article?p=1&token=SECRET', 'clicks': 1},
            {'site': 'https://site.example', 'page': 'https://site.example/article?p=2&token=SECRET', 'clicks': 1},
            {'site': 'https://site.example', 'page': 'https://site.example/static', 'clicks': 1},
            {'site': 'https://site.example', 'page': 'https://site.example/static', 'clicks': 1}]}
        plan = self.synthetic_plan('searchconsole', data)
        self.assertEqual(3, len(plan['observations']))
        self.assertEqual(3, len({e['observation_key'] for e in plan['observations']}))
        self.assertEqual(3, len({e['observation']['source']['row_key'] for e in plan['observations']}))
        self.assertEqual(plan, self.synthetic_plan('searchconsole', copy.deepcopy(data)))
        public = json.dumps(plan)
        self.assertNotIn('SECRET', public)
        self.assertNotIn('token=', public)
        self.assertNotIn('?p=', public)

    def test_youtube_watch_v_ids_distinguish_rows_without_copying_other_query_values(self):
        data = {'items': [
            {'title': '같은 제목', 'views': 5, 'url': 'https://www.youtube.com/watch?v=videoA&token=SECRET'},
            {'title': '같은 제목', 'views': 5, 'url': 'https://www.youtube.com/watch?v=videoB&token=SECRET'},
            {'title': '같은 제목', 'views': 5, 'url': 'https://www.youtube.com/watch?v=videoA&token=OTHER_SECRET'}]}
        plan = self.synthetic_plan('youtube', data)
        self.assertEqual(2, len(plan['observations']))
        self.assertEqual({'videoA', 'videoB'}, {e['observation']['remote_id'] for e in plan['observations']})
        self.assertEqual(2, len({e['observation_key'] for e in plan['observations']}))
        self.assertNotIn('SECRET', json.dumps(plan))
        self.assertNotIn('token=', json.dumps(plan))
        self.assertEqual(plan, self.synthetic_plan('youtube', copy.deepcopy(data)))

    def test_youtube_v_extraction_rejects_wrong_host_duplicate_and_invalid_ids(self):
        urls = ['https://youtube.com.evil.example/watch?v=videoA',
                'https://www.youtube.com/watch?v=videoA&v=videoB',
                'https://www.youtube.com/watch?v=bad%2Fid',
                'https://www.youtube.com/other?v=videoA',
                'https://www.youtube.com/watch?access_token=SECRET']
        plan = self.synthetic_plan('youtube', {'items': [{'url': url, 'views': 1} for url in urls]})
        self.assertEqual(len(urls), len(plan['observations']))
        self.assertTrue(all(e['observation']['remote_id'] is None for e in plan['observations']))
        self.assertNotIn('SECRET', json.dumps(plan))

    def test_unidentified_equal_rows_keep_separate_stable_source_positions(self):
        data = {'items': [{'title': '식별 불명', 'views': 1}, {'title': '식별 불명', 'views': 1}]}
        plan = self.synthetic_plan('blog', data)
        self.assertEqual(2, len(plan['observations']))
        self.assertNotEqual(plan['observations'][0]['observation_key'], plan['observations'][1]['observation_key'])
        self.assertEqual(plan, self.synthetic_plan('blog', copy.deepcopy(data)))

    def test_true_duplicate_with_strong_remote_identity_is_still_deduplicated(self):
        row = {'title': '중복', 'url': 'https://mine.tistory.com/7', 'views': 1}
        plan = self.synthetic_plan('blog', {'items': [row, dict(row)]})
        self.assertEqual(1, len(plan['observations']))

    def test_conflicting_import_rolls_back_earlier_new_row(self):
        plan = self.plan()
        store = MetricsStore(Path(self.tmp.name) / 'managed')
        store.initialize()
        import_snapshot(store, plan)
        before = store.list_observations()
        broken = copy.deepcopy(plan)
        added = copy.deepcopy(broken['observations'][0])
        added['observation_key'] = 'new-prefix'
        broken['observations'].insert(0, added)
        broken['observations'][-1]['observation']['title'] = '충돌'
        with self.assertRaises(ConflictError):
            import_snapshot(store, broken)
        self.assertEqual(before, store.list_observations())

    def test_explicit_registered_connection_and_target_can_assign_without_url(self):
        self.write('blog', {'items': [{'connection_id': 'personal-tistory', 'target_id': 'https://mine.tistory.com', 'views': 5}]})
        row = next(e['observation'] for e in self.plan()['observations'] if e['observation']['source']['kind'] == 'blog')
        self.assertEqual('personal', row['destination_account_id'])
        self.assertEqual('personal-tistory', row['connection_id'])
        self.assertIsNone(row['owner_account_id'])

    def test_arbitrary_original_keys_are_not_copied_to_public_sources(self):
        self.write('instagram', {'profile': {'uid': '178900'}, 'token': 'SECRET', 'items': [
            {'url': 'https://instagram.com/p/ABC?access_token=SECRET', 'views': 0,
             'source': {'absolute_path': '/secret/token', 'token': 'SECRET'}, 'password': 'SECRET'}]})
        output = json.dumps(self.plan())
        self.assertNotIn('SECRET', output)
        self.assertNotIn('/secret/token', output)
        self.assertNotIn('access_token', output)

    def test_different_or_ambiguous_registered_targets_remain_unassigned(self):
        duplicate = Connection('other', 'personal', 'instagram', target_id='178900')
        registry = Registry('r2', {'personal': {}, 'dept': {}}, {}, {}, {
            **dict(self.registry.connections), 'other': duplicate}, {}, {}, {})
        plan = build_import_plan(load_legacy_metrics(self.root, registry), registry)
        rows = [e['observation'] for e in plan['observations'] if e['observation']['platform'] == 'instagram']
        self.assertTrue(all(r['destination_account_id'] is None for r in rows))

    def test_bad_unicode_and_numeric_rows_do_not_abort_other_sources(self):
        self.write('blog', {'items': [{'title': chr(0xD800), 'views': 4}, {'title': '유효', 'views': True}]})
        plan = self.plan()
        rows = [e['observation'] for e in plan['observations'] if e['observation']['source']['kind'] == 'blog']
        self.assertEqual(2, len(rows))
        self.assertTrue(any('invalid_metric_value' in r['uncertainties'] for r in rows))
        self.assertGreater(plan['counts']['errors'], 0)
        store = MetricsStore(Path(self.tmp.name) / 'managed')
        store.initialize()
        self.assertGreater(import_snapshot(store, plan)['imported'], 0)

    def test_import_rollback_and_explicit_initialize_required(self):
        plan = self.plan()
        store = MetricsStore(Path(self.tmp.name) / 'managed')
        with self.assertRaises(StoreError):
            import_snapshot(store, plan)
        self.assertFalse(store.root.exists())
        store.initialize()
        broken = copy.deepcopy(plan)
        broken['observations'][-1]['observation']['values'] = {'views': True}
        with self.assertRaises(StoreError):
            import_snapshot(store, broken)
        self.assertEqual([], store.list_observations())

    def test_read_build_no_writes_network_or_unapproved_file_access(self):
        before = {str(p): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) for p in self.parts.iterdir()}
        opened = []
        real_open = os.open
        def tracked_open(path, flags, *args, **kwargs):
            self.assertEqual(0, flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
            opened.append(str(path))
            return real_open(path, flags, *args, **kwargs)
        with patch('socket.socket', side_effect=AssertionError('network forbidden')), patch('os.open', side_effect=tracked_open):
            first = load_legacy_metrics(self.root, self.registry)
            second = copy.deepcopy(first)
            self.assertEqual(build_import_plan(first, self.registry), build_import_plan(second, self.registry))
            self.assertEqual(first, second)
        self.assertEqual({str(self.root), 'common', 'analytics', 'snapshots', 'parts'} | {k + '.json' for k in self.fixtures}, set(opened))
        with patch('os.open', side_effect=AssertionError('pure build cannot read')):
            build_import_plan(first, self.registry)
        after = {str(p): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) for p in self.parts.iterdir()}
        self.assertEqual(before, after)
        self.assertEqual({'common'}, {p.name for p in self.root.iterdir()})

    def test_symlink_parent_directory_is_never_followed(self):
        outside = Path(self.tmp.name) / 'outside'
        self.parts.rename(outside)
        self.parts.symlink_to(outside, target_is_directory=True)
        snapshot = load_legacy_metrics(self.root, self.registry)
        self.assertTrue(all(f['status'] == 'unsafe' for f in snapshot['files']))


if __name__ == '__main__':
    unittest.main()
