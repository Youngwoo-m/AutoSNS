import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from common.operations.content_store import StoreError
from common.operations.models import ContractError
from common.operations.production import validate_production_result
from common.operations.video_tasks import APPLICATION_ID, COLUMNS, DB_NAME, LEGACY_DDL, VideoTaskService, VideoTaskStore
from tests.operations import test_video_tasks as legacy  # 기존 helper는 모듈 별칭으로만 재사용한다.

MP4 = legacy.MP4
PUBLIC = legacy.PUBLIC
GOOD = dict(audio_checked=True, font_checked=True, disclosure_checked=True, scenes_checked=True)
CONTEXT = {'task_id', 'state', 'content_id', 'input_revision', 'plan_revision', 'context_fingerprint', 'scene_count',
           'media', 'manifest', 'review_status'}
MEDIA = {'filename', 'media_type', 'size', 'sha256', 'seconds', 'width', 'height', 'has_audio'}
MANIFEST = {'exam', 'field', 'source', 'footer', 'disclosure', 'scenes'}
SCENE = {'index', 'kind', 'seconds', 'title', 'caption'}


class VideoReviewTests(unittest.TestCase):
    def test_korean_review_notes_use_character_limit_and_reject_invalid_unicode(self):
        svc,item,record,task_id=self.awaiting()
        fingerprint=svc.review_context(task_id)['context_fingerprint']
        with self.assertRaises(ContractError):self.confirm(svc,task_id,fingerprint,notes='\ud800')
        result=self.confirm(svc,task_id,fingerprint,notes='확'*1000)
        self.assertEqual(result['state'],'completed')

    def test_explicit_new_plan_supersedes_stale_review_without_touching_old_video(self):
        svc,item,record,task_id=self.awaiting()
        path=self.root_of(svc,task_id)/'short.mp4';before=path.read_bytes()
        changed={**record['plan'],'footer':'새 계획'}
        updated=self.plans.save(item['id'],item['revision'],record['plan_revision'],changed)
        new=svc.create(item['id'],item['revision'],updated['plan_revision'])
        self.assertEqual(new['state'],'queued');self.assertNotEqual(new['task_id'],task_id)
        self.assertEqual(self.tasks.get(task_id)['state'],'content_changed')
        self.assertEqual(path.read_bytes(),before);self.assertEqual(self.runs,1)

    setUp = legacy.VideoTaskTests.setUp
    make_content = legacy.VideoTaskTests.make_content
    ready_plan = legacy.VideoTaskTests.ready_plan
    prepare_record = legacy.VideoTaskTests.prepare_record
    tamper = legacy.VideoTaskTests.tamper
    factory = legacy.VideoTaskTests.factory
    runner = legacy.VideoTaskTests.runner
    authorize = staticmethod(legacy.VideoTaskTests.authorize)
    probe = staticmethod(legacy.VideoTaskTests.probe)
    inspect = staticmethod(legacy.VideoTaskTests.inspect)

    def service(self, **kwargs):
        options = dict(enabled=True, runner_factory=self.factory, reuse_authorization=self.authorize,
                       probe=self.probe, inspect_video=None, defer_video_review=True)
        options.update(kwargs)
        return VideoTaskService(self.tasks, self.contents, self.plans, **options)

    def awaiting(self, svc=None, **kwargs):
        svc = svc or self.service(**kwargs)
        item, record = self.prepare_record()
        task = svc.create(item['id'], item['revision'], record['plan_revision'])
        row = svc.run_next()
        self.assertEqual((row['task_id'], row['state']), (task['task_id'], 'awaiting_review'))
        return svc, item, record, task['task_id']

    def root_of(self, svc, task_id):
        return svc._artifact_root(self.tasks.get_row(task_id))

    def stored(self, task_id):
        return json.loads(self.tasks.get_row(task_id)['result'])

    def confirm(self, svc, task_id, fingerprint=None, decision='pass', checks=GOOD, notes='확인함', **kwargs):
        fingerprint = fingerprint or svc.review_context(task_id)['context_fingerprint']
        return svc.confirm_review(task_id, fingerprint, decision, dict(checks), notes, **kwargs)

    # --- 보류 ---------------------------------------------------------------
    def test_defer_renders_once_and_keeps_candidate_without_ingest(self):
        svc, item, record, task_id = self.awaiting()
        row = self.tasks.get(task_id)
        self.assertEqual(set(row), PUBLIC)
        self.assertEqual((row['state'], row['reason_code'], row['review_status']),
                         ('awaiting_review', 'video_review_required', 'not_checked'))
        self.assertEqual((row['output_revision'], row['asset_id']), (None, None))
        self.assertEqual((self.runs, self.factory_calls), (1, 1))
        self.assertEqual(self.contents.get(item['id'])['revision'], item['revision'])
        self.assertIsNone(svc.run_next())
        self.assertEqual(svc.resume(task_id)['state'], 'awaiting_review')
        self.assertEqual(svc.create(item['id'], item['revision'], record['plan_revision'])['task_id'], task_id)
        self.assertEqual((self.runs, self.contents.get(item['id'])['revision']), (1, item['revision']))
        self.assertEqual((self.root_of(svc, task_id) / 'short.mp4').read_bytes(), MP4)
        evidence = self.stored(task_id)['candidate']['evidence']
        self.assertEqual(set(evidence), {'kind', 'probe', 'font_sha256', 'inputs', 'disclosure'})

    def test_incomplete_inspector_defers_but_complete_inspector_completes_as_before(self):
        def partial(*, asset, manifest, probe):
            return dict(audio_checked=True, font_checked=False, disclosure_checked=True, scenes=[])
        svc, item, _, task_id = self.awaiting(inspect_video=partial)
        self.assertEqual(self.tasks.get(task_id)['state'], 'awaiting_review')
        self.assertEqual(self.contents.get(item['id'])['revision'], item['revision'])
        self.assertNotIn('audio_checked', self.stored(task_id)['candidate']['evidence'])
        svc = self.service(inspect_video=self.inspect)
        item, record = self.prepare_record()
        svc.create(item['id'], item['revision'], record['plan_revision'])
        done = svc.run_next()
        self.assertEqual((done['state'], done['review_status']), ('completed', 'not_checked'))

    def test_missing_inspector_without_option_stays_blocked(self):
        svc = self.service(defer_video_review=False)
        item, record = self.prepare_record()
        svc.create(item['id'], item['revision'], record['plan_revision'])
        row = svc.run_next()
        self.assertEqual((row['state'], row['reason_code']), ('blocked', 'video_unchecked'))
        self.assertEqual(self.contents.get(item['id'])['revision'], item['revision'])
        self.assertIsNone(self.tasks.get_row(row['task_id'])['result'])

    def test_wrong_media_is_blocked_even_when_deferring(self):
        def narrow(path):
            return dict(seconds=15, width=720, height=1280, has_audio=True)
        svc = self.service(probe=narrow)
        item, record = self.prepare_record()
        svc.create(item['id'], item['revision'], record['plan_revision'])
        row = svc.run_next()
        self.assertEqual((row['state'], row['reason_code']), ('blocked', 'video_dimensions_or_audio'))
        self.assertIsNone(self.tasks.get_row(row['task_id'])['result'])

    def test_deferred_evidence_cannot_pass_generic_video_contract(self):
        svc, _, _, task_id = self.awaiting()
        root, candidate = self.root_of(svc, task_id), self.stored(task_id)['candidate']
        item = dict(path=str(root / 'short.mp4'), filename='short.mp4', media_type='video/mp4', size=candidate['size'],
                    sha256=candidate['sha256'], evidence=candidate['evidence'])
        self.assertEqual(validate_production_result(dict(text='', assets=[item]), ('remotion_video',), root)['status'],
                         'blocked')

    # --- context / preview ---------------------------------------------------
    def test_review_context_and_video_have_exact_shape_and_no_internal_data(self):
        svc, item, record, task_id = self.awaiting()
        context = svc.review_context(task_id)
        self.assertEqual(set(context), CONTEXT)
        self.assertEqual((context['state'], context['review_status'], context['scene_count']),
                         ('awaiting_review', 'not_checked', 3))
        self.assertEqual(set(context['media']), MEDIA)
        self.assertEqual((context['media']['filename'], context['media']['media_type'], context['media']['size'],
                          context['media']['sha256']), ('short.mp4', 'video/mp4', len(MP4), hashlib.sha256(MP4).hexdigest()))
        self.assertEqual((context['media']['seconds'], context['media']['width'], context['media']['height'],
                          context['media']['has_audio']), (15, 1080, 1920, True))
        self.assertEqual(set(context['manifest']), MANIFEST)
        self.assertTrue(all(set(s) == SCENE for s in context['manifest']['scenes']))
        self.assertEqual([s['index'] for s in context['manifest']['scenes']], [1, 2, 3])
        self.assertRegex(context['context_fingerprint'], r'^[0-9a-f]{64}$')
        self.assertEqual(svc.review_context(task_id), context)
        text = json.dumps(context, ensure_ascii=False)
        for hidden in (str(self.root), 'media-artifacts', 'provenance', 'console_user', 'font_sha256'):
            self.assertNotIn(hidden, text)
        meta, raw = svc.review_video(task_id)
        self.assertEqual(meta, dict(filename='short.mp4', media_type='video/mp4', size=len(MP4),
                                    sha256=hashlib.sha256(MP4).hexdigest()))
        self.assertEqual(raw, MP4)
        self.assertEqual((self.runs, self.tasks.get(task_id)['state']), (1, 'awaiting_review'))

    def test_review_requires_awaiting_state(self):
        svc = self.service(inspect_video=self.inspect)
        item, record = self.prepare_record()
        task = svc.create(item['id'], item['revision'], record['plan_revision'])
        for action in (svc.review_context, svc.review_video):
            with self.assertRaises(ContractError) as caught:
                action(task['task_id'])
            self.assertEqual(caught.exception.code, 'video_review_unavailable')
        svc.run_next()
        with self.assertRaises(ContractError) as caught:
            svc.review_context(task['task_id'])
        self.assertEqual(caught.exception.code, 'video_review_unavailable')

    # --- 결정 ---------------------------------------------------------------
    def test_pass_registers_once_without_rerender_and_replays_read_only(self):
        svc, item, record, task_id = self.awaiting()
        fingerprint = svc.review_context(task_id)['context_fingerprint']
        done = svc.confirm_review(task_id, fingerprint, 'pass', dict(GOOD), '소리와 자막 확인')
        self.assertEqual(set(done), PUBLIC)
        self.assertEqual((done['state'], done['reason_code'], done['review_status']), ('completed', None, 'not_checked'))
        self.assertEqual(done['output_revision'], item['revision'] + 1)
        head = self.contents.get(item['id'])
        self.assertEqual(self.contents.read_asset(item['id'], head['revision'], done['asset_id'])[1], MP4)
        self.assertEqual(head['assets'][-1]['filename'], f'video-{task_id}.mp4')
        evidence = self.stored(task_id)['evidence']
        self.assertEqual(evidence['manual_review'], dict(actor='console_user', notes='소리와 자막 확인',
                                                         fingerprint=fingerprint, checks=GOOD))
        self.assertTrue(evidence['audio_checked'] and evidence['font_checked'])
        self.assertEqual((self.runs, self.factory_calls), (1, 1))
        with patch.object(self.contents, 'add_asset', side_effect=AssertionError):
            self.assertEqual(svc.confirm_review(task_id, fingerprint, 'pass', dict(GOOD), '소리와 자막 확인'), done)
            with self.assertRaises(ContractError) as caught:
                svc.confirm_review(task_id, fingerprint, 'pass', dict(GOOD), '다른 메모')
            self.assertEqual(caught.exception.code, 'video_review_conflict')
            with self.assertRaises(ContractError):
                svc.confirm_review(task_id, 'f' * 64, 'pass', dict(GOOD), '소리와 자막 확인')
        self.assertEqual(self.contents.get(item['id'])['revision'], head['revision'])

    def test_pass_actor_is_server_value_and_ingest_failure_resumes_without_render(self):
        svc, item, _, task_id = self.awaiting()
        with patch.object(self.contents, 'add_asset', side_effect=StoreError('storage_error')):
            row = self.confirm(svc, task_id, actor='local_reviewer')
        self.assertEqual(row['state'], 'rendered')
        self.assertEqual(self.stored(task_id)['evidence']['manual_review']['actor'], 'local_reviewer')
        self.assertEqual(svc.resume(task_id)['state'], 'completed')
        self.assertEqual(self.runs, 1)

    def test_changes_requested_preserves_candidate_without_registration_or_rerender(self):
        svc, item, record, task_id = self.awaiting()
        fingerprint = svc.review_context(task_id)['context_fingerprint']
        blocked = svc.confirm_review(task_id, fingerprint, 'changes_requested', dict(GOOD, audio_checked=False), '소리 크기 조정')
        self.assertEqual((blocked['state'], blocked['reason_code']), ('blocked', 'video_review_changes_requested'))
        self.assertEqual(self.contents.get(item['id'])['revision'], item['revision'])
        self.assertEqual((self.root_of(svc, task_id) / 'short.mp4').read_bytes(), MP4)
        self.assertEqual(self.stored(task_id)['changes_requested']['notes'], '소리 크기 조정')
        self.assertIsNone(svc.run_next())
        self.assertEqual(svc.resume(task_id)['state'], 'blocked')
        self.assertEqual(svc.create(item['id'], item['revision'], record['plan_revision'])['task_id'], task_id)
        self.assertEqual(svc.confirm_review(task_id, fingerprint, 'changes_requested', dict(GOOD, audio_checked=False),
                                            '소리 크기 조정'), blocked)
        with self.assertRaises(ContractError) as caught:
            svc.confirm_review(task_id, fingerprint, 'pass', dict(GOOD), '')
        self.assertEqual(caught.exception.code, 'video_review_conflict')
        self.assertEqual(self.runs, 1)

    def test_malformed_or_fake_confirmations_are_rejected_without_state_change(self):
        svc, _, _, task_id = self.awaiting()
        fingerprint = svc.review_context(task_id)['context_fingerprint']
        bad = [
            (fingerprint, 'pass', dict(GOOD, audio_checked=False), ''),
            (fingerprint, 'pass', {**GOOD, 'extra': True}, ''),
            (fingerprint, 'pass', {k: v for k, v in GOOD.items() if k != 'font_checked'}, ''),
            (fingerprint, 'pass', dict(GOOD, font_checked=1), ''),
            (fingerprint, 'changes_requested', dict(GOOD), '   '),
            (fingerprint, 'approve', dict(GOOD), ''),
            (fingerprint, 'pass', dict(GOOD), 'x\x00y'),
            (fingerprint, 'pass', dict(GOOD), '가' * 2001),
            (fingerprint.upper(), 'pass', dict(GOOD), ''),
            (fingerprint[:-1], 'pass', dict(GOOD), ''),
            (None, 'pass', dict(GOOD), ''),
        ]
        for args in bad:
            with self.subTest(args=str(args)[:40]), self.assertRaises(ContractError) as caught:
                svc.confirm_review(task_id, *args)
            self.assertEqual(caught.exception.code, 'invalid_video_review')
        for actor in ('', '  ', 'a\x00b', None):
            with self.subTest(actor=actor), self.assertRaises(ContractError):
                svc.confirm_review(task_id, fingerprint, 'pass', dict(GOOD), '', actor=actor)
        with self.assertRaises(ContractError) as caught:
            svc.confirm_review(task_id, 'a' * 64, 'pass', dict(GOOD), '')
        self.assertEqual(caught.exception.code, 'video_review_stale')
        self.assertEqual(self.tasks.get(task_id)['state'], 'awaiting_review')

    def test_confirm_shares_worker_lock_and_stale_version_is_rejected(self):
        svc, _, _, task_id = self.awaiting()
        fingerprint = svc.review_context(task_id)['context_fingerprint']
        with self.tasks.worker_lock():
            with self.assertRaises(ContractError) as caught:
                svc.confirm_review(task_id, fingerprint, 'pass', dict(GOOD), '')
            self.assertEqual(caught.exception.code, 'video_worker_busy')
        self.tamper(task_id, 'version', self.tasks.get_row(task_id)['version'] + 1)
        with self.assertRaises(ContractError) as caught:
            svc.confirm_review(task_id, fingerprint, 'pass', dict(GOOD), '')
        self.assertEqual(caught.exception.code, 'video_review_stale')
        self.assertEqual(self.tasks.get(task_id)['state'], 'awaiting_review')

    # --- 변조 / 오래된 입력 ----------------------------------------------------
    def assert_all_rejected(self, svc, task_id, fingerprint, code):
        for action in (lambda: svc.review_context(task_id), lambda: svc.review_video(task_id),
                       lambda: svc.confirm_review(task_id, fingerprint, 'pass', dict(GOOD), '')):
            with self.assertRaises(ContractError) as caught:
                action()
            self.assertEqual(caught.exception.code, code)
        self.assertEqual(self.tasks.get(task_id)['state'], 'awaiting_review')

    def test_changed_output_or_input_bytes_are_rejected(self):
        for target in ('short.mp4', 'input'):
            with self.subTest(target=target):
                svc, item, _, task_id = self.awaiting()
                fingerprint = svc.review_context(task_id)['context_fingerprint']
                root = self.root_of(svc, task_id)
                path = root / 'short.mp4' if target == 'short.mp4' else sorted(root.glob('*.png'))[0]
                path.write_bytes(path.read_bytes() + b'x')
                self.assert_all_rejected(svc, task_id, fingerprint, 'video_review_invalid')
                self.assertEqual(self.contents.get(item['id'])['revision'], item['revision'])

    def test_symlinked_output_is_rejected(self):
        svc, _, _, task_id = self.awaiting()
        fingerprint = svc.review_context(task_id)['context_fingerprint']
        output = self.root_of(svc, task_id) / 'short.mp4'
        other = output.with_name('other.mp4')
        other.write_bytes(MP4)
        output.unlink()
        output.symlink_to(other)
        self.assert_all_rejected(svc, task_id, fingerprint, 'video_review_invalid')

    def test_changed_head_or_plan_is_rejected(self):
        svc, item, record, task_id = self.awaiting()
        fingerprint = svc.review_context(task_id)['context_fingerprint']
        self.plans.save(item['id'], item['revision'], 1, {**record['plan'], 'footer': '검토 중 변경'})
        self.assert_all_rejected(svc, task_id, fingerprint, 'plan_changed')
        svc, item, record, task_id = self.awaiting()
        fingerprint = svc.review_context(task_id)['context_fingerprint']
        self.contents.update(item['id'], item['revision'], legacy.EDIT)
        self.assert_all_rejected(svc, task_id, fingerprint, 'content_changed')
        self.assertEqual(self.runs, 2)  # 검토 거부는 재렌더하지 않는다.

    def test_tampered_stored_candidate_fails_closed_without_leaking(self):
        svc, item, _, task_id = self.awaiting()
        fingerprint = svc.review_context(task_id)['context_fingerprint']
        good = self.stored(task_id)

        def variant(change):
            data = json.loads(json.dumps(good))
            change(data)
            return json.dumps(data)

        def fake_flags(d): d['candidate']['evidence'].update(audio_checked=True, font_checked=True)

        def drop_scene(d): d['manifest']['scenes'].pop()

        def drop_input(d): d['candidate']['evidence']['inputs'].pop()

        def wide(d): d['candidate']['evidence']['probe']['width'] = 1081

        def long(d): d['candidate']['evidence']['probe']['seconds'] = 21

        def no_disclosure(d): d['candidate']['evidence']['disclosure'] = '합성 아님'

        def foreign_path(d): d['candidate']['evidence']['inputs'][0]['path'] = '/etc/hosts'

        cases = [variant(f) for f in (fake_flags, drop_scene, drop_input, wide, long, no_disclosure, foreign_path)]
        cases += ['{"candidate":NaN,"manifest":{}}', '[]', 'not json', '{"candidate":{},"manifest":{}}']
        for value in cases:
            with self.subTest(value=value[:40]):
                self.tamper(task_id, 'result', value)
                for action in (lambda: svc.review_context(task_id), lambda: svc.confirm_review(
                        task_id, fingerprint, 'pass', dict(GOOD), '')):
                    with self.assertRaises(ContractError) as caught:
                        action()
                    self.assertEqual(caught.exception.code, 'video_review_invalid')
                    self.assertNotIn(str(self.root), str(caught.exception))
        self.tamper(task_id, 'prepared', '{"digest":"../../x"}')
        with self.assertRaises(ContractError) as caught:
            svc.review_video(task_id)
        self.assertEqual(caught.exception.code, 'video_review_invalid')
        self.assertEqual(self.contents.get(item['id'])['revision'], item['revision'])

    # --- 비활성 / 공개 ---------------------------------------------------------
    def test_disabled_service_does_no_io_for_review(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / 'never'
        svc = VideoTaskService(VideoTaskStore(root), self.contents, self.plans, enabled=False, defer_video_review=True)
        with patch.object(svc.store, 'get_row', side_effect=AssertionError):
            for action in (lambda: svc.review_context(str(uuid4())), lambda: svc.review_video(str(uuid4())),
                           lambda: svc.confirm_review(str(uuid4()), 'a' * 64, 'pass', dict(GOOD), '')):
                with self.assertRaises(ContractError) as caught:
                    action()
                self.assertEqual(caught.exception.code, 'video_disabled')
        self.assertFalse(root.exists())

    def test_public_projection_keeps_nine_fields_and_redacts_review_data(self):
        svc, item, _, task_id = self.awaiting()
        rows = [svc.get(task_id), *svc.list_for_content(item['id'])]
        text = json.dumps(rows, ensure_ascii=False)
        for row in rows:
            self.assertEqual(set(row), PUBLIC)
        for hidden in ('candidate', 'manifest', 'evidence', 'media-artifacts', 'inputs', 'provenance', 'font_sha256',
                       hashlib.sha256(MP4).hexdigest(), str(self.root)):
            self.assertNotIn(hidden, text)

    # --- schema 1 -> 2 -------------------------------------------------------
    def legacy_db(self, rows=2):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / 'legacy'
        root.mkdir()
        conn = sqlite3.connect(root / DB_NAME)
        for statement in LEGACY_DDL:
            conn.execute(statement)
        conn.execute('PRAGMA application_id=%d' % APPLICATION_ID)
        conn.execute('PRAGMA user_version=1')
        states = ('completed', 'blocked', 'unknown')
        for index in range(rows):
            conn.execute('INSERT INTO video_tasks(%s) VALUES(%s)' % (','.join(COLUMNS), ','.join('?' * len(COLUMNS))),
                         (str(uuid4()), 'intent%d' % index, 'personal', 'content%d' % index, 3, 'm' * 64, 2, 'p' * 64,
                          states[index % 3], 'media_render_blocked', '{"digest":"%s"}' % ('d' * 64),
                          '{"r":%d}' % index, 2 + index, 4 if index == 0 else None, 'asset' if index == 0 else None,
                          5 + index))
        conn.commit()
        conn.close()
        return root

    @staticmethod
    def dump(root):
        conn = sqlite3.connect(root / DB_NAME)
        conn.row_factory = sqlite3.Row
        try:
            rows = [dict(r) for r in conn.execute('SELECT rowid AS rid,* FROM video_tasks ORDER BY rowid')]
            return rows, conn.execute('PRAGMA user_version').fetchone()[0], dict(
                conn.execute("SELECT name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall())
        finally:
            conn.close()

    def test_schema1_reads_without_migration_and_initialize_preserves_every_row(self):
        root = self.legacy_db(3)
        before, version, _ = self.dump(root)
        self.assertEqual(version, 1)
        store = VideoTaskStore(root)
        self.assertEqual(store.get_row(before[0]['task_id'])['version'], 5)
        self.assertEqual(len(store.list_for_content('content1')), 1)
        self.assertEqual(self.dump(root)[1], 1)  # 읽기만으로는 migration하지 않는다.
        with self.assertRaises(ContractError):
            store.claim_next()
        store.initialize()
        after, version, objects = self.dump(root)
        self.assertEqual((version, after), (2, before))
        self.assertIn('awaiting_review', objects['video_tasks'])
        self.assertEqual(set(objects), {'video_tasks', 'video_tasks_content'})
        self.assertTrue(store.transition(before[0]['task_id'], ('completed',), state='awaiting_review',
                                         reason_code='video_review_required'))
        VideoTaskStore(root).initialize()  # 이미 schema 2면 그대로 통과한다.

    def test_foreign_schema_is_rejected_and_failed_migration_rolls_back(self):
        root = self.legacy_db(2)
        before = self.dump(root)
        with patch.object(VideoTaskStore, '_verify_migrated', side_effect=ContractError('video_storage_error')):
            store = VideoTaskStore(root)
            with self.assertRaises(ContractError) as caught:
                store.initialize()
        self.assertEqual(caught.exception.code, 'video_storage_error')
        self.assertFalse(store._initialized)
        self.assertEqual(self.dump(root), before)
        for sql in ("ALTER TABLE video_tasks ADD COLUMN extra TEXT", "PRAGMA application_id=7",
                    "ALTER TABLE video_tasks RENAME COLUMN reason_code TO reason"):
            foreign = self.legacy_db(1)
            conn = sqlite3.connect(foreign / DB_NAME)
            conn.execute(sql)
            conn.commit()
            conn.close()
            snapshot = (foreign / DB_NAME).read_bytes()
            with self.subTest(sql=sql), self.assertRaises(ContractError) as caught:
                VideoTaskStore(foreign).initialize()
            self.assertEqual(caught.exception.code, 'video_storage_foreign')
            self.assertEqual((foreign / DB_NAME).read_bytes(), snapshot)


if __name__ == '__main__':
    unittest.main()
