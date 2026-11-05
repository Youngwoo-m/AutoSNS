"""외부 전송 없는 TikTok 로컬 준비물의 문맥·원문·명시 자산 결속."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import unittest
from unittest.mock import patch

from common.operations.models import ContractError
from common.publishers.tiktok_payloads import (TikTokPreparationContext, PREPARED_KEYS, MAX_ASSET_BYTES,
    build_tiktok_payload, select_tiktok_assets, validate_tiktok_caption)
from tests.publishers.test_instagram_media_sources import context


def ctx(**over):
    args=dict(platform='tiktok',connection_id='dept.tiktok',target_id=None,owner_account_id='personal',
              destination_account_id='dept',content_id='content-1',content_revision=2,manifest_hash='a'*64,
              publication_purpose='initial',schedule_slot='slot',options={'tiktok':{'asset_ids':['video-2']}})
    return TikTokPreparationContext(**{**args,**over})


def asset(identifier='video-2'):
    return dict(id=identifier,sha256=hashlib.sha256(identifier.encode()).hexdigest(),size=16,media_type='video/mp4',
                filename='그대로.mp4',private_path='외부에 반환하지 않음')


def snapshot(current=None,text=' 캡션 https://example.com/ 그대로\n'):
    current=current or ctx()
    return dict(id=current.content_id,revision=current.content_revision,manifest_hash=current.manifest_hash,
                owner_account_id=current.owner_account_id,original=text,variants=[],assets=[asset('video-1'),asset()])


class TikTokPayloadTests(unittest.TestCase):
    def test_unknown_target_and_opaque_target_local_preparation_source_unchanged(self):
        for target in (None,'opaque-open-id_abc.xyz'):
            with self.subTest(target=target):
                current=ctx(target_id=target);source=snapshot(current);before=deepcopy(source)
                with patch('builtins.open',side_effect=AssertionError('파일 조회 금지')), \
                     patch('subprocess.run',side_effect=AssertionError('프로세스 금지')):
                    result=build_tiktok_payload(source,current)
                self.assertEqual(set(result),set(PREPARED_KEYS));self.assertEqual(len(result),15)
                self.assertEqual(result['target_id'],target)
                self.assertEqual(result['delivery_mode'],'local_preparation')
                self.assertEqual(result['caption'],source['original'])
                self.assertEqual(result['caption_sha256'],hashlib.sha256(source['original'].encode()).hexdigest())
                self.assertEqual(result['owner_account_id'],'personal');self.assertEqual(result['destination_account_id'],'dept')
                self.assertEqual(result['asset']['id'],'video-2')
                self.assertEqual(set(result['asset']),{'id','sha256','size','media_type'})
                self.assertEqual(result['media_sha256'],[asset()['sha256']])
                self.assertEqual(source,before)

    def test_real_publication_context_still_only_local_preparation(self):
        current=context(platform='tiktok',connection_id='dept.tiktok',target_id='open-id_opaque',options={'tiktok':{'asset_ids':['video-2']}})
        result=build_tiktok_payload(snapshot(current),current)
        self.assertEqual(result['delivery_mode'],'local_preparation')
        self.assertNotIn('authorization',result);self.assertNotIn('privacy_level',result)

    def test_cross_destination_variant_unique_and_all_mappings(self):
        current=ctx();source=snapshot(current)
        chosen=dict(platform='tiktok',destination_account_id='dept',text='  학과용 원문  ')
        source['variants']=[dict(platform='tiktok',destination_account_id='personal',text='다른 계정'),
                            dict(platform='instagram',destination_account_id='dept',text='다른 플랫폼'),chosen]
        self.assertEqual(build_tiktok_payload(source,current)['caption'],chosen['text'])
        for variants in (source['variants']+[chosen],[chosen,None],'bad'):
            with self.subTest(variants=variants):
                with self.assertRaises(ContractError):build_tiktok_payload({**source,'variants':variants},current)

    def test_snapshot_binding_and_context_validation(self):
        current=ctx();source=snapshot(current)
        with self.assertRaises(ContractError):build_tiktok_payload(source,object())
        for change in ({'id':'other'},{'revision':True},{'revision':3},{'manifest_hash':'b'*64},{'owner_account_id':'dept'}):
            with self.subTest(change=change):
                with self.assertRaises(ContractError):build_tiktok_payload({**source,**change},current)
        for change in ({'target_id':''},{'content_revision':True},{'manifest_hash':'\ud800'},{'options':None}):
            with self.subTest(change=repr(change)):
                with self.assertRaises(ContractError):ctx(**change)
        with self.assertRaises(ContractError):build_tiktok_payload(source,replace(current,platform='x'))

    def test_explicit_one_asset_selection_no_automatic_pick_or_extra_options(self):
        source=snapshot()
        self.assertEqual(select_tiktok_assets(source,{'asset_ids':['video-1']})[0]['id'],'video-1')
        for selection in (None,{}, {'asset_ids':[]},{'asset_ids':['video-1','video-2']},{'asset_ids':['video-2'],'format':'video'},
                          {'asset_ids':'video-2'},{'asset_ids':[True]},{'asset_ids':['../video-2']},{'asset_ids':['missing']}):
            with self.subTest(selection=selection):
                with self.assertRaises(ContractError):select_tiktok_assets(source,selection)
        for options in ({},{'tiktok':{'asset_ids':['video-2'],'privacy_level':'SELF_ONLY'}},
                        {'tiktok':{'asset_ids':['video-2']},'visibility':'PUBLIC_TO_EVERYONE'},
                        {'tiktok':{'asset_ids':['video-2']},'upload_consent':True}):
            with self.subTest(options=options):
                with self.assertRaises(ContractError):build_tiktok_payload(source,ctx(options=options))
        for visibility in ('public','private','unlisted'):
            result=build_tiktok_payload(source,ctx(options={'tiktok':{'asset_ids':['video-2']},'visibility':visibility}))
            self.assertNotIn('privacy_level',result)

    def test_asset_metadata_types_size_hash_duplicates_and_unselected_assets(self):
        for changes in ({'size':True},{'size':0},{'size':MAX_ASSET_BYTES+1},{'sha256':'bad'},{'media_type':'video/webm'}):
            with self.subTest(changes=changes):
                source=snapshot();source['assets'][1].update(changes)
                with self.assertRaises(ContractError):select_tiktok_assets(source,{'asset_ids':['video-2']})
        source=snapshot();source['assets'][1]['size']=MAX_ASSET_BYTES
        self.assertEqual(select_tiktok_assets(source,{'asset_ids':['video-2']})[0]['size'],MAX_ASSET_BYTES)
        source['assets'].append(asset())
        with self.assertRaises(ContractError):select_tiktok_assets(source,{'asset_ids':['video-2']})
        with self.assertRaises(ContractError):select_tiktok_assets({'assets':[asset(),None]},{'asset_ids':['video-2']})

    def test_caption_utf16_boundary_preserves_whitespace_and_rejects_invalid(self):
        for text in ('a'*2200,'😀'*1100,'e\u0301'*1100,' 空白とURL https://example.com/\n'):
            self.assertIs(validate_tiktok_caption(text),text)
        for text in ('a'*2201,'😀'*1101,'a'*2199+'😀',' \n\t','bad\x00','\ud800',None,False):
            with self.subTest(text=repr(text)[:50]):
                with self.assertRaises(ContractError):validate_tiktok_caption(text)

    def test_context_options_freeze_does_not_mutate_selection(self):
        options={'tiktok':{'asset_ids':['video-2']}}
        current=ctx(options=options);options['tiktok']['asset_ids'][0]='video-1'
        self.assertEqual(build_tiktok_payload(snapshot(current),current)['asset']['id'],'video-2')
