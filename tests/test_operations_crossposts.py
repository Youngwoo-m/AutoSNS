import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from datetime import datetime
from common.operations.crossposts import earliest_post_time, crosspost_intents, preview_crossposts
from common.operations.models import ContractError

ROOT=Path(__file__).resolve().parents[1]
def dt(t): return datetime.fromisoformat(t)
class CrosspostTests(unittest.TestCase):
    def setUp(self):
        self.rule=dict(id='r',owner_account_id='personal',source_connection_id='personal.youtube',destination_connection_id='dept.tiktok',trigger={'phase':'published'},allowed_slots=['morning','evening'],transform_id='video',delivery_owner='legacy',enabled=True,activation_evidence=[],delay_seconds=1800,delay_owner='legacy_queue_add',min_gap_seconds=10800,window={'start':'07:00','end':'23:00','timezone':'Asia/Seoul'},dedupe_strategy='youtube_id')
        self.event=dict(content_id='c',revision=1,owner_account_id='personal',source_connection_id='personal.youtube',phase='published',slot='morning',source_public_at='2026-10-30T08:00:00+09:00')
    def registry(self, rule=None): return SimpleNamespace(crossposts={'r':rule or self.rule},connections={'dept.tiktok':SimpleNamespace(account_id='dept',platform='tiktok')})
    def test_delay_gap_window(self):
        for source,last,expected in [('08:00',None,'2026-10-30T08:30:00+09:00'),('08:00','2026-10-30T07:00:00+09:00','2026-10-30T10:00:00+09:00'),('22:30',None,'2026-10-31T07:00:00+09:00')]:
            self.assertEqual(earliest_post_time(self.rule,dt('2026-10-30T'+source+':00+09:00'),dt(last) if last else None),dt(expected))
    def test_delay_owned_by_source_is_not_added_twice(self):
        self.assertEqual(earliest_post_time({**self.rule,'delay_owner':'source'},dt('2026-10-30T08:30:00+09:00'),None),dt('2026-10-30T08:30:00+09:00'))
    def test_invalid_time_or_delay_owner_rejected(self):
        with self.assertRaises(ContractError): earliest_post_time(self.rule,dt('2026-10-30T08:00:00'),None)
        with self.assertRaises(ContractError): earliest_post_time({**self.rule,'delay_owner':'mystery'},dt(self.event['source_public_at']),None)
    def test_legacy_disabled_unknown_never_create_intents(self):
        for changes,status in [({},'observe_legacy'),({'enabled':False},'disabled'),({'enabled':None},'unknown')]:
            registry=self.registry({**self.rule,**changes})
            self.assertEqual(crosspost_intents(self.event,registry),())
            result=preview_crossposts(self.event,registry)[0]
            self.assertEqual(result['status'],status); self.assertFalse(result['execution_enabled'])
            self.assertEqual(result['owner_account_id'],'personal'); self.assertEqual(result['destination_account_id'],'dept')
    def test_managed_rule_checks_owner_slot_and_flags(self):
        rule={**self.rule,'delivery_owner':'managed','conditions':{'all':[{'field':'visibility','op':'eq','value':'public'},{'field':'description','op':'not_contains','value':'쿠팡'}]}}
        event={**self.event,'visibility':'public','description':'교육'}
        self.assertEqual(len(crosspost_intents(event,self.registry(rule))),1)
        for changed in [{'owner_account_id':'dept'},{'slot':'noon'},{'visibility':'private'},{'description':'쿠팡 링크'}]:
            self.assertEqual(crosspost_intents({**event,**changed},self.registry(rule)),())
    def test_catalog_separates_conditions_and_activation_evidence(self):
        catalog=json.loads((ROOT/'ax-console/config/crossposts.json').read_text())
        self.assertEqual(catalog['schema_version'],1)
        rules={r['id']:r for r in catalog['rules']}
        short=rules['geoai-short.tiktok']; generic=rules['youtube-generic-personal.tiktok']
        self.assertNotEqual(short['conditions'],generic['conditions'])
        self.assertTrue(all(r['delivery_owner']=='legacy' for r in rules.values()))
        self.assertGreaterEqual(len(rules),20)
        evidence=short['activation_evidence']; self.assertIn({'kind':'config','key':'tiktok_web.daily','value':True},evidence)
        self.assertIn({'kind':'config','key':'tiktok.enabled','value':False},evidence)
        self.assertIn({'kind':'installed_plist','key':'tiktok_queue','present':False,'loaded':None,'disabled':None},evidence)
    def test_explicit_threads_override(self):
        rules=json.loads((ROOT/'ax-console/config/crossposts.json').read_text())['rules']; rule=next(r for r in rules if r['id']=='geoai.threads')
        rule={**rule,'delivery_owner':'managed','enabled':True}
        event={**self.event,'source_connection_id':rule['source_connection_id'],'slot':'morning','blogger_status':'published','threads':True,'no_video':False}
        self.assertEqual(len(crosspost_intents(event,self.registry(rule))),1)
        self.assertEqual(crosspost_intents({**event,'threads':False},self.registry(rule)),())

    def test_preview_does_not_mutate_deep_frozen_registry(self):
        from common.operations.registry import load_registry
        registry=load_registry(ROOT/'ax-console/config/operations.json')
        before=registry.to_dict()
        preview_crossposts(self.event,registry)
        self.assertEqual(registry.to_dict(),before)
        self.assertEqual(crosspost_intents(self.event,registry),())
    def test_queue_window_start_inclusive_end_exclusive(self):
        for source,expected in [('06:30','2026-10-30T07:00:00+09:00'),('22:29','2026-10-30T22:59:00+09:00'),('22:30','2026-10-31T07:00:00+09:00')]:
            self.assertEqual(earliest_post_time(self.rule,dt('2026-10-30T'+source+':00+09:00')),dt(expected))
    def test_source_schedule_is_the_base_not_preview_clock(self):
        rule={**self.rule,'source_time_basis':'youtube_scheduled_at_or_upload_at'}
        self.assertEqual(earliest_post_time(rule,dt('2026-11-01T08:00:00+09:00')),dt('2026-11-01T08:30:00+09:00'))
