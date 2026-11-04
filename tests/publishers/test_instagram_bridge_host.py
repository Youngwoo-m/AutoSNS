"""실제 Instagram BridgeHost의 부모 잠금·일회 permit·자격·STOP 경계.

직접 execute(RPC frame)를 호출하며 자식 process/native API/외부 전송은 없다. 부모 PID의
OS 시작시각 조회만 가짜로 고정하고 실제 임시 flock/descriptor 확인과 RuntimeStore의
승인·lease·consume·redeem 및 고정 실행기 검증은 유지한다. native bootstrap은 열지 않는다.
"""
from contextlib import closing,contextmanager
from dataclasses import replace
import copy
import json
import os
import sqlite3
import unittest
from unittest.mock import patch
from common.operations.models import ContractError
from common.publishers.instagram_payloads import build_instagram_payload
from common.publishers.instagram_runtime import build_instagram_catalog,build_instagram_host
from common.publishers.legacy_bridge import parent_evidence,prepared_digest
from tests.publishers import test_instagram_end_to_end as fixture_types
NOW=fixture_types.NOW
REMOTE=fixture_types.REMOTE

class FakeService:
    def __init__(self,locks):self.locks=locks;self.before_write=lambda:None;self.writes=0;self.stop_on_submit=False
    def submit(self,ctx,prepared,target):
        if self.stop_on_submit:self.locks.set_stop('fixture late STOP')
        self.before_write();self.writes+=1
        return dict(outcome='submitted',remote_id=REMOTE,evidence={})
