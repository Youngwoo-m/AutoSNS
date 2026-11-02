"""Facebook 고정 runtime 조립. 가짜 services와 공통 BridgeHost만 사용, 실제 API/자격 없음."""
from dataclasses import replace
from datetime import datetime,timezone,timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import hashlib
import os
import sys
import tempfile
import unittest

from common.operations.models import Registry,Connection,ContractError
from common.operations.runtime_models import PublicationContext,SubmissionPermit
from common.operations.admission_context import AdmissionReadContext
from common.shared.axlock import AxLock,LockPaths
from common.publishers.facebook_payloads import build_facebook_payload
from common.publishers.facebook_runtime import build_facebook_catalog,build_facebook_handlers,build_facebook_host,bridge_bootstrap
from common.publishers.legacy_bridge import prepared_digest

NOW=datetime(2026,11,2,tzinfo=timezone.utc)


def registry():
    keys=('personal.facebook','dept.facebook')
    return Registry('r',{'personal':{},'dept':{}},
        {key+'.credential':dict(account_id=key.split('.')[0],platform='facebook') for key in keys},
        {owner:dict(account_id=owner,lock_resource='profile:insta' if owner=='dept' else 'profile:tistory') for owner in ('personal','dept')},
        {key:Connection(key,key.split('.')[0],'facebook',target_id='123' if key.startswith('dept') else '789',credential_ref=key+'.credential',profile_ref=key.split('.')[0],enabled=True,capabilities=('text_only',)) for key in keys},
        {'job':dict(executor_id='facebook.dept',connection_id='dept.facebook',enabled=True,execution_owner='managed',managed_eligible=True,owner_account_id='personal',policy_revision='p')},{},{})


def context(**changes):
    return PublicationContext(**dict(dict(content_id='content',content_revision=1,manifest_hash='manifest',owner_account_id='personal',destination_account_id='dept',connection_id='dept.facebook',target_id='123',publication_purpose='initial',schedule_slot='slot',options={'text_only':True},schedule_condition={},registry_revision='r',policy_revision='p',auth_checked_at=NOW,auth_expires_at=NOW+timedelta(hours=1),review_report_hashes=('review',),platform='facebook',run_id='run'),**changes))


def payload(ctx=None):
    ctx=ctx or context()
    return build_facebook_payload(dict(id='content',revision=1,manifest_hash='manifest',owner_account_id='personal',original='개인 원본',variants=[dict(destination_account_id='dept',platform='facebook',text='학과 교차 게시')]),ctx)


class Services:
    def __init__(self):self.calls=[];self.before_write=None
    def inspect(self,target):self.calls.append(('inspect',target));return dict(platform='facebook',authenticated=True,target_id='123',login_subject='123',status='ready',verification_method='test_only')
    def submit(self,prepared,target):
        self.calls.append(('submit',prepared,target))
        if self.before_write:self.before_write()
        self.calls.append(('write',))
        return dict(outcome='submitted',remote_id='123_456')
    def row(self):return dict(remote_id='123_456',target_id='123',text='학과 교차 게시',body_sha256=hashlib.sha256('학과 교차 게시'.encode()).hexdigest(),media_sha256=[],created_at=NOW.isoformat(),url='https://www.facebook.com/123/posts/456',visibility='unknown')
    def read_post(self,target,remote):self.calls.append(('read',target,remote));return self.row()
    def lookup(self,target,attempt):self.calls.append(('lookup',target,attempt));return [self.row()]


class FacebookRuntimeTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.registry=registry();self.services=Services();self.factories=[]
        def factory(key,credentials):self.factories.append((key,credentials));return self.services
        self.factory=factory

    def handlers(self,**kwargs):return build_facebook_handlers(self.registry,services_factory=self.factory,clock=lambda:NOW,**kwargs)

    def test_default_catalog_and_bootstrap_are_disabled_and_explicit_catalog_has_fixed_module(self):
        self.assertEqual(dict(build_facebook_catalog(self.registry).executors),{})
        catalog=build_facebook_catalog(self.registry,configured=True)
        self.assertEqual(set(catalog.executors),{'facebook.dept'});spec=catalog.executors['facebook.dept']
        self.assertEqual(spec.module,'common.publishers.facebook');self.assertEqual(spec.mutation_actions,('publish',));self.assertEqual(spec.job_ids,('job',))
        with self.assertRaises(ContractError) as caught:bridge_bootstrap()
        self.assertEqual(caught.exception.code,'facebook_runtime_unconfigured');self.assertEqual(self.factories,[])

    def test_catalog_requires_enabled_managed_eligible_job_and_matching_page_connection(self):
        job=dict(self.registry.jobs['job'])
        for change in (dict(enabled=False),dict(execution_owner='legacy'),dict(managed_eligible=False),dict(connection_id='personal.facebook')):
            reg=replace(self.registry,jobs={'job':dict(job,**change)})
            self.assertEqual(dict(build_facebook_catalog(reg,configured=True).executors),{})
        for connection in (replace(self.registry.connections['dept.facebook'],enabled=False),replace(self.registry.connections['dept.facebook'],platform='threads')):
            reg=replace(self.registry,connections={'dept.facebook':connection})
            self.assertEqual(dict(build_facebook_catalog(reg,configured=True).executors),{})

    def test_inspect_expiry_is_server_clock_bound_and_admission_context_is_read_only(self):
        handlers=self.handlers();result=handlers[('facebook.dept','inspect_target')](context().to_dict(),{},'credential')
        self.assertEqual(result['checked_at'],NOW.isoformat());self.assertEqual(result['expires_at'],(NOW+timedelta(minutes=5)).isoformat())
        self.assertEqual(self.factories,[('dept.facebook','credential')])
        admission=AdmissionReadContext('dept.facebook','dept','123','facebook','r','personal','p','run','delivery',1)
        handlers[('facebook.dept','inspect_target')](admission.to_dict(),{},None)
        with self.assertRaises(ContractError):handlers[('facebook.dept','publish')](admission.to_dict(),payload(),None)

    def test_context_and_exact_prepared_binding_are_rejected_before_service_factory(self):
        handlers=self.handlers()
        for change in (dict(target_id='999'),dict(destination_account_id='personal'),dict(connection_id='personal.facebook'),dict(registry_revision='other'),dict(platform='threads')):
            with self.assertRaises(ContractError):handlers[('facebook.dept','inspect_target')](context(**change).to_dict(),{},None)
        for change in (dict(owner_account_id='dept'),dict(content_revision=2),dict(extra='PRIVATE'),dict(body_sha256='0'*64),dict(media_sha256=['asset'])):
            with self.assertRaises(ContractError):handlers[('facebook.dept','publish')](context().to_dict(),dict(payload(),**change),None)
        self.assertEqual(self.factories,[])

    def test_known_id_read_and_lookup_have_normalized_destination_without_public_claim(self):
        handlers=self.handlers();ctx=context().to_dict()
        result=handlers[('facebook.dept','verify')](ctx,{'remote_id':'123_456'},None)
        self.assertEqual(result['observation']['destination_account_id'],'dept');self.assertEqual(result['observation']['visibility'],'unknown')
        found=handlers[('facebook.dept','lookup')](ctx,{'attempt':{'remote_id':'123_456','created_at':NOW.isoformat()}},None)
        self.assertEqual(found['candidates'],[result['observation']]);self.assertEqual(found['checked_at'],NOW.isoformat())
        before=len(self.factories)
        for action,data in [('verify',{'remote_id':'999_456'}),('verify',{'remote_id':'123_456','endpoint':'arbitrary'}),('lookup',{'attempt':{}}),('inspect_target',{'target_id':'999'})]:
            with self.assertRaises(ContractError):handlers[('facebook.dept',action)](ctx,data,None)
        self.assertEqual(len(self.factories),before)

    def test_host_preserves_common_bridge_and_checks_stop_immediately_before_service_write(self):
        locks=AxLock(LockPaths.from_root(self.root/'source'),process_probe=lambda _:False)
        store=SimpleNamespace()
        host=build_facebook_host(self.registry,build_facebook_catalog(self.registry,configured=True),store,locks,services_factory=self.factory,credential_catalog={},credential_resolver=lambda *a,**k:self.fail('credentials not requested'),clock=lambda:NOW)
        from common.publishers.bridge_host import BridgeHost
        self.assertIsInstance(host,BridgeHost);self.assertIs(store.locks,locks)
        host.handlers[('facebook.dept','publish')](context().to_dict(),payload(),None)
        self.assertEqual(self.services.calls[-1],('write',))
        locks.set_stop('test')
        before=len([c for c in self.services.calls if c[0]=='write'])
        with self.assertRaises(ContractError):host.handlers[('facebook.dept','publish')](context().to_dict(),payload(),None)
        self.assertEqual(len([c for c in self.services.calls if c[0]=='write']),before)

    def test_managed_oauth_publication_is_still_rejected_by_common_host_before_resolver_or_leaf(self):
        ctx=context();data=payload();digest=prepared_digest(data);pid=os.getpid()
        store=SimpleNamespace(get_attempt=lambda _:dict(context_hash=ctx.context_hash),get_run=lambda _:dict(process_identity={'pid':pid},occurrence={'job_id':'job','phase':'submit','mode':'live'}))
        locks=AxLock(LockPaths.from_root(self.root/'source'),process_probe=lambda _:False)
        resolver=SimpleNamespace(use=lambda *a,**k:self.fail('managed write resolver must not run'))
        catalog=build_facebook_catalog(self.registry,configured=True)
        host=build_facebook_host(self.registry,catalog,store,locks,services_factory=self.factory,credential_catalog={},credential_resolver=resolver,clock=lambda:NOW)
        permit=SubmissionPermit('attempt','nonce','run',1,NOW+timedelta(minutes=1),ctx.context_hash,'approval')
        request=dict(context=ctx.to_dict(),payload=data,parent={},permit=permit.to_dict(),prepared_hash=digest)
        spec=replace(catalog.executors['facebook.dept'],interpreter=Path(sys.executable),cwd=Path.cwd())
        with patch('common.publishers.bridge_host._registered_spec',return_value=spec),patch('common.publishers.bridge_host.validate_job_binding'),patch('common.publishers.bridge_host.check_parent_evidence'):
            with self.assertRaises(ContractError) as caught:
                host.execute('facebook.dept','publish',request,'nonce',bootstrap_module='common.publishers.facebook',parent_pid=pid,secret_binding=dict(executor_id='facebook.dept',action='publish',context_hash=ctx.context_hash,prepared_hash=digest))
        self.assertEqual(caught.exception.code,'managed_publication_unverified');self.assertEqual(self.factories,[])

    def test_actual_service_adapter_and_runtime_preserve_crosspost_and_verified_public_url(self):
        import json
        import sqlite3
        from contextlib import closing
        from common.operations.content_store import ContentStore
        from common.operations.runtime_store import RuntimeStore
        from common.operations.verification import verify_delivery
        from common.publishers.facebook import FacebookAdapter
        from common.publishers.facebook_services import FacebookJournal,FacebookServices
        from tests.publishers import test_facebook_services as fixture
        root=self.root/'managed';content=ContentStore(root);content.initialize()
        snapshot=content.create('personal',dict(title='안전 원고',kind='article',original='개인 원문',variants=[dict(destination_account_id='dept',platform='facebook',text='안전 원고')]))
        ctx=context(content_id=snapshot['id'],manifest_hash=snapshot['manifest_hash'])
        journal=FacebookJournal(root);journal.initialize();client=fixture.Client()
        service=FacebookServices(client,journal,lambda:NOW,public_probe=fixture.public,page_authorizer=fixture.authorize)
        handlers=build_facebook_handlers(self.registry,services_factory=lambda key,credentials:service,clock=lambda:NOW)
        class Bridge:
            store=SimpleNamespace(content_store=content)
            def read(self,executor,action,context,payload):return handlers[(executor,action)](context.to_dict(),payload,None)
            def submit(self,executor,context,prepared,permit):return handlers[(executor,'publish')](context.to_dict(),prepared,None)
        adapter=FacebookAdapter(self.registry,Bridge());store=RuntimeStore(root,self.registry,content);store.initialize()
        with closing(sqlite3.connect(root/'operations.sqlite3')) as db:
            db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?)',('run','job',NOW.isoformat(),'prepare','fixture','{}'))
            db.execute('INSERT INTO deliveries VALUES(?,?,?,?,?,?,?,?)',('delivery',snapshot['id'],1,'dept.facebook','initial','slot','fixture',json.dumps({'status':'ready','approval':{'subject_hash':'fixture'}})))
            db.commit()
        store.locks=AxLock(LockPaths.from_root(self.root/'source'),process_probe=lambda _:False)
        store.create_run('run');store.create_delivery('delivery','run',ctx)
        store.record_publication_approval('delivery',1,ctx.context_hash,'approval',ctx.review_report_hashes)
        lease=store.claim_run('run','worker',dict(host_id='fixture',pid=123,started_at=NOW.isoformat()),NOW)
        attempt=store.create_attempt('delivery',store.get_delivery('delivery')['version'],lease,ctx.context_hash,'approval',now=NOW)
        permit=store.issue_permit(attempt['id'],lease,ctx.context_hash,'approval',NOW);store.consume_permit(permit,lease,NOW)
        prepared=adapter.prepare(ctx,snapshot);result=adapter.submit(ctx,prepared,permit)
        self.assertEqual(result.outcome,'submitted');store.finish_attempt(attempt['id'],'submitted',remote_id=result.remote_id,url=result.url,evidence=result.evidence,now=NOW)
        checked=verify_delivery(store,'delivery',adapter,snapshot,now=NOW)
        self.assertEqual(checked.outcome,'verified');self.assertEqual(store.get_delivery('delivery')['state'],'verified')
        self.assertEqual(store.get_delivery('delivery')['url'],'https://www.facebook.com/123/posts/456')
        self.assertEqual(adapter.submit(ctx,prepared,object()).remote_id,'123_456')
        self.assertEqual(len([call for call in client.calls if call[0]=='post']),1);self.assertEqual(content.get(snapshot['id']),snapshot)
