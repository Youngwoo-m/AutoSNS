"""실제 격리 콘텐츠·계획과 가짜 검사기로 TikTok 로컬 준비 경계를 확인한다."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import tempfile
import unittest

from common.operations.content_store import ContentStore, StoreError
from common.operations.ledger import Ledger
from common.operations.tiktok_preparation import TikTokPreparationService

NOW=datetime(2026,11,4,tzinfo=timezone.utc)
VIDEO=b'\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isommp42'
CAPTION='  학과 TikTok 원문 https://example.com/\n'
PUBLIC_KEYS={'plan_id','owner_account_id','destination_account_id','connection_id','content_id','content_revision',
             'manifest_hash','caption','caption_sha256','asset','asset_url','preparation_hash','status','publication_enabled',
             'technical_check_available','technical_check'}
TECHNICAL=dict(width=1080,height=1920,fps=30,duration_ms=16000,video_codec='h264',audio_codec='aac')


class Probe:
    def __init__(self,callback=None,result=None):
        self.calls=[];self.callback=callback;self.result=TECHNICAL if result is None else result
    def inspect(self,raw):
        self.calls.append(raw)
        if self.callback:self.callback()
        return deepcopy(self.result)


def create_plan(contents,ledger,*,raw=VIDEO,owner='personal',slot='fixture',selection=True):
    item=contents.create(owner,dict(title='비공개 준비 원고',kind='short',original='원본 보존',
        variants=[dict(destination_account_id='dept',platform='tiktok',text=CAPTION)]))
    item=contents.add_asset(item['id'],item['revision'],'private-original.mp4','video/mp4',raw)
    body=dict(content_id=item['id'],revision=item['revision'],manifest_hash=item['manifest_hash'],
        connection_id='dept.tiktok',publication_purpose='initial',schedule_slot=slot,
        scheduled_at='2026-11-04T10:00:00+09:00',timezone='Asia/Seoul',
        options={'tiktok':{'asset_ids':[item['assets'][0]['id']]}} if selection else {})
    if owner=='personal':body['crosspost_rule_id']='geoai-short.tiktok'
    return item,ledger.create_or_get_delivery(body)


class TikTokPreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'managed';self.contents=ContentStore(self.root);self.contents.initialize()
        self.ledger=Ledger(self.root,content_store=self.contents);self.ledger.initialize()
        self.item,self.plan=create_plan(self.contents,self.ledger)
        self.probe=None
        self.service=self.make_service()

    def make_service(self,probe=None,plans=None,registry=None):
        return TikTokPreparationService(self.contents,plans or self.ledger.get_delivery,registry or self.ledger.registry,
                                        probe=probe,clock=lambda:NOW)

    def assert_code(self,code,call):
        with self.assertRaises(StoreError) as caught:call()
        self.assertEqual(caught.exception.code,code)

    def update_head(self):
        return self.contents.update(self.item['id'],self.item['revision'],dict(title='검사 중 변경',kind='short',original='변경 원문'))

    def test_get_readonly_exact_projection_unknown_target_and_cross_owner(self):
        connection=self.ledger.registry().connections['dept.tiktok']
        self.assertFalse(connection.enabled);self.assertIsNone(connection.target_id)
        before=self.contents.get(self.item['id']);plan_before=self.ledger.get_delivery(self.plan['id'])
        files_before={str(p.relative_to(self.root)) for p in self.root.rglob('*')}
        value=self.service.get(self.plan['id'])
        self.assertEqual(set(value),PUBLIC_KEYS)
        self.assertEqual(value['owner_account_id'],'personal');self.assertEqual(value['destination_account_id'],'dept')
        self.assertEqual(value['caption'],CAPTION)
        self.assertEqual(value['caption_sha256'],hashlib.sha256(CAPTION.encode()).hexdigest())
        self.assertEqual(value['status'],'local_preparation_only');self.assertIs(value['publication_enabled'],False)
        self.assertIsNone(value['technical_check']);self.assertIs(value['technical_check_available'],False)
        asset=value['asset'];self.assertEqual(set(asset),{'id','sha256','size','media_type'})
        self.assertEqual(asset['sha256'],hashlib.sha256(VIDEO).hexdigest());self.assertEqual(asset['size'],len(VIDEO))
        self.assertEqual(value['asset_url'],f"/api/v2/contents/{self.item['id']}/revisions/{self.item['revision']}/assets/{asset['id']}")
        self.assertNotIn('private-original.mp4',str(value));self.assertNotIn(str(self.root),str(value))
        self.assertNotIn('target_id',value);self.assertNotIn('token',str(value));self.assertNotIn('uploaded',str(value))
        self.assertEqual(self.contents.get(self.item['id']),before)
        self.assertEqual(self.ledger.get_delivery(self.plan['id']),plan_before)
        self.assertEqual(files_before,{str(p.relative_to(self.root)) for p in self.root.rglob('*')})

    def test_check_unavailable_and_explicit_fake_probe_never_persists(self):
        subject=self.service.get(self.plan['id'])['preparation_hash']
        self.assert_code('storage_error',lambda:self.service.check(self.plan['id'],{'preparation_hash':subject}))
        probe=Probe();service=self.make_service(probe)
        before=self.ledger.get_delivery(self.plan['id'])
        self.assertIsNone(service.get(self.plan['id'])['technical_check']);self.assertEqual(probe.calls,[])
        result=service.check(self.plan['id'],{'preparation_hash':subject})
        self.assertEqual(probe.calls,[VIDEO]);self.assertEqual(set(result['technical_check']),set(TECHNICAL)|{'checked_at'})
        self.assertEqual(result['technical_check']['checked_at'],NOW.isoformat())
        self.assertFalse(result['publication_enabled']);self.assertEqual(self.ledger.get_delivery(self.plan['id']),before)
        self.assertIsNone(service.get(self.plan['id'])['technical_check'])

    def test_stale_plan_version_registry_or_source_head_rejected_before_probe(self):
        for change in ('plan','registry','head'):
            with self.subTest(change=change):
                probe=Probe();plan=deepcopy(self.plan);registry=self.ledger.registry()
                state={'plan':plan,'registry':registry}
                service=self.make_service(probe,plans=lambda _:deepcopy(state['plan']),registry=lambda:state['registry'])
                subject=service.get(self.plan['id'])['preparation_hash']
                if change=='plan':state['plan']['version']+=1
                elif change=='registry':state['registry']=replace(registry,revision=registry.revision+'-changed')
                else:self.update_head()
                self.assert_code('conflict',lambda:service.check(self.plan['id'],{'preparation_hash':subject}))
                self.assertEqual(probe.calls,[])

    def test_source_changes_during_probe_rejects_result(self):
        probe=Probe(self.update_head);service=self.make_service(probe)
        subject=service.get(self.plan['id'])['preparation_hash']
        self.assert_code('conflict',lambda:service.check(self.plan['id'],{'preparation_hash':subject}))
        self.assertEqual(probe.calls,[VIDEO])

    def test_cancelled_missing_legacy_no_selection_and_dept_owner(self):
        self.assert_code('not_found',lambda:self.service.get('missing'))
        self.ledger.cancel(self.plan['id'],self.plan['version'])
        self.assert_code('not_found',lambda:self.service.get(self.plan['id']))
        item,plan=create_plan(self.contents,self.ledger,owner='dept',slot='legacy',selection=False)
        self.assertEqual(plan['options'],{})
        self.assert_code('invalid',lambda:self.service.get(plan['id']))
        item,plan=create_plan(self.contents,self.ledger,owner='dept',slot='dept')
        self.assertEqual(self.service.get(plan['id'])['owner_account_id'],'dept')

    def test_real_asset_hash_tampering_and_malformed_ftyp_rejected(self):
        item,plan=create_plan(self.contents,self.ledger,raw=b'\x00\x00\x00\x80ftypisom',slot='bad-signature')
        self.assert_code('storage_error',lambda:self.service.get(plan['id']))
        path=next(p for p in self.root.rglob(self.item['assets'][0]['id']) if p.is_file())
        path.write_bytes(VIDEO[:-1]+b'x')
        self.assert_code('storage_error',lambda:self.service.get(self.plan['id']))

    def test_bad_check_body_or_probe_result_is_safe(self):
        probe=Probe(result={**TECHNICAL,'private_path':'secret'});service=self.make_service(probe)
        subject=service.get(self.plan['id'])['preparation_hash']
        for body in ({},{'preparation_hash':subject,'actor':'admin'},[],{'preparation_hash':True}):
            with self.subTest(body=body):
                self.assert_code('conflict' if body=={'preparation_hash':True} else 'invalid',lambda:service.check(self.plan['id'],body))
        self.assertEqual(probe.calls,[])
        self.assert_code('storage_error',lambda:service.check(self.plan['id'],{'preparation_hash':subject}))
