"""성과 저장은 운영 원장과 격리되고 관측은 변경하지 않는다."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from common.operations.content_store import ConflictError, StoreError


NOW = '2026-10-30T01:02:03+00:00'


def observation(**changes):
    row = dict(source_kind='verified_delivery', owner_account_id='personal',
               destination_account_id='dept', platform='youtube', connection_id='dept-yt',
               target_id='channel', remote_id='video', delivery_id='delivery-1',
               content_id='content-1', title='조회 관측', status='ok', values={'views': 0},
               observed_at=NOW, collected_at=NOW, file_mtime=None,
               definition_id='youtube.video.views.v1', basis='lifetime', period=None,
               source={'kind': 'test'}, uncertainties=[])
    row.update(changes)
    return row


class MetricsStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'managed'

    def store(self):
        from common.operations import metrics_store
        return metrics_store.MetricsStore(self.root)

    def test_contract_is_available(self):
        from common.operations import metrics_models
        self.assertTrue(hasattr(metrics_models, 'MetricObservation'))
        self.assertTrue(hasattr(self.store(), 'append_observation'))

    def test_constructor_and_gets_create_no_files(self):
        store = self.store()
        self.assertEqual(store.list_observations('all'), [])
        self.assertEqual(store.list_proposals('dept'), [])
        self.assertFalse(self.root.exists())
        with self.assertRaises(StoreError):
            store.append_observation(observation(), 'before-init')
        self.assertFalse(self.root.exists())

    def test_zero_preserved_and_error_unsupported_values_empty(self):
        store = self.store(); store.initialize()
        good = store.append_observation(observation(), 'zero')
        self.assertEqual(good['values'], {'views': 0})
        for status in ('error', 'unsupported'):
            saved = store.append_observation(observation(status=status, values={'views': 9}), status)
            self.assertEqual(saved['values'], {})
            self.assertEqual(saved['status'], status)

    def test_verified_ok_model_rejects_missing_observed_at(self):
        from common.operations.metrics_models import MetricObservation
        with self.assertRaises(StoreError) as caught:
            MetricObservation(**observation(observed_at=None))
        self.assertEqual(caught.exception.code, 'invalid')

    def test_verified_ok_append_rejects_missing_observed_at_without_write(self):
        store = self.store(); store.initialize()
        with self.assertRaises(StoreError) as caught:
            store.append_observation(observation(observed_at=None), 'missing-observed-at')
        self.assertEqual(caught.exception.code, 'invalid')
        self.assertEqual(store.list_observations(), [])

    def test_import_missing_success_observed_at_rolls_back_preceding_row(self):
        store = self.store(); store.initialize()
        existing = store.append_observation(observation(), 'existing')
        plan = {'preview_digest': 'missing-observed-at', 'observations': [
            {'observation_key': 'preceding', 'observation': observation(values={'views': 1})},
            {'observation_key': 'missing-observed-at', 'observation': observation(observed_at=None)},
        ]}
        with self.assertRaises(StoreError) as caught:
            store.import_rows(plan)
        self.assertEqual(caught.exception.code, 'invalid')
        self.assertEqual(self.store().list_observations(), [existing])

    def test_error_unsupported_and_legacy_keep_nullable_observed_at(self):
        from common.operations.metrics_models import MetricObservation
        store = self.store(); store.initialize()
        for status in ('error', 'unsupported', 'legacy_reported'):
            source_kind = 'legacy_reported' if status == 'legacy_reported' else 'verified_delivery'
            row = observation(source_kind=source_kind, status=status, observed_at=None)
            with self.subTest(status=status):
                self.assertIsNone(MetricObservation(**row).observed_at)
                saved = store.append_observation(row, status + '-null-time')
                self.assertIsNone(saved['observed_at'])

    def test_large_finite_integer_is_not_coerced_to_float(self):
        store = self.store(); store.initialize()
        integer = 10 ** 400
        saved = store.append_observation(observation(values={'views': integer}), 'large-int')
        self.assertEqual(saved['values']['views'], integer)

    def test_rejects_invalid_values_and_naive_times(self):
        store = self.store(); store.initialize()
        invalid = [dict(values={'views': x}) for x in (True, float('nan'), float('inf'), '0')]
        invalid += [dict(**{name: '2026-10-30T01:00:00'}) for name in ('observed_at', 'collected_at', 'file_mtime')]
        invalid += [dict(owner_account_id='unknown'), dict(destination_account_id=''), dict(status='not_collected')]
        for i, changes in enumerate(invalid):
            with self.subTest(changes=changes), self.assertRaises(StoreError):
                store.append_observation(observation(**changes), str(i))
        self.assertEqual(store.list_observations(), [])

    def test_interval_requires_ordered_timezone_aware_period(self):
        store = self.store(); store.initialize()
        periods = [None, {}, {'start': NOW, 'end': NOW, 'timezone': 'UTC'},
                   {'start': '2026-10-29T00:00:00', 'end': NOW, 'timezone': 'UTC'},
                   {'start': '2026-10-29T00:00:00Z', 'end': NOW},
                   {'start': '2026-10-29T00:00:00Z', 'end': NOW, 'timezone': 'Invalid/Nowhere'}]
        for i, period in enumerate(periods):
            with self.subTest(period=period), self.assertRaises(StoreError):
                store.append_observation(observation(basis='interval', period=period), str(i))
        period = {'start': '2026-10-29T00:00:00Z', 'end': NOW, 'timezone': 'Asia/Seoul'}
        saved = store.append_observation(observation(basis='interval', period=period), 'valid')
        self.assertEqual(saved['period']['start'], '2026-10-29T00:00:00+00:00')
        self.assertEqual(saved['period']['timezone'], 'Asia/Seoul')

    def test_same_key_replay_unchanged_and_changed_content_conflicts(self):
        store = self.store(); store.initialize()
        first = store.append_observation(observation(), 'one')
        self.assertEqual(store.append_observation(observation(), 'one'), first)
        with self.assertRaises(ConflictError):
            store.append_observation(observation(values={'views': 1}), 'one')
        self.assertEqual(store.list_observations(), [first])
        self.assertEqual(self.store().list_observations(), [first])

    def test_account_filter_includes_owner_and_destination_without_null_fallback(self):
        store = self.store(); store.initialize()
        dept = store.append_observation(observation(), 'dept')
        personal = store.append_observation(observation(destination_account_id='personal'), 'personal')
        unknown = store.append_observation(observation(source_kind='legacy_reported', status='legacy_reported',
                    destination_account_id=None, owner_account_id=None, uncertainties=['계정 식별 미확인']), 'unknown')
        self.assertEqual(store.list_observations('dept'), [dept])
        self.assertEqual(store.list_observations('personal'), [dept, personal])
        self.assertEqual(len(store.list_observations('all')), 3)
        self.assertIsNone(unknown['destination_account_id'])
        with self.assertRaises(StoreError): store.list_observations('unknown')

    def test_import_is_atomic_and_repeat_is_unchanged(self):
        store = self.store(); store.initialize()
        plan = {'preview_digest': 'digest-1', 'observations': [{'observation_key': 'one', 'observation': observation()},
                {'observation_key': 'two', 'observation': observation(values={'views': 2})}]}
        self.assertEqual(store.import_rows(plan), {'imported': 2, 'unchanged': 0, 'preview_digest': 'digest-1'})
        self.assertEqual(store.import_rows(plan), {'imported': 0, 'unchanged': 2, 'preview_digest': 'digest-1'})
        conflict = {'preview_digest': 'digest-2', 'observations': [{'observation_key': 'new', 'observation': observation()},
                    {'observation_key': 'one', 'observation': observation(values={'views': 99})}]}
        with self.assertRaises(ConflictError): store.import_rows(conflict)
        self.assertEqual(len(self.store().list_observations()), 2)

    def test_proposals_are_separate_drafts_and_idempotent_account_scoped(self):
        store = self.store(); store.initialize()
        dept = store.append_observation(observation(), 'dept')
        personal = store.append_observation(observation(owner_account_id='personal', destination_account_id='personal'), 'personal')
        proposal = store.save_proposal('dept', [dept['id']], '다음 주제', '메모', 'request')
        self.assertEqual(proposal['status'], 'draft')
        self.assertEqual(proposal['observation_ids'], [dept['id']])
        self.assertNotIn('content_id', proposal)
        owner_proposal = store.save_proposal('personal', [dept['id']], '원본 기획', '', 'owner')
        self.assertEqual(owner_proposal['account_id'], 'personal')
        self.assertEqual(store.save_proposal('dept', [dept['id']], '다음 주제', '메모', 'request'), proposal)
        with self.assertRaises(ConflictError):
            store.save_proposal('dept', [dept['id']], '다른 주제', '메모', 'request')
        for ids in ([personal['id']], ['missing'], []):
            with self.subTest(ids=ids), self.assertRaises(StoreError):
                store.save_proposal('dept', ids, '제안', '', 'bad-' + str(ids))
        self.assertEqual(store.list_proposals('personal'), [owner_proposal])
        self.assertEqual(self.store().list_proposals('dept'), [proposal])

    def test_operating_v3_ledger_bytes_untouched(self):
        from common.operations.database import initialize_database
        initialize_database(self.root)
        ledger = self.root / 'operations.sqlite3'
        before = hashlib.sha256(ledger.read_bytes()).hexdigest()
        store = self.store(); store.initialize()
        row = store.append_observation(observation(), 'safe')
        store.save_proposal('dept', [row['id']], '제안', '', 'safe')
        self.assertEqual(hashlib.sha256(ledger.read_bytes()).hexdigest(), before)
        with closing(sqlite3.connect(ledger)) as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], 3)

    def test_legacy_error_preserves_provenance_and_empties_values(self):
        store = self.store(); store.initialize()
        legacy = observation(source_kind='legacy_reported', status='error',
                             owner_account_id=None, destination_account_id=None, observed_at=None,
                             collected_at=None, uncertainties=['계정 미확인'])
        saved = store.append_observation(legacy, 'legacy-error')
        self.assertEqual(saved['source_kind'], 'legacy_reported')
        self.assertEqual(saved['status'], 'error')
        self.assertEqual(saved['values'], {})

    def test_legacy_unknown_collection_time_is_null_and_reimport_stable(self):
        store = self.store(); store.initialize()
        legacy = observation(source_kind='legacy_reported', status='legacy_reported',
                             owner_account_id=None, destination_account_id=None, observed_at=None,
                             collected_at=None, file_mtime=NOW, uncertainties=['수집 시각과 계정 미확인'])
        first = store.append_observation(legacy, 'legacy-time')
        self.assertIsNone(first['collected_at'])
        self.assertEqual(first['file_mtime'], NOW)
        self.assertEqual(store.append_observation(legacy, 'legacy-time'), first)

    def test_append_only_survives_direct_update_and_delete_attempts(self):
        store = self.store(); store.initialize()
        saved = store.append_observation(observation(), 'append-only')
        proposal = store.save_proposal('dept', [saved['id']], '제안', '', 'immutable')
        with closing(sqlite3.connect(store.path)) as conn:
            for table in ('observations', 'proposals'):
                for sql in (f"DELETE FROM {table}", f"UPDATE {table} SET payload='{{}}'"):
                    with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                        conn.execute(sql)
                    conn.rollback()
        self.assertEqual(store.list_observations(), [saved])
        self.assertEqual(store.list_proposals(), [proposal])

    def test_independent_writers_same_key_return_one_observation(self):
        first = self.store(); first.initialize()
        second = self.store(); second.initialize()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda store: store.append_observation(observation(), 'concurrent'), (first, second)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(self.store().list_observations(), [results[0]])

    def test_gets_of_existing_store_leave_database_bytes_unchanged(self):
        store = self.store(); store.initialize()
        store.append_observation(observation(), 'read-only')
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.iterdir()}
        reopened = self.store()
        reopened.list_observations('all'); reopened.list_proposals('all')
        after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.iterdir()}
        self.assertEqual(after, before)

    def test_metric_result_normalizes_error_and_requires_identity_for_ok(self):
        from common.operations.metrics_models import MetricResult
        args = dict(status='ok', values={'views': 0}, observed_at=NOW, remote_id='video',
                    target_id='channel', definition_id='views.v1', basis='lifetime', period=None, source={})
        self.assertEqual(MetricResult(**args).to_dict()['values'], {'views': 0})
        self.assertEqual(MetricResult(**dict(args, status='error')).to_dict()['values'], {})
        with self.assertRaises(StoreError): MetricResult(**dict(args, remote_id=None))

    def test_verified_identity_required_but_legacy_partial_identity_preserved(self):
        store = self.store(); store.initialize()
        for field in ('owner_account_id', 'destination_account_id', 'platform', 'connection_id',
                      'target_id', 'remote_id', 'delivery_id', 'content_id'):
            with self.subTest(field=field), self.assertRaises(StoreError):
                store.append_observation(observation(**{field: None}), field)
        legacy = observation(source_kind='legacy_reported', status='legacy_reported',
                             owner_account_id=None, destination_account_id=None, uncertainties=['소유 계정 미확인'])
        saved = store.append_observation(legacy, 'legacy')
        self.assertIsNone(saved['owner_account_id'])
        with self.assertRaises(StoreError): store.save_proposal('personal', [saved['id']], '불명', '', 'unknown')

    def test_model_freezes_input_and_serialization_returns_detached_data(self):
        from common.operations.metrics_models import MetricObservation
        source = observation()
        model = MetricObservation(**source)
        source['values']['views'] = 77
        self.assertEqual(model.to_dict()['values'], {'views': 0})
        copy = model.to_dict(); copy['values']['views'] = 88
        self.assertEqual(model.to_dict()['values'], {'views': 0})


if __name__ == '__main__':
    unittest.main()
