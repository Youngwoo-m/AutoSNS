"""실제 임시 Python 자식만 사용한다. socket/legacy 실행 없음."""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from contextlib import closing
from dataclasses import replace
from datetime import timedelta
from unittest.mock import Mock

from tests.operations.test_publication_gate import GateFixture
from tests.operations.test_runtime_store import NOW
from common.operations.execution_catalog import ExecutorSpec, ExecutionCatalog
from common.operations.publication_gate import consume_permit
from common.operations.models import Registry, Connection


class BridgeTests(GateFixture):
    def setUp(self):
        super().setUp()
        self.spec=ExecutorSpec('fixture',('j',),('submit','verify'),sys.executable,self.root,
                               'fixture_bridge',('publish',),('LANG',))
        self.catalog=ExecutionCatalog({'fixture':self.spec})
        self.module=self.root/'fixture_bridge.py'
        self.marker=self.root/'mutations'
        self.module.write_text(self.fixture_source())

    def fixture_source(self, before='', leaf=''):
        return f'''import os,sys,json
from pathlib import Path
from common.publishers.bridge_host import BridgeHost, main
from common.operations.execution_catalog import ExecutorSpec,ExecutionCatalog
from common.operations.models import Registry,Connection
from common.operations.runtime_store import RuntimeStore
from common.shared.axlock import AxLock,LockPaths
from datetime import datetime,timezone
ROOT=Path({str(self.root)!r})
def bootstrap():
    registry=Registry('r',{{'personal':{{}}}},{{}},{{'p':{{'account_id':'personal','lock_resource':'profile:tistory'}}}},{{'x':Connection('x','personal','tistory',target_id='t',profile_ref='p',enabled=True)}},{{'j':{{'enabled':True,'execution_owner':'managed','connection_id':'x','owner_account_id':'personal','policy_revision':'p'}}}},{{'p':{{'subscription_only':True,'auth_max_age_seconds':300}}}},{{}})
    store=RuntimeStore(ROOT/'managed',registry);store.initialize()
    locks=AxLock(LockPaths.from_root(ROOT/'source'),process_probe=lambda _:False)
    catalog=ExecutionCatalog({{'fixture':ExecutorSpec('fixture',('j',),('submit','verify'),sys.executable,ROOT,'fixture_bridge',('publish',),('LANG',))}})
    {before or 'pass'}
    def handler(ctx,payload,credentials):
        {leaf or "(ROOT/'mutations').open('a').write('1')"}
        return {{'outcome':'submitted','remote_id':'fixture-remote'}}
    return BridgeHost(registry,catalog,store,locks,{{('fixture','publish'):handler,('fixture','inspect_target'):lambda c,p,k:{{'platform':'tistory','target_id':'t'}}}},clock=lambda:datetime.fromisoformat({NOW.isoformat()!r}))
if __name__=='__main__':
    raise SystemExit(main(bootstrap=bootstrap,bootstrap_module=__spec__.name))
'''

    def bridge(self, spawn=None):
        from common.publishers.legacy_bridge import LegacyBridge
        return LegacyBridge(self.registry,self.catalog,self.store,self.store.locks,
                            spawn=spawn or subprocess.Popen,clock=lambda:NOW)

    def consumed(self):
        permit=self.ready()
        with closing(sqlite3.connect(self.store.root/'operations.sqlite3')) as db:
            row=json.loads(db.execute('SELECT process_identity FROM runtime_runs WHERE id=?',(self.run,)).fetchone()[0])
            row['pid']=os.getpid()
            db.execute('UPDATE runtime_runs SET process_identity=? WHERE id=?',(json.dumps(row),self.run));db.commit()
        consume_permit(self.store,permit,self.ctx,NOW)
        return permit

    def held(self):
        self.store.locks.process_probe=lambda _:False
        return self.store.locks.hold(['profile:tistory'],job='managed-publication',wait=.1)

    def test_unregistered_executor_spawn_zero(self):
        self.assertIsNotNone(importlib.util.find_spec('common.publishers.legacy_bridge'),'등록 bridge 구현 필요')
        spawn=Mock()
        with self.assertRaises(Exception):self.bridge(spawn).read('missing','inspect_target',self.ctx.to_dict(),{})
        spawn.assert_not_called()

    def test_forged_expired_or_replayed_permit_mutation_zero(self):
        permit=self.consumed()
        with self.held():
            for invalid in (replace(permit,nonce='forged'),replace(permit,expires_at=NOW-timedelta(seconds=1))):
                with self.assertRaises(Exception):self.bridge().submit('fixture',self.ctx,{},invalid)
            self.assertFalse(self.marker.exists())
            result=self.bridge().submit('fixture',self.ctx,{},permit)
            self.assertEqual(result['remote_id'],'fixture-remote')
            with self.assertRaises(Exception):self.bridge().submit('fixture',self.ctx,{},permit)
        self.assertEqual(self.marker.read_text(),'1')
        with closing(sqlite3.connect(self.store.root/'operations.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM bridge_redemptions').fetchone()[0],1)

    def test_cross_account_credential_ref_never_resolves(self):
        from common.publishers.legacy_bridge import resolve_registered_credentials
        resolver=Mock()
        registry=Registry('r',{'personal':{},'dept':{}},{'bad':{'account_id':'dept','platform':'blogger'}},{},
            {'x':Connection('x','personal','blogger',credential_ref='bad')},{},{},{})
        with self.assertRaises(Exception):resolve_registered_credentials('x',registry=registry,
            credential_catalog={'bad':{'account_id':'dept','platform':'blogger','credential_ref':'bad'}},resolver=resolver)
        resolver.assert_not_called()

    def test_stop_after_child_start_before_leaf_blocks(self):
        permit=self.consumed()
        self.module.write_text(self.fixture_source(before="locks.set_stop('fixture child start')"))
        with self.held():
            with self.assertRaises(Exception):self.bridge().submit('fixture',self.ctx,{},permit)
        self.assertFalse(self.marker.exists())

    def test_nonce_absent_from_argv_env_logs_and_json_result(self):
        permit=self.consumed();calls=[]
        def spawn(argv,**kw):
            self.assertNotIn(permit.nonce,json.dumps([argv,kw['env']]))
            self.assertIn('pass_fds',kw)
            calls.append(argv)
            return subprocess.Popen(argv,**kw)
        leaf="(ROOT/'mutations').open('a').write('1'); print(sys._getframe(1).f_locals['permit'].nonce); print(sys._getframe(1).f_locals['permit'].nonce,file=sys.stderr)"
        self.module.write_text(self.fixture_source(leaf=leaf))
        with self.held():result=self.bridge(spawn).submit('fixture',self.ctx,{},permit)
        self.assertEqual(len(calls),1)
        self.assertNotIn(permit.nonce,json.dumps(result))
        self.assertNotIn('sensitive',json.dumps(result))
        self.assertNotIn(permit.nonce.encode(),(self.store.root/'operations.sqlite3').read_bytes())

    def test_child_timeout_keeps_request_started(self):
        permit=self.consumed()
        self.module.write_text(self.fixture_source(leaf="(ROOT/'leaf-started').write_text('ready'); __import__('time').sleep(3)"))
        bridge=self.bridge();bridge.timeout=1.0
        with self.held():
            with self.assertRaisesRegex(Exception,'bridge_timeout'):bridge.submit('fixture',self.ctx,{},permit)
        self.assertEqual((self.root/'leaf-started').read_text(),'ready')
        # 실제 worker와 동일하게 명시 writer가 crash journal을 복구하고 unknown을 남긴다.
        self.store.finish_attempt(permit.attempt_id,'unknown',evidence={'reason':'submission_interrupted'},now=NOW)
        self.assertTrue(self.store.get_attempt(permit.attempt_id)['request_started'])
        self.assertFalse(self.store.get_attempt(permit.attempt_id)['resolved'])

    def test_read_write_action_and_editor_dry_never_spawn(self):
        spawn=Mock()
        for action in ('publish','dry','editor_dry','managed_submit'):
            with self.assertRaises(Exception):self.bridge(spawn).read('fixture',action,self.ctx.to_dict(),{})
        spawn.assert_not_called();self.assertFalse(self.marker.exists())

    def test_missing_parent_lock_and_ax_locked_alone_rejected(self):
        permit=self.consumed();spawn=Mock()
        from unittest.mock import patch
        with patch.dict(os.environ,{'AX_LOCKED':'1'}):
            with self.assertRaises(Exception):self.bridge(spawn).submit('fixture',self.ctx,{},permit)
        spawn.assert_not_called()

    def test_read_uses_real_child_without_redemption(self):
        self.consumed()
        with self.held():result=self.bridge().read('fixture','inspect_target',self.ctx.to_dict(),{})
        self.assertEqual(result,{'platform':'tistory','target_id':'t'})
        self.assertFalse(self.marker.exists())

    def test_concurrent_redemption_one_winner(self):
        import concurrent.futures
        permit=self.consumed()
        def redeem():
            try:return self.store.redeem_bridge(permit,'fixture','publish','a'*64,NOW)
            except Exception:return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:redeem(),range(2)))
        self.assertEqual(sum(r is not None for r in results),1)

    def test_prepared_hash_is_bound_to_secret_fd(self):
        from common.publishers.legacy_bridge import prepared_digest
        permit=self.consumed();bridge=self.bridge();exchange=bridge._exchange
        def tamper(process,raw):
            request=json.loads(raw);request['payload']={'changed':True}
            request['prepared_hash']=prepared_digest(request['payload'])
            return exchange(process,json.dumps(request).encode())
        bridge._exchange=tamper
        with self.held():
            with self.assertRaises(Exception):bridge.submit('fixture',self.ctx,{},permit)
        self.assertFalse(self.marker.exists())

    def test_credentials_scope_and_exact_reference(self):
        from common.publishers.legacy_bridge import resolve_registered_credentials
        registry=Registry('r',{'personal':{}},{'ok':{'account_id':'personal','platform':'blogger'}},{},
            {'x':Connection('x','personal','blogger',credential_ref='ok')},{},{},{})
        calls=[]
        def resolver(ref,**kw):calls.append((ref,kw));return object()
        for scope in ('read','publication'):
            value=resolve_registered_credentials('x',registry=registry,
                credential_catalog={'ok':{'account_id':'personal','platform':'blogger','credential_ref':'ok'}},
                resolver=resolver,scope=scope)
            self.assertIsNotNone(value)
        self.assertEqual([c[1]['scope'] for c in calls],['read','publication'])
        self.assertTrue(all(c[0]=='ok' and c[1]['account_id']=='personal' for c in calls))

    def test_approval_revoked_after_child_start_blocks_leaf(self):
        permit=self.consumed()
        code="store.record_publication_approval('d',store.get_delivery('d')['version'],store.get_delivery('d')['context_hash'],'revoked',store.get_delivery('d')['context']['review_report_hashes'],decision='revoked')"
        self.module.write_text(self.fixture_source(before=code))
        with self.held():
            with self.assertRaises(Exception):self.bridge().submit('fixture',self.ctx,{},permit)
        self.assertFalse(self.marker.exists())

    def test_import_has_no_db_log_browser_or_process_side_effect(self):
        import importlib
        from unittest.mock import patch
        with patch('sqlite3.connect',side_effect=AssertionError('DB import side effect')), \
             patch('subprocess.Popen',side_effect=AssertionError('process import side effect')), \
             patch.object(Path,'mkdir',side_effect=AssertionError('directory import side effect')):
            import common.publishers.legacy_bridge as bridge
            import common.publishers.bridge_host as host
            importlib.reload(bridge);importlib.reload(host)

    def test_read_cannot_select_executor_for_another_job(self):
        self.consumed();spawn=Mock()
        wrong=replace(self.spec,job_ids=('other-job',))
        self.catalog=ExecutionCatalog({'fixture':wrong})
        with self.held():
            with self.assertRaises(Exception):self.bridge(spawn).read('fixture','inspect_target',self.ctx.to_dict(),{})
        spawn.assert_not_called()

    def test_registry_target_change_between_parent_and_leaf_blocks(self):
        permit=self.consumed()
        source=self.fixture_source().replace("target_id='t'","target_id='other'")
        self.module.write_text(source)
        with self.held():
            with self.assertRaises(Exception):self.bridge().submit('fixture',self.ctx,{},permit)
        self.assertFalse(self.marker.exists())

    def test_bridge_output_limit_and_secret_result_rejected(self):
        permit=self.consumed()
        leaf="return {'nonce':sys._getframe(1).f_locals['permit'].nonce}"
        self.module.write_text(self.fixture_source(leaf=leaf))
        with self.held():
            with self.assertRaises(Exception):self.bridge().submit('fixture',self.ctx,{},permit)
        self.assertTrue(self.store.get_attempt(permit.attempt_id)['request_started'])
        self.assertFalse(self.store.get_attempt(permit.attempt_id)['resolved'])

    def test_large_payload_rejected_before_spawn(self):
        permit=self.consumed();spawn=Mock()
        with self.held():
            with self.assertRaisesRegex(Exception,'bridge_size_limit'):
                self.bridge(spawn).submit('fixture',self.ctx,{'body':'x'*(1024*1024+1)},permit)
        spawn.assert_not_called()

    def test_default_host_is_unavailable(self):
        from common.publishers.bridge_host import main
        self.assertNotEqual(main([]),0)
