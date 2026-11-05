from contextlib import closing
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from common.operations import production_media
from common.operations.media_plan_runtime import prepare_short_media
from common.operations.models import ContractError
from common.operations.reuse_approvals import (
    DB_NAME, ManagedReuseAuthorizer, ReuseApprovalService, ReuseApprovalStore)
from tests.operations import test_media_plans as fixture

PNG = fixture.PNG
DENIED = 'reuse_not_authorized'
PUBLIC_KEYS = {'content_id', 'content_revision', 'manifest_hash', 'owner_account_id', 'asset_id', 'sha256',
               'approval_revision', 'approved_revision', 'rights_confirmed', 'visual_checked', 'notes',
               'status', 'review_method'}


class ReuseApprovalTests(unittest.TestCase):
    make_content = fixture.MediaPlanTests.make_content
    ready_plan = fixture.MediaPlanTests.ready_plan

    def setUp(self):
        fixture.MediaPlanTests.setUp(self)
        self.approvals = ReuseApprovalStore(self.root)
        self.service = ReuseApprovalService(self.approvals, self.contents, self.plans)
        self.auth = ManagedReuseAuthorizer(self.service)

    # --- helpers ----------------------------------------------------------
    def assertCode(self, code, fn, *args, **kwargs):
        with self.assertRaises(ContractError) as ctx:
            fn(*args, **kwargs)
        self.assertEqual(ctx.exception.code, code)
        return ctx.exception

    def listing(self):
        return sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob('*'))

    def raw(self):
        return closing(sqlite3.connect(self.root / DB_NAME))

    def rows(self, item):
        return {r['asset_id']: r for r in self.service.get_for_content(item['id'], item['revision'])['items']}

    def approve(self, item, asset_id, expected=0, rights=True, visual=True, notes='확인', **kwargs):
        return self.service.save(item['id'], item['revision'], asset_id, expected, rights, visual, notes, **kwargs)

    def prepared(self, images=4):
        item, imgs, voice = self.make_content(images=images)
        self.plans.initialize()
        plan = self.plans.save(item['id'], item['revision'], 0, self.ready_plan(imgs, voice))
        return item, imgs, plan, prepare_short_media(plan, content_store=self.contents, attempt_id='a1')

    def manifest(self, prepared, asset_id, **override):
        reg = prepared.scene_assets[asset_id]
        manifest = dict(path=reg.path, sha256=reg.sha256, source=reg.source, reuse_request_id=reg.reuse_request_id)
        manifest.update(override)
        return manifest

    def call(self, prepared, asset_id, **override):
        manifest = self.manifest(prepared, asset_id, **override)
        return self.auth(manifest=manifest, asset=dict(sha256=prepared.scene_assets[asset_id].sha256))

    # --- tests ------------------------------------------------------------
    def test_default_read_is_empty_and_creates_nothing(self):
        item, imgs, voice = self.make_content()
        before = self.listing()
        result = self.service.get_for_content(item['id'], item['revision'])
        self.assertEqual(set(result), {'items'})
        self.assertEqual([r['asset_id'] for r in result['items']], imgs)  # 음성은 제외, 이미지만
        for row in result['items']:
            self.assertEqual(set(row), PUBLIC_KEYS)
            self.assertEqual((row['approval_revision'], row['approved_revision'], row['notes']), (0, None, ''))
            self.assertIs(row['rights_confirmed'], False)
            self.assertIs(row['visual_checked'], False)
            self.assertEqual((row['status'], row['review_method']), ('not_approved', 'manual'))
            self.assertEqual((row['content_revision'], row['manifest_hash']), (item['revision'], item['manifest_hash']))
        sha = result['items'][0]['sha256']
        self.assertIsNone(self.approvals.latest('personal', item['id'], imgs[0], sha))
        self.assertEqual(self.approvals.history('personal', item['id'], imgs[0], sha), [])
        self.assertEqual(before, self.listing())
        self.assertFalse((self.root / DB_NAME).exists())

    def test_constructors_and_uninitialized_save_write_nothing(self):
        item, imgs, voice = self.make_content()
        before = self.listing()
        ReuseApprovalService(ReuseApprovalStore(self.root), self.contents, self.plans)
        missing = ReuseApprovalStore(self.root.parent / 'never-created')
        self.assertIsNone(missing.latest('personal', item['id'], imgs[0], '0' * 64))
        self.assertFalse(missing.root.exists())
        self.assertCode('reuse_storage_error', self.approve, item, imgs[0])
        self.assertEqual(before, self.listing())
        self.assertFalse((self.root / DB_NAME).exists())
        with self.assertRaises(ContractError):
            ReuseApprovalService(missing, self.contents, self.plans)  # 루트가 다르면 거부

    def test_explicit_save_uses_cas_and_keeps_append_only_history(self):
        item, imgs, voice = self.make_content()
        self.approvals.initialize()
        first = self.approve(item, imgs[0])
        self.assertEqual((first['approval_revision'], first['approved_revision'], first['status']),
                         (1, item['revision'], 'approved'))
        self.assertCode('reuse_approval_conflict', self.approve, item, imgs[0], expected=0)
        revoked = self.approve(item, imgs[0], expected=1, rights=False, notes='철회')
        self.assertEqual((revoked['approval_revision'], revoked['status'], revoked['notes']), (2, 'not_approved', '철회'))
        with self.raw() as conn:
            rows = conn.execute('SELECT approval_revision,rights_confirmed,actor,approved_manifest_hash '
                                'FROM reuse_approvals ORDER BY approval_revision').fetchall()
            self.assertEqual(rows, [(1, 1, 'console_user', item['manifest_hash']),
                                    (2, 0, 'console_user', item['manifest_hash'])])
            for statement in ('UPDATE reuse_approvals SET notes=\'x\'', 'DELETE FROM reuse_approvals'):
                with self.assertRaises(sqlite3.DatabaseError):
                    conn.execute(statement)
        sha = revoked['sha256']
        history = self.approvals.history('personal', item['id'], imgs[0], sha)
        self.assertEqual([h['approval_revision'] for h in history], [1, 2])
        self.assertIs(history[0]['rights_confirmed'], True)  # 이전 행은 그대로 보존
        self.assertEqual(self.rows(item)[imgs[1]]['approval_revision'], 0)  # 다른 이미지 영향 없음

    def test_public_row_hides_internal_fields_and_needs_both_flags(self):
        item, imgs, voice = self.make_content()
        self.approvals.initialize()
        statuses = []
        for expected, (rights, visual) in enumerate(((True, False), (False, True), (False, False), (True, True))):
            row = self.approve(item, imgs[0], expected=expected, rights=rights, visual=visual, actor='ops-user')
            self.assertEqual(set(row), PUBLIC_KEYS)
            statuses.append(row['status'])
            dumped = json.dumps(row)
            for secret in ('ops-user', str(self.root), 'actor'):
                self.assertNotIn(secret, dumped)
        self.assertEqual(statuses, ['not_approved'] * 3 + ['approved'])
        self.assertEqual(self.rows(item)[imgs[0]]['review_method'], 'manual')
        with self.raw() as conn:
            self.assertEqual(conn.execute('SELECT DISTINCT actor FROM reuse_approvals').fetchall(), [('ops-user',)])

    def test_save_validation_and_lookup_errors_write_nothing(self):
        item, imgs, voice = self.make_content()
        self.approvals.initialize()
        base = dict(content_id=item['id'], content_revision=item['revision'], asset_id=imgs[0], expected_revision=0,
                    rights_confirmed=True, visual_checked=True, notes='x')
        invalid = [dict(rights_confirmed=1), dict(rights_confirmed='true'), dict(visual_checked=None),
                   dict(expected_revision=True), dict(expected_revision=-1), dict(expected_revision='0'),
                   dict(expected_revision=0.0), dict(notes='a\x00b'), dict(notes='x' * 2001), dict(notes=None),
                   dict(notes='\ud800'), dict(content_revision=True), dict(content_revision=0), dict(content_id=''),
                   dict(asset_id=None), dict(actor=''), dict(actor=None), dict(actor='a\x00')]
        for change in invalid:
            self.assertCode('invalid_reuse_request', self.service.save, **{**base, **change})
        for extra in (dict(owner_account_id='dept'), dict(sha256='0' * 64), dict(status='approved'), dict(path='/tmp/x')):
            with self.assertRaises(TypeError):
                self.service.save(**base, **extra)
        self.assertCode('content_not_found', self.service.save, **{**base, 'content_id': 'managed_' + '0' * 32})
        self.assertCode('asset_not_found', self.service.save, **{**base, 'asset_id': 'asset_' + '0' * 32})
        self.assertCode('asset_not_found', self.service.save, **{**base, 'asset_id': voice})  # 이미지가 아님
        with self.raw() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM reuse_approvals').fetchone()[0], 0)
        saved = self.service.save(**{**base, 'notes': '가' * 2000})
        self.assertEqual(len(saved['notes']), 2000)

    def test_new_version_carries_record_only_for_same_owner_content_id_and_hash(self):
        item, imgs, voice = self.make_content()
        self.approvals.initialize()
        self.approve(item, imgs[0])
        newer = self.contents.update(item['id'], item['revision'], {'title': '수정', 'kind': 'short'})
        self.assertNotEqual(newer['manifest_hash'], item['manifest_hash'])
        carried = self.rows(newer)[imgs[0]]
        self.assertEqual((carried['status'], carried['approval_revision'], carried['approved_revision']),
                         ('approved', 1, item['revision']))  # 승인 당시 버전을 그대로 보인다
        self.assertEqual((carried['content_revision'], carried['manifest_hash']), (newer['revision'], newer['manifest_hash']))
        self.assertEqual(self.rows(newer)[imgs[1]]['status'], 'not_approved')
        self.assertCode('content_revision_conflict', self.service.save, item['id'], item['revision'], imgs[0], 1, True, True, '')
        again = self.service.save(item['id'], newer['revision'], imgs[0], 1, True, True, '재확인')
        self.assertEqual((again['approval_revision'], again['approved_revision']), (2, newer['revision']))
        withnew = self.contents.add_asset(item['id'], newer['revision'], 'new.png', 'image/png', PNG + b'\x09' * 8)
        fresh = self.rows(withnew)[withnew['assets'][-1]['id']]
        self.assertEqual((fresh['status'], fresh['approval_revision'], fresh['approved_revision']), ('not_approved', 0, None))
        self.assertEqual(self.rows(withnew)[imgs[0]]['status'], 'approved')
        old = self.rows(item)[imgs[0]]  # 옛 버전 조회도 가능: 문맥은 그 버전, 기록은 최신 승인
        self.assertEqual((old['content_revision'], old['manifest_hash'], old['status'], old['approved_revision']),
                         (item['revision'], item['manifest_hash'], 'approved', newer['revision']))

    def test_other_owner_and_other_content_are_isolated_even_with_identical_bytes(self):
        a, aimgs, _ = self.make_content('personal')
        b, bimgs, _ = self.make_content('dept')
        c, cimgs, _ = self.make_content('personal')
        self.approvals.initialize()
        sha = self.approve(a, aimgs[0])['sha256']
        self.assertEqual(self.rows(b)[bimgs[0]]['sha256'], sha)  # 바이트가 같아도
        for other, ids in ((b, bimgs), (c, cimgs)):
            for row in self.rows(other).values():
                self.assertEqual((row['status'], row['approval_revision'], row['approved_revision']), ('not_approved', 0, None))
        self.assertIsNotNone(self.approvals.latest('personal', a['id'], aimgs[0], sha))
        self.assertIsNone(self.approvals.latest('dept', a['id'], aimgs[0], sha))
        self.assertIsNone(self.approvals.latest('personal', c['id'], aimgs[0], sha))
        self.assertIsNone(self.approvals.latest('personal', a['id'], bimgs[0], sha))

    def test_changed_or_mismatched_bytes_are_denied(self):
        item, imgs, plan, prepared = self.prepared()
        self.approvals.initialize()
        for asset_id in imgs[:3]:
            self.approve(item, asset_id)
        self.assertTrue(self.call(prepared, imgs[0])['authorized'])
        self.assertCode(DENIED, self.call, prepared, imgs[0], sha256='0' * 64)
        self.assertCode(DENIED, self.auth, manifest=self.manifest(prepared, imgs[0]), asset=dict(sha256='0' * 64))
        stored = [p for p in self.root.rglob(imgs[0]) if p.is_file() and p.parent.parent.name == str(item['revision'])]
        self.assertEqual(len(stored), 1)
        stored[0].write_bytes(PNG + b'tampered')
        self.assertCode(DENIED, self.call, prepared, imgs[0])
        self.assertCode('reuse_storage_error', self.service.get_for_content, item['id'], item['revision'])
        self.assertCode('reuse_storage_error', self.approve, item, imgs[0], expected=1)

    def test_unapproved_and_revoked_images_are_denied(self):
        item, imgs, plan, prepared = self.prepared()
        for asset_id in imgs[:3]:
            self.assertCode(DENIED, self.call, prepared, asset_id)  # DB 미존재
        self.assertFalse((self.root / DB_NAME).exists())
        self.approvals.initialize()
        self.approve(item, imgs[0], rights=True, visual=False)
        self.assertCode(DENIED, self.call, prepared, imgs[0])  # 플래그 하나만 참
        self.approve(item, imgs[0], expected=1)
        self.approve(item, imgs[1])
        self.assertTrue(self.call(prepared, imgs[0])['reviewed'])
        self.approve(item, imgs[0], expected=2, rights=False)  # 명시 철회
        self.assertCode(DENIED, self.call, prepared, imgs[0])
        self.assertTrue(self.call(prepared, imgs[1])['authorized'])
        self.approve(item, imgs[0], expected=3)
        self.assertTrue(self.call(prepared, imgs[0])['authorized'])

    def test_plan_hash_request_binding_and_scene_exclusion(self):
        item, imgs, plan, prepared = self.prepared()
        self.approvals.initialize()
        for asset_id in imgs:
            self.approve(item, asset_id)
        self.assertTrue(self.call(prepared, imgs[0])['authorized'])
        self.assertCode(DENIED, self.call, prepared, imgs[0], reuse_request_id='media-plan:' + '0' * 64)
        # 승인된 imgs[3]은 실제 계획 digest를 붙여도 scene에 없으면 거부한다.
        unplanned = 'managed-content:%s:r%d:%s' % (item['id'], item['revision'], imgs[3])
        sha3 = hashlib.sha256(PNG + bytes([3]) * 8).hexdigest()
        self.assertCode(DENIED, self.auth, manifest=self.manifest(prepared, imgs[0], source=unplanned, sha256=sha3),
                        asset=dict(sha256=sha3))
        # 계획이 바뀌면 이전 등록은 오래된 요청이다.
        edited = copy.deepcopy(plan['plan'])
        edited['scenes'][0]['seconds'] = 4
        second = self.plans.save(item['id'], item['revision'], 1, edited)
        self.assertCode(DENIED, self.call, prepared, imgs[0])
        prepared2 = prepare_short_media(second, content_store=self.contents, attempt_id='a2')
        self.assertTrue(self.call(prepared2, imgs[0])['authorized'])
        # imgs[0]을 계획에서 빼면 새 digest를 붙여도 거부한다.
        replaced = copy.deepcopy(plan['plan'])
        replaced['scenes'] = [fixture.scene(imgs[1]), fixture.scene(imgs[2]), fixture.scene(imgs[3], 'diagram')]
        third = self.plans.save(item['id'], item['revision'], 2, replaced)
        prepared3 = prepare_short_media(third, content_store=self.contents, attempt_id='a3')
        self.assertCode(DENIED, self.call, prepared2, imgs[0])
        reg1, reg0 = prepared3.scene_assets[imgs[1]], prepared.scene_assets[imgs[0]]
        self.assertCode(DENIED, self.auth, asset=dict(sha256=reg0.sha256),
                        manifest=dict(path=reg0.path, sha256=reg0.sha256, source=reg0.source,
                                      reuse_request_id=reg1.reuse_request_id))
        self.assertTrue(self.call(prepared3, imgs[3])['authorized'])

    def test_authorizer_accepts_real_prepare_registrations_and_never_reads_manifest_path(self):
        item, imgs, plan, prepared = self.prepared()
        self.approvals.initialize()
        for asset_id in imgs[:3]:
            self.approve(item, asset_id)
        for asset_id in imgs[:3]:
            reg = prepared.scene_assets[asset_id]
            result = self.call(prepared, asset_id)
            self.assertEqual(result, dict(authorized=True, reviewed=True, sha256=reg.sha256, source=reg.source,
                                          reuse_request_id=reg.reuse_request_id))
            production_media._authorize_reuse(self.manifest(prepared, asset_id), dict(sha256=reg.sha256), self.auth)
        outside = self.root.parent / 'outside.png'
        outside.write_bytes(b'secret')
        reads = []
        original = Path.read_bytes

        def spy(path_self):
            reads.append(Path(path_self))
            return original(path_self)

        with patch.object(Path, 'read_bytes', spy):
            for bad in (str(outside), '/etc/passwd', '../../outside.png', str(self.root / '..' / 'outside.png')):
                self.assertTrue(self.call(prepared, imgs[0], path=bad)['authorized'])
        self.assertTrue(reads)
        for path in reads:
            self.assertTrue(path.resolve().is_relative_to(self.root.resolve()), path)
            self.assertNotEqual(path.resolve(), outside.resolve())

    def test_malformed_tampered_and_cross_content_requests_get_one_fixed_error(self):
        item, imgs, plan, prepared = self.prepared()
        other, oimgs, _ = self.make_content('dept')
        self.approvals.initialize()
        for asset_id in imgs[:3]:
            self.approve(item, asset_id)
        self.approve(other, oimgs[0])
        reg = prepared.scene_assets[imgs[0]]
        good = self.manifest(prepared, imgs[0])
        prefix = 'managed-content:%s:r%d:' % (item['id'], item['revision'])
        cases = [None, 'x', [], {**good, 'extra': 1}, {k: v for k, v in good.items() if k != 'path'},
                 {**good, 'source': prefix + '../x'}, {**good, 'source': reg.source + 'x'},
                 {**good, 'source': reg.source.replace('managed-content', 'managed-other')},
                 {**good, 'source': 'managed-content:%s:r0:%s' % (item['id'], imgs[0])},
                 {**good, 'source': 'managed-content:%s:r0%d:%s' % (item['id'], item['revision'], imgs[0])},
                 {**good, 'source': 'managed-content:%s:r%d:%s' % (item['id'], item['revision'] + 1, imgs[0])},
                 {**good, 'source': 'managed-content:%s:r%d:%s' % (other['id'], other['revision'], imgs[0])},
                 {**good, 'source': prefix + oimgs[0]},
                 {**good, 'source': 'managed-content:%s:r%d:%s' % (other['id'], other['revision'], oimgs[0])},
                 {**good, 'sha256': 5}, {**good, 'sha256': reg.sha256.upper()},
                 {**good, 'reuse_request_id': 'media-plan:' + 'A' * 64}, {**good, 'reuse_request_id': 'x'}]
        for manifest in cases:
            error = self.assertCode(DENIED, self.auth, manifest=manifest, asset=dict(sha256=reg.sha256))
            self.assertEqual(str(error), DENIED)
            for leak in (item['id'], other['id'], imgs[0], str(self.root)):
                self.assertNotIn(leak, str(error))
        for asset in (None, {}, dict(sha256='0' * 64), dict(sha256=None)):
            self.assertCode(DENIED, self.auth, manifest=good, asset=asset)

    def test_foreign_symlink_and_corrupt_storage_are_rejected_untouched(self):
        item, imgs, voice = self.make_content()
        db = self.root / DB_NAME
        with closing(sqlite3.connect(db)) as conn:
            conn.execute('CREATE TABLE other(x)')
            conn.commit()
        foreign = db.read_bytes()
        self.assertCode('reuse_storage_error', self.approvals.initialize)
        self.assertCode('reuse_storage_error', self.approvals.latest, 'personal', item['id'], imgs[0], '0' * 64)
        self.assertCode('reuse_storage_error', self.service.get_for_content, item['id'], item['revision'])
        self.assertEqual(db.read_bytes(), foreign)
        db.unlink()
        target = self.root.parent / 'target.sqlite3'
        target.write_bytes(b'')
        db.symlink_to(target)
        self.assertCode('reuse_storage_error', self.approvals.initialize)
        self.assertCode('reuse_storage_error', self.approvals.latest, 'personal', item['id'], imgs[0], '0' * 64)
        self.assertEqual(target.read_bytes(), b'')
        db.unlink()
        link = self.root.parent / 'root-link'
        link.symlink_to(self.root, target_is_directory=True)
        linked = ReuseApprovalStore(link)
        self.assertCode('reuse_storage_error', linked.initialize)
        self.assertCode('reuse_storage_error', linked.latest, 'personal', item['id'], imgs[0], '0' * 64)
        self.assertFalse(db.exists())
        db.write_bytes(b'')  # 빈 파일은 정상 초기화 대상이다.
        self.approvals.initialize()
        self.approvals.initialize()  # 멱등
        sha = self.approve(item, imgs[0])['sha256']
        with self.raw() as conn:
            conn.execute('DROP TRIGGER reuse_approvals_no_update')
            conn.commit()
        self.assertCode('reuse_storage_error', ReuseApprovalStore(self.root).latest, 'personal', item['id'], imgs[0], sha)
        db.unlink()
        fresh = ReuseApprovalStore(self.root)
        fresh.initialize()
        with self.raw() as conn:
            conn.execute("INSERT INTO reuse_approvals VALUES('personal',?,?,?,1,1.5,?,'x',1,1,'',?)",
                         (item['id'], imgs[0], sha, item['manifest_hash'], 'now'))
            conn.commit()
        self.assertCode('reuse_storage_error', fresh.latest, 'personal', item['id'], imgs[0], sha)


if __name__ == '__main__':
    unittest.main()
