"""영상 작업 대기열을 한 건씩 처리하는 독립 worker.

실제 렌더·상태 전이·재검증은 VideoTaskService.run_next가 담당하고, 이 worker는 호출 순서와 정지만 다룬다.
생성자는 I/O도 thread도 시작하지 않는다. 진행 중인 작업은 중단하거나 kill하지 않으며, unknown 작업을
reset하거나 다시 렌더하지 않는다.
"""
import math
import threading

from .models import ContractError

BUSY_CODE = 'video_worker_busy'


def _poll(value):
    if (type(value) not in (int, float) or isinstance(value, bool)
            or not math.isfinite(value) or value <= 0):
        raise ContractError('invalid_poll_seconds')
    return value


class VideoTaskWorker:
    def __init__(self, service, *, stop_event=None, poll_seconds=1.0):
        # enabled는 service마다 읽어야 하므로 속성 존재만 확인하고 값은 run에서 읽는다.
        if not hasattr(service, 'enabled') or not callable(getattr(service, 'run_next', None)):
            raise ContractError('invalid_video_service')
        event = threading.Event() if stop_event is None else stop_event
        if not all(callable(getattr(event, name, None)) for name in ('set', 'is_set', 'wait')):
            raise ContractError('invalid_stop_event')
        self.service, self.stop_event = service, event
        self.poll_seconds = _poll(poll_seconds)

    def run(self, once=False):
        """처리한 작업 수를 돌려준다. disabled이거나 stop이 이미 설정됐으면 아무 I/O 없이 0."""
        if self.service.enabled is not True or self.stop_event.is_set():
            return 0
        done = 0
        while self.service.enabled is True and not self.stop_event.is_set():  # 다음 claim 전에 정책·정지를 확인한다.
            try:
                task = self.service.run_next()
            except ContractError as error:
                if error.code != BUSY_CODE:
                    raise
                task = None  # 다른 프로세스가 렌더 중이다. 오류가 아니라 idle로 본다.
            if task is not None:
                done += 1
                if once:
                    break
                continue
            if once:
                break
            self.stop_event.wait(self.poll_seconds)
        return done
