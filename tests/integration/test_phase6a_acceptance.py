"""6A 오프라인 수락: 실제 저장소/관문과 격리한 legacy 순수 구간만 실행한다.

legacy 모듈 import, main/upload, 프로필/키/운영 큐 접근은 없다. AST는 고정 저장소
파일의 지정 함수/실패절만 추출한다. 관리 TikTok 실행기 수락은 6B에 남긴다.
"""
import ast
import copy
from contextlib import closing
from dataclasses import replace
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from common.operations.content_store import ContentStore
from common.operations.crossposts import preview_crossposts, crosspost_intents, earliest_post_time
from common.operations.models import Connection, Registry, thaw
from common.operations.registry import load_registry
from common.operations.runtime_models import ExecutionPolicy, SubmissionResult, LookupResult, VerificationResult
from common.operations.runtime_store import RuntimeStore
from common.operations.production_store import ProductionStore
from common.operations.ledger import Ledger
from common.operations.execution_catalog import ExecutionCatalog
from common.operations.execution_service import ExecutionService
from common.operations.worker_service import WorkerService
from common.operations.quota import bucket_id, quota_window, reserve_quota
from common.shared.axlock import AxLock, LockPaths
from tests.operations.production_fixture import produce_reviewed_fixture

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / 'tests/integration/fixtures/phase6a-crosspost-events.json'
QUEUE_PATH = ROOT / 'dept/youtube-shorts-auto/tiktok_queue.py'
NOW = dt.datetime(2026, 10, 30, 12, tzinfo=dt.timezone.utc)


def _fixture():
    return json.loads(FIXTURE_PATH.read_text(encoding='utf-8'))


def _tree(path):
    # 경로는 시험 코드의 고정값이다. 실행될 파일을 fixture/HTTP가 선택하지 않는다.
    return ast.parse(path.read_text(encoding='utf-8'), filename=str(path))


def _pure_functions(path, names, environment):
    nodes = [copy.deepcopy(node) for node in _tree(path).body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    if {node.name for node in nodes} != set(names):
        raise AssertionError('고정 순수 함수가 없음')
    for node in nodes:
        if any(isinstance(item, (ast.Import, ast.ImportFrom, ast.Global)) for item in ast.walk(node)):
            raise AssertionError('순수 함수에 import/global이 추가됨')
    namespace = dict(environment)
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(path), 'exec'), namespace)
    return namespace


def _legacy_queue():
    constants = {}
    for node in _tree(QUEUE_PATH).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            key = node.targets[0].id
            if key in ('MAX_AGE_DAYS', 'MAX_TRIES', 'DELAY_MIN', 'GAP_HOURS', 'GAP_FRESH_HOURS', 'HOURS'):
                constants[key] = ast.literal_eval(node.value)
    return _pure_functions(QUEUE_PATH, ('pick',), dict(constants, dt=dt,
        os=SimpleNamespace(path=SimpleNamespace(exists=lambda path: Path(path).is_file()))))


def _legacy_failure(entry, error, when):
    main = next(node for node in _tree(QUEUE_PATH).body if isinstance(node, ast.FunctionDef) and node.name == 'main')
    handler = next(node for node in ast.walk(main) if isinstance(node, ast.ExceptHandler)
                   and isinstance(node.type, ast.Name) and node.type.id == 'BaseException')
    # upload가 포함된 try 본문은 컴파일하지 않고 except의 상태 전이만 추출한다.
    function = ast.parse('def apply(e, q, ex):\n    pass\n').body[0]
    function.body = copy.deepcopy(handler.body)
    if any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(function)):
        raise AssertionError('실패절 import 거부')
    class Clock(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return when
    saved = []
    environment = dict(dt=SimpleNamespace(datetime=Clock, timedelta=dt.timedelta),
                       _save=lambda queue: saved.append(copy.deepcopy(queue)), log=lambda message: None,
                       os=SimpleNamespace(path=SimpleNamespace(basename=lambda path: Path(path).name)), MAX_TRIES=5)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), str(QUEUE_PATH), 'exec'), environment)
    environment['apply'](entry, [entry], error)
    return saved


