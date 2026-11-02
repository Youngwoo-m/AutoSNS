"""순수 원본 전달 영수증·원격 관측 결속. 외부 호출은 없다."""
import copy
from datetime import datetime,timedelta,timezone
import hashlib
import unittest
from common.operations.instagram_evidence import instagram_upload_identity,safe_instagram_url,UPLOAD_RECEIPT_KEYS
from common.operations.runtime_models import PublicationContext
from common.publishers.instagram_payloads import build_instagram_payload
from common.operations.models import freeze
NOW=datetime(2026,11,2,tzinfo=timezone.utc)
def fixture(fmt='image',provisional=False):
    ids=['one','two'] if fmt=='carousel' else ['one']
    ctx=PublicationContext(content_id='c1',content_revision=1,manifest_hash='manifest',owner_account_id='personal',destination_account_id='dept',connection_id='dept.instagram',target_id='123',publication_purpose='initial',schedule_slot='slot',options={'instagram':{'format':fmt,'asset_ids':ids}},schedule_condition={},registry_revision='r1',policy_revision='p1',auth_checked_at=NOW-timedelta(minutes=2),auth_expires_at=NOW+timedelta(hours=1),review_report_hashes=('review',),platform='instagram')
    assets=[dict(id=x,sha256=hashlib.sha256(x.encode()).hexdigest(),size=12,media_type='video/mp4' if fmt=='reels' or x=='two' else 'image/jpeg') for x in ids]
    snapshot=dict(id='c1',revision=1,manifest_hash='manifest',owner_account_id='personal',original='원문 캡션',assets=assets)
    p=build_instagram_payload(snapshot,ctx)
    children=[dict(id='701',media_type='IMAGE'),dict(id='702',media_type='VIDEO')] if fmt=='carousel' else []
    receipt=dict(kind='instagram_upload_receipt_v1',context_hash=ctx.context_hash,connection_id=ctx.connection_id,target_id='123',remote_id='999',owner_account_id='personal',destination_account_id='dept',content_id='c1',content_revision=1,manifest_hash='manifest',caption_sha256=p['caption_sha256'],media_format=fmt,assets=copy.deepcopy(assets),creation_id='600',child_creation_ids=['601','602'] if fmt=='carousel' else [],published_children=None if provisional else copy.deepcopy(children))
    attempt=dict(request_started=True,context_hash=ctx.context_hash,outcome='submitted',created_at=NOW-timedelta(minutes=1),result=dict(outcome='submitted',remote_id='999',evidence={'upload_receipt':receipt}))
    candidate=dict(remote_id='999',target_id='123',destination_account_id='dept',created_at=NOW,text=p['caption'],body_sha256=p['caption_sha256'],media_sha256=None,media_format=fmt,media_type={'image':'IMAGE','reels':'VIDEO','carousel':'CAROUSEL_ALBUM'}[fmt],media_product_type='REELS' if fmt=='reels' else 'FEED',media_status='readable',children=children,visibility='public',url='https://www.instagram.com/'+('reel' if fmt=='reels' else 'p')+'/AbC_123/')
    return ctx,snapshot,candidate,attempt
