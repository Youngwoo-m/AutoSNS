"""prepare_managed_text_quota 시험. 가짜 native 없이 임시 RuntimeStore와 컴파일된 설정만 쓴다."""
from datetime import datetime, timezone
import json
import tempfile
import unittest

from common.operations.content_store import StoreError
from common.operations.models import Registry
from common.operations.production_quota import prepare_managed_text_quota
from common.operations.production_settings import METRIC, compile_production_settings
from common.operations.runtime_store import RuntimeStore

ACCOUNTS = {'personal': {'name': '개인'}, 'dept': {'name': '학과'}}
ON3 = {'enabled_preference': True, 'daily_limit': 3}
OFF = {'enabled_preference': False, 'daily_limit': None}
# 2026-11-02 12:00 KST. 로컬 창은 2026-11-02 00:00~24:00 KST.
NOW = datetime(2026, 11, 2, 3, 0, tzinfo=timezone.utc)
START = '2026-11-01T15:00:00+00:00'
END = '2026-11-02T15:00:00+00:00'


def rows(personal=OFF, dept=OFF, revision=1):
    base = {'applies_to': 'next_startup', 'execution_enabled': False, 'revision': revision}
    return [{**base, 'account_id': 'personal', **personal}, {**base, 'account_id': 'dept', **dept}]


def compiled(personal=OFF, dept=OFF, revision=1):
    return compile_production_settings(rows(personal, dept, revision), accounts=ACCOUNTS,
                                       code_root='/trusted/code', interpreter='/trusted/python').registry


def tweak(registry, change):
    data = registry.to_dict()
    change(data)
    return Registry(**data)


def requirement(data, account='personal'):
    job = data['jobs']['managed-text-' + account]
    return data['policies'][job['policy_revision']]['quota_requirements']


class ProductionQuotaTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = RuntimeStore(tmp.name)
        self.store.initialize()

    def snapshot(self):
        with self.store._db() as c:
            return {t: [tuple(r) for r in c.execute('SELECT * FROM %s ORDER BY id' % t)]
                    for t in ('quota_buckets', 'quota_productions', 'quota_reservations')}

    def prepare(self, registry, now=NOW):
        return prepare_managed_text_quota(self.store, registry, now)

    def sql(self, statement, params=()):
        with self.store._db(True) as c:
            c.execute(statement, params)

    def add_production(self, bucket, state, settled_at=None, amount=1, id=None):
        reqs = json.dumps([{'bucket_id': bucket, 'amount': amount}])
        self.sql('INSERT INTO quota_productions VALUES(?,?,?,?,?)',
                 (id or 'unit-%s-%s' % (state, settled_at), reqs, state, START, settled_at))

    def test_no_enabled_jobs_changes_nothing(self):
        disabled = compiled()
        before = self.snapshot()
        self.assertEqual(self.prepare(disabled), [])
        self.assertEqual(self.snapshot(), before)
        # 꺼진 job은 정책이 깨져 있어도 무시한다.
        broken = tweak(disabled, lambda d: d['policies'][d['jobs']['managed-text-dept']['policy_revision']]
                       .update(quota_requirements=[{'metric': 'other'}, {}]))
        self.assertEqual(self.prepare(broken), [])
        self.assertEqual(self.snapshot(), before)

    def test_new_local_window_starts_from_zero_baseline(self):
        result = self.prepare(compiled(personal=ON3))
        self.assertEqual(len(result), 1)
        bucket = result[0]
        self.assertEqual((bucket['owner_account_id'], bucket['metric']), ('personal', METRIC))
        self.assertEqual((bucket['capacity'], bucket['observed_usage'], bucket['reserved']), (3, 0, 0))
        self.assertEqual((bucket['observed_at'], bucket['expires_at']), (START, END))
        self.assertEqual((bucket['used'], bucket['remaining']), (0, 3))

    def test_held_and_settled_usage_in_window_is_preserved(self):
        bucket_id = self.prepare(compiled(personal=ON3))[0]['bucket_id']
        self.sql('DELETE FROM quota_buckets')
        self.add_production(bucket_id, 'held')
        self.add_production(bucket_id, 'settled', '2026-11-02T01:00:00+00:00')
        self.add_production(bucket_id, 'settled', '2026-11-01T14:00:00+00:00')  # 창 이전 정산은 제외
        self.add_production(bucket_id, 'released', '2026-11-02T01:00:00+00:00')
        result = self.prepare(compiled(personal=ON3))[0]
        self.assertEqual((result['observed_usage'], result['reserved'], result['remaining']), (0, 2, 1))

    def test_restart_is_idempotent(self):
        registry = compiled(personal=ON3, dept={'enabled_preference': True, 'daily_limit': 5})
        first = self.prepare(registry)
        before = self.snapshot()
        self.assertEqual([b['owner_account_id'] for b in first], ['dept', 'personal'])
        self.assertEqual(self.prepare(registry), first)
        self.assertEqual(self.snapshot(), before)

    def test_cap_change_updates_capacity_only(self):
        bucket_id = self.prepare(compiled(personal=ON3))[0]['bucket_id']
        self.add_production(bucket_id, 'held')
        self.sql('UPDATE quota_buckets SET observed_usage=1, observed_at=? WHERE id=?',
                 ('2026-11-02T00:00:00+00:00', bucket_id))
        before = self.snapshot()['quota_buckets'][0]
        result = self.prepare(compiled(personal={'enabled_preference': True, 'daily_limit': 7}, revision=2))[0]
        after = self.snapshot()['quota_buckets'][0]
        self.assertEqual(result['bucket_id'], bucket_id)
        self.assertEqual((after[2], after[3], after[4]), (before[2], before[3], before[4]))
        self.assertEqual((before[1], after[1]), (3.0, 7.0))
        self.assertEqual((result['capacity'], result['observed_usage'], result['reserved']), (7, 1, 1))

    def test_lower_cap_below_usage_does_not_reduce_usage(self):
        bucket_id = self.prepare(compiled(personal=ON3))[0]['bucket_id']
        for n in range(3):
            self.add_production(bucket_id, 'held', id='unit-%d' % n)
        result = self.prepare(compiled(personal={'enabled_preference': True, 'daily_limit': 1}, revision=2))[0]
        self.assertEqual((result['capacity'], result['reserved'], result['used'], result['remaining']), (1, 3, 3, 0))
        self.assertEqual(self.snapshot()['quota_buckets'][0][2], 0.0)

    def test_other_metric_and_other_window_buckets_are_untouched(self):
        self.sql('INSERT INTO quota_buckets VALUES(?,?,?,?,?)', ('external-api', 9, 4, START, END))
        self.sql('INSERT INTO quota_buckets VALUES(?,?,?,?,?)',
                 ('yesterday', 3, 2, '2026-10-31T15:00:00+00:00', START))
        before = {r[0]: r for r in self.snapshot()['quota_buckets']}
        self.prepare(compiled(personal=ON3))
        after = {r[0]: r for r in self.snapshot()['quota_buckets']}
        self.assertEqual(len(after), 3)
        for key in before:
            self.assertEqual(after[key], before[key])

    def test_bad_policy_is_rejected_before_any_write(self):
        base = compiled(personal=ON3, dept=ON3)
        job = lambda d, a='personal': d['jobs']['managed-text-' + a]
        req = lambda d, a='personal': requirement(d, a)[0]

        def duplicate_owner(d):
            d['jobs']['second'] = {**job(d, 'dept'), 'id': 'second', 'owner_account_id': 'personal'}

        def two_rows(d):
            requirement(d, 'dept').append(dict(req(d, 'dept')))

        cases = {
            'other_kind': lambda d: job(d).update(kind='publication'),
            'other_metric': lambda d: req(d, 'dept').update(metric='published_posts'),
            'duplicate_owner': duplicate_owner,
            'two_rows': two_rows,
            'no_rows': lambda d: requirement(d, 'dept').clear(),
            'wrong_scope': lambda d: req(d).update(scope_id='dept'),
            'not_subscription': lambda d: job(d, 'dept').update(subscription_only=False),
            'image_output': lambda d: job(d, 'dept').update(required_outputs=['text', 'image']),
            'bad_owner': lambda d: job(d, 'dept').update(owner_account_id='other'),
            'zero_limit': lambda d: req(d, 'dept').update(limit=0),
            'bool_limit': lambda d: req(d, 'dept').update(limit=True),
            'float_limit': lambda d: req(d, 'dept').update(limit=2.0),
            'amount_two': lambda d: req(d, 'dept').update(amount=2),
            'wrong_zone': lambda d: req(d, 'dept').update(timezone='UTC'),
            'extra_key': lambda d: req(d, 'dept').update(production_id='x'),
        }
        before = self.snapshot()
        for name, change in cases.items():
            with self.subTest(name), self.assertRaises(StoreError) as caught:
                self.prepare(tweak(base, change))
            self.assertEqual(caught.exception.code, 'invalid_quota_policy')
            self.assertEqual(self.snapshot(), before)

    def test_second_account_failure_rolls_back_first(self):
        self.prepare(compiled(personal=ON3))
        self.sql('UPDATE quota_buckets SET expires_at=?', ('2026-11-02T14:00:00+00:00',))
        before = self.snapshot()
        # dept가 먼저 INSERT되고 personal의 잘못된 expires_at에서 실패한다.
        with self.assertRaises(StoreError) as caught:
            self.prepare(compiled(personal=ON3, dept=ON3))
        self.assertEqual(caught.exception.code, 'invalid_quota_observation')
        self.assertEqual(self.snapshot(), before)

    def test_invalid_existing_bucket_fails_closed(self):
        bucket_id = self.prepare(compiled(personal=ON3))[0]['bucket_id']
        for column, value in (('observed_usage', -1), ('observed_at', '2026-11-01T14:00:00+00:00'),
                              ('observed_at', END), ('observed_at', 'garbage')):
            with self.subTest(column=column, value=value):
                self.sql('UPDATE quota_buckets SET observed_usage=0, observed_at=?, expires_at=? WHERE id=?',
                         (START, END, bucket_id))
                self.sql('UPDATE quota_buckets SET %s=? WHERE id=?' % column, (value, bucket_id))
                before = self.snapshot()
                with self.assertRaises(StoreError) as caught:
                    self.prepare(compiled(personal={'enabled_preference': True, 'daily_limit': 9}, revision=2))
                self.assertEqual(caught.exception.code, 'invalid_quota_observation')
                self.assertEqual(self.snapshot(), before)

    def test_corrupt_production_record_is_storage_error_and_rolls_back(self):
        self.sql("INSERT INTO quota_productions VALUES('broken','not json','held',?,NULL)", (START,))
        before = self.snapshot()
        with self.assertRaises(StoreError) as caught:
            self.prepare(compiled(personal=ON3))
        self.assertEqual(caught.exception.code, 'storage_error')
        self.assertEqual(self.snapshot(), before)

    def test_corrupt_negative_count_cannot_reduce_usage(self):
        registry=compiled(personal=ON3)
        bucket=self.prepare(registry)[0]['bucket_id']
        self.add_production(bucket,'held',amount=-1)
        before=self.snapshot()
        with self.assertRaises(StoreError):self.prepare(registry)
        self.assertEqual(before,self.snapshot())

    def test_invalid_inputs(self):
        registry = compiled(personal=ON3)
        for store, reg, now in ((self.store, registry, datetime(2026, 11, 2, 3, 0)), (self.store, registry, '2026-11-02T03:00:00Z'),
                                (self.store, registry.to_dict(), NOW), (object(), registry, NOW)):
            with self.subTest(now=now, reg=type(reg)), self.assertRaises(StoreError) as caught:
                prepare_managed_text_quota(store, reg, now)
            self.assertEqual(caught.exception.code, 'invalid')
        with tempfile.TemporaryDirectory() as tmp:  # 초기화하지 않은 store는 스스로 만들지 않는다.
            with self.assertRaises(StoreError) as caught:
                prepare_managed_text_quota(RuntimeStore(tmp), registry, NOW)
            self.assertEqual(caught.exception.code, 'storage_error')


if __name__ == '__main__':
    unittest.main()
