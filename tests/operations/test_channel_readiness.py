"""채널 구현 현황은 실제 인증·실행 성공과 구분하며 순수하게 계산한다."""
from dataclasses import replace
from unittest.mock import patch
import unittest
from common.operations.channel_readiness import build_channel_readiness
from common.operations.content_store import StoreError
from common.operations.models import Registry,Connection

KEYS={'account_id','platform','connection_id','label','planning_enabled','target_status','authentication_status','publisher_status','verification_status','metrics_status','live_enabled','next_actions'}
PLATFORMS={'naver_blog','blogger','tistory','youtube','instagram','threads','x','facebook','tiktok'}
def registry():
    names=('dept.youtube','dept.blogger','dept.instagram','dept.naver_blog','dept.tiktok','dept.x','dept.threads','personal.blogger','personal.tistory','personal.naver_blog','personal.youtube')
    connections={name:Connection(name,name.split('.')[0],name.split('.')[1],target_id='target-'+name,enabled=True,credential_ref='PRIVATE-CREDENTIAL',profile_ref='PRIVATE-PROFILE',auth_status='unknown') for name in names}
    return Registry('r',{'personal':{},'dept':{}},{'PRIVATE-CREDENTIAL':{'token':'PRIVATE-TOKEN'}},{'PRIVATE-PROFILE':{'path':'PRIVATE-PATH'}},connections,{},{},{})

