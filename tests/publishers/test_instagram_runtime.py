"""고정 Instagram runtime의 조립·whitelist·기본 비활성 계약. 가짜 서비스만 사용한다."""
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
import unittest
from common.operations.admission_context import AdmissionReadContext
from common.operations.models import ContractError
from common.publishers.instagram_runtime import build_instagram_catalog,build_instagram_handlers,build_instagram_host,bridge_bootstrap
from common.publishers.instagram_payloads import build_instagram_payload
from tests.publishers.test_instagram import registry,context,snapshot,receipt,observation,NOW,REMOTE

class Services:
 def __init__(self,ctx):self.ctx=ctx;self.calls=[];self.before_write=None
 def inspect(self,target):self.calls.append(('inspect',target));return dict(platform='instagram',target_id=target['target_id'],authenticated=True,login_subject='account-user',status='ready',verification_method='fixture',token='PRIVATE')
 def submit(self,ctx,payload,target):
  self.calls.append(('submit',ctx,payload,target))
  if self.before_write:self.before_write()
  return dict(outcome='submitted',remote_id=REMOTE,evidence={'upload_receipt':receipt(ctx,False),'token':'PRIVATE'})
 def observe(self,ctx,target,remote_id):self.calls.append(('observe',target,remote_id));return {**observation(ctx),'token':'PRIVATE','private_url':'https://private.example.com'}
 def lookup(self,ctx,target,attempt):self.calls.append(('lookup',target,attempt));return [self.observe(ctx,target,attempt['remote_id'])]
