"""Read-model fixtures never use operating data or home directories."""
import importlib.util
import json
import os
import plistlib
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'ax-console/app/read_model.py'
NOW = datetime.fromisoformat('2026-10-30T12:00:00+09:00')


def load_model():
    spec = importlib.util.spec_from_file_location('fixture_read_model', MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ReadModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def put(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        return path

    def config(self):
        self.put('ax-console/config/accounts.json', {'accounts': {
            'dept': {'label': '학과', 'channels': {'tiktok': {'secrets': ['HIDDEN_TOKEN']}, 'youtube': {}}},
            'personal': {'label': '개인', 'channels': {'youtube': {'status': '확인 필요'}}}}})
        self.put('ax-console/config/automations.json', {'jobs': [{
            'job': 'geoai.short', 'name': '개인 숏츠', 'account': 'personal',
            'channels': [['personal', 'youtube'], ['dept', 'tiktok']], 'enabled': False}]})

    def snapshot(self, account='all', **kwargs):
        return load_model().build_snapshot(self.root, account, now=NOW, **kwargs)

    def test_missing_sources_are_explicit_and_schema_is_complete(self):
        s = self.snapshot()
        self.assertEqual(s['schema_version'], 1)
        self.assertTrue(s['read_only'])
        self.assertEqual(s['scope'], 'all')
        self.assertEqual(s['generated_at'], '2026-10-30T12:00:00+09:00')
        self.assertEqual({a['id'] for a in s['accounts']}, {'dept', 'personal'})
        for key in ('contents', 'deliveries', 'channels', 'schedule', 'incidents', 'crossposts', 'proposals'):
            self.assertEqual(s[key], [])
        self.assertEqual(s['metrics'], {'status': 'unavailable', 'items': []})
        self.assertTrue(s['warnings'])
        self.assertNotIn(str(self.root), json.dumps(s))
        with self.assertRaises(ValueError):
            self.snapshot('arbitrary')

    def test_cross_destination_retains_original_ownership_and_filters_deliveries(self):
        self.config()
        self.put('ax-console/data/content/2026/10/a/meta.json', {
            'id': 'a', 'account': 'personal', 'title': '원본', 'status': 'scheduled',
            'kind': 'short', 'tasks': {'youtube': 'p', 'tiktok': 'd'}, 'channels': ['youtube']})
        self.put('ax-console/data/tasks.json', [
            {'id': 'p', 'content': 'a', 'account': 'personal', 'channel': 'youtube', 'status': 'done'},
            {'id': 'd', 'content': 'a', 'account': 'dept', 'channel': 'tiktok', 'status': 'scheduled', 'schedule': '2026-10-30T19:00:00'}])
        s = self.snapshot('dept')
        self.assertEqual(len(s['contents']), 1)
        self.assertEqual(s['contents'][0]['owner_account_id'], 'personal')
        self.assertEqual(s['contents'][0]['status'], 'scheduled')
        self.assertEqual(len(s['deliveries']), 1)
        delivery = s['deliveries'][0]
        self.assertEqual(delivery['owner_account_id'], 'personal')
        self.assertEqual(delivery['destination_account_id'], 'dept')
        self.assertEqual(delivery['status'], 'queued')
        self.assertEqual(delivery['content_id'], s['contents'][0]['id'])
        self.assertEqual(delivery['scheduled_at'], '2026-10-30T19:00:00+09:00')
        self.assertTrue(all(x['account_id'] == 'dept' for x in s['channels']))
        self.assertTrue(all(x['destination_account_id'] == 'dept' for x in s['schedule']))
        personal = self.snapshot('personal')
        self.assertEqual(len(personal['deliveries']), 2)
        done = next(x for x in personal['deliveries'] if x['channel'] == 'youtube')
        self.assertEqual(done['status'], 'reported_published')
        self.assertIsNone(done['checked_at'])
        self.assertEqual(s['crossposts'][0]['enabled'], False)

    def test_channel_config_does_not_imply_authentication_or_enabled(self):
        self.config()
        s = self.snapshot()
        tiktok = next(x for x in s['channels'] if x['platform'] == 'tiktok')
        self.assertEqual(tiktok['auth_status'], 'unknown')
        self.assertEqual(tiktok['configured_status'], 'registered')
        self.assertIsNone(tiktok['enabled'])
        self.assertNotIn('HIDDEN_TOKEN', json.dumps(s))
        self.assertNotIn('secrets', json.dumps(s))

    def test_corrupt_jsonl_line_keeps_other_records_and_does_not_verify(self):
        self.config()
        p = self.root / 'personal/claude-jobs/state/survey-daily.jsonl'
        p.parent.mkdir(parents=True)
        p.write_text('{broken\n' + json.dumps({'at': '2026-10-30T10:00:00+0900', 'status': 'published', 'title': '측량', 'urls': {'tistory': 'https://example.org/post', 'naver': 'javascript:alert(1)'}, 'note': 'private log body'}) + '\n')
        s = self.snapshot()
        self.assertEqual(len(s['contents']), 1)
        self.assertEqual(len(s['deliveries']), 2)
        self.assertEqual({d['status'] for d in s['deliveries']}, {'reported_published'})
        self.assertIsNone(next(d for d in s['deliveries'] if d['channel'] == 'naver_blog')['url'])
        self.assertTrue(any('JSONL' in w for w in s['warnings']))
        self.assertNotIn('private log body', json.dumps(s))
        ids = [x['id'] for x in s['contents']]
        with p.open('a') as stream:
            stream.write(json.dumps({'at': '2026-10-30T11:00:00', 'status': 'failed', 'title': '다음'}) + '\n')
        self.assertTrue(set(ids).issubset({x['id'] for x in self.snapshot()['contents']}))

    def test_upload_record_is_remote_recorded_even_after_scheduled_time(self):
        self.config()
        self.put('dept/disaster-shorts/2026-10-29_안전/upload.json', {
            'video_id': 'abc', 'url': 'https://youtu.be/abc', 'publish_at_kst': '2026-10-29T19:00:00+09:00',
            'uploaded_at': '2026-10-28T12:00:00+09:00'})
        s = self.snapshot()
        d = s['deliveries'][0]
        self.assertEqual(d['status'], 'scheduled_recorded')
        self.assertEqual(d['schedule_kind'], 'remote_recorded')
        self.assertIsNone(d['checked_at'])
        self.assertEqual(s['contents'][0]['status'], 'scheduled')

    def test_tiktok_queue_uses_source_ownership_and_posted_result_not_presence(self):
        self.config()
        self.put('dept/youtube-shorts-auto/posts/tiktok_queue.json', [
            {'video': '/private/raw/a.mp4', 'title': '개인 원본', 'source': 'geoai_short', 'not_before': '2026-10-30T19:10:00', 'added': '2026-10-30T10:00:00', 'posted': None},
            {'video': '/private/raw/b.mp4', 'title': '완료 기록', 'source': 'shorts-disaster', 'posted': {'at': '2026-10-29T12:00:00', 'status': 'posted'}},
            {'video': '/private/raw/c.mp4', 'title': '실패 기록', 'source': 'future_source', 'posted': {'at': '2026-10-29T12:00:00', 'status': 'error'}}])
        s = self.snapshot('personal')
        self.assertEqual(len(s['contents']), 1)
        self.assertEqual(s['contents'][0]['owner_account_id'], 'personal')
        self.assertEqual(s['deliveries'][0]['destination_account_id'], 'dept')
        self.assertEqual(s['deliveries'][0]['status'], 'queued')
        all_s = self.snapshot()
        self.assertEqual({d['status'] for d in all_s['deliveries']}, {'queued', 'failed', 'reported_published'})
        self.assertNotIn('/private/raw', json.dumps(all_s))
        self.assertIsNone(next(c for c in all_s['contents'] if c['title'] == '실패 기록')['owner_account_id'])

    def test_repeated_source_keys_do_not_merge_distinct_content(self):
        self.config()
        for key, account in [('a', 'dept'), ('b', 'personal')]:
            self.put(f'ax-console/data/content/2026/10/{key}/meta.json', {'id': 'same', 'account': account, 'title': key})
        self.put('ax-console/data/tasks.json', [{'id': 'task', 'content': 'same', 'account': 'dept', 'channel': 'youtube', 'status': 'done'}])
        s = self.snapshot()
        self.assertEqual(len({c['id'] for c in s['contents']}), 3)
        self.assertEqual(len(s['deliveries']), 1)
        self.assertEqual(next(c for c in s['contents'] if c['id'] == s['deliveries'][0]['content_id'])['title'], '제목 미기록')
        self.assertTrue(any('중복' in w for w in s['warnings']))

    def test_bad_json_and_wrong_shapes_warn_instead_of_crashing(self):
        self.config()
        self.put('ax-console/data/tasks.json', {'wrong': []})
        self.put('ax-console/data/content/2026/10/a/meta.json', [])
        p = self.root / 'ax-console/data/proposals/2026-W44_personal.json'
        p.parent.mkdir(parents=True)
        p.write_text('{')
        s = self.snapshot()
        self.assertFalse(s['contents'])
        self.assertTrue(len(s['warnings']) >= 3)

    def test_plist_metadata_is_korean_time_and_interval_next_time_unknown(self):
        self.config()
        agents = self.root / 'launchagents'
        agents.mkdir()
        for key, extra in [('geoai.short', {'StartCalendarInterval': {'Hour': 19, 'Minute': 0}, 'Disabled': True}),
                           ('interval', {'StartInterval': 3600})]:
            (agents / f'com.smuds.{key}.plist').write_bytes(plistlib.dumps({'Label': f'com.smuds.{key}', **extra}))
        s = self.snapshot(launchagents_dir=agents)
        timed = [x for x in s['schedule'] if x['scheduled_at'] == '2026-10-30T19:00:00+09:00']
        self.assertEqual(len(timed), 2)
        self.assertEqual({x['destination_account_id'] for x in timed}, {'personal', 'dept'})
        self.assertEqual({x['status'] for x in timed}, {'paused'})
        self.assertTrue(any(x['scheduled_at'] is None for x in s['schedule']))
        self.assertTrue(any('간격' in w for w in s['warnings']))

    def test_incidents_exclude_archive_and_proposals_keep_owner(self):
        self.config()
        self.put('ax-console/data/incidents/2026-10/i.json', {'id': 'i', 'name': '장애', 'account': 'personal', 'severity': 'error', 'status': 'open', 'last': '2026-10-30T09:00:00', 'evidence': [{'text': 'raw secret body'}]})
        self.put('ax-console/data/incidents/archive/old.json', {'id': 'old', 'name': '보관'})
        self.put('ax-console/data/proposals/2026-W44_personal.json', {'account': 'personal', 'items': [{'id': 'i', 'title': '제안', 'why': '기획 근거', 'status': 'new'}], 'log': 'raw secret body'})
        s = self.snapshot('personal')
        self.assertEqual(len(s['incidents']), 1)
        self.assertEqual(len(s['proposals']), 1)
        self.assertEqual(s['proposals'][0]['owner_account_id'], 'personal')
        self.assertNotIn('raw secret body', json.dumps(s))
        self.assertEqual(self.snapshot('dept')['incidents'], [])

    def test_snapshot_and_import_preserve_all_fixture_bytes_and_mtimes(self):
        self.config()
        self.put('ax-console/data/tasks.json', [])
        self.put('ax-console/data/orchestrator/waiting/dead.json', {'pid': 99999999})
        self.put('ax-console/data/STOP.json', {'reason': '사용자 중지'})
        def state():
            return {str(p.relative_to(self.root)): (p.read_bytes(), p.stat().st_mtime_ns)
                    for p in self.root.rglob('*') if p.is_file()}
        before = state()
        with patch('subprocess.run', side_effect=AssertionError('subprocess forbidden')):
            self.snapshot()
            self.snapshot('dept')
        self.assertEqual(state(), before)

    def test_recent_jsonl_and_queue_are_bounded_and_stable_when_reordered(self):
        self.config()
        p = self.root / 'personal/claude-jobs/state/big.jsonl'
        p.parent.mkdir(parents=True)
        p.write_text(''.join(json.dumps({'at': f'2026-10-30T10:{n % 60:02d}:00', 'title': f'line{n}', 'status': 'failed'}) + '\n' for n in range(1200)))
        queue = [{'video': f'/private/{n}.mp4', 'title': f'q{n}', 'source': 'geoai', 'added': f'2026-10-{n % 28 + 1:02d}T10:00:00'} for n in range(1200)]
        self.put('dept/youtube-shorts-auto/posts/tiktok_queue.json', queue)
        s = self.snapshot()
        self.assertLess(len(s['contents']), 1000)
        self.assertIn('line1199', {x['title'] for x in s['contents']})
        self.assertTrue(any('제한' in w for w in s['warnings']))
        ids = {x['title']: x['id'] for x in s['contents'] if x['title'].startswith('q')}
        self.put('dept/youtube-shorts-auto/posts/tiktok_queue.json', list(reversed(queue)))
        self.assertEqual({x['title']: x['id'] for x in self.snapshot()['contents'] if x['title'].startswith('q')}, ids)

    def test_ids_survive_task_state_and_proposal_status_changes(self):
        self.config()
        task = {'id': 'stable', 'account': 'dept', 'channel': 'youtube', 'title': '제목', 'status': 'scheduled'}
        proposal = {'account': 'personal', 'items': [
            {'id': 'p', 'title': '제안', 'status': 'new'},
            {'id': 'q', 'title': '다른 제안', 'status': 'new'}]}
        self.put('ax-console/data/tasks.json', [task])
        self.put('ax-console/data/proposals/2026-W44_personal.json', proposal)
        before = self.snapshot()
        task.update(status='done', url='https://example.org/post')
        proposal['items'][0]['status'] = 'accepted'
        self.put('ax-console/data/tasks.json', [task])
        self.put('ax-console/data/proposals/2026-W44_personal.json', proposal)
        after = self.snapshot()
        self.assertEqual(before['deliveries'][0]['id'], after['deliveries'][0]['id'])
        self.assertEqual(before['contents'][0]['id'], after['contents'][0]['id'])
        self.assertEqual({p['title']: p['id'] for p in before['proposals']},
                         {p['title']: p['id'] for p in after['proposals']})

    def test_authoritative_config_wins_and_symlink_sources_are_not_opened(self):
        self.config()
        self.put('config/accounts.json', {'accounts': {'dept': {'label': '잘못된 대체 설정', 'channels': {}}}})
        target = self.put('secret_config.json', {'id': 'secret', 'account': 'dept', 'title': 'MUST_NOT_READ'})
        content_dir = self.root / 'ax-console/data/content/2026/10/link'
        content_dir.mkdir(parents=True)
        (content_dir / 'meta.json').symlink_to(target)
        s = self.snapshot()
        self.assertEqual(s['accounts'][0]['label'], '학과')
        self.assertEqual(s['contents'], [])
        self.assertNotIn('MUST_NOT_READ', json.dumps(s))
        self.assertTrue(any('링크' in w for w in s['warnings']))

    def test_calendar_intervals_select_earliest_and_respect_weekday(self):
        self.config()
        agents = self.root / 'launchagents'
        agents.mkdir()
        (agents / 'com.smuds.geoai.short.plist').write_bytes(plistlib.dumps({
            'StartCalendarInterval': [{'Hour': 20}, {'Hour': 18, 'Minute': 10, 'Weekday': 5}]}))
        s = self.snapshot(launchagents_dir=agents)
        self.assertEqual({x['scheduled_at'] for x in s['schedule']}, {'2026-10-30T18:10:00+09:00'})

    def test_hourly_calendar_entry_is_not_hidden_by_daily_entry(self):
        self.config()
        agents = self.root / 'launchagents'
        agents.mkdir()
        (agents / 'com.smuds.geoai.short.plist').write_bytes(plistlib.dumps({
            'StartCalendarInterval': [{'Hour': 20, 'Minute': 0}, {'Minute': 30}]}))
        s = self.snapshot(launchagents_dir=agents)
        self.assertEqual({x['scheduled_at'] for x in s['schedule']}, {'2026-10-30T12:30:00+09:00'})

    def test_urls_with_credentials_or_secret_queries_and_absolute_paths_are_not_exposed(self):
        self.config()
        self.put('ax-console/data/tasks.json', [
            {'id': 'one', 'account': 'dept', 'channel': 'youtube', 'title': '원본', 'status': 'done', 'url': 'https://user:secret@example.org/x'},
            {'id': 'two', 'account': 'dept', 'channel': 'youtube', 'title': '원본', 'status': 'done', 'url': 'https://example.org/x?access_token=SECRET'}])
        s = self.snapshot()
        self.assertTrue(all(d['url'] is None for d in s['deliveries']))
        self.assertNotIn('SECRET', json.dumps(s))


if __name__ == '__main__':
    unittest.main()
