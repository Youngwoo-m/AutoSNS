"""고정 공식 conformance와 순수 X 텍스트 변환을 오프라인으로 확인한다."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from common.operations.models import ContractError
from common.publishers.x_payloads import PREPARED_KEYS, build_x_payload, validate_x_text
from common.publishers.vendor.twitter_text import parse_tweet, extract_urls, extract_urls_with_indices
from common.publishers.vendor.twitter_text.config import config
from tests.publishers.test_instagram_media_sources import context

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures/x-twitter-text'


def ctx(**over):
    return context(platform='x', options={'text_only':True,'visibility':'public'}, connection_id='dept.x', **over)


def snapshot(current, text='  원고 https://example.com/long/path 그대로\n'):
    return dict(id=current.content_id,revision=current.content_revision,manifest_hash=current.manifest_hash,
                owner_account_id=current.owner_account_id,original=text,variants=[],assets=[{'id':'keep-original-asset'}])


class XPayloadTests(unittest.TestCase):
    def test_prepared_exact_binding_preserves_text_assets_and_whitespace(self):
        current = ctx()
        source = snapshot(current)
        before = deepcopy(source)
        with patch('builtins.open',side_effect=AssertionError('외부 읽기 금지')), \
             patch('subprocess.run',side_effect=AssertionError('프로세스 금지')):
            result = build_x_payload(source,current)
        self.assertEqual(set(result),set(PREPARED_KEYS))
        self.assertEqual(result['platform'],'x')
        self.assertEqual(result['owner_account_id'],'personal')
        self.assertEqual(result['destination_account_id'],'dept')
        self.assertEqual(result['text'],source['original'])
        self.assertEqual(result['body_sha256'],hashlib.sha256(source['original'].encode()).hexdigest())
        self.assertEqual(result['media_sha256'],[])
        self.assertEqual(source,before)

    def test_destination_unique_variant_and_malformed_variants(self):
        current = ctx()
        source = snapshot(current)
        selected = {'destination_account_id':'dept','platform':'x','text':' 선택한 원문 https://example.com/\n'}
        source['variants'] = [{'destination_account_id':'personal','platform':'x','text':'다른 계정'},
                              {'destination_account_id':'dept','platform':'threads','text':'다른 플랫폼'},selected]
        self.assertEqual(build_x_payload(source,current)['text'],selected['text'])
        for variants in (source['variants']+[selected], [selected,None], 'bad'):
            with self.subTest(variants=variants):
                with self.assertRaises(ContractError):
                    build_x_payload({**source,'variants':variants},current)
        with self.assertRaises(ContractError):
            build_x_payload({**source,'variants':[{**selected,'text':None}]},current)

    def test_real_context_binding_options_and_revision_types(self):
        current = ctx()
        source = snapshot(current)
        with self.assertRaises(ContractError):
            build_x_payload(source, object())
        for changes in ({'id':'other'}, {'revision':True}, {'manifest_hash':'b'*64}, {'owner_account_id':'dept'}):
            with self.subTest(changes=changes):
                with self.assertRaises(ContractError):
                    build_x_payload({**source,**changes},current)
        for options in ({}, {'text_only':False}, {'text_only':True,'visibility':'private'},
                        {'text_only':True,'unexpected':True}):
            with self.subTest(options=options):
                with self.assertRaises(ContractError):
                    build_x_payload(source,replace(current,options=options))
        with self.assertRaises(ContractError):
            build_x_payload(source,replace(current,platform='threads'))

    def test_weighted_boundaries_cjk_long_url_emoji_and_nfc(self):
        accepted = ['a'*280, '한'*140, '👨🏽\u200d💻'*140, '👨\u200d👩\u200d👧\u200d👦'*140,
                    '🇰🇷'*140, '1️⃣'*140, 'e\u0301'*280, 'a'*256+' https://example.com/'+('p'*500), 'a'*278+'\r\n']
        for text in accepted:
            with self.subTest(text=text[:20]):
                self.assertIs(validate_x_text(text),text)
        for text in ('a'*281,'한'*141,'👨🏽\u200d💻'*141,'a'*257+' https://example.com/'+('p'*500), 'a'*279+'\r\n'):
            with self.subTest(text=text[:20]):
                with self.assertRaises(ContractError):validate_x_text(text)

    def test_invalid_blank_nul_surrogates_and_official_invalid_characters(self):
        for text in ('', ' \n\t', '\x00', 'a\ufeff', 'a\ufffe', 'a\uffff', '\ud800', '\udfff',None,False):
            with self.subTest(text=repr(text)):
                with self.assertRaises(ContractError):validate_x_text(text)


class OfficialTwitterTextConformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = json.loads((FIXTURES/'conformance.json').read_text())

    def test_all_44_weighted_emoji_nfc_and_directional_vectors_exact_results(self):
        total=0
        for group,rows in self.corpus['validation'].items():
            options = {**config['version2'],'emoji_parsing_enabled':False} if group=='WeightedTweetsCounterTest' else config['defaults']
            for row in rows:
                total+=1
                with self.subTest(group=group,description=row['description']):
                    self.assertEqual(parse_tweet(row['text'],options).asdict(),row['expected'])
                    if group!='WeightedTweetsCounterTest':
                        if row['expected']['valid'] and row['text'].strip():
                            self.assertEqual(validate_x_text(row['text']),row['text'])
                        else:
                            with self.assertRaises(ContractError):validate_x_text(row['text'])
        self.assertEqual(total,44)

    def test_all_1682_url_extraction_indices_and_tld_vectors(self):
        total=0
        for section in ('extraction','tlds'):
            for group,rows in self.corpus[section].items():
                for row in rows:
                    total+=1
                    with self.subTest(group=group,description=row['description']):
                        if row['expected'] and isinstance(row['expected'][0],dict):
                            actual=extract_urls_with_indices(row['text'])
                            for item in actual:
                                item['indices']=[len(row['text'][:i].encode('utf-16-le'))//2 for i in item['indices']]
                        else:
                            actual=extract_urls(row['text'])
                        self.assertEqual(actual,row['expected'])
        self.assertEqual(total,1682)

    def test_fixture_and_pinned_artifact_provenance(self):
        provenance=json.loads((FIXTURES/'PROVENANCE.json').read_text())
        self.assertEqual(hashlib.sha256((FIXTURES/'conformance.json').read_bytes()).hexdigest(),provenance['conformance_sha256'])
        self.assertEqual(len(provenance['commit']),40)
