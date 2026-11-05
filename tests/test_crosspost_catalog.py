"""등록 규칙의 안전한 조회 요약 계약."""
from dataclasses import replace
import json
from pathlib import Path
import unittest

from common.operations.registry import load_registry

ROOT = Path(__file__).resolve().parents[1]


class CrosspostCatalogTests(unittest.TestCase):
    def registry(self):
        return load_registry(ROOT / 'ax-console/config/operations.json')

    def test_registered_routes_and_related_scope(self):
        from common.operations.crosspost_catalog import crosspost_catalog
        registry = self.registry()
        rows = crosspost_catalog(registry)
        self.assertEqual(len(rows), 23)
        self.assertEqual(len({row['id'] for row in rows}), 23)
        for account in ('dept', 'personal'):
            scoped = crosspost_catalog(registry, account)
            self.assertEqual(scoped, [r for r in rows if account in (r['owner_account_id'], r['destination_account_id'])])
        row = next(r for r in rows if r['id'] == 'geoai-short.tiktok')
        self.assertEqual((row['source_channel'], row['destination_channel']), ('youtube', 'tiktok'))
        self.assertIn('1800秒'.replace('秒', '초'), row['condition'])
        self.assertIn('기존 실행기 담당', row['activation_summary'])
        self.assertFalse(row['execution_enabled'])

    def test_unknown_metadata_never_serialized(self):
        from common.operations.crosspost_catalog import crosspost_catalog
        registry = self.registry()
        rule = dict(next(iter(registry.crossposts.values())))
        secret = '/Users/private/token-SECRET'
        rule.update(conditions={'field': 'arbitrary', 'value': secret}, config={'secret': secret},
                    activation_evidence=[{'kind': 'config', 'key': secret, 'value': secret},
                        {'kind': 'code', 'path': secret}, {'kind': 'arbitrary', 'value': secret}])
        rows = crosspost_catalog(replace(registry, crossposts={'test': rule}))
        serialized = json.dumps(rows, ensure_ascii=False)
        self.assertNotIn(secret, serialized)
        self.assertIn('추가 실행기 조건 확인 필요', serialized)
        self.assertNotIn('credential_ref', serialized)
        self.assertNotIn('profile_ref', serialized)


if __name__ == '__main__': unittest.main()
