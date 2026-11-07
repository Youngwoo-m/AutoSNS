"""Windows 용 fcntl.flock 대체(2026-11-06 Mac 은퇴 후 이 PC 가 유일한 실행 환경).

POSIX 에서는 쓰지 않는다 — 각 파일이 `import fcntl` 을 먼저 시도하고, ImportError 일 때만 이 모듈을 쓴다.

msvcrt.locking 으로 파일 끝 너머 먼 위치(LOCK_OFFSET)의 1바이트를 잠근다. 데이터 영역을 잠그지 않으므로
잠금 파일 자체를 읽고 쓰는 코드(secret_env 의 .lock 등)와 부딪히지 않는다.

fcntl.flock 과 같게 맞춘 점:
- LOCK_EX|LOCK_NB 가 이미 잡혀 있으면 BlockingIOError(errno.EAGAIN).
- LOCK_EX(대기)는 잡힐 때까지 기다린다.
- LOCK_UN 은 잡지 않은 잠금이면 조용히 넘어간다.
- 프로세스가 죽거나 핸들을 닫으면 OS 가 풀어 준다.
다른 점: Windows 는 공유 잠금이 없어 LOCK_SH 도 배타로 잡는다. 같은 핸들로 다시 잡으면(flock 은 허용) 실패한다.
"""
import errno
import msvcrt
import os
import time

LOCK_SH = 1
LOCK_EX = 2
LOCK_NB = 4
LOCK_UN = 8
LOCK_OFFSET = 0x7FFFFFF0
_POLL = 0.05


def _fd(f):
    return f if isinstance(f, int) else f.fileno()


def flock(f, operation):
    fd = _fd(f)
    pos = os.lseek(fd, 0, os.SEEK_CUR)
    try:
        os.lseek(fd, LOCK_OFFSET, os.SEEK_SET)
        if operation & LOCK_UN:
            try:
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            return None
        while True:
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                return None
            except OSError as e:
                if e.errno not in (errno.EACCES, errno.EDEADLK, errno.EAGAIN):
                    raise
                if operation & LOCK_NB:
                    raise BlockingIOError(errno.EAGAIN, "Resource temporarily unavailable") from None
                time.sleep(_POLL)
                os.lseek(fd, LOCK_OFFSET, os.SEEK_SET)
    finally:
        os.lseek(fd, pos, os.SEEK_SET)


def load():
    """다른 파일에서 경로로 불러 쓸 때 같은 모듈 객체를 돌려준다."""
    import sys
    return sys.modules[__name__]