class InstagramBridgeHostTests(unittest.TestCase):
    def setUp(self):
        fixture=fixture_types.InstagramEndToEndTests();self.addCleanup(fixture.doCleanups);fixture.setUp();self.fixture=fixture
        job={**fixture.registry.jobs['instagram-job'],'owner_account_id':'personal','policy_revision':'p'}
        fixture.registry=replace(fixture.registry,jobs={'instagram-job':job},policies={'p':{'auth_max_age_seconds':300}})
        self.ctx=fixture.context();self.store,self.attempt,self.permit=fixture.started(self.ctx);self.locks=self.store.locks
        occurrence=dict(job_id='instagram-job',phase='submit',mode='live',scheduled_at_utc=NOW.isoformat(),request_kind='new_publication')
        with closing(sqlite3.connect(fixture.root/'operations.sqlite3')) as db:
            db.execute('UPDATE runs SET payload=? WHERE id=?',(json.dumps(occurrence),'r'))
            identity={**self.store.get_run('r')['process_identity'],'pid':os.getpid()}
            db.execute('UPDATE runtime_runs SET process_identity=? WHERE id=?',(json.dumps(identity),'r'));db.commit()
        self.prepared=build_instagram_payload(fixture.snap,self.ctx);self.digest=prepared_digest(self.prepared)
        self.catalog=build_instagram_catalog(fixture.registry,configured=True)
        self.service=FakeService(self.locks);self.credentials=object();self.resolved=[];self.factories=[]
    def resolver(self,reference,**binding):self.resolved.append((reference,binding));return self.credentials
    def host(self,*,resolver=None,wrong_owner=False):
        def factory(identifier,credentials):self.factories.append((identifier,credentials));return self.service
        return build_instagram_host(self.fixture.registry,self.catalog,self.store,self.locks,services_factory=factory,
            credential_catalog={'dept.instagram.credential':dict(credential_ref='dept.instagram.credential',account_id='personal' if wrong_owner else 'dept',platform='instagram')},
            credential_resolver=self.resolver if resolver is None else resolver,clock=lambda:NOW)
    @contextmanager
    def request(self):
        # 실제 프로세스를 생성/조회하지 않는다. 소유 descriptor와 부모 PID 비교는 그대로 유지한다.
        with patch('common.publishers.legacy_bridge._process_start',return_value='fixture-start'),patch('ctypes.CDLL',side_effect=AssertionError('native forbidden')):
            with self.locks.hold(['profile:insta'],job='fixture-parent',wait=.1):
                parent=parent_evidence(self.fixture.registry,self.locks,self.ctx.to_dict())
                yield dict(context=self.ctx.to_dict(),payload=self.prepared,parent=parent,permit=self.permit.to_dict(),prepared_hash=self.digest)
    def execute(self,host,frame,*,nonce=None,binding=None):
        secret=dict(executor_id='instagram.dept',action='publish',context_hash=self.ctx.context_hash,prepared_hash=self.digest)
        return host.execute('instagram.dept','publish',frame,self.permit.nonce if nonce is None else nonce,
            bootstrap_module='common.publishers.instagram',parent_pid=os.getpid(),secret_binding=secret if binding is None else binding)
    def redemptions(self):
        with closing(sqlite3.connect(self.fixture.root/'operations.sqlite3')) as db:return db.execute('SELECT COUNT(*) FROM bridge_redemptions').fetchone()[0]
    def test_actual_host_redeems_real_consumed_permit_once_and_binds_fake_credentials(self):
        host=self.host()
        with self.request() as frame:
            result=self.execute(host,frame);self.assertEqual(result['outcome'],'submitted');self.assertEqual(result['remote_id'],REMOTE)
            with self.assertRaises(Exception):self.execute(host,frame)
        self.assertEqual(self.service.writes,1);self.assertEqual(self.redemptions(),1)
        self.assertEqual(self.resolved[0],('dept.instagram.credential',dict(account_id='dept',platform='instagram',scope='publication')))
        self.assertEqual(self.factories,[('dept.instagram',self.credentials)])
    def test_absent_or_forged_permit_binding_never_redeems_or_calls_leaf(self):
        with self.request() as frame:
            missing={k:v for k,v in frame.items() if k!='permit'}
            with self.assertRaises(ContractError):self.execute(self.host(),missing)
            for nonce,binding in (('',None),(self.permit.nonce,{'executor_id':'instagram.personal'}),('wrong',None)):
                with self.assertRaises(Exception):self.execute(self.host(),frame,nonce=nonce,binding=binding)
        self.assertEqual(self.service.writes,0);self.assertEqual(self.factories,[]);self.assertEqual(self.redemptions(),0)
    def test_parent_proof_and_credential_owner_cannot_be_rebound(self):
        with self.request() as frame:
            forged=copy.deepcopy(frame);forged['parent']['pid']+=1
            with self.assertRaises(ContractError):self.execute(self.host(),forged)
            with self.assertRaises(ContractError):self.execute(self.host(wrong_owner=True),frame)
        self.assertEqual(self.resolved,[]);self.assertEqual(self.factories,[]);self.assertEqual(self.redemptions(),0)
    def test_managed_oauth_publication_missing_authority_never_redeems_or_calls_leaf(self):
        class Managed:
            @contextmanager
            def use(self,*a,**kw):yield object()
        with self.request() as frame:
            with self.assertRaises(ContractError) as caught:self.execute(self.host(resolver=Managed()),frame)
        self.assertEqual(caught.exception.code,'managed_publication_unverified');self.assertEqual(self.factories,[]);self.assertEqual(self.redemptions(),0)
    def test_stop_before_redemption_never_calls_resolver_or_leaf(self):
        with self.request() as frame:
            self.locks.set_stop('fixture STOP')
            with self.assertRaises(ContractError):self.execute(self.host(),frame)
        self.assertEqual(self.resolved,[]);self.assertEqual(self.factories,[]);self.assertEqual(self.redemptions(),0)
    def test_late_stop_preserves_runtime_before_write_hook_after_redemption(self):
        self.service.stop_on_submit=True
        with self.request() as frame:
            with self.assertRaises(ContractError):self.execute(self.host(),frame)
        self.assertEqual(self.service.writes,0);self.assertEqual(self.redemptions(),1)
