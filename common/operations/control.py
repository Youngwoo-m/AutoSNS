"""원본 루트의 순수 정지 관측과 관리 실행 범위의 pause CAS."""
from common.shared.axlock import read_control_state


def set_managed_pause(store, scope, id, paused, expected_version, actor, reason, request_key):
    """관리 DB 정책만 바꾼다. resume은 작업을 enqueue하지 않는다."""
    from .models import ContractError
    if type(paused) is not bool:
        raise ContractError('invalid_control')
    return store.control(scope, id, 'pause' if paused else 'resume', expected_version,
                         request_key, reason, actor=actor)
