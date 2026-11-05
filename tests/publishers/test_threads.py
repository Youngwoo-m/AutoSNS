"""Threads 텍스트 변환과 등록 adapter만 가짜 bridge로 검증한다."""
import copy
from dataclasses import replace
from datetime import datetime,timezone,timedelta
import hashlib
from types import SimpleNamespace
import unittest
from common.operations.models import Connection,ContractError
from common.operations.runtime_models import PublicationContext
from common.publishers.threads_payloads import build_threads_payload
from common.publishers.threads import ThreadsAdapter

NOW=datetime(2026,11,2,tzinfo=timezone.utc)
def context(account='dept',**over):
    values=dict(content_id='content',content_revision=2,manifest_hash='manifest',owner_account_id='personal',destination_account_id=account,connection_id=account+'.threads',target_id='123456',publication_purpose='initial',schedule_slot='slot',options={'text_only':True},schedule_condition={},registry_revision='registry',policy_revision='policy',auth_checked_at=NOW,auth_expires_at=NOW+timedelta(hours=1),review_report_hashes=('review',),platform='threads')
    return PublicationContext(**{**values,**over})
def snapshot():return dict(id='content',revision=2,manifest_hash='manifest',owner_account_id='personal',original=' 원문 그대로 ',variants=[dict(destination_account_id='dept',platform='threads',text=' 학과 교차 게시 ')],assets=[dict(id='image',sha256='a'*64,media_type='image/png')])
def registry(ctx):
    conn=Connection(ctx.connection_id,ctx.destination_account_id,'threads',target_id=ctx.target_id,credential_ref=ctx.connection_id+'.credential')
    return SimpleNamespace(revision='registry',connections={conn.id:conn},credentials={conn.credential_ref:dict(account_id=conn.account_id,platform='threads')})
def observation(ctx,text=' 학과 교차 게시 ',**over):return dict(remote_id='777',target_id=ctx.target_id,destination_account_id=ctx.destination_account_id,created_at=NOW.isoformat(),text=text,body_sha256=hashlib.sha256(text.encode()).hexdigest(),media_sha256=[],visibility='public',**over)
class Bridge:
    def __init__(self,ctx):self.calls=[];self.result=dict(outcome='submitted',remote_id='777',url='https://www.threads.net/@demo/post/abc',evidence={'token':'secret'});self.raw=dict(checked_at=(NOW+timedelta(minutes=1)).isoformat(),observation=observation(ctx));self.store=SimpleNamespace(content_store=SimpleNamespace(get=lambda *a:snapshot()))
    def read(self,executor,action,ctx,request):self.calls.append((executor,action,request));return self.raw
    def submit(self,*args):self.calls.append(('submit',args));return self.result
class ThreadsPayloadTests(unittest.TestCase):
    def test_explicit_text_only_preserves_source_and_selects_unique_cross_variant(self):
        ctx=context();source=snapshot();before=copy.deepcopy(source);payload=build_threads_payload(source,ctx)
        self.assertEqual(payload['text'],' 학과 교차 게시 ');self.assertEqual(payload['media_sha256'],[]);self.assertEqual(payload['body_sha256'],hashlib.sha256(payload['text'].encode()).hexdigest());self.assertEqual(source,before)
        self.assertEqual(build_threads_payload(source,context('personal'))['text'],' 원문 그대로 ')
        self.assertEqual(build_threads_payload(source,context(options={'text_only':True,'visibility':'public'}))['text'],' 학과 교차 게시 ')
    def test_exact_snapshot_options_variant_and_utf8_limits_required(self):
        for changes in (dict(id='other'),dict(revision=1),dict(manifest_hash='changed'),dict(owner_account_id='dept')):
            with self.assertRaises(ContractError):build_threads_payload({**snapshot(),**changes},context())
        for options in ({},{'text_only':False},{'text_only':1},{'text_only':True,'command':'publish'},{'text_only':True,'visibility':'private'}):
            with self.assertRaises(ContractError):build_threads_payload(snapshot(),context(options=options))
        for text in ('', ' '*5,'한'*501,'bad\ud800'):
            source={**snapshot(),'variants':[],'original':text}
            with self.assertRaises(ContractError):build_threads_payload(source,context())
        source=snapshot();source['variants']*=2
        with self.assertRaises(ContractError):build_threads_payload(source,context())