class ChannelReadinessTests(unittest.TestCase):
    def test_two_account_platform_matrix_preserves_existing_and_labels_missing(self):
        reg=registry();before=reg.to_dict();result=build_channel_readiness(reg)
        self.assertEqual(result['account_id'],'all');self.assertEqual(len(result['channels']),18)
        self.assertEqual({row['connection_id'] for row in result['channels'] if row['connection_id'] is not None},set(reg.connections))
        self.assertEqual(sum(row['connection_id'] is None for row in result['channels']),7)
        for account in ('personal','dept'):
            rows=[r for r in result['channels'] if r['account_id']==account]
            self.assertEqual({r['platform'] for r in rows},PLATFORMS)
            for row in rows:
                self.assertEqual(set(row),KEYS);self.assertIs(row['live_enabled'],False)
                self.assertTrue(row['next_actions']);self.assertTrue(all(type(x) is str for x in row['next_actions']))
                if row['connection_id'] is None:
                    self.assertIs(row['planning_enabled'],False);self.assertEqual(row['target_status'],'no_connection')
        self.assertEqual(reg.to_dict(),before)
    def test_account_filter_never_leaks_other_account_or_credentials(self):
        reg=registry()
        for account in ('personal','dept'):
            result=build_channel_readiness(reg,account)
            self.assertEqual(result['account_id'],account);self.assertTrue(all(r['account_id']==account for r in result['channels']))
            text=str(result)
            for secret in ('PRIVATE-CREDENTIAL','PRIVATE-PROFILE','PRIVATE-TOKEN','PRIVATE-PATH'):self.assertNotIn(secret,text)
    def test_implementation_status_is_not_inferred_from_auth_capabilities_or_enabled(self):
        reg=registry();connections=dict(reg.connections)
        connections['dept.instagram']=replace(connections['dept.instagram'],auth_status='connected',capabilities=('publish','metrics'),enabled=True)
        result=build_channel_readiness(replace(reg,connections=connections),'dept')
        by={r['platform']:r for r in result['channels']}
        self.assertEqual(by['instagram']['authentication_status'],'connected');self.assertIs(by['instagram']['live_enabled'],False)
        self.assertEqual(by['instagram']['publisher_status'],'implemented');self.assertEqual(by['instagram']['metrics_status'],'stored_only')
        self.assertEqual(by['threads']['publisher_status'],'text_only_implemented');self.assertEqual(by['threads']['verification_status'],'public_probe_required')
        self.assertEqual(by['facebook']['publisher_status'],'text_only_implemented');self.assertEqual(by['facebook']['verification_status'],'public_probe_required')
        self.assertEqual(by['youtube']['publisher_status'],'implemented');self.assertEqual(by['youtube']['verification_status'],'receipt_implemented');self.assertEqual(by['youtube']['metrics_status'],'implemented')
    def test_tistory_and_naver_browser_paths_and_x_cost_gate_are_explained(self):
        rows={r['platform']:r for r in build_channel_readiness(registry(),'personal')['channels']}
        self.assertEqual(rows['tistory']['publisher_status'],'browser_implemented');self.assertIn('공식 API',str(rows['tistory']['next_actions']))
        self.assertEqual(rows['naver_blog']['publisher_status'],'browser_implemented');self.assertIn('프로필',str(rows['naver_blog']['next_actions']))
        self.assertIn('결제',str(rows['x']['next_actions']));self.assertIn('페이지',str(rows['facebook']['next_actions']))
        self.assertIn('원본 자동 작업',str(rows['youtube']['next_actions']))
    def test_unknown_auth_is_not_echoed_and_recorded_target_property_is_preserved(self):
        reg=registry();connections=dict(reg.connections)
        connections['dept.youtube']=replace(connections['dept.youtube'],auth_status='PRIVATE-UNKNOWN-STATUS',target_id=None,planning_enabled=False)
        row=next(r for r in build_channel_readiness(replace(reg,connections=connections),'dept')['channels'] if r['platform']=='youtube')
        self.assertEqual(row['authentication_status'],'unknown');self.assertEqual(row['target_status'],'unverified');self.assertIs(row['planning_enabled'],False)
        row=next(r for r in build_channel_readiness(reg,'dept')['channels'] if r['platform']=='youtube')
        self.assertEqual(row['target_status'],'verified')
    def test_multiple_real_connections_are_not_collapsed_or_given_fake_ids(self):
        reg=registry();connections=dict(reg.connections)
        connections['second-youtube']=Connection('second-youtube','personal','youtube',target_id='second')
        rows=build_channel_readiness(replace(reg,connections=connections))['channels']
        self.assertEqual(len(rows),19);self.assertEqual(sum(r['account_id']=='personal' and r['platform']=='youtube' for r in rows),2)
    def test_inert_no_file_database_vault_or_network_access(self):
        reg=registry()
        with patch('builtins.open',side_effect=AssertionError('file I/O')),patch('sqlite3.connect',side_effect=AssertionError('database I/O')),patch('socket.socket',side_effect=AssertionError('network I/O')),patch('ctypes.CDLL',side_effect=AssertionError('native I/O')):
            result=build_channel_readiness(reg,services={})
        self.assertEqual(len(result['channels']),18)
    def test_invalid_account_registry_or_server_capability_override_rejected(self):
        for account in ('',None,True,'other'):
            with self.assertRaises(StoreError):build_channel_readiness(registry(),account)
        with self.assertRaises(StoreError):build_channel_readiness({})
        for services in (object(),{'live_enabled':True},{'metrics_enabled':True}):
            with self.assertRaises(StoreError):build_channel_readiness(registry(),services=services)

    def test_facebook_foundation_status_keeps_missing_connection_and_real_authorization_unproven(self):
        result=build_channel_readiness(registry())
        rows=[row for row in result['channels'] if row['platform']=='facebook']
        self.assertEqual(len(rows),2)
        for row in rows:
            self.assertIsNone(row['connection_id']);self.assertIs(row['planning_enabled'],False)
            self.assertEqual(row['target_status'],'no_connection');self.assertEqual(row['authentication_status'],'no_connection')
            self.assertEqual(row['publisher_status'],'text_only_implemented');self.assertEqual(row['verification_status'],'public_probe_required')
            self.assertEqual(row['metrics_status'],'stored_only');self.assertIs(row['live_enabled'],False)
            text=' '.join(row['next_actions'])
            for phrase in ('명시 선택','로그인 주체','페이지 자격','tasks','공개','아직'):self.assertIn(phrase,text)

    def test_instagram_foundation_never_implies_live_authorization_or_target(self):
        base=registry();connections=dict(base.connections)
        connections['dept.instagram']=replace(connections['dept.instagram'],target_id=None)
        base=replace(base,connections=connections)
        rows=[r for r in build_channel_readiness(base)['channels'] if r['platform']=='instagram']
        self.assertEqual(len(rows),2)
        for row in rows:
            self.assertEqual(row['publisher_status'],'implemented')
            self.assertEqual(row['verification_status'],'public_probe_required')
            self.assertEqual(row['metrics_status'],'stored_only');self.assertIs(row['live_enabled'],False)
            text=' '.join(row['next_actions'])
            for phrase in ('REELS','캐러셀','수동 검토','원본 전달 영수증','공개 호스팅','익명 공개','Instagram Login','직접 업로드','프로페셔널','미수락'):
                self.assertIn(phrase,text)
        personal=next(r for r in rows if r['account_id']=='personal')
        self.assertIsNone(personal['connection_id']);self.assertEqual(personal['target_status'],'no_connection')
        dept=next(r for r in rows if r['account_id']=='dept')
        self.assertEqual(dept['connection_id'],'dept.instagram');self.assertEqual(dept['target_status'],'unverified')
