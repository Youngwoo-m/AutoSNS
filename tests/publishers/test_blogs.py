"""다섯 연결의 실제 managed leaf를 fake Google/DOM까지 실행한다. 운영 접근 없음."""
import importlib
import importlib.util
import copy
import hashlib
import os
from pathlib import Path
import sys
import unittest
from datetime import timedelta
from unittest.mock import patch

from common.operations.models import Registry, Connection
from common.operations.runtime_models import SubmissionPermit
from tests.publishers.test_blog_payloads import context, snapshot, NOW


CONNECTIONS = ('dept.blogger', 'personal.blogger', 'dept.naver_blog', 'personal.naver_blog', 'personal.tistory')


def registry():
    connections = {}
    credentials = {}
    profiles = {}
    jobs = {}
    for key in CONNECTIONS:
        account, platform = key.split('.')
        profiles[account] = {'account_id': account, 'lock_resource': 'profile:naver' if account == 'dept' else 'profile:tistory'}
        ref = key + '.credential'
        credentials[ref] = {'account_id': account, 'platform': platform}
        connections[key] = Connection(key, account, platform, target_id='target-' + key,
                                     credential_ref=ref, profile_ref=account,
                                     expected_login_subject='subject-' + account, enabled=True)
        jobs['job-' + key] = dict(executor_id='blog.' + key, connection_id=key,
                                  owner_account_id=account, enabled=True, execution_owner='managed',
                                  policy_revision='policy', schedule_owner='console')
    return Registry('registry', {'dept': {}, 'personal': {}}, credentials, profiles, connections, jobs, {'policy': {}}, {})


def ctx(key):
    account, platform = key.split('.')
    return context(platform, destination_account_id=account, owner_account_id=account,
                   connection_id=key, target_id='target-' + key)


class Request:
    def __init__(self, result): self.result = result
    def execute(self): return copy.deepcopy(self.result)


class FakeGoogle:
    def __init__(self, key):
        self.key = key
        self.target = 'target-' + key
        self.calls = []
        self.remote = dict(id='remote', blog={'id': self.target}, title='안전 <확인>',
                           content='원본', published=NOW.isoformat(), status='LIVE', images=[])
    def blogs(self): return self
    def users(self): return self
    def posts(self): return self
    def listByUser(self, **kw):
        self.calls.append(('listByUser', kw))
        return Request({'items': [{'id': self.target}]})
    def get(self, **kw):
        self.calls.append(('get', kw))
        if 'userId' in kw: return Request({'id': 'subject-' + self.key.split('.')[0]})
        return Request(self.remote if 'postId' in kw else {'id': self.target})
    def list(self, **kw):
        self.calls.append(('list', kw))
        return Request({'items': [self.remote]})
    def insert(self, **kw):
        self.calls.append(('insert', kw))
        return Request({'id': 'remote', 'url': 'https://example.org/remote'})


class Element:
    def __init__(self, driver, name): self.driver, self.name = driver, name
    def send_keys(self, value): self.driver.events.append(('input', self.name, value))
    def click(self): self.driver.events.append(('click', self.name))
    def get_attribute(self, key): return ''
    @property
    def text(self): return '본문'


class FakeDriver:
    def __init__(self, key):
        self.key = key
        self.events = []
        self.current_url = ''
        self.editor_html = ''
        self.identity = dict(authenticated=True, login_subject='subject-' + key.split('.')[0],
                             targets=[{'id': 'target-' + key, 'url': 'https://fixture.tistory.com/manage'}])
        self.remote = dict(remote_id='123' if key.endswith('tistory') else 'remote', target_id='target-' + key, body_text='원본',
                           media=[], visibility='public', created_at=NOW.isoformat(),
                           url='https://example.org/remote')
    def get(self, url): self.current_url = url; self.events.append(('get', url))
    def execute_script(self, script, *args):
        self.events.append(('script', script, args))
        if 'DataTransfer' in script:
            self.editor_html = self.editor_html.replace('<p data-ax-attach="asset"></p>', '<p>[##_File|remote-token_##]</p>')
        if 'tinymce.activeEditor.setContent' in script and args: self.editor_html = args[0]
        if script == 'return tinymce.activeEditor.getContent()': return self.editor_html
        if 'AX_BLOG_IDENTITY_READ' in script: return copy.deepcopy(self.identity)
        if 'AX_BLOG_REMOTE_READ' in script: return copy.deepcopy(self.remote)
        if 'AX_BLOG_SUBMIT_RESULT' in script: return {'remote_id': '123' if self.key.endswith('tistory') else 'remote', 'target_id': 'target-' + self.key, 'url': 'https://example.org/remote'}
        return None
    def find_element(self, by, selector): return Element(self, selector)
    def find_elements(self, by, selector): return [Element(self, selector)]
    def quit(self): self.events.append(('quit',))


