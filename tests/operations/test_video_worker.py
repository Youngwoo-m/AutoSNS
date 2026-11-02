"""영상 worker 호출 순서·정지 시험. 가짜 service와 Event만 쓰며 렌더·DB·네트워크가 없다."""
import threading
import unittest

from common.operations.models import ContractError
from common.operations.video_worker import VideoTaskWorker

WAIT = 5


class FakeService:
    """results를 차례로 돌려주는 service. Exception 인스턴스는 던진다. 소진되면 None(idle)."""
    def __init__(self, results=(), enabled=True, on_call=None):
        self.enabled, self.results, self.on_call = enabled, list(results), on_call
        self.calls = []

    def run_next(self):
        self.calls.append('run_next')
        if self.on_call is not None:
            self.on_call(len(self.calls))
        if not self.results:
            return None
        item = self.results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class WaitSetsEvent(threading.Event):
    """idle 대기를 즉시 끝내며 poll 값을 기록하고 정지로 바꾸는 Event."""
    def __init__(self):
        super().__init__()
        self.waits = []

    def wait(self, timeout=None):
        self.waits.append(timeout)
        self.set()
        return True


def task(state='completed'):
    return {'task_id': 'task', 'state': state, 'review_status': 'not_checked'}


class VideoTaskWorkerTests(unittest.TestCase):
    def test_policy_disabled_after_one_task_stops_before_next_claim(self):
        service=FakeService([task(),task()])
        service.on_call=lambda _:setattr(service,'enabled',False)
        worker=VideoTaskWorker(service)
        self.assertEqual(worker.run(),1)
        self.assertEqual(service.calls,['run_next'])

    def test_constructor_validates_without_io_or_thread(self):
        service = FakeService([task()])
        before = threading.active_count()
        worker = VideoTaskWorker(service)
        self.assertEqual((service.calls, threading.active_count()), ([], before))
        self.assertIsInstance(worker.stop_event, threading.Event)
        self.assertFalse(worker.stop_event.is_set())
        self.assertIs(worker.service, service)
        event = threading.Event()
        self.assertIs(VideoTaskWorker(service, stop_event=event).stop_event, event)
        for bad in (object(), None, type('NoEnabled', (), {'run_next': lambda self: None})(),
                    type('NoRun', (), {'enabled': True})()):
            with self.assertRaises(ContractError) as caught:
                VideoTaskWorker(bad)
            self.assertEqual(caught.exception.code, 'invalid_video_service')
        with self.assertRaises(ContractError) as caught:
            VideoTaskWorker(service, stop_event=object())
        self.assertEqual(caught.exception.code, 'invalid_stop_event')
        for value in (0, -1, True, False, 'x', None, float('nan'), float('inf')):
            with self.assertRaises(ContractError) as caught:
                VideoTaskWorker(service, poll_seconds=value)
            self.assertEqual(caught.exception.code, 'invalid_poll_seconds')
        self.assertEqual(service.calls, [])

    def test_disabled_or_preset_stop_makes_no_claim(self):
        for flag in (False, None, 1, 'yes'):
            service = FakeService([task()], enabled=flag)
            self.assertEqual(VideoTaskWorker(service).run(), 0)
            self.assertEqual(VideoTaskWorker(service).run(once=True), 0)
            self.assertEqual(service.calls, [])
        service, stop = FakeService([task()]), threading.Event()
        stop.set()
        self.assertEqual(VideoTaskWorker(service, stop_event=stop).run(), 0)
        self.assertEqual(service.calls, [])
        self.assertTrue(stop.is_set())

    def test_once_calls_run_next_exactly_once(self):
        service = FakeService([task(), task()])
        self.assertEqual(VideoTaskWorker(service).run(once=True), 1)
        self.assertEqual(len(service.calls), 1)
        self.assertEqual(len(service.results), 1)
        idle = FakeService()
        worker = VideoTaskWorker(idle)
        self.assertEqual(worker.run(once=True), 0)
        self.assertEqual(len(idle.calls), 1)
        self.assertFalse(worker.stop_event.is_set())  # once는 대기하지 않는다.

    def test_loop_counts_processed_tasks_and_waits_poll_when_idle(self):
        stop = WaitSetsEvent()
        service = FakeService([task('completed'), task('blocked'), task('failed')])
        worker = VideoTaskWorker(service, stop_event=stop, poll_seconds=0.25)
        self.assertEqual(worker.run(), 3)
        self.assertEqual(len(service.calls), 4)  # 3건 + idle 1회
        self.assertEqual(stop.waits, [0.25])  # 작업이 있는 동안은 대기하지 않는다.

    def test_idle_wait_is_interrupted_by_stop_event(self):
        entered, stop, outcome = threading.Event(), threading.Event(), {}
        service = FakeService(on_call=lambda n: entered.set())
        worker = VideoTaskWorker(service, stop_event=stop, poll_seconds=60)
        thread = threading.Thread(target=lambda: outcome.setdefault('done', worker.run()))
        thread.start()
        self.addCleanup(thread.join, WAIT)
        self.addCleanup(stop.set)
        self.assertTrue(entered.wait(WAIT))
        stop.set()
        thread.join(WAIT)
        self.assertFalse(thread.is_alive())
        self.assertEqual(outcome, {'done': 0})
        self.assertEqual(len(service.calls), 1)

    def test_stop_during_job_finishes_it_and_claims_no_next(self):
        stop, finished = threading.Event(), []

        def stop_midway(number):
            stop.set()  # 렌더 도중 정지 요청. 작업은 끊기지 않고 끝까지 간다.

        service = FakeService([task(), task()], on_call=stop_midway)
        original = service.run_next

        def run_next():
            result = original()
            finished.append(result['task_id'])
            return result
        service.run_next = run_next
        self.assertEqual(VideoTaskWorker(service, stop_event=stop).run(), 1)
        self.assertEqual((service.calls, finished), (['run_next'], ['task']))
        self.assertEqual(len(service.results), 1)

    def test_busy_is_idle_but_other_errors_propagate_without_reset(self):
        busy = ContractError('video_worker_busy')
        service = FakeService([busy])
        self.assertEqual(VideoTaskWorker(service).run(once=True), 0)
        stop = WaitSetsEvent()
        service = FakeService([busy, busy, task()])
        self.assertEqual(VideoTaskWorker(service, stop_event=stop, poll_seconds=0.5).run(), 0)
        self.assertEqual((len(service.calls), stop.waits), (1, [0.5]))  # busy 뒤 대기, 정지로 종료
        retry = threading.Event()
        service = FakeService([busy, task()], on_call=lambda n: retry.set() if n == 2 else None)
        worker = VideoTaskWorker(service, stop_event=retry, poll_seconds=0.01)
        self.assertEqual(worker.run(), 1)  # busy는 오류 없이 다시 시도되어 다음 작업을 처리한다.
        self.assertEqual(len(service.calls), 2)
        for error in (ContractError('video_disabled'), ContractError('video_storage_error'), RuntimeError('boom')):
            service = FakeService([error, task()])
            with self.assertRaises(type(error)) as caught:
                VideoTaskWorker(service).run()
            self.assertIs(caught.exception, error)
            self.assertEqual(service.calls, ['run_next'])  # 재시도하지 않는다.
        # unknown 작업도 한 건 처리로 세기만 하고 service에 reset/resume을 요청하지 않는다.
        service = FakeService([task('unknown')])
        self.assertEqual(VideoTaskWorker(service).run(once=True), 1)
        self.assertEqual(service.calls, ['run_next'])


if __name__ == '__main__':
    unittest.main()
