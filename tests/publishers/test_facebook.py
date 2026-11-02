"""Facebook Pages adapter는 가짜 bridge로만 실행한다. 실제 게시·인증은 없다."""
from dataclasses import replace
from datetime import timedelta
import hashlib
import importlib
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
import unittest
from common.operations.models import Connection,ContractError
from common.operations.oauth_models import CredentialRef
from common.operations.oauth_stage_models import OwnedCredentialRef
from common.publishers.facebook import FacebookAdapter
from tests.publishers.test_facebook_payloads import NOW,context,snapshot

TEXT=' 학과 페이지 교차 게시\n그대로 '
def observation(ctx,**over):return {**dict(platform='facebook',remote_id=ctx.target_id+'_777',target_id=ctx.target_id,destination_account_id=ctx.destination_account_id,created_at=NOW.isoformat(),text=TEXT,body_sha256=hashlib.sha256(TEXT.encode()).hexdigest(),media_sha256=[],visibility='public',url='https://www.facebook.com/page/posts/777'),**over}
def registry(ctx):
 conn=Connection(ctx.connection_id,ctx.destination_account_id,'facebook',target_id=ctx.target_id,credential_ref=ctx.connection_id+'.credential')
 return SimpleNamespace(revision='registry',connections={conn.id:conn},credentials={conn.credential_ref:dict(account_id=conn.account_id,platform='facebook')})
class Bridge:
 def __init__(self,ctx):self.calls=[];self.result=dict(outcome='submitted',remote_id=ctx.target_id+'_777',url=None,evidence={'token':'secret'});self.raw=dict(checked_at=(NOW+timedelta(minutes=1)).isoformat(),observation=observation(ctx));self.store=SimpleNamespace(content_store=SimpleNamespace(get=lambda *args:{**snapshot(),'assets':[]}))
 def read(self,executor,action,ctx,request):self.calls.append((executor,action,request));return self.raw
 def submit(self,*args):self.calls.append(('submit',args));return self.result

