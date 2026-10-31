import unittest
from common.operations.metrics_normalization import normalize_metric_row

class NormalizationTests(unittest.TestCase):
    def row(self, value='0', **kwargs):
        return dict(platform='youtube', target_id='channel', remote_id='video', metric_name='views', value=value, observed_at='2026-01-01T00:00:00Z', basis='lifetime', **kwargs)

    def test_nan_bool_negative_fraction_and_null_not_zero(self):
        for value in ('NaN', 'Infinity', True, '-1', '1.5', '', None):
            result = normalize_metric_row(self.row(value))
            self.assertEqual(result.status, 'error')
            self.assertEqual(result.values, {})
        self.assertEqual(normalize_metric_row(self.row()).values, {'views': 0})

    def test_unknown_definition_and_interval(self):
        row = self.row(); row['metric_name'] = 'ctr'
        self.assertEqual(normalize_metric_row(row).status, 'unsupported')
        row = self.row(); row['basis'] = 'interval'
        self.assertEqual(normalize_metric_row(row).status, 'error')

    def test_complete_interval_and_forced_manual_source(self):
        row = self.row(); row.update(basis='interval', period_start='2026-01-01T00:00:00Z', period_end='2026-01-02T00:00:00Z', timezone='Asia/Seoul', source_kind='verified_delivery')
        result = normalize_metric_row(row)
        self.assertEqual(result.status, 'ok')
        self.assertEqual(result.definition_id, 'manual.csv.youtube.views.v1')
        self.assertNotIn('source_kind', result.source)

    def test_unsupported_definition_still_validates_value_time_and_period(self):
        base = self.row(); base['metric_name'] = 'ctr'
        for changes in ({'value': 'NaN'}, {'observed_at': 'not-a-time'}, {'basis': 'broken'},
                        {'basis': 'interval'}, {'basis': 'lifetime', 'period_start': '2026-01-01T00:00:00Z'},
                        {'basis': 'interval', 'period_start': '2026-01-02T00:00:00Z', 'period_end': '2026-01-01T00:00:00Z', 'timezone': 'UTC'}):
            with self.subTest(changes=changes):
                result = normalize_metric_row(dict(base, **changes))
                self.assertEqual(result.status, 'error'); self.assertEqual(result.values, {})
        for changes in ({}, {'basis': 'interval', 'period_start': '2026-01-01T00:00:00Z', 'period_end': '2026-01-02T00:00:00Z', 'timezone': 'UTC'}):
            result = normalize_metric_row(dict(base, **changes))
            self.assertEqual(result.status, 'unsupported'); self.assertEqual(result.values, {})
            self.assertEqual(result.basis, changes.get('basis', 'lifetime'))
            self.assertIsNotNone(result.observed_at)
