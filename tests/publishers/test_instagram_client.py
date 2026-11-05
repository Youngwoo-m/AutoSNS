"""Facebook Login Instagram 요청·응답 경계. 가짜 transport만 사용한다."""
import json
from unittest.mock import patch
import unittest
from urllib.parse import parse_qs

from common.operations.models import ContractError
from common.publishers.instagram_client import InstagramApiClient

TOKEN='private-instagram-token'
# 임의의 명시 경로 시험 값이며 현재 지원되는 API 버전을 주장하지 않는다.
VERSION='v26.0'
IMAGE='https://cdn.example.org/assets/card.jpg'
VIDEO='https://cdn.example.org/assets/short.mp4'


def media(**changes):
    return dict(dict(id='456',owner={'id':'123'},caption='승인한 캡션',media_type='IMAGE',media_product_type='FEED',timestamp='2026-11-02T02:00:00+0000',permalink='https://www.instagram.com/p/AbCd/'),**changes)


class InstagramClientTests(unittest.TestCase):
    def client(self,responses=None):
        calls=[];responses=list(responses or [(200,b'{"id":"456"}')])
        def transport(method,path,headers,body):calls.append((method,path,headers,body));return responses.pop(0)
        return InstagramApiClient(TOKEN,api_version=VERSION,login_mode='facebook_login',transport=transport),calls

    def code(self,code,call):
        with self.assertRaises(ContractError) as caught:call()
        self.assertEqual(caught.exception.code,code);self.assertNotIn(TOKEN,str(caught.exception))

    def test_constructor_requires_explicit_version_and_rejects_other_login_flavours(self):
        with self.assertRaises(TypeError):InstagramApiClient(TOKEN)
        for version in ('','latest','v0.0','v026.0','v26.1','v26.0/me',None):
            with self.assertRaises(ContractError):InstagramApiClient(TOKEN,api_version=version)
        for mode in ('instagram_login','facebook','auto',None):
            with self.assertRaises(ContractError):InstagramApiClient(TOKEN,api_version=VERSION,login_mode=mode)
        client,calls=self.client();self.assertEqual(calls,[]);self.assertNotIn(TOKEN,repr(client))

    def test_inspect_account_requests_only_verified_fields_and_does_not_claim_type_or_auth(self):
        client,calls=self.client([(200,b'{"id":"123","username":"dept","account_type":"BUSINESS","access_token":"PRIVATE"}')])
        self.assertEqual(client.inspect_account('123'),{'id':'123','username':'dept'})
        self.assertEqual(calls[0][:2],('GET','/v26.0/123?fields=id%2Cusername'));self.assertIsNone(calls[0][3])
        self.assertEqual(calls[0][2]['Authorization'],'Bearer '+TOKEN);self.assertNotIn(TOKEN,calls[0][1])
        client,_=self.client([(200,b'{"id":"999","username":"dept"}')]);self.code('instagram_invalid_response',lambda:client.inspect_account('123'))

    def test_single_image_and_reels_create_containers_only_with_exact_form_fields(self):
        client,calls=self.client([(200,b'{"id":"456"}'),(200,b'{"id":"789"}')])
        self.assertEqual(client.create_image('123',IMAGE,'캡션 & 원문'),{'id':'456'})
        self.assertEqual(client.create_reels('123',VIDEO,'릴스 캡션'),{'id':'789'})
        self.assertEqual([call[:2] for call in calls],[('POST','/v26.0/123/media')]*2)
        self.assertEqual(parse_qs(calls[0][3].decode(),keep_blank_values=True),{'image_url':[IMAGE],'caption':['캡션 & 원문']})
        self.assertEqual(parse_qs(calls[1][3].decode(),keep_blank_values=True),{'media_type':['REELS'],'video_url':[VIDEO],'caption':['릴스 캡션']})
        self.assertTrue(all('access_token' not in call[1] and TOKEN not in call[3].decode() for call in calls))

    def test_carousel_items_and_parent_are_explicit_and_ordered(self):
        client,calls=self.client([(200,b'{"id":"456"}'),(200,b'{"id":"789"}'),(200,b'{"id":"555"}')])
        self.assertEqual(client.create_carousel_item('123',image_url=IMAGE),{'id':'456'})
        self.assertEqual(client.create_carousel_item('123',video_url=VIDEO),{'id':'789'})
        self.assertEqual(client.create_carousel('123',['456','789'],'캐러셀'),{'id':'555'})
        forms=[parse_qs(row[3].decode(),keep_blank_values=True) for row in calls]
        self.assertEqual(forms,[{'image_url':[IMAGE],'is_carousel_item':['true']},{'video_url':[VIDEO],'media_type':['VIDEO'],'is_carousel_item':['true']},{'media_type':['CAROUSEL'],'children':['["456","789"]'],'caption':['캐러셀']}])
        before=len(calls)
        for children in ([],['456'],['456']*2,[str(n) for n in range(11)],['456','bad'],True):self.code('instagram_invalid_request',lambda:client.create_carousel('123',children,''))
        for options in ({},{'image_url':IMAGE,'video_url':VIDEO}):self.code('instagram_invalid_request',lambda:client.create_carousel_item('123',**options))
        self.assertEqual(len(calls),before)

    def test_container_status_and_publish_are_single_explicit_requests_without_polling(self):
        client,calls=self.client([(200,b'{"id":"456","status_code":"FINISHED","status":"PRIVATE ERROR TEXT"}'),(200,b'{"id":"789"}')])
        self.assertEqual(client.container_status('456'),{'id':'456','status_code':'FINISHED'})
        self.assertEqual(client.publish('123','456'),{'id':'789'})
        self.assertEqual(calls[0][:2],('GET','/v26.0/456?fields=id%2Cstatus_code'))
        self.assertEqual(calls[1][:2],('POST','/v26.0/123/media_publish'));self.assertEqual(parse_qs(calls[1][3].decode()),{'creation_id':['456']})
        for row in ({'id':'999','status_code':'FINISHED'},{'id':'456','status_code':[]},{'id':'456','status_code':'UNKNOWN'}):
            client,_=self.client([(200,json.dumps(row).encode())]);self.code('instagram_invalid_response',lambda:client.container_status('456'))

    def test_read_media_returns_only_observed_metadata_without_public_or_hash_claims(self):
        raw=media();client,calls=self.client([(200,json.dumps(dict(raw,access_token='PRIVATE',media_url='https://cdn.invalid/?token=PRIVATE')).encode())])
        self.assertEqual(client.read_media('456'),raw)
        self.assertEqual(calls[0][1],'/v26.0/456?fields=id%2Cowner%2Ccaption%2Cmedia_type%2Cmedia_product_type%2Ctimestamp%2Cpermalink')
        for change in ({'id':'999'},{'owner':'123'},{'owner':{'id':123}},{'timestamp':'bad'},{'timestamp':'2026-11-02T02:00:00'},{'media_type':True},{'media_product_type':None}):
            client,_=self.client([(200,json.dumps(media(**change)).encode())]);self.code('instagram_invalid_response',lambda:client.read_media('456'))
        for key in raw:
            missing=dict(raw);missing.pop(key);client,_=self.client([(200,json.dumps(missing).encode())]);self.code('instagram_invalid_response',lambda:client.read_media('456'))

    def test_public_media_urls_are_syntactic_server_inputs_and_unsafe_hosts_are_rejected(self):
        client,calls=self.client()
        for url in ('http://cdn.example.org/a.jpg','https://localhost/a.jpg','https://127.0.0.1/a.jpg','https://[::1]/a.jpg','https://2130706433/a.jpg','https://media.local/a.jpg','https://media.internal/a.jpg','https://cdn.example.org:443/a.jpg','https://user@cdn.example.org/a.jpg','https://cdn.example.org/a.jpg?token=x','https://cdn.example.org/a.jpg#frag',' https://cdn.example.org/a.jpg','https://cdn.example.org/a.jpg\n'):
            self.code('instagram_invalid_request',lambda:client.create_image('123',url,''))
        self.assertEqual(calls,[])

    def test_caption_internal_limit_utf8_and_ids_are_checked_before_transport(self):
        client,calls=self.client()
        for caption in ('가'*2201,'\ud800','bad\x00text',None):self.code('instagram_invalid_request',lambda:client.create_image('123',IMAGE,caption))
        for identifier in (123,True,'','１２３','123_456','1'*65,'../me'):
            self.code('instagram_invalid_request',lambda:client.inspect_account(identifier))
            self.code('instagram_invalid_request',lambda:client.publish('123',identifier))
        self.assertEqual(calls,[])
        client,_=self.client();self.assertEqual(client.create_image('123',IMAGE,'가'*2200),{'id':'456'})

    def test_default_transport_is_blocked_for_every_operation_without_native_access(self):
        with patch('socket.socket',side_effect=AssertionError('socket forbidden')):
            client=InstagramApiClient(TOKEN,api_version=VERSION)
            for call in (lambda:client.inspect_account('123'),lambda:client.create_image('123',IMAGE,''),lambda:client.create_reels('123',VIDEO,''),lambda:client.create_carousel_item('123',image_url=IMAGE),lambda:client.create_carousel('123',['456','789'],''),lambda:client.container_status('456'),lambda:client.publish('123','456'),lambda:client.read_media('789')):
                self.code('instagram_transport_unregistered',call)

    def test_json_http_and_transport_errors_are_sanitized_with_no_retry(self):
        for raw in (b'{"id":"123","id":"456"}',b'{"n":NaN}',b'{"n":1e309}',b'[]',b'null',b'\xff',b'{',b'x'*(1024*1024+1)):
            client,calls=self.client([(200,raw)]);self.code('instagram_invalid_response',lambda:client.inspect_account('123'));self.assertEqual(len(calls),1)
        for status in (301,302,400,401,429,500):
            client,calls=self.client([(status,json.dumps({'error':{'message':TOKEN}}).encode())]);self.code('instagram_api_unavailable',lambda:client.inspect_account('123'));self.assertEqual(len(calls),1)
        calls=[]
        def fail(*args):calls.append(1);raise OSError(TOKEN)
        client=InstagramApiClient(TOKEN,api_version=VERSION,transport=fail)
        self.code('instagram_api_unavailable',lambda:client.create_image('123',IMAGE,''));self.assertEqual(calls,[1])

    def test_permalink_is_limited_to_https_instagram_without_tokens_or_authority_changes(self):
        for url in ('http://www.instagram.com/p/A/','https://evil.invalid/p/A/','https://www.instagram.com.evil.invalid/p/A/','https://user@www.instagram.com/p/A/','https://www.instagram.com:443/p/A/','https://www.instagram.com/p/A/?access_token='+TOKEN,'https://www.instagram.com/p/A/#frag','https://www.instagram.com/p/A/\t'):
            client,_=self.client([(200,json.dumps(media(permalink=url)).encode())]);self.code('instagram_invalid_response',lambda:client.read_media('456'))

    def test_read_children_preserves_order_and_rejects_partial_or_ambiguous_edges(self):
        children=[{'id':'789','media_type':'VIDEO'},{'id':'456','media_type':'IMAGE'}]
        client,calls=self.client([(200,json.dumps({'data':children,'paging':{'cursors':{'after':'PRIVATE'}}}).encode())])
        self.assertEqual(client.read_children('555'),children)
        self.assertEqual(calls[0][1],'/v26.0/555/children?fields=id%2Cmedia_type')
        for row in ({'data':children,'paging':{'next':'https://remote/?access_token='+TOKEN}},
                    {'data':children,'paging':{'next':False}},{'data':children,'paging':{'next':[]}},
                    {'data':children,'paging':[]},{'data':[]},{'data':[children[0]]},
                    {'data':[children[0],children[0]]},{'data':children*6},
                    {'data':[{'id':789,'media_type':'VIDEO'},children[1]]},
                    {'data':[{'id':'789','media_type':True},children[1]]}):
            client,calls=self.client([(200,json.dumps(row).encode())])
            self.code('instagram_invalid_response',lambda:client.read_children('555'))
            self.assertEqual(len(calls),1)
        client=InstagramApiClient(TOKEN,api_version=VERSION)
        self.code('instagram_transport_unregistered',lambda:client.read_children('555'))

    def test_media_types_are_explicit_internal_support_policy(self):
        for changes in ({'media_type':'STORY'},{'media_type':'UNKNOWN'},{'media_type':[]},
                        {'media_product_type':'STORY'},{'media_product_type':'AD'},{'media_product_type':False}):
            client,_=self.client([(200,json.dumps(media(**changes)).encode())])
            self.code('instagram_invalid_response',lambda:client.read_media('456'))
        for kind in ('UNKNOWN','CAROUSEL_ALBUM',[],True):
            row={'data':[{'id':'789','media_type':kind},{'id':'456','media_type':'IMAGE'}]}
            client,_=self.client([(200,json.dumps(row).encode())])
            self.code('instagram_invalid_response',lambda:client.read_children('555'))
        for kind,product in (('IMAGE','FEED'),('VIDEO','REELS'),('CAROUSEL_ALBUM','FEED')):
            row=media(media_type=kind,media_product_type=product)
            client,_=self.client([(200,json.dumps(row).encode())]);self.assertEqual(client.read_media('456'),row)

    def test_urls_reject_raw_and_percent_encoded_control_characters(self):
        for suffix in ('\x80','\x9f','%0a','%00','%7f','%C2%80','%c2%9f','x%250a%0D'):
            client,calls=self.client()
            self.code('instagram_invalid_request',lambda:client.create_image('123',IMAGE+suffix,''))
            self.assertEqual(calls,[])
            client,_=self.client([(200,json.dumps(media(permalink='https://www.instagram.com/p/A/'+suffix)).encode())])
            self.code('instagram_invalid_response',lambda:client.read_media('456'))