class FacebookAdapterTests(unittest.TestCase):
 def setUp(self):self.ctx=context();self.reg=registry(self.ctx);self.bridge=Bridge(self.ctx);self.adapter=FacebookAdapter(self.reg,self.bridge)
 def test_crosspost_prepare_and_submit_keep_exact_bindings_without_url_requirement(self):
  prepared=self.adapter.prepare(self.ctx,snapshot());self.assertEqual(prepared['text'],TEXT);self.assertEqual(self.bridge.calls,[])
  result=self.adapter.submit(self.ctx,prepared,object());self.assertEqual(result.outcome,'submitted');self.assertEqual(result.remote_id,self.ctx.target_id+'_777');self.assertIsNone(result.url);self.assertNotIn('token',result.evidence)
  self.adapter.inspect_target(self.ctx);self.assertEqual(self.bridge.calls[-1][0],'facebook.dept')
 def test_wrong_target_account_registry_or_prepared_hash_never_reaches_submit(self):
  for changes in (dict(target_id='name'),dict(destination_account_id='personal'),dict(registry_revision='old')):
   with self.assertRaises(ContractError):self.adapter.inspect_target(replace(self.ctx,**changes))
  prepared=self.adapter.prepare(self.ctx,snapshot())
  for change in (dict(target_id='999'),dict(publication_purpose='other'),dict(text='changed'),dict(media_sha256=['a'*64]),dict(extra=True)):
   with self.assertRaises(ContractError):self.adapter.submit(self.ctx,{**prepared,**change},object())
  self.assertEqual(self.bridge.calls,[])
 def test_composite_post_must_belong_to_exact_page_and_unknown_is_sanitized(self):
  for remote in ('777','999_777',self.ctx.target_id+'_bad'):
   self.bridge.result=dict(outcome='submitted',remote_id=remote,url=None)
   self.assertEqual(self.adapter.submit(self.ctx,self.adapter.prepare(self.ctx,snapshot()),object()).outcome,'unknown')
  self.bridge.result=dict(outcome='unknown',evidence={'token':'secret'})
  result=self.adapter.submit(self.ctx,self.adapter.prepare(self.ctx,snapshot()),object());self.assertEqual(result.outcome,'unknown');self.assertNotIn('token',result.evidence)
 def test_managed_oauth_mutation_keeps_global_block(self):
  conn=self.reg.connections[self.ctx.connection_id];key='oauth:dept:facebook:dept.facebook:2';ref=OwnedCredentialRef(CredentialRef('autosns.oauth','dept','facebook','dept.facebook',2,'token'),uuid4().hex,'a'*64,'stage')
  self.reg.connections[conn.id]=replace(conn,credential_ref=key);self.reg.credentials={key:dict(account_id='dept',platform='facebook',credential_ref=ref)}
  result=self.adapter.submit(self.ctx,self.adapter.prepare(self.ctx,snapshot()),object());self.assertEqual(result.outcome,'failed');self.assertTrue(result.evidence['confirmed_not_submitted']);self.assertEqual(self.bridge.calls,[])
 def test_unknown_preserves_only_valid_known_remote_id_for_readonly_recovery(self):
  remote=self.ctx.target_id+'_777';self.bridge.result=dict(outcome='unknown',remote_id=remote,evidence={'token':'secret'})
  result=self.adapter.submit(self.ctx,self.adapter.prepare(self.ctx,snapshot()),object())
  self.assertEqual(result.outcome,'unknown');self.assertEqual(result.remote_id,remote);self.assertNotIn('token',result.evidence)
  self.bridge.result=dict(outcome='unknown',remote_id='999_777')
  self.assertIsNone(self.adapter.submit(self.ctx,self.adapter.prepare(self.ctx,snapshot()),object()).remote_id)
 def test_verify_requires_actual_remote_text_owner_media_time_and_public_visibility(self):
  remote=self.ctx.target_id+'_777';result=self.adapter.verify(self.ctx,remote,snapshot());self.assertEqual(result.outcome,'verified');self.assertNotIn('text',result.evidence)
  for changes in (dict(remote_id='999_777'),dict(target_id='999'),dict(destination_account_id='personal'),dict(body_sha256='b'*64),dict(media_sha256=['a'*64]),dict(text='changed'),dict(created_at=None)):
   self.bridge.raw['observation']=observation(self.ctx,**changes);self.assertNotEqual(self.adapter.verify(self.ctx,remote,snapshot()).outcome,'verified')
  for visibility in ('private','unknown'):
   self.bridge.raw['observation']=observation(self.ctx,visibility=visibility);self.assertEqual(self.adapter.verify(self.ctx,remote,snapshot()).outcome,'pending')
 def test_only_safe_facebook_urls_are_exposed(self):
  for url in ('http://www.facebook.com/page/posts/777','https://evil.example/post','https://user@www.facebook.com/post','https://www.facebook.com:443/post','https://www.facebook.com/post?access_token=secret','https://www.facebook.com/post#fragment','https://www.facebook.com/\npost','https://www.facebook.com','https://www.facebook.com/'):
   self.bridge.result=dict(outcome='submitted',remote_id=self.ctx.target_id+'_777',url=url)
   self.assertIsNone(self.adapter.submit(self.ctx,self.adapter.prepare(self.ctx,snapshot()),object()).url)
 def test_lookup_without_known_page_post_does_not_scan_and_known_match_is_bound(self):
  for attempt in ({'created_at':NOW.isoformat()},{'remote_id':'999_777','created_at':NOW.isoformat()}):
   self.assertEqual(self.adapter.lookup(self.ctx,attempt).outcome,'unsupported')
  self.assertEqual(self.bridge.calls,[])
  self.bridge.raw=dict(checked_at=(NOW+timedelta(minutes=1)).isoformat(),candidates=[observation(self.ctx)])
  result=self.adapter.lookup(self.ctx,dict(remote_id=self.ctx.target_id+'_777',created_at=NOW.isoformat()));self.assertEqual(result.outcome,'matched');self.assertEqual(self.bridge.calls[-1][1],'lookup')
  self.bridge.raw['candidates']=[];self.assertEqual(self.adapter.lookup(self.ctx,dict(remote_id=self.ctx.target_id+'_777',created_at=NOW.isoformat())).outcome,'unsupported')
 def test_import_constructor_and_prepare_are_inert(self):
  with patch('subprocess.run',side_effect=AssertionError('no process')),patch('builtins.open',side_effect=AssertionError('no file')):
   module=importlib.import_module('common.publishers.facebook');adapter=module.FacebookAdapter(self.reg,self.bridge);adapter.prepare(self.ctx,snapshot())
  self.assertEqual(self.bridge.calls,[])
