import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

from common.operations.content_store import StoreError
from common.operations.models import ContractError
from common.operations.video_tasks import DB_NAME, VideoTaskService, VideoTaskStore
from tests.operations import test_media_plans as fixture

MP4 = b'\x00\x00\x00\x18ftypisomfixture'
PUBLIC = {'task_id', 'state', 'reason_code', 'content_id', 'input_revision', 'plan_revision', 'output_revision',
          'asset_id', 'review_status'}
EDIT = {'title': '바뀐 제목', 'kind': 'short', 'series': '시리즈'}


class Boom(Exception):
    pass


class VideoTaskTests(unittest.TestCase):
    make_content = fixture.MediaPlanTests.make_content
    ready_plan = fixture.MediaPlanTests.ready_plan

    def setUp(self):
        fixture.MediaPlanTests.setUp(self)
        self.tasks = VideoTaskStore(self.root)
        self.tasks.initialize()
        self.mode, self.reason = 'ok', 'reuse_not_authorized'
        self.runs = self.factory_calls = 0
        self.started, self.release = threading.Event(), threading.Event()

    # --- 가짜 주입물: 실제 Remotion/ffprobe/네트워크는 쓰지 않는다 -----------------
    def factory(self, **kwargs):
        self.factory_calls += 1
        return self.runner

    def runner(self, *, manifest, artifact_root):
        self.runs += 1
        if self.mode == 'throw':
            raise Boom('secret /private/tmp/leak')
        if self.mode == 'blocked':
            return dict(status='blocked', reason_code=self.reason)
        if self.mode == 'wait':
            self.started.set()
            self.release.wait(10)
        path = Path(artifact_root) / 'short.mp4'
        path.write_bytes(MP4)
        return dict(path=str(path), font_sha256='a' * 64)

    @staticmethod
    def authorize(*, manifest, asset):
        return dict(authorized=True, reviewed=True, sha256=manifest['sha256'], source=manifest['source'],
                    reuse_request_id=manifest['reuse_request_id'])

    @staticmethod
    def probe(path):
        return dict(seconds=15, width=1080, height=1920, has_audio=True)

    @staticmethod
    def inspect(*, asset, manifest, probe):
        return dict(audio_checked=True, font_checked=True, disclosure_checked=True,
                    scenes=[dict(index=i, checked=True) for i in range(1, len(manifest['scenes']) + 1)])

    def service(self, **kwargs):
        options = dict(enabled=True, runner_factory=self.factory, reuse_authorization=self.authorize,
                       probe=self.probe, inspect_video=self.inspect)
        options.update(kwargs)
        return VideoTaskService(self.tasks, self.contents, self.plans, **options)

    def prepare_record(self):
        item, images, voice = self.make_content()
        self.plans.initialize()
        return item, self.plans.save(item['id'], item['revision'], 0, self.ready_plan(images, voice))

    def queued(self, svc=None):
        item, record = self.prepare_record()
        svc = svc or self.service()
        return svc, item, record, svc.create(item['id'], item['revision'], record['plan_revision'])

    def rendered_task(self):
        svc, item, record, task = self.queued()
        with patch.object(self.contents, 'add_asset', side_effect=StoreError('storage_error')):
            self.assertEqual(svc.run_next()['state'], 'rendered')
        return svc, item, task['task_id']

    def tamper(self, task_id, column, value):
        conn = sqlite3.connect(self.root / DB_NAME)
        try:
            conn.execute('UPDATE video_tasks SET %s=? WHERE task_id=?' % column, (value, task_id))
            conn.commit()
        finally:
            conn.close()

    # --- 저장소 -----------------------------------------------------------
    def test_constructor_and_reads_never_create_database(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / 'fresh'
        store = VideoTaskStore(root)
        self.assertFalse(root.exists())
        self.assertIsNone(store.get_row(str(uuid4())))
        self.assertIsNone(store.get(str(uuid4())))
        self.assertEqual(store.list_for_content('content'), [])
        self.assertFalse(root.exists())
        with self.assertRaises(ContractError):
            store.claim_next()
        store.initialize()
        conn = sqlite3.connect(root / DB_NAME)
        self.addCleanup(conn.close)
        self.assertEqual(conn.execute('PRAGMA application_id').fetchone()[0], 0x56494445)
        self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], 2)

    def test_foreign_database_and_symlinks_are_rejected(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        foreign = base / 'foreign'
        foreign.mkdir()
        conn = sqlite3.connect(foreign / DB_NAME)
        conn.execute('CREATE TABLE other(x)')
        conn.commit()
        conn.close()
        for action in (VideoTaskStore(foreign).initialize, lambda: VideoTaskStore(foreign).get_row(str(uuid4()))):
            with self.assertRaises(ContractError) as caught:
                action()
            self.assertEqual(caught.exception.code, 'video_storage_foreign')
        linked = base / 'linked'
        linked.mkdir()
        os.symlink(self.root / DB_NAME, linked / DB_NAME)
        with self.assertRaises(ContractError) as caught:
            VideoTaskStore(linked).initialize()
        self.assertEqual(caught.exception.code, 'video_storage_unsafe')
        os.symlink(base / 'linked', base / 'rootlink')
        with self.assertRaises(ContractError) as caught:
            VideoTaskStore(base / 'rootlink').initialize()
        self.assertEqual(caught.exception.code, 'video_storage_unsafe')

    def test_transition_is_compare_and_swap(self):
        _, _, _, task = self.queued()
        self.assertFalse(self.tasks.transition(task['task_id'], ('rendering',), state='failed',
                                               reason_code='media_prepare_failed'))
        self.assertEqual(self.tasks.get(task['task_id'])['state'], 'queued')
        self.assertTrue(self.tasks.transition(task['task_id'], ('queued',), state='failed',
                                              reason_code='media_prepare_failed'))
        for fields in (dict(state='failed', plan_hash='x'), dict(state='failed', reason_code='/etc/passwd'),
                       dict(state='nope'), dict(reason_code='media_prepare_failed')):
            with self.assertRaises(ContractError):
                self.tasks.transition(task['task_id'], ('failed',), **fields)

    def test_worker_lock_is_exclusive_and_refuses_symlink(self):
        with self.tasks.worker_lock():
            with self.assertRaises(ContractError) as caught:
                with self.tasks.worker_lock():
                    pass
            self.assertEqual(caught.exception.code, 'video_worker_busy')
        with self.tasks.worker_lock():
            pass
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / 'store'
        store = VideoTaskStore(root)
        store.initialize()
        (Path(tmp.name) / 'target').write_text('x')
        os.symlink(Path(tmp.name) / 'target', root / 'video-worker.lock')
        with self.assertRaises(ContractError) as caught:
            with store.worker_lock():
                pass
        self.assertEqual(caught.exception.code, 'video_storage_unsafe')

    # --- create -----------------------------------------------------------
    def test_create_requires_enabled_and_runner_factory(self):
        item, record = self.prepare_record()
        for options in (dict(enabled=False), dict(runner_factory=None), dict(runner_factory='not callable')):
            with self.assertRaises(ContractError) as caught:
                self.service(**options).create(item['id'], item['revision'], record['plan_revision'])
            self.assertEqual(caught.exception.code, 'video_renderer_unavailable')
        self.assertEqual(self.tasks.list_for_content(item['id']), [])

    def test_create_only_queues_without_copy_or_render(self):
        svc, item, record, task = self.queued()
        self.assertEqual(set(task), PUBLIC)
        self.assertEqual((task['state'], task['review_status'], task['plan_revision']), ('queued', 'not_checked', 1))
        self.assertEqual(task['input_revision'], item['revision'])
        self.assertEqual((self.runs, self.factory_calls), (0, 0))
        self.assertFalse((self.root / 'media-artifacts').exists())
        self.assertEqual(self.contents.get(item['id'])['revision'], item['revision'])

    def test_same_intent_replays_and_other_intent_conflicts_while_nonterminal(self):
        svc, item, record, task = self.queued()
        again = svc.create(item['id'], item['revision'], record['plan_revision'])
        self.assertEqual(again['task_id'], task['task_id'])
        self.assertEqual(len(self.tasks.list_for_content(item['id'])), 1)
        changed = self.plans.save(item['id'], item['revision'], 1, {**record['plan'], 'footer': '다른 계획'})
        with self.assertRaises(ContractError) as caught:
            svc.create(item['id'], item['revision'], changed['plan_revision'])
        self.assertEqual(caught.exception.code, 'video_task_conflict')
        self.assertEqual(len(self.tasks.list_for_content(item['id'])), 1)

    def test_concurrent_creates_claim_one_task(self):
        item, record = self.prepare_record()
        svc, ids, errors = self.service(), [], []
        barrier = threading.Barrier(4)

        def work():
            barrier.wait()
            try:
                ids.append(svc.create(item['id'], item['revision'], record['plan_revision'])['task_id'])
            except Exception as exc:  # pragma: no cover - 실패 시 단언에서 드러난다.
                errors.append(exc)
        threads = [threading.Thread(target=work) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(20)
        self.assertEqual(errors, [])
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual(len(self.tasks.list_for_content(item['id'])), 1)

    def test_create_checks_head_plan_readiness_and_existence(self):
        item, record = self.prepare_record()
        svc = self.service()
        cases = [(item['id'], item['revision'], 2, 'plan_revision_conflict'),
                 ('managed_missing', 1, 1, 'content_not_found')]
        self.contents.update(item['id'], item['revision'], EDIT)
        cases.append((item['id'], item['revision'], 1, 'content_revision_conflict'))
        bare, images, _ = self.make_content(voice=False)
        saved = self.plans.save(bare['id'], bare['revision'], 0, self.ready_plan(images, None))
        cases.append((bare['id'], bare['revision'], saved['plan_revision'], 'media_inputs_required'))
        for content_id, revision, plan_revision, code in cases:
            with self.subTest(code=code), self.assertRaises(ContractError) as caught:
                svc.create(content_id, revision, plan_revision)
            self.assertEqual(caught.exception.code, code)
        self.assertEqual(self.tasks.list_for_content(item['id']), [])
        self.assertEqual(self.tasks.list_for_content(bare['id']), [])

    # --- run_next ---------------------------------------------------------
    def test_disabled_run_next_and_resume_do_no_io(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / 'never'
        svc = VideoTaskService(VideoTaskStore(root), self.contents, self.plans, enabled=False,
                               runner_factory=self.factory)
        with patch('common.operations.video_tasks.prepare_short_media', side_effect=AssertionError):
            for action in (svc.run_next, lambda: svc.resume(str(uuid4()))):
                with self.assertRaises(ContractError) as caught:
                    action()
                self.assertEqual(caught.exception.code, 'video_disabled')
        self.assertFalse(root.exists())

    def test_missing_runner_at_run_next_leaves_task_queued(self):
        svc, item, record, task = self.queued()
        with self.assertRaises(ContractError) as caught:
            self.service(runner_factory=None).run_next()
        self.assertEqual(caught.exception.code, 'video_renderer_unavailable')
        self.assertEqual(self.tasks.get(task['task_id'])['state'], 'queued')
        self.assertFalse((self.root / 'media-artifacts').exists())

    def test_run_next_renders_through_existing_contract_and_cas_registers_exact_video(self):
        svc, item, record, task = self.queued()
        before = self.contents.get(item['id'])
        done = svc.run_next()
        self.assertEqual(set(done), PUBLIC)
        self.assertEqual((done['state'], done['reason_code'], done['review_status']), ('completed', None, 'not_checked'))
        self.assertEqual(done['output_revision'], item['revision'] + 1)
        head = self.contents.get(item['id'])
        added = head['assets'][-1]
        self.assertEqual((added['id'], added['filename'], added['media_type']),
                         (done['asset_id'], f'video-{task["task_id"]}.mp4', 'video/mp4'))
        self.assertEqual(self.contents.read_asset(item['id'], head['revision'], added['id'])[1], MP4)
        self.assertEqual((added['size'], added['sha256']), (len(MP4), hashlib.sha256(MP4).hexdigest()))
        self.assertEqual(head['assets'][:-1], before['assets'])
        for key in ('title', 'kind', 'series', 'status', 'original', 'variants', 'sources', 'owner_account_id'):
            self.assertEqual(head[key], before[key])
        self.assertEqual((self.runs, self.factory_calls), (1, 1))
        self.assertIsNone(svc.run_next())
        replay = svc.create(item['id'], item['revision'], record['plan_revision'])
        self.assertEqual((replay['task_id'], replay['state']), (task['task_id'], 'completed'))
        self.assertEqual((self.runs, self.contents.get(item['id'])['revision']), (1, head['revision']))

    def test_blocked_result_is_preserved_with_safe_reason_and_never_rerendered(self):
        for reason, expected in (('reuse_not_authorized', 'reuse_not_authorized'),
                                 ('/Users/me/secret.mp4', 'media_render_blocked')):
            with self.subTest(reason=reason):
                self.mode, self.reason, self.runs = 'blocked', reason, 0
                svc, item, record, task = self.queued()
                blocked = svc.run_next()
                self.assertEqual((blocked['state'], blocked['reason_code']), ('blocked', expected))
                self.assertEqual(self.contents.get(item['id'])['revision'], item['revision'])
                self.assertIsNone(svc.run_next())
                self.assertEqual(svc.resume(task['task_id'])['state'], 'blocked')
                self.assertEqual(svc.create(item['id'], item['revision'], 1)['task_id'], task['task_id'])
                self.assertEqual(self.runs, 1)

    def test_renderer_exception_is_unknown_sanitized_and_not_retried(self):
        self.mode = 'throw'
        svc, item, record, task = self.queued()
        row = svc.run_next()
        self.assertEqual((row['state'], row['reason_code']), ('unknown', 'render_outcome_unknown'))
        self.assertNotIn('secret', repr(row) + repr(self.tasks.list_for_content(item['id'])))
        self.assertEqual(svc.resume(task['task_id'])['state'], 'unknown')
        self.assertIsNone(svc.run_next())
        self.assertEqual(self.runs, 1)
        changed = self.plans.save(item['id'], item['revision'], 1, {**record['plan'], 'footer': '다시'})
        with self.assertRaises(ContractError) as caught:
            svc.create(item['id'], item['revision'], changed['plan_revision'])
        self.assertEqual(caught.exception.code, 'video_task_conflict')

    def test_plan_changed_after_queue_does_not_render(self):
        svc, item, record, task = self.queued()
        self.plans.save(item['id'], item['revision'], 1, {**record['plan'], 'footer': '대기 중 변경'})
        row = svc.run_next()
        self.assertEqual((row['state'], row['reason_code']), ('content_changed', 'plan_changed'))
        self.assertEqual((self.runs, self.factory_calls), (0, 0))
        self.assertFalse((self.root / 'media-artifacts').exists())

    def test_different_head_marks_content_changed_before_and_after_render(self):
        svc, item, record, task = self.queued()
        self.contents.update(item['id'], item['revision'], EDIT)
        row = svc.run_next()
        self.assertEqual((row['state'], row['reason_code']), ('content_changed', 'content_changed'))
        self.assertEqual(self.runs, 0)
        svc, item, task_id = self.rendered_task()
        self.contents.update(item['id'], item['revision'], EDIT)
        self.assertEqual(svc.resume(task_id)['state'], 'content_changed')
        self.assertEqual(self.runs, 1)
        self.assertEqual(self.contents.get(item['id'])['revision'], item['revision'] + 1)

    def test_only_one_worker_renders_at_a_time(self):
        self.mode = 'wait'
        svc, item, record, task = self.queued()
        outcome = []
        worker = threading.Thread(target=lambda: outcome.append(svc.run_next()))
        worker.start()
        self.assertTrue(self.started.wait(10))
        with self.assertRaises(ContractError) as caught:
            svc.run_next()
        self.assertEqual(caught.exception.code, 'video_worker_busy')
        self.release.set()
        worker.join(20)
        self.assertEqual(outcome[0]['state'], 'completed')
        self.assertEqual(self.runs, 1)

    # --- resume / 복구 ----------------------------------------------------
    def test_rendered_resume_only_ingests_and_never_renders(self):
        svc, item, task_id = self.rendered_task()
        self.assertEqual(self.contents.get(item['id'])['revision'], item['revision'])
        done = svc.resume(task_id)
        self.assertEqual((done['state'], done['output_revision']), ('completed', item['revision'] + 1))
        self.assertEqual((self.runs, self.factory_calls), (1, 1))
        queued, _, _, other = self.queued()
        self.assertEqual(queued.resume(other['task_id'])['state'], 'queued')
        self.assertEqual(self.runs, 1)

    def test_crash_after_ingest_recovers_read_only(self):
        svc, item, record, task = self.queued()
        real = self.contents.add_asset

        def add_then_crash(*args, **kwargs):
            real(*args, **kwargs)
            raise StoreError('storage_error')
        with patch.object(self.contents, 'add_asset', side_effect=add_then_crash):
            self.assertEqual(svc.run_next()['state'], 'rendered')
        head = self.contents.get(item['id'])
        self.assertEqual(head['revision'], item['revision'] + 1)
        with patch.object(self.contents, 'add_asset', side_effect=AssertionError):
            done = svc.resume(task['task_id'])
        self.assertEqual((done['state'], done['output_revision']), ('completed', head['revision']))
        self.assertEqual(done['asset_id'], head['assets'][-1]['id'])
        self.assertEqual(self.contents.get(item['id'])['revision'], head['revision'])
        self.assertEqual(self.runs, 1)

    def test_tampered_stored_metadata_is_not_trusted(self):
        bad_result = json.dumps(dict(filename='../../x.mp4', media_type='video/mp4', size=len(MP4),
                                     sha256='0' * 64, evidence={}))
        nan_result = ('{"filename":"short.mp4","media_type":"video/mp4","size":NaN,"sha256":"x","evidence":{}}')
        for column, value in (('result', bad_result), ('result', nan_result),
                              ('prepared', json.dumps({'digest': '../' * 4})), ('prepared', '{"digest":1}')):
            with self.subTest(column=column, value=value[:30]):
                svc, item, task_id = self.rendered_task()
                self.tamper(task_id, column, value)
                row = svc.resume(task_id)
                self.assertEqual((row['state'], row['reason_code']), ('failed', 'render_artifact_invalid'))
                self.assertEqual(self.contents.get(item['id'])['revision'], item['revision'])

    # --- 공개 projection --------------------------------------------------
    def test_public_projection_redacts_internal_fields(self):
        svc, item, record, task = self.queued()
        done = svc.run_next()
        text = json.dumps([done, svc.get(task['task_id']), svc.list_for_content(item['id'])], ensure_ascii=False)
        for row in (done, svc.get(task['task_id']), *svc.list_for_content(item['id'])):
            self.assertEqual(set(row), PUBLIC)
        for hidden in ('media-artifacts', 'plan_hash', 'intent', 'manifest', 'digest', '.mp4', hashlib.sha256(MP4).hexdigest(),
                       record['manifest_hash'], str(self.root), 'evidence', 'scenes'):
            self.assertNotIn(hidden, text)
        self.assertIsNone(svc.get(str(uuid4())))
        with self.assertRaises(ContractError) as caught:
            svc.get('../../etc/passwd')
        self.assertEqual(caught.exception.code, 'invalid_task')


if __name__ == '__main__':
    unittest.main()
