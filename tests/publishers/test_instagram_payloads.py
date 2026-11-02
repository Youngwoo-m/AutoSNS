"""명시 Instagram 매체 선택의 순수 준비 계약. 실제 파일·권한·API를 검증하지 않는다."""
import copy
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import hashlib
import unittest
from common.operations.models import ContractError
from common.operations.runtime_models import PublicationContext
from common.publishers.instagram_payloads import build_instagram_payload

NOW=datetime(2026,11,2,tzinfo=timezone.utc)
KEYS={'platform','connection_id','target_id','owner_account_id','destination_account_id','content_id','content_revision','manifest_hash','publication_purpose','schedule_slot','caption','caption_sha256','media_format','assets','media_sha256'}
def asset(identifier,mime='image/jpeg',sha='a',**changes):return dict(id=identifier,filename=identifier+'.bin',media_type=mime,size=50,sha256=sha*64,**changes)
def snapshot():return dict(id='content',revision=2,manifest_hash='manifest',owner_account_id='personal',original='원본 캡션',variants=[dict(destination_account_id='dept',platform='instagram',text=' 학과용 캡션\n#안전 ')],assets=[asset('image1'),asset('image2',sha='b'),asset('video1','video/mp4','c'),asset('png1','image/png','d')])
def context(format='image',ids=None,**changes):
    values=dict(content_id='content',content_revision=2,manifest_hash='manifest',owner_account_id='personal',destination_account_id='dept',connection_id='dept.instagram',target_id='123',publication_purpose='initial',schedule_slot='main',options={'instagram':{'format':format,'asset_ids':['image1'] if ids is None else ids}},schedule_condition={'kind':'immediate'},registry_revision='registry',policy_revision='policy',auth_checked_at=NOW,auth_expires_at=NOW+timedelta(hours=1),review_report_hashes=('r',),run_id='run',platform='instagram')
    values.update(changes);return PublicationContext(**values)

