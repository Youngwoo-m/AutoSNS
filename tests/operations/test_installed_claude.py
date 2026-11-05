import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from common.operations.installed_claude import InstalledClaudeRunner, PROBE_MARKER, PROBE_PROMPT
from common.operations.models import ContractError
from common.operations.production_models import ProductionRequest, ProviderPolicy
from common.operations.production_providers import ClaudeSubscriptionProvider, _REQUIRED_FLAGS, _parse

MODEL = 'claude-sonnet-5-5'
HELP = 'Usage: claude [options]\n  ' + '\n  '.join(sorted(_REQUIRED_FLAGS)) + '\n'
AUTH_OK = dict(loggedIn=True, authMethod='claude.ai', apiProvider='firstParty', subscriptionType='max')
FIXED_ENV = {'HOME': '/Users/tester', 'USER': 'tester', 'LOGNAME': 'tester',
             'PATH': '/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin', 'LANG': 'en_US.UTF-8'}


def cp(stdout, returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout, '')


def stream(text, extra=()):
    events = [{'type': 'system', 'subtype': 'init', 'tools': []}, *extra,
              {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': text}]}},
              {'type': 'result', 'subtype': 'success', 'is_error': False, 'result': text}]
    return '\n'.join(json.dumps(event) for event in events)


def command(executable):
    return [str(executable), '-p', '--model', MODEL, '--tools', '', '--setting-sources', '',
            '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}', '--disable-slash-commands',
            '--no-session-persistence', '--output-format', 'stream-json', '--verbose']


class FakeSpawn:
    def __init__(self):
        self.calls, self.hooks = [], {}
        self.help, self.auth = HELP, dict(AUTH_OK)

    @staticmethod
    def step(args):
        rest = list(args[1:])
        if rest == ['--version']:
            return 'version'
        if rest == ['--help']:
            return 'help'
        if rest == ['auth', 'status']:
            return 'auth'
        return 'model' if '-p' in rest else 'unknown'

    def __call__(self, args, **kwargs):
        step = self.step(args)
        self.calls.append((step, list(args), kwargs))
        if step in self.hooks:
            return self.hooks[step](args, kwargs)
        if step == 'version':
            return cp('2.1.310 (Claude Code)\n')
        if step == 'help':
            return cp(self.help)
        if step == 'auth':
            return cp(json.dumps(self.auth), 0 if self.auth.get('loggedIn') else 1)
        if step == 'model':
            return cp(stream(PROBE_MARKER if kwargs['input'] == PROBE_PROMPT else 'generated text'))
        raise AssertionError('unexpected process')

    def steps(self):
        return [call[0] for call in self.calls]


class InstalledClaudeRunnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.exe = Path(self.tmp.name) / 'claude'
        self.exe.write_bytes(b'#!/bin/sh\necho original\n')
        self.exe.chmod(0o755)
        self.fake = FakeSpawn()
        self.runner = InstalledClaudeRunner(self.exe, Path('/Users/tester'), 'tester', MODEL, spawn=self.fake)
        self.args = command(self.exe)

    def verified(self):
        self.assertTrue(self.runner.verify()['verified'])
        self.fake.calls.clear()

    def test_default_constructor_is_inert_and_evidence_immutable(self):
        evidence = self.runner.capability_evidence
        self.assertEqual(self.fake.calls, [])
        self.assertIs(evidence['text_only_verified'], False)
        self.assertEqual(evidence['executable'], str(self.exe))
        with self.assertRaises(TypeError):
            evidence['text_only_verified'] = True
        self.assertIsInstance(evidence['supported_flags'], frozenset)

    def test_verify_success_runs_isolated_probe_once(self):
        with mock.patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'sk-secret', 'CLAUDE_CODE_OAUTH_TOKEN': 'tok'}):
            result = self.runner.verify()
        self.assertEqual(dict(result), dict(verified=True, reason_code=None, version='2.1.310 (Claude Code)'))
        self.assertEqual(self.fake.steps(), ['version', 'help', 'auth', 'model'])
        self.assertEqual(self.fake.calls[-1][1], self.args)
        self.assertEqual(self.fake.calls[-1][2]['input'], PROBE_PROMPT)
        cwds = [call[2]['cwd'] for call in self.fake.calls]
        for _, _, kwargs in self.fake.calls:
            self.assertEqual(kwargs['env'], {**FIXED_ENV, 'HOME': '/Users/tester'})
            self.assertIs(kwargs['shell'], False)
            self.assertIs(kwargs['capture_output'], True)
            self.assertIs(kwargs['text'], True)
            self.assertGreater(kwargs['timeout'], 0)
        self.assertEqual(len(set(cwds)), len(cwds))
        self.assertFalse(any(os.path.exists(cwd) for cwd in cwds))
        self.assertNotIn('secret', json.dumps([call[2]['env'] for call in self.fake.calls]))
        evidence = self.runner.capability_evidence
        self.assertIs(evidence['text_only_verified'], True)
        self.assertLessEqual(_REQUIRED_FLAGS, evidence['supported_flags'])

    def test_missing_required_flags_skip_auth_and_probe(self):
        self.fake.help = HELP.replace('--tools', '--tool-x')
        result = self.runner.verify()
        self.assertEqual(result['reason_code'], 'missing_flags')
        self.assertEqual(self.fake.steps(), ['version', 'help'])
        self.assertIs(self.runner.capability_evidence['text_only_verified'], False)

    def test_non_subscription_auth_never_reaches_model(self):
        cases = [('needs_login', dict(loggedIn=False)),
                 ('auth_not_subscription', dict(AUTH_OK, authMethod='api_key')),
                 ('auth_not_subscription', dict(AUTH_OK, apiProvider='bedrock')),
                 ('auth_not_subscription', dict(AUTH_OK, subscriptionType='pro'))]
        for expected, auth in cases:
            with self.subTest(auth=auth):
                self.fake.calls.clear()
                self.fake.auth = auth
                result = self.runner.verify()
                self.assertEqual(result['reason_code'], expected)
                self.assertNotIn('model', self.fake.steps())
                self.assertNotIn('@', json.dumps(dict(result)))
                self.assertIs(self.runner.capability_evidence['text_only_verified'], False)

    def test_probe_failures_return_safe_reason_codes(self):
        tool = {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'name': 'Bash'}]}}
        limit = json.dumps({'type': 'result', 'subtype': 'weekly_limit', 'is_error': True, 'result': '/secret'})

        def raises(exc):
            def hook(args, kwargs):
                raise exc
            return hook
        cases = [('weekly_limit', lambda a, k: cp(limit, 1)),
                 ('probe_failed', lambda a, k: cp('not json')),
                 ('probe_failed', lambda a, k: cp(json.dumps({'type': 'assistant', 'message': {'content': []}}))),
                 ('isolation_violation', lambda a, k: cp(stream(PROBE_MARKER, [tool]))),
                 ('probe_mismatch', lambda a, k: cp(stream('hello'))),
                 ('probe_mismatch', lambda a, k: cp(stream(PROBE_MARKER + ' extra'))),
                 ('probe_timeout', raises(subprocess.TimeoutExpired('x', 1, output='secret'))),
                 ('spawn_failed', raises(OSError('/secret/path')))]
        for expected, hook in cases:
            with self.subTest(expected=expected):
                self.fake.hooks['model'] = hook
                result = self.runner.verify()
                self.assertEqual(result['reason_code'], expected)
                self.assertNotIn('secret', json.dumps(dict(result)))
                self.assertIs(self.runner.capability_evidence['text_only_verified'], False)

    def test_earlier_timeouts_and_binary_swap_fail_verify(self):
        def hang(args, kwargs):
            raise subprocess.TimeoutExpired(args, 1)
        self.fake.hooks['help'] = hang
        self.assertEqual(self.runner.verify()['reason_code'], 'command_timeout')
        self.assertNotIn('model', self.fake.steps())
        del self.fake.hooks['help']

        def swap(args, kwargs):
            self.exe.write_bytes(b'#!/bin/sh\necho evil\n')
            return cp(stream(PROBE_MARKER))
        self.fake.hooks['model'] = swap
        self.assertEqual(self.runner.verify()['reason_code'], 'executable_changed')
        self.assertIs(self.runner.capability_evidence['text_only_verified'], False)

    def test_failed_reverify_discards_previous_evidence(self):
        self.verified()
        self.assertIs(self.runner.capability_evidence['text_only_verified'], True)
        self.fake.auth = dict(loggedIn=False)
        self.assertFalse(self.runner.verify()['verified'])
        self.assertIs(self.runner.capability_evidence['text_only_verified'], False)
        self.fake.calls.clear()
        self.assertEqual(_parse(self.runner(self.args, input='x', timeout=9).stdout, 1, 'e')['reason_code'],
                         'provider_error')
        self.assertEqual(self.fake.calls, [])

    def test_generation_without_verify_makes_no_process_calls(self):
        result = self.runner(self.args, input='prompt', timeout=900)
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(_parse(result.stdout, result.returncode, 'e')['reason_code'], 'provider_error')

    def test_generation_reauths_and_replaces_env(self):
        self.verified()
        with mock.patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'sk-secret'}):
            result = self.runner(self.args, input='write', capture_output=True, text=True, shell=False,
                                 timeout=900, cwd='/tmp/other', env={'ANTHROPIC_API_KEY': 'sk-injected'})
        self.assertEqual(self.fake.steps(), ['auth', 'model'])
        self.assertEqual(self.fake.calls[1][2]['input'], 'write')
        for _, _, kwargs in self.fake.calls:
            self.assertEqual(kwargs['env'], FIXED_ENV)
            self.assertNotEqual(kwargs['cwd'], '/tmp/other')
        self.assertEqual(_parse(result.stdout, result.returncode, 'e')['text'], 'generated text')
        self.assertEqual(result.stderr, '')

    def test_generation_auth_failure_makes_zero_model_calls(self):
        self.verified()
        self.fake.auth = dict(loggedIn=False)
        result = self.runner(self.args, input='write', timeout=900)
        self.assertEqual(self.fake.steps(), ['auth'])
        self.assertEqual(_parse(result.stdout, result.returncode, 'e')['reason_code'], 'needs_login')
        self.fake.auth = dict(AUTH_OK, subscriptionType='pro')
        self.fake.calls.clear()
        result = self.runner(self.args, input='write', timeout=900)
        self.assertEqual(self.fake.steps(), ['auth'])
        self.assertEqual(_parse(result.stdout, result.returncode, 'e')['reason_code'], 'provider_error')

    def test_replaced_binary_is_rejected_before_any_execution(self):
        self.verified()
        self.exe.write_bytes(b'#!/bin/sh\necho evil\n')
        result = self.runner(self.args, input='write', timeout=900)
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(result.returncode, 1)
        self.assertIs(self.runner.capability_evidence['text_only_verified'], False)
        # 호출 도중 교체되면 모델 출력도 폐기한다.
        self.exe.write_bytes(b'#!/bin/sh\necho original\n')
        self.verified()

        def swap(args, kwargs):
            self.exe.write_bytes(b'#!/bin/sh\necho evil2\n')
            return cp(stream('tainted'))
        self.fake.hooks['model'] = swap
        result = self.runner(self.args, input='write', timeout=900)
        self.assertNotIn('tainted', result.stdout)
        self.assertIs(self.runner.capability_evidence['text_only_verified'], False)

    def test_binary_changed_during_auth_is_not_executed_for_generation(self):
        self.verified()
        def swap(args, kwargs):
            self.exe.write_bytes(b'changed during auth')
            return cp(json.dumps(AUTH_OK))
        self.fake.hooks['auth'] = swap
        result = self.runner(self.args, input='write', timeout=900)
        self.assertEqual(self.fake.steps(), ['auth'])
        self.assertEqual(result.returncode, 1)
        self.assertIs(self.runner.capability_evidence['text_only_verified'], False)

    def test_injected_model_flags_and_kwargs_are_rejected(self):
        self.verified()
        swapped = lambda old, new: [new if a == old else a for a in self.args]
        bad_args = [swapped(MODEL, 'claude-other'), self.args[:-1], self.args + ['--dangerously-skip-permissions'],
                    swapped('{"mcpServers":{}}', '{"mcpServers":{"x":{}}}'),
                    self.args[:5] + ['Bash'] + self.args[6:], ' '.join(self.args), self.args[:-1] + ['--debug'],
                    ['/bin/sh'] + self.args[1:]]
        for args in bad_args:
            with self.subTest(args=args):
                self.assertEqual(self.runner(args, input='x', timeout=9).returncode, 1)
        bad_kwargs = [dict(input=1), dict(), dict(input='x', timeout=901), dict(input='x', timeout=True),
                      dict(input='x', shell=True), dict(input='x', check=True), dict(input='x', stdin=None),
                      dict(input='x', capture_output=False), dict(input='x', executable='/bin/sh')]
        for kwargs in bad_kwargs:
            with self.subTest(kwargs=kwargs):
                self.assertEqual(self.runner(self.args, **kwargs).returncode, 1)
        self.assertEqual(self.fake.calls, [])

    def test_constructor_rejects_untrusted_inputs(self):
        good = dict(executable=self.exe, home=Path('/Users/tester'), username='tester', model=MODEL, spawn=self.fake)
        for key, value in dict(executable=Path('claude'), home=Path('home'), username='a b', model='-x',
                               spawn=None).items():
            with self.subTest(key=key):
                with self.assertRaises(ContractError):
                    InstalledClaudeRunner(**dict(good, **{key: value}))
        with self.assertRaises(ContractError):
            InstalledClaudeRunner(**good, pinned_paths=(Path('relative'),))

    def test_provider_generate_integration(self):
        provider = ClaudeSubscriptionProvider(self.exe, MODEL, spawn=self.runner)
        policy = ProviderPolicy(id='p', owner_account_id='personal', job_ids=('j1',), subscription_only=True,
                                allowed_provider_ids=('claude-subscription',), allowed_media=('text',),
                                budget_refs=())
        request = ProductionRequest(job_id='j1', owner_account_id='personal', occurrence_id='o1',
                                    content_id='c1', expected_revision=1, brief='b', required_outputs=('text',))
        self.assertEqual(provider.generate(request, 'write', policy)['reason_code'], 'provider_unavailable')
        self.assertEqual(self.fake.calls, [])
        self.verified()
        result = provider.generate(request, 'write', policy)
        self.assertEqual((result['status'], result['text']), ('completed', 'generated text'))
        self.fake.auth = dict(loggedIn=False)
        result = provider.generate(request, 'write', policy)
        self.assertEqual((result['status'], result['reason_code']), ('blocked', 'needs_login'))
        self.fake.auth = dict(AUTH_OK)

        def hang(args, kwargs):
            raise subprocess.TimeoutExpired(args, 900, output='secret prompt')
        self.fake.hooks['model'] = hang
        result = provider.generate(request, 'secret prompt', policy)
        self.assertEqual((result['status'], result['reason_code']), ('unknown', 'timeout'))
        self.assertNotIn('secret', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
