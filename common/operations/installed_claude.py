"""설치된 Claude CLI(구독 로그인)를 ClaudeSubscriptionProvider의 spawn으로 쓰는 격리 실행기.

서버가 신뢰하는 절대 executable/home/username/model만 받는다. 생성자는 프로세스를 띄우거나
키체인에 접근하지 않으며 capability_evidence의 text_only_verified는 False다. 명시적 verify()만
version/help/auth status를 읽고 도구 없는 고정 probe를 한 번 실행한다. 모든 프로세스는 새
임시 cwd와 고정 환경(HOME/USER/LOGNAME/PATH/LANG)으로만 실행하며 부모 환경은 읽지 않는다.
API fallback, 키 조회, 인증 파일 읽기, 자동 재검증은 없다.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
from types import MappingProxyType

from .models import ContractError
from .production_providers import _REQUIRED_FLAGS, _parse

PROBE_MARKER = 'AUTOSNS_INSTALLED_CLAUDE_PROBE_7f3a9c1e5b2d'
PROBE_PROMPT = 'Reply with exactly this single token and nothing else: ' + PROBE_MARKER
_PATH = '/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin'
_LANG = 'en_US.UTF-8'
_QUICK_TIMEOUT = 30
_PROBE_TIMEOUT = 180
_MAX_GENERATION_TIMEOUT = 900
_SPAWN_KWARGS = frozenset(('input', 'capture_output', 'text', 'cwd', 'env', 'timeout', 'shell'))
_VERSION = re.compile(r'[A-Za-z0-9][A-Za-z0-9._ ()+-]{0,63}')
_USERNAME = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}')
_MODEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}')
_PASSTHROUGH_REASONS = ('daily_limit', 'weekly_limit', 'monthly_limit', 'needs_login', 'isolation_violation')


@dataclass(frozen=True)
class _Verified:
    version: str
    flags: frozenset
    digests: tuple


def _digest(path):
    try:
        if not path.is_file():
            return None
        sha = hashlib.sha256()
        with path.open('rb') as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b''):
                sha.update(chunk)
        return sha.hexdigest()
    except OSError:
        return None


def _has_flag(help_text, flag):
    return re.search(r'(?<![\w-])' + re.escape(flag) + r'(?![\w-])', help_text) is not None


class InstalledClaudeRunner:
    """subprocess.run 호환 호출자. ClaudeSubscriptionProvider(spawn=runner)로 주입한다."""

    def __init__(self, executable: Path, home: Path, username: str, model: str, *,
                 spawn=subprocess.run, pinned_paths: tuple = ()):
        pinned = tuple(pinned_paths) if isinstance(pinned_paths, (tuple, list)) else None
        if (not isinstance(executable, Path) or not executable.is_absolute()
                or not isinstance(home, Path) or not home.is_absolute() or '\x00' in str(home)
                or not isinstance(username, str) or not _USERNAME.fullmatch(username)
                or not isinstance(model, str) or not _MODEL.fullmatch(model)
                or not callable(spawn) or pinned is None
                or not all(isinstance(p, Path) and p.is_absolute() for p in pinned)):
            raise ContractError('invalid_installed_claude_runner')
        self.executable, self.model, self.spawn = executable, model, spawn
        self._home, self._username = str(home), username
        # wrapper script를 쓰면 실제 바이너리를 pinned_paths로 함께 고정한다.
        self._pinned = (executable,) + pinned
        self._lock = threading.Lock()
        self._verify_lock = threading.Lock()
        self._state = None

    @property
    def capability_evidence(self):
        with self._lock:
            state = self._state
        return MappingProxyType(dict(
            executable=str(self.executable), version=state.version if state else '',
            supported_flags=state.flags if state else frozenset(), text_only_verified=state is not None))

    # -- 공통 ---------------------------------------------------------------
    def _environment(self):
        return {'HOME': self._home, 'USER': self._username, 'LOGNAME': self._username,
                'PATH': _PATH, 'LANG': _LANG}

    def _generation_args(self):
        # ClaudeSubscriptionProvider.generate가 만드는 명령과 정확히 같아야 한다.
        return [str(self.executable), '-p', '--model', self.model, '--tools', '', '--setting-sources', '',
                '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}', '--disable-slash-commands',
                '--no-session-persistence', '--output-format', 'stream-json', '--verbose']

    def _run(self, args, input_text, timeout):
        """(completed, None) 또는 (None, 'timeout'|'spawn_failed'). 원문 예외/출력은 버린다."""
        try:
            with tempfile.TemporaryDirectory(prefix='autosns-installed-claude-') as scratch:
                completed = self.spawn(list(args), input=input_text, capture_output=True, text=True,
                                       cwd=scratch, env=self._environment(), timeout=timeout, shell=False)
        except subprocess.TimeoutExpired:
            return None, 'timeout'
        except (OSError, subprocess.SubprocessError):
            return None, 'spawn_failed'
        if (not isinstance(getattr(completed, 'stdout', None), str)
                or type(getattr(completed, 'returncode', None)) is not int):
            return None, 'spawn_failed'
        return completed, None

    def _quick(self, *subcommand):
        completed, reason = self._run([str(self.executable), *subcommand], '', _QUICK_TIMEOUT)
        return completed, ('command_timeout' if reason == 'timeout' else reason)

    def _snapshot(self):
        pairs = tuple((str(path), _digest(path)) for path in self._pinned)
        return None if any(digest is None for _, digest in pairs) else pairs

    @staticmethod
    def _unchanged(digests):
        return all(_digest(Path(path)) == digest for path, digest in digests)

    def _check_auth(self):
        """구독(claude.ai/firstParty/max) 로그인만 통과. 값은 반환하지 않고 이유코드만 반환한다."""
        completed, reason = self._quick('auth', 'status')
        if reason:
            return reason
        try:
            data = json.loads(completed.stdout)
        except ValueError:
            return 'auth_unreadable'
        if not isinstance(data, dict):
            return 'auth_unreadable'
        if data.get('loggedIn') is not True:
            return 'needs_login'
        if (data.get('authMethod') != 'claude.ai' or data.get('apiProvider') != 'firstParty'
                or data.get('subscriptionType') != 'max'):
            return 'auth_not_subscription'
        return None if completed.returncode == 0 else 'auth_failed'

    # -- 명시 검증 ------------------------------------------------------------
    def verify(self):
        """설치를 검증한다. 시작 시 이전 증거를 폐기하며 성공할 때만 text_only_verified가 True가 된다."""
        with self._verify_lock:
            with self._lock:
                self._state = None
            reason, state = self._verify()
            if reason is None:
                with self._lock:
                    self._state = state
            return MappingProxyType(dict(verified=reason is None, reason_code=reason,
                                         version=state.version if reason is None else ''))

    def _verify(self):
        digests = self._snapshot()
        if digests is None or not os.access(self.executable, os.X_OK):
            return 'executable_untrusted', None
        completed, reason = self._quick('--version')
        version = completed.stdout.strip() if completed else ''
        if reason or completed.returncode != 0 or not _VERSION.fullmatch(version):
            return reason or 'version_failed', None
        completed, reason = self._quick('--help')
        if reason or completed.returncode != 0:
            return reason or 'help_failed', None
        flags = frozenset(flag for flag in _REQUIRED_FLAGS if _has_flag(completed.stdout, flag))
        if flags != _REQUIRED_FLAGS:
            return 'missing_flags', None
        reason = self._check_auth()
        if reason or not self._unchanged(digests):
            return reason or 'executable_changed', None
        completed, reason = self._run(self._generation_args(), PROBE_PROMPT, _PROBE_TIMEOUT)
        if reason:
            return ('probe_timeout' if reason == 'timeout' else reason), None
        parsed = _parse(completed.stdout, completed.returncode, 'installed-claude-probe')
        if parsed['status'] != 'completed':
            code = parsed['reason_code']
            return (code if code in _PASSTHROUGH_REASONS else 'probe_failed'), None
        if parsed['text'].strip() != PROBE_MARKER:
            return 'probe_mismatch', None
        if not self._unchanged(digests):
            return 'executable_changed', None
        return None, _Verified(version=version, flags=flags, digests=digests)

    # -- 생성 -----------------------------------------------------------------
    def _failure(self, subtype):
        stdout = json.dumps(dict(type='result', subtype=subtype, is_error=True))
        return subprocess.CompletedProcess([str(self.executable)], 1, stdout, '')

    def _rejects(self, args, kwargs):
        if not isinstance(args, (list, tuple)) or list(args) != self._generation_args():
            return True
        if not set(kwargs) <= _SPAWN_KWARGS or not isinstance(kwargs.get('input'), str):
            return True
        if 'shell' in kwargs and kwargs['shell'] is not False:
            return True
        if any(key in kwargs and kwargs[key] is not True for key in ('capture_output', 'text')):
            return True
        timeout = kwargs.get('timeout', _MAX_GENERATION_TIMEOUT)
        return (type(timeout) not in (int, float) or not 0 < timeout <= _MAX_GENERATION_TIMEOUT)

    def __call__(self, args, **kwargs):
        if self._rejects(args, kwargs):
            return self._failure('provider_error')
        with self._lock:
            state = self._state
        if state is None:
            return self._failure('provider_error')
        timeout = kwargs.get('timeout', _MAX_GENERATION_TIMEOUT)
        if not self._unchanged(state.digests):
            return self._discard(state)
        reason = self._check_auth()
        if reason is not None:
            return self._failure('needs_login' if reason == 'needs_login' else 'provider_error')
        if not self._unchanged(state.digests):
            return self._discard(state)
        completed, reason = self._run(self._generation_args(), kwargs['input'], timeout)
        if reason == 'timeout':
            # 원문 없는 새 예외. 기존 provider가 unknown/timeout으로 처리한다.
            raise subprocess.TimeoutExpired([str(self.executable)], timeout)
        if reason or not self._unchanged(state.digests):
            return self._discard(state) if not reason else self._failure('provider_error')
        return subprocess.CompletedProcess(self._generation_args(), completed.returncode, completed.stdout, '')

    def _discard(self, state):
        with self._lock:
            if self._state is state:
                self._state = None
        return self._failure('provider_error')