class InstagramPayloadTests(unittest.TestCase):
    def test_image_explicit_selection_caption_and_cross_account_are_bound(self):
        source=snapshot();before=copy.deepcopy(source);result=build_instagram_payload(source,context())
        self.assertEqual(set(result),KEYS);self.assertEqual(result['caption'],' 학과용 캡션\n#안전 ')
        self.assertEqual(result['caption_sha256'],hashlib.sha256(result['caption'].encode()).hexdigest())
        self.assertEqual(result['owner_account_id'],'personal');self.assertEqual(result['destination_account_id'],'dept')
        self.assertEqual(result['assets'],[dict(id='image1',media_type='image/jpeg',size=50,sha256='a'*64)])
        self.assertEqual(result['media_sha256'],['a'*64]);self.assertEqual(result['media_format'],'image');self.assertEqual(source,before)
    def test_reels_and_mixed_carousel_preserve_explicit_selection_order(self):
        source=snapshot();result=build_instagram_payload(source,context('reels',['video1']))
        self.assertEqual(result['media_format'],'reels');self.assertEqual(result['media_sha256'],['c'*64])
        result=build_instagram_payload(source,context('carousel',['video1','image2','image1']))
        self.assertEqual([a['id'] for a in result['assets']],['video1','image2','image1'])
        self.assertEqual(result['media_sha256'],['c'*64,'b'*64,'a'*64]);self.assertEqual([a['id'] for a in source['assets']],['image1','image2','video1','png1'])
        result['assets'][0]['sha256']='changed';self.assertEqual(source['assets'][2]['sha256'],'c'*64)
    def test_original_used_only_when_no_destination_instagram_variant_exists(self):
        result=build_instagram_payload(snapshot(),context(destination_account_id='personal',connection_id='personal.instagram'))
        self.assertEqual(result['caption'],'원본 캡션')
        source=snapshot();source['variants'].append(dict(source['variants'][0]))
        with self.assertRaises(ContractError):build_instagram_payload(source,context())
    def test_wrong_content_owner_revision_manifest_platform_and_target_rejected(self):
        source=snapshot()
        for changes in ({'content_id':'other'},{'content_revision':3},{'manifest_hash':'different'},{'owner_account_id':'dept'},{'destination_account_id':'unknown'},{'platform':'facebook'},{'target_id':'username'},{'target_id':'123/path'},{'target_id':'1'*65}):
            with self.assertRaises(ContractError):build_instagram_payload(source,context(**changes))
        with self.assertRaises(ContractError):build_instagram_payload(source,{})
    def test_options_are_exact_no_default_asset_or_url_selection(self):
        for options in ({},{'instagram':None},{'instagram':{'format':'image'}},{'instagram':{'format':'image','asset_ids':['image1'],'url':'https://example.org/image.jpg'}},{'instagram':{'format':'story','asset_ids':['image1']}},{'instagram':{'format':'image','asset_ids':['image1']},'command':'native'},{'instagram':{'format':'image','asset_ids':['image1']},'visibility':'private'},{'instagram':{'format':'image','asset_ids':['image1']},'visibility':'unlisted'}):
            with self.assertRaises(ContractError):build_instagram_payload(snapshot(),context(options=options))
    def test_format_counts_types_duplicate_or_missing_assets_rejected_without_conversion(self):
        for format,ids in (('image',[]),('image',['image1','image2']),('image',['png1']),('image',['video1']),('reels',['image1']),('reels',['video1','image1']),('carousel',['image1']),('carousel',['image1','image1']),('carousel',['image1','missing']),('carousel',['image1','png1'])):
            with self.assertRaises(ContractError):build_instagram_payload(snapshot(),context(format,ids))
        for ids in (None,'image1',[],['image1',True]):
            with self.assertRaises(ContractError):build_instagram_payload(snapshot(),context(options={'instagram':{'format':'image','asset_ids':ids}}))
    def test_carousel_internal_count_boundary_2_to_10_without_mutating_snapshot(self):
        source=snapshot();source['assets']=[asset('asset'+str(i)) for i in range(11)]
        for count in (2,10):self.assertEqual(len(build_instagram_payload(source,context('carousel',['asset'+str(i) for i in range(count)]))['assets']),count)
        with self.assertRaises(ContractError):build_instagram_payload(source,context('carousel',['asset'+str(i) for i in range(11)]))
    def test_selected_asset_metadata_is_unique_and_hash_size_mime_checked(self):
        for metadata in ({'sha256':'A'*64},{'sha256':'short'},{'sha256':None},{'size':True},{'size':0},{'size':-1},{'size':'50'},{'media_type':'image/png'},{'media_type':[]}):
            source=snapshot();source['assets'][0].update(metadata)
            with self.assertRaises(ContractError):build_instagram_payload(source,context())
        source=snapshot();source['assets'].append(dict(source['assets'][0]))
        with self.assertRaises(ContractError):build_instagram_payload(source,context())
    def test_caption_internal_limit_utf8_nul_and_blank_no_truncation(self):
        for text in ('가'*2200,' leading\ncaption #한글 '):
            source=snapshot();source['variants'][0]['text']=text
            self.assertEqual(build_instagram_payload(source,context())['caption'],text)
        for text in ('가'*2201,' ','a\x00b','\ud800',None):
            source=snapshot();source['variants'][0]['text']=text
            with self.assertRaises(ContractError):build_instagram_payload(source,context())
    def test_no_file_database_network_or_native_access_and_no_readiness_claim(self):
        source=snapshot();ctx=context()
        with patch('builtins.open',side_effect=AssertionError('file')),patch('sqlite3.connect',side_effect=AssertionError('database')),patch('socket.socket',side_effect=AssertionError('network')),patch('ctypes.CDLL',side_effect=AssertionError('native')):
            result=build_instagram_payload(source,ctx)
        self.assertFalse({'reviewed','approved','execution_enabled','image_url','video_url','token','path'}&set(result))

    def test_selected_asset_ids_reject_whitespace_invalid_utf8_and_control_even_when_source_matches(self):
        for identifier in (' ','asset id',' asset','asset ','asset\nid','asset\tid','asset\x00id','asset\x7fid','asset\u0085id','\ud800','a'*301):
            with self.subTest(identifier=repr(identifier)):
                source=snapshot();source['assets'][0]['id']=identifier
                with self.assertRaises(ContractError):build_instagram_payload(source,context(ids=[identifier]))
        source=snapshot();source['assets'][0]['id']='한글자산_'+'a'*295
        result=build_instagram_payload(source,context(ids=[source['assets'][0]['id']]))
        self.assertEqual(result['assets'][0]['id'],source['assets'][0]['id'])

    def test_snapshot_owner_missing_or_wrong_type_never_selects_an_asset(self):
        for owner in (None,True,[],{},'other'):
            source=snapshot();source['owner_account_id']=owner
            with self.assertRaises(ContractError):build_instagram_payload(source,context())
        source=snapshot();del source['owner_account_id']
        with self.assertRaises(ContractError):build_instagram_payload(source,context())

    def test_selected_asset_identifier_is_not_a_source_folder_path(self):
        for identifier in ('/tmp/card.jpg','../card.jpg','folder/card.jpg','folder\\card.jpg','.','..'):
            source=snapshot();source['assets'][0]['id']=identifier
            with self.assertRaises(ContractError):build_instagram_payload(source,context(ids=[identifier]))

    def test_context_owner_and_destination_bad_types_are_contract_errors(self):
        for field in ('owner_account_id','destination_account_id'):
            for value in (None,True,[],{},1):
                ctx=context();object.__setattr__(ctx,field,value)
                with self.assertRaises(ContractError):build_instagram_payload(snapshot(),ctx)
