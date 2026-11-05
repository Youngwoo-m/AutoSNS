"""Instagram adapter 준비·영수증·관측 결속. 가짜 bridge만 쓰며 외부 API는 없다."""
from dataclasses import replace
from datetime import timedelta
import copy
from types import SimpleNamespace
from uuid import uuid4
import unittest
from common.operations.models import Registry,Connection,ContractError
from common.operations.oauth_models import CredentialRef
from common.operations.oauth_stage_models import OwnedCredentialRef
from common.publishers.instagram import InstagramAdapter
from common.publishers.instagram_payloads import build_instagram_payload
from tests.publishers.test_instagram_payloads import context,snapshot,NOW

REMOTE='900';URL='https://www.instagram.com/p/fixture/'
def registry(ctx=None):
 ctx=ctx or context();conn=Connection(ctx.connection_id,ctx.destination_account_id,'instagram',target_id=ctx.target_id,credential_ref=ctx.connection_id+'.credential',enabled=True)
 return Registry('registry',{'personal':{},'dept':{}},{conn.credential_ref:dict(account_id=conn.account_id,platform='instagram')},{},{conn.id:conn},{'job':dict(executor_id='instagram.dept',connection_id=conn.id,enabled=True,execution_owner='managed',managed_eligible=True)}, {},{})
def receipt(ctx=None,final=True):
 ctx=ctx or context();p=build_instagram_payload(snapshot(),ctx);carousel=p['media_format']=='carousel';children=[dict(id=str(901+i),media_type='IMAGE' if a['media_type']=='image/jpeg' else 'VIDEO') for i,a in enumerate(p['assets'])]
 return dict(kind='instagram_upload_receipt_v1',context_hash=ctx.context_hash,**{k:p[k] for k in ('connection_id','target_id','owner_account_id','destination_account_id','content_id','content_revision','manifest_hash','caption_sha256','media_format','assets')},remote_id=REMOTE,creation_id='700',child_creation_ids=[str(701+i) for i in range(len(p['assets']))] if carousel else [],published_children=children if carousel and final else None if carousel else [])
def observation(ctx=None):
 ctx=ctx or context();p=build_instagram_payload(snapshot(),ctx);fmt=p['media_format'];r=receipt(ctx)
 return dict(remote_id=REMOTE,target_id=ctx.target_id,destination_account_id=ctx.destination_account_id,created_at=NOW.isoformat(),text=p['caption'],body_sha256=p['caption_sha256'],media_sha256=None,media_format=fmt,media_type={'image':'IMAGE','reels':'VIDEO','carousel':'CAROUSEL_ALBUM'}[fmt],media_product_type='REELS' if fmt=='reels' else 'FEED',media_status='readable',children=r['published_children'] if fmt=='carousel' else [],visibility='public',url=URL,upload_receipt=r)
def attempt(ctx=None,outcome='submitted',source=True):
 ctx=ctx or context();return dict(created_at=NOW.isoformat(),request_started=True,context_hash=ctx.context_hash,outcome=outcome,result=dict(outcome=outcome,remote_id=REMOTE,evidence={'upload_receipt':receipt(ctx,False)} if source else {}))
class Bridge:
 def __init__(self,ctx):self.calls=[];self.raw=dict(checked_at=NOW.isoformat(),observation=observation(ctx));self.result=dict(outcome='submitted',remote_id=REMOTE,evidence={'upload_receipt':receipt(ctx,False)});self.store=SimpleNamespace(content_store=SimpleNamespace(get=lambda *a:snapshot()))
 def read(self,executor,action,ctx,payload):self.calls.append((executor,action,payload));return self.raw
 def submit(self,*args):self.calls.append(('submit',));return self.result