class InlineBridge:
    """프로세스 보안관문은 A2 시험, 여기서는 실 handler→leaf→lowest fake를 검사한다."""
    def __init__(self, handlers, credentials): self.handlers, self.credentials = handlers, credentials
    def read(self, executor, action, context, payload):
        values = context.to_dict() if hasattr(context, 'to_dict') else context
        return self.handlers[(executor, action)](values, payload, self.credentials[values['connection_id']])
    def submit(self, executor, context, prepared, permit):
        return self.handlers[(executor, 'publish')](context.to_dict(), prepared, self.credentials[context.connection_id])


class BlogTests(unittest.TestCase):
    def setUp(self):
        self.registry = registry()
        self.google = {key: FakeGoogle(key) for key in CONNECTIONS if key.endswith('blogger')}
        self.drivers = {key: FakeDriver(key) for key in CONNECTIONS if not key.endswith('blogger')}
        self.credentials = {key: object() for key in CONNECTIONS}
        self.profiles = []

    def components(self):
        self.assertIsNotNone(importlib.util.find_spec('common.publishers.blog_runtime'), '고정 blog runtime 구현 필요')
        from common.publishers.blog_runtime import build_blog_handlers
        from common.publishers.blog_services import GoogleBlogServices, BrowserBlogServices
        def services(key, credentials):
            self.assertIs(credentials, self.credentials[key])
            if key.endswith('blogger'):
                return GoogleBlogServices(self.google[key], public_service=self.google[key], clock=lambda: NOW)
            def factory(profile):
                self.profiles.append((key, profile))
                return self.drivers[key]
            return BrowserBlogServices(key, driver_factory=factory, clock=lambda: NOW)
        handlers = build_blog_handlers(self.registry, services_factory=services, clock=lambda: NOW)
        bridge = InlineBridge(handlers, self.credentials)
        adapters = {}
        for key in CONNECTIONS:
            platform = key.split('.')[1]
            module_name = 'naver' if platform == 'naver_blog' else platform
            adapters[key] = importlib.import_module('common.publishers.' + module_name).build_adapter(self.registry, bridge)
        return adapters

    def test_account_target_and_credential_are_exact(self):
        adapters = self.components()
        for key, adapter in adapters.items():
            with self.subTest(connection=key):
                result = adapter.inspect_target(ctx(key))
                self.assertTrue(result['authenticated'])
                self.assertEqual(result['target_id'], 'target-' + key)
                self.assertEqual(result['login_subject'], 'subject-' + key.split('.')[0])
                self.assertEqual(result['platform'], key.split('.')[1])
        personal_profiles = [str(profile) for key, profile in self.profiles if key == 'personal.naver_blog']
        self.assertTrue(personal_profiles)
        self.assertTrue(all('safeworking' in profile for profile in personal_profiles))
        self.assertFalse(any(profile.endswith('/chrome-profile') for profile in personal_profiles))

    def test_prepare_and_inspect_never_write_editor_or_publish(self):
        adapters = self.components()
        for key, adapter in adapters.items():
            with self.subTest(connection=key):
                adapter.prepare(ctx(key), snapshot())
                adapter.inspect_target(ctx(key))
        self.assertFalse(any(name == 'insert' for api in self.google.values() for name, _ in api.calls))
        for driver in self.drivers.values():
            self.assertFalse(any(event[0] in ('input', 'click') for event in driver.events))
            self.assertFalse(any(event[0] == 'get' and ('newpost' in event[1] or 'GoBlogWrite' in event[1]) for event in driver.events))
            self.assertFalse(any(event[0] == 'script' and ('setContent' in event[1] or 'Network.setCookies' in event[1]) for event in driver.events))

    def test_submit_reaches_existing_managed_leaf_exactly_once(self):
        adapters = self.components()
        for key, adapter in adapters.items():
            with self.subTest(connection=key):
                c = ctx(key)
                prepared = adapter.prepare(c, {**snapshot(), 'assets': []})
                permit = SubmissionPermit('attempt', 'nonce', c.run_id or 'run', 1, NOW + timedelta(minutes=1), c.context_hash, 'approval')
                result = adapter.submit(c, prepared, permit)
                self.assertEqual(result.outcome, 'submitted')
                self.assertEqual(result.remote_id, '123' if key.endswith('tistory') else 'remote')
                if key.endswith('blogger'):
                    inserts = [args for name, args in self.google[key].calls if name == 'insert']
                    self.assertEqual(len(inserts), 1)
                    self.assertEqual(inserts[0]['blogId'], c.target_id)
                    self.assertEqual(inserts[0]['body']['content'], prepared['body_html'])
                else:
                    events = self.drivers[key].events
                    self.assertTrue(any(event[0] == 'input' for event in events))
                    self.assertEqual(sum(event[0] == 'script' and 'AX_BLOG_FINAL_PUBLISH' in event[1] for event in events), 1)

    def test_transform_preserves_sources_category_ai_notice(self):
        from dataclasses import replace
        for key, adapter in self.components().items():
            with self.subTest(connection=key):
                c = replace(ctx(key), options={'category': '필수분류', 'ai_notice': 'AI 활용 고지'})
                data = adapter.prepare(c, snapshot())
                self.assertEqual(data['category'], '필수분류')
                self.assertEqual(data['sources'], snapshot()['sources'])
                self.assertIn('AI 활용 고지', data['body_html'])

    def test_import_side_effects_zero(self):
        self.assertIsNotNone(importlib.util.find_spec('common.publishers.blog_legacy'), '안전 leaf loader 구현 필요')
        from common.publishers.blog_legacy import load_blog_leaf
        for key in CONNECTIONS:
            sys.modules.pop('_autosns_managed_' + key.replace('.', '_'), None)
        before_env, before_path = dict(os.environ), list(sys.path)
        with patch('os.makedirs', side_effect=AssertionError('mkdir 금지')), \
             patch('socket.socket', side_effect=AssertionError('network 금지')), \
             patch('subprocess.Popen', side_effect=AssertionError('spawn 금지')):
            for key in CONNECTIONS:
                module = load_blog_leaf(key)
                self.assertTrue(callable(module.managed_submit))
        self.assertEqual(dict(os.environ), before_env)
        self.assertEqual(sys.path, before_path)

    def test_tistory_read_driver_never_restores_saves_or_relogs(self):
        from common.publishers.blog_legacy import load_tistory_support
        from types import ModuleType
        support = load_tistory_support()
        class Options:
            def __init__(self): self.args = []
            def add_argument(self, value): self.args.append(value)
            def add_experimental_option(self, *args): pass
            def set_capability(self, *args): pass
        root_module, webdriver, options = ModuleType('selenium'), ModuleType('selenium.webdriver'), ModuleType('selenium.webdriver.chrome.options')
        webdriver.Chrome = lambda **kwargs: self.drivers['personal.tistory']
        root_module.webdriver, options.Options = webdriver, Options
        with patch.dict(sys.modules, {'selenium': root_module, 'selenium.webdriver': webdriver, 'selenium.webdriver.chrome.options': options}), \
             patch.object(support, 'restore_cookies', side_effect=AssertionError('쿠키 restore 금지')), \
             patch.object(support, 'save_cookies', side_effect=AssertionError('쿠키 save 금지')), \
             patch.object(support, 'kakao_relogin', side_effect=AssertionError('자동 재인증 금지')), \
             patch.object(support, 'start_chrome', side_effect=AssertionError('legacy driver 금지')):
            driver = support.build_read_driver(profile=Path('/tmp/fixture-profile'))
        self.assertIs(driver, self.drivers['personal.tistory'])

    def test_legacy_common_import_does_not_create_profile_or_data_directories(self):
        root = Path(__file__).resolve().parents[2]
        spec = importlib.util.spec_from_file_location('_fixture_legacy_common', root / 'dept/naver-blog-auto/common.py')
        module = importlib.util.module_from_spec(spec)
        with patch('os.makedirs', side_effect=AssertionError('import mkdir 금지')):
            spec.loader.exec_module(module)
        self.assertTrue(callable(module.start_chrome))

    def test_timeout_retains_remote_uncertainty(self):
        adapters = self.components()
        for key, adapter in adapters.items():
            with self.subTest(connection=key):
                with patch.object(adapter.bridge, 'submit', side_effect=TimeoutError('no result')):
                    result = adapter.submit(ctx(key), adapter.prepare(ctx(key), snapshot()), object())
                self.assertEqual(result.outcome, 'unknown')
                self.assertIsNone(result.remote_id)

    def test_remote_body_change_cannot_verify(self):
        adapters = self.components()
        for key, adapter in adapters.items():
            with self.subTest(connection=key):
                if key in self.google: self.google[key].remote['content'] = '다른 본문'
                else: self.drivers[key].remote['body_text'] = '다른 본문'
                result = adapter.verify(ctx(key), '123' if key.endswith('tistory') else 'remote', {**snapshot(), 'assets': []})
                self.assertNotEqual(result.outcome, 'verified')

    def test_reviewed_asset_reader_is_bound_on_server_and_uploads_only_in_submit(self):
        from common.publishers.blog_runtime import build_blog_handlers
        from common.publishers.blog_services import BrowserBlogServices
        from common.publishers.blog_legacy import load_blog_leaf
        from types import SimpleNamespace
        data = b'%PDF-fixture'
        asset = dict(id='asset', filename='reviewed.pdf', sha256=hashlib.sha256(data).hexdigest())
        reads = []
        def read_asset(content_id, revision, asset_id):
            reads.append((content_id, revision, asset_id))
            return asset, data
        services = {}
        def factory(key, credentials):
            services[key] = BrowserBlogServices(key, driver_factory=lambda profile: self.drivers[key], clock=lambda: NOW)
            return services[key]
        import inspect
        self.assertIn('content_store', inspect.signature(build_blog_handlers).parameters, '서버 자산 reader 결속 필요')
        handlers = build_blog_handlers(self.registry, services_factory=factory, clock=lambda: NOW,
                                       content_store=SimpleNamespace(read_asset=read_asset))
        bridge = InlineBridge(handlers, self.credentials)
        for key in CONNECTIONS[2:]:
            with self.subTest(connection=key):
                module = importlib.import_module('common.publishers.' + ('tistory' if key.endswith('tistory') else 'naver'))
                adapter = module.build_adapter(self.registry, bridge)
                prepared = adapter.prepare(ctx(key), {**snapshot(), 'assets': [asset]})
                adapter.inspect_target(ctx(key))
                self.assertFalse(any(item[0] == 'input' for item in self.drivers[key].events))
                leaf = load_blog_leaf(key)
                with patch.object(leaf.time, 'sleep', return_value=None) if hasattr(leaf, 'time') else patch('time.sleep', return_value=None):
                    result = adapter.submit(ctx(key), prepared, object())
                self.assertEqual(result.outcome, 'submitted')
                self.assertEqual(reads[-1], ('content', 1, 'asset'))
                if key.endswith('tistory'):
                    self.assertEqual(sum(event[0] == 'script' and 'DataTransfer' in event[1] for event in self.drivers[key].events), 1)
                else:
                    self.assertEqual(sum(event[0] == 'input' and event[1] == 'input[type="file"]' for event in self.drivers[key].events), 1)

    def test_exact_credential_resolver_and_default_disabled_catalog(self):
        from common.publishers.blog_runtime import CREDENTIAL_CATALOG, build_blog_catalog
        from common.publishers.legacy_bridge import resolve_registered_credentials
        from common.operations.registry import load_registry
        calls = []
        def resolver(reference, **kwargs):
            calls.append((reference, kwargs))
            return self.credentials[reference.removesuffix('.credential')]
        for key in CONNECTIONS:
            for scope in ('read', 'publication'):
                result = resolve_registered_credentials(key, registry=self.registry,
                    credential_catalog=CREDENTIAL_CATALOG, resolver=resolver, scope=scope)
                self.assertIs(result, self.credentials[key])
                self.assertEqual(calls[-1], (key + '.credential', dict(account_id=key.split('.')[0], platform=key.split('.')[1], scope=scope)))
        actual = load_registry(Path(__file__).resolve().parents[2] / 'ax-console/config/operations.json')
        self.assertEqual(dict(build_blog_catalog(actual).executors), {})
        catalog = build_blog_catalog(self.registry)
        self.assertEqual(set(catalog.executors), {'blog.' + key for key in CONNECTIONS})
        self.assertTrue(all(spec.mutation_actions == ('publish',) for spec in catalog.executors.values()))
        for key in CONNECTIONS:
            spec = catalog.executors['blog.' + key]
            project = 'personal/naver-blog-auto' if key == 'personal.tistory' else 'dept/naver-blog-auto'
            self.assertTrue(str(spec.cwd).endswith(project))
            self.assertEqual(spec.interpreter, str(spec.cwd / '.venv/bin/python'))

    def test_managed_paths_never_call_legacy_dry_count_or_generation(self):
        from common.publishers.blog_legacy import load_blog_leaf
        adapters = self.components()
        for key, adapter in adapters.items():
            with self.subTest(connection=key):
                leaf = load_blog_leaf(key)
                with patch.object(leaf, 'publish', side_effect=AssertionError('legacy publish/dry 금지'), create=True), \
                     patch.object(leaf, '_count_post', side_effect=AssertionError('이중 한도 금지'), create=True), \
                     patch.object(leaf, 'load_config', side_effect=AssertionError('설정/비밀 읽기 금지'), create=True):
                    prepared = adapter.prepare(ctx(key), {**snapshot(), 'assets': []})
                    adapter.inspect_target(ctx(key))
                    self.assertEqual(adapter.submit(ctx(key), prepared, object()).outcome, 'submitted')

    def test_response_loss_after_lowest_transport_started_stays_unknown(self):
        adapters = self.components()
        for key, adapter in adapters.items():
            with self.subTest(connection=key):
                prepared = adapter.prepare(ctx(key), {**snapshot(), 'assets': []})
                if key in self.google:
                    original = self.google[key].insert
                    def lost(**kwargs):
                        original(**kwargs)
                        raise TimeoutError('response lost')
                    with patch.object(self.google[key], 'insert', side_effect=lost):
                        result = adapter.submit(ctx(key), prepared, object())
                    self.assertEqual(sum(name == 'insert' for name, _ in self.google[key].calls), 1)
                else:
                    original = self.drivers[key].execute_script
                    def lost(script, *args):
                        value = original(script, *args)
                        if 'AX_BLOG_SUBMIT_RESULT' in script: raise TimeoutError('response lost')
                        return value
                    with patch.object(self.drivers[key], 'execute_script', side_effect=lost):
                        result = adapter.submit(ctx(key), prepared, object())
                    self.assertTrue(any(event[0] == 'input' for event in self.drivers[key].events))
                self.assertEqual(result.outcome, 'unknown')

    def test_matching_remote_bytes_can_verify_and_media_unknown_cannot(self):
        from dataclasses import replace
        for key, adapter in self.components().items():
            with self.subTest(connection=key):
                data = {**snapshot(), 'variants': [], 'sources': [], 'assets': []}
                c = ctx(key)
                if key in self.google:
                    data['original'] = '<p>원본</p>'
                    self.google[key].remote['content'] = data['original']
                    c = replace(c, options={'body_format': 'html'})
                result = adapter.verify(c, '123' if key.endswith('tistory') else 'remote', data)
                self.assertEqual(result.outcome, 'verified')
                if key in self.google:
                    self.google[key].remote['images'] = [{'url': 'https://example.org/image'}]
                else:
                    self.drivers[key].remote['media'] = [{'url': 'https://example.org/image'}]
                result = adapter.verify(c, '123' if key.endswith('tistory') else 'remote', data)
                self.assertEqual(result.outcome, 'unsupported')

    def test_stop_after_editor_input_blocks_final_publish(self):
        from common.publishers.blog_runtime import build_blog_handlers
        from common.publishers.blog_services import BrowserBlogServices
        from common.publishers.naver import build_adapter
        checks = []
        def before_write():
            checks.append('checked')
            if len(checks) > 1: raise RuntimeError('fixture STOP')
        service = BrowserBlogServices('personal.naver_blog', driver_factory=lambda profile: self.drivers['personal.naver_blog'])
        handlers = build_blog_handlers(self.registry, services_factory=lambda *args: service,
                                       before_write=before_write, clock=lambda: NOW)
        adapter = build_adapter(self.registry, InlineBridge(handlers, self.credentials))
        result = adapter.submit(ctx('personal.naver_blog'), adapter.prepare(ctx('personal.naver_blog'), {**snapshot(), 'assets': []}), object())
        self.assertEqual(result.outcome, 'unknown')
        self.assertTrue(any(event[0] == 'input' for event in self.drivers['personal.naver_blog'].events))
        self.assertFalse(any(event[0] == 'script' and 'AX_BLOG_FINAL_PUBLISH' in event[1] for event in self.drivers['personal.naver_blog'].events))

    def test_default_bootstrap_is_disabled_before_store_or_profile_access(self):
        from common.publishers.blog_runtime import bridge_bootstrap
        with patch('common.operations.runtime_store.RuntimeStore', side_effect=AssertionError('비활성 DB 접근 금지')), \
             patch('common.publishers.blog_services.chrome_driver', side_effect=AssertionError('비활성 profile 접근 금지')):
            for platform in ('blogger', 'naver_blog', 'tistory'):
                with self.subTest(platform=platform), self.assertRaisesRegex(Exception, 'bridge_unavailable'):
                    bridge_bootstrap(platform)

    def test_fixed_encrypted_keys_and_google_client_factory_use_exact_credentials(self):
        from common.publishers.blog_runtime import resolve_blog_credentials
        from common.publishers.blog_services import create_blog_services
        from types import ModuleType, SimpleNamespace
        import common.shared as shared_package
        secrets = ModuleType('common.shared.secret_env')
        secrets.read = lambda: {'BLOGGER_TOKEN_DEPT': '{"fixture":"dept"}', 'BLOGGER_TOKEN_GEOAI': '{"fixture":"personal"}'}
        credentials_module = ModuleType('google.oauth2.credentials')
        captures = []
        class Credentials:
            @staticmethod
            def from_authorized_user_info(value, scopes):
                captures.append((value, scopes))
                return SimpleNamespace(valid=True, owner=value['fixture'])
        credentials_module.Credentials = Credentials
        request_module = ModuleType('google.auth.transport.requests')
        request_module.Request = lambda: object()
        discovery = ModuleType('googleapiclient.discovery')
        clients = []
        def build(api, version, **kwargs):
            clients.append((api, version, kwargs))
            return self.google['dept.blogger']
        discovery.build = build
        http = ModuleType('httplib2')
        http.Http = lambda: 'unauthenticated-http'
        modules = {'common.shared.secret_env': secrets, 'google.oauth2.credentials': credentials_module,
                   'google.auth.transport.requests': request_module, 'googleapiclient.discovery': discovery, 'httplib2': http}
        with patch.dict(sys.modules, modules), patch.object(shared_package, 'secret_env', secrets, create=True):
            for account in ('dept', 'personal'):
                credential = resolve_blog_credentials(account + '.blogger.credential', account_id=account, platform='blogger', scope='read')
                self.assertEqual(credential.owner, account)
                self.assertEqual(captures[-1], ({'fixture': account}, ['https://www.googleapis.com/auth/blogger']))
                create_blog_services(account + '.blogger', credential)
                self.assertIs(clients[-2][2]['credentials'], credential)
                self.assertNotIn('credentials', clients[-1][2])
                self.assertEqual(clients[-1][2]['http'], 'unauthenticated-http')
            with self.assertRaises(Exception):
                resolve_blog_credentials('dept.blogger.credential', account_id='personal', platform='blogger', scope='read')

    def test_lookup_requires_unique_body_media_time_match(self):
        from types import SimpleNamespace
        adapters = self.components()
        data = {**snapshot(), 'variants': [], 'sources': [], 'assets': []}
        bridge = next(iter(adapters.values())).bridge
        bridge.store = SimpleNamespace(content_store=SimpleNamespace(get=lambda *args: data))
        for key, adapter in adapters.items():
            with self.subTest(connection=key):
                attempt = {'created_at': NOW.isoformat(), 'remote_id': '123' if key.endswith('tistory') else 'remote'}
                matched = adapter.lookup(ctx(key), attempt)
                self.assertEqual(matched.outcome, 'matched')
                if key in self.google: self.google[key].remote['content'] = '다른 내용'
                else: self.drivers[key].remote['body_text'] = '다른 내용'
                changed = adapter.lookup(ctx(key), attempt)
                self.assertEqual(changed.outcome, 'ambiguous')
        # 제목 하나만 같은 후보는 신원으로 쓰지 않는다.
        key = 'dept.blogger'
        self.google[key].remote = {'id': 'remote', 'title': data['title'], 'blog': {'id': ctx(key).target_id}}
        result = adapters[key].lookup(ctx(key), {'created_at': NOW.isoformat()})
        self.assertEqual(result.outcome, 'unsupported')

    def test_actual_bridge_child_redeems_once_then_calls_tistory_leaf_and_fake_dom(self):
        # A2 실제 child/FD/잠금 fixture의 handler만 실제 A6 leaf로 교체한다.
        from tests.publishers.test_legacy_bridge import BridgeTests
        from common.publishers.blog_payloads import build_blog_payload
        fixture = BridgeTests('runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        leaf = """from common.publishers.blog_legacy import load_blog_leaf
from common.publishers.blog_services import BrowserBlogServices
from tests.publishers.test_blogs import FakeDriver
driver=FakeDriver('personal.tistory')
driver.identity={'authenticated':True,'login_subject':'subject','targets':[{'id':'t','url':'https://fixture.tistory.com/manage'}]}
driver.execute_result_target='t'
original=driver.execute_script
def execute(script,*args):
    result=original(script,*args)
    if 'AX_BLOG_SUBMIT_RESULT' in script:result['target_id']='t'
    return result
driver.execute_script=execute
services=BrowserBlogServices('personal.tistory',driver_factory=lambda profile:driver)
result=load_blog_leaf('personal.tistory').managed_submit(payload,{'platform':'tistory','target_id':'t','expected_login_subject':'subject'},services)
(ROOT/'mutations').write_text(json.dumps(driver.events,ensure_ascii=False))
return result"""
        from dataclasses import replace
        from common.operations.execution_catalog import ExecutionCatalog
        legacy_cwd = fixture.root / 'legacy'
        legacy_cwd.mkdir()
        bomb_marker = fixture.root / 'legacy-common-imported'
        (legacy_cwd / 'common.py').write_text('from pathlib import Path\nPath(' + repr(str(bomb_marker)) + ').write_text("bomb")\nraise RuntimeError("legacy common shadow")\n')
        fixture.spec = replace(fixture.spec, cwd=legacy_cwd)
        fixture.catalog = ExecutionCatalog({'fixture': fixture.spec})
        child_source = fixture.fixture_source(leaf=leaf.replace('\n','\n        '))
        child_source = child_source.replace("sys.executable,ROOT,'fixture_bridge'", "sys.executable,ROOT/'legacy','fixture_bridge'")
        fixture.module.write_text(child_source)
        permit = fixture.consumed()
        prepared = build_blog_payload('tistory', fixture.content, fixture.ctx)
        with fixture.held():
            result = fixture.bridge().submit('fixture', fixture.ctx, prepared, permit)
            with self.assertRaises(Exception):
                fixture.bridge().submit('fixture', fixture.ctx, prepared, permit)
        self.assertEqual(result['outcome'], 'submitted')
        self.assertEqual(result['remote_id'], '123')
        self.assertFalse(bomb_marker.exists())
        import json
        events = json.loads(fixture.marker.read_text())
        self.assertEqual(sum(event[0]=='script' and 'AX_BLOG_FINAL_PUBLISH' in event[1] for event in events), 1)
        self.assertTrue(any(event[0] == 'input' for event in events))

    def test_unconfirmed_target_never_opens_editor(self):
        adapters = self.components()
        for key, adapter in adapters.items():
            with self.subTest(connection=key):
                if key in self.google: self.google[key].target = 'other'
                else: self.drivers[key].identity['targets'] = []
                result = adapter.submit(ctx(key), adapter.prepare(ctx(key), {**snapshot(), 'assets': []}), object())
                self.assertEqual(result.outcome, 'failed')
        self.assertFalse(any(name == 'insert' for api in self.google.values() for name, _ in api.calls))
        self.assertFalse(any(event[0] == 'input' for driver in self.drivers.values() for event in driver.events))


if __name__ == '__main__': unittest.main()
