import unittest
from common.operations.models import ContractError
from common.operations.schedule_time import normalize_schedule

class ScheduleTimeTests(unittest.TestCase):
    def test_normalizes_aware_iana_and_fixed_utc(self):
        self.assertEqual(normalize_schedule('2026-10-30T09:00:00+09:00'), '2026-10-30T00:00:00+00:00')
        self.assertEqual(normalize_schedule('2026-10-30T00:00:00Z', 'UTC'), '2026-10-30T00:00:00+00:00')

    def test_rejects_naive_wrong_offset_invalid_zone_and_dst(self):
        for value, zone in [('2026-10-30T09:00:00', 'Asia/Seoul'),
            ('2026-10-30T09:00:00+00:00', 'Asia/Seoul'),
            ('2026-10-30T09:00:00+09:00', 'No/SuchZone'),
            ('2026-11-01T01:30:00-04:00', 'America/New_York'),
            ('2026-03-08T02:30:00-05:00', 'America/New_York')]:
            with self.subTest(value=value):
                with self.assertRaises(ContractError) as caught:
                    normalize_schedule(value, zone)
                self.assertEqual(caught.exception.code, 'invalid_schedule')
