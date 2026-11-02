"""준비→실바이트/전달 계약→가짜 API 요청의 조립 시험. 실제 발행기는 아직 아니다.

작은 MIME 시그니처 fixture를 사용하며 실제 이미지/영상 품질·공개 호스팅을 증명하지 않는다.
"""
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
from urllib.parse import parse_qs
import unittest
from common.publishers.instagram_client import InstagramApiClient
from common.publishers.instagram_payloads import build_instagram_payload
from common.publishers.instagram_media_sources import InstagramMediaSourceFactory
from common.operations.models import thaw
from tests.publishers.test_instagram_payloads import context,snapshot,NOW

class InstagramMediaContractTests(unittest.TestCase):
    def configured(self,media_format,identifiers):
        raw={'image1':b'\xff\xd8\xff\xe0fixture-one\xff\xd9','image2':b'\xff\xd8\xff\xe0fixture-two\xff\xd9',
             'video1':b'\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2'}
        source=snapshot()
        for item in source['assets']:
            if item['id'] in raw:
                item.update(size=len(raw[item['id']]),sha256=hashlib.sha256(raw[item['id']]).hexdigest())
        ctx=context(media_format,identifiers);prepared=build_instagram_payload(source,ctx)
        metadata={item['id']:dict(item) for item in source['assets']};staged=[];loads=[]
        def loader(content_id,revision,asset_id):
            self.assertEqual((content_id,revision),(ctx.content_id,ctx.content_revision));loads.append(asset_id)
            return metadata[asset_id],raw[asset_id]
        def stage(request,data):
            # 모든 로컬 바이트가 검증된 다음에만 외부 전달 요청을 만들 수 있다.
            self.assertEqual(loads,identifiers);staged.append((request,data))
            digest=hashlib.sha256(data).hexdigest()
            return dict(url='https://cdn.example.org/media/'+digest,asset_sha256=digest,asset_size=len(data),
                        expires_at=(NOW+timedelta(hours=1)).isoformat(),receipt_id='receipt-'+str(len(staged)))
        factory=InstagramMediaSourceFactory(loader,stager=stage,approval_guard=lambda observed,body: observed.context_hash==ctx.context_hash and thaw(body)==prepared,
                                           allowed_hosts=('cdn.example.org',),clock=lambda:NOW)
        return ctx,prepared,factory,staged

    def client(self):
        calls=[]
        def transport(method,path,headers,body):
            calls.append((method,path,headers,body));return 200,json.dumps({'id':str(700+len(calls))}).encode()
        return InstagramApiClient('fixture-token',api_version='v26.0',transport=transport),calls

    def test_single_image_and_reels_pass_only_bound_url_and_exact_caption(self):
        for media_format,asset_id in (('image','image1'),('reels','video1')):
            with self.subTest(media_format=media_format):
                ctx,prepared,factory,staged=self.configured(media_format,[asset_id]);leases=factory.prepare(ctx,prepared)
                client,calls=self.client();method=client.create_image if media_format=='image' else client.create_reels
                result=method(ctx.target_id,leases[0].url,prepared['caption'])
                form=parse_qs(calls[0][3].decode())
                self.assertEqual(form['caption'],[prepared['caption']]);self.assertEqual(result,{'id':'701'})
                self.assertEqual(leases[0].context_hash,ctx.context_hash);self.assertEqual(leases[0].asset_id,asset_id)
                self.assertEqual(len(staged),1);self.assertNotIn('fixture-token',str(staged[0][0]));self.assertNotIn(prepared['caption'],str(staged[0][0]))
                self.assertNotIn('fixture-token',calls[0][1]);self.assertNotIn('fixture-token',calls[0][3].decode())

    def test_mixed_carousel_preserves_chosen_order_through_hosted_sources_and_child_ids(self):
        ctx,prepared,factory,staged=self.configured('carousel',['video1','image2','image1'])
        leases=factory.prepare(ctx,prepared);client,calls=self.client();children=[]
        for lease in leases:
            option={'image_url':lease.url} if lease.media_type=='image/jpeg' else {'video_url':lease.url}
            children.append(client.create_carousel_item(ctx.target_id,**option)['id'])
        client.create_carousel(ctx.target_id,children,prepared['caption'])
        self.assertEqual([lease.asset_id for lease in leases],['video1','image2','image1'])
        self.assertEqual(parse_qs(calls[-1][3].decode())['children'],['701,702,703'])
        self.assertEqual([lease.asset_sha256 for lease in leases],prepared['media_sha256'])
        self.assertEqual(len(staged),3)
