import copy
import math
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from common.operations.content_store import ConflictError, ContentStore, StoreError
from common.operations.media_plans import (
    DB_NAME, MediaPlanStore, default_media_plan, media_plan_readiness, validate_media_plan)

PNG = b'\x89PNG\r\n\x1a\n'
WAV = b'RIFF\x00\x00\x00\x00WAVE'
PUBLIC_KEYS = {'content_id', 'content_revision', 'manifest_hash', 'owner_account_id', 'plan_revision', 'plan',
               'inputs_ready', 'blockers', 'execution_enabled', 'review_status'}


def scene(asset_id, kind='diorama', seconds=5, title='장면', caption='자막'):
    return {'asset_id': asset_id, 'kind': kind, 'seconds': seconds, 'title': title, 'caption': caption}


class MediaPlanTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / 'store'
        self.contents = ContentStore(self.root)
        self.contents.initialize()
        self.plans = MediaPlanStore(self.root, self.contents)

    def make_content(self, owner='personal', images=3, voice=True, series='시리즈'):
        """실제 ContentStore에 PNG/WAV 자산을 올리고 마지막 snapshot과 자산 id를 돌려준다."""
        item = self.contents.create(owner, {'title': '제목', 'kind': 'short', 'series': series})
        image_ids, voice_id = [], None
        for index in range(images):
            item = self.contents.add_asset(item['id'], item['revision'], 'img%d.png' % index, 'image/png',
                                           PNG + bytes([index]) * 8)
            image_ids.append(item['assets'][-1]['id'])
        if voice:
            item = self.contents.add_asset(item['id'], item['revision'], 'voice.wav', 'audio/wav', WAV + b'data')
            voice_id = item['assets'][-1]['id']
        return item, image_ids, voice_id

    def ready_plan(self, images, voice):
        return {**default_media_plan({'title': '제목'}), 'voice_asset_id': voice,
                'scenes': [scene(images[0]), scene(images[1]), scene(images[2], 'diagram')]}

    def test_get_without_database_returns_default_and_mutates_nothing(self):
        item, images, voice = self.make_content()
        before = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob('*'))
        result = self.plans.get(item['id'], item['revision'])
        self.assertEqual(set(result), PUBLIC_KEYS)
        self.assertEqual(result['plan_revision'], 0)
        self.assertEqual(result['plan'], {'exam': '시리즈', 'field': '제목', 'source': '', 'footer': '',
                                          'disclosure': 'AI 합성 음성 · 검토 전', 'voice_asset_id': None, 'scenes': []})
        self.assertIs(result['execution_enabled'], False)
        self.assertEqual(result['review_status'], 'not_checked')
        self.assertEqual(result['owner_account_id'], 'personal')
        self.assertEqual(result['manifest_hash'], item['manifest_hash'])
        self.assertFalse((self.root / DB_NAME).exists())
        self.assertEqual(sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob('*')), before)
        self.assertEqual(default_media_plan({'title': 'T', 'series': ''})['exam'], '콘텐츠')

    def test_initialize_is_explicit_and_required_for_save(self):
        item, images, voice = self.make_content()
        self.assertFalse((self.root / DB_NAME).exists())
        plan = self.ready_plan(images, voice)
        with self.assertRaises(StoreError) as caught:
            self.plans.save(item['id'], item['revision'], 0, plan)
        self.assertEqual(caught.exception.code, 'storage_error')
        self.assertFalse((self.root / DB_NAME).exists())
        self.plans.initialize()
        self.assertTrue((self.root / DB_NAME).is_file())
        self.plans.initialize()  # 멱등
        with sqlite3.connect(self.root / DB_NAME) as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], 1)
        # 새 인스턴스는 DB가 있어도 initialize 전에는 저장할 수 없다.
        with self.assertRaises(StoreError):
            MediaPlanStore(self.root, self.contents).save(item['id'], item['revision'], 0, plan)
        with self.assertRaises(StoreError):
            MediaPlanStore(Path(self._tmp.name) / 'other', self.contents)

    def test_cas_revisions_and_conflict(self):
        item, images, voice = self.make_content()
        self.plans.initialize()
        plan = self.ready_plan(images, voice)
        first = self.plans.save(item['id'], item['revision'], 0, plan)
        self.assertEqual(set(first), PUBLIC_KEYS)
        self.assertEqual(first['plan_revision'], 1)
        with self.assertRaises(ConflictError) as caught:
            self.plans.save(item['id'], item['revision'], 0, plan)
        self.assertEqual(caught.exception.code, 'conflict')
        changed = {**plan, 'source': '출처'}
        second = self.plans.save(item['id'], item['revision'], 1, changed)
        self.assertEqual(second['plan_revision'], 2)
        self.assertEqual(self.plans.get(item['id'], item['revision']), second)
        self.assertEqual(self.plans.get(item['id'], item['revision'])['plan']['source'], '출처')
        for bad in (-1, True, '1', 1.0, None):
            with self.assertRaises(StoreError) as invalid:
                self.plans.save(item['id'], item['revision'], bad, plan)
            self.assertEqual(invalid.exception.code, 'invalid')

    def test_accounts_are_separated_and_owner_is_server_bound(self):
        personal, p_images, p_voice = self.make_content('personal')
        dept, d_images, d_voice = self.make_content('dept')
        self.plans.initialize()
        saved_p = self.plans.save(personal['id'], personal['revision'], 0, self.ready_plan(p_images, p_voice))
        self.assertEqual(self.plans.get(dept['id'], dept['revision'])['plan_revision'], 0)
        saved_d = self.plans.save(dept['id'], dept['revision'], 0, {**self.ready_plan(d_images, d_voice), 'footer': '학과'})
        self.assertEqual((saved_p['owner_account_id'], saved_d['owner_account_id']), ('personal', 'dept'))
        self.assertEqual(self.plans.get(personal['id'], personal['revision'])['plan']['footer'], '')
        # 다른 원본의 자산 id는 같은 형식이어도 거부한다.
        with self.assertRaises(StoreError) as caught:
            self.plans.save(personal['id'], personal['revision'], 1, self.ready_plan(d_images, d_voice))
        self.assertEqual(caught.exception.code, 'invalid')
        with self.assertRaises(StoreError) as missing:
            self.plans.get('managed_nope', 1)
        self.assertEqual(missing.exception.code, 'not_found')

    def test_plan_is_pinned_to_content_revision(self):
        item, images, voice = self.make_content()
        self.plans.initialize()
        saved = self.plans.save(item['id'], item['revision'], 0, self.ready_plan(images, voice))
        revised = self.contents.update(item['id'], item['revision'], {'title': '수정 제목', 'kind': 'short', 'series': '시리즈'})
        self.assertEqual(revised['revision'], item['revision'] + 1)
        newer = self.plans.get(item['id'], revised['revision'])
        self.assertEqual(newer['plan_revision'], 0)
        self.assertEqual(newer['plan']['field'], '수정 제목')
        self.assertNotEqual(newer['manifest_hash'], saved['manifest_hash'])
        self.assertEqual(self.plans.get(item['id'], item['revision']), saved)
        with self.assertRaises(StoreError) as caught:
            self.plans.get(item['id'], revised['revision'] + 1)
        self.assertEqual(caught.exception.code, 'not_found')
        # 새 리비전은 자체 CAS 계열을 시작한다.
        self.assertEqual(self.plans.save(item['id'], revised['revision'], 0, self.ready_plan(images, voice))['plan_revision'], 1)

    def test_unknown_assets_and_media_types_are_rejected(self):
        item, images, voice = self.make_content()
        self.plans.initialize()
        base = self.ready_plan(images, voice)
        cases = []
        cases.append({**base, 'scenes': [scene('asset_unknown')]})
        cases.append({**base, 'scenes': [scene(voice)]})          # 음성은 장면 이미지가 될 수 없다.
        cases.append({**base, 'voice_asset_id': images[0]})       # 이미지는 음성이 될 수 없다.
        cases.append({**base, 'voice_asset_id': 'asset_unknown'})
        cases.append({**base, 'scenes': [scene(images[0], kind='video')]})
        for plan in cases:
            with self.assertRaises(StoreError) as caught:
                self.plans.save(item['id'], item['revision'], 0, plan)
            self.assertEqual(caught.exception.code, 'invalid')
        self.assertEqual(self.plans.get(item['id'], item['revision'])['plan_revision'], 0)

    def test_incomplete_draft_saves_with_blockers(self):
        item, images, voice = self.make_content()
        self.plans.initialize()
        empty = self.plans.save(item['id'], item['revision'], 0, default_media_plan(item))
        self.assertFalse(empty['inputs_ready'])
        self.assertEqual(empty['blockers'], ['voice_required', 'scenes_required', 'diorama_required',
                                             'distinct_diorama_required'])
        same = {**default_media_plan(item), 'voice_asset_id': voice, 'scenes': [scene(images[0]), scene(images[0])]}
        self.assertEqual(self.plans.save(item['id'], item['revision'], 1, same)['blockers'], ['distinct_diorama_required'])
        four = {**same, 'scenes': [scene(images[0]), scene(images[1]), scene(images[2]), scene(images[0])]}
        # 4장면(서로 다른 이미지 3개)은 장면 수만 위반한다.
        self.assertEqual(media_plan_readiness(validate_media_plan(four, item))['blockers'], ['diorama_required'])
        diagrams = {**same, 'scenes': [scene(images[0], 'diagram'), scene(images[1], 'diagram')]}
        self.assertIn('diorama_required', media_plan_readiness(diagrams)['blockers'])
        no_voice = {**self.ready_plan(images, voice), 'voice_asset_id': None}
        self.assertEqual(self.plans.save(item['id'], item['revision'], 2, no_voice)['blockers'], ['voice_required'])
        ready = self.plans.save(item['id'], item['revision'], 3, self.ready_plan(images, voice))
        self.assertTrue(ready['inputs_ready'])
        self.assertEqual(ready['blockers'], [])
        self.assertIs(ready['execution_enabled'], False)
        self.assertEqual(ready['review_status'], 'not_checked')

    def test_total_duration_scene_count_and_seconds_limits(self):
        item, images, voice = self.make_content()
        self.plans.initialize()
        base = self.ready_plan(images, voice)

        def plan_with(*seconds):
            return {**base, 'scenes': [scene(images[i % 3], seconds=s) for i, s in enumerate(seconds)]}

        saved = self.plans.save(item['id'], item['revision'], 0, plan_with(10, 10))
        self.assertEqual(saved['plan_revision'], 1)
        self.assertEqual(self.plans.save(item['id'], item['revision'], 1, plan_with(0.5, 19.5))['plan_revision'], 2)
        for bad in ((10, 10.01), (20.5,), (0,), (-1, 5), (True, 5), (math.nan, 5), (math.inf,), ('5',), (None,)):
            with self.assertRaises(StoreError, msg=repr(bad)) as caught:
                self.plans.save(item['id'], item['revision'], 2, plan_with(*bad))
            self.assertEqual(caught.exception.code, 'invalid')
        self.assertEqual(len(validate_media_plan(plan_with(*([0.5] * 30)), item)['scenes']), 30)
        with self.assertRaises(StoreError):
            validate_media_plan(plan_with(*([0.1] * 31)), item)
        with self.assertRaises(StoreError):
            validate_media_plan({**base, 'scenes': [scene(images[0], title='가' * 301)]}, item)
        with self.assertRaises(StoreError):
            validate_media_plan({**base, 'scenes': [scene(images[0], caption='가' * 1001)]}, item)
        self.assertEqual(self.plans.get(item['id'], item['revision'])['plan_revision'], 2)

    def test_arbitrary_paths_extra_keys_and_bad_strings_are_rejected(self):
        item, images, voice = self.make_content()
        self.plans.initialize()
        base = self.ready_plan(images, voice)
        bad_plans = [
            {**base, 'scenes': [scene('/etc/passwd')]},
            {**base, 'scenes': [scene('../outside.png')]},
            {**base, 'scenes': [scene(str(self.root / 'x.png'))]},
            {**base, 'voice_asset_id': '/tmp/voice.wav'},
            {**base, 'owner_account_id': 'dept'},
            {**base, 'scenes': [{**scene(images[0]), 'path': '/tmp/a.png'}]},
            {**base, 'scenes': [{k: v for k, v in scene(images[0]).items() if k != 'caption'}]},
            {k: v for k, v in base.items() if k != 'footer'},
            {**base, 'exam': 'a\x00b'},
            {**base, 'source': 'x' * 2001},
            {**base, 'disclosure': 3},
            {**base, 'scenes': tuple(base['scenes'])},
            [],
        ]
        for plan in bad_plans:
            with self.assertRaises(StoreError, msg=repr(plan)[:80]) as caught:
                self.plans.save(item['id'], item['revision'], 0, plan)
            self.assertEqual(caught.exception.code, 'invalid')
        self.assertEqual(validate_media_plan({**base, 'source': 'x' * 2000}, item)['source'], 'x' * 2000)
        original = copy.deepcopy(base)
        normalized = validate_media_plan(base, item)
        normalized['scenes'][0]['title'] = '변경'
        self.assertEqual(base, original)

    def test_save_does_not_change_content_assets_or_execute(self):
        item, images, voice = self.make_content()
        self.plans.initialize()
        revisions = self.contents.list_revisions(item['id'])
        before = self.contents.get(item['id'])
        asset_bytes = self.contents.read_asset(item['id'], item['revision'], images[0])[1]
        self.plans.save(item['id'], item['revision'], 0, self.ready_plan(images, voice))
        self.assertEqual(self.contents.list_revisions(item['id']), revisions)
        self.assertEqual(self.contents.get(item['id']), before)
        self.assertEqual(self.contents.read_asset(item['id'], item['revision'], images[0])[1], asset_bytes)
        with sqlite3.connect(self.root / DB_NAME) as conn:
            self.assertEqual([r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")], ['media_plans'])

    def test_symlink_root_and_database_are_rejected(self):
        real = Path(self._tmp.name) / 'real'
        real.mkdir()
        link = Path(self._tmp.name) / 'link'
        link.symlink_to(real)

        class FakeContents:
            root = link

            def get(self, content_id, revision=None): return None

        linked = MediaPlanStore(link, FakeContents())
        for action in (linked.initialize, lambda: linked.get('managed_x', 1)):
            with self.assertRaises(StoreError) as caught:
                action()
            self.assertIn(caught.exception.code, ('storage_error', 'not_found'))
        with self.assertRaises(StoreError) as init_error:
            linked.initialize()
        self.assertEqual(init_error.exception.code, 'storage_error')
        self.assertEqual(list(real.iterdir()), [])
        # DB 파일 자체가 심볼릭 링크여도 거부하고 대상을 만들지 않는다.
        target = Path(self._tmp.name) / 'elsewhere.sqlite3'
        os.symlink(target, self.root / DB_NAME)
        with self.assertRaises(StoreError) as db_error:
            self.plans.initialize()
        self.assertEqual(db_error.exception.code, 'storage_error')
        self.assertFalse(target.exists())
        item, images, voice = self.make_content()
        with self.assertRaises(StoreError) as get_error:
            self.plans.get(item['id'], item['revision'])
        self.assertEqual(get_error.exception.code, 'storage_error')

    def test_foreign_database_is_rejected(self):
        item, images, voice = self.make_content()
        foreign = self.root / DB_NAME
        with sqlite3.connect(foreign) as conn:
            conn.execute('CREATE TABLE other(x TEXT)')
            conn.execute("INSERT INTO other VALUES('keep')")
        with self.assertRaises(StoreError) as caught:
            self.plans.initialize()
        self.assertEqual(caught.exception.code, 'storage_error')
        with self.assertRaises(StoreError) as read_error:
            self.plans.get(item['id'], item['revision'])
        self.assertEqual(read_error.exception.code, 'storage_error')
        with sqlite3.connect(foreign) as conn:
            self.assertEqual(conn.execute('SELECT x FROM other').fetchall(), [('keep',)])
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], 0)
        self.assertFalse(self.plans._initialized)


if __name__ == '__main__':
    unittest.main()
