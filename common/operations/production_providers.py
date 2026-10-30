"""구독 CLI의 텍스트 전용 실행 경계. 실제 CLI는 기본 unavailable이다.

spawn은 서버가 주입하는 subprocess.run 호환 호출자다. 서버 검증한 설치 버전의
capability_evidence(executable, version, supported_flags, text_only_verified)를
보유해야 한다. 요청/프롬프트로 capability 증거를 제출할 수 없다. 이 모듈은
CLI 발견, 인증 내용 추출, 설치 검증, 키 조회, fallback을 수행하지 않는다.
"""
from collections.abc import Mapping
import json
from pathlib import Path
import subprocess
import tempfile
import uuid

from .models import ContractError
from .production_models import ProductionRequest, ProviderPolicy
from .provider_policy import validate_provider_use

PROVIDER_ID = 'claude-subscription'
_REQUIRED_FLAGS = frozenset(('-p', '--model', '--tools', '--setting-sources', '--strict-mcp-config',
                             '--mcp-config', '--disable-slash-commands', '--no-session-persistence',
                             '--output-format', '--verbose'))
_ENV_ALLOWLIST = frozenset(('LANG', 'LC_ALL', 'TZ'))


def build_production_environment(names: tuple[str, ...], source: Mapping[str, str]) -> dict:
    """허용한 이름만 직접 읽는다. API 키/설정/런타임 주입 변수는 조회도 하지 않는다."""
    result = {}
    for name in names:
        if name in _ENV_ALLOWLIST:
            value = source.get(name)
            if isinstance(value, str) and '\x00' not in value:
                result[name] = value
    return result


def _result(execution_id, status, reason_code, text='', observed_usage=None):
    return dict(status=status, text=text, provider_id=PROVIDER_ID, execution_id=execution_id,
                reason_code=reason_code, observed_usage=observed_usage)


def _parse(stdout, returncode, execution_id):
    events = []
    try:
        for line in stdout.splitlines():
            if line.strip():
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError()
                events.append(event)
    except (TypeError, ValueError):
        return _result(execution_id, 'unknown', 'invalid_output')
    results = [e for e in events if e.get('type') == 'result']
    if not results:
        return _result(execution_id, 'unknown', 'missing_result')
    if len(results) != 1 or events[-1] is not results[0]:
        return _result(execution_id, 'unknown', 'invalid_output')
    pieces = []
    for event in events:
        if event.get('type') in ('tool_use', 'server_tool_use', 'tool_result', 'user'):
            return _result(execution_id, 'blocked', 'isolation_violation')
        if event.get('type') == 'assistant':
            message = event.get('message')
            if not isinstance(message, dict) or not isinstance(message.get('content'), list):
                return _result(execution_id, 'unknown', 'invalid_output')
            for block in message['content']:
                if not isinstance(block, dict):
                    return _result(execution_id, 'unknown', 'invalid_output')
                if block.get('type') in ('tool_use', 'server_tool_use', 'tool_result'):
                    return _result(execution_id, 'blocked', 'isolation_violation')
                if block.get('type') == 'text':
                    if not isinstance(block.get('text'), str):
                        return _result(execution_id, 'unknown', 'invalid_output')
                    pieces.append(block['text'])
    terminal = results[0]
    if terminal.get('is_error') is True or returncode != 0:
        # 오류 원문은 비밀/경로/임의 명령을 포함할 수 있어 반환하지 않는다.
        code = terminal.get('subtype')
        reason = code if code in ('daily_limit', 'weekly_limit', 'monthly_limit', 'needs_login') else 'provider_error'
        return _result(execution_id, 'blocked', reason)
    text = ''.join(pieces) if pieces else terminal.get('result')
    if terminal.get('is_error') is not False or not isinstance(text, str) or not text:
        return _result(execution_id, 'unknown', 'invalid_output')
    # CLI 비용 추정치를 실제 청구 사용량으로 취급하지 않는다.
    return _result(execution_id, 'completed', None, text=text)


class ClaudeSubscriptionProvider:
    def __init__(self, executable: Path, model: str, *, spawn):
        if (not isinstance(executable, Path) or not executable.is_absolute()
                or not isinstance(model, str) or not model.strip() or model.startswith('-')
                or not callable(spawn)):
            raise ContractError('invalid_production_provider')
        self.executable, self.model, self.spawn = executable, model, spawn

    def _available(self):
        evidence = getattr(self.spawn, 'capability_evidence', None)
        return (isinstance(evidence, Mapping) and evidence.get('executable') == str(self.executable)
                and isinstance(evidence.get('version'), str) and bool(evidence['version'])
                and evidence.get('text_only_verified') is True
                and isinstance(evidence.get('supported_flags'), (list, tuple, set, frozenset))
                and all(isinstance(flag,str) for flag in evidence['supported_flags'])
                and _REQUIRED_FLAGS <= set(evidence['supported_flags']))

    def generate(self, request, prompt: str, policy: ProviderPolicy) -> dict:
        if not isinstance(request, ProductionRequest) or not isinstance(prompt, str):
            raise ContractError('invalid_production_request')
        if (not isinstance(policy, ProviderPolicy) or request.owner_account_id != policy.owner_account_id
                or request.job_id not in policy.job_ids):
            raise ContractError('provider_policy_violation')
        for medium in request.required_outputs:
            validate_provider_use(policy, PROVIDER_ID, medium)
            if medium != 'text':
                raise ContractError('provider_media_unavailable')
        execution_id = 'production-execution-' + uuid.uuid4().hex
        if not self._available():
            return _result(execution_id, 'blocked', 'provider_unavailable')
        args = [str(self.executable), '-p', '--model', self.model, '--tools', '', '--setting-sources', '',
                '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}', '--disable-slash-commands',
                '--no-session-persistence', '--output-format', 'stream-json', '--verbose']
        # 부모 환경 전체를 읽거나 복사하지 않는다. 인증은 CLI 자체에 맡긴다.
        environment = {'PATH': '/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin', 'LANG': 'en_US.UTF-8'}
        try:
            with tempfile.TemporaryDirectory(prefix='autosns-production-') as scratch:
                completed = self.spawn(args, input=prompt, capture_output=True, text=True,
                                       cwd=scratch, env=environment, timeout=900, shell=False)
            return _parse(completed.stdout, completed.returncode, execution_id)
        except subprocess.TimeoutExpired:
            return _result(execution_id, 'unknown', 'timeout')
        except (OSError, subprocess.SubprocessError):
            return _result(execution_id, 'unknown', 'spawn_failed')
