"""가짜 서버 공급자·실제 바이트로만 검증한다. 파일 공개·업로드·API는 실행하지 않는다."""
from dataclasses import FrozenInstanceError,replace
from datetime import datetime,timezone,timedelta
import hashlib
import unittest
from common.operations.models import ContractError
from common.operations.runtime_models import PublicationContext
from common.publishers.instagram_media_sources import InstagramMediaSourceFactory,InstagramHostedMedia

NOW=datetime(2026,11,2,tzinfo=timezone.utc)
JPEG=b'\xff\xd8\xff\xe0fixture\xff\xd9'
VIDEO=b'\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isommp42'
def context(**over):
    base=dict(content_id='content-1',content_revision=2,manifest_hash='a'*64,owner_account_id='personal',destination_account_id='dept',connection_id='dept.instagram',target_id='123456',publication_purpose='initial',schedule_slot='slot',options={'instagram':{'format':'carousel','asset_ids':['image-1','image-2']}},schedule_condition={},registry_revision='registry',policy_revision='policy',auth_checked_at=NOW,auth_expires_at=NOW+timedelta(hours=1),review_report_hashes=('review',),platform='instagram')
    return PublicationContext(**{**base,**over})
def metadata(aid,raw=JPEG,mime='image/jpeg'):return dict(id=aid,sha256=hashlib.sha256(raw).hexdigest(),size=len(raw),media_type=mime)
def prepared(ctx=None,assets=None):
    ctx=ctx or context();caption=' 학과용 캡션 그대로 '
    result={name:getattr(ctx,name) for name in ('platform','connection_id','target_id','owner_account_id','destination_account_id','content_id','content_revision','manifest_hash','publication_purpose','schedule_slot')}
    selected=assets or [metadata('image-1'),metadata('image-2')]
    result.update(caption=caption,caption_sha256=hashlib.sha256(caption.encode()).hexdigest(),media_format=ctx.options['instagram']['format'],assets=selected,media_sha256=[a['sha256'] for a in selected]);return result