def _legacy_delay(source):
    add = next(node for node in _tree(QUEUE_PATH).body if isinstance(node, ast.FunctionDef) and node.name == 'add')
    value = next(value for node in ast.walk(add) if isinstance(node, ast.Dict)
                 for key, value in zip(node.keys, node.values)
                 if isinstance(key, ast.Constant) and key.value == 'not_before')
    return eval(compile(ast.Expression(body=value), str(QUEUE_PATH), 'eval'), dict(dt=dt, not_before=source, DELAY_MIN=30))


def _legacy_candidates(event):
    """감사표/legacy caller의 분기에서 독립 추출한 predicate. 등록부 조건을 읽지 않는다.

    URL/파일/업로드 성공은 정규화 사건의 관측값이다. 원격 성공으로 꾸미지 않는다.
    """
    source, owner = event.get('source_connection_id'), event.get('owner_account_id')
    phase, caller = event.get('phase'), event.get('caller')
    found = set()
    if source == 'personal.youtube' and owner == 'personal':
        if caller == 'geoai_short' and phase in ('uploaded', 'scheduled', 'published') and event.get('upload_response') is True and event.get('channel_ok') is True:
            found.add('geoai-short.tiktok')
    if source in ('personal.youtube', 'dept.youtube') and owner == source.split('.')[0]:
        if caller == 'youtube_upload' and phase == 'uploaded' and event.get('video_id_present') is True and event.get('visibility') == 'public' and isinstance(event.get('description'), str) and '쿠팡' not in event['description']:
            found.add('youtube-generic-' + owner + '.tiktok')
    if source == 'personal.blogger' and owner == 'personal':
        if event.get('slot') in ('morning', 'evening') and (event.get('blogger_status') == 'published' or event.get('dry_run') is True):
            found.add('geoai.community')
            if event.get('no_video') is True or event.get('threads') is True:
                found.add('geoai.threads')
        if phase == 'published' and event.get('tistory_explicit_disabled') is False:
            found.add('blogger.tistory')
    if source == 'dept.naver_blog' and owner == 'dept' and phase == 'published':
        if caller == 'naver_weekly':
            found.add('naver.blogger')
        if (caller == 'jobs' and event.get('naver_success') is True
                and event.get('draft_age_seconds', 999999) <= 21600
                and event.get('naver_posted_job_count', 0) >= 1 and event.get('valid_job_count', 0) >= 3):
            found.add('jobs.tistory')
    if source == 'personal.tistory' and owner == 'personal' and phase == 'published':
        if (event.get('public_verified') is True and event.get('subject_area') in ('survey', 'civil', 'building', 'safety', 'nordic', 'safekorea')
                and event.get('shorts_only') is False and event.get('department_round') is False):
            found.add('tistory.safeworking')
    if source == 'dept.youtube' and owner == 'dept':
        if phase == 'published' and caller == 'weekly_news' and event.get('youtube_success') is True:
            found.update(('news.naver_blog', 'news.threads', 'news.x'))
            if event.get('made_anchor') is True:
                found.add('news.instagram')
            if event.get('tiktok_enabled') is True:
                found.add('news.tiktok')
        if phase == 'published' and caller == 'publish_career' and event.get('youtube_success') is True:
            found.update(('career.tiktok', 'career.x'))
            if event.get('no_ig') is False:
                found.add('career.instagram')
            if event.get('no_threads') is False:
                found.add('career.threads')
        if phase in ('scheduled', 'uploaded') and caller == 'disaster_publish' and event.get('upload_response') is True:
            found.add('disaster.tiktok')
        if phase == 'published' and caller == 'disaster' and 'target_previous_state' in event and event['target_previous_state'] not in ('published', 'shared_unconfirmed'):
            found.update(('disaster.instagram', 'disaster.blogger', 'disaster.naver_blog', 'disaster.threads'))
    return found


