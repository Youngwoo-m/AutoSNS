"""외부 실행 없는 로컬 문구 규칙 시험."""
import copy
import re
import unittest
from unittest.mock import patch
from common.operations.packaging_rules import build_packaging_preview


class PackagingRulesTests(unittest.TestCase):
    def test_korean_unicode_zero_width_duplicates_and_length(self):
        snapshot = {'id':'c', 'revision':2, 'title':'  가이드  ', 'original':'안전 점검',
                    'sources':[{'url':'https://example.org/proof', 'note':'근거'}], 'secret':'SECRET'}
        before_snapshot = copy.deepcopy(snapshot)
        preview = build_packaging_preview(snapshot, platform='youtube', keywords=(' 안전 ', '안전', '점검\u200b'))
        self.assertEqual(snapshot, before_snapshot)
        self.assertLessEqual(len(preview['candidates']), 3)
        self.assertEqual('가이드', preview['candidates'][0]['title'])
        self.assertTrue(any(f['code']=='invisible_control' for f in preview['findings']))
        self.assertNotIn('SECRET', str(preview))
        self.assertIn('search_volume', preview['unavailable_fields'])
        self.assertNotIn('ctr', preview)
        for candidate in preview['candidates']:
            self.assertLessEqual(len(candidate['title']), 300)
            self.assertLessEqual(len(candidate['hashtags']),10)
            self.assertEqual(len(candidate['hashtags']),len(set(candidate['hashtags'])))
        long = build_packaging_preview({'title':'가'*301},platform='youtube')
        self.assertEqual([],long['candidates'])
        self.assertIn('title_too_long',[f['code'] for f in long['findings']])
        with self.assertRaises(ValueError):build_packaging_preview(snapshot,platform='youtube',keywords=('가'*51,))
        with self.assertRaises(ValueError):build_packaging_preview(snapshot,platform='youtube',keywords=('가',)*21)

    def test_candidate_changes_only_input_vocabulary(self):
        snapshot={'title':'안전 점검', 'original':'현장 확인', 'sources':[{'url':'https://example.org/a','note':'자료'}]}
        with patch('urllib.request.urlopen',side_effect=AssertionError('fetch')), patch('subprocess.run',side_effect=AssertionError('process')):
            first=build_packaging_preview(snapshot,platform='naver_blog',keywords=('현장','확인'))
            self.assertEqual(first,build_packaging_preview(snapshot,platform='naver_blog',keywords=('현장','확인')))
        words=set(re.findall(r'\w+',snapshot['title']+' '+snapshot['original']))
        for candidate in first['candidates']:
            self.assertLessEqual(set(re.findall(r'\w+',candidate['title'])),words)
            self.assertLessEqual(set(candidate['hashtags']),{'#현장','#확인'})
        self.assertEqual([{'url':'https://example.org/a'}],first['evidence_refs'])
        self.assertNotIn('tags',first)
