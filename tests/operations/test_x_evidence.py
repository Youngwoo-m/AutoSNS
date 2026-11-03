"""승인 원문과 t.co 엔터티의 순수 대응 시험."""
import hashlib
import unittest
from common.operations.x_evidence import reconstruct_x_text,safe_x_url

SHORT='https://t.co/Ab123'
LONG='https://source.example.com/a?keep=1&keep=2#part'

def entity(prefix='',**changes):
    return dict(start=len(prefix),end=len(prefix)+len(SHORT),url=SHORT,expanded_url=LONG,**changes)

class XEvidenceTests(unittest.TestCase):
    def test_exact_original_and_distinct_remote_hash(self):
        self.assertEqual(reconstruct_x_text(' 원문 ',{},' 원문 ')['text'],' 원문 ')
        result=reconstruct_x_text('링크 '+SHORT,{'urls':[entity('링크 ')]},'링크 '+LONG)
        self.assertEqual(result['text'],'링크 '+LONG)
        self.assertEqual(result['remote_text_sha256'],hashlib.sha256(('링크 '+SHORT).encode()).hexdigest())
        self.assertNotEqual(result['remote_text_sha256'],result['body_sha256'])
        self.assertIsNone(reconstruct_x_text('원문',{},'원문 '))

    def test_emoji_codepoint_and_utf16_require_actual_exact_spans(self):
        prefix='😀 한글 '
        row=entity(prefix)
        for delta in (0,1):
            adjusted={**row,'start':row['start']+delta,'end':row['end']+delta}
            self.assertIsNotNone(reconstruct_x_text(prefix+SHORT,{'urls':[adjusted]},prefix+LONG))
        self.assertIsNone(reconstruct_x_text(prefix+SHORT,{'urls':[{**row,'start':1}]},prefix+LONG))

    def test_no_missing_duplicate_overlap_wrong_expansion_or_schema(self):
        row=entity()
        for rows in ([],[row,row],[{**row,'start':True}],[{**row,'end':999}],
                [{**row,'expanded_url':'https://wrong.example.com'}],[{**row,'extra':True}],
                [{k:v for k,v in row.items() if k!='expanded_url'}]):
            self.assertIsNone(reconstruct_x_text(SHORT,{'urls':rows},LONG))
        self.assertIsNone(reconstruct_x_text(SHORT,{'urls':[row],'extra':[]},LONG))
        self.assertIsNone(reconstruct_x_text(SHORT,{'urls':[row]*11},LONG))

    def test_redirect_destination_is_not_original_url_identity(self):
        row={**entity(),'expanded_url':'https://redirect.example.com','unwound_url':LONG}
        self.assertIsNone(reconstruct_x_text(SHORT,{'urls':[row]},LONG))
        self.assertIsNotNone(reconstruct_x_text(SHORT,{'urls':[row]},'https://redirect.example.com'))
        self.assertIsNone(reconstruct_x_text(SHORT,{'urls':[row]},LONG.replace('&keep=2','')))
        remote=SHORT+' '+SHORT
        rows=[entity(),{**entity(),'start':len(SHORT)+1,'end':len(remote)}]
        self.assertIsNotNone(reconstruct_x_text(remote,{'urls':rows},LONG+' '+LONG))
        self.assertIsNone(reconstruct_x_text(remote,{'urls':rows[:1]},LONG+' '+LONG))

    def test_safe_publication_urls_are_exact(self):
        for host in ('x.com','www.x.com','twitter.com','www.twitter.com'):
            for path in ('/user_name/status/123','/i/web/status/123'):
                url='https://'+host+path
                self.assertEqual(safe_x_url(url,'123'),url)
        for url in ('http://x.com/u/status/123','https://x.com:443/u/status/123',
                'https://u@x.com/u/status/123','https://evil.com/u/status/123',
                'https://x.com/u/status/123?token=x','https://x.com/u/status/123?',
                'https://x.com/u/status/123#','https://x.com/u/status/124',
                'https://x.com/u/status/123/','https://x.com/u/status/%31%32%33',
                'https://x.com/u/status/123\r\n','https://x.com/한글/status/123'):
            self.assertIsNone(safe_x_url(url,'123'))

    def test_crlf_and_eleven_url_posts_preserve_exact_original(self):
        self.assertEqual(reconstruct_x_text('첫줄\r\n다음줄',{},'첫줄\r\n다음줄')['text'],'첫줄\r\n다음줄')
        self.assertIsNone(reconstruct_x_text('첫줄\n다음줄',{},'첫줄\r\n다음줄'))
        urls=['https://t.co/X'+str(i) for i in range(11)]
        expanded=['https://example.org/'+str(i) for i in range(11)]
        remote=' '.join(urls);approved=' '.join(expanded);rows=[];position=0
        for short,long in zip(urls,expanded):
            rows.append(dict(start=position,end=position+len(short),url=short,expanded_url=long))
            position+=len(short)+1
        self.assertIsNotNone(reconstruct_x_text(remote,{'urls':rows},approved))