class LegacyCrosspostAcceptanceTests(unittest.TestCase):
    def test_all_23_rules_and_disabled_unknown_preserved(self):
        fixture = _fixture()
        registry = load_registry(ROOT / 'ax-console/config/operations.json')
        rules = {row['id']: row for row in fixture['rules']}
        covered = set()
        for case in fixture['events']:
            with self.subTest(event=case['id']):
                expected = _legacy_candidates(case['event'])
                self.assertEqual(set(case['expected_eligible_rules']), expected)
                rows = preview_crossposts(case['event'], registry)
                self.assertEqual(expected, {row['rule_id'] for row in rows if row['eligible']})
                self.assertEqual((), crosspost_intents(case['event'], registry))
                for row in rows:
                    rule = rules[row['rule_id']]
                    for field in ('owner_account_id', 'source_connection_id', 'destination_connection_id',
                                  'delivery_owner', 'delay_owner', 'delay_seconds', 'min_gap_seconds',
                                  'allowed_slots', 'conditions', 'trigger', 'transform_id'):
                        self.assertEqual(rule[field], row[field], field)
                    self.assertEqual(case['event']['content_id'], row['content_id'])
                    self.assertEqual(case['event']['revision'], row['revision'])
                    self.assertEqual(registry.connections[row['connection_id']].account_id, row['destination_account_id'])
                    self.assertFalse(row['execution_enabled'])
                    if row['eligible']:
                        state = 'disabled' if rule['enabled'] is False else 'unknown' if rule['enabled'] is None else 'observe_legacy'
                        self.assertEqual(state, row['status'])
                    if rule['delay_owner'] == 'legacy_queue_add':
                        # 동일 source 회차의 queue_add 실제 식과 관리 관측시각 비교. 추가 enqueue는 0.
                        expected_time = dt.datetime.fromisoformat(_legacy_delay(case['event']['source_public_at'])).astimezone(dt.timezone.utc)
                        self.assertEqual(expected_time, dt.datetime.fromisoformat(row['not_before']))
                covered.update(expected)
        self.assertEqual(set(rules), covered)
        self.assertEqual(23, len(covered))
        self.assertEqual(17, sum(row['enabled'] is None for row in rules.values()))
        self.assertIs(rules['news.tiktok']['enabled'], False)

    def test_all_18_legacy_queue_cases_execute_with_temp_video_only(self):
        fixture = _fixture()
        pick = _legacy_queue()['pick']
        with tempfile.TemporaryDirectory() as directory:
            existing = Path(directory) / 'video.mp4'
            existing.write_bytes(b'fixture-video-not-uploaded')
            for case in fixture['tiktok_queue_cases']:
                with self.subTest(case=case['id']):
                    entries = [dict(fixture['tiktok_queue_entry_defaults'], **case.get('overrides', {}))]
                    entries += [dict(fixture['tiktok_queue_entry_defaults'], **extra) for extra in case.get('extra_entries', [])]
                    for entry in entries:
                        entry['video'] = str(existing if entry.pop('video_exists', True) else Path(directory) / 'missing.mp4')
                    if case.get('last_posted_at'):
                        entries.append(dict(fixture['tiktok_queue_entry_defaults'], id='last-posted', video=str(existing), posted={'at': case['last_posted_at']}))
                    before = copy.deepcopy(entries)
                    selected, _ = pick(entries, dt.datetime.fromisoformat(case['now']))
                    self.assertEqual(case['expected_selected'], selected['id'] if selected else None)
                    self.assertEqual(before, entries)
        self.assertEqual(18, len(fixture['tiktok_queue_cases']))

    def test_all_3_failure_policies_execute_without_upload_or_queue_save(self):
        for case in _fixture()['tiktok_failure_cases']:
            names = case.get('exceptions', [case.get('exception')])
            if 'message_substring' in case:
                names = names + ['RuntimeError']
            for name in names:
                with self.subTest(case=case['id'], exception=name):
                    error_type = type(name, (Exception,), {})
                    message = case.get('message', case.get('message_substring', 'fixture infrastructure'))
                    entry = dict(video='fixture.mp4', tries=case['tries_before'],
                                 fail_streak=case.get('fail_streak_before', 0), last_fail=case.get('last_fail'))
                    saved = _legacy_failure(entry, error_type(message), dt.datetime.fromisoformat(case.get('now', '2026-10-30T12:00:00')))
                    self.assertEqual(case['expected_tries'], entry['tries'])
                    self.assertEqual(case.get('expected_hold_until'), entry.get('hold_until'))
                    if 'expected_fail_streak' in case:
                        self.assertEqual(case['expected_fail_streak'], entry['fail_streak'])
                    self.assertEqual(0 if case['id'].startswith('infrastructure') else 1, len(saved))

    def test_legacy_transform_tags_ai_notice_and_source_are_executed(self):
        # API/모델을 호출하는 make_caption은 제외하고 순수 fallback + 실제 후처리 AST만 실행.
        tree = _tree(QUEUE_PATH)
        nodes = [copy.deepcopy(node) for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in ('_fallback_caption', 'make_caption')]
        caption = next(node for node in nodes if node.name == 'make_caption')
        caption.body = [node for node in caption.body if not isinstance(node, ast.Try)]
        environment = dict(re=re, CROSS_LINE=_fixture()['tiktok_caption_contract']['cross_line'], log=lambda message: None)
        exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(QUEUE_PATH), 'exec'), environment)
        entry = dict(title='안전 O·X #Shorts | 학과', description='첫 번째 문장. 다음 문장.', hashtags=['shorts', '안전', '세명대학교'],
                     notice='광고 고지 보존', ai_generated=True, ai_voice=True)
        # queue_add의 Shorts 제외는 실제 add dict 식에서 별도 검증한다.
        add = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'add')
        tags = next(value for node in ast.walk(add) if isinstance(node, ast.Dict) for key, value in zip(node.keys, node.values)
                    if isinstance(key, ast.Constant) and key.value == 'hashtags')
        entry['hashtags'] = eval(compile(ast.Expression(body=tags), str(QUEUE_PATH), 'eval'), dict(hashtags=entry['hashtags']))
        text = environment['make_caption'](entry, {'fixture': True})
        self.assertNotIn('#Shorts', text)
        self.assertNotIn('#shorts', text)
        self.assertIn('광고 고지 보존', text)
        self.assertIn('※ 영상의 목소리는 AI로 합성한 음성입니다.', text)
        self.assertTrue(text.endswith('#안전 #재난안전학과 #제천'))
        self.assertLess(text.index('광고 고지 보존'), text.rindex('#안전'))
        entry['ai_voice'] = False
        self.assertIn('※ 진행자 모습과 목소리는 AI로 합성한 아바타입니다.', environment['make_caption'](entry, {'fixture': True}))
        self.assertIn(_fixture()['tiktok_caption_contract']['cross_line'], text)
        career = _pure_functions(ROOT / 'dept/youtube-shorts-auto/publish_career.py', ('_threads_text', '_ig_caption'), {'re': re})
        episode = dict(title='진로 #Shorts', description='요약\n#태그', tags=['shorts', '안전', '진로', '1', '2', '3', '4'])
        self.assertEqual('진로\n\n요약\n\n▶ https://example.invalid/source\n\n#안전 #진로 #1 #2 #3', career['_threads_text'](episode, 'https://example.invalid/source'))
        self.assertEqual('요약', career['_ig_caption'](episode))
        disaster = _pure_functions(ROOT / 'dept/disaster-shorts/tools/crosspost.py', ('texts',), {})
        caption, tags, thread = disaster['texts'](dict(type='화재', title='대피', scenes=[{'narration': '계단으로'}]), 'https://example.invalid/source')
        self.assertIn('출처: 행정안전부 국민안전24', caption)
        self.assertIn('※ AI 아바타·AI 생성 재현 영상', caption)
        self.assertEqual(5, len(tags))
        self.assertEqual('대피\n\n✔ 계단으로\n\n▶ https://example.invalid/source\n#화재', thread)


