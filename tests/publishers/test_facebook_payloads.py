"""Facebook Pages 텍스트 준비는 승인 자료를 바꾸거나 외부 I/O를 하지 않는다."""
import copy
from datetime import datetime,timezone,timedelta
import hashlib
import unittest
from unittest.mock import patch
from common.operations.models import ContractError,freeze
from common.operations.runtime_models import PublicationContext
from common.publishers.facebook_payloads import build_facebook_payload,validate_facebook_text,PREPARED_KEYS,MAX_TEXT_BYTES

NOW=datetime(2026,11,2,tzinfo=timezone.utc)
def context(account='dept',**over):
    value=dict(content_id='content-1',content_revision=1,manifest_hash='manifest-1',owner_account_id='personal',destination_account_id=account,connection_id=account+'.facebook',target_id='123456789',publication_purpose='initial',schedule_slot='slot-1',options={'text_only':True},schedule_condition={},registry_revision='registry',policy_revision='policy',auth_checked_at=NOW,auth_expires_at=NOW+timedelta(hours=1),review_report_hashes=('review',),platform='facebook')
    return PublicationContext(**{**value,**over})
def snapshot():
    return dict(id='content-1',revision=1,manifest_hash='manifest-1',owner_account_id='personal',title='원고',original=' 원문\n그대로 ',variants=[dict(destination_account_id='dept',platform='facebook',text=' 학과 페이지 교차 게시\n그대로 '),dict(destination_account_id='personal',platform='threads',text='다른 채널')],assets=[dict(id='image-1',media_type='image/png',sha256='a'*64),dict(id='video-1',media_type='video/mp4',sha256='b'*64)])

class FacebookPayloadTests(unittest.TestCase):
    def test_explicit_text_only_binds_crosspost_and_preserves_all_source_assets(self):
        source=snapshot();before=copy.deepcopy(source);ctx=context();prepared=build_facebook_payload(source,ctx)
        self.assertEqual(set(prepared),set(PREPARED_KEYS));self.assertEqual(len(prepared),13)
        for name in PREPARED_KEYS:
            if name not in ('text','body_sha256','media_sha256'):self.assertEqual(prepared[name],getattr(ctx,name))
        self.assertEqual(prepared['text'],source['variants'][0]['text']);self.assertEqual(prepared['body_sha256'],hashlib.sha256(prepared['text'].encode('utf-8')).hexdigest());self.assertEqual(prepared['media_sha256'],[]);self.assertEqual(source,before)
    def test_same_account_without_facebook_variant_uses_exact_original(self):
        source=snapshot();prepared=build_facebook_payload(source,context('personal'))
        self.assertEqual(prepared['text'],' 원문\n그대로 ');self.assertEqual(prepared['owner_account_id'],'personal');self.assertEqual(prepared['destination_account_id'],'personal')
        self.assertEqual(build_facebook_payload(source,context(options={'text_only':True,'visibility':'public'}))['text'],source['variants'][0]['text'])
    def test_content_identity_and_revision_type_are_exact(self):
        for change in (dict(id='other'),dict(revision=2),dict(revision=True),dict(manifest_hash='other'),dict(owner_account_id='dept')):
            with self.subTest(change=change),self.assertRaises(ContractError):build_facebook_payload({**snapshot(),**change},context())
        with self.assertRaises(ContractError):build_facebook_payload(snapshot(),object())
    def test_platform_accounts_and_numeric_page_target_are_required(self):
        for change in (dict(platform='threads'),dict(owner_account_id='other'),dict(destination_account_id='other'),dict(target_id='page/name'),dict(target_id='１２３'),dict(target_id='1'*65)):
            with self.subTest(change=change),self.assertRaises(ContractError):build_facebook_payload(snapshot(),context(**change))
    def test_only_explicit_text_only_and_optional_public_visibility_are_supported(self):
        for options in ({},{'text_only':False},{'text_only':1},{'text_only':'true'},{'text_only':True,'visibility':'private'},{'text_only':True,'title_override':'other'},{'text_only':True,'profile':True}):
            with self.subTest(options=options),self.assertRaises(ContractError):build_facebook_payload(snapshot(),context(options=options))
    def test_ambiguous_facebook_variant_or_malformed_variant_is_rejected(self):
        source=snapshot();source['variants'].append(copy.deepcopy(source['variants'][0]))
        with self.assertRaises(ContractError):build_facebook_payload(source,context())
        for variants in (None,'text',[True],[{'destination_account_id':'dept','platform':'facebook','text':False}]):
            with self.subTest(variants=variants),self.assertRaises(ContractError):build_facebook_payload({**snapshot(),'variants':variants},context())
    def test_utf8_nonblank_nul_and_internal_transport_bound_are_checked_without_trimming(self):
        self.assertEqual(MAX_TEXT_BYTES,200000)
        accepted='한'*66666+'ab';self.assertEqual(len(accepted.encode('utf-8')),MAX_TEXT_BYTES)
        self.assertEqual(validate_facebook_text(accepted),accepted)
        for text in ('',' \n\t ','x\x00y','invalid\ud800','x'*200001,'한'*66667,True,None):
            with self.subTest(kind=type(text).__name__),self.assertRaises(ContractError):validate_facebook_text(text)
    def test_frozen_snapshot_and_options_are_accepted_and_result_is_independent(self):
        source=freeze(snapshot());prepared=build_facebook_payload(source,context())
        prepared['media_sha256'].append('not-source');self.assertEqual(len(source['assets']),2)
        self.assertEqual(build_facebook_payload(source,context())['media_sha256'],[])
    def test_preparation_performs_no_file_or_process_access(self):
        with patch('builtins.open',side_effect=AssertionError('no files')),patch('subprocess.run',side_effect=AssertionError('no processes')):
            prepared=build_facebook_payload(snapshot(),context())
        self.assertEqual(prepared['platform'],'facebook')
