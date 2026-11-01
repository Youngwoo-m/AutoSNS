import json
import multiprocessing
import os
from pathlib import Path
import stat
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import warnings

from common.operations import oauth_workspace as workspace


def _process_guard(root, connection, release, timeout=2):
    context = workspace.load_workspace_owner(root)
    try:
        with workspace.oauth_write_guard(context, timeout=timeout):
            connection.send('held')
            if not release.wait(5):
                raise RuntimeError('test_release_timeout')
        connection.send('released')
    except workspace.WorkspaceError as error:
        connection.send(error.code)
    finally:
        connection.close()


def _fork_guard(context, connection):
    results = []
    for action in (lambda: workspace.require_oauth_write_guard(context.root, context.owner),
                   lambda: workspace.oauth_write_guard(context).__enter__()):
        try:
            action()
            results.append('unexpected_success')
        except workspace.WorkspaceError as error:
            results.append(error.code)
    fresh = workspace.load_workspace_owner(context.root)
    try:
        with workspace.oauth_write_guard(fresh, timeout=0):
            results.append('fresh_held')
    except workspace.WorkspaceError as error:
        results.append(error.code)
    connection.send(results)
    connection.close()


class OAuthWriteGuardTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(callable(getattr(workspace, 'oauth_write_guard', None)),
                        'explicit OAuth write guard is not implemented')
        self.assertTrue(callable(getattr(workspace, 'require_oauth_write_guard', None)),
                        'held OAuth write guard check is not implemented')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'oauth'
        self.context = workspace.initialize_workspace_owner(self.root)
        self.lock = self.root / '.oauth-workspace.lock'

    def assertCode(self, code, action):
        with self.assertRaises(workspace.WorkspaceError) as caught:
            action()
        self.assertEqual(caught.exception.code, code)

    def run_thread(self, action):
        result = []
        def target():
            try:
                result.append(action())
            except BaseException as error:
                result.append(error)
        thread = threading.Thread(target=target)
        thread.start()
        thread.join(5)
        self.assertFalse(thread.is_alive(), 'guard thread did not finish')
        self.assertEqual(len(result), 1)
        if isinstance(result[0], BaseException):
            raise result[0]
        return result[0]

    def child(self, target=_process_guard, args=(), method='spawn'):
        process_context = multiprocessing.get_context(method)
        parent, child = process_context.Pipe()
        release = process_context.Event()
        if target is _process_guard:
            args = (str(self.root), child, release) + args
        else:
            args = args + (child,)
        process = process_context.Process(target=target, args=args)
        process.start()
        child.close()
        def cleanup():
            # A killed process may have been inside Event.wait's condition;
            # never signal that condition once its waiter has died.
            if process.is_alive():
                release.set()
            process.join(5)
            if process.is_alive():
                process.terminate()
                process.join(5)
            parent.close()
        self.addCleanup(cleanup)
        return process, parent, release

    def receive(self, connection):
        self.assertTrue(connection.poll(5), 'guard child did not report')
        return connection.recv()

    def test_load_and_context_construction_never_create_lock(self):
        workspace.load_workspace_owner(self.root)
        workspace.OAuthWorkspaceContext(self.context.root, self.context.owner,
                                        self.context.key_provider)
        self.assertFalse(self.lock.exists())
        self.assertCode('oauth_guard_required', lambda: workspace.require_oauth_write_guard(
            self.root, self.context.owner))
        self.assertFalse(self.lock.exists())

    def test_explicit_guard_creates_private_lock_and_releases_on_exception(self):
        with self.assertRaisesRegex(RuntimeError, 'body_failed'):
            with workspace.oauth_write_guard(self.context, timeout=0) as held:
                self.assertIs(held, self.context)
                self.assertIs(workspace.require_oauth_write_guard(self.root, self.context.owner),
                              self.context)
                self.assertTrue(stat.S_ISREG(self.lock.stat().st_mode))
                self.assertEqual(stat.S_IMODE(self.lock.stat().st_mode), 0o600)
                raise RuntimeError('body_failed')
        self.assertCode('oauth_guard_required', lambda: workspace.require_oauth_write_guard(
            self.root, self.context.owner))
        with workspace.oauth_write_guard(workspace.load_workspace_owner(self.root), timeout=0):
            pass

    def test_reentrant_guard_keeps_outer_flock_and_rejects_other_context(self):
        other_root = Path(self.temp.name) / 'other'
        other = workspace.initialize_workspace_owner(other_root)
        with workspace.oauth_write_guard(self.context):
            with workspace.oauth_write_guard(self.context, timeout=0):
                self.assertIs(workspace.require_oauth_write_guard(self.root, self.context.owner),
                              self.context)
            with workspace.oauth_write_guard(workspace.load_workspace_owner(self.root), timeout=0):
                self.assertIs(workspace.require_oauth_write_guard(self.root, self.context.owner),
                              self.context)
            self.assertCode('oauth_workspace_invalid_context', lambda:
                            workspace.oauth_write_guard(other, timeout=0).__enter__())
            process, connection, _ = self.child(args=(0,))
            self.assertEqual(self.receive(connection), 'oauth_workspace_busy')
            process.join(5)
            self.assertEqual(process.exitcode, 0)
        self.assertFalse((other_root / '.oauth-workspace.lock').exists())

    def test_thread_cannot_claim_guard_and_separate_loaded_context_contends(self):
        loaded = workspace.load_workspace_owner(self.root)
        def contender():
            self.assertCode('oauth_guard_required', lambda: workspace.require_oauth_write_guard(
                self.root, self.context.owner))
            self.assertCode('oauth_workspace_busy', lambda:
                            workspace.oauth_write_guard(loaded, timeout=0).__enter__())
        with workspace.oauth_write_guard(self.context):
            self.run_thread(contender)
        self.assertTrue(self.run_thread(lambda: self._enter(loaded)))

    def test_copied_thread_state_and_absent_held_token_cannot_authorize_writes(self):
        with workspace.oauth_write_guard(self.context):
            held = workspace._guard_local.held
            def copy_to_other_thread():
                workspace._guard_local.held = held
                self.assertCode('oauth_guard_required', lambda:
                                workspace.require_oauth_write_guard(self.root, self.context.owner))
            self.run_thread(copy_to_other_thread)
            original_pid = held.pid
            held.pid = original_pid + 1
            try:
                self.assertCode('oauth_guard_required', lambda:
                                workspace.require_oauth_write_guard(self.root, self.context.owner))
            finally:
                held.pid = original_pid
            registered = workspace._guard_tokens.pop(held.token)
            try:
                self.assertCode('oauth_guard_required', lambda:
                                workspace.require_oauth_write_guard(self.root, self.context.owner))
            finally:
                workspace._guard_tokens[held.token] = registered

    def _enter(self, context):
        with workspace.oauth_write_guard(context, timeout=0):
            return workspace.require_oauth_write_guard(context.root, context.owner) is context

    def test_thread_waiter_enters_after_event_release(self):
        held = threading.Event()
        release = threading.Event()
        errors = []
        def holder():
            try:
                with workspace.oauth_write_guard(workspace.load_workspace_owner(self.root)):
                    held.set()
                    if not release.wait(5):
                        raise RuntimeError('test_release_timeout')
            except BaseException as error:
                errors.append(error)
        thread = threading.Thread(target=holder)
        thread.start()
        self.assertTrue(held.wait(5))
        release.set()
        with workspace.oauth_write_guard(self.context, timeout=2):
            self.assertIs(workspace.require_oauth_write_guard(self.root, self.context.owner),
                          self.context)
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])

    def test_distinct_root_can_be_held_in_other_thread(self):
        other = workspace.initialize_workspace_owner(Path(self.temp.name) / 'other')
        with workspace.oauth_write_guard(self.context):
            self.assertTrue(self.run_thread(lambda: self._enter(other)))
            self.assertCode('oauth_guard_required', lambda: workspace.require_oauth_write_guard(
                other.root, other.owner))

    def test_other_process_holds_until_event_release(self):
        process, connection, release = self.child()
        self.assertEqual(self.receive(connection), 'held')
        self.assertCode('oauth_workspace_busy', lambda:
                        workspace.oauth_write_guard(self.context, timeout=0).__enter__())
        release.set()
        self.assertEqual(self.receive(connection), 'released')
        process.join(5)
        self.assertEqual(process.exitcode, 0)
        with workspace.oauth_write_guard(self.context, timeout=0):
            pass

    def test_terminated_holder_releases_os_lock_without_touching_marker(self):
        before = (self.root / workspace.OWNER_MARKER_NAME).read_bytes()
        process, connection, _ = self.child()
        self.assertEqual(self.receive(connection), 'held')
        process.terminate()
        process.join(5)
        self.assertIsNotNone(process.exitcode)
        with workspace.oauth_write_guard(self.context, timeout=0):
            pass
        self.assertEqual((self.root / workspace.OWNER_MARKER_NAME).read_bytes(), before)

    def test_timeout_rejects_invalid_values_without_creating_lock(self):
        for value in (-1, float('nan'), float('inf'), float('-inf'), True, None, '1'):
            with self.subTest(value=value):
                self.assertCode('oauth_workspace_invalid_timeout', lambda:
                                workspace.oauth_write_guard(self.context, timeout=value).__enter__())
        self.assertFalse(self.lock.exists())

    def test_flock_timeout_has_one_monotonic_deadline(self):
        process, connection, _ = self.child()
        self.assertEqual(self.receive(connection), 'held')
        started = time.monotonic()
        self.assertCode('oauth_workspace_busy', lambda:
                        workspace.oauth_write_guard(self.context, timeout=0.1).__enter__())
        self.assertLess(time.monotonic() - started, 1)

    def test_thread_wait_and_flock_retry_share_remaining_budget(self):
        process, connection, _ = self.child()
        self.assertEqual(self.receive(connection), 'held')
        waits = []
        class ClockWait:
            def wait(self, timeout):
                waits.append(timeout)
        # 0.06 of the original 0.10 budget has elapsed before flock is
        # attempted. Its retry may consume only the remaining 0.04.
        with patch.object(workspace.time, 'monotonic', side_effect=(100, 100.06, 100.06, 100.10)), \
                patch.object(workspace.threading, 'Event', ClockWait):
            self.assertCode('oauth_workspace_busy', lambda:
                            workspace.oauth_write_guard(self.context, timeout=0.1).__enter__())
        self.assertEqual(len(waits), 1)
        self.assertAlmostEqual(waits[0], 0.04)

    def test_root_owner_key_mismatch_and_uninitialized_context_create_no_lock(self):
        other = workspace.initialize_workspace_owner(Path(self.temp.name) / 'other')
        invalid = workspace.OAuthWorkspaceContext(other.root, self.context.owner,
                                                  self.context.key_provider)
        self.assertCode('oauth_workspace_owner_mismatch', lambda:
                        workspace.oauth_write_guard(invalid).__enter__())
        uninitialized = Path(self.temp.name) / 'uninitialized'
        uninitialized.mkdir(mode=0o700)
        invalid = workspace.OAuthWorkspaceContext(uninitialized, self.context.owner,
                                                  self.context.key_provider)
        self.assertCode('oauth_workspace_owner_missing', lambda:
                        workspace.oauth_write_guard(invalid).__enter__())
        self.assertEqual(list(uninitialized.iterdir()), [])
        self.assertFalse((other.root / '.oauth-workspace.lock').exists())
        self.assertFalse(self.lock.exists())

    def test_missing_truncated_or_changed_marker_is_rejected_before_lock_creation(self):
        marker = self.root / workspace.OWNER_MARKER_NAME
        before = marker.read_bytes()
        changed = json.loads(before)
        changed['key'] = 'ab' * 32
        for content in (None, b'{', json.dumps(changed).encode()):
            with self.subTest(content=content):
                if content is None:
                    marker.unlink()
                else:
                    marker.write_bytes(content)
                with self.assertRaises(workspace.WorkspaceError):
                    with workspace.oauth_write_guard(self.context):
                        self.fail('invalid marker accepted')
                self.assertFalse(self.lock.exists())
                marker.write_bytes(before)
                marker.chmod(0o600)

    def test_guard_rechecks_marker_for_each_required_write(self):
        marker = self.root / workspace.OWNER_MARKER_NAME
        with workspace.oauth_write_guard(self.context):
            marker.write_bytes(b'{')
            self.assertCode('oauth_workspace_invalid_marker', lambda:
                            workspace.require_oauth_write_guard(self.root, self.context.owner))

    def test_lock_symlink_fifo_directory_and_bad_permissions_are_preserved(self):
        target = self.root / 'target'
        target.write_bytes(b'keep')
        self.lock.symlink_to(target)
        with self.assertRaises(workspace.WorkspaceError):
            with workspace.oauth_write_guard(self.context):
                self.fail('symlink lock accepted')
        self.assertTrue(self.lock.is_symlink())
        self.assertEqual(target.read_bytes(), b'keep')
        self.lock.unlink()
        os.mkfifo(self.lock, 0o600)
        with self.assertRaises(workspace.WorkspaceError):
            with workspace.oauth_write_guard(self.context):
                self.fail('fifo lock accepted')
        self.assertTrue(stat.S_ISFIFO(self.lock.stat().st_mode))
        self.lock.unlink()
        self.lock.mkdir(mode=0o700)
        with self.assertRaises(workspace.WorkspaceError):
            with workspace.oauth_write_guard(self.context):
                self.fail('directory lock accepted')
        self.lock.rmdir()
        self.lock.write_bytes(b'keep')
        self.lock.chmod(0o644)
        self.assertCode('oauth_workspace_invalid_permissions', lambda:
                        workspace.oauth_write_guard(self.context).__enter__())
        self.assertEqual(self.lock.read_bytes(), b'keep')
        self.assertEqual(stat.S_IMODE(self.lock.stat().st_mode), 0o644)

    @unittest.skipUnless(hasattr(os, 'fork'), 'fork unavailable')
    def test_fork_rejects_inherited_context_and_held_state_but_reload_can_contend(self):
        with workspace.oauth_write_guard(self.context):
            process, connection, _ = self.child(target=_fork_guard,
                                               args=(self.context,), method='fork')
            self.assertEqual(self.receive(connection), ['oauth_guard_required',
                             'oauth_workspace_invalid_context', 'oauth_workspace_busy'])
            process.join(5)
            self.assertEqual(process.exitcode, 0)
        process, connection, _ = self.child(target=_fork_guard,
                                           args=(self.context,), method='fork')
        self.assertEqual(self.receive(connection), ['oauth_guard_required',
                         'oauth_workspace_invalid_context', 'fresh_held'])
        process.join(5)
        self.assertEqual(process.exitcode, 0)

    def _fork_during_fd_interval(self, phase):
        interval_reached = threading.Event()
        finish_interval = threading.Event()
        fork_progress = threading.Event()
        holder_identity = []
        fork_identity = []
        fd_value = []
        child_pids = []
        results = []
        process_context = multiprocessing.get_context('fork')
        parent_connection, child_connection = process_context.Pipe()
        original_open = workspace._open_guard_file
        original_close = os.close
        real_fd_lock = getattr(workspace, '_guard_fd_lock', threading.Lock())

        class ObservedForkLock:
            # Observe the fork hook reaching the real lock, without weakening
            # mutual exclusion. Before the fix, fork instead completes first.
            def acquire(self, *args, **kwargs):
                if fork_identity and threading.get_ident() == fork_identity[0]:
                    fork_progress.set()
                return real_fd_lock.acquire(*args, **kwargs)
            def release(self):
                return real_fd_lock.release()
            def __enter__(self):
                self.acquire()
                return self
            def __exit__(self, *args):
                self.release()

        def pause_interval():
            interval_reached.set()
            if not finish_interval.wait(5):
                raise RuntimeError('test_fd_interval_timeout')

        def open_guard(root_fd):
            fd = original_open(root_fd)
            fd_value.append(fd)
            if phase == 'open':
                pause_interval()
            return fd

        def close_guard(fd):
            if (phase == 'close' and fd_value and fd == fd_value[0]
                    and holder_identity and threading.get_ident() == holder_identity[0]):
                pause_interval()
            return original_close(fd)

        def holder():
            holder_identity.append(threading.get_ident())
            try:
                with workspace.oauth_write_guard(self.context):
                    results.append('held')
                results.append('released')
            except BaseException as error:
                results.append(error)

        def fork_child():
            fork_identity.append(threading.get_ident())
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', message='This process .*multi-threaded.*',
                                        category=DeprecationWarning)
                pid = os.fork()
            if pid == 0:
                try:
                    parent_connection.close()
                    child_connection.send('alive')
                    child_connection.recv()
                    child_connection.close()
                    os._exit(0)
                except BaseException:
                    os._exit(1)
            child_pids.append(pid)
            child_connection.close()
            fork_progress.set()

        holder_thread = threading.Thread(target=holder)
        fork_thread = threading.Thread(target=fork_child)
        try:
            with patch.object(workspace, '_guard_fd_lock', ObservedForkLock(), create=True), \
                    patch.object(workspace, '_open_guard_file', open_guard), \
                    patch.object(workspace.os, 'close', close_guard):
                holder_thread.start()
                self.assertTrue(interval_reached.wait(5), 'fd interval not reached')
                fork_thread.start()
                self.assertTrue(fork_progress.wait(5), 'fork hook did not reach fd boundary')
                finish_interval.set()
                holder_thread.join(5)
                fork_thread.join(5)
                self.assertFalse(holder_thread.is_alive())
                self.assertFalse(fork_thread.is_alive())
                self.assertEqual(results, ['held', 'released'])
                self.assertEqual(self.receive(parent_connection), 'alive')
                # The child is deliberately still alive. Its inherited fd
                # must not retain the parent's completed flock.
                try:
                    acquired = self._enter(self.context)
                except workspace.WorkspaceError as error:
                    acquired = error.code
                self.assertIs(acquired, True, 'live child retained a completed parent flock')
        finally:
            finish_interval.set()
            holder_thread.join(5)
            if fork_thread.ident is not None:
                fork_thread.join(5)
            if child_pids:
                parent_connection.send('exit')
                _, status = os.waitpid(child_pids[0], 0)
                self.assertEqual(os.waitstatus_to_exitcode(status), 0)
            parent_connection.close()
            child_connection.close()

    @unittest.skipUnless(hasattr(os, 'fork'), 'fork unavailable')
    def test_fork_during_fd_open_registration_does_not_retain_completed_flock(self):
        self._fork_during_fd_interval('open')

    @unittest.skipUnless(hasattr(os, 'fork'), 'fork unavailable')
    def test_fork_during_fd_unregister_close_does_not_retain_completed_flock(self):
        self._fork_during_fd_interval('close')


if __name__ == '__main__':
    unittest.main()
