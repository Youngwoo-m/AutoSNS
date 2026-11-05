import copy
import unittest
from common.operations.approvals import approval_fingerprint, is_approval_current
from common.operations.models import ContractError

class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = dict(id='c1', revision=1, manifest_hash='a'*64, owner_account_id='personal', title='제목', kind='article', original='원문', variants=[dict(destination_account_id='dept',platform='threads',text='변환')], sources=[dict(url='https://example.org',note='출처')], assets=[dict(id='a',sha256='1'*64),dict(id='b',sha256='2'*64)], reviews=[dict(kind='source',decision='reviewed',revision=1,manifest_hash='a'*64,method='manual',notes='확인',created_at='yesterday')])
        self.context = dict(content_id='c1',content_revision=1,owner_account_id='personal',destination_account_id='dept',platform='threads',target_id='thread-id',connection_id='dept.threads',publication_purpose='initial',schedule_slot='evening',scope='plan',execution_enabled=False,dry_run=True,policy_revision='p1',registry_revision='r1',options={'visibility':'public'},schedule_condition={'kind':'window','from':'2026-10-30T00:00:00Z','to':'2026-10-31T00:00:00Z'})
    def test_object_order_and_review_time_do_not_change_subject(self):
        changed=copy.deepcopy(self.snapshot); changed['reviews'][0]['created_at']='today'
        self.assertEqual(approval_fingerprint(self.snapshot,self.context),approval_fingerprint(dict(reversed(list(changed.items()))),self.context))
    def test_semantic_changes_invalidate(self):
        initial=approval_fingerprint(self.snapshot,self.context)
        for key,value in [('original','다른 원문'),('assets',list(reversed(self.snapshot['assets']))),('sources',[])]:
            with self.subTest(key=key):
                changed=copy.deepcopy(self.snapshot); changed[key]=value
                self.assertNotEqual(initial,approval_fingerprint(changed,self.context))
        for key,value in [('target_id','other'),('policy_revision','p2'),('registry_revision','r2'),('options',{'visibility':'private'}),('schedule_condition',{'kind':'fixed','at':'2026-10-30T12:00:00Z'})]:
            with self.subTest(key=key):
                changed={**self.context,key:value}; self.assertNotEqual(initial,approval_fingerprint(self.snapshot,changed))
        changed=copy.deepcopy(self.snapshot); changed['variants'][0]['text']='새 변환'
        self.assertNotEqual(initial,approval_fingerprint(changed,self.context))
    def test_review_version_and_target_and_live_scope_rejected(self):
        for key,value in [('target_id',None),('scope','publish'),('execution_enabled',True),('content_revision',2)]:
            with self.subTest(key=key),self.assertRaises(ContractError): approval_fingerprint(self.snapshot,{**self.context,key:value})
        changed=copy.deepcopy(self.snapshot); changed['reviews'][0]['revision']=2
        with self.assertRaises(ContractError): approval_fingerprint(changed,self.context)
    def test_only_matching_explicit_plan_approval_is_current(self):
        record=dict(decision='approved',source='manual',scope='plan',content_revision=1,subject_hash=approval_fingerprint(self.snapshot,self.context))
        self.assertTrue(is_approval_current(record,self.snapshot,self.context))
        for key,value in [('decision','revoked'),('source','automatic'),('scope','publish'),('content_revision',2),('subject_hash','bad'),('policy_revision','p2')]:
            self.assertFalse(is_approval_current({**record,key:value},self.snapshot,self.context))
        self.assertFalse(is_approval_current(self.snapshot['reviews'][0],self.snapshot,self.context))
    def test_invalid_json_is_contract_error(self):
        with self.assertRaises(ContractError): approval_fingerprint(self.snapshot,{**self.context,'options':{'x':float('nan')}})

    def test_missing_dry_contract_and_revisions_are_rejected(self):
        for key in ('scope','execution_enabled','dry_run','registry_revision','policy_revision'):
            changed=dict(self.context); changed.pop(key)
            with self.subTest(key=key),self.assertRaises(ContractError): approval_fingerprint(self.snapshot,changed)
    def test_malformed_nested_subject_is_contract_error(self):
        for key,value in [('variants',[None]),('assets',{}),('reviews',[None]),('sources','text')]:
            with self.subTest(key=key),self.assertRaises(ContractError): approval_fingerprint({**self.snapshot,key:value},self.context)
    def test_unrelated_variant_does_not_change_subject_except_manifest(self):
        changed=copy.deepcopy(self.snapshot)
        changed['variants'].append(dict(destination_account_id='personal',platform='blogger',text='별도 변환'))
        self.assertEqual(approval_fingerprint(self.snapshot,self.context),approval_fingerprint(changed,self.context))