class InstagramRuntimeTests(unittest.TestCase):
 def setUp(self):self.ctx=context();self.registry=registry(self.ctx);self.services=Services(self.ctx);self.factories=[]
 def factory(self,*args):self.factories.append(args);return self.services
 def handlers(self,**extra):return build_instagram_handlers(self.registry,services_factory=self.factory,clock=lambda:NOW,**extra)
 def test_catalog_and_bootstrap_are_disabled_without_explicit_server_configuration(self):
  self.assertEqual(dict(build_instagram_catalog(self.registry).executors),{});catalog=build_instagram_catalog(self.registry,configured=True);self.assertIn('instagram.dept',catalog.executors);self.assertEqual(self.factories,[])
  with self.assertRaises(ContractError):bridge_bootstrap()
  conn=self.registry.connections['dept.instagram'];disabled=replace(self.registry,connections={conn.id:replace(conn,enabled=False)});self.assertEqual(dict(build_instagram_catalog(disabled,configured=True).executors),{})
 def test_handler_creation_and_host_assembly_do_not_call_services_or_initialize_storage(self):
  handlers=self.handlers();self.assertEqual(self.factories,[]);self.assertIn(('instagram.dept','verify'),handlers)
  store=SimpleNamespace();host=build_instagram_host(self.registry,build_instagram_catalog(self.registry),store,object(),services_factory=self.factory,credential_catalog={},credential_resolver=None,clock=lambda:NOW)
  self.assertEqual(self.factories,[]);self.assertEqual(self.services.calls,[]);self.assertIs(store.locks,host.locks)
 def test_publish_revalidates_all_fifteen_fields_before_factory_and_forwards_only_safe_receipt(self):
  handler=self.handlers()[('instagram.dept','publish')];prepared=build_instagram_payload(snapshot(),self.ctx)
  for change in (dict(caption='changed'),dict(target_id='999'),dict(media_sha256=[]),dict(extra=True)):
   with self.assertRaises(ContractError):handler(self.ctx.to_dict(),{**prepared,**change},None)
  self.assertEqual(self.factories,[]);result=handler(self.ctx.to_dict(),prepared,None);self.assertEqual(result['outcome'],'submitted');self.assertIn('upload_receipt',result['evidence']);self.assertNotIn('token',result['evidence'])
 def test_read_handlers_bind_exact_known_id_and_strip_private_fields(self):
  handlers=self.handlers()
  for action,payload in (('verify',{'remote_id':REMOTE,'extra':True}),('lookup',{'attempt':{'search':'title'}}),('lookup',{'attempt':{'remote_id':'user/path'}})):
   with self.assertRaises(ContractError):handlers[('instagram.dept',action)](self.ctx.to_dict(),payload,None)
  self.assertEqual(self.factories,[])
  result=handlers[('instagram.dept','verify')](self.ctx.to_dict(),{'remote_id':REMOTE},None);self.assertEqual(result['observation']['destination_account_id'],'dept');self.assertIsNone(result['observation']['media_sha256']);self.assertNotIn('token',result['observation']);self.assertNotIn('private_url',result['observation'])
 def test_admission_context_is_inspection_only_and_stop_hook_runs_before_publish(self):
  ctx=AdmissionReadContext(connection_id='dept.instagram',destination_account_id='dept',target_id='123',platform='instagram',registry_revision='registry',owner_account_id='personal',policy_revision='p',run_id='run',planned_delivery_id='plan',plan_version=1)
  handlers=self.handlers();result=handlers[('instagram.dept','inspect_target')](ctx.to_dict(),{},None);self.assertTrue(result['authenticated']);self.assertNotIn('token',result)
  with self.assertRaises(ContractError):handlers[('instagram.dept','publish')](ctx.to_dict(),{},None)
  def stop():raise ContractError('fixture_stop')
  handler=self.handlers(before_write=stop)[('instagram.dept','publish')]
  with self.assertRaises(ContractError):handler(self.ctx.to_dict(),build_instagram_payload(snapshot(),self.ctx),None)

 def test_semantically_invalid_children_wait_without_rpc_error_and_lookup_filters_them(self):
  ctx=context('carousel',['image1','video1']);reg=registry(ctx);service=Services(ctx);bad=observation(ctx);bad['children']=list(reversed(bad['children']));bad['upload_receipt']=receipt(ctx,False)
  service.observe=lambda *args:bad
  handlers=build_instagram_handlers(reg,services_factory=lambda *args:service,clock=lambda:NOW)
  result=handlers[('instagram.dept','verify')](ctx.to_dict(),{'remote_id':REMOTE},None)
  self.assertIsNone(result['observation']);self.assertNotIn('url',result)
  lookup=handlers[('instagram.dept','lookup')](ctx.to_dict(),{'attempt':{'remote_id':REMOTE,'created_at':NOW.isoformat()}},None)
  self.assertEqual(lookup['candidates'],[])
  # 다른 계정·원격 주체 관측은 의미 불일치 처리로 완화하지 않는다.
  service.observe=lambda *args:{**bad,'destination_account_id':'personal'}
  with self.assertRaises(ContractError):handlers[('instagram.dept','verify')](ctx.to_dict(),{'remote_id':REMOTE},None)
 def test_first_wrong_children_stay_unpinned_then_correct_read_verifies_without_new_post(self):
  from tests.publishers.test_instagram_end_to_end import InstagramEndToEndTests,URL
  from common.operations.verification import verify_delivery
  import json,sqlite3
  from contextlib import closing
  fixture=InstagramEndToEndTests();self.addCleanup(fixture.doCleanups);fixture.setUp()
  ctx=fixture.context('carousel');adapter=fixture.adapter(ctx);store=fixture.submitted(ctx,adapter);posts=len(fixture.http.posts);fixture.http.reverse=True
  first=verify_delivery(store,'d',adapter,fixture.snap,now=NOW)
  self.assertEqual(first.outcome,'pending');self.assertIsNone(store.get_delivery('d')['url'])
  with closing(sqlite3.connect(fixture.root/'instagram-submissions.sqlite3')) as db:
   payload=json.loads(db.execute('SELECT data FROM instagram_submissions').fetchone()[0])
  self.assertIsNone(payload['upload_receipt']['published_children']);fixture.http.reverse=False
  second=verify_delivery(store,'d',adapter,fixture.snap,now=NOW)
  self.assertEqual(second.outcome,'verified');self.assertEqual(store.get_delivery('d')['url'],URL);self.assertEqual(len(fixture.http.posts),posts)
  with closing(sqlite3.connect(fixture.root/'instagram-submissions.sqlite3')) as db:
   final=json.loads(db.execute('SELECT data FROM instagram_submissions').fetchone()[0])
  self.assertEqual([child['id'] for child in final['upload_receipt']['published_children']],['701','702'])
