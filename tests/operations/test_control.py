import json
import io
from contextlib import closing, redirect_stdout
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from common.shared import axlock


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def paths(self, name='source'):
        return axlock.LockPaths.from_root(self.root / name)

    def test_construct_and_observe_do_not_create_or_clean_files(self):
        from common.operations.control import read_control_state
        paths = self.paths()
        lock = axlock.AxLock(paths)
        self.assertEqual(read_control_state(paths)['state'], 'clear')
        self.assertFalse(paths.root.exists())
        paths.lock_dir.mkdir(parents=True)
        stale = paths.lock_dir / 'waiting' / 'dead.json'
        stale.parent.mkdir()
        stale.write_text('{"pid": -1}')
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths.root.rglob('*') if p.is_file()}
        lock.status()
        read_control_state(paths, process_probe=lambda pid: False)
        self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths.root.rglob('*') if p.is_file()})

    def test_source_roots_and_alias_locks(self):
        one = axlock.AxLock(self.paths(), process_probe=lambda res: False)
        two = axlock.AxLock(self.paths('worktree'), process_probe=lambda res: False)
        with one.hold(['profile:naver'], job='one', wait=0):
            with self.assertRaises(axlock.Timeout):
                with one.hold(['profile:tiktok'], job='two', wait=0):
                    self.fail('same account escaped lock')
            with two.hold(['profile:tiktok'], job='separate-root', wait=0):
                pass
            with one.hold(['profile:tistory'], job='personal', wait=0):
                pass

    def test_stop_corrupt_and_permission_are_unknown(self):
        from common.operations.control import read_control_state
        paths = self.paths()
        paths.stop.parent.mkdir(parents=True)
        paths.stop.write_text('{')
        self.assertEqual(read_control_state(paths)['state'], 'unknown')
        with patch.object(Path, 'read_bytes', side_effect=PermissionError):
            self.assertEqual(read_control_state(paths)['state'], 'unknown')

    def test_stop_atomic_cas_and_gate_order(self):
        lock = axlock.AxLock(self.paths())
        first = lock.set_stop('one')
        self.assertEqual(first['state'], 'stopped')
        second = lock.set_stop('two')
        with self.assertRaises(axlock.ControlBlocked):
            lock.clear_stop(first['version'])
        self.assertEqual(lock.status()['stop']['reason'], 'two')
        lock.clear_stop(second['version'])
        self.assertEqual(lock.status()['control']['state'], 'clear')
        ready = threading.Event()
        done = threading.Event()
        with lock.hold(['control:publish-gate'], job='consume', wait=0):
            t = threading.Thread(target=lambda: (ready.set(), lock.set_stop('ordered'), done.set()))
            t.start()
            ready.wait(1)
            self.assertFalse(done.wait(.05))
        t.join(3)
        self.assertTrue(done.is_set())
        self.assertEqual(json.loads(lock.paths.stop.read_text())['reason'], 'ordered')

    def test_stop_during_profile_wait_blocks_and_env_does_not_bypass(self):
        lock = axlock.AxLock(self.paths(), process_probe=lambda res: False)
        original = lock._try
        def try_and_stop(res, holder):
            if res == 'control:publish-gate':
                return original(res, holder)
            lock.set_stop('during wait')
            return None
        with patch.object(lock, '_try', side_effect=try_and_stop), patch.dict('os.environ', {'AX_LOCKED': '1'}):
            with self.assertRaises(axlock.ControlBlocked):
                with lock.hold(['profile:naver'], job='test', wait=.01):
                    self.fail('STOP escaped')
        lock._try = original

    def test_legacy_module_and_cli_compatibility(self):
        paths = self.paths()
        with patch.multiple(axlock, ROOT=paths.root, DIR=paths.lock_dir, STOP=paths.stop,
                            LOG=paths.log, SKIP=paths.skip, CATALOG=paths.catalog):
            axlock.set_stop('legacy')
            self.assertEqual(axlock.stopped()['reason'], 'legacy')
            self.assertEqual(axlock.main(['resume']), 0)
            self.assertIsNone(axlock.stopped())
            with redirect_stdout(io.StringIO()):
                self.assertEqual(axlock.main(['status']), 0)

    def test_repeated_identical_stop_still_has_new_cas_version(self):
        lock = axlock.AxLock(self.paths())
        with patch.object(axlock, '_now', return_value='2026-10-30T00:00:00'):
            first = lock.set_stop('same')
            second = lock.set_stop('same')
        self.assertNotEqual(first['version'], second['version'])
        with self.assertRaises(axlock.ControlBlocked):
            lock.clear_stop(first['version'])

    def test_shared_source_root_across_independent_callers(self):
        source = self.paths()
        worker = axlock.AxLock(source, process_probe=lambda res: False)
        console = axlock.AxLock(axlock.LockPaths.from_root(source.root / '..' / 'source'), process_probe=lambda res: False)
        with worker.hold(['profile:youtube-personal'], job='worker', wait=0):
            with self.assertRaises(axlock.Timeout):
                with console.hold(['profile:tistory'], job='console', wait=0):
                    self.fail('shared source did not serialize')

    def test_external_browser_is_waited_for_without_closing_it(self):
        lock = axlock.AxLock(self.paths(), process_probe=lambda res: res.startswith('profile:'))
        with self.assertRaises(axlock.Timeout):
            with lock.hold(['profile:naver'], job='external', wait=0):
                self.fail('external browser ignored')

    def test_lock_is_released_when_metadata_write_fails(self):
        lock = axlock.AxLock(self.paths(), process_probe=lambda res: False)
        original = Path.write_text
        def write(path, *args, **kwargs):
            if path.name.startswith('second'):
                raise OSError('fixture failure')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'write_text', write):
            with self.assertRaises(OSError):
                with lock.hold(['first', 'second'], job='broken', wait=0):
                    pass
        with lock.hold(['first', 'second'], job='later', wait=0):
            pass

    def test_managed_pause_resume_cas_has_no_enqueue_and_does_not_change_stop(self):
        import sqlite3
        from common.operations.control import set_managed_pause
        from common.operations.runtime_store import RuntimeStore
        from common.operations.content_store import ConflictError
        managed = self.root / 'managed'
        store = RuntimeStore(managed)
        store.initialize()
        lock = axlock.AxLock(self.paths())
        lock.set_stop('legacy stop')
        before = lock.paths.stop.read_bytes()
        paused = set_managed_pause(store, 'account', 'personal', True, 0, 'console_user', 'test pause', 'p1')
        self.assertEqual(paused['action'], 'pause')
        self.assertEqual(set_managed_pause(store, 'account', 'personal', True, 0, 'console_user', 'test pause', 'p1'), paused)
        with self.assertRaises(ConflictError):
            set_managed_pause(store, 'account', 'personal', False, 0, 'console_user', 'stale', 'p2')
        resumed = set_managed_pause(store, 'account', 'personal', False, paused['version'], 'console_user', 'resume', 'p3')
        self.assertEqual(resumed['action'], 'resume')
        self.assertEqual(lock.paths.stop.read_bytes(), before)
        with closing(sqlite3.connect(managed / 'operations.sqlite3')) as conn:
            for table in ('runs', 'deliveries', 'runtime_runs', 'runtime_deliveries', 'attempts'):
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0)

    def test_cli_run_executes_under_lock_and_stopped_run_is_not_executed(self):
        import sys
        paths = self.paths()
        marker = self.root / 'child.json'
        cmd = [sys.executable, '-c',
               'import os,pathlib; pathlib.Path(os.environ["TEST_MARKER"]).write_text(os.environ["AX_LOCKED"])']
        with patch.multiple(axlock, ROOT=paths.root, DIR=paths.lock_dir, STOP=paths.stop,
                            LOG=paths.log, SKIP=paths.skip, CATALOG=paths.catalog), patch.dict('os.environ', {'TEST_MARKER': str(marker), 'AX_LOCKED': '1'}):
            self.assertEqual(axlock.main(['run', '--job', 'fixture', '--wait', '0', '--', *cmd]), 0)
            self.assertEqual(marker.read_text(), '1')
            marker.unlink()
            axlock.set_stop('fixture')
            with redirect_stdout(io.StringIO()):
                self.assertEqual(axlock.main(['run', '--job', 'fixture', '--wait', '0', '--', *cmd]), 0)
            self.assertFalse(marker.exists())

    def test_gate_released_when_only_acquisition_complete_log_fails(self):
        paths = self.paths()
        blocker = axlock.AxLock(paths, process_probe=lambda res: False)
        waiter = axlock.AxLock(paths, process_probe=lambda res: False)
        held = blocker.acquire(['control:publish-gate'], job='blocker', wait=0)
        self.addCleanup(lambda: blocker._release(held))
        original_log = waiter.log
        messages = []

        def fail_only_complete_log(message):
            messages.append(message)
            if len(messages) == 1:
                original_log(message)
                blocker._release(held)
                held.clear()
            else:
                raise OSError('fixture log disk full')

        with patch.object(waiter, 'log', side_effect=fail_only_complete_log):
            with self.assertRaisesRegex(OSError, 'fixture log disk full'):
                with waiter.hold(['control:publish-gate'], job='waiter', wait=1):
                    self.fail('failed log must precede fd handoff')
        self.assertEqual(len(messages), 2)
        self.assertIn('기다림', messages[0])
        self.assertIn('기다린 끝에 잡음', messages[1])
        with blocker.hold(['control:publish-gate'], job='after-log-failure', wait=0):
            pass
