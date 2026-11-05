"""검증된 게시 맥락에 결속하는 YouTube 성과 수집기. 명시 호출 전에는 I/O가 없다."""
from collections.abc import Mapping
from datetime import datetime,timezone
import re

from .content_store import StoreError
from .metrics import MetricsContext
from .metrics_models import MetricResult,_time

_MAX_COUNT=2**63-1


def _count(value):
    if type(value) is int:
        parsed=value
    elif isinstance(value,str) and re.fullmatch(r'[0-9]{1,20}',value):
        parsed=int(value)
    else:
        raise ValueError('invalid_count')
    if not 0<=parsed<=_MAX_COUNT:
        raise ValueError('invalid_count')
    return parsed


def _nonempty(value):
    if not isinstance(value,str) or not value.strip() or '\x00' in value:
        return False
    try:value.encode('utf-8')
    except UnicodeError:return False
    return True


class YouTubeMetricsCollector:
    def __init__(self,services_factory,clock=None):
        if not callable(services_factory) or clock is not None and not callable(clock):
            raise StoreError('invalid')
        self.services_factory=services_factory
        self.clock=clock if clock is not None else lambda:datetime.now(timezone.utc)

    def __call__(self,ctx,remote_id):
        # 원장으로 만든 고정 맥락 이외의 계정·대상·원격 ID를 수집기에 넘기지 않는다.
        if (not isinstance(ctx,MetricsContext) or ctx.platform!='youtube'
                or not _nonempty(remote_id) or remote_id!=ctx.remote_id
                or ctx.owner_account_id not in ('personal','dept')
                or ctx.destination_account_id not in ('personal','dept')
                or ctx.connection_id!=ctx.destination_account_id+'.youtube'
                or not _nonempty(ctx.target_id)):
            raise StoreError('metrics_identity_mismatch')
        try:_time(ctx.verified_at)
        except StoreError:raise StoreError('metrics_identity_mismatch') from None
        failure=lambda:MetricResult('error',{},None,ctx.remote_id,ctx.target_id,'youtube.views',basis='lifetime')
        try:
            services=self.services_factory(ctx)
            target=dict(platform='youtube',target_id=ctx.target_id,expected_login_subject=ctx.target_id)
            raw=services.read_statistics(target,remote_id)
            if (not isinstance(raw,Mapping) or raw.get('id')!=ctx.remote_id
                    or not isinstance(raw.get('snippet'),Mapping) or raw['snippet'].get('channelId')!=ctx.target_id
                    or not isinstance(raw.get('status'),Mapping) or raw['status'].get('privacyStatus')!='public'
                    or not isinstance(raw.get('statistics'),Mapping)):
                return failure()
            stats=raw['statistics'];values={'views':_count(stats['viewCount'])}
            for key,name in (('likeCount','likes'),('commentCount','comments')):
                if key in stats:values[name]=_count(stats[key])
            return MetricResult('ok',values,self.clock(),ctx.remote_id,ctx.target_id,'youtube.views',basis='lifetime')
        except Exception:
            # 원문 응답·토큰·오류 메시지는 결과/로그/HTTP에 전달하지 않는다.
            return failure()