class _Remote:
    def __init__(self, now, *, lose_response=False):
        self.now = now
        self.lose_response = lose_response
        self.submissions = []
        self.remote = {}
        self.reads = []

    def inspect_target(self, context):
        self.reads.append(context.connection_id)
        return dict(platform=context.platform, target_id=context.target_id, authenticated=True,
                    login_subject='fixture-subject', verification_method='fixture-only',
                    checked_at=self.now().isoformat(), expires_at=(self.now() + dt.timedelta(hours=1)).isoformat())

    def prepare(self, context, snapshot):
        return dict(body_sha256=hashlib.sha256(snapshot['original'].encode()).hexdigest(), media_sha256=[])

    def submit(self, context, prepared, permit):
        self.submissions.append(context.connection_id)
        value = dict(prepared, remote_id='fixture-remote-' + str(len(self.remote)), target_id=context.target_id,
                     destination_account_id=context.destination_account_id, created_at=(self.now() + dt.timedelta(seconds=1)).isoformat(), visibility='public')
        self.remote[permit.attempt_id] = value
        if self.lose_response:
            raise TimeoutError('fixture remote accepted, response lost')
        return SubmissionResult('submitted', remote_id=value['remote_id'])

    def lookup(self, context, attempt):
        value = self.remote.get(attempt['id']) if attempt else None
        return LookupResult('matched' if value else 'not_found', [value] if value else [])

    def verify(self, context, remote_id, snapshot):
        value = next(row for row in self.remote.values() if row['remote_id'] == remote_id)
        return VerificationResult('verified', self.now(), value)


class RuntimeAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = NOW
        self.content = ContentStore(self.root / 'managed')
        self.content.initialize()
        snapshot = self.content.create('personal', dict(title='통합 fixture 원고', kind='article', original='출처가 있는 본문'))
        connections = {
            'personal.blogger': Connection('personal.blogger', 'personal', 'blogger', target_id='fixture-blog', profile_ref='personal', enabled=True, expected_login_subject='fixture-subject'),
            'dept.youtube': Connection('dept.youtube', 'dept', 'youtube', target_id='fixture-channel', profile_ref='dept', enabled=True, expected_login_subject='fixture-subject')}
        policies = {}
        jobs = {}
        for job, connection, policy in [('blog', 'personal.blogger', 'p'), ('youtube', 'dept.youtube', 'p2')]:
            requirements = [dict(scope_kind=kind, scope_id=scope, metric='posts', window_kind='day', timezone='UTC', amount=1, limit=10)
                            for kind, scope in [('target', connections[connection].target_id), ('api', 'fixture-api-' + job), ('owner', 'personal')]]
            policies[policy] = dict(subscription_only=True, review_authorities={'reviewer': ['source']}, quota_requirements=requirements)
            jobs[job] = dict(id=job, enabled=True, execution_owner='managed', schedule_owner='console', owner_account_id='personal', connection_id=connection, policy_revision=policy)
        registry = Registry('fixture-r', {'personal': {}, 'dept': {}}, {},
            {'personal': {'account_id': 'personal', 'lock_resource': 'profile:tistory'}, 'dept': {'account_id': 'dept', 'lock_resource': 'profile:youtube-dept'}},
            connections, jobs, policies,
            {'fixture-cross-account': dict(id='fixture-cross-account', enabled=True, owner_account_id='personal', source_connection_id='personal.blogger', destination_connection_id='dept.youtube')})
        self.policy = ExecutionPolicy(True, tuple(connections), 'fixture-only', {'subscription_only': True})
        self.store = RuntimeStore(self.content.root, registry, self.content)
        self.store.initialize()
        self.locks = AxLock(LockPaths.from_root(self.root / 'source'), process_probe=lambda resource: False)
        self.store.locks = self.locks
        self.store.execution_policy = self.policy
        # 실제 A5 제작→독립 source review→immutable output link를 소비한다.
        from tests.operations.production_fixture import _FixtureProvider
        generate = _FixtureProvider.generate
        self.model_requests = []
        def observe_generate(provider, request, prompt, policy):
            self.model_requests.append(request)
            return generate(provider, request, prompt, policy)
        with patch.object(_FixtureProvider, 'generate', observe_generate):
            self.made = produce_reviewed_fixture(self.content, self.store, registry, snapshot, self.now)
        self.registry = self.made['registry']
        self.snapshot = self.made['snapshot']
        self.production = self.made['production_store']
        self.remotes = {key: _Remote(lambda: self.now) for key in connections}
        self.runs = {}

    def service(self, *, reopen=False, policy=None):
        if reopen:
            self.content = ContentStore(self.content.root)
            self.store = RuntimeStore(self.content.root, self.registry, self.content)
            self.store.initialize()
            self.production = ProductionStore(self.content.root, registry=self.registry)
            self.production.initialize()
        ledger = Ledger(self.content.root, self.registry, self.content)
        return ExecutionService(self.store, ledger, self.registry, ExecutionCatalog(), policy or self.policy,
                                self.remotes, {}, self.production, self.locks, lambda: self.now)

    def plan(self, service, connection, identifier):
        job = 'blog' if connection == 'personal.blogger' else 'youtube'
        run = self.store.submit_occurrence(dict(job_id=job, scheduled_at_utc=self.now.isoformat(), phase='submit',
                                                source='console', request_kind='new_publication', mode='live'))['id']
        self.runs[identifier] = run
        plan = dict(id=identifier, content_id=self.snapshot['id'], revision=self.snapshot['revision'], manifest_hash=self.snapshot['manifest_hash'],
                    owner_account_id='personal', destination_account_id=self.registry.connections[connection].account_id,
                    connection_id=connection, publication_purpose='initial', schedule_slot=identifier, options={},
                    schedule_condition={'kind': 'fixed', 'at': self.now.isoformat()}, status='ready', version=1)
        with closing(sqlite3.connect(self.content.root / 'operations.sqlite3')) as db:
            db.execute('INSERT INTO deliveries VALUES(?,?,?,?,?,?,?,?)', (identifier, self.snapshot['id'], self.snapshot['revision'], connection, 'initial', identifier, 'fixture-plan-hash', json.dumps(plan)))
            db.commit()
        observed = service.observe(identifier, run, 1)
        delivery = service.admit(identifier, run, 1, observed['id'])
        return delivery

    def approve(self, service, delivery):
        return service.approve(delivery['id'], delivery['version'], delivery['context_hash'], 'fixture-approve:' + delivery['id'], 'fixture-user')

    def observe_budgets(self):
        for policy in self.registry.policies.values():
            for requirement in policy['quota_requirements']:
                if requirement['scope_kind'] == 'owner':
                    continue
                start, end = quota_window(requirement, self.now)
                self.store.observe_bucket(bucket_id(requirement['scope_kind'], requirement['scope_id'], requirement['metric'], start, end), requirement['limit'], 0, self.now, end)

    def tick(self, service):
        return WorkerService(service, clock=lambda: self.now, stop_event=threading.Event()).tick()

    def test_subscription_production_to_blog_and_youtube_without_publish_authority(self):
        service = self.service()
        blog = self.plan(service, 'personal.blogger', 'blog-delivery')
        video = self.plan(service, 'dept.youtube', 'youtube-delivery')
        result = self.tick(service)
        self.assertEqual('blocked', result['state'])
        self.assertEqual([], [call for remote in self.remotes.values() for call in remote.submissions])
        self.assertIsNone(self.store.get_publication_approval(blog['id']))
        self.assertIsNone(self.store.get_publication_approval(video['id']))
        self.assertEqual(1, len(self.store.list_productions()))
        self.assertEqual(self.made['unit_id'], self.store.get_production_for_output(self.snapshot['id'], self.snapshot['revision'], self.snapshot['manifest_hash'])['production_id'])
        self.assertIsNone(self.production.get(self.made['unit_id'])['result']['observed_usage'])
        self.assertEqual(2, len(self.model_requests))  # 제작 1회 + 독립 source review 1회
        for request in self.model_requests:
            self.assertEqual(('text',), request.required_outputs)
            self.assertFalse(any(hasattr(request, name) for name in ('connection_id', 'permit', 'profile', 'credential', 'adapter', 'runtime_store')))

    def test_cross_account_delivery_does_not_reproduce_content(self):
        service = self.service()
        one = self.plan(service, 'personal.blogger', 'blog-delivery')
        two = self.plan(service, 'dept.youtube', 'youtube-delivery')
        self.approve(service, one)
        self.approve(service, two)
        self.observe_budgets()
        self.tick(service)
        self.tick(service)
        self.assertEqual(1, len(self.remotes['personal.blogger'].submissions))
        self.assertEqual(1, len(self.remotes['dept.youtube'].submissions))
        self.assertEqual('personal', self.store.get_delivery(two['id'])['context']['owner_account_id'])
        self.assertEqual('dept', self.store.get_delivery(two['id'])['context']['destination_account_id'])
        for identifier in (one['id'], two['id']):
            attempt = self.store.attempts(identifier)[0]
            self.assertEqual([self.made['unit_id']], self.store.get_reservation(attempt['reservation_id'])['production_ids'])
        self.assertEqual(1, len(self.store.list_productions()))
        self.assertEqual('settled', self.store.get_production(self.made['unit_id'])['state'])

    def test_next_day_delivery_reuses_one_production_charge(self):
        self.now += dt.timedelta(days=1)
        service = self.service(reopen=True)
        delivery = self.plan(service, 'dept.youtube', 'next-day-youtube')
        self.approve(service, delivery)
        self.observe_budgets()
        self.tick(service)
        self.assertEqual(1, len(self.store.list_productions()))
        self.assertEqual(1, len(self.remotes['dept.youtube'].submissions))
        owner_buckets = [row for row in self.store.quota_buckets() if row['id'] in [req['bucket_id'] for req in self.store.get_production(self.made['unit_id'])['requirements']]]
        self.assertEqual(1, len(owner_buckets))
        self.assertEqual(1, owner_buckets[0]['reserved'])

    def test_remote_success_lost_response_reopen_no_duplicate(self):
        service = self.service()
        blog = self.plan(service, 'personal.blogger', 'blog-delivery')
        video = self.plan(service, 'dept.youtube', 'youtube-delivery')
        self.approve(service, blog)
        self.approve(service, video)
        self.observe_budgets()
        self.remotes['dept.youtube'].lose_response = True
        self.tick(service)
        self.tick(service)
        self.assertEqual('unknown', self.store.get_delivery(video['id'])['state'])
        self.assertEqual('uploaded', self.store.get_delivery(blog['id'])['state'])
        old_attempt = self.store.attempts(video['id'])[0]
        self.assertEqual('held', self.store.get_reservation(old_attempt['reservation_id'])['state'])
        self.now += dt.timedelta(seconds=2)
        reopened = self.service(reopen=True)
        self.tick(reopened)
        current = self.store.get_delivery(video['id'])
        reopened.reconcile(video['id'], expected_version=current['version'], request_key='fixture-reconcile')
        current = self.store.get_delivery(video['id'])
        reopened.verify(video['id'], expected_version=current['version'])
        current_blog = self.store.get_delivery(blog['id'])
        reopened.verify(blog['id'], expected_version=current_blog['version'])
        self.assertEqual('verified', self.store.get_delivery(video['id'])['state'])
        self.assertEqual('verified', self.store.get_delivery(blog['id'])['state'])
        self.assertEqual(1, len(self.remotes['personal.blogger'].submissions))
        self.assertEqual(1, len(self.remotes['dept.youtube'].submissions))
        self.assertEqual(1, len(self.store.attempts(video['id'])))
        self.assertEqual(1, len(self.store.list_productions()))

    def test_default_offline_worker_starts_no_external_io_or_db_writes(self):
        service = self.service(policy=ExecutionPolicy())
        before = (self.content.root / 'operations.sqlite3').read_bytes()
        result = self.tick(service)
        self.assertEqual('disabled', result['state'])
        self.assertEqual(before, (self.content.root / 'operations.sqlite3').read_bytes())
        self.assertEqual([], [read for remote in self.remotes.values() for read in remote.reads])
        self.assertEqual([], [call for remote in self.remotes.values() for call in remote.submissions])


class CutoverAcceptanceTests(unittest.TestCase):
    def test_legacy_side_effects_block_cutover(self):
        from common.operations.cutover import assess_cutover
        registry = load_registry(ROOT / 'ax-console/config/operations.json')
        inventory = json.loads((ROOT / 'docs/runbooks/execution-entrypoint-inventory.json').read_text())
        result = assess_cutover(None, 'geoai.daily', {'production_ready': True, 'legacy_side_effects': False}, registry=registry, inventory=inventory)
        self.assertFalse(result['production_ready'])
        self.assertIn('production:entrypoint_inventory_incomplete', result['blockers'])

    def test_incomplete_live_evidence_keeps_production_false(self):
        from common.tools.check_operations_release import check_release
        result = check_release({'live_auth_evidence': [], 'live_publish_evidence': []})
        self.assertFalse(result['production_ready'])
        self.assertIn('production:live_auth_evidence_missing', result['blockers'])
        self.assertIn('production:live_publish_evidence_missing', result['blockers'])
