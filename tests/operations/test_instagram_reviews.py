"""실제 ContentStore 자산과 임시 append-only 최종 검토 원장. 외부 호출 없음."""
import copy
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch
from common.operations.content_store import ContentStore
from common.operations.models import Registry,Connection,ContractError
from common.operations.runtime_models import PublicationContext
from common.operations.instagram_reviews import InstagramReviewStore,InstagramReviewService
from common.publishers.instagram_payloads import InstagramPreparationContext,build_instagram_payload

NOW=datetime(2026,11,2,tzinfo=timezone.utc)
CHECKS=dict(rights_confirmed=True,visual_checked=True,caption_checked=True,composition_checked=True,audio_checked=False)
PUBLIC_KEYS={'plan_id','content_id','content_revision','manifest_hash','owner_account_id','destination_account_id','connection_id','target_id','media_format','caption','assets','subject_hash','review_revision','decision','checks','notes','review_method','status','audio_required'}
class InstagramReviewTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)/'managed'
        self.contents=ContentStore(self.root);self.contents.initialize()
        self.item=self.contents.create('personal',dict(title='카드',kind='card',original='원본',variants=[dict(destination_account_id='dept',platform='instagram',text='배포 캡션')]))
        for name,mime,raw in (('one.jpg','image/jpeg',b'\xff\xd8\xffimage1'),('two.jpg','image/jpeg',b'\xff\xd8\xffimage2'),('short.mp4','video/mp4',b'\x00\x00\x00\x18ftyp'+b'\x00'*16)):
            self.item=self.contents.add_asset(self.item['id'],self.item['revision'],name,mime,raw)
        self.ids=[asset['id'] for asset in self.item['assets']]
        self.registry=Registry('registry',{'personal':{},'dept':{}},{},{},{'dept.instagram':Connection('dept.instagram','dept','instagram',target_id='123')},{},{},{})
        self.plan=dict(id='plan1',source='managed',schedule_kind='local_plan',content_id=self.item['id'],revision=self.item['revision'],manifest_hash=self.item['manifest_hash'],owner_account_id='personal',destination_account_id='dept',connection_id='dept.instagram',platform='instagram',publication_purpose='initial',schedule_slot='main',options=dict(instagram=dict(format='image',asset_ids=[self.ids[0]])),status='pending',version=1,execution_enabled=False)
        self.store=InstagramReviewStore(self.root)
        self.service=InstagramReviewService(self.store,self.contents,lambda ident:copy.deepcopy(self.plan) if ident=='plan1' else None,lambda:self.registry,lambda:NOW)
    def body(self,**changes):
        current=self.service.get('plan1')
        values=dict(expected_review_revision=current['review_revision'],subject_hash=current['subject_hash'],decision='approved',checks=dict(CHECKS),notes='검토 기록')
        values.update(changes);return values
    def context(self,**changes):
        fields=dict(content_id=self.item['id'],content_revision=self.item['revision'],manifest_hash=self.item['manifest_hash'],owner_account_id='personal',destination_account_id='dept',connection_id='dept.instagram',target_id='123',publication_purpose='initial',schedule_slot='main',options=self.plan['options'],schedule_condition={'kind':'immediate'},registry_revision='registry',policy_revision='policy',auth_checked_at=NOW,auth_expires_at=NOW+timedelta(hours=1),review_report_hashes=('source-review','calc-review'),run_id='run',platform='instagram')
        fields.update(changes);return PublicationContext(**fields)
    def approve(self,**changes):self.store.initialize();return self.service.record('plan1',self.body(**changes))
    def test_get_is_read_only_fixed_public_projection_without_fake_auth(self):
        before=self.contents.get(self.item['id']);current=self.service.get('plan1')
        self.assertEqual(set(current),PUBLIC_KEYS);self.assertEqual(current['status'],'not_reviewed');self.assertEqual(current['review_revision'],0)
        self.assertIsNone(current['decision']);self.assertEqual(current['review_method'],'manual');self.assertIs(current['audio_required'],False)
        self.assertEqual(current['caption'],'배포 캡션');self.assertEqual([a['id'] for a in current['assets']],[self.ids[0]])
        self.assertFalse((self.root/'instagram-reviews.sqlite3').exists());self.assertEqual(before,self.contents.get(self.item['id']))
        self.assertNotIn('actor',current);self.assertNotIn('path',str(current))
    def test_approved_composition_authorizes_actual_context_only_and_revocation_blocks(self):
        before=self.contents.get(self.item['id']);approved=self.approve();self.assertEqual(approved['status'],'approved');self.assertEqual(approved['review_revision'],1)
        ctx=self.context();prepared=build_instagram_payload(self.item,ctx)
        self.assertTrue(self.service.authorize(ctx,prepared))
        authless=InstagramPreparationContext(**{k:getattr(ctx,k) for k in ('platform','connection_id','target_id','owner_account_id','destination_account_id','content_id','content_revision','manifest_hash','publication_purpose','schedule_slot','options')})
        self.assertFalse(self.service.authorize(authless,prepared))
        revoked=self.service.record('plan1',self.body(decision='revoked',checks={k:False for k in CHECKS}))
        self.assertEqual(revoked['status'],'revoked');self.assertEqual(revoked['review_revision'],2);self.assertFalse(self.service.authorize(ctx,prepared))
        self.assertEqual(before,self.contents.get(self.item['id']))
    def test_record_requires_explicit_initialize_and_cas(self):
        body=self.body()
        with self.assertRaises(ContractError):self.service.record('plan1',body)
        self.assertFalse((self.root/'instagram-reviews.sqlite3').exists())
        self.store.initialize();self.service.record('plan1',body)
        with self.assertRaises(ContractError) as caught:self.service.record('plan1',body)
        self.assertEqual(caught.exception.code,'instagram_review_conflict')
    def test_four_checks_and_video_audio_check_are_required_but_not_auto_filled(self):
        self.store.initialize()
        for key in tuple(CHECKS)[:4]:
            with self.assertRaises(ContractError):self.service.record('plan1',self.body(checks={**CHECKS,key:False}))
        self.plan['options']['instagram']=dict(format='reels',asset_ids=[self.ids[2]])
        self.assertTrue(self.service.get('plan1')['audio_required'])
        with self.assertRaises(ContractError):self.service.record('plan1',self.body())
        approved=self.service.record('plan1',self.body(checks={**CHECKS,'audio_checked':True}));self.assertEqual(approved['status'],'approved')
    def test_changed_selection_order_caption_target_or_content_has_new_unreviewed_subject(self):
        self.plan['options']['instagram']=dict(format='carousel',asset_ids=self.ids[:2]);approved=self.approve()
        self.plan['options']['instagram']['asset_ids']=list(reversed(self.ids[:2]))
        changed=self.service.get('plan1');self.assertNotEqual(changed['subject_hash'],approved['subject_hash']);self.assertEqual(changed['status'],'not_reviewed')
        ctx=self.context();self.assertFalse(self.service.authorize(ctx,build_instagram_payload(self.item,ctx)))
        self.registry=replace(self.registry,connections={'dept.instagram':replace(self.registry.connections['dept.instagram'],target_id='456')})
        changed=self.service.get('plan1');self.assertEqual(changed['target_id'],'456');self.assertEqual(changed['status'],'not_reviewed')
        self.assertFalse(self.service.authorize(ctx,build_instagram_payload(self.item,ctx)))
    def test_wrong_body_hash_extra_actor_flags_notes_and_revision_are_rejected(self):
        self.store.initialize()
        for changes in ({'subject_hash':'a'*64},{'expected_review_revision':True},{'decision':'pass'},{'checks':{**CHECKS,'visual_checked':1}},{'checks':{'rights_confirmed':True}},{'notes':'\ud800'},{'notes':'x'*2001},{'actor':'client'},{'review_method':'auto'}):
            with self.assertRaises(ContractError):self.service.record('plan1',self.body(**changes))
        self.assertEqual(self.service.get('plan1')['review_revision'],0)
    def test_missing_or_unverified_target_is_explicitly_rejected(self):
        for target in (None,'not-numeric'):
            self.registry=replace(self.registry,connections={'dept.instagram':replace(self.registry.connections['dept.instagram'],target_id=target)})
            with self.assertRaises(ContractError) as caught:self.service.get('plan1')
            self.assertEqual(caught.exception.code,'instagram_target_unverified')
        self.assertFalse((self.root/'instagram-reviews.sqlite3').exists())
    def test_cancelled_missing_plan_and_other_account_are_not_reviewed(self):
        with self.assertRaises(ContractError):self.service.get('missing')
        self.plan['status']='cancelled'
        with self.assertRaises(ContractError):self.service.get('plan1')
        self.plan['status']='pending';self.plan['destination_account_id']='personal'
        with self.assertRaises(ContractError):self.service.get('plan1')
    def test_new_content_revision_cannot_use_old_plan_or_approval(self):
        self.approve();ctx=self.context();prepared=build_instagram_payload(self.item,ctx)
        self.contents.update(self.item['id'],self.item['revision'],dict(title='새 원고',kind='card',original='본문'))
        with self.assertRaises(ContractError):self.service.get('plan1')
        self.assertFalse(self.service.authorize(ctx,prepared))
    def test_actual_asset_bytes_are_reverified_for_get_record_and_authorize(self):
        self.approve();ctx=self.context();prepared=build_instagram_payload(self.item,ctx);body=self.body();original=self.contents.read_asset
        def tamper(*args):
            meta,raw=original(*args);return meta,raw+b'changed'
        with patch.object(self.contents,'read_asset',side_effect=tamper):
            with self.assertRaises(ContractError):self.service.get('plan1')
            with self.assertRaises(ContractError):self.service.record('plan1',body)
            self.assertFalse(self.service.authorize(ctx,prepared))
    def test_authorize_rejects_prepared_forgery_and_wrong_current_registry(self):
        self.approve();ctx=self.context();prepared=build_instagram_payload(self.item,ctx)
        for patch_ in ({'target_id':'456'},{'owner_account_id':'dept'},{'caption':'edited'},{'assets':list(reversed(self.item['assets']))},{'extra':'client'}):
            self.assertFalse(self.service.authorize(ctx,{**prepared,**patch_}))
        self.registry=replace(self.registry,revision='new-registry');self.assertFalse(self.service.authorize(ctx,prepared))
    def test_store_is_append_only_strict_and_private_actor_is_not_projected(self):
        approved=self.approve();latest=self.store.latest(approved['subject_hash']);self.assertEqual(latest['actor'],'console_user')
        self.assertNotIn('actor',approved)
        db=sqlite3.connect(self.root/'instagram-reviews.sqlite3')
        try:
            for sql in ('UPDATE instagram_reviews SET decision=\'revoked\'','DELETE FROM instagram_reviews'):
                with self.assertRaises(sqlite3.IntegrityError):db.execute(sql)
        finally:db.close()
    def test_store_inert_foreign_schema_symlink_and_other_workspace_rejected(self):
        root=self.root.parent/'empty';store=InstagramReviewStore(root);self.assertIsNone(store.latest('a'*64));self.assertFalse(root.exists())
        root.mkdir();db=sqlite3.connect(root/'instagram-reviews.sqlite3');db.execute('CREATE TABLE keep(value)');db.commit();db.close()
        with self.assertRaises(ContractError):store.initialize()
        (root/'instagram-reviews.sqlite3').unlink();outside=self.root.parent/'outside';(root/'instagram-reviews.sqlite3').symlink_to(outside)
        with self.assertRaises(ContractError):store.initialize()
        self.assertFalse(outside.exists())
        with self.assertRaises(ContractError):InstagramReviewService(InstagramReviewStore(self.root.parent/'other'),self.contents,lambda _:self.plan,lambda:self.registry,lambda:NOW)
    def test_reads_do_not_call_native_network_or_modify_source_reviews(self):
        before=self.contents.get(self.item['id'])
        with patch('socket.socket',side_effect=AssertionError('network')),patch('ctypes.CDLL',side_effect=AssertionError('native')):
            self.service.get('plan1')
        self.assertEqual(before,self.contents.get(self.item['id']))

    def test_concurrent_expected_revision_appends_only_one_manual_review(self):
        self.store.initialize();body=self.body()
        def record(_):
            try:return self.service.record('plan1',body)['status']
            except ContractError as exc:return exc.code
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(record,range(2)))
        self.assertEqual(sorted(results),['approved','instagram_review_conflict'])
        self.assertEqual(self.service.get('plan1')['review_revision'],1)

    def test_caption_new_version_has_new_subject_and_does_not_inherit_review(self):
        approved=self.approve()
        latest=self.contents.update(self.item['id'],self.item['revision'],dict(title='카드',kind='card',original='원본',variants=[dict(destination_account_id='dept',platform='instagram',text='다른 캡션')]))
        self.plan.update(revision=latest['revision'],manifest_hash=latest['manifest_hash'])
        current=self.service.get('plan1');self.assertEqual(current['caption'],'다른 캡션')
        self.assertNotEqual(current['subject_hash'],approved['subject_hash']);self.assertEqual(current['status'],'not_reviewed')

    def test_other_connection_destination_or_purpose_requires_its_own_composition_review(self):
        self.approve()
        connections=dict(self.registry.connections)
        connections['personal.instagram']=Connection('personal.instagram','personal','instagram',target_id='123')
        self.registry=replace(self.registry,connections=connections)
        for changes in ({'connection_id':'personal.instagram','destination_account_id':'personal'},{'publication_purpose':'followup'},{'schedule_slot':'other'}):
            ctx=self.context(**changes);prepared=build_instagram_payload(self.item,ctx)
            self.assertFalse(self.service.authorize(ctx,prepared))
