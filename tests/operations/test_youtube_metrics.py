"""공개 검증된 YouTube 맥락과 통계 조회의 결속. 가짜 서비스·SDK만 사용."""
from datetime import datetime,timezone
import unittest

from common.operations.content_store import StoreError
from common.operations.metrics import MetricsContext
from common.operations.youtube_metrics import YouTubeMetricsCollector
from common.publishers.youtube_services import GoogleYoutubeServices
from tests.publishers import test_youtube as google

NOW=datetime(2026,11,2,tzinfo=timezone.utc)

def context(**changes):
    values=dict(delivery_id='delivery',platform='youtube',content_id='content',content_revision=1,manifest_hash='manifest',
        owner_account_id='personal',destination_account_id='dept',connection_id='dept.youtube',target_id='UC-dept',remote_id='remote',verified_at=NOW.isoformat())
    return MetricsContext(**dict(values,**changes))


def video(**changes):
    return dict(dict(id='remote',snippet=dict(channelId='UC-dept'),status=dict(privacyStatus='public'),statistics=dict(viewCount='12',likeCount='3',commentCount='0')),**changes)


class FakeServices:
    def __init__(self,row=None):self.row=video() if row is None else row;self.calls=[]
    def read_statistics(self,target,remote_id):self.calls.append((target,remote_id));return self.row


class YoutubeMetricsTests(unittest.TestCase):
    def test_constructor_is_inert_and_explicit_collection_has_no_publication_calls(self):
        calls=[];services=FakeServices()
        def factory(ctx):calls.append(ctx);return services
        collector=YouTubeMetricsCollector(factory,clock=lambda:NOW)
        self.assertEqual(calls,[]);self.assertEqual(services.calls,[])
        ctx=context();result=collector(ctx,'remote')
        self.assertEqual(calls,[ctx]);self.assertEqual(services.calls,[(dict(platform='youtube',target_id='UC-dept',expected_login_subject='UC-dept'),'remote')])
        self.assertEqual(result.status,'ok');self.assertEqual(dict(result.values),dict(views=12,likes=3,comments=0))
        self.assertEqual(result.definition_id,'youtube.views');self.assertEqual(result.basis,'lifetime')
        self.assertEqual(result.observed_at,NOW.isoformat());self.assertEqual(result.source,{})
        self.assertEqual(result.remote_id,'remote');self.assertEqual(result.target_id,'UC-dept')

    def test_missing_optional_statistics_are_omitted_and_unknown_fields_never_escape(self):
        services=FakeServices(video(statistics=dict(viewCount='0',secret='PRIVATE',subscriberCount='500')))
        result=YouTubeMetricsCollector(lambda _:services,clock=lambda:NOW)(context(),'remote')
        self.assertEqual(result.status,'ok');self.assertEqual(dict(result.values),{'views':0});self.assertNotIn('PRIVATE',str(result.to_dict()))

    def test_invalid_metric_values_return_sanitized_error_without_raw_payload(self):
        for value in (True,-1,1.5,'-1','1.0','１','',str(2**63),'0'*21,None):
            for key in ('viewCount','likeCount','commentCount'):
                row=video();row['statistics'][key]=value
                result=YouTubeMetricsCollector(lambda _:FakeServices(row),clock=lambda:NOW)(context(),'remote')
                self.assertEqual(result.status,'error',(key,value));self.assertEqual(dict(result.values),{});self.assertEqual(result.source,{})
        for value in (2**63-1,str(2**63-1)):
            result=YouTubeMetricsCollector(lambda _:FakeServices(video(statistics={'viewCount':value})),clock=lambda:NOW)(context(),'remote')
            self.assertEqual(result.status,'ok');self.assertEqual(result.values['views'],2**63-1)

    def test_invalid_context_is_rejected_before_service_factory(self):
        calls=[];collector=YouTubeMetricsCollector(lambda ctx:calls.append(ctx))
        for changes in ({'platform':'x'},{'owner_account_id':'unknown'},{'destination_account_id':'unknown'},{'connection_id':'personal.youtube'},{'target_id':''},{'verified_at':'invalid'}):
            with self.assertRaises(StoreError):collector(context(**changes),'remote')
        with self.assertRaises(StoreError):collector(context(),'other')
        self.assertEqual(calls,[])

    def test_not_found_private_wrong_identity_and_exceptions_are_error_not_zero(self):
        for row in ({},video(id='another'),video(snippet={'channelId':'UC-other'}),video(status={'privacyStatus':'private'}),video(statistics={})):
            result=YouTubeMetricsCollector(lambda _:FakeServices(row),clock=lambda:NOW)(context(),'remote')
            self.assertEqual(result.status,'error');self.assertEqual(dict(result.values),{})
        def fail(_):raise RuntimeError('PRIVATE TOKEN')
        result=YouTubeMetricsCollector(fail)(context(),'remote');self.assertEqual(result.status,'error');self.assertNotIn('PRIVATE',str(result.to_dict()))
        result=YouTubeMetricsCollector(lambda _:FakeServices(),clock=lambda:'bad')(context(),'remote');self.assertEqual(result.status,'error')

    def test_google_statistics_read_is_bound_to_authenticated_channel_and_public_single_id(self):
        fake=google.FakeGoogle('dept');fake.videos=[video()]
        service=GoogleYoutubeServices(google.Client(fake),media_factory=lambda *_:self.fail('media factory used'))
        target=dict(platform='youtube',target_id='UC-dept',expected_login_subject='UC-dept')
        self.assertEqual(service.read_statistics(target,'remote'),video())
        self.assertEqual(fake.calls,[('channels.list',dict(part='id,contentDetails',mine=True)),('videos.list',dict(part='snippet,status,statistics',id='remote'))])
        self.assertFalse(any('insert' in name for name,_ in fake.calls))
        for rows in ([],[video(),video()],[video(id='other')],[video(snippet={'channelId':'wrong'})],[video(status={'privacyStatus':'private'})]):
            fake.videos=rows;self.assertIsNone(service.read_statistics(target,'remote'))
        fake.calls.clear();fake.channel='UC-other';self.assertIsNone(service.read_statistics(target,'remote'));self.assertFalse(any(name=='videos.list' for name,_ in fake.calls))

    def test_google_statistics_invalid_remote_id_never_reads_sdk(self):
        fake=google.FakeGoogle('dept');service=GoogleYoutubeServices(google.Client(fake),media_factory=lambda *_:None)
        for remote in ('',None,True):self.assertIsNone(service.read_statistics(dict(target_id='UC-dept'),remote))
        self.assertEqual(fake.calls,[])