class InstagramEvidenceTests(unittest.TestCase):
    def valid(self,args,**kw):return instagram_upload_identity(*args,NOW,'999',**kw)
    def test_three_formats_and_exact_receipt_schema(self):
        for fmt in ('image','reels','carousel'):
            args=fixture(fmt);self.assertTrue(self.valid(args));self.assertEqual(len(UPLOAD_RECEIPT_KEYS),16)
            self.assertEqual(set(args[3]['result']['evidence']['upload_receipt']),UPLOAD_RECEIPT_KEYS)
    def test_frozen_bridge_observation_matches_persisted_json_receipt(self):
        ctx,snapshot,candidate,attempt=fixture('carousel',True)
        candidate['upload_receipt']={**attempt['result']['evidence']['upload_receipt'],'published_children':copy.deepcopy(candidate['children'])}
        candidate['created_at']=candidate['created_at'].isoformat()
        self.assertTrue(self.valid((ctx,snapshot,freeze(candidate),attempt)))
    def test_extra_observation_receipt_is_validated_even_when_source_is_already_final(self):
        for fmt in ('image','carousel'):
            args=fixture(fmt)
            args[2]['upload_receipt']={**args[3]['result']['evidence']['upload_receipt'],'private_url':'https://private/'}
            self.assertFalse(self.valid(args))
            args[2]['upload_receipt']=copy.deepcopy(args[3]['result']['evidence']['upload_receipt'])
            args[2]['upload_receipt']['creation_id']='800'
            self.assertFalse(self.valid(args))
    def test_missing_receipt_parent_only_receipt_and_extra_secret_fields_fail(self):
        for change in ('missing','extra','parentonly'):
            args=fixture('carousel');r=args[3]['result']['evidence']
            if change=='missing':r.clear()
            elif change=='extra':r['upload_receipt']['url']='https://secret/'
            else:r['upload_receipt']['published_children']=None
            self.assertFalse(self.valid(args))
    def test_provisional_carousel_requires_exact_final_private_journal_pin(self):
        args=fixture('carousel',True);self.assertFalse(self.valid(args))
        candidate=args[2];source=args[3]['result']['evidence']['upload_receipt']
        candidate['upload_receipt']={**source,'published_children':copy.deepcopy(candidate['children'])}
        self.assertTrue(self.valid(args))
        candidate['upload_receipt']['creation_id']='888';self.assertFalse(self.valid(args))
    def test_caption_replacement_and_remote_hash_substitution_fail(self):
        for change in ({'text':'다른 캡션'},{'body_sha256':'b'*64},{'media_sha256':['a'*64]}):
            args=fixture();args[2].update(change);self.assertFalse(self.valid(args))
    def test_child_order_type_count_and_identity_must_match_selection_and_pin(self):
        for changes in ('reverse','type','count','id','duplicate'):
            args=fixture('carousel');children=args[2]['children']
            if changes=='reverse':children.reverse()
            elif changes=='type':children[0]['media_type']='VIDEO'
            elif changes=='count':children.pop()
            elif changes=='id':children[0]['id']='800'
            else:children[1]['id']=children[0]['id']
            self.assertFalse(self.valid(args))
    def test_receipt_binding_metadata_types_and_creation_ids_are_strict(self):
        for field,value in (('context_hash','wrong'),('content_revision',True),('owner_account_id','dept'),('caption_sha256','0'*64),('creation_id','bad'),('child_creation_ids',['601','601']),('child_creation_ids',['600','602'])):
            args=fixture('carousel');args[3]['result']['evidence']['upload_receipt'][field]=value;self.assertFalse(self.valid(args))
        for field,value in (('size',True),('sha256','0'*64),('id','wrong')):
            args=fixture();args[3]['result']['evidence']['upload_receipt']['assets'][0][field]=value;self.assertFalse(self.valid(args))
    def test_snapshot_revision_manifest_owner_and_asset_order_are_recomputed(self):
        for key,value in (('revision',2),('manifest_hash','wrong'),('owner_account_id','dept')):
            args=fixture();args[1][key]=value;self.assertFalse(self.valid(args))
    def test_normal_attempt_and_result_must_be_submitted_or_scheduled_and_known(self):
        for change in ({'request_started':False},{'request_started':1.0},{'context_hash':'wrong'},{'outcome':'unknown'}):
            args=fixture();args[3].update(change);self.assertFalse(self.valid(args))
        args=fixture();args[3]['outcome']='scheduled';args[3]['result']['outcome']='scheduled';self.assertTrue(self.valid(args))
        for changes in ({'remote_id':'888'},{'outcome':'failed'}):
            args=fixture();args[3]['result'].update(changes);self.assertFalse(self.valid(args))
    def test_unknown_known_id_only_for_explicit_owned_read_mode(self):
        args=fixture();args[3]['outcome']='unknown';args[3]['result']['outcome']='unknown';args[2]['visibility']='unknown'
        self.assertFalse(self.valid(args));self.assertFalse(self.valid(args,require_public=False))
        self.assertTrue(self.valid(args,require_public=False,allow_unknown=True))
        args[3]['result']['remote_id']='888';self.assertFalse(self.valid(args,require_public=False,allow_unknown=True))
    def test_link_existing_unknown_uses_exact_resolution_receipt(self):
        args=fixture('carousel',True);args[3]['outcome']='unknown';result=args[3]['result'];result['outcome']='unknown'
        final={**result['evidence']['upload_receipt'],'published_children':copy.deepcopy(args[2]['children'])}
        result['resolution']=dict(kind='link_existing',evidence={'upload_receipt':final})
        self.assertTrue(self.valid(args));result['resolution']['kind']='accept';self.assertFalse(self.valid(args))
    def test_visibility_safe_url_and_time_are_required_even_in_owned_read_mode(self):
        for patch in ({'visibility':'private'},{'url':'https://instagram.com/accounts/login/'},{'created_at':NOW+timedelta(seconds=1)},{'created_at':NOW-timedelta(minutes=2)}):
            args=fixture();args[2].update(patch);self.assertFalse(self.valid(args))
        args=fixture();args[2]['visibility']='private';self.assertTrue(self.valid(args,require_public=False))
        del args[2]['media_sha256'];self.assertFalse(self.valid(args,require_public=False))
    def test_url_rejects_controls_tokens_wrong_host_and_nonpost_paths(self):
        for url in ('https://instagram.com/','https://instagram.com/accounts/login/','http://instagram.com/p/A/','https://evil.instagram.com/p/A/','https://user@instagram.com/p/A/','https://instagram.com:443/p/A/','https://instagram.com/p/A/?access_token=SECRET','https://instagram.com/p/A/#x','https://instagram.com/p/A/%0a','https://instagram.com/p/A/\x80','https://instagram.com/p/A/%C2%80'):
            self.assertIsNone(safe_instagram_url(url))
        self.assertEqual(safe_instagram_url('https://instagram.com/reel/A_1-/'),'https://instagram.com/reel/A_1-/')