class InstagramMediaSourcesTests(unittest.TestCase):
    def setUp(self):self.events=[];self.raw={'image-1':JPEG,'image-2':JPEG};self.proofs=[]
    def loader(self,cid,revision,aid):self.events.append(('load',aid));return metadata(aid,self.raw[aid],'video/mp4' if self.raw[aid]==VIDEO else 'image/jpeg'),self.raw[aid]
    def guard(self,ctx,payload):self.events.append(('guard',));return True
    def stager(self,request,raw):
        self.events.append(('stage',request['asset_id']));self.proofs.append((request,raw))
        return dict(url='https://cdn.example.com/'+request['asset_id']+'.jpg',asset_sha256=hashlib.sha256(raw).hexdigest(),asset_size=len(raw),expires_at=(NOW+timedelta(hours=1)).isoformat(),receipt_id='receipt_'+request['asset_id'])
    def factory(self,**over):return InstagramMediaSourceFactory(self.loader,stager=self.stager,approval_guard=self.guard,allowed_hosts=('cdn.example.com',),clock=lambda:NOW,**over)
    def test_constructor_and_unconfigured_defaults_never_load_stage_or_call_clock(self):
        factory=InstagramMediaSourceFactory(self.loader,clock=lambda:(_ for _ in ()).throw(AssertionError('no clock')))
        self.assertEqual(self.events,[])
        with self.assertRaises(ContractError):factory.prepare(context(),prepared())
        self.assertEqual(self.events,[])
        for missing in ('stager','approval_guard','allowed_hosts'):
            args=dict(stager=self.stager,approval_guard=self.guard,allowed_hosts=('cdn.example.com',),clock=lambda:NOW);args[missing]=() if missing=='allowed_hosts' else None
            with self.assertRaises(ContractError):InstagramMediaSourceFactory(self.loader,**args).prepare(context(),prepared())
        self.assertEqual(self.events,[])
    def test_entire_selection_is_validated_before_staging_and_receipts_bind_context_order(self):
        ctx=context();source=prepared(ctx);receipts=self.factory().prepare(ctx,source)
        self.assertEqual(self.events,[('guard',),('load','image-1'),('load','image-2'),('guard',),('stage','image-1'),('guard',),('stage','image-2')])
        self.assertIsInstance(receipts,tuple);self.assertEqual([r.asset_id for r in receipts],['image-1','image-2']);self.assertEqual([r.position for r in receipts],[0,1])
        for receipt in receipts:
            self.assertIsInstance(receipt,InstagramHostedMedia);self.assertEqual(receipt.context_hash,ctx.context_hash);self.assertEqual(receipt.owner_account_id,'personal');self.assertEqual(receipt.destination_account_id,'dept');self.assertEqual(receipt.target_id,'123456');self.assertEqual(receipt.expires_at,NOW+timedelta(hours=1))
            self.assertNotIn('https://',repr(receipt));self.assertNotIn(receipt.receipt_id,repr(receipt))
            with self.assertRaises(FrozenInstanceError):receipt.url='changed'
        for request,raw in self.proofs:self.assertNotIn('caption',request);self.assertNotIn('token',request);self.assertEqual(request['context_hash'],ctx.context_hash)
        self.assertEqual(source['media_sha256'],[hashlib.sha256(JPEG).hexdigest()]*2)
    def test_wrong_owner_options_hash_or_schema_reject_before_loader(self):
        ctx=context()
        for change in (dict(owner_account_id='dept'),dict(target_id='other'),dict(caption_sha256='b'*64),dict(extra=True),dict(media_sha256=['b'*64]),dict(media_format='image')):
            with self.assertRaises(ContractError):self.factory().prepare(ctx,{**prepared(ctx),**change})
        reordered=replace(ctx,options={'instagram':{'format':'carousel','asset_ids':['image-2','image-1']}})
        with self.assertRaises(ContractError):self.factory().prepare(reordered,prepared(ctx))
        with self.assertRaises(ContractError):self.factory().prepare(replace(ctx,platform='facebook'),prepared(ctx))
        self.assertEqual(self.events,[])
    def test_invalid_later_asset_never_stages_earlier_valid_asset(self):
        def loader(cid,revision,aid):
            self.events.append(('load',aid));meta=metadata(aid);return meta,JPEG if aid=='image-1' else JPEG+b'tampered'
        factory=InstagramMediaSourceFactory(loader,stager=self.stager,approval_guard=self.guard,allowed_hosts=('cdn.example.com',),clock=lambda:NOW)
        with self.assertRaises(ContractError):factory.prepare(context(),prepared())
        self.assertEqual(self.proofs,[]);self.assertEqual([e for e in self.events if e[0]=='stage'],[])
    def test_png_claimed_jpeg_and_malformed_mp4_are_not_staged(self):
        png=b'\x89PNG\r\n\x1a\nnot-jpeg'
        for raw,mime,fmt in ((png,'image/jpeg','image'),(b'xxxxftypnotbox','video/mp4','reels')):
            ctx=context(options={'instagram':{'format':fmt,'asset_ids':['one']}});meta=metadata('one',raw,mime)
            factory=InstagramMediaSourceFactory(lambda *a:(meta,raw),stager=self.stager,approval_guard=self.guard,allowed_hosts=('cdn.example.com',),clock=lambda:NOW)
            with self.assertRaises(ContractError):factory.prepare(ctx,prepared(ctx,[meta]))
        self.assertEqual(self.proofs,[])
    def test_valid_image_reels_and_mixed_carousel_keep_order_without_conversion(self):
        self.raw['video']=VIDEO
        for fmt,ids in (('image',['image-1']),('reels',['video']),('carousel',['video','image-1'])):
            ctx=context(options={'instagram':{'format':fmt,'asset_ids':ids}});metas=[metadata(aid,self.raw[aid],'video/mp4' if aid=='video' else 'image/jpeg') for aid in ids]
            receipts=self.factory().prepare(ctx,prepared(ctx,metas));self.assertEqual([r.asset_id for r in receipts],ids)
    def test_revoked_guard_prevents_staging_after_full_load_and_before_each_next_stage(self):
        for accepted,expected in ((0,0),(1,0),(2,1)):
            calls=[];staged=[]
            def guard(*args):calls.append(1);return len(calls)<=accepted
            def stage(request,raw):staged.append(1);return self.stager(request,raw)
            factory=InstagramMediaSourceFactory(self.loader,stager=stage,approval_guard=guard,allowed_hosts=('cdn.example.com',),clock=lambda:NOW)
            with self.assertRaises(ContractError):factory.prepare(context(),prepared())
            self.assertEqual(len(staged),expected)
    def test_bad_public_urls_or_proof_bindings_and_expiries_are_rejected(self):
        changes=[dict(url=url) for url in ('http://cdn.example.com/a','https://evil.example.com/a','https://127.0.0.1/a','https://user@cdn.example.com/a','https://cdn.example.com:443/a','https://cdn.example.com/a?token=x','https://cdn.example.com/a#x','https://cdn.example.com/\na','https://cdn.example.com/\u0085a','https://cdn.example.com/\ud800','https://cdn.example.com/%0aa')]
        changes += [dict(asset_sha256='b'*64),dict(asset_size=True),dict(receipt_id='secret/token?key=x'),dict(expires_at=(NOW+timedelta(minutes=5)).isoformat()),dict(expires_at=(NOW+timedelta(hours=25)).isoformat()),dict(expires_at='2026-11-02T01:00:00'),dict(extra=True)]
        for change in changes:
            def stage(request,raw,change=change):return {**self.stager(request,raw),**change}
            factory=InstagramMediaSourceFactory(self.loader,stager=stage,approval_guard=self.guard,allowed_hosts=('cdn.example.com',),clock=lambda:NOW)
            with self.subTest(change=change),self.assertRaises(ContractError):factory.prepare(context(),prepared())
    def test_ip_local_internal_or_ambiguous_allowlist_hosts_never_become_configured(self):
        for host in ('127.0.0.1','localhost','media.local','media.internal','media.localhost','::1','cdn.example.com:443','https://cdn.example.com','cdn.example.com.','media.test','media.invalid','media.example','media.onion','cdn.123'):
            with self.subTest(host=host),self.assertRaises(ContractError):InstagramMediaSourceFactory(self.loader,stager=self.stager,approval_guard=self.guard,allowed_hosts=(host,),clock=lambda:NOW)
        self.assertEqual(self.events,[])
