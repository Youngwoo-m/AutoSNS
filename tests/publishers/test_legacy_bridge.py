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
    return BridgeHost(registry,catalog,store,locks,{{('fixture','publish'):handler,('fixture','inspect_target'):lambda c,p,k:{{'platform':'tistory','target_id':'t'}}}},clock=lambda:datetime.fromisoformat({NOW.isoformat()!r}),module_root=ROOT)
if __name__=='__main__':
    raise SystemExit(main(bootstrap=bootstrap,bootstrap_module=__spec__.name))
'''

    def bridge(self, spawn=None):
        from common.publishers.legacy_bridge import LegacyBridge
        return LegacyBridge(self.registry,self.catalog,self.store,self.store.locks,
                            spawn=spawn or subprocess.Popen,clock=lambda:NOW,module_root=self.root)

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

    def test_stale_holder_json_without_flock_rejected_by_parent_and_child(self):
        from common.publishers.legacy_bridge import parent_evidence,check_parent_evidence
        from common.shared.axlock import _canon,_safe
        import fcntl
        self.consumed()
        with self.held():
            evidence=parent_evidence(self.registry,self.store.locks,self.ctx.to_dict())
            metadata=self.store.locks.paths.lock_dir/(_safe(_canon('profile:tistory'))+'.json')
            saved=metadata.read_bytes()
        metadata.write_bytes(saved)
        lockpath=metadata.with_suffix('.lock')
        with lockpath.open('r+b') as probe:
            fcntl.flock(probe.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            fcntl.flock(probe.fileno(),fcntl.LOCK_UN)
            with self.assertRaises(Exception):parent_evidence(self.registry,self.store.locks,self.ctx.to_dict())
            evidence['lock_fd']=probe.fileno()
            with self.assertRaises(Exception):check_parent_evidence(self.registry,self.store.locks,self.ctx.to_dict(),evidence,parent_pid=os.getpid())
            # 부모 검사를 고의로 우회해도 실제 자식이 free FD를 독립 거절한다.
            with self.assertRaisesRegex(Exception,'bridge_child_failed'):
                self.bridge()._call(self.spec,'inspect_target',dict(context=self.ctx.to_dict(),payload={},parent=evidence),None)

    def child_credentials_barrier(self):
        source=self.fixture_source().replace('    return BridgeHost(','    host=BridgeHost(')
        replacement="""    def credentials(ctx,scope):
        (ROOT/'credentials-ready').write_text('ready')
        import time
        deadline=time.monotonic()+5
        while not (ROOT/'credentials-release').exists():
            if time.monotonic()>deadline:raise RuntimeError('fixture barrier timeout')
            time.sleep(.01)
        return None
    host._credentials=credentials
    return host
if __name__=='__main__':"""
        self.module.write_text(source.replace("if __name__=='__main__':",replacement))

    def wait_marker(self,name):
        import time
        deadline=time.monotonic()+5
        while not (self.root/name).exists():
            if time.monotonic()>deadline:self.fail('child marker timeout: '+name)
            time.sleep(.01)

    def submit_in_thread(self,permit):
        import threading
        results=[]
        def run():
            try:results.append(self.bridge().submit('fixture',self.ctx,{},permit))
            except Exception as exc:results.append(exc)
        thread=threading.Thread(target=run);thread.start()
        return thread,results

    def test_approval_revoke_during_credentials_blocks_actual_child_leaf(self):
        permit=self.consumed();self.child_credentials_barrier()
        with self.held():
            thread,results=self.submit_in_thread(permit)
            try:
                self.wait_marker('credentials-ready')
                delivery=self.store.get_delivery('d')
                self.store.record_publication_approval('d',delivery['version'],self.ctx.context_hash,
                    'revoked',self.ctx.review_report_hashes,decision='revoked')
            finally:(self.root/'credentials-release').write_text('release')
            thread.join(5);self.assertFalse(thread.is_alive())
        self.assertFalse(self.marker.exists())
        self.assertIsInstance(results[0],Exception)

    def test_stop_writer_returns_while_actual_child_handler_io_is_blocked(self):
        import threading,time
        permit=self.consumed()
        self.module.write_text(self.fixture_source(leaf="(ROOT/'handler-ready').write_text('ready'); __import__('time').sleep(2)"))
        with self.held():
            child,results=self.submit_in_thread(permit)
            self.wait_marker('handler-ready')
            done=threading.Event()
            def stop():self.store.locks.set_stop('after-authorization');done.set()
            writer=threading.Thread(target=stop);writer.start()
            responsive=done.wait(.5)
            child.join(5);writer.join(5)
        self.assertTrue(responsive,'STOP must not wait for handler I/O')
        self.assertTrue(self.store.get_attempt(permit.attempt_id)['request_started'])
        self.assertFalse(self.store.get_attempt(permit.attempt_id)['resolved'])
        self.assertEqual(results[0]['outcome'],'submitted')

    def test_approval_writer_uses_final_gate_and_nested_same_thread_does_not_deadlock(self):
        import threading
        self.consumed();entered=threading.Event();done=threading.Event();errors=[]
        def revoke():
            entered.set()
            try:
                delivery=self.store.get_delivery('d')
                self.store.record_publication_approval('d',delivery['version'],self.ctx.context_hash,
                    'revoked',self.ctx.review_report_hashes,decision='revoked')
            except Exception as exc:errors.append(exc)
            finally:done.set()
        with self.store.locks.hold(['control:publish-gate'],job='nested-final-permission',wait=.1):
            delivery=self.store.get_delivery('d')
            self.store.record_publication_approval('d',delivery['version'],self.ctx.context_hash,
                'approved-again',self.ctx.review_report_hashes)
            thread=threading.Thread(target=revoke);thread.start()
            self.assertTrue(entered.wait(1));self.assertFalse(done.wait(.1))
            self.assertEqual(self.store.get_publication_approval('d')['decision'],'approved')
        thread.join(3)
        self.assertTrue(done.is_set());self.assertEqual(errors,[])
        self.assertEqual(self.store.get_publication_approval('d')['decision'],'revoked')

    def test_managed_approval_writer_missing_locks_fails_closed(self):
        from common.operations.runtime_models import ExecutionPolicy
        saved_locks=self.store.locks;del self.store.locks
        path=self.store.root/'operations.sqlite3';before=path.read_bytes()
        for registry,policy in ((self.registry,None),(None,self.policy)):
            with self.subTest(registry=registry is not None):
                self.store.registry=registry;self.store.execution_policy=policy
                with self.assertRaisesRegex(Exception,'publication_lock_required'):
                    self.store.record_publication_approval('d',self.store.get_delivery('d')['version'],
                        self.ctx.context_hash,'revoked',self.ctx.review_report_hashes,decision='revoked')
        self.assertEqual(path.read_bytes(),before)
        self.store.locks=saved_locks

    def test_module_lookup_uses_trusted_root_with_distinct_legacy_cwd(self):
        permit=self.consumed()
        legacy=self.root/'legacy-project';legacy.mkdir()
        self.spec=replace(self.spec,cwd=legacy);self.catalog=ExecutionCatalog({'fixture':self.spec})
        source=self.fixture_source().replace("sys.executable,ROOT,'fixture_bridge'",
            "sys.executable,Path("+repr(str(legacy))+"),'fixture_bridge'")
        self.module.write_text(source)
        (legacy/'common.py').write_text("from pathlib import Path; Path("+repr(str(self.root/'shadow-loaded'))+").write_text('bad'); raise RuntimeError('cwd shadow')")
        result=None
        with self.held():
            try:result=self.bridge().submit('fixture',self.ctx,{},permit)
            except Exception:pass
        self.assertIsNotNone(result,'registered module must resolve from server code root, independently of cwd')
        self.assertFalse((self.root/'shadow-loaded').exists())
        self.assertEqual(self.marker.read_text(),'1')

    def test_real_child_cwd_common_shadow_is_never_imported(self):
        permit=self.consumed()
        legacy=self.root/'legacy-project';legacy.mkdir()
        self.spec=replace(self.spec,cwd=legacy);self.catalog=ExecutionCatalog({'fixture':self.spec})
        source=self.fixture_source().replace("sys.executable,ROOT,'fixture_bridge'",
            "sys.executable,Path("+repr(str(legacy))+"),'fixture_bridge'")
        self.module.write_text(source)
        # 이전 cwd 기반 lookup도 통과시켜 실제 Python import shadow를 재현한다.
        (legacy/'fixture_bridge.py').write_text(source)
        (legacy/'common.py').write_text("from pathlib import Path; Path("+repr(str(self.root/'shadow-loaded'))+").write_text('bad'); raise RuntimeError('cwd shadow')")
        result=None
        from unittest.mock import patch
        with self.held(),patch.dict(os.environ,{'PYTHONPATH':str(legacy),'PYTHONHOME':str(legacy)}):
            try:result=self.bridge().submit('fixture',self.ctx,{},permit)
            except Exception:pass
        self.assertFalse((self.root/'shadow-loaded').exists(),'legacy cwd common.py must never execute')
        self.assertIsNotNone(result)
        self.assertEqual(self.marker.read_text(),'1')

    def test_default_managed_module_is_found_in_code_root_not_legacy_cwd(self):
        from common.publishers.legacy_bridge import _registered_spec
        legacy=self.root/'legacy-project';legacy.mkdir()
        spec=replace(self.spec,cwd=legacy,module='common.publishers.bridge_host')
        self.assertEqual(_registered_spec(ExecutionCatalog({'fixture':spec}),'fixture'),spec)

    def test_fixed_interpreter_without_isolation_support_is_unavailable_no_fallback(self):
        interpreter=self.root/'unsupported-python'
        interpreter.write_text('#!'+sys.executable+' -I\nfrom pathlib import Path\nPath('+repr(str(self.root/'capability-checked'))+").write_text('1')\nraise SystemExit(78)\n")
        interpreter.chmod(0o700)
        self.spec=replace(self.spec,interpreter=str(interpreter));self.catalog=ExecutionCatalog({'fixture':self.spec})
        permit=self.consumed();spawn=Mock()
        with self.held():
            with self.assertRaisesRegex(Exception,'bridge_unavailable'):self.bridge(spawn).submit('fixture',self.ctx,{},permit)
        self.assertEqual((self.root/'capability-checked').read_text(),'1')
        spawn.assert_not_called();self.assertFalse(self.marker.exists())

    def test_default_host_is_unavailable(self):
        from common.publishers.bridge_host import main
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO
        error,output=StringIO(),StringIO()
        with redirect_stderr(error),redirect_stdout(output):
            self.assertEqual(main([]),2)
        self.assertEqual(error.getvalue(),'bridge_child_failed\n')
        self.assertEqual(output.getvalue(),'')