class ThreadsAdapterTests(unittest.TestCase):
    def setUp(self):self.ctx=context();self.reg=registry(self.ctx);self.bridge=Bridge(self.ctx);self.adapter=ThreadsAdapter(self.reg,self.bridge)
    def test_fixed_binding_inspect_prepare_and_sanitized_submit(self):
        self.adapter.inspect_target(self.ctx);self.assertEqual(self.bridge.calls[0][0],'threads.dept')
        prepared=self.adapter.prepare(self.ctx,snapshot());result=self.adapter.submit(self.ctx,prepared,object())
        self.assertEqual(result.outcome,'submitted');self.assertEqual(result.remote_id,'777');self.assertNotIn('token',result.evidence)
        for field,value in (('target_id','999'),('publication_purpose','other'),('text','changed'),('media_sha256',['a'*64])):
            with self.assertRaises(ContractError):self.adapter.submit(self.ctx,{**prepared,field:value},object())
    def test_wrong_target_account_or_registry_and_managed_mutation_fail_closed(self):
        for ctx in (replace(self.ctx,target_id='abc'),replace(self.ctx,registry_revision='old'),replace(self.ctx,destination_account_id='personal')):
            with self.assertRaises(ContractError):self.adapter.inspect_target(ctx)
        from common.operations.oauth_models import CredentialRef
        from common.operations.oauth_stage_models import OwnedCredentialRef
        from uuid import uuid4
        conn=self.reg.connections[self.ctx.connection_id];key='oauth:dept:threads:dept.threads:1';ref=OwnedCredentialRef(CredentialRef('autosns.oauth','dept','threads','dept.threads',1,'token'),uuid4().hex,'a'*64,'stage')
        self.reg.connections[conn.id]=replace(conn,credential_ref=key);self.reg.credentials={key:dict(account_id='dept',platform='threads',credential_ref=ref)}
        result=self.adapter.submit(self.ctx,self.adapter.prepare(self.ctx,snapshot()),object());self.assertEqual(result.outcome,'failed');self.assertTrue(result.evidence['confirmed_not_submitted']);self.assertEqual(self.bridge.calls,[])
    def test_verify_requires_actual_body_media_identity_public_time_and_safe_evidence(self):
        result=self.adapter.verify(self.ctx,'777',snapshot());self.assertEqual(result.outcome,'verified');self.assertEqual(list(result.evidence['media_sha256']),[])
        for change in ({'remote_id':'other'},{'target_id':'999'},{'destination_account_id':'personal'},{'body_sha256':'b'*64},{'media_sha256':['a'*64]}):
            self.bridge.raw['observation']={**observation(self.ctx),**change};self.assertEqual(self.adapter.verify(self.ctx,'777',snapshot()).outcome,'failed')
        self.bridge.raw['observation']={**observation(self.ctx),'visibility':'private'};self.assertEqual(self.adapter.verify(self.ctx,'777',snapshot()).outcome,'pending')
        self.bridge.raw['observation']={**observation(self.ctx),'created_at':None};self.assertNotEqual(self.adapter.verify(self.ctx,'777',snapshot()).outcome,'verified')
    def test_lookup_requires_known_id_and_never_broadly_scans(self):
        result=self.adapter.lookup(self.ctx,{'created_at':NOW.isoformat()});self.assertEqual(result.outcome,'unsupported');self.assertEqual(self.bridge.calls,[])
        self.bridge.raw=dict(checked_at=(NOW+timedelta(minutes=1)).isoformat(),candidates=[])
        result=self.adapter.lookup(self.ctx,{'created_at':NOW.isoformat(),'remote_id':'777'});self.assertEqual(result.outcome,'unsupported');self.assertEqual(self.bridge.calls[0][1],'lookup')

    def test_remote_text_is_rehashed_and_never_exposes_arbitrary_evidence(self):
        self.bridge.raw['observation']={**observation(self.ctx),'text':'changed','token':'secret'}
        self.assertNotEqual(self.adapter.verify(self.ctx,'777',snapshot()).outcome,'verified')
        self.bridge.raw['observation']={**observation(self.ctx),'token':'secret'}
        result=self.adapter.verify(self.ctx,'777',snapshot())
        self.assertEqual(result.outcome,'verified');self.assertNotIn('text',result.evidence);self.assertNotIn('token',result.evidence)
    def test_single_known_post_with_complete_actual_text_evidence_can_match(self):
        approved={**snapshot(),'assets':[]};self.bridge.store.content_store.get=lambda *args:approved
        self.bridge.raw=dict(checked_at=(NOW+timedelta(minutes=1)).isoformat(),candidates=[observation(self.ctx)])
        result=self.adapter.lookup(self.ctx,{'created_at':NOW.isoformat(),'remote_id':'777'})
        self.assertEqual(result.outcome,'matched');self.assertNotIn('text',result.candidates[0])
        self.bridge.raw['candidates'].append(observation(self.ctx))
        self.assertEqual(self.adapter.lookup(self.ctx,{'created_at':NOW.isoformat(),'remote_id':'777'}).outcome,'ambiguous')
