"""수동 검토 HTTP handler는 서버 권한과 public 필드만 전달한다."""
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
APP=Path(__file__).resolve().parents[1]/'ax-console/app'
if str(APP) not in sys.path:sys.path.insert(0,str(APP))
from web_instagram_reviews import handle,public,recognizes,FIELDS,CHECKS
from common.operations.content_store import StoreError
from common.operations.models import ContractError

PLAN='delivery_'+'a'*32
PATH='/api/v2/deliveries/'+PLAN+'/instagram-review'
def row():
    result={key:None for key in FIELDS}
    result.update(plan_id=PLAN,review_method='manual',status='not_reviewed',checks={key:False for key in CHECKS},assets=[])
    return result

class InstagramReviewHTTPContractTests(unittest.TestCase):
    def test_public_contract_drops_private_fields_and_binds_actor_on_post(self):
        calls=[];value={**row(),'actor':'PRIVATE','storage_path':'PRIVATE'}
        service=SimpleNamespace(get=lambda plan:value,record=lambda plan,body,**kwargs:(calls.append((plan,body,kwargs)) or value))
        self.assertEqual(set(handle(service,'GET',PATH,{},lambda:self.fail())),FIELDS)
        body=dict(expected_review_revision=0,subject_hash='a'*64,decision='approved',checks={key:True for key in CHECKS},notes='수동 확인')
        self.assertEqual(handle(service,'POST',PATH,{},lambda:body),row())
        self.assertEqual(calls,[(PLAN,body,{'actor':'console_user'})])
        for key in ('actor','owner_account_id','target_id','path'):
            with self.assertRaises(StoreError):handle(service,'POST',PATH,{},lambda:{**body,key:'PRIVATE'})
        self.assertEqual(len(calls),1)

    def test_unknown_query_method_and_error_text_are_not_forwarded(self):
        self.assertTrue(recognizes(PATH));self.assertFalse(recognizes(PATH+'/more'))
        self.assertIsNone(handle(None,'PUT',PATH,{},lambda:None))
        with self.assertRaises(StoreError):handle(None,'GET',PATH,{'owner':['dept']},lambda:None)
        def failed(_):raise ContractError('PRIVATE-TOKEN')
        with self.assertRaises(StoreError) as error:handle(SimpleNamespace(get=failed),'GET',PATH,{},lambda:None)
        self.assertEqual(error.exception.code,'storage_error');self.assertNotIn('PRIVATE',str(error.exception))
