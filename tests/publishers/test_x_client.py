import json
import unittest
from common.operations.models import ContractError
from common.publishers.x_client import XApiClient, ME_PATH, POST_FIELDS

TOKEN='private-user-context-token'
POST={'id':'456','text':'원문 https://t.co/a','author_id':'123','created_at':'2026-11-04T00:00:00Z','entities':{'urls':[{'start':3,'end':17,'url':'https://t.co/a','expanded_url':'https://example.org/full','display_url':'example.org/full'}]}}


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.calls=[];self.raw=b'{}';self.status=200
        def transport(*args):self.calls.append(args);return self.status,self.raw
        self.client=XApiClient(TOKEN,transport=transport)
    def reply(self,value):self.raw=json.dumps(value,ensure_ascii=False).encode()
    def invalid(self,fn,code='x_invalid_response'):
        with self.assertRaises(ContractError) as caught:fn()
        self.assertEqual(str(caught.exception),code)
        self.assertNotIn(TOKEN,str(caught.exception))
    def test_default_inert_and_bad_arguments(self):
        self.invalid(lambda:XApiClient(TOKEN).inspect_account(),'x_transport_unregistered')
        for token in ('bad\r\n',None,''):
            self.invalid(lambda:XApiClient(token),'x_invalid_request')
        for value in ('','\x00','\ud800',None):self.invalid(lambda:self.client.create_post(value),'x_invalid_request')
        for value in ('abc',1,'1/2','1?x'):
            self.invalid(lambda:self.client.read_post(value),'x_invalid_request')
        self.assertEqual(self.calls,[])
        self.assertNotIn(TOKEN,repr(self.client))
    def test_methods_preserve_text_and_url_evidence(self):
        self.reply({'data':{'id':'123','username':'Name_1','name':'표시 이름','protected':False}})
        self.assertEqual(self.client.inspect_account(),{'id':'123','username':'Name_1','protected':False})
        self.assertEqual(self.calls[-1][0:2],('GET',ME_PATH))
        text='  한글 😀 & =\nhttps://example.org/a?b=1&c=2  '
        self.reply({'data':{'id':'456','text':'원격 반환 원문','edit_history_tweet_ids':['456']}})
        self.assertEqual(self.client.create_post(text),{'id':'456','text':'원격 반환 원문'})
        self.assertEqual(json.loads(self.calls[-1][3]),{'text':text})
        self.assertEqual(self.calls[-1][2],{'Accept':'application/json','Authorization':'Bearer '+TOKEN,'Content-Type':'application/json'})
        self.reply({'data':POST});observed=self.client.read_post('456')
        self.assertEqual(observed,POST)
        self.assertEqual(self.calls[-1][1],'/2/tweets/456'+POST_FIELDS)
        self.assertNotIn('public',observed);self.assertNotIn('body_sha256',observed)
    def test_missing_entities_normalized_and_withheld_preserved(self):
        value={k:v for k,v in POST.items() if k!='entities'}
        value['withheld']={'country_codes':['US'],'copyright':True,'scope':'tweet'}
        self.reply({'data':value});result=self.client.read_post('456')
        self.assertEqual(result['entities'],{'urls':[]});self.assertEqual(result['withheld'],value['withheld'])
    def test_schema_errors_pagination_and_unknown_fields_rejected(self):
        bodies=[{'data':POST,'meta':{'next_token':'secret'}},{'data':POST,'errors':[]},{'data':{**POST,'secret':TOKEN}},{'data':{**POST,'id':'999'}},{'data':{**POST,'author_id':123}},{'data':{**POST,'created_at':'tomorrow'}},{'data':{**POST,'entities':{'urls':[{**POST['entities']['urls'][0],'secret':TOKEN}]}}},{'data':{**POST,'entities':{'unknown':[]}}},{'data':{**POST,'withheld':{'country_codes':'US'}}}]
        for body in bodies:
            self.reply(body);self.invalid(lambda:self.client.read_post('456'))
        for account in ({'id':'123','username':'bad-name','protected':False},{'id':'123','username':'a'*16,'protected':False},{'id':'123','username':'valid','protected':'false'},{'id':'123','username':'valid'}):
            self.reply({'data':account});self.invalid(self.client.inspect_account)
    def test_duplicate_nonfinite_unicode_and_transport_errors_redacted(self):
        for raw in (b'{"data":{},"data":{}}',b'{"data":{"x":NaN}}',b'{"data":{"x":1e999}}',b'{"data":{"x":"\\ud800"}}',b'\xff',b'x'*(1024*1024+1)):
            self.raw=raw;self.invalid(self.client.inspect_account)
        def failure(*_):raise OSError(TOKEN)
        self.invalid(lambda:XApiClient(TOKEN,transport=failure).inspect_account(),'x_api_unavailable')
        self.status=429;self.invalid(self.client.inspect_account,'x_api_unavailable')
    def test_official_rich_url_metadata_is_validated_and_not_returned(self):
        url={**POST['entities']['urls'][0],'images':[{'height':630,'width':1200,'url':'https://example.org/image.jpg'}],'title':'Preview title','description':'Preview description','status':200,'media_key':'3_123'}
        self.reply({'data':{**POST,'entities':{'urls':[url]}}})
        self.assertEqual(self.client.read_post('456')['entities'],POST['entities'])
        for change in ({'status':'200'},{'images':[{'height':True,'width':1,'url':'https://example.org/a'}]},{'title':None},{'unknown':'private'}):
            self.reply({'data':{**POST,'entities':{'urls':[{**url,**change}]}}})
            self.invalid(lambda:self.client.read_post('456'))

    def test_entity_whitelist_and_standard_non_url_entities(self):
        value={**POST,'entities':{**POST['entities'],'hashtags':[{'start':18,'end':22,'tag':'태그'}],'mentions':[{'start':23,'end':28,'username':'User','id':'12'}],'annotations':[{'start':30,'end':35,'probability':0.8,'type':'Place','normalized_text':'서울'}]}}
        self.reply({'data':value});self.assertEqual(self.client.read_post('456')['entities'],POST['entities'])
        value['entities']['hashtags'][0]['extra']='secret';self.reply({'data':value});self.invalid(lambda:self.client.read_post('456'))


if __name__=='__main__':unittest.main()