class InstagramAdapterTests(unittest.TestCase):
 def setUp(self):self.ctx=context();self.reg=registry(self.ctx);self.bridge=Bridge(self.ctx);self.adapter=InstagramAdapter(self.reg,self.bridge)
 def test_prepare_is_inert_and_submit_keeps_only_bounded_source_receipt(self):
  prepared=self.adapter.prepare(self.ctx,snapshot());self.assertEqual(self.bridge.calls,[]);result=self.adapter.submit(self.ctx,prepared,object());self.assertEqual(result.outcome,'submitted');self.assertEqual(result.remote_id,REMOTE);self.assertIsNone(result.url);self.assertEqual(result.evidence['upload_receipt']['context_hash'],self.ctx.context_hash);self.assertNotIn('url',result.evidence['upload_receipt'])
  self.adapter.inspect_target(self.ctx);self.assertEqual(self.bridge.calls[-1][0],'instagram.dept')
 def test_prepared_context_caption_selection_or_metadata_mismatch_is_rejected(self):
  prepared=self.adapter.prepare(self.ctx,snapshot())
  for change in (dict(target_id='999'),dict(caption='changed'),dict(media_sha256=['f'*64]),dict(media_format='reels'),dict(extra=True)):
   with self.assertRaises(ContractError):self.adapter.submit(self.ctx,{**prepared,**change},object())
  for change in (dict(target_id='name'),dict(registry_revision='other'),dict(destination_account_id='personal')):
   with self.assertRaises(ContractError):self.adapter.inspect_target(replace(self.ctx,**change))
  self.assertEqual(self.bridge.calls,[])
 def test_unknown_valid_id_and_receipt_are_preserved_without_secret_fields(self):
  self.bridge.result=dict(outcome='unknown',remote_id=REMOTE,evidence={'upload_receipt':receipt(),'token':'PRIVATE'});result=self.adapter.submit(self.ctx,self.adapter.prepare(self.ctx,snapshot()),object());self.assertEqual(result.outcome,'unknown');self.assertEqual(result.remote_id,REMOTE);self.assertIn('upload_receipt',result.evidence);self.assertNotIn('token',result.evidence)
  for bad in ({**receipt(),'url':'https://private.example.com/secret'}, {**receipt(),'context_hash':'a'*64},{**receipt(),'assets':[dict(id='image1',sha256='a'*64,size=True,media_type='image/jpeg')]}):
   self.bridge.result=dict(outcome='submitted',remote_id=REMOTE,evidence={'upload_receipt':bad});result=self.adapter.submit(self.ctx,self.adapter.prepare(self.ctx,snapshot()),object());self.assertNotIn('upload_receipt',result.evidence)
 def test_managed_oauth_mutation_remains_confirmed_not_submitted(self):
  conn=self.reg.connections[self.ctx.connection_id];key='oauth:dept:instagram:dept.instagram:1';ref=OwnedCredentialRef(CredentialRef('autosns.oauth','dept','instagram','dept.instagram',1,'token'),uuid4().hex,'a'*64,'stage')
  managed=replace(self.reg,connections={conn.id:replace(conn,credential_ref=key)},credentials={key:dict(account_id='dept',platform='instagram',credential_ref=ref)});adapter=InstagramAdapter(managed,self.bridge);result=adapter.submit(self.ctx,adapter.prepare(self.ctx,snapshot()),object());self.assertEqual(result.outcome,'failed');self.assertTrue(result.evidence['confirmed_not_submitted']);self.assertEqual(self.bridge.calls,[])
 def test_verify_uses_actual_caption_and_types_without_forging_remote_hashes(self):
  result=self.adapter.verify(self.ctx,REMOTE,snapshot());self.assertEqual(result.outcome,'verified');self.assertIsNone(result.evidence['media_sha256']);self.assertEqual(result.evidence['text'],observation()['text'])
  for change in (dict(text='changed'),dict(target_id='999'),dict(body_sha256='f'*64),dict(media_sha256=['a'*64]),dict(media_type='VIDEO'),dict(media_product_type='REELS'),dict(children=[dict(id='901',media_type='IMAGE')]),dict(url='https://www.instagram.com/accounts/login/')):
   self.bridge.raw['observation']={**observation(),**change};self.assertNotEqual(self.adapter.verify(self.ctx,REMOTE,snapshot()).outcome,'verified')
  self.bridge.raw['observation']={**observation(),'visibility':'unknown'};self.assertEqual(self.adapter.verify(self.ctx,REMOTE,snapshot()).outcome,'pending')
 def test_lookup_requires_known_id_and_authoritative_attempt_receipt(self):
  self.assertEqual(self.adapter.lookup(self.ctx,{'created_at':NOW.isoformat()}).outcome,'unsupported');self.assertEqual(self.bridge.calls,[])
  self.bridge.raw=dict(checked_at=NOW.isoformat(),candidates=[observation()]);self.assertEqual(self.adapter.lookup(self.ctx,attempt(source=False)).outcome,'unsupported');self.assertEqual(self.adapter.lookup(self.ctx,attempt()).outcome,'matched');self.assertEqual(self.adapter.lookup(self.ctx,attempt(outcome='unknown')).outcome,'matched')
 def test_carousel_order_and_provisional_receipt_pin_are_preserved(self):
  ctx=context('carousel',['image2','video1']);bridge=Bridge(ctx);adapter=InstagramAdapter(registry(ctx),bridge);result=adapter.submit(ctx,adapter.prepare(ctx,snapshot()),object());self.assertIsNone(result.evidence['upload_receipt']['published_children']);self.assertEqual(list(result.evidence['upload_receipt']['child_creation_ids']),['701','702'])
  bridge.raw=dict(checked_at=NOW.isoformat(),candidates=[observation(ctx)]);self.assertEqual(adapter.lookup(ctx,attempt(ctx)).outcome,'matched');bad=observation(ctx);bad['children']=list(reversed(bad['children']));bridge.raw['candidates']=[bad];self.assertNotEqual(adapter.lookup(ctx,attempt(ctx)).outcome,'matched')
